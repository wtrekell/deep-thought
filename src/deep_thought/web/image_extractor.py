"""Image extraction and download for the web crawl tool.

Finds image URLs in HTML pages, downloads them to a local directory,
and returns the paths to successfully downloaded files.
"""

from __future__ import annotations

import logging
import urllib.request
from html.parser import HTMLParser
from pathlib import Path  # noqa: TC003
from urllib.parse import urljoin, urlparse

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# HTML image URL extraction
# ---------------------------------------------------------------------------


class _ImageSrcParser(HTMLParser):
    """Minimal HTMLParser subclass that collects src attributes from <img> tags."""

    def __init__(self) -> None:
        super().__init__()
        self.src_values: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect src attribute values from image tags.

        Args:
            tag: The HTML tag name.
            attrs: List of (name, value) attribute pairs for the tag.
        """
        if tag.lower() == "img":
            for attr_name, attr_value in attrs:
                if attr_name.lower() == "src" and attr_value:
                    self.src_values.append(attr_value)


def extract_image_urls(html: str, base_url: str) -> list[str]:
    """Extract all image URLs from an HTML document.

    Finds all <img src> attributes, resolves relative URLs against base_url,
    deduplicates, and returns a list of absolute URLs.

    Args:
        html: Raw HTML content.
        base_url: Base URL of the page, used to resolve relative image sources.

    Returns:
        Deduplicated list of absolute image URLs found in the HTML.
    """
    parser = _ImageSrcParser()
    parser.feed(html)

    seen_urls: set[str] = set()
    resolved_image_urls: list[str] = []

    for raw_src in parser.src_values:
        absolute_url = urljoin(base_url, raw_src)
        if absolute_url not in seen_urls:
            seen_urls.add(absolute_url)
            resolved_image_urls.append(absolute_url)

    return resolved_image_urls


# ---------------------------------------------------------------------------
# Image download
# ---------------------------------------------------------------------------


def download_images(image_urls: list[str], output_dir: Path) -> list[Path]:
    """Download image URLs to output_dir and return successfully downloaded paths.

    Images are saved as image_001.ext, image_002.ext, etc. where the extension
    is derived from the URL path. Errors on individual images are logged as
    warnings and that image is skipped.

    Args:
        image_urls: List of absolute image URLs to download.
        output_dir: Directory to write downloaded images into. Created if absent.

    Returns:
        List of Path objects for successfully downloaded image files.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    downloaded_paths: list[Path] = []

    for image_index, image_url in enumerate(image_urls, start=1):
        url_path_segment = urlparse(image_url).path
        url_extension = Path(url_path_segment).suffix or ".jpg"
        image_filename = f"image_{image_index:03d}{url_extension}"
        destination_path = output_dir / image_filename

        try:
            urllib.request.urlretrieve(image_url, str(destination_path))  # noqa: S310
            downloaded_paths.append(destination_path)
        except Exception as download_error:
            logger.warning("Skipping image %s: %s", image_url, download_error)

    return downloaded_paths
