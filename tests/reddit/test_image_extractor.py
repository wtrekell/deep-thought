"""Tests for reddit image extraction and download in deep_thought.reddit.image_extractor."""

from __future__ import annotations

import ipaddress
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

from deep_thought.reddit.image_extractor import (
    _download_single_image,
    _is_direct_image_url,
    download_post_images,
)

# ---------------------------------------------------------------------------
# TestIsDirectImageUrl
# ---------------------------------------------------------------------------


class TestIsDirectImageUrl:
    def test_jpg_url_is_direct_image(self) -> None:
        """A URL ending in .jpg must be identified as a direct image link."""
        assert _is_direct_image_url("https://i.redd.it/abc123.jpg") is True

    def test_jpeg_url_is_direct_image(self) -> None:
        """A URL ending in .jpeg must be identified as a direct image link."""
        assert _is_direct_image_url("https://example.com/photo.jpeg") is True

    def test_png_url_is_direct_image(self) -> None:
        """A URL ending in .png must be identified as a direct image link."""
        assert _is_direct_image_url("https://i.redd.it/img.png") is True

    def test_gif_url_is_direct_image(self) -> None:
        """A URL ending in .gif must be identified as a direct image link."""
        assert _is_direct_image_url("https://example.com/anim.gif") is True

    def test_webp_url_is_direct_image(self) -> None:
        """A URL ending in .webp must be identified as a direct image link."""
        assert _is_direct_image_url("https://example.com/image.webp") is True

    def test_extension_check_is_case_insensitive(self) -> None:
        """Extension check must be case-insensitive (.JPG, .PNG, etc.)."""
        assert _is_direct_image_url("https://example.com/photo.JPG") is True
        assert _is_direct_image_url("https://example.com/photo.PNG") is True

    def test_reddit_video_url_not_direct_image(self) -> None:
        """A Reddit video URL must not be identified as a direct image link."""
        assert _is_direct_image_url("https://v.redd.it/abc123") is False

    def test_reddit_gallery_url_not_direct_image(self) -> None:
        """A Reddit gallery URL must not be identified as a direct image link."""
        assert _is_direct_image_url("https://www.reddit.com/gallery/abc123") is False

    def test_html_page_url_not_direct_image(self) -> None:
        """A URL pointing to an HTML page must not be identified as a direct image link."""
        assert _is_direct_image_url("https://example.com/page.html") is False

    def test_url_with_query_string_strips_query_before_checking(self) -> None:
        """Query strings must be stripped before extension checking."""
        assert _is_direct_image_url("https://i.redd.it/photo.jpg?width=1080") is True

    def test_url_with_no_extension_not_direct_image(self) -> None:
        """A URL with no file extension must not be identified as a direct image link."""
        assert _is_direct_image_url("https://example.com/image") is False


# ---------------------------------------------------------------------------
# TestDownloadSingleImage
# ---------------------------------------------------------------------------


class TestDownloadSingleImage:
    def test_downloads_image_successfully(self, tmp_path: Path) -> None:
        """A valid image URL with routable IP must be downloaded to destination_path."""
        destination = tmp_path / "image_001.jpg"
        fake_image_bytes = b"\xff\xd8\xff" + b"\x00" * 100  # minimal JPEG-like header

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.headers.get.return_value = "image/jpeg"
        mock_response.read.return_value = fake_image_bytes

        with (
            patch("socket.gethostbyname", return_value="93.184.216.34"),
            patch("ipaddress.ip_address", return_value=ipaddress.ip_address("93.184.216.34")),
            patch("urllib.request.urlopen", return_value=mock_response),
        ):
            result = _download_single_image("https://example.com/photo.jpg", destination)

        assert result is True
        assert destination.exists()
        assert destination.read_bytes() == fake_image_bytes

    def test_rejects_disallowed_url_scheme(self, tmp_path: Path) -> None:
        """A URL with a non-http/https scheme must be rejected without attempting download."""
        destination = tmp_path / "image_001.jpg"
        result = _download_single_image("file:///etc/passwd", destination)
        assert result is False
        assert not destination.exists()

    def test_rejects_private_ip_address(self, tmp_path: Path) -> None:
        """A URL that resolves to a private IP address must be rejected (SSRF prevention)."""
        destination = tmp_path / "image_001.jpg"
        with patch("socket.gethostbyname", return_value="192.168.1.1"):
            result = _download_single_image("https://internal.example.com/photo.jpg", destination)
        assert result is False
        assert not destination.exists()

    def test_rejects_loopback_ip_address(self, tmp_path: Path) -> None:
        """A URL that resolves to a loopback IP must be rejected."""
        destination = tmp_path / "image_001.jpg"
        with patch("socket.gethostbyname", return_value="127.0.0.1"):
            result = _download_single_image("https://localhost/photo.jpg", destination)
        assert result is False

    def test_returns_false_on_dns_failure(self, tmp_path: Path) -> None:
        """When hostname resolution fails, _download_single_image must return False."""
        destination = tmp_path / "image_001.jpg"
        with patch("socket.gethostbyname", side_effect=OSError("DNS lookup failed")):
            result = _download_single_image("https://nonexistent.example.com/photo.jpg", destination)
        assert result is False

    def test_returns_false_on_http_error(self, tmp_path: Path) -> None:
        """When the HTTP request raises an exception, False is returned gracefully."""
        destination = tmp_path / "image_001.jpg"
        with (
            patch("socket.gethostbyname", return_value="93.184.216.34"),
            patch("ipaddress.ip_address", return_value=ipaddress.ip_address("93.184.216.34")),
            patch("urllib.request.urlopen", side_effect=OSError("Connection refused")),
        ):
            result = _download_single_image("https://example.com/photo.jpg", destination)
        assert result is False

    def test_rejects_oversized_image(self, tmp_path: Path) -> None:
        """An image exceeding the size limit must be rejected and not written to disk."""
        destination = tmp_path / "image_001.jpg"
        # Simulate a response that returns slightly more than the limit
        oversized_bytes = b"\x00" * (20 * 1024 * 1024 + 2)

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.headers.get.return_value = "image/jpeg"
        mock_response.read.return_value = oversized_bytes

        with (
            patch("socket.gethostbyname", return_value="93.184.216.34"),
            patch("ipaddress.ip_address", return_value=ipaddress.ip_address("93.184.216.34")),
            patch("urllib.request.urlopen", return_value=mock_response),
        ):
            result = _download_single_image("https://example.com/large.jpg", destination)

        assert result is False
        assert not destination.exists()


