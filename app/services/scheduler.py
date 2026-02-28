import logging
from datetime import datetime, timedelta, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import delete, select, update

from app.config import settings
from app.database import AsyncSessionLocal
from app.models import Article
from app.services import feed_ingestion, summariser
from app.services.activity_log import log_activity

logger = logging.getLogger(__name__)

UTC = timezone.utc
STUCK_THRESHOLD_MINUTES = 5


def create_scheduler() -> AsyncIOScheduler:
    scheduler = AsyncIOScheduler(timezone="UTC")
    scheduler.add_job(
        ingest_and_summarise,
        "interval",
        minutes=settings.FETCH_INTERVAL_MINUTES,
        id="fetch_job",
        replace_existing=True,
    )
    scheduler.add_job(
        purge_old_articles,
        "cron",
        hour=2,
        minute=0,
        id="purge_job",
        replace_existing=True,
    )
    scheduler.add_job(
        watchdog_stuck_articles,
        "interval",
        minutes=10,
        id="watchdog_job",
        replace_existing=True,
    )
    scheduler.add_job(
        retry_and_summarise_failed,
        "interval",
        minutes=2,
        id="retry_failed_job",
        replace_existing=True,
    )
    return scheduler


async def ingest_and_summarise() -> None:
    async with AsyncSessionLocal() as db:
        stats = await feed_ingestion.ingest_all_feeds(db)
        await summariser.process_pending_articles(db)
        logger.info("Cycle complete: %s", stats)


async def retry_and_summarise_failed() -> None:
    """
    Auto-retry: resets all 'failed' articles back to 'pending' every 2 minutes,
    then triggers summarisation. Ensures failed articles are never permanently stuck.
    """
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Article)
            .where(Article.summary_status == "failed")
            .values(summary_status="pending")
        )
        await db.commit()
        count = result.rowcount
        if count > 0:
            log_activity("warn", "retry", f"Auto-retry: resetting {count} failed articles → pending")
            logger.info("Auto-retry: reset %d failed articles to pending", count)
            await summariser.process_pending_articles(db)
        else:
            logger.debug("Auto-retry: no failed articles found")


async def purge_old_articles() -> None:
    """
    Delete articles older than ARTICLE_RETENTION_DAYS.
    Protection: never delete the only done articles for a category —
    if a category has NO done articles within the retention window,
    its older done articles are kept so the category never shows 0.
    """
    async with AsyncSessionLocal() as db:
        cutoff = datetime.now(UTC) - timedelta(days=settings.ARTICLE_RETENTION_DAYS)

        # Categories that have at least 1 done article WITHIN the retention window
        recent_result = await db.execute(
            select(Article.category)
            .where(Article.summary_status == "done", Article.fetched_at >= cutoff)
            .distinct()
        )
        safe_categories = [row[0] for row in recent_result.all()]

        # Always delete old non-done articles (pending/failed that aged out will never summarise)
        r1 = await db.execute(
            delete(Article).where(
                Article.fetched_at < cutoff,
                Article.summary_status != "done",
            )
        )

        # Delete old done articles only for categories that have recent done articles
        r2_count = 0
        if safe_categories:
            r2 = await db.execute(
                delete(Article).where(
                    Article.fetched_at < cutoff,
                    Article.summary_status == "done",
                    Article.category.in_(safe_categories),
                )
            )
            r2_count = r2.rowcount

        await db.commit()
        total = r1.rowcount + r2_count
        log_activity("info", "system", f"Purge: removed {total} old articles (retained done articles for low-volume categories)")
        logger.info("Purged %d old articles", total)


async def watchdog_stuck_articles() -> None:
    """
    Self-healing watchdog: finds articles stuck in 'processing'
    for longer than STUCK_THRESHOLD_MINUTES and resets them to 'pending'
    so they get re-summarised on the next cycle.
    """
    cutoff = datetime.now(UTC) - timedelta(minutes=STUCK_THRESHOLD_MINUTES)
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            update(Article)
            .where(Article.summary_status == "processing")
            .where(Article.fetched_at < cutoff)
            .values(summary_status="pending")
        )
        await db.commit()
        if result.rowcount > 0:
            log_activity("warn", "system", f"Watchdog: reset {result.rowcount} stuck 'processing' articles → pending")
            logger.warning(
                "Watchdog: reset %d stuck articles back to pending",
                result.rowcount,
            )
        else:
            logger.debug("Watchdog: no stuck articles found")
