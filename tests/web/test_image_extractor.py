"""Tests for image_extractor.py: extract_image_urls and download_images."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from deep_thought.web.image_extractor import download_images, extract_image_urls

# ---------------------------------------------------------------------------
# HTML fixtures
# ---------------------------------------------------------------------------

_HTML_WITH_TWO_IMAGES = """<!DOCTYPE html>
<html>
<head><title>Page</title></head>
<body>
<img src="/images/photo.jpg" alt="A photo">
<img src="https://cdn.example.com/banner.png" alt="Banner">
</body>
</html>"""

_HTML_WITH_DATA_URI = """<!DOCTYPE html>
<html>
<body>
<img src="data:image/png;base64,iVBORw0KGgo=" alt="Inline">
<img src="/normal.jpg" alt="Normal">
</body>
</html>"""

_HTML_NO_IMAGES = """<!DOCTYPE html>
<html><body><p>No images here.</p></body></html>"""

_HTML_WITH_RELATIVE_IMAGES = """<!DOCTYPE html>
<html>
<body>
<img src="../assets/logo.png" alt="Logo">
<img src="images/photo.jpg" alt="Photo">
</body>
</html>"""

_HTML_WITH_DUPLICATE_IMAGES = """<!DOCTYPE html>
<html>
<body>
<img src="/images/photo.jpg" alt="First">
<img src="/images/photo.jpg" alt="Second (duplicate)">
</body>
</html>"""


# ---------------------------------------------------------------------------
# TestExtractImageUrls
# ---------------------------------------------------------------------------


class TestExtractImageUrls:
    """Tests for extract_image_urls."""

    def test_returns_absolute_urls_for_relative_src(self) -> None:
        """Relative src paths must be resolved to absolute URLs using the base URL."""
        result = extract_image_urls(_HTML_WITH_RELATIVE_IMAGES, "https://example.com/blog/post/")
        assert all(url.startswith("https://") for url in result)

    def test_returns_empty_list_when_no_images(self) -> None:
        """HTML with no img tags must return an empty list."""
        result = extract_image_urls(_HTML_NO_IMAGES, "https://example.com/")
        assert result == []

    def test_filters_data_uri_images(self) -> None:
        """data: URI images must be excluded from the returned URL list."""
        result = extract_image_urls(_HTML_WITH_DATA_URI, "https://example.com/")
        assert all(not url.startswith("data:") for url in result)

    def test_data_uri_page_still_returns_normal_image(self) -> None:
        """A page with a data: URI and a normal image must return only the normal image."""
        result = extract_image_urls(_HTML_WITH_DATA_URI, "https://example.com/")
        assert len(result) == 1
        assert "normal.jpg" in result[0]

    def test_deduplicates_identical_urls(self) -> None:
        """The same image URL appearing multiple times must appear only once in results."""
        result = extract_image_urls(_HTML_WITH_DUPLICATE_IMAGES, "https://example.com/")
        assert len(result) == 1

    def test_preserves_already_absolute_urls(self) -> None:
        """An img src that is already an absolute URL must be returned as-is."""
        result = extract_image_urls(_HTML_WITH_TWO_IMAGES, "https://example.com/")
        absolute_cdn_url = "https://cdn.example.com/banner.png"
        assert absolute_cdn_url in result

    def test_returns_list_not_set(self) -> None:
        """The return type must be a list (preserving insertion order for determinism)."""
        result = extract_image_urls(_HTML_WITH_TWO_IMAGES, "https://example.com/")
        assert isinstance(result, list)


# ---------------------------------------------------------------------------
# TestDownloadImages
# ---------------------------------------------------------------------------


class TestDownloadImages:
    """Tests for download_images."""

    def _make_mock_response(
        self,
        content: bytes = b"fake image data",
        content_type: str = "image/jpeg",
    ) -> MagicMock:
        """Build a mock urlopen response with configurable content and Content-Type."""
        mock_response = MagicMock()
        mock_response.headers = MagicMock()
        mock_response.headers.get = MagicMock(return_value=content_type)
        mock_response.read = MagicMock(return_value=content)
        mock_response.__enter__ = MagicMock(return_value=mock_response)
        mock_response.__exit__ = MagicMock(return_value=False)
        return mock_response

    def test_creates_output_directory_if_absent(self, tmp_path: Path) -> None:
        """download_images must create the output directory if it does not exist."""
        output_dir = tmp_path / "images"
        with patch("deep_thought.web.image_extractor.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_mock_response()
            download_images(["https://example.com/photo.jpg"], output_dir)
        assert output_dir.exists()

    def test_returns_list_of_downloaded_paths(self, tmp_path: Path) -> None:
        """Successful downloads must return a list of the file paths written."""
        output_dir = tmp_path / "images"
        with patch("deep_thought.web.image_extractor.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_mock_response()
            result = download_images(["https://example.com/photo.jpg"], output_dir)
        assert len(result) == 1
        assert isinstance(result[0], Path)

    def test_uses_content_type_for_extension(self, tmp_path: Path) -> None:
        """When Content-Type is image/png, the downloaded file must have a .png extension."""
        output_dir = tmp_path / "images"
        with patch("deep_thought.web.image_extractor.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_mock_response(content_type="image/png")
            result = download_images(["https://example.com/photo"], output_dir)
        assert result[0].suffix == ".png"

    def test_falls_back_to_url_extension_when_content_type_unknown(self, tmp_path: Path) -> None:
        """When Content-Type is not a known image MIME type, the URL's extension is used."""
        output_dir = tmp_path / "images"
        with patch("deep_thought.web.image_extractor.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_mock_response(content_type="application/octet-stream")
            result = download_images(["https://example.com/photo.gif"], output_dir)
        assert result[0].suffix == ".gif"

    def test_skips_images_with_disallowed_scheme(self, tmp_path: Path) -> None:
        """Images with non-http/https schemes (e.g. ftp://) must be skipped."""
        output_dir = tmp_path / "images"
        with patch("deep_thought.web.image_extractor.urllib.request.urlopen") as mock_urlopen:
            result = download_images(["ftp://example.com/photo.jpg"], output_dir)
        mock_urlopen.assert_not_called()
        assert result == []

    def test_logs_warning_and_skips_on_download_error(self, tmp_path: Path) -> None:
        """A network error on a single image must be logged and that image skipped."""
        output_dir = tmp_path / "images"
        with patch("deep_thought.web.image_extractor.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.side_effect = OSError("Network error")
            result = download_images(["https://example.com/photo.jpg"], output_dir)
        assert result == []

    def test_skips_oversized_images(self, tmp_path: Path) -> None:
        """Images that exceed the 50 MB size limit must be skipped and not written to disk."""
        output_dir = tmp_path / "images"
        # Simulate a response that reports more data than the cap
        oversized_content = b"x" * (50 * 1024 * 1024 + 2)
        with patch("deep_thought.web.image_extractor.urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value = self._make_mock_response(content=oversized_content)
            result = download_images(["https://example.com/huge.jpg"], output_dir)
        assert result == []
        assert not any(output_dir.glob("*")) if output_dir.exists() else True

    def test_returns_empty_list_for_empty_input(self, tmp_path: Path) -> None:
        """An empty URL list must return an empty list without touching the filesystem."""
        output_dir = tmp_path / "images"
        result = download_images([], output_dir)
        assert result == []
