"""
Admin action endpoints — manual triggers & monitoring.
All routes require admin session cookie (same auth as /admin panel).
Mounted at /admin/actions/
"""
import asyncio
import logging

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import delete, func, select, update

from app.database import AsyncSessionLocal
from app.models import Article, Category, Source
from app.services.activity_log import ACTIVITY_LOG, log_activity
from app.services.summariser import process_pending_articles

router = APIRouter(prefix="/admin/actions", tags=["admin-actions"])
logger = logging.getLogger(__name__)


def require_admin(request: Request) -> None:
    if not request.session.get("authenticated"):
        raise HTTPException(status_code=401, detail="Admin authentication required")


# ── Pipeline status ───────────────────────────────────────────────────────────

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


# ── Sources ───────────────────────────────────────────────────────────────────

@router.get("/sources")
async def get_sources(request: Request):
    """Returns feed source stats for the Sources tab in the console."""
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Source).order_by(Source.category, Source.name))
        sources = result.scalars().all()
    return JSONResponse([
        {
            "id": s.id,
            "name": s.name,
            "url": s.url,
            "category": s.category,
            "article_count": s.article_count,
            "last_fetched_at": s.last_fetched_at.isoformat() if s.last_fetched_at else None,
            "consecutive_failures": s.consecutive_failures,
            "is_active": s.is_active,
        }
        for s in sources
    ])


@router.patch("/sources/{source_id}/toggle-active")
async def toggle_source_active(request: Request, source_id: int):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Source).where(Source.id == source_id))
        source = result.scalar_one_or_none()
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        source.is_active = not source.is_active
        await db.commit()
        return JSONResponse({"id": source_id, "is_active": source.is_active})


@router.post("/sources")
async def create_source(request: Request):
    require_admin(request)
    body = await request.json()
    name = body.get("name", "").strip()
    url  = body.get("url", "").strip()
    category = body.get("category", "").strip()
    source_type = body.get("source_type", "rss").strip()
    if not name or not url or not category:
        raise HTTPException(status_code=400, detail="name, url, and category are required")
    async with AsyncSessionLocal() as db:
        src = Source(
            name=name,
            url=url,
            category=category,
            source_type=source_type,
            scrape_engine=body.get("scrape_engine") or None,
            list_selector=body.get("list_selector") or None,
            link_selector=body.get("link_selector") or None,
            rate_limit_seconds=int(body.get("rate_limit_seconds") or 60),
        )
        db.add(src)
        await db.commit()
        await db.refresh(src)
        return JSONResponse({
            "id": src.id, "name": src.name, "url": src.url, "category": src.category,
            "source_type": src.source_type, "is_active": src.is_active,
        })


@router.patch("/sources/{source_id}")
async def update_source(request: Request, source_id: int):
    require_admin(request)
    body = await request.json()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Source).where(Source.id == source_id))
        source = result.scalar_one_or_none()
        if not source:
            raise HTTPException(status_code=404, detail="Source not found")
        for field in ("name", "url", "category", "source_type", "scrape_engine",
                      "list_selector", "link_selector"):
            if field in body:
                setattr(source, field, body[field] or None if field not in ("name","url","category","source_type") else body[field].strip())
        if "rate_limit_seconds" in body:
            source.rate_limit_seconds = int(body["rate_limit_seconds"] or 60)
        if "is_active" in body:
            source.is_active = bool(body["is_active"])
        await db.commit()
        return JSONResponse({
            "id": source.id, "name": source.name, "url": source.url,
            "category": source.category, "source_type": source.source_type,
            "is_active": source.is_active,
        })


@router.delete("/sources/{source_id}")
async def delete_source(request: Request, source_id: int):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Source).where(Source.id == source_id)
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Source not found")
    return JSONResponse({"deleted": source_id})


# ── Articles ──────────────────────────────────────────────────────────────────

@router.get("/articles")
async def list_articles(
    request: Request,
    status: str | None = None,
    category: str | None = None,
    search: str | None = None,
    page: int = 1,
    per_page: int = 50,
):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        filters = []
        if status and status != "all":
            filters.append(Article.summary_status == status)
        if category and category != "all":
            filters.append(Article.category == category)
        if search:
            filters.append(Article.title.ilike(f"%{search}%"))

        total_result = await db.execute(
            select(func.count(Article.id)).where(*filters) if filters
            else select(func.count(Article.id))
        )
        total = total_result.scalar_one()

        offset = (page - 1) * per_page
        q = select(Article).order_by(Article.fetched_at.desc()).offset(offset).limit(per_page)
        if filters:
            q = q.where(*filters)
        result = await db.execute(q)
        articles = result.scalars().all()

    return JSONResponse({
        "total": total,
        "page": page,
        "per_page": per_page,
        "pages": max(1, (total + per_page - 1) // per_page),
        "articles": [
            {
                "id": a.id,
                "title": a.title,
                "source_name": a.source_name,
                "category": a.category,
                "summary_status": a.summary_status,
                "published_at": a.published_at.isoformat() if a.published_at else None,
                "fetched_at": a.fetched_at.isoformat() if a.fetched_at else None,
                "is_active": a.is_active,
                "is_featured": a.is_featured,
                "url": a.url,
            }
            for a in articles
        ],
    })


@router.delete("/articles/{article_id}")
async def delete_article(request: Request, article_id: int):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Article).where(Article.id == article_id)
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Article not found")
    return JSONResponse({"deleted": article_id})


