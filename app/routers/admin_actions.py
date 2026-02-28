"""
Admin action endpoints — manual triggers & monitoring.
All routes require admin session cookie (same auth as /admin panel).
Mounted at /admin/actions/
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func, select, update

from app.database import AsyncSessionLocal
from app.models import Article
from app.services.activity_log import ACTIVITY_LOG, log_activity
from app.services.summariser import process_pending_articles

router = APIRouter(prefix="/admin/actions", tags=["admin-actions"])
logger = logging.getLogger(__name__)


def require_admin(request: Request) -> None:
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Admin authentication required")


@router.get("/status")
async def summarisation_status(request: Request):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        count_result = await db.execute(
            select(Article.summary_status, func.count())
            .group_by(Article.summary_status)
        )
        counts = {row[0]: row[1] for row in count_result.all()}

        proc_result = await db.execute(
            select(Article.id, Article.title, Article.source_name)
            .where(Article.summary_status == "processing")
            .order_by(Article.fetched_at.asc())
            .limit(5)
        )
        processing_articles = [
            {"id": r[0], "title": r[1][:70] if r[1] else "", "source": r[2] or ""}
            for r in proc_result.all()
        ]

    return JSONResponse({
        "pending":             counts.get("pending", 0),
        "processing":          counts.get("processing", 0),
        "done":                counts.get("done", 0),
        "failed":              counts.get("failed", 0),
        "total":               sum(counts.values()),
        "processing_articles": processing_articles,
    })


@router.get("/activity")
async def get_activity(request: Request):
    """Returns recent pipeline activity events for the live log view."""
    require_admin(request)
    return JSONResponse(list(ACTIVITY_LOG)[:60])


@router.post("/trigger-summarise")
async def trigger_summarise(request: Request):
    require_admin(request)
    log_activity("info", "system", "Manual summarisation triggered from console")
    logger.info("Manual summarisation triggered from admin panel")
    asyncio.create_task(_run_summarise())
    return JSONResponse({"message": "Summarisation started", "status": "running"})


@router.post("/retry-failed")
async def retry_failed(request: Request):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Article)
            .where(Article.summary_status == "failed")
            .values(summary_status="pending")
        )
        await db.commit()
        count = result.rowcount
    log_activity("warn", "retry", f"Manual retry: reset {count} failed articles → pending")
    logger.info("Admin reset %d failed articles to pending", count)
    asyncio.create_task(_run_summarise())
    return JSONResponse({
        "message": f"Reset {count} failed articles to pending. Summarisation started.",
        "reset_count": count,
        "status": "running",
    })


@router.post("/trigger-fetch")
async def trigger_fetch(request: Request):
    require_admin(request)
    from app.services.scheduler import ingest_and_summarise
    log_activity("info", "fetch", "Manual fetch + summarise cycle triggered from console")
    logger.info("Manual fetch+summarise triggered from admin panel")
    asyncio.create_task(ingest_and_summarise())
    return JSONResponse({"message": "Fetch + summarise cycle started", "status": "running"})


async def _run_summarise() -> None:
    async with AsyncSessionLocal() as db:
        await process_pending_articles(db)
