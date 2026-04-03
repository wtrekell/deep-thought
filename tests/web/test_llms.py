"""Tests for llms.py: write_llms_full, write_llms_index, and strip_frontmatter."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

import pytest

from deep_thought.web.llms import PageSummary, strip_frontmatter, write_llms_full, write_llms_index

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary(
    title: str | None = "My Article",
    url: str = "https://example.com/article",
    md_relative_path: str = "example.com/article.md",
    mode: str = "blog",
    word_count: int = 300,
    content: str = "Some article content here.",
) -> PageSummary:
    """Create a minimal PageSummary for use in tests."""
    return PageSummary(
        title=title,
        url=url,
        md_relative_path=md_relative_path,
        mode=mode,
        word_count=word_count,
        content=content,
    )


# ---------------------------------------------------------------------------
# TestStripFrontmatter
# ---------------------------------------------------------------------------


class TestStripFrontmatter:
    """Tests for the strip_frontmatter helper."""

    def test_strips_standard_frontmatter(self) -> None:
        """A standard YAML frontmatter block must be removed, leaving only the body."""
        markdown = "---\ntool: web\nurl: https://example.com\n---\n\nBody text here."
        result = strip_frontmatter(markdown)
        assert result == "Body text here."

    def test_returns_text_unchanged_when_no_frontmatter(self) -> None:
        """Text that does not begin with --- must be returned unchanged."""
        markdown = "No frontmatter here.\n\nJust body."
        result = strip_frontmatter(markdown)
        assert result == markdown

    def test_returns_text_unchanged_when_no_closing_delimiter(self) -> None:
        """Text that starts with --- but has no closing --- must be returned unchanged."""
        markdown = "---\ntool: web\nurl: https://example.com\n\nNo closing delimiter."
        result = strip_frontmatter(markdown)
        assert result == markdown

    def test_handles_empty_body_after_frontmatter(self) -> None:
        """A frontmatter block with no body after it must return an empty string."""
        markdown = "---\ntool: web\n---\n"
        result = strip_frontmatter(markdown)
        assert result == ""

    def test_strips_leading_blank_lines_from_body(self) -> None:
        """Blank lines immediately after the closing --- must be stripped from the body."""
        markdown = "---\ntool: web\n---\n\n\nFirst paragraph."
        result = strip_frontmatter(markdown)
        assert result == "First paragraph."

    def test_handles_empty_string_input(self) -> None:
        """An empty input string must be returned as-is."""
        result = strip_frontmatter("")
        assert result == ""

    def test_does_not_strip_internal_dashes(self) -> None:
        """A --- divider inside the body (not in frontmatter position) must be preserved."""
        markdown = "---\ntool: web\n---\n\nBody content.\n\n---\n\nMore content."
        result = strip_frontmatter(markdown)
        assert "---" in result
        assert "More content." in result


# ---------------------------------------------------------------------------
# TestWriteLlmsFull
# ---------------------------------------------------------------------------


class TestWriteLlmsFull:
    """Tests for write_llms_full."""

    def test_creates_llms_full_txt_in_output_root(self, tmp_path: Path) -> None:
        """write_llms_full must create llms-full.txt in the given output_root."""
        summaries = [_make_summary()]
        result_path = write_llms_full(summaries, tmp_path)
        assert result_path == tmp_path / "llms-full.txt"
        assert result_path.exists()

    def test_creates_output_root_if_absent(self, tmp_path: Path) -> None:
        """write_llms_full must create the output root directory if it does not exist."""
        output_root = tmp_path / "nested" / "dir"
        write_llms_full([_make_summary()], output_root)
        assert (output_root / "llms-full.txt").exists()

    def test_each_page_heading_appears_in_output(self, tmp_path: Path) -> None:
        """The title of each summary must appear as a heading in the output file."""
        summaries = [
            _make_summary(title="Article One", url="https://example.com/one"),
            _make_summary(title="Article Two", url="https://example.com/two"),
        ]
        result_path = write_llms_full(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "# Article One" in file_content
        assert "# Article Two" in file_content

    def test_url_used_as_heading_when_title_is_none(self, tmp_path: Path) -> None:
        """When title is None, the URL must be used as the heading instead."""
        summaries = [_make_summary(title=None, url="https://example.com/notitle")]
        result_path = write_llms_full(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "# https://example.com/notitle" in file_content

    def test_page_content_appears_in_output(self, tmp_path: Path) -> None:
        """The full content of each page must be included in the output file."""
        unique_content = "Unique content marker abc123."
        summaries = [_make_summary(content=unique_content)]
        result_path = write_llms_full(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert unique_content in file_content

    def test_url_metadata_appears_in_output(self, tmp_path: Path) -> None:
        """Each page block must contain its source URL."""
        summaries = [_make_summary(url="https://example.com/my-page")]
        result_path = write_llms_full(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "url: https://example.com/my-page" in file_content

    def test_generated_field_present_not_crawled(self, tmp_path: Path) -> None:
        """Each page block must use 'generated:' not 'crawled:' for the timestamp."""
        summaries = [_make_summary()]
        result_path = write_llms_full(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "generated:" in file_content
        assert "crawled:" not in file_content

    def test_pages_separated_by_divider(self, tmp_path: Path) -> None:
        """Multiple pages must be separated by --- dividers."""
        summaries = [
            _make_summary(url="https://example.com/one"),
            _make_summary(url="https://example.com/two"),
        ]
        result_path = write_llms_full(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "---" in file_content

    def test_empty_summaries_creates_empty_file(self, tmp_path: Path) -> None:
        """An empty summaries list must create an empty llms-full.txt file."""
        result_path = write_llms_full([], tmp_path)
        assert result_path.read_text(encoding="utf-8") == ""


# ---------------------------------------------------------------------------
# TestWriteLlmsIndex
# ---------------------------------------------------------------------------


class TestWriteLlmsIndex:
    """Tests for write_llms_index."""

    def test_creates_llms_txt_in_output_root(self, tmp_path: Path) -> None:
        """write_llms_index must create llms.txt in the given output_root."""
        summaries = [_make_summary()]
        result_path = write_llms_index(summaries, tmp_path)
        assert result_path == tmp_path / "llms.txt"
        assert result_path.exists()

    def test_creates_output_root_if_absent(self, tmp_path: Path) -> None:
        """write_llms_index must create the output root directory if it does not exist."""
        output_root = tmp_path / "nested" / "dir"
        write_llms_index([_make_summary()], output_root)
        assert (output_root / "llms.txt").exists()

    def test_page_count_in_header(self, tmp_path: Path) -> None:
        """The header must report the correct number of pages."""
        summaries = [
            _make_summary(url="https://example.com/one"),
            _make_summary(url="https://example.com/two"),
        ]
        result_path = write_llms_index(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "2 pages" in file_content

    def test_each_page_entry_contains_url(self, tmp_path: Path) -> None:
        """Each entry in the index must contain the page's source URL."""
        summaries = [_make_summary(url="https://example.com/article")]
        result_path = write_llms_index(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "https://example.com/article" in file_content

    def test_each_entry_contains_word_count(self, tmp_path: Path) -> None:
        """Each entry must report the word count for the page."""
        summaries = [_make_summary(word_count=450)]
        result_path = write_llms_index(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "450 words" in file_content

    def test_each_entry_links_to_md_path(self, tmp_path: Path) -> None:
        """Each entry must contain a markdown link using the md_relative_path."""
        summaries = [_make_summary(md_relative_path="example.com/article.md")]
        result_path = write_llms_index(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "example.com/article.md" in file_content

    def test_label_includes_md_extension(self, tmp_path: Path) -> None:
        """Per spec, the display label for each entry must include the .md suffix."""
        summaries = [_make_summary(title="My Article")]
        result_path = write_llms_index(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "My Article.md" in file_content

    def test_url_used_as_label_when_title_is_none(self, tmp_path: Path) -> None:
        """When title is None, the URL must be used as the display label."""
        summaries = [_make_summary(title=None, url="https://example.com/notitle")]
        result_path = write_llms_index(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert "https://example.com/notitle" in file_content

    def test_contains_page_index_heading(self, tmp_path: Path) -> None:
        """The output file must start with a '# Page Index' heading."""
        result_path = write_llms_index([_make_summary()], tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert file_content.startswith("# Page Index")

    @pytest.mark.parametrize("count", [0, 1, 5])
    def test_page_count_various_sizes(self, tmp_path: Path, count: int) -> None:
        """Page count in the header must match the number of summaries for 0, 1, and 5 pages."""
        summaries = [
            _make_summary(url=f"https://example.com/page-{index}", md_relative_path=f"example.com/page-{index}.md")
            for index in range(count)
        ]
        result_path = write_llms_index(summaries, tmp_path)
        file_content = result_path.read_text(encoding="utf-8")
        assert f"{count} pages" in file_content
