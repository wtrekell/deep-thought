"""Tests for parameterized SQL query functions in deep_thought.stackexchange.db.queries.

All tests use an in-memory SQLite database via the in_memory_db fixture.
Write functions do not auto-commit; tests call conn.commit() explicitly.
"""

from __future__ import annotations

import sqlite3  # noqa: TC003
from datetime import UTC, datetime
from typing import Any

from deep_thought.stackexchange.db.queries import (
    delete_all_questions,
    delete_questions_by_rule,
    get_collected_question,
    get_key_value,
    get_questions_by_rule,
    get_quota_usage,
    set_key_value,
    upsert_collected_question,
    upsert_quota_usage,
)
from deep_thought.stackexchange.models import CollectedQuestionLocal
from tests.stackexchange.conftest import make_mock_question

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_question_dict(
    question_id: int = 12345,
    rule_name: str = "test_rule",
    site: str = "stackoverflow",
    answer_count: int = 5,
) -> dict[str, Any]:
    """Build a question dict suitable for upsert_collected_question."""
    api_question = make_mock_question(question_id=question_id, answer_count=answer_count)
    local_question = CollectedQuestionLocal.from_api(
        api_question=api_question,
        rule_name=rule_name,
        site=site,
        output_path=f"/data/export/{rule_name}/{question_id}.md",
    )
    return local_question.to_dict()


# ---------------------------------------------------------------------------
# TestUpsertCollectedQuestion
# ---------------------------------------------------------------------------


class TestUpsertCollectedQuestion:
    def test_insert_new_question(self, in_memory_db: sqlite3.Connection) -> None:
        """Upserting a new question should create a row in collected_questions."""
        question_dict = _make_question_dict(question_id=111)
        upsert_collected_question(in_memory_db, question_dict)
        in_memory_db.commit()

        result = get_collected_question(in_memory_db, question_dict["state_key"])
        assert result is not None
        assert result["question_id"] == 111

    def test_update_preserves_created_at(self, in_memory_db: sqlite3.Connection) -> None:
        """Upserting an existing question should preserve the original created_at timestamp."""
        question_dict = _make_question_dict(question_id=222)
        upsert_collected_question(in_memory_db, question_dict)
        in_memory_db.commit()

        original_row = get_collected_question(in_memory_db, question_dict["state_key"])
        assert original_row is not None
        original_created_at = original_row["created_at"]

        # Upsert again with different score
        updated_dict = {**question_dict, "score": 999}
        upsert_collected_question(in_memory_db, updated_dict)
        in_memory_db.commit()

        updated_row = get_collected_question(in_memory_db, question_dict["state_key"])
        assert updated_row is not None
        assert updated_row["created_at"] == original_created_at

    def test_update_changes_updated_at(self, in_memory_db: sqlite3.Connection) -> None:
        """Upserting an existing question should update the updated_at timestamp."""
        question_dict = _make_question_dict(question_id=333)
        # Set an artificially old updated_at
        old_time = "2020-01-01T00:00:00+00:00"
        question_dict = {**question_dict, "updated_at": old_time}
        upsert_collected_question(in_memory_db, question_dict)
        in_memory_db.commit()

        # Upsert again
        updated_dict = {**question_dict, "score": 500}
        upsert_collected_question(in_memory_db, updated_dict)
        in_memory_db.commit()

        updated_row = get_collected_question(in_memory_db, question_dict["state_key"])
        assert updated_row is not None
        # updated_at should have changed from the old timestamp
        assert updated_row["updated_at"] != old_time

    def test_update_overwrites_score(self, in_memory_db: sqlite3.Connection) -> None:
        """Upserting with a new score should overwrite the previous score value."""
        question_dict = _make_question_dict(question_id=444)
        upsert_collected_question(in_memory_db, question_dict)
        in_memory_db.commit()

        updated_dict = {**question_dict, "score": 9999}
        upsert_collected_question(in_memory_db, updated_dict)
        in_memory_db.commit()

        updated_row = get_collected_question(in_memory_db, question_dict["state_key"])
        assert updated_row is not None
        assert updated_row["score"] == 9999


# ---------------------------------------------------------------------------
# TestGetCollectedQuestion
# ---------------------------------------------------------------------------


class TestGetCollectedQuestion:
    def test_found_returns_dict(self, in_memory_db: sqlite3.Connection) -> None:
        """get_collected_question should return a dict when the row exists."""
        question_dict = _make_question_dict(question_id=555)
        upsert_collected_question(in_memory_db, question_dict)
        in_memory_db.commit()

        result = get_collected_question(in_memory_db, question_dict["state_key"])
        assert result is not None
        assert isinstance(result, dict)
        assert result["question_id"] == 555

    def test_not_found_returns_none(self, in_memory_db: sqlite3.Connection) -> None:
        """get_collected_question should return None for a non-existent state_key."""
        result = get_collected_question(in_memory_db, "99999:nonexistent:rule")
        assert result is None


# ---------------------------------------------------------------------------
# TestGetQuestionsByRule
# ---------------------------------------------------------------------------


