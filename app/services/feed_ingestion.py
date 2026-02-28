import asyncio
import logging
import re
from datetime import datetime, timedelta, timezone
from typing import Any

import feedparser
import trafilatura
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Article, Source
from app.services.categoriser import categorise
from app.services.deduplication import compute_url_hash, is_duplicate
from app.services.activity_log import log_activity

logger = logging.getLogger(__name__)


async def extract_content_and_image(url: str, entry: dict) -> tuple[str, str | None]:
    """
    3-tier content extraction with OG image capture.
    Returns (content, image_url). Never returns empty content if any source available.
    """
    content = ""
    image_url: str | None = None

    # Tier 1: trafilatura bare_extraction — gets text AND image in one pass
    try:
        loop = asyncio.get_event_loop()
        html = await asyncio.wait_for(
            loop.run_in_executor(None, trafilatura.fetch_url, url),
            timeout=10.0,
        )
        if html:
            result = trafilatura.bare_extraction(
                html,
                include_comments=False,
                include_tables=False,
                no_fallback=False,
                favor_precision=False,
            )
            if result:
                extracted_text = result.get("text") or ""
                if len(extracted_text.strip()) > 100:
                    content = extracted_text.strip()[:3000]
                # Always capture image even if text was short
                image_url = result.get("image") or None
    except Exception:
        pass

    # Tier 2: feedparser entry content fields (if content still empty)
    if not content:
        for field in ["content", "summary_detail", "summary", "description"]:
            val = entry.get(field)
            if isinstance(val, list) and val:
                val = val[0].get("value", "")
            if val and isinstance(val, str) and len(val.strip()) > 50:
                clean = re.sub(r"<[^>]+>", " ", val).strip()
                clean = re.sub(r"\s+", " ", clean)
                if len(clean) > 50:
                    content = clean[:3000]
                    break

    # Tier 3: title + source as last resort
    if not content:
        title = entry.get("title", "")
        source = entry.get("source", {})
        source_title = source.get("title", "") if isinstance(source, dict) else ""
        content = f"{title}. {source_title}".strip()

    return content, image_url


async def ingest_all_feeds(db: AsyncSession) -> dict[str, Any]:
    result = await db.execute(
        select(Source).where(Source.is_active.is_(True), Source.source_type == "rss")
    )
    sources = result.scalars().all()

    feeds_processed = 0
    articles_added = 0
    articles_skipped = 0
    errors = 0

    backfill_cutoff = datetime.now(timezone.utc) - timedelta(
        days=settings.INITIAL_BACKFILL_DAYS
    )
    loop = asyncio.get_event_loop()

    for source in sources:
        try:
            feed = await loop.run_in_executor(None, feedparser.parse, source.url)
            feeds_processed += 1
            source_added = 0
            log_activity("info", "fetch", f"Fetching: {source.name}")

            for entry in feed.entries:
                try:
                    link = getattr(entry, "link", None)
                    if not link:
                        articles_skipped += 1
                        continue

                    published_at: datetime | None = None
                    if hasattr(entry, "published_parsed") and entry.published_parsed:
                        try:
                            published_at = datetime(
                                *entry.published_parsed[:6], tzinfo=timezone.utc
                            )
                        except Exception:
                            published_at = None

                    if published_at and published_at < backfill_cutoff:
                        articles_skipped += 1
                        continue

                    url_hash = compute_url_hash(link)
                    if await is_duplicate(db, url_hash):
                        articles_skipped += 1
                        continue

                    title = getattr(entry, "title", "Untitled") or "Untitled"

                    raw_content, image_url = await extract_content_and_image(link, entry)

                    category = categorise(title, raw_content)

                    article = Article(
                        url=link,
                        url_hash=url_hash,
                        title=title,
                        source_name=source.name,
                        category=category,
                        published_at=published_at,
                        raw_content=raw_content,
                        image_url=image_url,
                        summary_status="pending",
                    )
                    db.add(article)
                    source_added += 1
                    articles_added += 1

                except Exception as exc:
                    logger.warning(
                        "Error processing entry from %s: %s", source.name, exc
                    )
                    articles_skipped += 1
                    continue

            await db.commit()

            source.last_fetched_at = datetime.now(timezone.utc)
            source.article_count = (source.article_count or 0) + source_added
            source.consecutive_failures = 0
            await db.commit()
            if source_added > 0:
                log_activity("success", "fetch", f"{source.name}: {source_added} new article{'s' if source_added != 1 else ''}")

        except Exception as exc:
            errors += 1
            source.consecutive_failures = (source.consecutive_failures or 0) + 1
            try:
                await db.commit()
            except Exception:
                await db.rollback()
            logger.error("Feed error for %s (%s): %s", source.name, source.url, exc)
            log_activity("error", "fetch", f"Feed error: {source.name} — {exc}")
            continue

    return {
        "feeds_processed": feeds_processed,
        "articles_added": articles_added,
        "articles_skipped": articles_skipped,
        "errors": errors,
    }
