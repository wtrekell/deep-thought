"""Image extraction for converted markdown documents.

Scans converted markdown for embedded base64 image data, writes each image
to an img/ subdirectory, and rewrites the markdown references to point to
the local files.
"""

from __future__ import annotations

import base64
import re
from pathlib import Path  # noqa: TC003

# Matches markdown image tags that embed base64 data URIs.
# Capture groups: (1) alt text, (2) mime type, (3) base64 data
_BASE64_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\(data:image/([a-zA-Z]+);base64,([A-Za-z0-9+/=]+)\)")

# Matches markdown image tags referencing external or relative paths.
# Capture groups: (1) alt text, (2) src path
_EXTERNAL_IMAGE_PATTERN = re.compile(r"!\[([^\]]*)\]\((?!data:)([^)]+)\)")


def extract_images(markdown_text: str, output_dir: Path) -> tuple[str, bool]:
    """Extract embedded base64 images from markdown and write them to disk.

    Scans markdown_text for embedded base64 data URI images, writes each
    one to output_dir/img/<index>.<ext>, and rewrites the markdown
    references to use the local relative paths.

    External URL image references (http://, https://) and already-local
    references are left unchanged.

    Args:
        markdown_text: The full markdown content from a conversion engine.
        output_dir: The document's output directory. Images are written to
                    a subdirectory named ``img/`` within this directory.

    Returns:
        A tuple of (updated_markdown, has_images) where updated_markdown
        has all base64 data URIs replaced with local ``img/`` paths, and
        has_images is True if any image was found and extracted.
    """
    extracted_count = 0
    updated_markdown = markdown_text

    def _replace_base64_image(match: re.Match[str]) -> str:
        nonlocal extracted_count

        alt_text = match.group(1)
        mime_subtype = match.group(2).lower()
        base64_data = match.group(3)

        # Map mime subtype to a file extension
        extension = _mime_subtype_to_extension(mime_subtype)

        image_filename = f"image_{extracted_count + 1}.{extension}"
        image_path = output_dir / "img" / image_filename

        image_path.parent.mkdir(parents=True, exist_ok=True)

        image_bytes = base64.b64decode(base64_data)
        image_path.write_bytes(image_bytes)

        extracted_count += 1

        local_reference = f"img/{image_filename}"
        return f"![{alt_text}]({local_reference})"

    updated_markdown = _BASE64_IMAGE_PATTERN.sub(_replace_base64_image, updated_markdown)
    has_images = extracted_count > 0

    return updated_markdown, has_images


def _mime_subtype_to_extension(mime_subtype: str) -> str:
    """Map a MIME image subtype string to a file extension.

    Falls back to the subtype itself when there is no known mapping.

    Args:
        mime_subtype: The subtype portion of an image MIME type, e.g. 'jpeg'.

    Returns:
        A file extension string without a leading dot, e.g. 'jpg'.
    """
    mime_to_ext: dict[str, str] = {
        "jpeg": "jpg",
        "jpg": "jpg",
        "png": "png",
        "gif": "gif",
        "webp": "webp",
        "svg+xml": "svg",
        "tiff": "tiff",
        "bmp": "bmp",
    }
    return mime_to_ext.get(mime_subtype, mime_subtype)
