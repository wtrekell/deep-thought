"""Tests for the single-file conversion orchestrator in deep_thought.file_txt.convert."""

from __future__ import annotations

from pathlib import Path  # noqa: TC003
from unittest.mock import patch

import pytest

from deep_thought.file_txt.config import FileTxtConfig, FilterConfig, LimitsConfig, MarkerConfig, OutputConfig
from deep_thought.file_txt.convert import convert_file

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_config(
    max_file_size_mb: int = 200,
    extract_images: bool = False,
    force_ocr: bool = False,
    torch_device: str = "cpu",
    include_page_numbers: bool = False,
    output_dir: str = "output/",
) -> FileTxtConfig:
    """Return a FileTxtConfig with sensible test defaults."""
    return FileTxtConfig(
        marker=MarkerConfig(force_ocr=force_ocr, torch_device=torch_device),
        output=OutputConfig(
            output_dir=output_dir,
            include_page_numbers=include_page_numbers,
            extract_images=extract_images,
        ),
        limits=LimitsConfig(max_file_size_mb=max_file_size_mb),
        filter=FilterConfig(allowed_extensions=[".pdf", ".docx"], exclude_patterns=[]),
    )


def _write_small_file(path: Path, content: bytes = b"fake content") -> None:
    """Write a small file at path, creating parent directories as needed."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)


# ---------------------------------------------------------------------------
# Dry-run behaviour
# ---------------------------------------------------------------------------


class TestConvertFileDryRun:
    def test_dry_run_returns_result_without_writing(self, tmp_path: Path) -> None:
        """In dry-run mode, no output file must be written."""
        source_file = tmp_path / "test.pdf"
        _write_small_file(source_file)
        config = _make_config()

        result = convert_file(source_file, tmp_path / "output", config, dry_run=True)

        assert result.skipped is False
        assert result.output_path is None
        assert result.errors == []

    def test_dry_run_does_not_call_conversion_engines(self, tmp_path: Path) -> None:
        """In dry-run mode, neither Marker nor MarkItDown must be called."""
        source_file = tmp_path / "doc.docx"
        _write_small_file(source_file)
        config = _make_config()

        with patch("deep_thought.file_txt.convert._convert_via_markitdown") as mock_convert:
            convert_file(source_file, tmp_path / "output", config, dry_run=True)
            mock_convert.assert_not_called()

    def test_dry_run_sets_file_type_correctly(self, tmp_path: Path) -> None:
        """Dry-run result must still report the correct file_type."""
        source_file = tmp_path / "presentation.pptx"
        _write_small_file(source_file)
        config = _make_config()

        result = convert_file(source_file, tmp_path / "output", config, dry_run=True)

        assert result.file_type == "pptx"


# ---------------------------------------------------------------------------
# Skip conditions
# ---------------------------------------------------------------------------


class TestConvertFileSkip:
    def test_file_exceeding_size_limit_is_skipped(self, tmp_path: Path) -> None:
        """A file larger than max_file_size_mb must be returned as skipped."""
        large_file = tmp_path / "large.pdf"
        # Write 3 MB of data with a 1 MB limit
        large_file.write_bytes(b"x" * (3 * 1024 * 1024))
        config = _make_config(max_file_size_mb=1)

        result = convert_file(large_file, tmp_path / "output", config)

        assert result.skipped is True
        assert result.output_path is None
        assert "exceeds limit" in result.skip_reason

    def test_skipped_result_has_empty_errors(self, tmp_path: Path) -> None:
        """A skipped result must have no errors — skipping is not an error."""
        large_file = tmp_path / "large.pdf"
        large_file.write_bytes(b"x" * (3 * 1024 * 1024))
        config = _make_config(max_file_size_mb=1)

        result = convert_file(large_file, tmp_path / "output", config)

        assert result.errors == []


# ---------------------------------------------------------------------------
# Successful PDF conversion
# ---------------------------------------------------------------------------


class TestConvertFilePdf:
    def test_pdf_dispatches_to_marker_engine(self, tmp_path: Path) -> None:
        """A .pdf file must trigger a call to the Marker conversion engine."""
        source_file = tmp_path / "report.pdf"
        _write_small_file(source_file)
        config = _make_config()
        output_root = tmp_path / "output"

        mock_markdown = "# Report\n\nConverted content."
        mock_page_count = 3

        with (
            patch("deep_thought.file_txt.convert._convert_via_marker") as mock_marker,
            patch("deep_thought.file_txt.convert.write_document") as mock_write,
        ):
            mock_marker.return_value = (mock_markdown, mock_page_count)
            mock_write.return_value = output_root / "report" / "report.md"

            result = convert_file(source_file, output_root, config)

        mock_marker.assert_called_once_with(source_file, config)
        assert result.page_count == 3
        assert result.file_type == "pdf"

    def test_pdf_result_has_correct_word_count(self, tmp_path: Path) -> None:
        """The result word_count must reflect the converted markdown body."""
        source_file = tmp_path / "report.pdf"
        _write_small_file(source_file)
        config = _make_config()
        output_root = tmp_path / "output"

        mock_markdown = "word1 word2 word3 word4 word5"

        with (
            patch("deep_thought.file_txt.convert._convert_via_marker") as mock_marker,
            patch("deep_thought.file_txt.convert.write_document") as mock_write,
        ):
            mock_marker.return_value = (mock_markdown, 1)
            mock_write.return_value = output_root / "report" / "report.md"

            result = convert_file(source_file, output_root, config)

        assert result.word_count == 5


# ---------------------------------------------------------------------------
# Successful Office/HTML conversion
# ---------------------------------------------------------------------------


class TestConvertFileOffice:
    def test_docx_dispatches_to_markitdown_engine(self, tmp_path: Path) -> None:
        """A .docx file must trigger a call to the MarkItDown conversion engine."""
        source_file = tmp_path / "document.docx"
        _write_small_file(source_file)
        config = _make_config()
        output_root = tmp_path / "output"

        mock_markdown = "# Document\n\nContent."

        with (
            patch("deep_thought.file_txt.convert._convert_via_markitdown") as mock_markitdown,
            patch("deep_thought.file_txt.convert.write_document") as mock_write,
        ):
            mock_markitdown.return_value = (mock_markdown, None)
            mock_write.return_value = output_root / "document" / "document.md"

            result = convert_file(source_file, output_root, config)

        mock_markitdown.assert_called_once_with(source_file)
        assert result.page_count is None
        assert result.file_type == "docx"

    def test_html_dispatches_to_markitdown_engine(self, tmp_path: Path) -> None:
        """A .html file must use the MarkItDown engine (not Marker)."""
        source_file = tmp_path / "page.html"
        _write_small_file(source_file)
        config = _make_config()
        output_root = tmp_path / "output"

        with (
            patch("deep_thought.file_txt.convert._convert_via_markitdown") as mock_markitdown,
            patch("deep_thought.file_txt.convert.write_document") as mock_write,
        ):
            mock_markitdown.return_value = ("# Page", None)
            mock_write.return_value = output_root / "page" / "page.md"

            result = convert_file(source_file, output_root, config)

        mock_markitdown.assert_called_once()
        assert result.file_type == "html"


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


class TestConvertFileErrors:
    @pytest.mark.error_handling
    def test_conversion_engine_error_recorded_in_result(self, tmp_path: Path) -> None:
        """An exception from a conversion engine must be recorded in result.errors."""
        source_file = tmp_path / "broken.pdf"
        _write_small_file(source_file)
        config = _make_config()
        output_root = tmp_path / "output"

        with patch("deep_thought.file_txt.convert._convert_via_marker") as mock_marker:
            mock_marker.side_effect = RuntimeError("Marker failed")

            result = convert_file(source_file, output_root, config)

        assert len(result.errors) > 0
        assert "Conversion failed" in result.errors[0]
        assert result.output_path is None

    @pytest.mark.error_handling
    def test_write_error_recorded_in_result(self, tmp_path: Path) -> None:
        """An exception from write_document must be recorded in result.errors."""
        source_file = tmp_path / "report.pdf"
        _write_small_file(source_file)
        config = _make_config()
        output_root = tmp_path / "output"

        # Patch the name as it appears in convert.py's namespace (imported directly)
        with (
            patch("deep_thought.file_txt.convert._convert_via_marker") as mock_marker,
            patch("deep_thought.file_txt.convert.write_document") as mock_write,
        ):
            mock_marker.return_value = ("# Content", 1)
            mock_write.side_effect = OSError("Disk full")

            result = convert_file(source_file, output_root, config)

        assert len(result.errors) > 0
        assert result.output_path is None

    @pytest.mark.error_handling
    def test_result_not_skipped_when_error_occurs(self, tmp_path: Path) -> None:
        """A conversion error must not mark the result as skipped."""
        source_file = tmp_path / "broken.pdf"
        _write_small_file(source_file)
        config = _make_config()
        output_root = tmp_path / "output"

        with patch("deep_thought.file_txt.convert._convert_via_marker") as mock_marker:
            mock_marker.side_effect = RuntimeError("Engine error")

            result = convert_file(source_file, output_root, config)

        assert result.skipped is False
        assert result.errors != []


# ---------------------------------------------------------------------------
# Image extraction integration
# ---------------------------------------------------------------------------


class TestConvertFileImageExtraction:
    def test_image_extraction_called_when_enabled(self, tmp_path: Path) -> None:
        """When extract_images is True, the image_extractor must be called."""
        source_file = tmp_path / "report.pdf"
        _write_small_file(source_file)
        config = _make_config(extract_images=True)
        output_root = tmp_path / "output"

        with (
            patch("deep_thought.file_txt.convert._convert_via_marker") as mock_marker,
            patch("deep_thought.file_txt.image_extractor.extract_images") as mock_extract,
            patch("deep_thought.file_txt.convert.write_document") as mock_write,
        ):
            mock_marker.return_value = ("# Content with ![img](data:image/png;base64,abc)", 1)
            mock_extract.return_value = ("# Content with ![img](img/image_1.png)", True)
            mock_write.return_value = output_root / "report" / "report.md"

            result = convert_file(source_file, output_root, config)

        mock_extract.assert_called_once()
        assert result.has_images is True

    def test_image_extraction_skipped_when_disabled(self, tmp_path: Path) -> None:
        """When extract_images is False, the image_extractor must not be called."""
        source_file = tmp_path / "report.pdf"
        _write_small_file(source_file)
        config = _make_config(extract_images=False)
        output_root = tmp_path / "output"

        with (
            patch("deep_thought.file_txt.convert._convert_via_marker") as mock_marker,
            patch("deep_thought.file_txt.image_extractor.extract_images") as mock_extract,
            patch("deep_thought.file_txt.convert.write_document") as mock_write,
        ):
            mock_marker.return_value = ("# Content", 1)
            mock_write.return_value = output_root / "report" / "report.md"

            convert_file(source_file, output_root, config)

        mock_extract.assert_not_called()
