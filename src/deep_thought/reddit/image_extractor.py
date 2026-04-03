"""Image download for Reddit posts.

Extracts direct image URLs from a post's markdown content, downloads each to
an ``img/`` subdirectory adjacent to the markdown file, and returns updated
markdown where remote image URLs are replaced with local relative paths.

Only direct image links (ending with a recognised image extension) are
downloaded. Reddit video URLs, external links to galleries, and any URL that
does not resolve to a downloadable image file are left unchanged.

This module is intentionally dependency-free beyond the Python standard
library — it uses ``urllib.request`` for HTTP, matching the pattern
established by ``web/image_extractor.py``.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import urllib.request
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ALLOWED_IMAGE_EXTENSIONS: frozenset[str] = frozenset({".jpg", ".jpeg", ".png", ".gif", ".webp"})
_ALLOWED_URL_SCHEMES: frozenset[str] = frozenset({"http", "https"})
_IMAGE_DOWNLOAD_TIMEOUT_SECONDS: int = 30
_IMAGE_MAX_SIZE_BYTES: int = 20 * 1024 * 1024  # 20 MB

# Maps MIME type (Content-Type header) to a canonical file extension.
_MIME_TO_EXTENSION: dict[str, str] = {
    "image/jpeg": ".jpg",
    "image/jpg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}

# Matches markdown image references of the form ![alt](url)
_MARKDOWN_IMAGE_PATTERN: re.Pattern[str] = re.compile(r"!\[([^\]]*)\]\(([^)]+)\)")

# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _is_direct_image_url(url: str) -> bool:
    """Return True if the URL appears to point directly to a downloadable image file.

    Checks the URL path suffix against the set of allowed image extensions.
    Reddit video URLs, gallery links, and other non-image URLs are excluded.

    Args:
        url: Absolute URL string to evaluate.

    Returns:
        True if the URL ends with a recognised image extension, False otherwise.
    """
    # Strip query strings before checking the extension
    path_without_query = url.split("?")[0].split("#")[0]
    suffix = Path(path_without_query).suffix.lower()
    return suffix in _ALLOWED_IMAGE_EXTENSIONS


def _download_single_image(image_url: str, destination_path: Path) -> bool:
    """Download a single image URL to destination_path.

    Validates the URL scheme and resolved IP address before fetching to
    prevent SSRF against private network addresses. Logs a warning and
    returns False on any error so callers can keep the original URL.

    Args:
        image_url: The absolute image URL to fetch.
        destination_path: Where to write the downloaded bytes.

    Returns:
        True if the image was downloaded successfully, False otherwise.
    """
    parsed = urlparse(image_url)

    if parsed.scheme not in _ALLOWED_URL_SCHEMES:
        logger.warning("Skipping image %s: disallowed URL scheme %r", image_url, parsed.scheme)
        return False

    try:
        image_host = parsed.hostname or ""
        # DNS rebinding limitation: this pre-resolution check and the subsequent
        # urlopen() call each perform their own DNS lookup. A DNS rebinding attack
        # could return a public IP here and a private IP for the real connection,
        # bypassing the guard. This is low-risk for a personal tool operating against
        # known Reddit CDN hostnames, but the check is not a complete SSRF defense.
        resolved_ip = ipaddress.ip_address(socket.gethostbyname(image_host))
        if (
            resolved_ip.is_private
            or resolved_ip.is_loopback
            or resolved_ip.is_link_local
            or resolved_ip.is_reserved
            or resolved_ip.is_multicast
        ):
            logger.warning("Skipping image %s: resolved to non-routable IP %s", image_url, resolved_ip)
            return False
    except (OSError, ValueError):
        logger.warning("Skipping image %s: could not resolve hostname", image_url)
        return False

    url_extension = Path(parsed.path).suffix.lower() or ".jpg"

    try:
        with urllib.request.urlopen(image_url, timeout=_IMAGE_DOWNLOAD_TIMEOUT_SECONDS) as response:  # noqa: S310
            content_type_header: str = response.headers.get("Content-Type", "")
            mime_type = content_type_header.split(";")[0].strip().lower()
            resolved_extension = _MIME_TO_EXTENSION.get(mime_type, url_extension) or ".jpg"

            # Adjust destination extension to match the actual content type
            final_destination = destination_path.with_suffix(resolved_extension)

            image_data = response.read(_IMAGE_MAX_SIZE_BYTES + 1)

        if len(image_data) > _IMAGE_MAX_SIZE_BYTES:
            logger.warning("Skipping image %s: exceeds %d-byte size limit", image_url, _IMAGE_MAX_SIZE_BYTES)
            return False

        final_destination.write_bytes(image_data)
        return True

    except Exception as download_error:
        logger.warning("Skipping image %s: %s", image_url, download_error)
        return False


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def download_post_images(
    output_path: Path,
    markdown_content: str,
) -> str:
    """Download images referenced in a post's markdown and rewrite their URLs to local paths.

    Scans markdown_content for ``![alt](url)`` patterns whose URL ends with a
    recognised image extension. For each matching URL, attempts to download the
    image to ``{output_path.parent}/img/`` and rewrites the markdown reference
    to the relative local path.

    On download failure the original URL is left intact so the markdown
    remains valid — the failure is logged as a warning.

    Args:
        output_path: The path to the markdown file that was written to disk.
            Images are saved to an ``img/`` directory adjacent to this file.
        markdown_content: The full markdown string to scan and rewrite.

    Returns:
        Updated markdown content with successful downloads replaced by local
        relative paths. Unchanged if no images were found or all downloads
        failed.
    """
    image_dir = output_path.parent / "img"

    updated_markdown = markdown_content
    image_counter = 0

    for match in _MARKDOWN_IMAGE_PATTERN.finditer(markdown_content):
        alt_text = match.group(1)
        image_url = match.group(2)

        if not _is_direct_image_url(image_url):
            continue

        image_counter += 1
        url_extension = Path(image_url.split("?")[0]).suffix.lower() or ".jpg"
        candidate_filename = f"image_{image_counter:03d}{url_extension}"
        destination_path = image_dir / candidate_filename

        image_dir.mkdir(parents=True, exist_ok=True)
        success = _download_single_image(image_url, destination_path)

        if success:
            # Find the file that was actually written — extension may differ from the URL
            # because _download_single_image adjusts for Content-Type.
            actual_extensions = list(_MIME_TO_EXTENSION.values()) + [url_extension]
            actual_path: Path | None = None
            for candidate_extension in dict.fromkeys(actual_extensions):
                candidate = image_dir / f"image_{image_counter:03d}{candidate_extension}"
                if candidate.exists():
                    actual_path = candidate
                    break

            if actual_path is not None:
                relative_local_path = f"img/{actual_path.name}"
                original_reference = match.group(0)
                local_reference = f"![{alt_text}]({relative_local_path})"
                updated_markdown = updated_markdown.replace(original_reference, local_reference, 1)
                logger.debug("Downloaded image %s -> %s", image_url, actual_path)
            else:
                logger.warning("Image download reported success but file not found for %s", image_url)

    return updated_markdown
