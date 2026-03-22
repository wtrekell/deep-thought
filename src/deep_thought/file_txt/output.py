"""Document output writer for the file-txt tool.

Generates output markdown files with YAML frontmatter from converted
document content. Each document is written to its own subdirectory
inside the output root.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path  # noqa: TC003
from typing import Any


def write_document(
    markdown_text: str,
    source_path: Path,
    output_root: Path,
    *,
    file_type: str,
    page_count: int | None,
    word_count: int,
    has_images: bool,
    email_metadata: dict[str, Any] | None = None,
) -> Path:
    """Write converted markdown to disk with YAML frontmatter.

    Creates a subdirectory named after the source document (without
    extension) inside output_root, then writes
    ``{document_name}/{document_name}.md``.

    Frontmatter fields:
    - tool: always "file-txt"
    - source_file: the original filename
    - file_type: the document type string (e.g., "pdf", "docx")
    - page_count: included only when not None (PDF documents)
    - word_count: approximate word count of the body text
    - has_images: whether images were found and extracted
    - processed_date: ISO 8601 datetime in UTC
    - from, to, subject, date, has_attachments, attachment_count: email only

    Args:
        markdown_text: The converted document body (may already have images
                       rewritten by image_extractor).
        source_path: Original source file path (used to derive the document
                     name and populate the source_file frontmatter field).
        output_root: Root directory under which per-document subdirectories
                     are created.
        file_type: Short string identifying the document type, e.g. "pdf".
        page_count: Number of pages (PDF only). Pass None for non-PDF files
                    to omit this field from the frontmatter.
        word_count: Approximate number of words in markdown_text.
        has_images: Whether the document contains extracted images.
        email_metadata: Optional dict with email-specific fields (from_address,
                        to_address, subject, date, has_attachments, attachment_count).
                        Pass None for non-email files.

    Returns:
        The Path to the written markdown file.
    """
    document_name = source_path.stem
    document_dir = output_root / document_name

    # Disambiguate if the directory already contains a file from a different source
    if document_dir.exists():
        existing_md = document_dir / f"{document_name}.md"
        if existing_md.exists():
            existing_content = existing_md.read_text(encoding="utf-8")
            if f"source_file: {source_path.name}" not in existing_content:
                document_name = f"{source_path.stem}_{source_path.suffix.lstrip('.')}"
                document_dir = output_root / document_name

    document_dir.mkdir(parents=True, exist_ok=True)
    output_file_path = document_dir / f"{document_name}.md"

    processed_date = datetime.now(tz=UTC).isoformat()
    frontmatter_lines = _build_frontmatter(
        source_file=source_path.name,
        file_type=file_type,
        page_count=page_count,
        word_count=word_count,
        has_images=has_images,
        processed_date=processed_date,
        email_metadata=email_metadata,
    )

    full_content = frontmatter_lines + "\n" + markdown_text
    output_file_path.write_text(full_content, encoding="utf-8")

    return output_file_path


def _build_frontmatter(
    *,
    source_file: str,
    file_type: str,
    page_count: int | None,
    word_count: int,
    has_images: bool,
    processed_date: str,
    email_metadata: dict[str, Any] | None = None,
) -> str:
    """Build the YAML frontmatter block as a string.

    page_count is omitted when None so that non-PDF documents do not
    include a meaningless zero count. Email metadata fields are included
    only when email_metadata is provided.

    Args:
        source_file: The original filename to include in frontmatter.
        file_type: The document type string.
        page_count: Page count for PDF files; None to omit the field.
        word_count: Approximate word count of the document body.
        has_images: Whether the document contains images.
        processed_date: ISO 8601 datetime string for when processing occurred.
        email_metadata: Optional dict with email-specific frontmatter fields.

    Returns:
        A string containing the full YAML frontmatter block including
        the opening and closing ``---`` delimiters and a trailing newline.
    """
    lines: list[str] = ["---"]
    lines.append("tool: file-txt")
    lines.append(f"source_file: {source_file}")
    lines.append(f"file_type: {file_type}")
    if page_count is not None:
        lines.append(f"page_count: {page_count}")
    if email_metadata is not None:
        lines.append(f'from: "{_escape_yaml_string(email_metadata["from_address"])}"')
        lines.append(f'to: "{_escape_yaml_string(email_metadata["to_address"])}"')
        lines.append(f'subject: "{_escape_yaml_string(email_metadata["subject"])}"')
        lines.append(f'date: "{_escape_yaml_string(email_metadata["date"])}"')
        lines.append(f"has_attachments: {str(email_metadata['has_attachments']).lower()}")
        lines.append(f"attachment_count: {email_metadata['attachment_count']}")
    lines.append(f"word_count: {word_count}")
    lines.append(f"has_images: {str(has_images).lower()}")
    lines.append(f"processed_date: {processed_date}")
    lines.append("---")
    return "\n".join(lines) + "\n"


def _escape_yaml_string(value: str) -> str:
    """Escape characters that would break a double-quoted YAML string value.

    Replaces backslashes and double quotes so that the resulting string is
    safe for interpolation inside YAML double-quoted scalars.

    Args:
        value: The raw string value from email metadata.

    Returns:
        An escaped string safe for use inside YAML double quotes.
    """
    return value.replace("\\", "\\\\").replace('"', '\\"')


def count_words(text: str) -> int:
    """Return an approximate word count for a string.

    Splits on whitespace — suitable for estimating document length without
    accounting for markdown syntax tokens.

    Args:
        text: Any string, typically the body of a converted markdown document.

    Returns:
        Number of whitespace-separated tokens in text.
    """
    return len(text.split())
