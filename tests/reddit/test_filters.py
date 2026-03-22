"""Tests for the filter engine in deep_thought.reddit.filters.

These tests operate entirely on in-memory mock objects — no database required.
"""

from __future__ import annotations

import time

import pytest

from deep_thought.reddit.config import RuleConfig
from deep_thought.reddit.filters import (
    apply_rule_filters,
    passes_age_filter,
    passes_comment_filter,
    passes_flair_filter,
    passes_keyword_filter,
    passes_score_filter,
)
from tests.reddit.conftest import make_mock_comment, make_mock_submission

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule_config(
    min_score: int = 0,
    min_comments: int = 0,
    max_age_days: int = 30,
    include_keywords: list[str] | None = None,
    exclude_keywords: list[str] | None = None,
    include_flair: list[str] | None = None,
    exclude_flair: list[str] | None = None,
    search_comments: bool = False,
) -> RuleConfig:
    """Build a RuleConfig with sensible defaults for filter testing."""
    return RuleConfig(
        name="test_rule",
        subreddit="python",
        sort="hot",
        time_filter="week",
        limit=10,
        min_score=min_score,
        min_comments=min_comments,
        max_age_days=max_age_days,
        include_keywords=include_keywords or [],
        exclude_keywords=exclude_keywords or [],
        include_flair=include_flair or [],
        exclude_flair=exclude_flair or [],
        search_comments=search_comments,
        max_comment_depth=3,
        max_comments=50,
        include_images=False,
    )


# ---------------------------------------------------------------------------
# passes_score_filter
# ---------------------------------------------------------------------------


class TestPassesScoreFilter:
    def test_passes_when_score_meets_minimum(self) -> None:
        """A post with score >= min_score should pass."""
        submission = make_mock_submission(score=100)
        assert passes_score_filter(submission, min_score=50) is True

    def test_passes_when_score_equals_minimum(self) -> None:
        """A post with score exactly equal to min_score should pass (inclusive)."""
        submission = make_mock_submission(score=50)
        assert passes_score_filter(submission, min_score=50) is True

    def test_fails_when_score_below_minimum(self) -> None:
        """A post with score < min_score should fail."""
        submission = make_mock_submission(score=10)
        assert passes_score_filter(submission, min_score=50) is False

    def test_zero_min_score_always_passes(self) -> None:
        """A min_score of 0 should always pass any post."""
        submission = make_mock_submission(score=0)
        assert passes_score_filter(submission, min_score=0) is True


# ---------------------------------------------------------------------------
# passes_comment_filter
# ---------------------------------------------------------------------------


class TestPassesCommentFilter:
    def test_passes_when_comment_count_meets_minimum(self) -> None:
        """A post with num_comments >= min_comments should pass."""
        submission = make_mock_submission(num_comments=20)
        assert passes_comment_filter(submission, min_comments=10) is True

    def test_passes_when_comment_count_equals_minimum(self) -> None:
        """A post with exactly min_comments should pass (inclusive)."""
        submission = make_mock_submission(num_comments=10)
        assert passes_comment_filter(submission, min_comments=10) is True

    def test_fails_when_comment_count_below_minimum(self) -> None:
        """A post with num_comments < min_comments should fail."""
        submission = make_mock_submission(num_comments=3)
        assert passes_comment_filter(submission, min_comments=10) is False

    def test_zero_min_comments_always_passes(self) -> None:
        """A min_comments of 0 should always pass any post."""
        submission = make_mock_submission(num_comments=0)
        assert passes_comment_filter(submission, min_comments=0) is True


# ---------------------------------------------------------------------------
# passes_age_filter
# ---------------------------------------------------------------------------


