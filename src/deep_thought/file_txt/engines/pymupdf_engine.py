"""PyMuPDF4LLM PDF conversion engine wrapper for the file-txt tool.

Wraps pymupdf4llm.to_markdown to produce markdown from native PDF files.
Fast, no ML models, no GPU required.

Note: This engine does not perform OCR. Scanned/image-only PDFs will produce
empty or minimal output. That capability is intentionally not supported.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def convert_pdf(source_path: Path) -> tuple[str, int]:
    """Convert a PDF file to markdown text using pymupdf4llm.

    Args:
        source_path: Absolute path to the PDF file to convert.

    Returns:
        A tuple of (markdown_text, page_count) where markdown_text is the
        full converted content and page_count is the number of pages in the
        document.

    Raises:
        ImportError: If pymupdf4llm is not installed.
        FileNotFoundError: If source_path does not exist.
        OSError: If the file cannot be read.
    """
    try:
        import pymupdf4llm  # type: ignore[import-untyped]
    except ImportError as import_error:
        raise ImportError(
            "The pymupdf4llm library is required for PDF conversion but is not installed. "
            "Install it with: pip install pymupdf4llm>=0.0.17"
        ) from import_error

    if not source_path.exists():
        raise FileNotFoundError(f"PDF file not found: {source_path}")

    import fitz  # type: ignore[import-untyped]

    with fitz.open(str(source_path)) as pdf_document:
        page_count: int = pdf_document.page_count

    markdown_text: str = pymupdf4llm.to_markdown(str(source_path))
    return markdown_text, page_count
