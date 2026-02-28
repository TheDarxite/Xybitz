import json
import logging
import re
import urllib.parse
from datetime import date, datetime, timedelta, timezone
from math import ceil

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database import get_db
from app.models import Article, Category

logger = logging.getLogger(__name__)

router = APIRouter()
templates = Jinja2Templates(directory="app/templates")

PLACEHOLDER_IMAGE = "https://placehold.co/800x420/1a1a2e/ffffff?text=XYBITZ"

# Maps Bootstrap color names (used in Category.color field) to hex
_BOOTSTRAP_TO_HEX = {
    "danger":    "c0392b",
    "warning":   "d35400",
    "primary":   "1a56db",
    "info":      "0891b2",
    "success":   "057a55",
    "secondary": "4b5563",
    "purple":    "7c3aed",
    "dark":      "1f2937",
}


def _cat_hex(color: str) -> str:
    """Convert Bootstrap color name or #hex to a bare hex string."""
    if color.startswith("#"):
        return color.lstrip("#")
    return _BOOTSTRAP_TO_HEX.get(color, "4f46e5")


_SLUG_TO_COLOR = {
    "vulnerabilities": "danger",
    "malware":         "warning",
    "appsec":          "primary",
    "cloud_security":  "info",
    "compliance":      "success",
    "privacy":         "secondary",
    "threat_intel":    "purple",
    "ai_security":     "#6610f2",
}


def _placeholder_for(article) -> str:
    """Generate a category-coloured placeholder image URL using the article title."""
    color_name = _SLUG_TO_COLOR.get(getattr(article, "category", ""), "primary")
    bg = _cat_hex(color_name)
    raw_title = (article.title or "Xybitz")
    title = re.sub(r"[^\w\s\-\.\:]", "", raw_title)[:45].strip()
    encoded = urllib.parse.quote(title, safe="").replace("%20", "+")
    return f"https://placehold.co/800x420/{bg}/ffffff?text={encoded or 'Xybitz'}"


def _time_ago(dt: datetime | None) -> str:
    if not dt:
        return ""
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    diff = now - dt
    seconds = int(diff.total_seconds())
    if seconds < 60:
        return "just now"
    if seconds < 3600:
        mins = seconds // 60
        return f"{mins} minute{'s' if mins != 1 else ''} ago"
    if seconds < 86400:
        hrs = seconds // 3600
        return f"{hrs} hour{'s' if hrs != 1 else ''} ago"
    days = seconds // 86400
    return f"{days} day{'s' if days != 1 else ''} ago"


templates.env.filters["time_ago"] = _time_ago
templates.env.filters["tojson"] = lambda v: json.dumps(v, default=str)
templates.env.filters["cat_hex"] = _cat_hex


def _display_cutoff() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=settings.DISPLAY_DAYS)


def _date_filter():
    """SQLAlchemy filter: published_at >= cutoff, OR null published_at with recent fetched_at."""
    cutoff = _display_cutoff()
    return or_(
        Article.published_at >= cutoff,
        (Article.published_at.is_(None)) & (Article.fetched_at >= cutoff),
    )


def _article_placeholder(article) -> str:
    """Generate placeholder URL — used in templates via the article object."""
    return _placeholder_for(article)


templates.env.filters["placeholder_url"] = _article_placeholder


@router.get("/", response_class=HTMLResponse)
async def index(
    request: Request,
    category: str | None = None,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    filters = [
        Article.is_active.is_(True),
        Article.summary_status == "done",
        _date_filter(),
    ]
    if category and category != "all":
        filters.append(Article.category == category)

    ids_result = await db.execute(
        select(Article.id)
        .where(*filters)
        .order_by(Article.published_at.desc().nullslast())
    )
    article_ids = [row[0] for row in ids_result.all()]

    first_article = None
    if article_ids:
        art_result = await db.execute(
            select(Article).where(Article.id == article_ids[0])
        )
        first_article = art_result.scalar_one_or_none()

    cats_result = await db.execute(
        select(Category).where(Category.is_visible.is_(True))
    )
    categories = cats_result.scalars().all()

    today = date.today()
    today_count_result = await db.execute(
        select(func.count(Article.id)).where(
            Article.is_active.is_(True),
            func.date(Article.fetched_at) == today,
        )
    )
    total_today = today_count_result.scalar_one()

    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "article": first_article,
            "article_ids": article_ids,
            "categories": categories,
            "current_category": category or "all",
            "total_today": total_today,
            "placeholder_image": PLACEHOLDER_IMAGE,
        },
    )


@router.get("/articles/card/{article_id}", response_class=HTMLResponse)
async def article_card(
    request: Request,
    article_id: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    result = await db.execute(
        select(Article).where(
            Article.id == article_id,
            Article.is_active.is_(True),
        )
    )
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    return templates.TemplateResponse(
        "partials/tinder_card.html",
        {
            "request": request,
            "article": article,
            "placeholder_image": PLACEHOLDER_IMAGE,
        },
    )


@router.get("/articles/{article_id}", response_class=HTMLResponse)
async def article_detail(
    request: Request,
    article_id: int,
    db: AsyncSession = Depends(get_db),
) -> HTMLResponse:
    result = await db.execute(
        select(Article).where(
            Article.id == article_id, Article.is_active.is_(True)
        )
    )
    article = result.scalar_one_or_none()

    if not article:
        raise HTTPException(status_code=404, detail="Article not found")

    return templates.TemplateResponse(
        "article_detail.html",
        {"request": request, "article": article, "placeholder_image": PLACEHOLDER_IMAGE},
    )
