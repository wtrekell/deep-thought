"""MarkItDown Office/web conversion engine wrapper for the file-txt tool.

Wraps the markitdown library to produce markdown from Office documents
(.docx, .pptx, .xlsx) and HTML files. The markitdown dependency is
optional at import time — a clear error is raised if not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def convert_office(source_path: Path) -> str:
    """Convert an Office or HTML file to markdown text using MarkItDown.

    Supports .docx, .pptx, .xlsx, .html, and .htm files. The appropriate
    converter is selected automatically by MarkItDown based on the file
    extension.

    Args:
        source_path: Absolute path to the file to convert.

    Returns:
        Markdown text representation of the document content.

    Raises:
        ImportError: If markitdown is not installed.
        FileNotFoundError: If source_path does not exist.
        OSError: If the file cannot be read.
    """
    try:
        from markitdown import MarkItDown
    except ImportError as import_error:
        raise ImportError(
            "The markitdown library is required for Office/HTML conversion but is not installed. "
            "Install it with: pip install markitdown>=0.1.0"
        ) from import_error

    if not source_path.exists():
        raise FileNotFoundError(f"File not found: {source_path}")

    converter = MarkItDown()
    conversion_result = converter.convert(str(source_path))

    if hasattr(conversion_result, "text_content"):
        markdown_text: str = conversion_result.text_content
    else:
        markdown_text = str(conversion_result)
    return markdown_text
