"""Tests for collection orchestration in deep_thought.stackexchange.processor.

Tests cover rule processing, incremental update detection, global caps, and
per-question error handling.
"""

from __future__ import annotations

import sqlite3  # noqa: TC003
from pathlib import Path  # noqa: TC003
from unittest.mock import MagicMock, patch

from deep_thought.stackexchange.config import RuleConfig, StackExchangeConfig, TagConfig
from deep_thought.stackexchange.db.queries import get_quota_usage
from deep_thought.stackexchange.processor import (
    CollectionResult,
    _process_rule,
    _process_single_question,
    run_collection,
)
from tests.stackexchange.conftest import make_mock_question

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_rule_config(
    name: str = "test_rule",
    site: str = "stackoverflow",
    min_score: int = 0,
    min_answers: int = 0,
    max_questions: int = 50,
) -> RuleConfig:
    """Build a permissive RuleConfig for processor tests."""
    return RuleConfig(
        name=name,
        site=site,
        tags=TagConfig(include=[], any=[]),
        sort="votes",
        order="desc",
        min_score=min_score,
        min_answers=min_answers,
        only_answered=False,
        max_age_days=0,  # 0 disables age filter
        keywords=[],
        max_questions=max_questions,
        max_answers_per_question=5,
        include_comments=False,
        max_comments_per_question=30,
    )


def _make_se_config(rules: list[RuleConfig] | None = None) -> StackExchangeConfig:
    """Build a minimal StackExchangeConfig for processor tests."""
    return StackExchangeConfig(
        api_key_env="STACKEXCHANGE_API_KEY",
        max_questions_per_run=100,
        output_dir="data/stackexchange/export/",
        generate_llms_files=False,
        qdrant_collection="deep_thought_db",
        rules=rules or [_make_rule_config()],
    )


# ---------------------------------------------------------------------------
# TestCollectionResult
# ---------------------------------------------------------------------------


class TestCollectionResult:
    def test_default_counts_are_zero(self) -> None:
        """CollectionResult should initialize all count fields to zero."""
        result = CollectionResult()
        assert result.questions_collected == 0
        assert result.questions_skipped == 0
        assert result.questions_updated == 0
        assert result.questions_errored == 0

    def test_default_errors_is_empty_list(self) -> None:
        """CollectionResult should initialize errors as an empty list."""
        result = CollectionResult()
        assert result.errors == []

    def test_default_rate_limited_is_false(self) -> None:
        """CollectionResult should initialize rate_limited to False."""
        result = CollectionResult()
        assert result.rate_limited is False

    def test_fields_can_be_modified(self) -> None:
        """CollectionResult fields should be mutable."""
        result = CollectionResult()
        result.questions_collected = 5
        result.errors.append("some error")
        assert result.questions_collected == 5
        assert len(result.errors) == 1


# ---------------------------------------------------------------------------
# TestRunCollection
# ---------------------------------------------------------------------------


