"""Tests for local dataclasses in deep_thought.reddit.models.

Tests cover CollectedPostLocal.from_submission() with various post types
and the to_dict() roundtrip.
"""

from __future__ import annotations

from unittest.mock import MagicMock  # noqa: TC003

from deep_thought.reddit.models import CollectedPostLocal
from deep_thought.reddit.utils import get_author_name as _get_author_name
from deep_thought.reddit.utils import slugify_title as _slugify_title
from tests.reddit.conftest import make_mock_submission

# ---------------------------------------------------------------------------
# Helper: build mock submission variants
# ---------------------------------------------------------------------------


def _make_self_post() -> MagicMock:
    """Return a mock self (text) post."""
    return make_mock_submission(
        post_id="abc123",
        title="How to use asyncio",
        selftext="Here is my question about asyncio...",
        subreddit_name="python",
        author_name="dev_user",
        score=200,
        num_comments=15,
        url="https://www.reddit.com/r/python/comments/abc123/",
        is_self=True,
        upvote_ratio=0.95,
    )


def _make_link_post() -> MagicMock:
    """Return a mock link (external URL) post."""
    return make_mock_submission(
        post_id="def456",
        title="Python 3.13 Release Notes",
        selftext="",
        subreddit_name="Python",
        author_name="link_poster",
        score=500,
        num_comments=42,
        url="https://docs.python.org/3.13/whatsnew/3.13.html",
        is_self=False,
    )


def _make_video_post() -> MagicMock:
    """Return a mock video post."""
    return make_mock_submission(
        post_id="ghi789",
        title="Python Tutorial Video",
        selftext="",
        subreddit_name="learnpython",
        author_name="video_creator",
        score=75,
        num_comments=5,
        url="https://v.redd.it/some_video_id",
        is_video=True,
        is_self=False,
    )


# ---------------------------------------------------------------------------
# _get_author_name
# ---------------------------------------------------------------------------


class TestGetAuthorName:
    def test_returns_author_string_when_present(self) -> None:
        """Author name should be extracted as a string from the author attribute."""
        submission = make_mock_submission(author_name="test_user")
        assert _get_author_name(submission.author) == "test_user"

    def test_returns_deleted_when_author_is_none(self) -> None:
        """A None author attribute should return the '[deleted]' placeholder."""
        assert _get_author_name(None) == "[deleted]"


# ---------------------------------------------------------------------------
# _slugify_title
# ---------------------------------------------------------------------------


class TestSlugifyTitle:
    def test_lowercases_and_replaces_special_chars(self) -> None:
        """Title should be lowercased and non-alphanumeric characters replaced with hyphens."""
        result = _slugify_title("Python 3.13: New Features!")
        assert result == "python-3-13-new-features"

    def test_strips_leading_and_trailing_hyphens(self) -> None:
        """Leading and trailing hyphens should be removed."""
        result = _slugify_title("  Hello World  ")
        # spaces become hyphens, then stripped
        assert not result.startswith("-")
        assert not result.endswith("-")

    def test_truncates_at_max_length(self) -> None:
        """Slugs longer than 80 characters should be truncated to 80."""
        long_title = "a" * 200
        result = _slugify_title(long_title)
        assert len(result) <= 80

    def test_collapses_multiple_separators(self) -> None:
        """Multiple consecutive special characters should produce a single hyphen."""
        result = _slugify_title("Hello --- World!!!")
        assert "--" not in result


# ---------------------------------------------------------------------------
# CollectedPostLocal.from_submission
# ---------------------------------------------------------------------------


