"""Tests for data models in deep_thought.stackexchange.models.

Verifies from_api() construction, to_dict() output, and key field encoding.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from deep_thought.stackexchange.models import CollectedQuestionLocal, QuotaUsageLocal
from tests.stackexchange.conftest import make_mock_question

# ---------------------------------------------------------------------------
# TestCollectedQuestionLocal
# ---------------------------------------------------------------------------


class TestCollectedQuestionLocal:
    def test_from_api_creates_correct_state_key(self) -> None:
        """from_api() should construct state_key as '{question_id}:{site}:{rule_name}'."""
        api_question = make_mock_question(question_id=99999)
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="my_rule",
            site="stackoverflow",
            output_path="/some/output/path.md",
        )
        assert result.state_key == "99999:stackoverflow:my_rule"

    def test_from_api_sets_question_id(self) -> None:
        """from_api() should set question_id as an integer."""
        api_question = make_mock_question(question_id=42)
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        assert result.question_id == 42

    def test_from_api_sets_site(self) -> None:
        """from_api() should store the site name correctly."""
        api_question = make_mock_question()
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="superuser",
            output_path="/path.md",
        )
        assert result.site == "superuser"

    def test_from_api_sets_rule_name(self) -> None:
        """from_api() should store the rule name correctly."""
        api_question = make_mock_question()
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="my_collection_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        assert result.rule_name == "my_collection_rule"

    def test_from_api_tags_are_json_encoded(self) -> None:
        """from_api() should JSON-encode the tags list into a string."""
        api_question = make_mock_question(tags=["python", "list", "sorting"])
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        assert isinstance(result.tags, str)
        decoded_tags = json.loads(result.tags)
        assert decoded_tags == ["python", "list", "sorting"]

    def test_from_api_sets_output_path(self) -> None:
        """from_api() should store the output_path as provided."""
        api_question = make_mock_question()
        output_path = "/data/stackexchange/export/test_rule/260411_12345_title.md"
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path=output_path,
        )
        assert result.output_path == output_path

    def test_from_api_status_is_ok(self) -> None:
        """from_api() should set status to 'ok'."""
        api_question = make_mock_question()
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        assert result.status == "ok"

    def test_from_api_sets_accepted_answer_id(self) -> None:
        """from_api() should store the accepted_answer_id when present."""
        api_question = make_mock_question(accepted_answer_id=55555)
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        assert result.accepted_answer_id == 55555

    def test_from_api_accepted_answer_id_none_when_absent(self) -> None:
        """from_api() should store None for accepted_answer_id when not present in the API response."""
        api_question = make_mock_question(accepted_answer_id=None)
        result = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        assert result.accepted_answer_id is None

    def test_to_dict_returns_complete_dict(self) -> None:
        """to_dict() should return a dict with all expected keys."""
        api_question = make_mock_question()
        local_question = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        result = local_question.to_dict()
        expected_keys = {
            "state_key",
            "question_id",
            "site",
            "rule_name",
            "title",
            "link",
            "tags",
            "score",
            "answer_count",
            "accepted_answer_id",
            "output_path",
            "status",
            "created_at",
            "updated_at",
        }
        assert set(result.keys()) == expected_keys

    def test_to_dict_tags_are_json_string(self) -> None:
        """to_dict() should preserve the JSON-encoded tags string."""
        api_question = make_mock_question(tags=["python", "performance"])
        local_question = CollectedQuestionLocal.from_api(
            api_question=api_question,
            rule_name="test_rule",
            site="stackoverflow",
            output_path="/path.md",
        )
        result_dict = local_question.to_dict()
        assert isinstance(result_dict["tags"], str)
        assert json.loads(result_dict["tags"]) == ["python", "performance"]


# ---------------------------------------------------------------------------
# TestQuotaUsageLocal
# ---------------------------------------------------------------------------


class TestQuotaUsageLocal:
    def test_from_api_sets_correct_date_format(self) -> None:
        """from_api() should set date as YYYY-MM-DD using today's UTC date."""
        result = QuotaUsageLocal.from_api(quota_remaining=9000, requests_delta=1)
        today_str = datetime.now(UTC).strftime("%Y-%m-%d")
        assert result.date == today_str

    def test_from_api_sets_quota_remaining(self) -> None:
        """from_api() should store the quota_remaining value correctly."""
        result = QuotaUsageLocal.from_api(quota_remaining=8765, requests_delta=1)
        assert result.quota_remaining == 8765

    def test_from_api_sets_requests_used(self) -> None:
        """from_api() should store the requests_delta as requests_used."""
        result = QuotaUsageLocal.from_api(quota_remaining=9000, requests_delta=3)
        assert result.requests_used == 3

    def test_from_api_default_requests_delta_is_one(self) -> None:
        """from_api() should default requests_delta to 1 when not specified."""
        result = QuotaUsageLocal.from_api(quota_remaining=5000)
        assert result.requests_used == 1

    def test_to_dict_returns_complete_dict(self) -> None:
        """to_dict() should return a dict with all expected keys."""
        result = QuotaUsageLocal.from_api(quota_remaining=9000)
        result_dict = result.to_dict()
        expected_keys = {"date", "requests_used", "quota_remaining", "created_at", "updated_at"}
        assert set(result_dict.keys()) == expected_keys

    def test_to_dict_values_match_fields(self) -> None:
        """to_dict() should return values that match the dataclass fields."""
        quota = QuotaUsageLocal.from_api(quota_remaining=7777, requests_delta=2)
        quota_dict = quota.to_dict()
        assert quota_dict["quota_remaining"] == 7777
        assert quota_dict["requests_used"] == 2
        assert quota_dict["date"] == quota.date
