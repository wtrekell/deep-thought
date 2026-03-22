"""Marker PDF conversion engine wrapper for the file-txt tool.

Wraps the marker-pdf library's PdfConverter to produce markdown from PDF
files. The marker-pdf dependency is optional at import time — a clear error
is raised if the library is not installed.

Model loading is expensive. A module-level cache avoids reloading the model
dict on repeated calls within the same process.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from pathlib import Path

_cached_model_dict: dict[str, Any] | None = None
_cached_converter: Any | None = None
_cached_converter_config: dict[str, object] | None = None


def _get_converter(converter_config: dict[str, object]) -> Any:
    """Return a cached PdfConverter, recreating it only when config changes.

    The model dict (which holds the heavy neural network weights) is cached
    separately and is never discarded — only the converter wrapper is replaced
    when the config changes.
    """
    global _cached_model_dict, _cached_converter, _cached_converter_config

    if _cached_converter is not None and _cached_converter_config == converter_config:
        return _cached_converter

    from marker.converters.pdf import PdfConverter  # type: ignore[import-untyped]
    from marker.models import create_model_dict  # type: ignore[import-untyped]

    if _cached_model_dict is None:
        _cached_model_dict = create_model_dict()

    _cached_converter = PdfConverter(config=converter_config, artifact_dict=_cached_model_dict)
    _cached_converter_config = converter_config
    return _cached_converter


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
        import marker.converters.pdf  # type: ignore[import-untyped]  # noqa: F401
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

    converter = _get_converter(converter_config)
    conversion_result = converter(str(source_path))

    if hasattr(conversion_result, "markdown"):
        markdown_text: str = conversion_result.markdown
    else:
        markdown_text = str(conversion_result)
    page_count: int = len(conversion_result.pages) if hasattr(conversion_result, "pages") else 0

    return markdown_text, page_count