class TestPassesAgeFilter:
    def test_passes_when_post_is_recent(self) -> None:
        """A post created 1 hour ago should pass a 7-day age limit."""
        submission = make_mock_submission(created_utc=time.time() - 3600)
        assert passes_age_filter(submission, max_age_days=7) is True

    def test_fails_when_post_is_too_old(self) -> None:
        """A post created 30 days ago should fail a 7-day age limit."""
        thirty_days_ago = time.time() - (30 * 86400)
        submission = make_mock_submission(created_utc=thirty_days_ago)
        assert passes_age_filter(submission, max_age_days=7) is False

    def test_passes_when_post_age_equals_limit(self) -> None:
        """A post exactly at the age limit should pass (inclusive boundary)."""
        exactly_seven_days_ago = time.time() - (7 * 86400) + 1  # 1 second buffer
        submission = make_mock_submission(created_utc=exactly_seven_days_ago)
        assert passes_age_filter(submission, max_age_days=7) is True


# ---------------------------------------------------------------------------
# passes_keyword_filter
# ---------------------------------------------------------------------------


class TestPassesKeywordFilter:
    def test_empty_include_and_exclude_always_passes(self) -> None:
        """With no keyword constraints, all posts should pass."""
        submission = make_mock_submission(title="Any title here")
        assert passes_keyword_filter(submission, [], [], False) is True

    def test_include_keyword_matches_title(self) -> None:
        """A post whose title matches an include keyword should pass."""
        submission = make_mock_submission(title="Python asyncio tutorial")
        assert passes_keyword_filter(submission, ["asyncio"], [], False) is True

    def test_include_keyword_fails_when_no_match(self) -> None:
        """A post that does not match any include keyword should fail."""
        submission = make_mock_submission(title="Unrelated post about cats")
        assert passes_keyword_filter(submission, ["asyncio"], [], False) is False

    def test_include_keyword_matches_body(self) -> None:
        """An include keyword found in selftext should also cause a pass."""
        submission = make_mock_submission(title="General Python question", selftext="I use asyncio for my project")
        assert passes_keyword_filter(submission, ["asyncio"], [], False) is True

    def test_exclude_keyword_blocks_matching_post(self) -> None:
        """A post containing an exclude keyword should fail."""
        submission = make_mock_submission(title="Python hiring engineers now")
        assert passes_keyword_filter(submission, [], ["hiring"], False) is False

    def test_exclude_keyword_allows_non_matching_post(self) -> None:
        """A post not containing any exclude keyword should pass."""
        submission = make_mock_submission(title="Python 3.13 released")
        # Post does not contain "hiring", so it should pass the exclude filter
        result = passes_keyword_filter(submission, [], ["hiring"], False)
        assert result is True

    def test_glob_wildcard_matches_in_keyword(self) -> None:
        """Glob wildcard * in a keyword should match any substring."""
        submission = make_mock_submission(title="Python 3.13 performance improvements")
        assert passes_keyword_filter(submission, ["python 3*"], [], False) is True

    def test_keyword_matching_is_case_insensitive(self) -> None:
        """Keyword matching should be case-insensitive."""
        submission = make_mock_submission(title="PYTHON ASYNCIO TUTORIAL")
        assert passes_keyword_filter(submission, ["asyncio"], [], False) is True

    def test_search_comments_extends_keyword_search(self) -> None:
        """When search_comments=True, keyword match in a comment body should count."""
        submission = make_mock_submission(title="General question", selftext="")
        comment = make_mock_comment(body="I love using asyncio in my projects")
        result = passes_keyword_filter(submission, ["asyncio"], [], True, [comment])
        assert result is True

    def test_search_comments_false_ignores_comments(self) -> None:
        """When search_comments=False, comment bodies should not be searched."""
        submission = make_mock_submission(title="Unrelated title", selftext="")
        comment = make_mock_comment(body="I use asyncio every day")
        result = passes_keyword_filter(submission, ["asyncio"], [], False, [comment])
        assert result is False


# ---------------------------------------------------------------------------
# passes_flair_filter
# ---------------------------------------------------------------------------


