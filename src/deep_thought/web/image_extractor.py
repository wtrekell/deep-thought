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


def _pick_largest_srcset_variant(srcset_value: str) -> str | None:
    """Return the URL with the largest size descriptor from a srcset value.

    Parses the ``srcset`` attribute grammar (comma-separated ``url descriptor``
    pairs where descriptors look like ``2x``, ``1.5x``, ``800w``, ``100h``).
    When multiple variants are declared, the one with the highest numeric
    descriptor wins; unitless or unparseable descriptors score as 1 so they
    can still be compared among themselves.

    Args:
        srcset_value: The raw ``srcset`` attribute value.

    Returns:
        The URL of the largest variant, or None if no parseable URL is found.
    """
    if not srcset_value:
        return None

    best_url: str | None = None
    best_score = -1.0

    for candidate in srcset_value.split(","):
        candidate_parts = candidate.strip().split()
        if not candidate_parts:
            continue
        candidate_url = candidate_parts[0]
        candidate_descriptor = candidate_parts[1] if len(candidate_parts) > 1 else ""

        score = 1.0
        if candidate_descriptor:
            numeric_portion = candidate_descriptor.rstrip("xwh")
            try:
                score = float(numeric_portion)
            except ValueError:
                score = 1.0

        if score > best_score:
            best_score = score
            best_url = candidate_url

    return best_url


class _ImageSrcParser(HTMLParser):
    """Collects image URLs from ``<img>``, ``<img srcset>``, and ``<picture>/<source>``.

    Responsive image patterns handled:

    - ``<img src>`` — the classic case.
    - ``<img srcset="url 1x, url 2x">`` — the largest variant is selected.
    - ``<picture><source srcset=...><img ...></picture>`` — each ``<source>``
      inside a ``<picture>`` contributes its largest variant; the fallback
      ``<img>`` continues to contribute via ``src``/``srcset`` as usual.

    CSS ``background-image: url(...)`` is intentionally not handled — inline
    ``<style>`` and external stylesheets require a CSS parser and a stylesheet
    loader, which is out of scope for a conservative HTMLParser subclass.
    """

    def __init__(self) -> None:
        super().__init__()
        self.src_values: list[str] = []
        self._picture_depth: int = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """Collect candidate image URLs from image-carrying tags.

        Args:
            tag: The HTML tag name.
            attrs: List of (name, value) attribute pairs for the tag.
        """
        tag_lower = tag.lower()
        attrs_map = {attr_name.lower(): attr_value for attr_name, attr_value in attrs if attr_value is not None}

        if tag_lower == "picture":
            self._picture_depth += 1
            return

        if tag_lower == "img":
            src_value = attrs_map.get("src")
            if src_value:
                self.src_values.append(src_value)
            srcset_value = attrs_map.get("srcset")
            if srcset_value:
                best_variant = _pick_largest_srcset_variant(srcset_value)
                if best_variant:
                    self.src_values.append(best_variant)
            return

        if tag_lower == "source" and self._picture_depth > 0:
            # Inside <picture>, <source srcset> is a responsive variant of the
            # outer image. Outside <picture>, <source> belongs to <video>/<audio>.
            srcset_value = attrs_map.get("srcset")
            if srcset_value:
                best_variant = _pick_largest_srcset_variant(srcset_value)
                if best_variant:
                    self.src_values.append(best_variant)

    def handle_endtag(self, tag: str) -> None:
        """Track exit from ``<picture>`` so outer ``<source>`` tags are ignored."""
        if tag.lower() == "picture" and self._picture_depth > 0:
            self._picture_depth -= 1


def extract_image_urls(html: str, base_url: str) -> list[str]:
    """Extract all image URLs from an HTML document.

    Finds ``<img src>``, ``<img srcset>``, and ``<picture>/<source srcset>``
    references, resolves relative URLs against base_url, deduplicates while
    preserving first-seen order, and returns absolute URLs. ``data:`` URIs
    are skipped.

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
