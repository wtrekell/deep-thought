"""Tests for the image extraction module in deep_thought.file_txt.image_extractor."""

from __future__ import annotations

import base64
from pathlib import Path  # noqa: TC003

from deep_thought.file_txt.image_extractor import _mime_subtype_to_extension, extract_images

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

# A minimal valid 1x1 pixel PNG, base64-encoded.
_TINY_PNG = base64.b64encode(
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00"
    b"\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00\x00\x01\x01\x00"
    b"\x05\x18\xd8N\x00\x00\x00\x00IEND\xaeB`\x82"
).decode()


# ---------------------------------------------------------------------------
# TestExtractImages
# ---------------------------------------------------------------------------


class TestExtractImages:
    def test_extracts_base64_png_image(self, tmp_path: Path) -> None:
        """A base64-embedded PNG must be extracted to img/ and reference rewritten."""
        markdown = f"![alt text](data:image/png;base64,{_TINY_PNG})"

        updated_markdown, has_images = extract_images(markdown, tmp_path)

        assert has_images is True
        assert "img/image_1.png" in updated_markdown
        assert (tmp_path / "img" / "image_1.png").exists()

    def test_no_images_returns_unchanged(self, tmp_path: Path) -> None:
        """Markdown without embedded images must be returned unchanged."""
        markdown = "# Title\n\nNo images here."

        updated_markdown, has_images = extract_images(markdown, tmp_path)

        assert has_images is False
        assert updated_markdown == markdown

    def test_multiple_images_extracted_sequentially(self, tmp_path: Path) -> None:
        """Multiple images must be numbered sequentially."""
        markdown = f"![img1](data:image/png;base64,{_TINY_PNG})\n![img2](data:image/png;base64,{_TINY_PNG})"

        updated_markdown, has_images = extract_images(markdown, tmp_path)

        assert has_images is True
        assert "image_1.png" in updated_markdown
        assert "image_2.png" in updated_markdown

    def test_external_url_images_left_unchanged(self, tmp_path: Path) -> None:
        """HTTP image references must not be modified."""
        markdown = "![photo](https://example.com/photo.jpg)"

        updated_markdown, has_images = extract_images(markdown, tmp_path)

        assert has_images is False
        assert updated_markdown == markdown

    def test_malformed_base64_leaves_original(self, tmp_path: Path) -> None:
        """Malformed base64 data must leave the original markdown unchanged."""
        # The regex only matches [A-Za-z0-9+/=], so invalid chars like '!' won't match
        markdown = "![bad](data:image/png;base64,!!!not-valid-base64!!!)"

        updated_markdown, has_images = extract_images(markdown, tmp_path)

        assert has_images is False

    def test_svg_xml_mime_type_matched(self, tmp_path: Path) -> None:
        """SVG images with svg+xml MIME type must be extracted."""
        svg_data = base64.b64encode(b"<svg></svg>").decode()
        markdown = f"![icon](data:image/svg+xml;base64,{svg_data})"

        updated_markdown, has_images = extract_images(markdown, tmp_path)

        assert has_images is True
        assert "image_1.svg" in updated_markdown

    def test_jpeg_extension_mapped_to_jpg(self, tmp_path: Path) -> None:
        """MIME type image/jpeg must produce a .jpg file extension."""
        fake_jpeg_data = base64.b64encode(b"\xff\xd8\xff\xe0fake jpeg").decode()
        markdown = f"![photo](data:image/jpeg;base64,{fake_jpeg_data})"

        updated_markdown, has_images = extract_images(markdown, tmp_path)

        assert has_images is True
        assert "image_1.jpg" in updated_markdown

    def test_creates_img_directory(self, tmp_path: Path) -> None:
        """The img/ subdirectory must be created if it doesn't exist."""
        output_dir = tmp_path / "doc_output"
        markdown = f"![img](data:image/png;base64,{_TINY_PNG})"

        extract_images(markdown, output_dir)

        assert (output_dir / "img").is_dir()


# ---------------------------------------------------------------------------
# TestMimeSubtypeToExtension
# ---------------------------------------------------------------------------


class TestMimeSubtypeToExtension:
    def test_jpeg_maps_to_jpg(self) -> None:
        """MIME subtype 'jpeg' must map to extension 'jpg'."""
        assert _mime_subtype_to_extension("jpeg") == "jpg"

    def test_png_maps_to_png(self) -> None:
        """MIME subtype 'png' must map to extension 'png'."""
        assert _mime_subtype_to_extension("png") == "png"

    def test_svg_xml_maps_to_svg(self) -> None:
        """MIME subtype 'svg+xml' must map to extension 'svg'."""
        assert _mime_subtype_to_extension("svg+xml") == "svg"

    def test_unknown_subtype_returns_itself(self) -> None:
        """An unrecognised MIME subtype must be returned as-is."""
        assert _mime_subtype_to_extension("avif") == "avif"
