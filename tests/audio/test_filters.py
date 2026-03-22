"""Tests for the file filtering functions in deep_thought.audio.filters."""

from __future__ import annotations

from pathlib import Path

import pytest

from deep_thought.audio.filters import (
    _SUPPORTED_EXTENSIONS,
    check_file,
    collect_input_files,
    compute_file_hash,
    is_empty_file,
    is_supported_extension,
    is_within_size_limit,
)

# ---------------------------------------------------------------------------
# is_supported_extension
# ---------------------------------------------------------------------------


class TestIsSupportedExtension:
    def test_mp3_returns_true(self) -> None:
        """The .mp3 extension must be recognised as supported."""
        assert is_supported_extension(Path("interview.mp3")) is True

    def test_wav_returns_true(self) -> None:
        """The .wav extension must be recognised as supported."""
        assert is_supported_extension(Path("recording.wav")) is True

    def test_m4a_returns_true(self) -> None:
        """The .m4a extension must be recognised as supported."""
        assert is_supported_extension(Path("podcast.m4a")) is True

    def test_all_supported_extensions_return_true(self) -> None:
        """Every extension in _SUPPORTED_EXTENSIONS must return True."""
        for extension in _SUPPORTED_EXTENSIONS:
            assert is_supported_extension(Path(f"file{extension}")) is True, f"Expected True for {extension}"

    def test_unsupported_extension_returns_false(self) -> None:
        """A file with an unsupported extension must return False."""
        assert is_supported_extension(Path("document.pdf")) is False

    def test_txt_extension_returns_false(self) -> None:
        """A .txt file must return False."""
        assert is_supported_extension(Path("transcript.txt")) is False

    def test_no_extension_returns_false(self) -> None:
        """A file with no extension must return False."""
        assert is_supported_extension(Path("README")) is False

    def test_matching_is_case_insensitive(self) -> None:
        """Extension matching must be case-insensitive."""
        assert is_supported_extension(Path("AUDIO.MP3")) is True
        assert is_supported_extension(Path("recording.WAV")) is True


# ---------------------------------------------------------------------------
# is_within_size_limit
# ---------------------------------------------------------------------------


class TestIsWithinSizeLimit:
    def test_small_file_is_within_limit(self, tmp_path: Path) -> None:
        """A file much smaller than the limit must return True."""
        small_file = tmp_path / "small.wav"
        small_file.write_bytes(b"x" * 100)
        assert is_within_size_limit(small_file, 1) is True

    def test_file_at_exact_limit_is_within(self, tmp_path: Path) -> None:
        """A file exactly at the limit must return True."""
        exact_file = tmp_path / "exact.wav"
        exact_file.write_bytes(b"x" * (1 * 1024 * 1024))  # exactly 1 MB
        assert is_within_size_limit(exact_file, 1) is True

    def test_file_exceeding_limit_returns_false(self, tmp_path: Path) -> None:
        """A file larger than the limit must return False."""
        large_file = tmp_path / "large.wav"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
        assert is_within_size_limit(large_file, 1) is False

    def test_empty_file_is_within_any_positive_limit(self, tmp_path: Path) -> None:
        """An empty file must be within any positive size limit."""
        empty_file = tmp_path / "empty.wav"
        empty_file.write_bytes(b"")
        assert is_within_size_limit(empty_file, 1) is True


# ---------------------------------------------------------------------------
# is_empty_file
# ---------------------------------------------------------------------------


class TestIsEmptyFile:
    def test_empty_file_returns_true(self, tmp_path: Path) -> None:
        """A file with zero bytes must return True."""
        empty_file = tmp_path / "empty.wav"
        empty_file.write_bytes(b"")
        assert is_empty_file(empty_file) is True

    def test_non_empty_file_returns_false(self, tmp_path: Path) -> None:
        """A file with content must return False."""
        content_file = tmp_path / "audio.wav"
        content_file.write_bytes(b"some audio data here")
        assert is_empty_file(content_file) is False

    def test_single_byte_file_returns_false(self, tmp_path: Path) -> None:
        """A file with exactly one byte must return False."""
        single_byte_file = tmp_path / "tiny.wav"
        single_byte_file.write_bytes(b"\x00")
        assert is_empty_file(single_byte_file) is False


# ---------------------------------------------------------------------------
# compute_file_hash
# ---------------------------------------------------------------------------


class TestComputeFileHash:
    def test_returns_string(self, tmp_path: Path) -> None:
        """compute_file_hash() must return a string."""
        test_file = tmp_path / "audio.wav"
        test_file.write_bytes(b"audio data")
        result = compute_file_hash(test_file)
        assert isinstance(result, str)

    def test_returns_64_character_hex_string(self, tmp_path: Path) -> None:
        """SHA-256 digest must produce a 64-character hex string."""
        test_file = tmp_path / "audio.wav"
        test_file.write_bytes(b"audio data")
        result = compute_file_hash(test_file)
        assert len(result) == 64
        assert all(character in "0123456789abcdef" for character in result)

    def test_same_content_produces_same_hash(self, tmp_path: Path) -> None:
        """Two files with identical content must produce the same hash."""
        file_a = tmp_path / "a.wav"
        file_b = tmp_path / "b.wav"
        file_a.write_bytes(b"identical content")
        file_b.write_bytes(b"identical content")
        assert compute_file_hash(file_a) == compute_file_hash(file_b)

    def test_different_content_produces_different_hash(self, tmp_path: Path) -> None:
        """Two files with different content must produce different hashes."""
        file_a = tmp_path / "a.wav"
        file_b = tmp_path / "b.wav"
        file_a.write_bytes(b"content A")
        file_b.write_bytes(b"content B")
        assert compute_file_hash(file_a) != compute_file_hash(file_b)

    def test_hash_is_deterministic(self, tmp_path: Path) -> None:
        """Calling compute_file_hash() twice on the same file must return the same value."""
        test_file = tmp_path / "audio.wav"
        test_file.write_bytes(b"consistent data")
        first_hash = compute_file_hash(test_file)
        second_hash = compute_file_hash(test_file)
        assert first_hash == second_hash


