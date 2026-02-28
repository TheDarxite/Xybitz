import pytest
from httpx import AsyncClient


class TestHealthEndpoint:
    @pytest.mark.asyncio
    async def test_health_returns_200(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_health_has_required_keys(self, client: AsyncClient):
        response = await client.get("/health")
        data = response.json()
        required_keys = {
            "status", "ollama", "db", "articles_total",
            "articles_pending_summary", "articles_failed_summary", "scheduler",
        }
        assert required_keys.issubset(data.keys())

    @pytest.mark.asyncio
    async def test_health_db_ok(self, client: AsyncClient):
        response = await client.get("/health")
        assert response.json()["db"] == "ok"


class TestIndexEndpoint:
    @pytest.mark.asyncio
    async def test_index_returns_200(self, client: AsyncClient):
        response = await client.get("/")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_index_contains_xybitz(self, client: AsyncClient):
        response = await client.get("/")
        assert b"Xybitz" in response.content

    @pytest.mark.asyncio
    async def test_index_contains_htmx(self, client: AsyncClient):
        response = await client.get("/")
        assert b"htmx" in response.content.lower()


class TestArticlesEndpoint:
    @pytest.mark.asyncio
    async def test_articles_returns_200(self, client: AsyncClient):
        response = await client.get("/articles")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_articles_htmx_returns_partial(self, client: AsyncClient):
        response = await client.get(
            "/articles", headers={"HX-Request": "true"}
        )
        assert response.status_code == 200
        # Partial should NOT contain the full base layout
        assert b"<!DOCTYPE html>" not in response.content

    @pytest.mark.asyncio
    async def test_articles_category_filter(self, client: AsyncClient):
        response = await client.get("/articles?category=malware")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_articles_search(self, client: AsyncClient):
        response = await client.get("/articles?search=ransomware")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_article_detail_404(self, client: AsyncClient):
        response = await client.get("/articles/999999")
        assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_articles_pagination(self, client: AsyncClient):
        response = await client.get("/articles?page=1&limit=5")
        assert response.status_code == 200


class TestCategoriesApiEndpoint:
    @pytest.mark.asyncio
    async def test_categories_returns_200(self, client: AsyncClient):
        response = await client.get("/api/v1/categories")
        assert response.status_code == 200

    @pytest.mark.asyncio
    async def test_categories_returns_list(self, client: AsyncClient):
        response = await client.get("/api/v1/categories")
        data = response.json()
        assert isinstance(data, list)
