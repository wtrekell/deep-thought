"""Tests for the document output writer in deep_thought.file_txt.output."""

from __future__ import annotations

from pathlib import Path

from deep_thought.file_txt.output import _build_frontmatter, count_words, write_document

# ---------------------------------------------------------------------------
# _build_frontmatter
# ---------------------------------------------------------------------------


class TestBuildFrontmatter:
    def test_frontmatter_contains_required_fields(self) -> None:
        """All required frontmatter fields must appear in the output."""
        frontmatter = _build_frontmatter(
            source_file="report.pdf",
            file_type="pdf",
            page_count=5,
            word_count=1200,
            has_images=True,
            processed_date="2026-03-21T00:00:00+00:00",
        )
        assert "tool: file-txt" in frontmatter
        assert 'source_file: "report.pdf"' in frontmatter
        assert "file_type: pdf" in frontmatter
        assert "page_count: 5" in frontmatter
        assert "word_count: 1200" in frontmatter
        assert "has_images: true" in frontmatter
        assert 'processed_date: "2026-03-21T00:00:00+00:00"' in frontmatter

    def test_frontmatter_is_wrapped_in_dashes(self) -> None:
        """The frontmatter block must be delimited by --- markers."""
        frontmatter = _build_frontmatter(
            source_file="file.docx",
            file_type="docx",
            page_count=None,
            word_count=0,
            has_images=False,
            processed_date="2026-03-21T00:00:00+00:00",
        )
        lines = frontmatter.strip().splitlines()
        assert lines[0] == "---"
        assert lines[-1] == "---"

    def test_page_count_omitted_for_non_pdf(self) -> None:
        """When page_count is None, the page_count field must not appear."""
        frontmatter = _build_frontmatter(
            source_file="document.docx",
            file_type="docx",
            page_count=None,
            word_count=500,
            has_images=False,
            processed_date="2026-03-21T00:00:00+00:00",
        )
        assert "page_count" not in frontmatter

    def test_page_count_included_for_pdf(self) -> None:
        """When page_count is provided, the page_count field must appear."""
        frontmatter = _build_frontmatter(
            source_file="report.pdf",
            file_type="pdf",
            page_count=10,
            word_count=2000,
            has_images=False,
            processed_date="2026-03-21T00:00:00+00:00",
        )
        assert "page_count: 10" in frontmatter

    def test_has_images_false_written_as_lowercase(self) -> None:
        """has_images: false must be written in lowercase YAML style."""
        frontmatter = _build_frontmatter(
            source_file="plain.docx",
            file_type="docx",
            page_count=None,
            word_count=100,
            has_images=False,
            processed_date="2026-03-21T00:00:00+00:00",
        )
        assert "has_images: false" in frontmatter

    def test_has_images_true_written_as_lowercase(self) -> None:
        """has_images: true must be written in lowercase YAML style."""
        frontmatter = _build_frontmatter(
            source_file="diagram.pptx",
            file_type="pptx",
            page_count=None,
            word_count=300,
            has_images=True,
            processed_date="2026-03-21T00:00:00+00:00",
        )
        assert "has_images: true" in frontmatter


# ---------------------------------------------------------------------------
# _build_frontmatter — email metadata
# ---------------------------------------------------------------------------


class TestBuildFrontmatterEmail:
    def test_email_frontmatter_contains_email_fields(self) -> None:
        """Email metadata fields must appear in the frontmatter when provided."""
        email_metadata = {
            "from_address": "sender@example.com",
            "to_address": "recipient@example.com",
            "subject": "Project Update",
            "date": "2026-03-15T09:30:00Z",
            "has_attachments": True,
            "attachment_count": 2,
        }
        frontmatter = _build_frontmatter(
            source_file="message.eml",
            file_type="eml",
            page_count=None,
            word_count=150,
            has_images=False,
            processed_date="2026-03-21T00:00:00+00:00",
            email_metadata=email_metadata,
        )
        assert 'from: "sender@example.com"' in frontmatter
        assert 'to: "recipient@example.com"' in frontmatter
        assert 'subject: "Project Update"' in frontmatter
        assert 'date: "2026-03-15T09:30:00Z"' in frontmatter
        assert "has_attachments: true" in frontmatter
        assert "attachment_count: 2" in frontmatter

    def test_email_frontmatter_omits_page_count(self) -> None:
        """Email frontmatter must not include page_count when None."""
        email_metadata = {
            "from_address": "a@b.com",
            "to_address": "c@d.com",
            "subject": "Test",
            "date": "2026-03-15T09:30:00Z",
            "has_attachments": False,
            "attachment_count": 0,
        }
        frontmatter = _build_frontmatter(
            source_file="message.eml",
            file_type="eml",
            page_count=None,
            word_count=50,
            has_images=False,
            processed_date="2026-03-21T00:00:00+00:00",
            email_metadata=email_metadata,
        )
        assert "page_count" not in frontmatter

    def test_non_email_frontmatter_omits_email_fields(self) -> None:
        """When email_metadata is None, email fields must not appear."""
        frontmatter = _build_frontmatter(
            source_file="report.pdf",
            file_type="pdf",
            page_count=10,
            word_count=2000,
            has_images=False,
            processed_date="2026-03-21T00:00:00+00:00",
            email_metadata=None,
        )
        assert "from:" not in frontmatter
        assert "to:" not in frontmatter
        assert "subject:" not in frontmatter
        assert "has_attachments:" not in frontmatter
        assert "attachment_count:" not in frontmatter


