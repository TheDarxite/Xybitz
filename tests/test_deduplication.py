import pytest

from app.services.deduplication import compute_url_hash, is_duplicate


class TestComputeUrlHash:
    def test_returns_64_char_hex(self):
        result = compute_url_hash("https://example.com/article/1")
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_same_url_same_hash(self):
        url = "https://example.com/article/1"
        assert compute_url_hash(url) == compute_url_hash(url)

    def test_case_insensitive(self):
        assert compute_url_hash("HTTPS://EXAMPLE.COM/A") == compute_url_hash(
            "https://example.com/a"
        )

    def test_strips_whitespace(self):
        assert compute_url_hash("  https://example.com/a  ") == compute_url_hash(
            "https://example.com/a"
        )

    def test_different_urls_different_hashes(self):
        h1 = compute_url_hash("https://example.com/a")
        h2 = compute_url_hash("https://example.com/b")
        assert h1 != h2


class TestIsDuplicate:
    @pytest.mark.asyncio
    async def test_not_duplicate_when_empty(self, db_session):
        url_hash = compute_url_hash("https://example.com/unique-article")
        result = await is_duplicate(db_session, url_hash)
        assert result is False

    @pytest.mark.asyncio
    async def test_is_duplicate_after_insert(self, db_session):
        from datetime import datetime, timezone

        from app.models import Article

        url = "https://example.com/dup-test-article"
        url_hash = compute_url_hash(url)

        article = Article(
            url=url,
            url_hash=url_hash,
            title="Dup Test",
            source_name="Test Source",
            category="general",
            summary_status="pending",
        )
        db_session.add(article)
        await db_session.commit()

        result = await is_duplicate(db_session, url_hash)
        assert result is True

    @pytest.mark.asyncio
    async def test_not_duplicate_for_different_hash(self, db_session):
        other_hash = compute_url_hash("https://completely-different.com/article")
        result = await is_duplicate(db_session, other_hash)
        assert result is False