class TestGetQuestionsByRule:
    def test_returns_matching_questions(self, in_memory_db: sqlite3.Connection) -> None:
        """get_questions_by_rule should return all questions for the given rule name."""
        question_dict_a = _make_question_dict(question_id=601, rule_name="rule_alpha")
        question_dict_b = _make_question_dict(question_id=602, rule_name="rule_alpha")
        upsert_collected_question(in_memory_db, question_dict_a)
        upsert_collected_question(in_memory_db, question_dict_b)
        in_memory_db.commit()

        results = get_questions_by_rule(in_memory_db, "rule_alpha")
        assert len(results) == 2
        returned_ids = {row["question_id"] for row in results}
        assert returned_ids == {601, 602}

    def test_empty_for_unknown_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """get_questions_by_rule should return an empty list for an unknown rule name."""
        results = get_questions_by_rule(in_memory_db, "nonexistent_rule")
        assert results == []

    def test_does_not_return_other_rule_questions(self, in_memory_db: sqlite3.Connection) -> None:
        """get_questions_by_rule should not include questions from other rules."""
        question_dict_a = _make_question_dict(question_id=701, rule_name="rule_a")
        question_dict_b = _make_question_dict(question_id=702, rule_name="rule_b")
        upsert_collected_question(in_memory_db, question_dict_a)
        upsert_collected_question(in_memory_db, question_dict_b)
        in_memory_db.commit()

        results = get_questions_by_rule(in_memory_db, "rule_a")
        assert all(row["rule_name"] == "rule_a" for row in results)


# ---------------------------------------------------------------------------
# TestDeleteAllQuestions
# ---------------------------------------------------------------------------


class TestDeleteAllQuestions:
    def test_deletes_all_and_returns_count(self, in_memory_db: sqlite3.Connection) -> None:
        """delete_all_questions should remove every row and return the deletion count."""
        for question_id in [801, 802, 803]:
            upsert_collected_question(in_memory_db, _make_question_dict(question_id=question_id))
        in_memory_db.commit()

        deleted_count = delete_all_questions(in_memory_db)
        in_memory_db.commit()
        assert deleted_count == 3

        remaining = get_questions_by_rule(in_memory_db, "test_rule")
        assert remaining == []

    def test_returns_zero_when_table_empty(self, in_memory_db: sqlite3.Connection) -> None:
        """delete_all_questions on an empty table should return 0."""
        deleted_count = delete_all_questions(in_memory_db)
        assert deleted_count == 0


# ---------------------------------------------------------------------------
# TestDeleteQuestionsByRule
# ---------------------------------------------------------------------------


class TestDeleteQuestionsByRule:
    def test_deletes_only_matching_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """delete_questions_by_rule should only remove rows for the specified rule."""
        upsert_collected_question(in_memory_db, _make_question_dict(question_id=901, rule_name="rule_to_delete"))
        upsert_collected_question(in_memory_db, _make_question_dict(question_id=902, rule_name="rule_to_keep"))
        in_memory_db.commit()

        deleted_count = delete_questions_by_rule(in_memory_db, "rule_to_delete")
        in_memory_db.commit()
        assert deleted_count == 1

        remaining_deleted = get_questions_by_rule(in_memory_db, "rule_to_delete")
        remaining_kept = get_questions_by_rule(in_memory_db, "rule_to_keep")
        assert remaining_deleted == []
        assert len(remaining_kept) == 1

    def test_returns_zero_for_nonexistent_rule(self, in_memory_db: sqlite3.Connection) -> None:
        """delete_questions_by_rule for an unknown rule should return 0."""
        deleted_count = delete_questions_by_rule(in_memory_db, "ghost_rule")
        assert deleted_count == 0


# ---------------------------------------------------------------------------
# TestQuotaUsage
# ---------------------------------------------------------------------------


class TestQuotaUsage:
    def test_upsert_and_get_quota(self, in_memory_db: sqlite3.Connection) -> None:
        """upsert_quota_usage should insert a row, and get_quota_usage should retrieve it."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        upsert_quota_usage(in_memory_db, date=today, requests_used=5, quota_remaining=9000)
        in_memory_db.commit()

        result = get_quota_usage(in_memory_db, today)
        assert result is not None
        assert result["quota_remaining"] == 9000
        assert result["requests_used"] == 5

    def test_upsert_increments_requests_used(self, in_memory_db: sqlite3.Connection) -> None:
        """Subsequent upserts should accumulate requests_used additively."""
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        upsert_quota_usage(in_memory_db, date=today, requests_used=3, quota_remaining=9990)
        upsert_quota_usage(in_memory_db, date=today, requests_used=4, quota_remaining=9980)
        in_memory_db.commit()

        result = get_quota_usage(in_memory_db, today)
        assert result is not None
        assert result["requests_used"] == 7  # 3 + 4

    def test_get_quota_returns_none_for_missing_date(self, in_memory_db: sqlite3.Connection) -> None:
        """get_quota_usage should return None for a date with no record."""
        result = get_quota_usage(in_memory_db, "2000-01-01")
        assert result is None


# ---------------------------------------------------------------------------
# TestKeyValue
# ---------------------------------------------------------------------------


class TestKeyValue:
    def test_set_and_get_key_value(self, in_memory_db: sqlite3.Connection) -> None:
        """set_key_value should store a value and get_key_value should retrieve it."""
        set_key_value(in_memory_db, "my_key", "my_value")
        in_memory_db.commit()

        result = get_key_value(in_memory_db, "my_key")
        assert result == "my_value"

    def test_overwrite_existing_key(self, in_memory_db: sqlite3.Connection) -> None:
        """set_key_value should overwrite an existing key without raising an error."""
        set_key_value(in_memory_db, "overwrite_key", "first_value")
        in_memory_db.commit()

        set_key_value(in_memory_db, "overwrite_key", "second_value")
        in_memory_db.commit()

        result = get_key_value(in_memory_db, "overwrite_key")
        assert result == "second_value"

    def test_get_missing_key_returns_none(self, in_memory_db: sqlite3.Connection) -> None:
        """get_key_value should return None for a key that was never set."""
        result = get_key_value(in_memory_db, "nonexistent_key")
        assert result is None
