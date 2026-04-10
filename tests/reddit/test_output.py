"""Tests for markdown generation in deep_thought.reddit.output.

Tests cover frontmatter correctness, comment nesting, image inclusion,
word counting, file writing, comment depth calculation, and nested comment rendering.
"""

from __future__ import annotations

from pathlib import Path  # noqa: TC003

from deep_thought.reddit.config import RuleConfig
from deep_thought.reddit.output import (
    _build_frontmatter,
    _extract_image_url,
    _get_comment_depth,
    _render_comment,
    _render_comments_section,
    count_words,
    generate_markdown,
    write_post_file,
)
from deep_thought.reddit.utils import get_author_name as _get_author_name
from tests.reddit.conftest import make_mock_comment, make_mock_submission

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule_config(
    name: str = "test_rule",
    include_images: bool = False,
) -> RuleConfig:
    """Return a minimal RuleConfig for output tests."""
    return RuleConfig(
        name=name,
        subreddit="python",
        sort="top",
        time_filter="week",
        limit=10,
        min_score=0,
        min_comments=0,
        max_age_days=7,
        include_keywords=[],
        exclude_keywords=[],
        include_flair=[],
        exclude_flair=[],
        search_comments=False,
        max_comment_depth=3,
        max_comments=50,
        include_images=include_images,
        exclude_stickied=False,
        exclude_locked=False,
        replace_more_limit=32,
    )


# ---------------------------------------------------------------------------
# count_words
# ---------------------------------------------------------------------------


class TestCountWords:
    def test_counts_whitespace_separated_tokens(self) -> None:
        """Word count should equal the number of whitespace-separated tokens."""
        assert count_words("hello world foo") == 3

    def test_empty_string_returns_zero(self) -> None:
        """An empty string should return a word count of 0."""
        assert count_words("") == 0

    def test_single_word_returns_one(self) -> None:
        """A single word with no whitespace should return 1."""
        assert count_words("python") == 1


# ---------------------------------------------------------------------------
# _get_author_name (output module version)
# ---------------------------------------------------------------------------


class TestGetAuthorName:
    def test_extracts_author_when_present(self) -> None:
        """Author name should be extracted from a PRAW author object."""
        submission = make_mock_submission(author_name="test_author")
        assert _get_author_name(submission.author) == "test_author"

    def test_returns_deleted_when_author_is_none(self) -> None:
        """None author should produce the '[deleted]' placeholder."""
        assert _get_author_name(None) == "[deleted]"


# ---------------------------------------------------------------------------
# _extract_image_url
# ---------------------------------------------------------------------------


class TestExtractImageUrl:
    def test_returns_url_for_jpg_link(self) -> None:
        """A direct .jpg URL should be identified as an image."""
        submission = make_mock_submission(url="https://example.com/photo.jpg")
        assert _extract_image_url(submission) == "https://example.com/photo.jpg"

    def test_returns_url_for_png_link(self) -> None:
        """A direct .png URL should be identified as an image."""
        submission = make_mock_submission(url="https://example.com/photo.png")
        assert _extract_image_url(submission) is not None

    def test_returns_url_for_i_redd_it_host(self) -> None:
        """An i.redd.it URL should be identified as an image."""
        submission = make_mock_submission(url="https://i.redd.it/some_image_id.jpg")
        assert _extract_image_url(submission) is not None

    def test_returns_none_for_external_non_image_url(self) -> None:
        """A URL that is not a known image format should return None."""
        submission = make_mock_submission(url="https://docs.python.org/3.13/whatsnew/")
        assert _extract_image_url(submission) is None

    def test_returns_none_for_reddit_post_url(self) -> None:
        """A standard Reddit permalink should return None (not an image)."""
        submission = make_mock_submission(url="https://www.reddit.com/r/python/comments/abc123/")
        assert _extract_image_url(submission) is None


# ---------------------------------------------------------------------------
# _build_frontmatter
# ---------------------------------------------------------------------------