@router.patch("/articles/{article_id}/toggle-active")
async def toggle_article_active(request: Request, article_id: int):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        article.is_active = not article.is_active
        await db.commit()
        return JSONResponse({"id": article_id, "is_active": article.is_active})


@router.patch("/articles/{article_id}/toggle-featured")
async def toggle_article_featured(request: Request, article_id: int):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        article.is_featured = not article.is_featured
        await db.commit()
        return JSONResponse({"id": article_id, "is_featured": article.is_featured})


@router.patch("/articles/{article_id}/reset")
async def reset_article_status(request: Request, article_id: int):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article).where(Article.id == article_id))
        article = result.scalar_one_or_none()
        if not article:
            raise HTTPException(status_code=404, detail="Article not found")
        article.summary_status = "pending"
        await db.commit()
        return JSONResponse({"id": article_id, "summary_status": "pending"})


@router.post("/articles/bulk")
async def bulk_article_action(request: Request):
    """Bulk action on multiple articles.
    Body: { "ids": [int, ...], "action": "delete" | "hide" | "show" | "reset" }
    """
    require_admin(request)
    body = await request.json()
    ids = body.get("ids", [])
    action = body.get("action", "")
    if not ids or action not in ("delete", "hide", "show", "reset"):
        raise HTTPException(status_code=400, detail="ids list and valid action required")

    async with AsyncSessionLocal() as db:
        if action == "delete":
            result = await db.execute(delete(Article).where(Article.id.in_(ids)))
            await db.commit()
            return JSONResponse({"action": action, "affected": result.rowcount})
        elif action == "hide":
            result = await db.execute(
                update(Article).where(Article.id.in_(ids)).values(is_active=False)
            )
            await db.commit()
            return JSONResponse({"action": action, "affected": result.rowcount})
        elif action == "show":
            result = await db.execute(
                update(Article).where(Article.id.in_(ids)).values(is_active=True)
            )
            await db.commit()
            return JSONResponse({"action": action, "affected": result.rowcount})
        elif action == "reset":
            result = await db.execute(
                update(Article)
                .where(Article.id.in_(ids))
                .values(summary_status="pending", summary=None, is_active=True)
            )
            await db.commit()
            return JSONResponse({"action": action, "affected": result.rowcount})


# ── Categories ────────────────────────────────────────────────────────────────

@router.get("/categories")
async def list_categories(request: Request):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category).order_by(Category.name))
        cats = result.scalars().all()
    return JSONResponse([
        {
            "id": c.id,
            "slug": c.slug,
            "name": c.name,
            "color": c.color,
            "is_visible": c.is_visible,
        }
        for c in cats
    ])


@router.post("/categories")
async def create_category(request: Request):
    require_admin(request)
    body = await request.json()
    slug = body.get("slug", "").strip().lower().replace(" ", "_")
    name = body.get("name", "").strip()
    color = body.get("color", "primary").strip()
    if not slug or not name:
        raise HTTPException(status_code=400, detail="slug and name are required")
    async with AsyncSessionLocal() as db:
        cat = Category(slug=slug, name=name, color=color)
        db.add(cat)
        await db.commit()
        await db.refresh(cat)
        return JSONResponse({"id": cat.id, "slug": cat.slug, "name": cat.name, "color": cat.color, "is_visible": cat.is_visible})


@router.patch("/categories/{category_id}")
async def update_category(request: Request, category_id: int):
    require_admin(request)
    body = await request.json()
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Category).where(Category.id == category_id))
        cat = result.scalar_one_or_none()
        if not cat:
            raise HTTPException(status_code=404, detail="Category not found")
        if "name" in body:
            cat.name = body["name"].strip()
        if "color" in body:
            cat.color = body["color"].strip()
        if "is_visible" in body:
            cat.is_visible = bool(body["is_visible"])
        await db.commit()
        return JSONResponse({"id": cat.id, "slug": cat.slug, "name": cat.name, "color": cat.color, "is_visible": cat.is_visible})


@router.delete("/categories/{category_id}")
async def delete_category(request: Request, category_id: int):
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            delete(Category).where(Category.id == category_id)
        )
        await db.commit()
        if result.rowcount == 0:
            raise HTTPException(status_code=404, detail="Category not found")
    return JSONResponse({"deleted": category_id})


# ── Pipeline controls ─────────────────────────────────────────────────────────

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


@router.post("/reset-all-done")
async def reset_all_done(request: Request):
    """Re-queue all summarised articles for fresh summarisation with the current prompt.
    Clears existing summaries and resets visibility — use after updating the prompt."""
    require_admin(request)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Article)
            .where(Article.summary_status == "done")
            .values(summary_status="pending", summary=None, is_active=True)
        )
        await db.commit()
        count = result.rowcount
    log_activity("warn", "system", f"Re-summarise all: reset {count} done articles → pending (prompt refresh)")
    logger.info("Admin reset %d done articles to pending for re-summarisation", count)
    asyncio.create_task(_run_summarise())
    return JSONResponse({
        "message": f"Reset {count} articles for re-summarisation. Running now.",
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
