import logging
from typing import AsyncGenerator

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


engine = create_async_engine(settings.DATABASE_URL, echo=settings.DEBUG)


@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_conn, connection_record):
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


AsyncSessionLocal = async_sessionmaker(
    engine, class_=AsyncSession, expire_on_commit=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        yield session


async def run_migrations() -> None:
    """
    Apply any missing column migrations to existing tables.
    Safe to run on a fresh DB (table won't exist yet — create_all_tables handles that).
    """
    async with engine.begin() as conn:
        result = await conn.execute(text("PRAGMA table_info(articles)"))
        columns = [row[1] for row in result.fetchall()]
        if columns and "image_url" not in columns:
            await conn.execute(text("ALTER TABLE articles ADD COLUMN image_url TEXT"))
            logger.info("Migration: added image_url column to articles table")


async def create_all_tables() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