class TestBuildFrontmatter:
    def test_frontmatter_contains_required_fields(self) -> None:
        """All required frontmatter fields must be present in the output."""
        submission = make_mock_submission(
            post_id="abc123",
            flair_text="Discussion",
            permalink="/r/python/comments/abc123/test_title/",
            upvote_ratio=0.95,
        )
        rule_config = _make_rule_config()
        result = _build_frontmatter(submission, rule_config, word_count=42, processed_date="2026-03-22T10:00:00Z")

        assert "tool: reddit" in result
        assert "post_id: abc123" in result
        assert "subreddit: python" in result
        assert "rule: test_rule" in result
        assert "score:" in result
        assert "num_comments:" in result
        assert "is_video: false" in result
        assert "word_count: 42" in result
        assert "processed_date: 2026-03-22T10:00:00Z" in result
        assert "flair: " in result
        assert "permalink:" in result
        assert "https://reddit.com" in result
        assert "upvote_ratio:" in result
        assert "upvote_ratio: 0.950" in result

    def test_frontmatter_starts_and_ends_with_dashes(self) -> None:
        """The frontmatter must be delimited by --- on both ends."""
        submission = make_mock_submission()
        rule_config = _make_rule_config()
        result = _build_frontmatter(submission, rule_config, word_count=10, processed_date="2026-03-22T10:00:00Z")
        assert result.startswith("---\n")
        assert "---\n" in result[4:]  # closing delimiter exists after the opener

    def test_state_key_is_composite(self) -> None:
        """The state_key in frontmatter should be post_id:subreddit:rule_name."""
        submission = make_mock_submission(post_id="xyz789", subreddit_name="learnpython")
        rule_config = _make_rule_config(name="my_rule")
        result = _build_frontmatter(submission, rule_config, word_count=5, processed_date="2026-03-22")
        assert "state_key: xyz789:learnpython:my_rule" in result

    def test_flair_null_when_no_flair(self) -> None:
        """Posts with no flair should show 'flair: null' in frontmatter."""
        submission = make_mock_submission(flair_text=None)
        rule_config = _make_rule_config()
        result = _build_frontmatter(submission, rule_config, word_count=5, processed_date="2026-03-22")
        assert "flair: null" in result


# ---------------------------------------------------------------------------
# _render_comment
# ---------------------------------------------------------------------------


class TestRenderComment:
    def test_top_level_comment_uses_heading(self) -> None:
        """Top-level comments (depth=0) should use a ### heading."""
        comment = make_mock_comment(body="This is a top-level comment.", author_name="author_one", score=25)
        result = _render_comment(comment, depth=0)
        assert "### u/author_one" in result
        assert "25" in result
        assert "This is a top-level comment." in result

    def test_nested_comment_uses_blockquote(self) -> None:
        """Nested comments (depth>0) should use blockquote prefix."""
        comment = make_mock_comment(body="This is a reply.", author_name="replier", score=5)
        result = _render_comment(comment, depth=1)
        assert ">" in result
        assert "replier" in result
        assert "This is a reply." in result

    def test_deeper_nesting_adds_more_quote_levels(self) -> None:
        """Depth 2 should produce deeper blockquote indentation than depth 1."""
        comment = make_mock_comment(body="Deep reply.")
        result_depth_1 = _render_comment(comment, depth=1)
        result_depth_2 = _render_comment(comment, depth=2)
        assert result_depth_2.count(">") > result_depth_1.count(">")


# ---------------------------------------------------------------------------
# generate_markdown
# ---------------------------------------------------------------------------


class TestGenerateMarkdown:
    def test_output_starts_with_frontmatter(self) -> None:
        """The generated markdown should begin with YAML frontmatter."""
        submission = make_mock_submission()
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        assert result.startswith("---\n")

    def test_output_contains_permalink(self) -> None:
        """The generated markdown frontmatter must include a permalink field."""
        submission = make_mock_submission(
            permalink="/r/python/comments/abc123/test_title/",
        )
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        assert "permalink:" in result
        assert "https://reddit.com" in result

    def test_output_contains_upvote_ratio(self) -> None:
        """The generated markdown frontmatter must include an upvote_ratio field."""
        submission = make_mock_submission(upvote_ratio=0.87)
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        assert "upvote_ratio:" in result
        assert "0.870" in result

    def test_output_contains_post_title_as_heading(self) -> None:
        """The post title should appear as a level-1 heading in the body."""
        submission = make_mock_submission(title="My Test Post Title")
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        assert "# My Test Post Title" in result

    def test_output_contains_score_and_comments(self) -> None:
        """The header line should include score and comment count."""
        submission = make_mock_submission(score=500, num_comments=42)
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        assert "500" in result
        assert "42" in result

    def test_selftext_is_included(self) -> None:
        """For self posts, the selftext body should appear in the output."""
        submission = make_mock_submission(selftext="This is the post body text.")
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        assert "This is the post body text." in result

    def test_image_url_included_when_configured(self) -> None:
        """When include_images=True, an image URL should appear in the output."""
        submission = make_mock_submission(url="https://i.redd.it/cool_image.jpg")
        rule_config = _make_rule_config(include_images=True)
        result = generate_markdown(submission, [], rule_config)
        assert "i.redd.it" in result

    def test_image_url_omitted_when_not_configured(self) -> None:
        """When include_images=False, image URLs should not appear in the output."""
        submission = make_mock_submission(url="https://i.redd.it/cool_image.jpg")
        rule_config = _make_rule_config(include_images=False)
        result = generate_markdown(submission, [], rule_config)
        # The URL might appear in the frontmatter, but not as a markdown image
        assert "![Image]" not in result

    def test_comments_section_appears_when_comments_provided(self) -> None:
        """When comments are provided, a ## Comments section should appear."""
        submission = make_mock_submission(post_id="abc123")
        comment = make_mock_comment(body="Interesting!", parent_id="t3_abc123")
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [comment], rule_config)
        assert "## Comments" in result
        assert "Interesting!" in result

    def test_no_comments_section_when_no_comments(self) -> None:
        """With no comments, the ## Comments heading should not appear."""
        submission = make_mock_submission()
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        assert "## Comments" not in result

    def test_removed_selftext_is_omitted(self) -> None:
        """The '[removed]' placeholder selftext should not appear in the output body."""
        submission = make_mock_submission(selftext="[removed]")
        rule_config = _make_rule_config()
        result = generate_markdown(submission, [], rule_config)
        # [removed] in selftext should be omitted (not written as body content)
        # It may appear in frontmatter but not as body text
        lines = result.split("\n")
        body_lines = [line for line in lines if not line.startswith("---") and ":" not in line[:20]]
        assert "[removed]" not in "\n".join(body_lines)


