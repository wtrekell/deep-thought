"""Image extraction and download for the web crawl tool.

Finds image URLs in HTML pages, downloads them to a local directory,
and returns the paths to successfully downloaded files.
"""

from __future__ import annotations

import ipaddress
import logging
import socket
import urllib.request
from html.parser import HTMLParser
from pathlib import Path  # noqa: TC003
from urllib.parse import urljoin, urlparse

_ALLOWED_IMAGE_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_IMAGE_DOWNLOAD_TIMEOUT_SECONDS: int = 30
_IMAGE_MAX_SIZE_BYTES: int = 50 * 1024 * 1024  # 50 MB

# Maps MIME type (from Content-Type header) to file extension
_MIME_TO_EXTENSION: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
    "image/svg+xml": ".svg",
    "image/avif": ".avif",
    "image/bmp": ".bmp",
    "image/tiff": ".tiff",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}

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
        if raw_src.lower().startswith("data:"):
            continue
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
        parsed_url = urlparse(image_url)

        if parsed_url.scheme not in _ALLOWED_IMAGE_SCHEMES:
            logger.warning("Skipping image %s: disallowed URL scheme %r", image_url, parsed_url.scheme)
            continue

        try:
            image_host = parsed_url.hostname or ""
            # DNS rebinding limitation: this pre-resolution check and the subsequent
            # urlopen() call each perform their own DNS lookup. A DNS rebinding attack
            # could return a public IP here and a private IP for the real connection,
            # bypassing the guard. This is low-risk for a personal tool operating against
            # known web CDN hostnames, but the check is not a complete SSRF defense.
            resolved_ip = ipaddress.ip_address(socket.gethostbyname(image_host))
            if (
                resolved_ip.is_private
                or resolved_ip.is_loopback
                or resolved_ip.is_link_local
                or resolved_ip.is_reserved
                or resolved_ip.is_multicast
            ):
                logger.warning("Skipping image %s: resolved to non-routable IP %s", image_url, resolved_ip)
                continue
        except (OSError, ValueError):
            logger.warning("Skipping image %s: could not resolve hostname", image_url)
            continue

        url_extension = Path(parsed_url.path).suffix or ".jpg"

        try:
            with urllib.request.urlopen(image_url, timeout=_IMAGE_DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
                content_type_header: str = response.headers.get("Content-Type", "")
                # Strip parameters like "; charset=utf-8" before looking up the MIME type
                mime_type = content_type_header.split(";")[0].strip().lower()
                resolved_extension = _MIME_TO_EXTENSION.get(mime_type, url_extension) or ".jpg"

                image_filename = f"image_{image_index:03d}{resolved_extension}"
                destination_path = output_dir / image_filename

                image_data = response.read(_IMAGE_MAX_SIZE_BYTES + 1)

            if len(image_data) > _IMAGE_MAX_SIZE_BYTES:
                logger.warning("Skipping image %s: exceeds %d-byte size limit", image_url, _IMAGE_MAX_SIZE_BYTES)
                continue

            destination_path.write_bytes(image_data)
            downloaded_paths.append(destination_path)
        except Exception as download_error:
            logger.warning("Skipping image %s: %s", image_url, download_error)

    return downloaded_paths
