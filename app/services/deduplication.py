import hashlib

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Article


def compute_url_hash(url: str) -> str:
    return hashlib.sha256(url.strip().lower().encode()).hexdigest()


async def is_duplicate(db: AsyncSession, url_hash: str) -> bool:
    result = await db.execute(
        select(Article).where(Article.url_hash == url_hash)
    )
    return result.scalar_one_or_none() is not None