# ---------------------------------------------------------------------------
# write_post_file
# ---------------------------------------------------------------------------


class TestWritePostFile:
    def test_creates_file_under_rule_directory(self, tmp_path: Path) -> None:
        """The output file should be created under output_dir/rule_name/."""
        content = "---\ntool: reddit\n---\n\n# Test Post"
        output_path = write_post_file(
            content=content,
            output_dir=tmp_path,
            rule_name="test_rule",
            post_id="abc123",
            title="Test Post",
            date_prefix="260101",
        )
        assert output_path.exists()
        assert output_path.parent == tmp_path / "test_rule"

    def test_filename_contains_post_id_and_slug(self, tmp_path: Path) -> None:
        """The filename should contain the post ID and a title slug."""
        content = "# content"
        output_path = write_post_file(
            content=content,
            output_dir=tmp_path,
            rule_name="my_rule",
            post_id="xyz789",
            title="Python Tutorial Post",
            date_prefix="260101",
        )
        assert "xyz789" in output_path.name
        assert "python" in output_path.name

    def test_written_content_matches_input(self, tmp_path: Path) -> None:
        """The written file should contain exactly the provided content string."""
        content = "---\ntool: reddit\n---\n\n# A great post"
        output_path = write_post_file(
            content=content,
            output_dir=tmp_path,
            rule_name="test_rule",
            post_id="abc123",
            title="A great post",
            date_prefix="260101",
        )
        assert output_path.read_text(encoding="utf-8") == content

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        """Missing parent directories should be created automatically."""
        nested_output_dir = tmp_path / "deep" / "nested" / "output"
        output_path = write_post_file(
            content="# content",
            output_dir=nested_output_dir,
            rule_name="rule",
            post_id="abc",
            title="test",
            date_prefix="260101",
        )
        assert output_path.exists()


# ---------------------------------------------------------------------------
# _get_comment_depth — T-06: parent-chain traversal
# ---------------------------------------------------------------------------


