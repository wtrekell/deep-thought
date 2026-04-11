"""Tests for pure filter functions in deep_thought.stackexchange.filters.

All functions operate on plain dicts and have no side effects, so no
database or network fixtures are required.
"""

from __future__ import annotations

import time

from deep_thought.stackexchange.config import RuleConfig, TagConfig
from deep_thought.stackexchange.filters import (
    apply_rule_filters,
    passes_age_filter,
    passes_answer_count_filter,
    passes_answered_filter,
    passes_keyword_filter,
    passes_score_filter,
    passes_tag_any_filter,
)
from tests.stackexchange.conftest import make_mock_question

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_permissive_rule_config(name: str = "test_rule") -> RuleConfig:
    """Return a RuleConfig with all filters set to pass everything."""
    return RuleConfig(
        name=name,
        site="stackoverflow",
        tags=TagConfig(include=[], any=[]),
        sort="votes",
        order="desc",
        min_score=0,
        min_answers=0,
        only_answered=False,
        max_age_days=0,  # 0 disables age filter
        keywords=[],
        max_questions=50,
        max_answers_per_question=5,
        include_comments=False,
        max_comments_per_question=30,
    )


# ---------------------------------------------------------------------------
# TestPassesAnsweredFilter
# ---------------------------------------------------------------------------


class TestPassesAnsweredFilter:
    def test_passes_when_answered_and_only_answered_true(self) -> None:
        """A question with is_answered=True should pass when only_answered=True."""
        question = make_mock_question(is_answered=True)
        assert passes_answered_filter(question, only_answered=True) is True

    def test_fails_when_not_answered_and_only_answered_true(self) -> None:
        """A question with is_answered=False should fail when only_answered=True."""
        question = make_mock_question(is_answered=False)
        assert passes_answered_filter(question, only_answered=True) is False

    def test_passes_when_not_answered_and_only_answered_false(self) -> None:
        """All questions should pass when only_answered=False, regardless of is_answered."""
        question = make_mock_question(is_answered=False)
        assert passes_answered_filter(question, only_answered=False) is True

    def test_passes_when_answered_and_only_answered_false(self) -> None:
        """An answered question should pass when only_answered=False."""
        question = make_mock_question(is_answered=True)
        assert passes_answered_filter(question, only_answered=False) is True


# ---------------------------------------------------------------------------
# TestPassesScoreFilter
# ---------------------------------------------------------------------------


class TestPassesScoreFilter:
    def test_passes_at_exact_threshold(self) -> None:
        """A question exactly at min_score should pass."""
        question = make_mock_question(score=10)
        assert passes_score_filter(question, min_score=10) is True

    def test_passes_above_threshold(self) -> None:
        """A question above min_score should pass."""
        question = make_mock_question(score=100)
        assert passes_score_filter(question, min_score=10) is True

    def test_fails_below_threshold(self) -> None:
        """A question below min_score should fail."""
        question = make_mock_question(score=5)
        assert passes_score_filter(question, min_score=10) is False

    def test_passes_with_zero_min_score(self) -> None:
        """Any question should pass with min_score=0."""
        question = make_mock_question(score=0)
        assert passes_score_filter(question, min_score=0) is True


# ---------------------------------------------------------------------------
# TestPassesAnswerCountFilter
# ---------------------------------------------------------------------------


class TestPassesAnswerCountFilter:
    def test_passes_at_exact_threshold(self) -> None:
        """A question with exactly min_answers should pass."""
        question = make_mock_question(answer_count=1)
        assert passes_answer_count_filter(question, min_answers=1) is True

    def test_passes_above_threshold(self) -> None:
        """A question with more than min_answers should pass."""
        question = make_mock_question(answer_count=10)
        assert passes_answer_count_filter(question, min_answers=1) is True

    def test_fails_below_threshold(self) -> None:
        """A question with fewer than min_answers should fail."""
        question = make_mock_question(answer_count=0)
        assert passes_answer_count_filter(question, min_answers=1) is False

    def test_passes_with_zero_min_answers(self) -> None:
        """Any question should pass with min_answers=0."""
        question = make_mock_question(answer_count=0)
        assert passes_answer_count_filter(question, min_answers=0) is True


# ---------------------------------------------------------------------------
# TestPassesTagAnyFilter
# ---------------------------------------------------------------------------


class TestPassesTagAnyFilter:
    def test_passes_with_matching_tag(self) -> None:
        """A question with at least one matching tag should pass."""
        question = make_mock_question(tags=["python", "performance"])
        assert passes_tag_any_filter(question, any_tags=["python"]) is True

    def test_passes_with_one_of_multiple_any_tags(self) -> None:
        """A question matching any of several any_tags should pass."""
        question = make_mock_question(tags=["pandas"])
        assert passes_tag_any_filter(question, any_tags=["numpy", "pandas", "scipy"]) is True

    def test_passes_with_empty_any_tags(self) -> None:
        """An empty any_tags list means no constraint — any question should pass."""
        question = make_mock_question(tags=["python"])
        assert passes_tag_any_filter(question, any_tags=[]) is True

    def test_fails_with_no_match(self) -> None:
        """A question with no matching tags should fail when any_tags is non-empty."""
        question = make_mock_question(tags=["javascript", "react"])
        assert passes_tag_any_filter(question, any_tags=["python", "pandas"]) is False


