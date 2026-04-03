"""Single-file conversion orchestrator for the file-txt tool.

Dispatches each source file to the appropriate engine, applies image
extraction, writes output, and collects results into a typed ConvertResult.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from deep_thought.file_txt.filters import is_within_size_limit
from deep_thought.file_txt.output import count_words, write_document

if TYPE_CHECKING:
    from pathlib import Path

    from deep_thought.file_txt.config import FileTxtConfig


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass
class ConvertResult:
    """Outcome of a single file conversion attempt."""

    source_path: Path
    output_path: Path | None
    file_type: str
    word_count: int
    page_count: int | None
    has_images: bool
    skipped: bool
    skip_reason: str
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

_PDF_EXTENSION = ".pdf"
_EMAIL_EXTENSIONS = {".eml", ".msg"}

_EXTENSION_TO_TYPE: dict[str, str] = {
    ".pdf": "pdf",
    ".docx": "docx",
    ".pptx": "pptx",
    ".xlsx": "xlsx",
    ".html": "html",
    ".htm": "html",
    ".eml": "eml",
    ".msg": "msg",
}


def _file_type_from_path(source_path: Path) -> str:
    """Return a short file type string derived from the file extension.

    Args:
        source_path: The path whose extension determines the type.

    Returns:
        A lowercase type string such as 'pdf', 'docx', or 'html'.
        Falls back to the raw extension (without dot) when unknown.
    """
    extension = source_path.suffix.lower()
    return _EXTENSION_TO_TYPE.get(extension, extension.lstrip("."))


def _convert_via_pymupdf(source_path: Path) -> tuple[str, int]:
    """Delegate PDF conversion to the PyMuPDF engine.

    Args:
        source_path: Path to the PDF file.

    Returns:
        (markdown_text, page_count) from the PyMuPDF engine.
    """
    from deep_thought.file_txt.engines.pymupdf_engine import convert_pdf

    return convert_pdf(source_path)


def _convert_via_markitdown(source_path: Path) -> tuple[str, None]:
    """Delegate Office/HTML conversion to the MarkItDown engine.

    Args:
        source_path: Path to the Office or HTML file.

    Returns:
        (markdown_text, None) — page count is not available for these types.
    """
    from deep_thought.file_txt.engines.markitdown_engine import convert_office

    markdown_text = convert_office(source_path)
    return markdown_text, None


def _convert_via_email_engine(source_path: Path, config: FileTxtConfig) -> tuple[str, dict[str, Any]]:
    """Delegate email conversion to the appropriate email engine.

    Routes .eml files to the EML engine and .msg files to the MSG engine.

    Args:
        source_path: Path to the email file.
        config: The loaded FileTxtConfig supplying email settings.

    Returns:
        (markdown_text, email_metadata) from the email engine.
    """
    extension = source_path.suffix.lower()
    if extension == ".eml":
        from deep_thought.file_txt.engines.eml_engine import convert_eml

        return convert_eml(
            source_path,
            prefer_html=config.email.prefer_html,
            full_headers=config.email.full_headers,
            include_attachments=config.email.include_attachments,
        )

    from deep_thought.file_txt.engines.msg_engine import convert_msg

    return convert_msg(
        source_path,
        prefer_html=config.email.prefer_html,
        full_headers=config.email.full_headers,
        include_attachments=config.email.include_attachments,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def convert_file(
    source_path: Path,
    output_root: Path,
    config: FileTxtConfig,
    *,
    dry_run: bool = False,
) -> ConvertResult:
    """Convert a single file to markdown and write the output.

    Dispatch logic:
    - .pdf → PyMuPDF engine
    - .eml, .msg → Email engines
    - all other allowed types → MarkItDown engine

    On dry-run, the conversion engines are not called; a ConvertResult with
    output_path=None is returned to indicate what would have happened.

    Skip conditions (returned with skipped=True, no output written):
    - File exceeds config.limits.max_file_size_mb

    Args:
        source_path: Absolute path to the file to convert.
        output_root: Root directory where per-document output subdirectories
                     are created.
        config: The loaded FileTxtConfig.
        dry_run: If True, return a result describing what would happen without
                 writing any files.

    Returns:
        A ConvertResult summarising the outcome. Check the errors list and
        skipped flag to determine whether the conversion succeeded.
    """
    file_type = _file_type_from_path(source_path)

    # Size check — applied before any expensive I/O
    if not is_within_size_limit(source_path, config.limits.max_file_size_mb):
        file_size_mb = source_path.stat().st_size / (1024 * 1024)
        return ConvertResult(
            source_path=source_path,
            output_path=None,
            file_type=file_type,
            word_count=0,
            page_count=None,
            has_images=False,
            skipped=True,
            skip_reason=(f"File size {file_size_mb:.1f} MB exceeds limit of {config.limits.max_file_size_mb} MB."),
        )

    if dry_run:
        return ConvertResult(
            source_path=source_path,
            output_path=None,
            file_type=file_type,
            word_count=0,
            page_count=None,
            has_images=False,
            skipped=False,
            skip_reason="",
        )

    errors: list[str] = []
    markdown_text: str = ""
    page_count: int | None = None
    email_metadata: dict[str, Any] | None = None

    try:
        if source_path.suffix.lower() == _PDF_EXTENSION:
            markdown_text, page_count = _convert_via_pymupdf(source_path)
        elif source_path.suffix.lower() in _EMAIL_EXTENSIONS:
            markdown_text, email_metadata = _convert_via_email_engine(source_path, config)
        else:
            markdown_text, page_count = _convert_via_markitdown(source_path)
    except Exception as conversion_error:
        errors.append(f"Conversion failed: {conversion_error}")
        return ConvertResult(
            source_path=source_path,
            output_path=None,
            file_type=file_type,
            word_count=0,
            page_count=None,
            has_images=False,
            skipped=False,
            skip_reason="",
            errors=errors,
        )

    has_images = False
    if config.output.extract_images:
        try:
            from deep_thought.file_txt.image_extractor import extract_images

            document_output_dir = output_root / source_path.stem
            markdown_text, has_images = extract_images(markdown_text, document_output_dir)
        except Exception as image_error:
            errors.append(f"Image extraction failed: {image_error}")

    word_count = count_words(markdown_text)

    try:
        output_path = write_document(
            markdown_text,
            source_path,
            output_root,
            file_type=file_type,
            page_count=page_count,
            word_count=word_count,
            has_images=has_images,
            email_metadata=email_metadata,
        )
    except Exception as write_error:
        errors.append(f"Failed to write output: {write_error}")
        return ConvertResult(
            source_path=source_path,
            output_path=None,
            file_type=file_type,
            word_count=word_count,
            page_count=page_count,
            has_images=has_images,
            skipped=False,
            skip_reason="",
            errors=errors,
        )

    return ConvertResult(
        source_path=source_path,
        output_path=output_path,
        file_type=file_type,
        word_count=word_count,
        page_count=page_count,
        has_images=has_images,
        skipped=False,
        skip_reason="",
        errors=errors,
    )
