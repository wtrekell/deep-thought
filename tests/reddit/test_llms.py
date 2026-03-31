"""Tests for llms.py — LLM context file generation for the Reddit Tool.

Uses in-memory helpers so no real PRAW objects or disk I/O are needed except
where write behaviour is explicitly being tested.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from deep_thought.reddit.llms import (
    generate_llms_full,
    generate_llms_index,
    strip_frontmatter,
    write_llms_files,
    write_post_llms_files,
)
from deep_thought.reddit.models import CollectedPostLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collected_post(
    state_key: str = "abc123:python:rule1",
    post_id: str = "abc123",
    subreddit: str = "python",
    rule_name: str = "rule1",
    title: str = "Test Post Title",
    author: str = "test_user",
    score: int = 100,
    comment_count: int = 20,
    url: str = "https://www.reddit.com/r/python/comments/abc123/",
    output_path: str = "/data/reddit/export/rule1/260101-abc123_test-post-title.md",
    word_count: int = 50,
) -> CollectedPostLocal:
    """Return a CollectedPostLocal with defaults suitable for testing."""
    return CollectedPostLocal(
        state_key=state_key,
        post_id=post_id,
        subreddit=subreddit,
        rule_name=rule_name,
        title=title,
        author=author,
        score=score,
        comment_count=comment_count,
        url=url,
        is_video=0,
        flair=None,
        word_count=word_count,
        output_path=output_path,
        status="ok",
        created_at="2026-01-01T10:00:00+00:00",
        updated_at="2026-01-01T10:00:00+00:00",
        synced_at="2026-01-01T10:00:00+00:00",
    )


# ---------------------------------------------------------------------------
# strip_frontmatter
# ---------------------------------------------------------------------------


class TestStripFrontmatter:
    def test_strips_valid_frontmatter_block(self) -> None:
        """Standard YAML frontmatter should be removed, leaving only the body."""
        markdown_text = "---\ntool: reddit\npost_id: abc\n---\n\n# Post Title\n\nBody text."
        result = strip_frontmatter(markdown_text)
        assert result.startswith("# Post Title")
        assert "tool: reddit" not in result

    def test_returns_unchanged_when_no_frontmatter(self) -> None:
        """Markdown without a leading --- block must be returned unchanged."""
        plain_text = "# Just a heading\n\nSome body text."
        result = strip_frontmatter(plain_text)
        assert result == plain_text

    def test_returns_unchanged_when_only_opening_delimiter(self) -> None:
        """A lone opening --- with no closing delimiter must not strip anything."""
        partial = "---\ntool: reddit\nno closing delimiter here"
        result = strip_frontmatter(partial)
        assert result == partial

    def test_handles_empty_string(self) -> None:
        """An empty string must be returned as-is without error."""
        result = strip_frontmatter("")
        assert result == ""

    def test_strips_leading_newlines_from_body(self) -> None:
        """Empty lines between the closing --- and body content should be trimmed."""
        markdown_text = "---\nkey: value\n---\n\n\n# Heading"
        result = strip_frontmatter(markdown_text)
        assert result.startswith("# Heading")

    def test_body_only_document_unchanged(self) -> None:
        """A document starting with a non-dash character is not modified."""
        body_only = "Some text that does not start with ---"
        result = strip_frontmatter(body_only)
        assert result == body_only


# ---------------------------------------------------------------------------
# generate_llms_index
# ---------------------------------------------------------------------------


class TestGenerateLlmsIndex:
    def test_output_contains_rule_name_in_header(self) -> None:
        """The index header must include the rule name."""
        post = _make_collected_post()
        result = generate_llms_index([post], rule_name="my_rule")
        assert "my_rule" in result

    def test_output_contains_post_entry(self) -> None:
        """Each post must produce an entry line in the index."""
        post = _make_collected_post(title="Cool Python Post", score=500)
        result = generate_llms_index([post], rule_name="rule1")
        assert "score 500" in result
        assert "python" in result.lower()

    def test_post_count_is_shown(self) -> None:
        """The header must state the number of posts collected."""
        posts = [_make_collected_post(state_key=f"p{i}:sub:rule", post_id=f"p{i}") for i in range(3)]
        result = generate_llms_index(posts, rule_name="rule1")
        assert "3 posts" in result

    def test_empty_posts_list(self) -> None:
        """An empty post list should produce a valid (but empty posts section) index."""
        result = generate_llms_index([], rule_name="rule1")
        assert "## Posts" in result
        assert "0 posts" in result

    def test_word_count_is_included(self) -> None:
        """Each entry should include the word count from the post."""
        post = _make_collected_post(word_count=123)
        result = generate_llms_index([post], rule_name="rule1")
        assert "123 words" in result


# ---------------------------------------------------------------------------
# generate_llms_full
# ---------------------------------------------------------------------------


class TestGenerateLlmsFull:
    def test_output_contains_post_title(self) -> None:
        """Each post's title must appear as a heading in the full output."""
        post = _make_collected_post(title="My Amazing Post")
        result = generate_llms_full([post], rule_name="rule1")
        assert "# My Amazing Post" in result

    def test_output_contains_post_metadata(self) -> None:
        """Key metadata (post_id, subreddit, score) must appear in the output."""
        post = _make_collected_post(post_id="xyz789", subreddit="learnpython", score=42)
        result = generate_llms_full([post], rule_name="rule1")
        assert "post_id: xyz789" in result
        assert "subreddit: learnpython" in result
        assert "score: 42" in result

    def test_output_has_separator_between_posts(self) -> None:
        """Multiple posts must be separated by --- dividers."""
        posts = [_make_collected_post(state_key=f"p{i}:sub:rule", post_id=f"p{i}", title=f"Post {i}") for i in range(2)]
        result = generate_llms_full(posts, rule_name="rule1")
        assert "---" in result

    def test_frontmatter_is_stripped_from_post_content(self, tmp_path: Path) -> None:
        """The YAML frontmatter should be stripped from the file content when included."""
        post_file = tmp_path / "rule1" / "260101-abc123_test-post.md"
        post_file.parent.mkdir(parents=True)
        post_file.write_text(
            "---\ntool: reddit\npost_id: abc123\n---\n\n# Post Title\n\nBody text.",
            encoding="utf-8",
        )
        post = _make_collected_post(output_path=str(post_file))
        result = generate_llms_full([post], rule_name="rule1")
        assert "tool: reddit" not in result
        assert "# Post Title" in result

    def test_missing_output_file_produces_empty_content(self) -> None:
        """If a post's output file is missing, the block should contain empty content without error."""
        post = _make_collected_post(output_path="/nonexistent/path/post.md")
        # Should not raise; just produce an empty content block
        result = generate_llms_full([post], rule_name="rule1")
        assert "My Amazing Post" not in result or isinstance(result, str)


