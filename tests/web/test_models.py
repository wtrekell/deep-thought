"""Tests for models.py: CrawledPageLocal.to_dict()."""

from __future__ import annotations

from deep_thought.web.models import CrawledPageLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_page(
    url: str = "https://example.com/post",
    title: str | None = "Post Title",
    status_code: int | None = 200,
    word_count: int = 300,
    output_path: str = "output/web/example.com/post.md",
    status: str = "success",
    created_at: str = "2026-03-22T00:00:00+00:00",
    updated_at: str = "2026-03-22T00:00:00+00:00",
    synced_at: str = "2026-03-22T00:00:00+00:00",
) -> CrawledPageLocal:
    """Build a CrawledPageLocal instance for testing."""
    return CrawledPageLocal(
        url=url,
        title=title,
        status_code=status_code,
        word_count=word_count,
        output_path=output_path,
        status=status,
        created_at=created_at,
        updated_at=updated_at,
        synced_at=synced_at,
    )


# ---------------------------------------------------------------------------
# TestCrawledPageLocalToDict
# ---------------------------------------------------------------------------


class TestCrawledPageLocalToDict:
    """Tests for CrawledPageLocal.to_dict()."""

    def test_returns_dict_type(self) -> None:
        """to_dict must return a plain dict."""
        page = _make_page()
        result = page.to_dict()
        assert isinstance(result, dict)

    def test_url_is_preserved(self) -> None:
        """to_dict must include the url field with the correct value."""
        page = _make_page(url="https://example.com/article")
        result = page.to_dict()
        assert result["url"] == "https://example.com/article"

    def test_title_none_is_preserved(self) -> None:
        """to_dict must include title as None when not set."""
        page = _make_page(title=None)
        result = page.to_dict()
        assert result["title"] is None

    def test_status_code_int_is_preserved(self) -> None:
        """to_dict must include a non-None status_code correctly."""
        page = _make_page(status_code=200)
        result = page.to_dict()
        assert result["status_code"] == 200

    def test_status_code_none_is_preserved(self) -> None:
        """to_dict must include status_code as None when not set (DB nullable column)."""
        page = _make_page(status_code=None)
        result = page.to_dict()
        assert result["status_code"] is None

    def test_word_count_is_preserved(self) -> None:
        """to_dict must include the word_count field."""
        page = _make_page(word_count=450)
        result = page.to_dict()
        assert result["word_count"] == 450

    def test_output_path_is_preserved(self) -> None:
        """to_dict must include the output_path field."""
        page = _make_page(output_path="output/web/example.com/post.md")
        result = page.to_dict()
        assert result["output_path"] == "output/web/example.com/post.md"

    def test_status_field_is_preserved(self) -> None:
        """to_dict must include the status field."""
        page = _make_page(status="error")
        result = page.to_dict()
        assert result["status"] == "error"

    def test_all_required_keys_present(self) -> None:
        """to_dict must contain all expected column keys."""
        page = _make_page()
        result = page.to_dict()
        expected_keys = {
            "url",
            "title",
            "status_code",
            "word_count",
            "output_path",
            "status",
            "created_at",
            "updated_at",
            "synced_at",
        }
        assert expected_keys.issubset(result.keys())

    def test_to_dict_is_stable(self) -> None:
        """Calling to_dict twice on the same instance must return equal dicts."""
        page = _make_page()
        assert page.to_dict() == page.to_dict()

    def test_skipped_status_page(self) -> None:
        """A page with status='skipped' must be correctly represented in the dict."""
        page = _make_page(status="skipped", output_path="", word_count=10, status_code=200)
        result = page.to_dict()
        assert result["status"] == "skipped"
        assert result["output_path"] == ""