class TestPassesFlairFilter:
    def test_empty_include_and_exclude_always_passes(self) -> None:
        """With no flair constraints, all posts pass regardless of flair."""
        submission = make_mock_submission(flair_text="Discussion")
        assert passes_flair_filter(submission, [], []) is True

    def test_include_flair_matches_when_correct(self) -> None:
        """A post with flair in the include list should pass."""
        submission = make_mock_submission(flair_text="Discussion")
        assert passes_flair_filter(submission, ["Discussion"], []) is True

    def test_include_flair_fails_when_no_match(self) -> None:
        """A post with flair not in the include list should fail."""
        submission = make_mock_submission(flair_text="Meme")
        assert passes_flair_filter(submission, ["Discussion"], []) is False

    def test_include_flair_fails_when_flair_is_none(self) -> None:
        """A post with no flair should fail a non-empty include list."""
        submission = make_mock_submission(flair_text=None)
        assert passes_flair_filter(submission, ["Discussion"], []) is False

    def test_exclude_flair_blocks_matching_post(self) -> None:
        """A post with flair in the exclude list should fail."""
        submission = make_mock_submission(flair_text="Meme")
        assert passes_flair_filter(submission, [], ["Meme"]) is False

    def test_exclude_flair_allows_non_matching_post(self) -> None:
        """A post with flair not in the exclude list should pass."""
        submission = make_mock_submission(flair_text="Discussion")
        assert passes_flair_filter(submission, [], ["Meme"]) is True

    def test_flair_matching_is_case_insensitive(self) -> None:
        """Flair matching should be case-insensitive."""
        submission = make_mock_submission(flair_text="DISCUSSION")
        assert passes_flair_filter(submission, ["discussion"], []) is True

    def test_no_flair_passes_exclude_only_constraint(self) -> None:
        """A post with no flair should pass an exclude-only constraint (nothing to exclude)."""
        submission = make_mock_submission(flair_text=None)
        assert passes_flair_filter(submission, [], ["Meme"]) is True


# ---------------------------------------------------------------------------
# apply_rule_filters (combined)
# ---------------------------------------------------------------------------


class TestApplyRuleFilters:
    def test_passes_all_filters_with_permissive_config(self) -> None:
        """A post should pass all filters when thresholds are all zero/empty."""
        submission = make_mock_submission(score=50, num_comments=10)
        rule_config = _make_rule_config()
        assert apply_rule_filters(submission, rule_config) is True

    def test_fails_score_filter(self) -> None:
        """A post below the min_score threshold should fail the combined filter."""
        submission = make_mock_submission(score=5)
        rule_config = _make_rule_config(min_score=50)
        assert apply_rule_filters(submission, rule_config) is False

    def test_fails_comment_filter(self) -> None:
        """A post below the min_comments threshold should fail the combined filter."""
        submission = make_mock_submission(score=100, num_comments=1)
        rule_config = _make_rule_config(min_comments=10)
        assert apply_rule_filters(submission, rule_config) is False

    def test_fails_age_filter(self) -> None:
        """A post older than max_age_days should fail the combined filter."""
        old_post_timestamp = time.time() - (30 * 86400)
        submission = make_mock_submission(score=100, num_comments=10, created_utc=old_post_timestamp)
        rule_config = _make_rule_config(max_age_days=7)
        assert apply_rule_filters(submission, rule_config) is False

    def test_fails_flair_filter(self) -> None:
        """A post with excluded flair should fail the combined filter."""
        submission = make_mock_submission(score=100, num_comments=10, flair_text="Meme")
        rule_config = _make_rule_config(exclude_flair=["Meme"])
        assert apply_rule_filters(submission, rule_config) is False

    def test_fails_keyword_filter(self) -> None:
        """A post without any included keyword should fail the combined filter."""
        submission = make_mock_submission(title="Unrelated post about cats", score=100, num_comments=10)
        rule_config = _make_rule_config(include_keywords=["asyncio"])
        assert apply_rule_filters(submission, rule_config) is False

    @pytest.mark.error_handling
    def test_all_filters_pass_simultaneously(self) -> None:
        """A post meeting all thresholds simultaneously should pass."""
        submission = make_mock_submission(
            title="Python asyncio tutorial",
            score=200,
            num_comments=25,
            flair_text="Tutorial",
        )
        rule_config = _make_rule_config(
            min_score=50,
            min_comments=10,
            max_age_days=7,
            include_keywords=["asyncio"],
            exclude_flair=["Meme"],
        )
        assert apply_rule_filters(submission, rule_config) is True
