"""Tests for the LLM aggregate file generators in deep_thought.file_txt.llms."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from deep_thought.file_txt.llms import (
    DocumentSummary,
    strip_frontmatter,
    write_llms_full,
    write_llms_index,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_summary(
    name: str = "report",
    source_file: str = "report.pdf",
    file_type: str = "pdf",
    word_count: int = 500,
    content: str = "# Report\n\nContent here.",
    md_relative_path: str = "report/report.md",
) -> DocumentSummary:
    """Return a DocumentSummary with sensible test defaults."""
    return DocumentSummary(
        name=name,
        md_relative_path=md_relative_path,
        source_file=source_file,
        file_type=file_type,
        word_count=word_count,
        content=content,
    )


# ---------------------------------------------------------------------------
# _strip_frontmatter
# ---------------------------------------------------------------------------


class TestStripFrontmatter:
    def test_removes_frontmatter_block(self) -> None:
        """A document with frontmatter must have the block stripped."""
        text = "---\ntool: file-txt\n---\n# Title\n\nBody."
        result = strip_frontmatter(text)
        assert "tool: file-txt" not in result
        assert "# Title" in result

    def test_returns_unchanged_when_no_frontmatter(self) -> None:
        """Text without a leading --- must be returned unchanged."""
        text = "# Title\n\nBody content."
        result = strip_frontmatter(text)
        assert result == text

    def test_handles_document_with_only_frontmatter(self) -> None:
        """A document containing only a frontmatter block must return empty string."""
        text = "---\ntool: file-txt\n---\n"
        result = strip_frontmatter(text)
        assert result.strip() == ""

    def test_unclosed_frontmatter_returned_unchanged(self) -> None:
        """A --- that is never closed must leave the text unchanged."""
        text = "---\ntool: file-txt\n# Title"
        result = strip_frontmatter(text)
        assert result == text


# ---------------------------------------------------------------------------
# write_llms_full
# ---------------------------------------------------------------------------


class TestWriteLlmsFull:
    def test_creates_llms_full_txt(self, tmp_path: Path) -> None:
        """write_llms_full must create llms-full.txt in the output root."""
        summaries = [_make_summary()]
        output_path = write_llms_full(summaries, tmp_path)
        assert output_path == tmp_path / "llms-full.txt"
        assert output_path.exists()

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """The returned Path must point to the file that was written."""
        summaries = [_make_summary()]
        returned_path = write_llms_full(summaries, tmp_path)
        assert returned_path.is_file()

    def test_content_includes_document_name(self, tmp_path: Path) -> None:
        """Each document block must include the document name as a heading."""
        summaries = [_make_summary(name="annual_report")]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / "llms-full.txt").read_text(encoding="utf-8")
        assert "# annual_report" in content

    def test_content_includes_source_metadata(self, tmp_path: Path) -> None:
        """Each document block must include source, type, and processed fields."""
        summaries = [_make_summary(source_file="report.pdf", file_type="pdf")]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / "llms-full.txt").read_text(encoding="utf-8")
        assert "source: report.pdf" in content
        assert "type: pdf" in content
        assert "processed:" in content

    def test_content_includes_body(self, tmp_path: Path) -> None:
        """Each document block must include the document body content."""
        summaries = [_make_summary(content="# Section\n\nBody text.")]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / "llms-full.txt").read_text(encoding="utf-8")
        assert "# Section" in content
        assert "Body text." in content

    def test_multiple_documents_separated_by_divider(self, tmp_path: Path) -> None:
        """Multiple documents must be separated by --- dividers."""
        summaries = [
            _make_summary(name="doc_a", md_relative_path="doc_a/doc_a.md"),
            _make_summary(name="doc_b", md_relative_path="doc_b/doc_b.md"),
        ]
        write_llms_full(summaries, tmp_path)
        content = (tmp_path / "llms-full.txt").read_text(encoding="utf-8")
        assert "# doc_a" in content
        assert "# doc_b" in content
        # At least one --- divider separating the documents
        assert content.count("---") >= 1

    def test_empty_summaries_creates_empty_file(self, tmp_path: Path) -> None:
        """An empty summaries list must produce an empty (or minimal) file."""
        output_path = write_llms_full([], tmp_path)
        assert output_path.exists()

    def test_creates_output_directory_if_missing(self, tmp_path: Path) -> None:
        """write_llms_full must create output_root if it does not exist."""
        new_dir = tmp_path / "new_output"
        summaries = [_make_summary()]
        write_llms_full(summaries, new_dir)
        assert (new_dir / "llms-full.txt").exists()


# ---------------------------------------------------------------------------
# write_llms_index
# ---------------------------------------------------------------------------


class TestWriteLlmsIndex:
    def test_creates_llms_txt(self, tmp_path: Path) -> None:
        """write_llms_index must create llms.txt in the output root."""
        summaries = [_make_summary()]
        output_path = write_llms_index(summaries, tmp_path)
        assert output_path == tmp_path / "llms.txt"
        assert output_path.exists()

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """The returned Path must point to the file that was written."""
        returned_path = write_llms_index([_make_summary()], tmp_path)
        assert returned_path.is_file()

    def test_index_contains_header(self, tmp_path: Path) -> None:
        """The index must contain the '# Document Index' heading."""
        write_llms_index([_make_summary()], tmp_path)
        content = (tmp_path / "llms.txt").read_text(encoding="utf-8")
        assert "# Document Index" in content

    def test_index_contains_document_count(self, tmp_path: Path) -> None:
        """The index must state the total number of documents."""
        summaries = [
            _make_summary(name="a", md_relative_path="a/a.md"),
            _make_summary(name="b", md_relative_path="b/b.md"),
        ]
        write_llms_index(summaries, tmp_path)
        content = (tmp_path / "llms.txt").read_text(encoding="utf-8")
        assert "2 documents" in content

    def test_index_contains_document_entry(self, tmp_path: Path) -> None:
        """Each document must appear as a list entry with link and metadata."""
        summary = _make_summary(
            name="report",
            source_file="report.pdf",
            file_type="pdf",
            word_count=1500,
            md_relative_path="report/report.md",
        )
        write_llms_index([summary], tmp_path)
        content = (tmp_path / "llms.txt").read_text(encoding="utf-8")
        assert "[report.md](report/report.md)" in content
        assert "report.pdf" in content
        assert "pdf" in content
        assert "1500 words" in content

    def test_index_contains_processed_date(self, tmp_path: Path) -> None:
        """The index must contain a 'Processed by file-txt' line with a date."""
        write_llms_index([_make_summary()], tmp_path)
        content = (tmp_path / "llms.txt").read_text(encoding="utf-8")
        assert "Processed by file-txt" in content

    def test_creates_output_directory_if_missing(self, tmp_path: Path) -> None:
        """write_llms_index must create output_root if it does not exist."""
        new_dir = tmp_path / "new_output"
        write_llms_index([_make_summary()], new_dir)
        assert (new_dir / "llms.txt").exists()
