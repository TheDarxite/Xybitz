from sqladmin import ModelView
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request

from app.config import settings
from app.models import Article, Category, Source


class ArticleAdmin(ModelView, model=Article):
    name = "Article"
    name_plural = "Articles"
    icon = "fa-solid fa-newspaper"
    column_list = [
        Article.id,
        Article.title,
        Article.source_name,
        Article.category,
        Article.summary_status,
        Article.published_at,
        Article.is_featured,
        Article.is_active,
    ]
    column_searchable_list = [Article.title, Article.summary, Article.source_name]
    column_sortable_list = [
        Article.published_at,
        Article.category,
        Article.summary_status,
    ]
    column_filters = [
        Article.category,
        Article.summary_status,
        Article.is_active,
        Article.source_name,
    ]
    can_delete = True
    can_export = True
    page_size = 50
    page_size_options = [10, 25, 50, 100]


class SourceAdmin(ModelView, model=Source):
    name = "Source"
    name_plural = "Sources"
    icon = "fa-solid fa-rss"
    column_list = [
        Source.id,
        Source.name,
        Source.url,
        Source.category,
        Source.source_type,
        Source.is_active,
        Source.last_fetched_at,
        Source.consecutive_failures,
        Source.article_count,
    ]
    can_create = True
    can_edit = True
    can_delete = True
    column_searchable_list = [Source.name, Source.url]


class CategoryAdmin(ModelView, model=Category):
    name = "Category"
    name_plural = "Categories"
    icon = "fa-solid fa-tags"
    column_list = [
        Category.id,
        Category.slug,
        Category.name,
        Category.color,
        Category.is_visible,
    ]
    can_create = True
    can_edit = True
    can_delete = True


class AdminAuth(AuthenticationBackend):
    async def login(self, request: Request) -> bool:
        form = await request.form()
        if (
            form.get("username") == settings.ADMIN_USERNAME
            and form.get("password") == settings.ADMIN_PASSWORD
        ):
            request.session.update({"authenticated": True})
            return True
        return False

    async def authenticate(self, request: Request) -> bool:
        return request.session.get("authenticated", False)

    async def logout(self, request: Request) -> bool:
        request.session.clear()
        return True