# ---------------------------------------------------------------------------
# check_file
# ---------------------------------------------------------------------------


class TestCheckFile:
    def test_valid_file_passes(self, sample_wav: Path) -> None:
        """A valid WAV file within limits must pass all checks."""
        file_hash = compute_file_hash(sample_wav)
        passed, reason = check_file(sample_wav, file_hash, max_size_mb=10)
        assert passed is True
        assert reason == ""

    def test_unsupported_extension_fails(self, tmp_path: Path) -> None:
        """A file with an unsupported extension must fail with a descriptive reason."""
        pdf_file = tmp_path / "document.pdf"
        pdf_file.write_bytes(b"not audio")
        file_hash = compute_file_hash(pdf_file)
        passed, reason = check_file(pdf_file, file_hash, max_size_mb=10)
        assert passed is False
        assert "Unsupported extension" in reason

    def test_empty_file_fails(self, tmp_path: Path) -> None:
        """An empty WAV file must fail with a descriptive reason."""
        empty_file = tmp_path / "empty.wav"
        empty_file.write_bytes(b"")
        file_hash = compute_file_hash(empty_file)
        passed, reason = check_file(empty_file, file_hash, max_size_mb=10)
        assert passed is False
        assert "empty" in reason.lower()

    def test_oversize_file_fails(self, tmp_path: Path) -> None:
        """A file exceeding the size limit must fail with a descriptive reason."""
        large_file = tmp_path / "large.wav"
        large_file.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
        file_hash = compute_file_hash(large_file)
        passed, reason = check_file(large_file, file_hash, max_size_mb=1)
        assert passed is False
        assert "exceeds limit" in reason

    def test_passes_without_db_connection(self, sample_wav: Path) -> None:
        """check_file() must work correctly when no DB connection is provided."""
        file_hash = compute_file_hash(sample_wav)
        passed, reason = check_file(sample_wav, file_hash, max_size_mb=10, conn=None)
        assert passed is True


# ---------------------------------------------------------------------------
# collect_input_files
# ---------------------------------------------------------------------------


class TestCollectInputFiles:
    def test_single_supported_file_returned(self, sample_wav: Path) -> None:
        """A single WAV file passed directly must be returned as a single-item list."""
        result = collect_input_files(sample_wav)
        assert result == [sample_wav]

    def test_directory_walk_finds_supported_audio_files(self, tmp_path: Path) -> None:
        """Walking a directory must return only files with supported extensions."""
        (tmp_path / "interview.mp3").write_bytes(b"mp3 data")
        (tmp_path / "recording.wav").write_bytes(b"wav data")
        (tmp_path / "notes.txt").write_bytes(b"text")
        (tmp_path / "document.pdf").write_bytes(b"pdf")

        result = collect_input_files(tmp_path)
        result_names = {path.name for path in result}

        assert "interview.mp3" in result_names
        assert "recording.wav" in result_names
        assert "notes.txt" not in result_names
        assert "document.pdf" not in result_names

    def test_all_supported_extension_types_collected(self, tmp_path: Path) -> None:
        """Files with every supported extension must be found in a directory walk."""
        for extension in _SUPPORTED_EXTENSIONS:
            (tmp_path / f"file{extension}").write_bytes(b"data")

        result = collect_input_files(tmp_path)
        assert len(result) == len(_SUPPORTED_EXTENSIONS)

    def test_recursive_walk_finds_nested_files(self, tmp_path: Path) -> None:
        """Files in subdirectories must be included in the results."""
        subdir = tmp_path / "recordings" / "2026"
        subdir.mkdir(parents=True)
        nested_file = subdir / "meeting.m4a"
        nested_file.write_bytes(b"audio data")

        result = collect_input_files(tmp_path)
        assert nested_file in result

    def test_results_are_sorted(self, tmp_path: Path) -> None:
        """collect_input_files() must return a sorted list for deterministic ordering."""
        (tmp_path / "z.wav").write_bytes(b"z")
        (tmp_path / "a.wav").write_bytes(b"a")
        (tmp_path / "m.mp3").write_bytes(b"m")

        result = collect_input_files(tmp_path)
        assert result == sorted(result)

    def test_empty_directory_returns_empty_list(self, tmp_path: Path) -> None:
        """Walking an empty directory must return an empty list."""
        result = collect_input_files(tmp_path)
        assert result == []

    @pytest.mark.error_handling
    def test_missing_path_raises_file_not_found(self, tmp_path: Path) -> None:
        """A non-existent input path must raise FileNotFoundError."""
        missing_path = tmp_path / "nonexistent"
        with pytest.raises(FileNotFoundError, match="Input path does not exist"):
            collect_input_files(missing_path)
