"""Marker PDF conversion engine wrapper for the file-txt tool.

Wraps the marker-pdf library's PdfConverter to produce markdown from PDF
files. The marker-pdf dependency is optional at import time — a clear error
is raised if the library is not installed.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path


def convert_pdf(
    source_path: Path,
    *,
    force_ocr: bool,
    torch_device: str,
    include_page_numbers: bool,
) -> tuple[str, int]:
    """Convert a PDF file to markdown text using the Marker library.

    Args:
        source_path: Absolute path to the PDF file to convert.
        force_ocr: If True, force OCR even when text is extractable directly.
        torch_device: Hardware device to run Marker on — 'mps', 'cuda', or 'cpu'.
        include_page_numbers: If True, page number markers are retained in
                              the output markdown.

    Returns:
        A tuple of (markdown_text, page_count) where markdown_text is the
        full converted content and page_count is the number of pages processed.

    Raises:
        ImportError: If marker-pdf is not installed.
        FileNotFoundError: If source_path does not exist.
        OSError: If the file cannot be read.
    """
    try:
        from marker.converters.pdf import PdfConverter  # type: ignore[import-not-found]
        from marker.models import create_model_dict  # type: ignore[import-not-found]
    except ImportError as import_error:
        raise ImportError(
            "The marker-pdf library is required for PDF conversion but is not installed. "
            "Install it with: pip install marker-pdf>=1.0.0"
        ) from import_error

    if not source_path.exists():
        raise FileNotFoundError(f"PDF file not found: {source_path}")

    converter_config: dict[str, object] = {
        "force_ocr": force_ocr,
        "device": torch_device,
        "paginate_output": include_page_numbers,
    }

    model_dict = create_model_dict()
    converter = PdfConverter(
        config=converter_config,
        artifact_dict=model_dict,
    )

    conversion_result = converter(str(source_path))

    if hasattr(conversion_result, "markdown"):
        markdown_text: str = conversion_result.markdown
    else:
        markdown_text = str(conversion_result)
    page_count: int = len(conversion_result.pages) if hasattr(conversion_result, "pages") else 0

    return markdown_text, page_count