# ---------------------------------------------------------------------------
# write_document
# ---------------------------------------------------------------------------


class TestWriteDocument:
    def test_creates_subdirectory_and_file(self, tmp_path: Path) -> None:
        """write_document must create {output_root}/{stem}/{stem}.md."""
        source_path = Path("/original/report.pdf")
        output_path = write_document(
            "# Report content\n\nSome text here.",
            source_path,
            tmp_path,
            file_type="pdf",
            page_count=3,
            word_count=5,
            has_images=False,
        )
        assert output_path == tmp_path / "report" / "report.md"
        assert output_path.exists()

    def test_output_contains_frontmatter(self, tmp_path: Path) -> None:
        """The written file must start with the YAML frontmatter block."""
        source_path = Path("/docs/summary.docx")
        output_path = write_document(
            "Some content.",
            source_path,
            tmp_path,
            file_type="docx",
            page_count=None,
            word_count=2,
            has_images=False,
        )
        content = output_path.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "tool: file-txt" in content
        assert 'source_file: "summary.docx"' in content

    def test_page_count_omitted_for_non_pdf_in_written_file(self, tmp_path: Path) -> None:
        """The written file must not include page_count when it is None."""
        source_path = Path("/docs/slides.pptx")
        output_path = write_document(
            "Slide content.",
            source_path,
            tmp_path,
            file_type="pptx",
            page_count=None,
            word_count=2,
            has_images=False,
        )
        content = output_path.read_text(encoding="utf-8")
        assert "page_count" not in content

    def test_body_follows_frontmatter(self, tmp_path: Path) -> None:
        """The markdown body must appear after the closing --- of frontmatter."""
        source_path = Path("/docs/report.pdf")
        body_text = "# Title\n\nBody paragraph."
        output_path = write_document(
            body_text,
            source_path,
            tmp_path,
            file_type="pdf",
            page_count=1,
            word_count=3,
            has_images=False,
        )
        content = output_path.read_text(encoding="utf-8")
        # Find closing --- and check body follows
        closing_index = content.index("---\n", 4)  # skip opening ---
        body_portion = content[closing_index + 4 :]
        assert "# Title" in body_portion

    def test_returns_path_to_written_file(self, tmp_path: Path) -> None:
        """write_document must return the Path to the file that was written."""
        source_path = Path("/input/data.xlsx")
        returned_path = write_document(
            "Spreadsheet content.",
            source_path,
            tmp_path,
            file_type="xlsx",
            page_count=None,
            word_count=2,
            has_images=False,
        )
        assert returned_path.is_file()
        assert returned_path.name == "data.md"

    def test_creates_parent_directories_as_needed(self, tmp_path: Path) -> None:
        """Output subdirectory must be created when it does not exist."""
        deep_output_root = tmp_path / "nested" / "output"
        source_path = Path("/docs/report.pdf")
        output_path = write_document(
            "Content.",
            source_path,
            deep_output_root,
            file_type="pdf",
            page_count=2,
            word_count=1,
            has_images=False,
        )
        assert output_path.exists()

    def test_collision_with_different_source_adds_extension_suffix(self, tmp_path: Path) -> None:
        """When a same-stem directory exists for a different source file, append extension suffix."""
        # First write: report.pdf -> report/report.md
        pdf_source = Path("/input/report.pdf")
        first_output = write_document(
            "PDF content.",
            pdf_source,
            tmp_path,
            file_type="pdf",
            page_count=3,
            word_count=2,
            has_images=False,
        )
        assert first_output == tmp_path / "report" / "report.md"

        # Second write: report.docx shares the stem "report" but is a different source
        docx_source = Path("/input/report.docx")
        second_output = write_document(
            "DOCX content.",
            docx_source,
            tmp_path,
            file_type="docx",
            page_count=None,
            word_count=2,
            has_images=False,
        )
        # Must be disambiguated to report_docx/report_docx.md
        assert second_output == tmp_path / "report_docx" / "report_docx.md"
        assert second_output.exists()

    def test_no_collision_when_same_source_rewrites(self, tmp_path: Path) -> None:
        """Re-writing the same source file must overwrite in place without a suffix."""
        source_path = Path("/input/report.pdf")
        first_output = write_document(
            "Original content.",
            source_path,
            tmp_path,
            file_type="pdf",
            page_count=3,
            word_count=2,
            has_images=False,
        )
        second_output = write_document(
            "Updated content.",
            source_path,
            tmp_path,
            file_type="pdf",
            page_count=3,
            word_count=2,
            has_images=False,
        )
        # Both should resolve to the same path — no suffix appended
        assert first_output == second_output
        assert second_output == tmp_path / "report" / "report.md"
        assert "Updated content." in second_output.read_text(encoding="utf-8")


# ---------------------------------------------------------------------------
# count_words
# ---------------------------------------------------------------------------


class TestCountWords:
    def test_simple_sentence(self) -> None:
        """A simple sentence must return the correct word count."""
        assert count_words("Hello world this is text") == 5

    def test_empty_string_returns_zero(self) -> None:
        """An empty string must return 0."""
        assert count_words("") == 0

    def test_extra_whitespace_is_normalised(self) -> None:
        """Extra whitespace between words must not inflate the count."""
        assert count_words("  word   another  ") == 2

    def test_newlines_treated_as_whitespace(self) -> None:
        """Newlines must be treated as word separators."""
        assert count_words("line one\nline two") == 4
