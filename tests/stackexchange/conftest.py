"""Shared pytest fixtures for the Stack Exchange Tool test suite.

All database fixtures use in-memory SQLite so no disk I/O occurs.
API client fixtures use MagicMock so no real network calls are made.
"""

from __future__ import annotations

import time
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import MagicMock

if TYPE_CHECKING:
    import sqlite3
    from collections.abc import Generator

import pytest

from deep_thought.stackexchange.config import RuleConfig, StackExchangeConfig, TagConfig
from deep_thought.stackexchange.db.schema import initialize_database

# Path to the fixtures directory, used by tests that load files from disk
FIXTURES_DIR = Path(__file__).parent / "fixtures"


# ---------------------------------------------------------------------------
# Database fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def in_memory_db() -> Generator[sqlite3.Connection, None, None]:
    """Return a fully initialized in-memory SQLite connection.

    The connection has WAL mode enabled, foreign keys enforced, and all
    migrations applied. Closes automatically after each test.
    """
    connection = initialize_database(":memory:")
    yield connection
    connection.close()


# ---------------------------------------------------------------------------
# Config fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_rule_config() -> RuleConfig:
    """Return a RuleConfig with realistic test values."""
    return RuleConfig(
        name="test_rule",
        site="stackoverflow",
        tags=TagConfig(include=["python"], any=[]),
        sort="votes",
        order="desc",
        min_score=10,
        min_answers=1,
        only_answered=True,
        max_age_days=365,
        keywords=[],
        max_questions=50,
        max_answers_per_question=5,
        include_comments=True,
        max_comments_per_question=30,
    )


@pytest.fixture()
def sample_config(sample_rule_config: RuleConfig) -> StackExchangeConfig:
    """Return a StackExchangeConfig with realistic test values."""
    return StackExchangeConfig(
        api_key_env="STACKEXCHANGE_API_KEY",
        max_questions_per_run=100,
        output_dir="data/stackexchange/export/",
        generate_llms_files=False,
        qdrant_collection="deep_thought_db",
        rules=[sample_rule_config],
    )


# ---------------------------------------------------------------------------
# Mock client fixture
# ---------------------------------------------------------------------------


@pytest.fixture()
def mock_se_client() -> MagicMock:
    """Return a mock StackExchangeClient with all methods returning empty values."""
    client = MagicMock()
    client.get_questions.return_value = []
    client.get_answers.return_value = {}
    client.get_question_comments.return_value = {}
    client.get_answer_comments.return_value = {}
    return client


# ---------------------------------------------------------------------------
# Mock question/answer/comment factories
# ---------------------------------------------------------------------------


def make_mock_question(
    question_id: int = 12345,
    title: str = "How do I reverse a list in Python?",
    body_markdown: str = "I want to reverse a list. What is the best way to do this?",
    score: int = 150,
    answer_count: int = 5,
    is_answered: bool = True,
    creation_date: float | None = None,
    link: str = "https://stackoverflow.com/questions/12345/how-do-i-reverse-a-list-in-python",
    tags: list[str] | None = None,
    display_name: str = "question_author",
    accepted_answer_id: int | None = 67890,
    last_activity_date: float | None = None,
) -> dict[str, Any]:
    """Return a dict mimicking a Stack Exchange API question response.

    Args:
        question_id: The unique identifier for the question.
        title: The question title text.
        body_markdown: The question body in markdown format.
        score: The vote score for the question.
        answer_count: Number of answers on the question.
        is_answered: Whether the question has an accepted or highly-voted answer.
        creation_date: Unix timestamp of question creation. Defaults to one day ago.
        link: Full URL to the question.
        tags: List of tag strings. Defaults to ["python"].
        display_name: Username of the question author.
        accepted_answer_id: ID of the accepted answer, or None if none exists.
        last_activity_date: Unix timestamp of last activity. Defaults to now.

    Returns:
        A dict matching the structure of a Stack Exchange API question response.
    """
    now = time.time()
    return {
        "question_id": question_id,
        "title": title,
        "body_markdown": body_markdown,
        "score": score,
        "answer_count": answer_count,
        "is_answered": is_answered,
        "creation_date": creation_date if creation_date is not None else now - 86400,
        "link": link,
        "tags": tags if tags is not None else ["python"],
        "owner": {"display_name": display_name},
        "accepted_answer_id": accepted_answer_id,
        "last_activity_date": last_activity_date if last_activity_date is not None else now,
    }


def make_mock_answer(
    answer_id: int = 67890,
    question_id: int = 12345,
    body_markdown: str = "Use `list.reverse()` or `reversed()` built-in.",
    score: int = 200,
    is_accepted: bool = True,
    display_name: str = "answer_author",
    creation_date: float | None = None,
) -> dict[str, Any]:
    """Return a dict mimicking a Stack Exchange API answer response.

    Args:
        answer_id: The unique identifier for the answer.
        question_id: The question this answer belongs to.
        body_markdown: The answer body in markdown format.
        score: The vote score for the answer.
        is_accepted: Whether this is the accepted answer.
        display_name: Username of the answer author.
        creation_date: Unix timestamp of answer creation. Defaults to one day ago.

    Returns:
        A dict matching the structure of a Stack Exchange API answer response.
    """
    return {
        "answer_id": answer_id,
        "question_id": question_id,
        "body_markdown": body_markdown,
        "score": score,
        "is_accepted": is_accepted,
        "owner": {"display_name": display_name},
        "creation_date": creation_date if creation_date is not None else time.time() - 86400,
    }


def make_mock_comment(
    comment_id: int = 11111,
    post_id: int = 12345,
    body: str = "This is a helpful comment.",
    score: int = 5,
    display_name: str = "comment_author",
    creation_date: float | None = None,
) -> dict[str, Any]:
    """Return a dict mimicking a Stack Exchange API comment response.

    Args:
        comment_id: The unique identifier for the comment.
        post_id: The question or answer ID this comment belongs to.
        body: The comment text.
        score: The vote score for the comment.
        display_name: Username of the comment author.
        creation_date: Unix timestamp of comment creation. Defaults to one hour ago.

    Returns:
        A dict matching the structure of a Stack Exchange API comment response.
    """
    return {
        "comment_id": comment_id,
        "post_id": post_id,
        "body": body,
        "score": score,
        "owner": {"display_name": display_name},
        "creation_date": creation_date if creation_date is not None else time.time() - 3600,
    }


# ---------------------------------------------------------------------------
# Fixture-based versions of the factories
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_question() -> dict[str, Any]:
    """Return a mock Stack Exchange question dict with default realistic attributes."""
    return make_mock_question()