# ---------------------------------------------------------------------------
# TestPassesAgeFilter
# ---------------------------------------------------------------------------


class TestPassesAgeFilter:
    def test_passes_within_window(self) -> None:
        """A question created within max_age_days should pass."""
        recent_creation_date = time.time() - (7 * 86400)  # 7 days ago
        question = make_mock_question(creation_date=recent_creation_date)
        assert passes_age_filter(question, max_age_days=365) is True

    def test_fails_outside_window(self) -> None:
        """A question created beyond max_age_days should fail."""
        old_creation_date = time.time() - (400 * 86400)  # 400 days ago
        question = make_mock_question(creation_date=old_creation_date)
        assert passes_age_filter(question, max_age_days=365) is False

    def test_passes_when_max_age_days_is_zero(self) -> None:
        """A max_age_days of 0 should disable the age filter (all questions pass)."""
        very_old_creation_date = time.time() - (10000 * 86400)
        question = make_mock_question(creation_date=very_old_creation_date)
        assert passes_age_filter(question, max_age_days=0) is True

    def test_passes_when_max_age_days_is_negative(self) -> None:
        """A negative max_age_days should disable the age filter."""
        old_question = make_mock_question(creation_date=time.time() - (1000 * 86400))
        assert passes_age_filter(old_question, max_age_days=-1) is True


# ---------------------------------------------------------------------------
# TestPassesKeywordFilter
# ---------------------------------------------------------------------------


class TestPassesKeywordFilter:
    def test_passes_with_keyword_in_title(self) -> None:
        """A keyword found in the question title should make the question pass."""
        question = make_mock_question(title="How to reverse a Python list?")
        assert passes_keyword_filter(question, keywords=["reverse"]) is True

    def test_passes_with_keyword_in_body(self) -> None:
        """A keyword found in body_markdown should make the question pass."""
        question = make_mock_question(body_markdown="I want to use asyncio for async programming.")
        assert passes_keyword_filter(question, keywords=["asyncio"]) is True

    def test_passes_with_empty_keywords(self) -> None:
        """An empty keywords list means no constraint — any question should pass."""
        question = make_mock_question(title="Unrelated title", body_markdown="Unrelated body.")
        assert passes_keyword_filter(question, keywords=[]) is True

    def test_fails_with_no_match(self) -> None:
        """A question with no matching keywords should fail."""
        question = make_mock_question(title="JavaScript tips", body_markdown="Use const and let.")
        assert passes_keyword_filter(question, keywords=["python", "django"]) is False

    def test_matching_is_case_insensitive(self) -> None:
        """Keyword matching should be case-insensitive."""
        question = make_mock_question(title="Python Best Practices")
        assert passes_keyword_filter(question, keywords=["PYTHON"]) is True


# ---------------------------------------------------------------------------
# TestApplyRuleFilters
# ---------------------------------------------------------------------------


class TestApplyRuleFilters:
    def test_all_pass_returns_true(self) -> None:
        """A question that passes all filters should return True."""
        question = make_mock_question(
            score=50,
            answer_count=5,
            is_answered=True,
            tags=["python"],
            creation_date=time.time() - 86400,  # 1 day ago
        )
        rule_config = _make_permissive_rule_config()
        assert apply_rule_filters(question, rule_config) is True

    def test_short_circuits_on_first_failure(self) -> None:
        """If the cheapest filter fails, the result should be False without evaluating further."""
        question = make_mock_question(is_answered=False)
        rule_config = _make_permissive_rule_config()
        rule_config.only_answered = True
        assert apply_rule_filters(question, rule_config) is False

    def test_score_filter_blocks_low_score(self) -> None:
        """A question with score below min_score should fail apply_rule_filters."""
        question = make_mock_question(score=0, is_answered=True, answer_count=5)
        rule_config = _make_permissive_rule_config()
        rule_config.min_score = 10
        assert apply_rule_filters(question, rule_config) is False

    def test_keyword_filter_blocks_no_match(self) -> None:
        """A question with no keyword match should fail apply_rule_filters."""
        question = make_mock_question(
            title="JavaScript closures",
            body_markdown="This is about JS.",
            score=100,
            answer_count=5,
            is_answered=True,
        )
        rule_config = _make_permissive_rule_config()
        rule_config.keywords = ["python", "pandas"]
        assert apply_rule_filters(question, rule_config) is False
