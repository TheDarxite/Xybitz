import asyncio
import logging

import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.models import Article
from app.services.activity_log import log_activity

logger = logging.getLogger(__name__)

def build_prompt(text: str, title: str = "") -> str:
    word_count = len(text.split())
    if word_count < 30:
        # Very short content — ask Ollama to expand from title context
        return (
            f"Write a 100-word cybersecurity news summary based on this title:\n"
            f"{text}\n"
            f"Focus on what happened, who was affected, and why it matters to security practitioners.\n"
            f"Summary:"
        )
    else:
        # Normal full content summarisation
        return (
            f"Summarise the following cybersecurity news article in exactly 100 words.\n"
            f"Write in plain English. No bullet points. No markdown. No headers.\n"
            f"Start directly with the key finding or event.\n"
            f"Article: {text}\n"
            f"Summary:"
        )


class SummarisationError(Exception):
    pass


class OllamaSummariser:
    def __init__(self) -> None:
        self._client = httpx.AsyncClient(timeout=120.0)
        self._semaphore = asyncio.Semaphore(settings.SUMMARISATION_CONCURRENCY)

    async def summarise(self, text: str, title: str = "", article_id: int = 0) -> str:
        truncated = text[:2000]
        prompt = build_prompt(truncated, title)

        async with self._semaphore:
            try:
                provider = settings.LLM_PROVIDER

                if provider == "ollama":
                    response = await self._client.post(
                        f"{settings.OLLAMA_BASE_URL}/api/generate",
                        json={
                            "model": settings.OLLAMA_MODEL,
                            "prompt": prompt,
                            "stream": False,
                        },
                        timeout=120.0,
                    )
                    response.raise_for_status()
                    data = response.json()
                    response_text = data.get("response", "").strip()
                    if not response_text or len(response_text) < 10:
                        raise SummarisationError(
                            f"Ollama returned empty/short response for article {article_id}"
                        )
                    return response_text

                elif provider == "openai":
                    response = await self._client.post(
                        "https://api.openai.com/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.OPENAI_API_KEY}"},
                        json={
                            "model": settings.OPENAI_MODEL,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                        timeout=60.0,
                    )
                    response.raise_for_status()
                    return response.json()["choices"][0]["message"]["content"].strip()

                elif provider == "groq":
                    response = await self._client.post(
                        "https://api.groq.com/openai/v1/chat/completions",
                        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
                        json={
                            "model": settings.GROQ_MODEL,
                            "messages": [{"role": "user", "content": prompt}],
                        },
                        timeout=60.0,
                    )
                    response.raise_for_status()
                    return response.json()["choices"][0]["message"]["content"].strip()

                else:
                    raise SummarisationError(f"Unknown LLM provider: {provider}")

            except SummarisationError:
                raise
            except Exception as exc:
                raise SummarisationError(f"Summarisation failed: {exc}") from exc

    async def close(self) -> None:
        await self._client.aclose()

    async def summarise_with_retry(self, text: str, article_id: int) -> str:
        for attempt in range(2):  # try twice
            try:
                return await self.summarise(text)
            except SummarisationError as e:
                if attempt == 0:
                    logger.warning(
                        "Retry article %d after failure: %s", article_id, e
                    )
                    await asyncio.sleep(5)
                else:
                    raise


_summariser = OllamaSummariser()


async def process_pending_articles(db: AsyncSession) -> dict:
    """
    Summarises pending articles with full self-healing guarantees:
    - Each article has its own try/except — one failure never kills the batch
    - Per-article DB commit — partial progress always saved
    - Timeout per article — never blocks the batch indefinitely
    - Returns stats dict for logging
    """
    # 1. Fetch pending articles
    result = await db.execute(
        select(Article)
        .where(Article.summary_status == "pending")
        .order_by(Article.fetched_at.asc())
        .limit(50)
    )
    articles = result.scalars().all()

    if not articles:
        logger.debug("No pending articles to summarise")
        return {"processed": 0, "done": 0, "failed": 0}

    total = len(articles)
    done_count = 0
    failed_count = 0

    logger.info("Starting summarisation: %d articles queued", total)

    # 2. Mark ALL as "processing" in one batch commit before any Ollama calls
    article_ids = [a.id for a in articles]
    await db.execute(
        update(Article)
        .where(Article.id.in_(article_ids))
        .values(summary_status="processing")
    )
    await db.commit()   # ← committed BEFORE Ollama calls start

    # 3. Summarise each article individually — fully isolated
    summariser = OllamaSummariser()

    async def process_one(article: Article, idx: int) -> None:
        nonlocal done_count, failed_count
        try:
            content = article.raw_content or article.title or ""
            summary = await summariser.summarise_with_retry(content, article.id)
            article.summary = summary
            article.summary_status = "done"
            done_count += 1
            log_activity("success", "summarise", f"Summarised: {article.title[:60]}" if article.title else "Summarised article")
            logger.info(
                "[%d/%d] ✓ Summarised: %s",
                idx + 1, total, article.title[:60],
            )
        except Exception as exc:
            article.summary_status = "failed"
            failed_count += 1
            log_activity("error", "summarise", f"Failed: {article.title[:60] if article.title else str(article.id)} — {exc}")
            logger.error(
                "[%d/%d] ✗ Failed article_id=%d: %s",
                idx + 1, total, article.id, exc, exc_info=False,
            )
        finally:
            # Per-article commit — progress ALWAYS saved regardless of outcome
            try:
                await db.commit()
            except Exception as commit_exc:
                logger.error(
                    "DB commit failed for article %d: %s", article.id, commit_exc
                )
                await db.rollback()

    # 4. Run with semaphore to control concurrency
    semaphore = asyncio.Semaphore(settings.SUMMARISATION_CONCURRENCY)

    async def guarded_process(article: Article, idx: int) -> None:
        async with semaphore:
            await process_one(article, idx)

    await asyncio.gather(*[
        guarded_process(article, idx)
        for idx, article in enumerate(articles)
    ])

    logger.info(
        "Summarisation batch complete: %d done, %d failed, %d total",
        done_count, failed_count, total,
    )
    return {"processed": total, "done": done_count, "failed": failed_count}
