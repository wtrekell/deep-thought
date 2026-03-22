"""Tests for the file filtering functions in deep_thought.file_txt.filters."""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_thought.file_txt.config import FilterConfig
from deep_thought.file_txt.filters import (
    collect_input_files,
    is_allowed_extension,
    is_excluded,
    is_within_size_limit,
)

# ---------------------------------------------------------------------------
# is_allowed_extension
# ---------------------------------------------------------------------------


class TestIsAllowedExtension:
    def test_matching_extension_returns_true(self) -> None:
        """A file with an extension in the allowed list must return True."""
        path = Path("report.pdf")
        assert is_allowed_extension(path, [".pdf", ".docx"]) is True

    def test_non_matching_extension_returns_false(self) -> None:
        """A file with an extension not in the allowed list must return False."""
        path = Path("archive.zip")
        assert is_allowed_extension(path, [".pdf", ".docx"]) is False

    def test_empty_allowed_list_permits_all(self) -> None:
        """An empty allowed list must allow every file."""
        assert is_allowed_extension(Path("anything.xyz"), []) is True

    def test_matching_is_case_insensitive(self) -> None:
        """Extension matching must be case-insensitive."""
        assert is_allowed_extension(Path("REPORT.PDF"), [".pdf"]) is True
        assert is_allowed_extension(Path("doc.DOCX"), [".docx"]) is True

    def test_extension_with_different_case_in_list(self) -> None:
        """Extensions in the allowed list are normalised to lowercase."""
        assert is_allowed_extension(Path("file.pdf"), [".PDF"]) is True

    def test_file_with_no_extension(self) -> None:
        """A file with no extension must not match extension-only allowed lists."""
        assert is_allowed_extension(Path("README"), [".pdf"]) is False


# ---------------------------------------------------------------------------
# is_excluded
# ---------------------------------------------------------------------------


class TestIsExcluded:
    def test_matching_pattern_returns_true(self) -> None:
        """A filename matching an exclude pattern must return True."""
        assert is_excluded(Path("~$document.docx"), ["~$*"]) is True

    def test_non_matching_pattern_returns_false(self) -> None:
        """A filename not matching any pattern must return False."""
        assert is_excluded(Path("report.pdf"), ["~$*", ".*"]) is False

    def test_empty_patterns_never_excludes(self) -> None:
        """An empty patterns list must never exclude any file."""
        assert is_excluded(Path("anything.pdf"), []) is False

    def test_dotfile_matches_dotstar_pattern(self) -> None:
        """Dotfiles must match the '.*' exclusion pattern."""
        assert is_excluded(Path(".hidden"), [".*"]) is True

    def test_only_filename_component_is_matched(self) -> None:
        """Pattern matching uses only the filename, not the full path."""
        path = Path("/some/deep/.config/report.pdf")
        assert is_excluded(path, [".*"]) is False

    def test_multiple_patterns_any_match_excludes(self) -> None:
        """A filename matching any one of several patterns must be excluded."""
        assert is_excluded(Path("~$temp.docx"), ["~$*", "temp*"]) is True


# ---------------------------------------------------------------------------
# is_within_size_limit
# ---------------------------------------------------------------------------


class TestIsWithinSizeLimit:
    def test_small_file_is_within_limit(self, tmp_path: Path) -> None:
        """A file smaller than the limit must return True."""
        small_file = tmp_path / "small.pdf"
        small_file.write_bytes(b"x" * 100)
        assert is_within_size_limit(small_file, 1) is True

    def test_file_at_exact_limit_is_within(self, tmp_path: Path) -> None:
        """A file exactly at the limit must return True."""
        exact_file = tmp_path / "exact.pdf"
        exact_file.write_bytes(b"x" * (1 * 1024 * 1024))  # exactly 1 MB
        assert is_within_size_limit(exact_file, 1) is True

    def test_file_exceeding_limit_returns_false(self, tmp_path: Path) -> None:
        """A file larger than the limit must return False."""
        large_file = tmp_path / "large.pdf"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
        assert is_within_size_limit(large_file, 1) is False

    def test_empty_file_is_within_any_positive_limit(self, tmp_path: Path) -> None:
        """An empty file must be within any positive size limit."""
        empty_file = tmp_path / "empty.pdf"
        empty_file.write_bytes(b"")
        assert is_within_size_limit(empty_file, 1) is True


# ---------------------------------------------------------------------------
# collect_input_files
# ---------------------------------------------------------------------------


class TestCollectInputFiles:
    def _make_filter_config(
        self,
        allowed: list[str] | None = None,
        excluded: list[str] | None = None,
    ) -> FilterConfig:
        """Return a FilterConfig with sensible test defaults."""
        return FilterConfig(
            allowed_extensions=allowed if allowed is not None else [".pdf", ".docx"],
            exclude_patterns=excluded if excluded is not None else [],
        )

    def test_single_allowed_file_returned(self, tmp_path: Path) -> None:
        """A single file that passes all filters must be returned."""
        pdf_file = tmp_path / "report.pdf"
        pdf_file.write_bytes(b"content")
        config = self._make_filter_config()
        result = collect_input_files(pdf_file, config)
        assert result == [pdf_file]

    def test_directory_walk_finds_matching_files(self, tmp_path: Path) -> None:
        """Walking a directory must return all files with allowed extensions."""
        (tmp_path / "a.pdf").write_bytes(b"a")
        (tmp_path / "b.docx").write_bytes(b"b")
        (tmp_path / "c.zip").write_bytes(b"c")

        config = self._make_filter_config()
        result = collect_input_files(tmp_path, config)
        result_names = {p.name for p in result}
        assert "a.pdf" in result_names
        assert "b.docx" in result_names
        assert "c.zip" not in result_names

    def test_excluded_files_are_removed(self, tmp_path: Path) -> None:
        """Files matching an exclusion pattern must not appear in results."""
        (tmp_path / "report.pdf").write_bytes(b"ok")
        (tmp_path / "~$temp.pdf").write_bytes(b"lock")
        config = self._make_filter_config(excluded=["~$*"])
        result = collect_input_files(tmp_path, config)
        result_names = {p.name for p in result}
        assert "report.pdf" in result_names
        assert "~$temp.pdf" not in result_names

    def test_recursive_walk_finds_nested_files(self, tmp_path: Path) -> None:
        """Files in subdirectories must be included in the results."""
        subdir = tmp_path / "sub"
        subdir.mkdir()
        nested_file = subdir / "nested.pdf"
        nested_file.write_bytes(b"nested")
        config = self._make_filter_config()
        result = collect_input_files(tmp_path, config)
        assert nested_file in result

    @pytest.mark.error_handling
    def test_missing_path_raises_file_not_found(self, tmp_path: Path) -> None:
        """A non-existent input path must raise FileNotFoundError."""
        missing_path = tmp_path / "nonexistent"
        config = self._make_filter_config()
        with pytest.raises(FileNotFoundError, match="Input path does not exist"):
            collect_input_files(missing_path, config)

    def test_results_are_sorted(self, tmp_path: Path) -> None:
        """Results must be sorted for deterministic ordering."""
        (tmp_path / "z.pdf").write_bytes(b"z")
        (tmp_path / "a.pdf").write_bytes(b"a")
        (tmp_path / "m.pdf").write_bytes(b"m")
        config = self._make_filter_config()
        result = collect_input_files(tmp_path, config)
        assert result == sorted(result)

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        """Walking an empty directory must return an empty list."""
        config = self._make_filter_config()
        result = collect_input_files(tmp_path, config)
        assert result == []