class TestGetCommentDepth:
    def test_top_level_comment_returns_zero(self) -> None:
        """A comment whose parent is the submission itself must have depth 0."""
        submission = make_mock_submission(post_id="abc123")
        comment = make_mock_comment(parent_id="t3_abc123")
        depth = _get_comment_depth(comment, submission, comment_lookup=None)
        assert depth == 0

    def test_direct_reply_returns_one_without_lookup(self) -> None:
        """A reply to a top-level comment returns depth 1 when no lookup is provided."""
        submission = make_mock_submission(post_id="abc123")
        reply = make_mock_comment(comment_id="c2", parent_id="t1_c1")
        depth = _get_comment_depth(reply, submission, comment_lookup=None)
        assert depth == 1

    def test_depth_two_with_comment_lookup(self) -> None:
        """A comment two levels deep must return depth 2 when the lookup is provided."""
        submission = make_mock_submission(post_id="abc123")
        top_comment = make_mock_comment(comment_id="c1", parent_id="t3_abc123")
        reply_1 = make_mock_comment(comment_id="c2", parent_id="t1_c1")
        reply_2 = make_mock_comment(comment_id="c3", parent_id="t1_c2")

        comment_lookup = {
            "t1_c1": top_comment,
            "t1_c2": reply_1,
            "t1_c3": reply_2,
        }
        depth = _get_comment_depth(reply_2, submission, comment_lookup=comment_lookup)
        assert depth == 2

    def test_depth_three_with_comment_lookup(self) -> None:
        """Three levels deep must return depth 3."""
        submission = make_mock_submission(post_id="abc123")
        c1 = make_mock_comment(comment_id="c1", parent_id="t3_abc123")
        c2 = make_mock_comment(comment_id="c2", parent_id="t1_c1")
        c3 = make_mock_comment(comment_id="c3", parent_id="t1_c2")
        c4 = make_mock_comment(comment_id="c4", parent_id="t1_c3")

        comment_lookup = {
            "t1_c1": c1,
            "t1_c2": c2,
            "t1_c3": c3,
            "t1_c4": c4,
        }
        depth = _get_comment_depth(c4, submission, comment_lookup=comment_lookup)
        assert depth == 3

    def test_safety_cap_at_ten(self) -> None:
        """The depth cap of 10 must prevent infinite loops on malformed data."""
        submission = make_mock_submission(post_id="abc123")

        # Build a very deep chain — deeper than the safety cap of 10
        comments = {}
        previous_id = "t3_abc123"
        for i in range(15):
            cid = f"c{i}"
            comment = make_mock_comment(comment_id=cid, parent_id=previous_id)
            comments[f"t1_{cid}"] = comment
            previous_id = f"t1_{cid}"

        deepest_comment = comments["t1_c14"]
        depth = _get_comment_depth(deepest_comment, submission, comment_lookup=comments)
        assert depth <= 10

    def test_missing_parent_in_lookup_terminates_early(self) -> None:
        """If a parent is not found in the lookup, traversal stops without raising."""
        submission = make_mock_submission(post_id="abc123")
        orphan_comment = make_mock_comment(comment_id="c99", parent_id="t1_missing")
        # Empty lookup — parent t1_missing won't be found
        depth = _get_comment_depth(orphan_comment, submission, comment_lookup={})
        assert isinstance(depth, int)


# ---------------------------------------------------------------------------
# _render_comments_section — T-07: nested comment rendering
# ---------------------------------------------------------------------------


class TestRenderCommentsSection:
    def test_empty_comments_returns_empty_string(self) -> None:
        """With no comments, the section should be an empty string."""
        submission = make_mock_submission(post_id="abc123")
        result = _render_comments_section([], submission)
        assert result == ""

    def test_single_top_level_comment(self) -> None:
        """A single top-level comment should produce a ## Comments heading and the comment body."""
        submission = make_mock_submission(post_id="abc123")
        comment = make_mock_comment(body="Top level comment here.", parent_id="t3_abc123")
        result = _render_comments_section([comment], submission)
        assert "## Comments" in result
        assert "Top level comment here." in result

    def test_nested_comment_uses_blockquote_indent(self) -> None:
        """A reply to a top-level comment should appear with blockquote (>) formatting."""
        submission = make_mock_submission(post_id="abc123")
        top_comment = make_mock_comment(comment_id="c1", body="Top level.", parent_id="t3_abc123")
        reply = make_mock_comment(comment_id="c2", body="A reply.", parent_id="t1_c1")
        result = _render_comments_section([top_comment, reply], submission)
        assert ">" in result
        assert "A reply." in result

    def test_multiple_top_level_comments(self) -> None:
        """Multiple top-level comments should all appear under the ## Comments heading."""
        submission = make_mock_submission(post_id="abc123")
        comment_a = make_mock_comment(comment_id="c1", body="First comment.", parent_id="t3_abc123")
        comment_b = make_mock_comment(comment_id="c2", body="Second comment.", parent_id="t3_abc123")
        result = _render_comments_section([comment_a, comment_b], submission)
        assert "First comment." in result
        assert "Second comment." in result

    def test_deep_nesting_increases_blockquote_level(self) -> None:
        """A depth-2 reply must have more > characters than a depth-1 reply."""
        submission = make_mock_submission(post_id="abc123")
        c1 = make_mock_comment(comment_id="c1", body="Level 1.", parent_id="t3_abc123")
        c2 = make_mock_comment(comment_id="c2", body="Level 2.", parent_id="t1_c1")
        c3 = make_mock_comment(comment_id="c3", body="Level 3.", parent_id="t1_c2")

        result = _render_comments_section([c1, c2, c3], submission)

        # Count the > characters in lines containing each comment body
        lines_with_level_2 = [line for line in result.splitlines() if "Level 2." in line]
        lines_with_level_3 = [line for line in result.splitlines() if "Level 3." in line]

        # Level 3 must have more > than level 2
        assert lines_with_level_3
        assert lines_with_level_2
        assert lines_with_level_3[0].count(">") > lines_with_level_2[0].count(">")

    def test_comments_section_includes_comment_heading(self) -> None:
        """The section must start with a ## Comments heading."""
        submission = make_mock_submission(post_id="abc123")
        comment = make_mock_comment(parent_id="t3_abc123")
        result = _render_comments_section([comment], submission)
        assert result.startswith("## Comments")