class TestCollectedPostLocalFromSubmission:
    def test_self_post_all_fields_populated(self) -> None:
        """from_submission on a self post should correctly populate all fields."""
        submission = _make_self_post()
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/data/reddit/export/test_rule/260322-abc123_test.md",
            word_count=42,
        )

        assert post.post_id == "abc123"
        assert post.subreddit == "python"
        assert post.rule_name == "test_rule"
        assert post.title == "How to use asyncio"
        assert post.author == "dev_user"
        assert post.score == 200
        assert post.upvote_ratio == 0.95
        assert post.comment_count == 15
        assert post.url == "https://www.reddit.com/r/python/comments/abc123/"
        assert post.is_video == 0
        assert post.word_count == 42
        assert post.status == "ok"

    def test_state_key_is_composite(self) -> None:
        """state_key should be composed of post_id:subreddit:rule_name."""
        submission = _make_self_post()
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="my_rule",
            output_path="/some/path.md",
            word_count=10,
        )
        assert post.state_key == "abc123:python:my_rule"

    def test_link_post_is_video_false(self) -> None:
        """A non-video post should have is_video set to 0."""
        submission = _make_link_post()
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/some/path.md",
            word_count=5,
        )
        assert post.is_video == 0

    def test_video_post_is_video_true(self) -> None:
        """A video post should have is_video set to 1."""
        submission = _make_video_post()
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/some/path.md",
            word_count=3,
        )
        assert post.is_video == 1

    def test_flair_is_none_when_not_set(self) -> None:
        """Posts without flair should have flair=None."""
        submission = make_mock_submission(flair_text=None)
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/some/path.md",
            word_count=10,
        )
        assert post.flair is None

    def test_flair_is_set_when_present(self) -> None:
        """Posts with flair should have that flair text captured."""
        submission = make_mock_submission(flair_text="Discussion")
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/some/path.md",
            word_count=10,
        )
        assert post.flair == "Discussion"

    def test_timestamps_are_iso_strings(self) -> None:
        """All three timestamp fields should be non-empty ISO 8601 strings."""
        submission = _make_self_post()
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/some/path.md",
            word_count=10,
        )
        assert "T" in post.created_at  # basic ISO 8601 check
        assert "T" in post.updated_at
        assert "T" in post.synced_at

    def test_deleted_author_produces_placeholder(self) -> None:
        """A submission with author=None should show '[deleted]' in the author field."""
        submission = _make_self_post()
        submission.author = None
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/some/path.md",
            word_count=10,
        )
        assert post.author == "[deleted]"


# ---------------------------------------------------------------------------
# CollectedPostLocal.to_dict
# ---------------------------------------------------------------------------


class TestCollectedPostLocalToDict:
    def test_to_dict_roundtrip_contains_all_keys(self) -> None:
        """to_dict should return a flat dict with all expected database column keys."""
        submission = _make_self_post()
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/data/reddit/export/test_rule/post.md",
            word_count=55,
        )
        result = post.to_dict()

        expected_keys = {
            "state_key",
            "post_id",
            "subreddit",
            "rule_name",
            "title",
            "author",
            "score",
            "upvote_ratio",
            "comment_count",
            "url",
            "is_video",
            "flair",
            "word_count",
            "output_path",
            "status",
            "created_at",
            "updated_at",
            "synced_at",
        }
        assert expected_keys == set(result.keys())

    def test_to_dict_values_match_dataclass_fields(self) -> None:
        """Values in the dict should match the dataclass attributes exactly."""
        submission = _make_self_post()
        post = CollectedPostLocal.from_submission(
            submission=submission,
            rule_name="test_rule",
            output_path="/data/path.md",
            word_count=99,
        )
        result = post.to_dict()

        assert result["post_id"] == post.post_id
        assert result["state_key"] == post.state_key
        assert result["word_count"] == 99
        assert result["status"] == "ok"

    def test_same_post_two_rules_have_different_state_keys(self) -> None:
        """The same post collected under different rules produces distinct state keys."""
        submission = _make_self_post()
        post_rule_a = CollectedPostLocal.from_submission(
            submission=submission, rule_name="rule_a", output_path="/a.md", word_count=10
        )
        post_rule_b = CollectedPostLocal.from_submission(
            submission=submission, rule_name="rule_b", output_path="/b.md", word_count=10
        )
        assert post_rule_a.state_key != post_rule_b.state_key
        assert post_rule_a.post_id == post_rule_b.post_id