class TestRunCollection:
    def test_calls_process_rule_for_each_rule(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_collection should call _process_rule once per configured rule."""
        rule_a = _make_rule_config(name="rule_a")
        rule_b = _make_rule_config(name="rule_b")
        config = _make_se_config(rules=[rule_a, rule_b])

        mock_client = MagicMock()
        mock_client.get_questions.return_value = []
        mock_client.get_answers.return_value = {}
        mock_client.get_question_comments.return_value = {}
        mock_client.get_answer_comments.return_value = {}

        with patch("deep_thought.stackexchange.processor._process_rule") as mock_process_rule:
            mock_process_rule.return_value = CollectionResult()
            run_collection(
                se_client=mock_client,
                config=config,
                db_conn=in_memory_db,
                dry_run=True,
                force=False,
                rule_name_filter=None,
                output_override=tmp_path,
            )

        assert mock_process_rule.call_count == 2

    def test_rule_name_filter_limits_to_one_rule(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """When rule_name_filter is set, only the matching rule should be processed."""
        rule_a = _make_rule_config(name="rule_a")
        rule_b = _make_rule_config(name="rule_b")
        config = _make_se_config(rules=[rule_a, rule_b])

        mock_client = MagicMock()

        with patch("deep_thought.stackexchange.processor._process_rule") as mock_process_rule:
            mock_process_rule.return_value = CollectionResult()
            run_collection(
                se_client=mock_client,
                config=config,
                db_conn=in_memory_db,
                dry_run=True,
                force=False,
                rule_name_filter="rule_a",
                output_override=tmp_path,
            )

        assert mock_process_rule.call_count == 1
        called_rule = mock_process_rule.call_args.kwargs["rule_config"]
        assert called_rule.name == "rule_a"

    def test_unknown_rule_name_filter_returns_error(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A rule_name_filter that matches no rule should append an error to the result."""
        config = _make_se_config(rules=[_make_rule_config(name="test_rule")])
        mock_client = MagicMock()

        result = run_collection(
            se_client=mock_client,
            config=config,
            db_conn=in_memory_db,
            dry_run=True,
            force=False,
            rule_name_filter="nonexistent_rule",
            output_override=tmp_path,
        )

        assert len(result.errors) > 0
        assert any("nonexistent_rule" in error for error in result.errors)

    def test_output_override_is_used(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """When output_override is set, it should be passed to _process_rule instead of config.output_dir."""
        config = _make_se_config()
        override_dir = tmp_path / "custom_output"
        mock_client = MagicMock()

        with patch("deep_thought.stackexchange.processor._process_rule") as mock_process_rule:
            mock_process_rule.return_value = CollectionResult()
            run_collection(
                se_client=mock_client,
                config=config,
                db_conn=in_memory_db,
                dry_run=True,
                force=False,
                rule_name_filter=None,
                output_override=override_dir,
            )

        called_output_dir = mock_process_rule.call_args.kwargs["output_dir"]
        assert called_output_dir == override_dir


# ---------------------------------------------------------------------------
# TestProcessRule
# ---------------------------------------------------------------------------


class TestProcessRule:
    def test_fetches_and_filters_questions(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """_process_rule should call get_questions on the client and apply filters."""
        rule_config = _make_rule_config()
        mock_client = MagicMock()
        mock_client.get_questions.return_value = []
        mock_client.get_answers.return_value = {}

        with patch("deep_thought.stackexchange.processor.apply_rule_filters", return_value=True):
            result = _process_rule(
                se_client=mock_client,
                rule_config=rule_config,
                db_conn=in_memory_db,
                output_dir=tmp_path,
                dry_run=True,
                force=False,
                global_question_count=0,
                max_questions_per_run=100,
            )

        mock_client.get_questions.assert_called_once()
        assert isinstance(result, CollectionResult)

    def test_returns_empty_result_when_global_cap_reached(
        self, in_memory_db: sqlite3.Connection, tmp_path: Path
    ) -> None:
        """When global_question_count >= max_questions_per_run, the rule should be skipped entirely."""
        rule_config = _make_rule_config()
        mock_client = MagicMock()

        result = _process_rule(
            se_client=mock_client,
            rule_config=rule_config,
            db_conn=in_memory_db,
            output_dir=tmp_path,
            dry_run=True,
            force=False,
            global_question_count=100,
            max_questions_per_run=100,
        )

        mock_client.get_questions.assert_not_called()
        assert result.questions_collected == 0


# ---------------------------------------------------------------------------
# TestIncrementalUpdate
# ---------------------------------------------------------------------------


class TestIncrementalUpdate:
    def test_skips_when_answer_count_unchanged(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A question with the same answer_count as stored should be skipped."""
        from deep_thought.stackexchange.db.queries import upsert_collected_question
        from deep_thought.stackexchange.models import CollectedQuestionLocal

        question = make_mock_question(question_id=11111, answer_count=5)
        local_question = CollectedQuestionLocal.from_api(
            api_question=question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path=str(tmp_path / "test_rule" / "test.md"),
        )
        upsert_collected_question(in_memory_db, local_question.to_dict())
        in_memory_db.commit()

        rule_config = _make_rule_config()
        action = _process_single_question(
            question=question,
            answers=[],
            question_comments=[],
            answer_comments={},
            rule_config=rule_config,
            db_conn=in_memory_db,
            output_dir=tmp_path,
            date_prefix="260411",
            dry_run=False,
            force=False,
        )

        assert action == "skipped"

    def test_reprocesses_when_answer_count_increases(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """A question with more answers than stored should be reprocessed."""
        from deep_thought.stackexchange.db.queries import upsert_collected_question
        from deep_thought.stackexchange.models import CollectedQuestionLocal

        old_question = make_mock_question(question_id=22222, answer_count=2)
        local_question = CollectedQuestionLocal.from_api(
            api_question=old_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path=str(tmp_path / "test_rule" / "old.md"),
        )
        upsert_collected_question(in_memory_db, local_question.to_dict())
        in_memory_db.commit()

        # Now the same question has more answers
        updated_question = make_mock_question(question_id=22222, answer_count=5)
        rule_config = _make_rule_config()

        action = _process_single_question(
            question=updated_question,
            answers=[],
            question_comments=[],
            answer_comments={},
            rule_config=rule_config,
            db_conn=in_memory_db,
            output_dir=tmp_path,
            date_prefix="260411",
            dry_run=False,
            force=False,
        )

        assert action == "updated"


# ---------------------------------------------------------------------------
# TestGlobalCap
# ---------------------------------------------------------------------------


class TestGlobalCap:
    def test_stops_when_max_questions_per_run_reached(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_collection should pass the running question count to _process_rule so it can
        honor the global cap. After the cap is reached, subsequent rules receive a
        global_question_count >= max_questions_per_run and return without collecting.
        """
        many_rules = [_make_rule_config(name=f"rule_{i}") for i in range(5)]
        config = _make_se_config(rules=many_rules)
        config.max_questions_per_run = 2

        # Each call records the global_question_count that was passed in
        received_global_counts: list[int] = []

        def fake_process_rule(**kwargs: object) -> CollectionResult:
            """Record the incoming global count and simulate 1 question collected."""
            received_global_counts.append(int(str(kwargs["global_question_count"])))
            result = CollectionResult()
            result.questions_collected = 1
            return result

        mock_client = MagicMock()

        with patch("deep_thought.stackexchange.processor._process_rule", side_effect=fake_process_rule):
            run_collection(
                se_client=mock_client,
                config=config,
                db_conn=in_memory_db,
                dry_run=True,
                force=False,
                rule_name_filter=None,
                output_override=tmp_path,
            )

        # The global count passed to the third and later rules must be >= max_questions_per_run
        # (meaning those rules see that the cap is reached and can bail early inside _process_rule)
        assert len(received_global_counts) == 5  # all rules are dispatched by run_collection
        # After 2 rules collect 1 each, global_question_count grows to 2
        assert received_global_counts[2] >= config.max_questions_per_run


# ---------------------------------------------------------------------------
# TestQuotaPersistence
# ---------------------------------------------------------------------------


class TestQuotaPersistence:
    def test_quota_is_persisted_after_collection(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_collection should write quota usage to the DB when dry_run=False."""
        config = _make_se_config()
        mock_client = MagicMock()
        mock_client.get_questions.return_value = []
        mock_client.quota_remaining = 9500

        run_collection(
            se_client=mock_client,
            config=config,
            db_conn=in_memory_db,
            dry_run=False,
            force=False,
            rule_name_filter=None,
            output_override=tmp_path,
        )
        in_memory_db.commit()

        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        quota_row = get_quota_usage(in_memory_db, today)
        assert quota_row is not None
        assert quota_row["quota_remaining"] == 9500

    def test_quota_not_persisted_on_dry_run(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_collection should NOT write quota usage when dry_run=True."""
        config = _make_se_config()
        mock_client = MagicMock()
        mock_client.get_questions.return_value = []
        mock_client.quota_remaining = 9500

        run_collection(
            se_client=mock_client,
            config=config,
            db_conn=in_memory_db,
            dry_run=True,
            force=False,
            rule_name_filter=None,
            output_override=tmp_path,
        )
        in_memory_db.commit()

        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        quota_row = get_quota_usage(in_memory_db, today)
        assert quota_row is None

    def test_quota_not_persisted_when_none(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """run_collection should NOT write quota when client.quota_remaining is None."""
        config = _make_se_config()
        mock_client = MagicMock()
        mock_client.get_questions.return_value = []
        mock_client.quota_remaining = None

        run_collection(
            se_client=mock_client,
            config=config,
            db_conn=in_memory_db,
            dry_run=False,
            force=False,
            rule_name_filter=None,
            output_override=tmp_path,
        )
        in_memory_db.commit()

        from datetime import UTC, datetime

        today = datetime.now(tz=UTC).strftime("%Y-%m-%d")
        quota_row = get_quota_usage(in_memory_db, today)
        assert quota_row is None


# ---------------------------------------------------------------------------
# TestLlmsIntegration
# ---------------------------------------------------------------------------


class TestLlmsIntegration:
    def test_llms_files_generated_when_enabled(self, in_memory_db: sqlite3.Connection, tmp_path: Path) -> None:
        """_process_rule should generate .llms.txt when generate_llms_files=True and questions are collected."""
        rule_config = _make_rule_config()
        mock_client = MagicMock()

        question = make_mock_question(question_id=99999)
        mock_client.get_questions.return_value = [question]
        mock_client.get_answers.return_value = {99999: []}
        mock_client.get_question_comments.return_value = {99999: []}
        mock_client.get_answer_comments.return_value = {}

        result = _process_rule(
            se_client=mock_client,
            rule_config=rule_config,
            db_conn=in_memory_db,
            output_dir=tmp_path,
            dry_run=False,
            force=False,
            global_question_count=0,
            max_questions_per_run=100,
            generate_llms_files=True,
        )

        assert result.questions_collected == 1
        rule_output_dir = tmp_path / rule_config.name
        llms_index = rule_output_dir / ".llms.txt"
        llms_full = rule_output_dir / ".llms-full.txt"
        assert llms_index.exists(), ".llms.txt should be generated"
        assert llms_full.exists(), ".llms-full.txt should be generated"
