"""Pure filter functions for Stack Exchange questions.

All functions operate on API response dicts (not local models) and have no
side effects. The apply_rule_filters() function chains them in short-circuit
order from cheapest to most expensive.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from deep_thought.stackexchange.config import RuleConfig

logger = logging.getLogger(__name__)


def passes_answered_filter(question: dict[str, Any], only_answered: bool) -> bool:
    """Check if the question satisfies the answered requirement.

    Args:
        question: A Stack Exchange API question dict.
        only_answered: If True, the question must have is_answered=True to pass.

    Returns:
        True if the filter is satisfied, False otherwise.
    """
    if not only_answered:
        return True
    return bool(question.get("is_answered", False))


def passes_score_filter(question: dict[str, Any], min_score: int) -> bool:
    """Check if the question meets the minimum score threshold.

    Args:
        question: A Stack Exchange API question dict.
        min_score: Minimum vote score required (inclusive).

    Returns:
        True if the question's score is >= min_score, False otherwise.
    """
    return int(question.get("score", 0)) >= min_score


def passes_answer_count_filter(question: dict[str, Any], min_answers: int) -> bool:
    """Check if the question has enough answers.

    Args:
        question: A Stack Exchange API question dict.
        min_answers: Minimum number of answers required (inclusive).

    Returns:
        True if the question's answer_count is >= min_answers, False otherwise.
    """
    return int(question.get("answer_count", 0)) >= min_answers


def passes_tag_any_filter(question: dict[str, Any], any_tags: list[str]) -> bool:
    """Check if the question has at least one of the 'any' tags (client-side OR).

    This is a client-side supplement to the API's tagged parameter (which does
    AND matching). Use this to express OR semantics across a tag set.

    Returns True if any_tags is empty (no constraint).

    Args:
        question: A Stack Exchange API question dict.
        any_tags: Tags where at least one must be present. Empty list = no constraint.

    Returns:
        True if the question carries at least one of the any_tags, or if any_tags is empty.
    """
    if not any_tags:
        return True
    question_tags = set(question.get("tags", []))
    return bool(question_tags.intersection(any_tags))


def passes_age_filter(question: dict[str, Any], max_age_days: int) -> bool:
    """Check if the question was created within the max_age_days window.

    Args:
        question: A Stack Exchange API question dict with a creation_date field.
        max_age_days: Maximum allowed age in days. A value of 0 or below disables the filter.

    Returns:
        True if the question is within the age window, False otherwise.
    """
    if max_age_days <= 0:
        return True
    creation_date = question.get("creation_date", 0)
    age_seconds = time.time() - int(creation_date)
    max_age_seconds = max_age_days * 86400
    return age_seconds <= max_age_seconds


def passes_keyword_filter(question: dict[str, Any], keywords: list[str]) -> bool:
    """Check if any keyword appears in the question title or body_markdown.

    Client-side post-fetch filter. Returns True if keywords list is empty.
    Matching is case-insensitive substring matching — no glob wildcards.

    Args:
        question: A Stack Exchange API question dict.
        keywords: List of keyword strings to search for. Empty list = no constraint.

    Returns:
        True if at least one keyword matches or the keyword list is empty.
    """
    if not keywords:
        return True
    title = str(question.get("title", "")).lower()
    body = str(question.get("body_markdown", "")).lower()
    searchable_text = f"{title} {body}"
    return any(keyword.lower() in searchable_text for keyword in keywords)


def apply_rule_filters(question: dict[str, Any], rule_config: RuleConfig) -> bool:
    """Apply all rule filters in short-circuit order (cheapest first).

    Returns True only if the question passes all configured filters. Filters
    are evaluated from least expensive (boolean flag, integer comparison) to
    most expensive (string scanning).

    Args:
        question: A Stack Exchange API question dict.
        rule_config: The RuleConfig containing all filter parameters.

    Returns:
        True if the question passes every filter, False if any filter fails.
    """
    question_id = question.get("question_id", "?")

    if not passes_answered_filter(question, rule_config.only_answered):
        logger.debug("Question %s: filtered by answered requirement", question_id)
        return False

    if not passes_score_filter(question, rule_config.min_score):
        logger.debug(
            "Question %s: filtered by min_score=%d (score=%s)",
            question_id,
            rule_config.min_score,
            question.get("score"),
        )
        return False

    if not passes_answer_count_filter(question, rule_config.min_answers):
        logger.debug(
            "Question %s: filtered by min_answers=%d (answers=%s)",
            question_id,
            rule_config.min_answers,
            question.get("answer_count"),
        )
        return False

    if not passes_tag_any_filter(question, rule_config.tags.any):
        logger.debug("Question %s: filtered by tags.any=%s", question_id, rule_config.tags.any)
        return False

    if not passes_age_filter(question, rule_config.max_age_days):
        logger.debug("Question %s: filtered by max_age_days=%d", question_id, rule_config.max_age_days)
        return False

    if not passes_keyword_filter(question, rule_config.keywords):
        logger.debug("Question %s: filtered by keywords=%s", question_id, rule_config.keywords)
        return False

    return True
