from datetime import datetime
from typing import Optional

from pydantic import BaseModel


class CategorySchema(BaseModel):
    id: int
    slug: str
    name: str
    color: str
    is_visible: bool

    model_config = {"from_attributes": True}


class ArticleSchema(BaseModel):
    id: int
    url: str
    title: str
    source_name: str
    category: str
    published_at: Optional[datetime]
    fetched_at: datetime
    summary: Optional[str]
    summary_status: str
    is_active: bool
    is_featured: bool

    model_config = {"from_attributes": True}


class PaginationMeta(BaseModel):
    page: int
    limit: int
    total: int
    total_pages: int
    prev_page: Optional[int]
    next_page: Optional[int]