# ---------------------------------------------------------------------------
# TestDownloadPostImages
# ---------------------------------------------------------------------------


class TestDownloadPostImages:
    def test_rewrites_successful_download_to_local_path(self, tmp_path: Path) -> None:
        """A successfully downloaded image URL must be replaced with a local path."""
        markdown_file = tmp_path / "post.md"
        markdown_content = "# Title\n\n![Image](https://i.redd.it/abc.jpg)"
        fake_image_bytes = b"\xff\xd8\xff" + b"\x00" * 50

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.headers.get.return_value = "image/jpeg"
        mock_response.read.return_value = fake_image_bytes

        with (
            patch("socket.gethostbyname", return_value="93.184.216.34"),
            patch("ipaddress.ip_address", return_value=ipaddress.ip_address("93.184.216.34")),
            patch("urllib.request.urlopen", return_value=mock_response),
        ):
            result = download_post_images(
                output_path=markdown_file,
                markdown_content=markdown_content,
            )

        assert "img/image_001.jpg" in result
        assert "https://i.redd.it/abc.jpg" not in result

    def test_keeps_original_url_on_download_failure(self, tmp_path: Path) -> None:
        """When a download fails, the original remote URL must be preserved."""
        markdown_file = tmp_path / "post.md"
        original_url = "https://i.redd.it/abc.jpg"
        markdown_content = f"# Title\n\n![Image]({original_url})"

        with (
            patch("socket.gethostbyname", side_effect=OSError("DNS lookup failed")),
        ):
            result = download_post_images(
                output_path=markdown_file,
                markdown_content=markdown_content,
            )

        assert original_url in result

    def test_skips_non_image_urls(self, tmp_path: Path) -> None:
        """Non-image URLs (videos, galleries) must be left unchanged."""
        markdown_file = tmp_path / "post.md"
        video_url = "https://v.redd.it/abc123"
        markdown_content = f"# Title\n\n![Video]({video_url})"

        result = download_post_images(
            output_path=markdown_file,
            markdown_content=markdown_content,
        )

        assert video_url in result
        assert "img/" not in result

    def test_creates_img_subdirectory(self, tmp_path: Path) -> None:
        """The img/ directory must be created when a download succeeds."""
        markdown_file = tmp_path / "rule_name" / "post.md"
        markdown_file.parent.mkdir(parents=True)
        fake_image_bytes = b"\x89PNG\r\n" + b"\x00" * 50

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.headers.get.return_value = "image/png"
        mock_response.read.return_value = fake_image_bytes

        with (
            patch("socket.gethostbyname", return_value="93.184.216.34"),
            patch("ipaddress.ip_address", return_value=ipaddress.ip_address("93.184.216.34")),
            patch("urllib.request.urlopen", return_value=mock_response),
        ):
            download_post_images(
                output_path=markdown_file,
                markdown_content="![Photo](https://i.redd.it/photo.png)",
            )

        assert (markdown_file.parent / "img").is_dir()

    def test_markdown_with_no_images_is_unchanged(self, tmp_path: Path) -> None:
        """Markdown with no image references must be returned without modification."""
        markdown_file = tmp_path / "post.md"
        original_markdown = "# Title\n\nSome text without any images."

        result = download_post_images(
            output_path=markdown_file,
            markdown_content=original_markdown,
        )

        assert result == original_markdown

    def test_multiple_images_are_downloaded_and_numbered(self, tmp_path: Path) -> None:
        """Multiple images in a post must each be downloaded and numbered sequentially."""
        markdown_file = tmp_path / "post.md"
        markdown_content = "# Title\n\n![First](https://i.redd.it/first.jpg)\n\n![Second](https://i.redd.it/second.jpg)"
        fake_image_bytes = b"\xff\xd8\xff" + b"\x00" * 20

        mock_response = MagicMock()
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        mock_response.headers.get.return_value = "image/jpeg"
        mock_response.read.return_value = fake_image_bytes

        with (
            patch("socket.gethostbyname", return_value="93.184.216.34"),
            patch("ipaddress.ip_address", return_value=ipaddress.ip_address("93.184.216.34")),
            patch("urllib.request.urlopen", return_value=mock_response),
        ):
            result = download_post_images(
                output_path=markdown_file,
                markdown_content=markdown_content,
            )

        assert "img/image_001.jpg" in result
        assert "img/image_002.jpg" in result
