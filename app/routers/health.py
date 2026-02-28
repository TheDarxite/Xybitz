import logging

import httpx
from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Article, Source

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/health")
async def health_check(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    # Check Ollama / cloud LLM
    ollama_status = "n/a"
    if settings.LLM_PROVIDER == "ollama":
        ollama_status = "offline"
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                if resp.status_code == 200:
                    ollama_status = "online"
        except Exception:
            pass

    # Check DB
    db_status = "ok"
    articles_total = 0
    articles_pending = 0
    articles_failed = 0
    try:
        articles_total = (
            await db.execute(select(func.count(Article.id)))
        ).scalar_one()
        articles_pending = (
            await db.execute(
                select(func.count(Article.id)).where(
                    Article.summary_status == "pending"
                )
            )
        ).scalar_one()
        articles_failed = (
            await db.execute(
                select(func.count(Article.id)).where(
                    Article.summary_status == "failed"
                )
            )
        ).scalar_one()
    except Exception:
        db_status = "error"

    # Scheduler state
    scheduler = getattr(request.app.state, "scheduler", None)
    scheduler_status = "running" if scheduler and scheduler.running else "stopped"

    # Last fetch time
    last_fetch = None
    try:
        row = (
            await db.execute(
                select(Source.last_fetched_at)
                .where(Source.last_fetched_at.isnot(None))
                .order_by(Source.last_fetched_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if row:
            last_fetch = row.isoformat()
    except Exception:
        pass

    overall_status = "ok"
    if ollama_status == "offline" or db_status == "error":
        overall_status = "degraded"

    return {
        "status": overall_status,
        "ollama": ollama_status,
        "ollama_model": settings.OLLAMA_MODEL,
        "llm_provider": settings.LLM_PROVIDER,
        "db": db_status,
        "articles_total": articles_total,
        "articles_pending_summary": articles_pending,
        "articles_failed_summary": articles_failed,
        "scheduler": scheduler_status,
        "last_fetch": last_fetch,
    }