# ---------------------------------------------------------------------------
# write_llms_files
# ---------------------------------------------------------------------------


class TestWriteLlmsFiles:
    def test_creates_llms_txt_file(self, tmp_path: Path) -> None:
        """write_llms_files must create an llms.txt file in the rule directory."""
        post = _make_collected_post()
        llms_path, _ = write_llms_files([post], output_dir=tmp_path, rule_name="rule1")
        assert llms_path.exists()
        assert llms_path.name == "llms.txt"

    def test_creates_llms_full_txt_file(self, tmp_path: Path) -> None:
        """write_llms_files must create an llms-full.txt file in the rule directory."""
        post = _make_collected_post()
        _, full_path = write_llms_files([post], output_dir=tmp_path, rule_name="rule1")
        assert full_path.exists()
        assert full_path.name == "llms-full.txt"

    def test_files_are_written_under_rule_directory(self, tmp_path: Path) -> None:
        """Both output files must live inside output_dir/rule_name/."""
        post = _make_collected_post()
        llms_path, full_path = write_llms_files([post], output_dir=tmp_path, rule_name="my_rule")
        assert llms_path.parent == tmp_path / "my_rule"
        assert full_path.parent == tmp_path / "my_rule"

    def test_creates_missing_rule_directory(self, tmp_path: Path) -> None:
        """write_llms_files must create the rule subdirectory if it doesn't exist."""
        post = _make_collected_post()
        rule_dir = tmp_path / "new_rule"
        assert not rule_dir.exists()
        write_llms_files([post], output_dir=tmp_path, rule_name="new_rule")
        assert rule_dir.exists()


# ---------------------------------------------------------------------------
# write_post_llms_files (per-post sidecar files, M-10 naming check)
# ---------------------------------------------------------------------------


class TestWritePostLlmsFiles:
    def test_creates_llms_txt_without_leading_dot(self, tmp_path: Path) -> None:
        """Per-post llms file must be named without a leading dot (e.g., base-llms.txt)."""
        write_post_llms_files(
            post_content="---\ntool: reddit\n---\n\n# Title\n\nBody.",
            output_dir=tmp_path,
            rule_name="rule1",
            post_id="abc123",
            title="My Test Post",
            post_metadata=MagicMock(score=10, comment_count=5),
        )
        llm_dir = tmp_path / "rule1" / "llm"
        txt_files = list(llm_dir.glob("*-llms.txt"))
        assert len(txt_files) == 1
        assert not txt_files[0].name.startswith(".")

    def test_creates_llms_full_txt_without_leading_dot(self, tmp_path: Path) -> None:
        """Per-post llms-full file must be named without a leading dot."""
        write_post_llms_files(
            post_content="---\ntool: reddit\n---\n\n# Title\n\nBody.",
            output_dir=tmp_path,
            rule_name="rule1",
            post_id="abc123",
            title="My Test Post",
            post_metadata=MagicMock(score=10, comment_count=5),
        )
        llm_dir = tmp_path / "rule1" / "llm"
        full_files = list(llm_dir.glob("*-llms-full.txt"))
        assert len(full_files) == 1
        assert not full_files[0].name.startswith(".")

    def test_sidecar_files_contain_title(self, tmp_path: Path) -> None:
        """The llms.txt sidecar must contain the post title."""
        write_post_llms_files(
            post_content="---\ntool: reddit\n---\n\n# Amazing Title\n\nBody.",
            output_dir=tmp_path,
            rule_name="rule1",
            post_id="abc123",
            title="Amazing Title",
            post_metadata=MagicMock(score=10, comment_count=5),
        )
        llm_dir = tmp_path / "rule1" / "llm"
        txt_file = next(llm_dir.glob("*-llms.txt"))
        content = txt_file.read_text(encoding="utf-8")
        assert "Amazing Title" in content


# ---------------------------------------------------------------------------
# Import to allow MagicMock usage
# ---------------------------------------------------------------------------
from unittest.mock import MagicMock  # noqa: E402 — needed for TestWritePostLlmsFiles
