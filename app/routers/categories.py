import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Category
from app.schemas import CategorySchema

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/categories", response_model=list[CategorySchema])
async def list_categories(
    db: AsyncSession = Depends(get_db),
) -> list[Category]:
    result = await db.execute(
        select(Category).where(Category.is_visible.is_(True))
    )
    return result.scalars().all()
