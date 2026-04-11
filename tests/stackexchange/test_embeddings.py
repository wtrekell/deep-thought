"""Tests for deep_thought.stackexchange.embeddings.

All tests mock ``deep_thought.embeddings.write_embedding`` at the module
boundary so no real MLX model or Qdrant connection is required.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from unittest.mock import MagicMock, patch

from deep_thought.stackexchange.models import CollectedQuestionLocal

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_collected_question(
    question_id: int = 12345,
    site: str = "stackoverflow",
    rule_name: str = "test_rule",
    score: int = 150,
    answer_count: int = 5,
) -> CollectedQuestionLocal:
    """Return a CollectedQuestionLocal with realistic test values.

    Args:
        question_id: The Stack Exchange question ID.
        site: The Stack Exchange site slug.
        rule_name: The collection rule name.
        score: The vote score.
        answer_count: Number of answers.

    Returns:
        A fully populated CollectedQuestionLocal.
    """
    now_iso = datetime.now(tz=UTC).isoformat()
    return CollectedQuestionLocal(
        state_key=f"{question_id}:{site}:{rule_name}",
        question_id=question_id,
        site=site,
        rule_name=rule_name,
        title="How do I reverse a list in Python?",
        link=f"https://stackoverflow.com/questions/{question_id}/test",
        tags='["python", "list"]',
        score=score,
        answer_count=answer_count,
        accepted_answer_id=67890,
        output_path=f"/data/stackexchange/export/{rule_name}/260411_{question_id}_test.md",
        status="ok",
        created_at=now_iso,
        updated_at=now_iso,
    )


def _call_write_embedding(
    question: CollectedQuestionLocal,
    content: str = "Title: How do I reverse a list?\n\nSome body text.",
) -> Any:
    """Invoke the module under test with a mock model and client, returning the shared mock.

    Args:
        question: The CollectedQuestionLocal to embed.
        content: The text content to embed.

    Returns:
        The MagicMock for the shared write_embedding call.
    """
    mock_model = MagicMock()
    mock_qdrant_client = MagicMock()

    with patch("deep_thought.embeddings.write_embedding") as mock_shared_write:
        from deep_thought.stackexchange.embeddings import write_embedding

        write_embedding(
            content=content,
            question=question,
            model=mock_model,
            qdrant_client=mock_qdrant_client,
        )
        return mock_shared_write


# ---------------------------------------------------------------------------
# TestWriteEmbedding
# ---------------------------------------------------------------------------


class TestWriteEmbedding:
    def test_write_embedding_calls_shared_write_embedding(self) -> None:
        """The stackexchange write_embedding must call the shared write_embedding exactly once."""
        question = _make_collected_question()
        mock_shared = _call_write_embedding(question)
        mock_shared.assert_called_once()

    def test_payload_source_tool_is_stackexchange(self) -> None:
        """The payload passed to the shared function must have source_tool='stackexchange'."""
        question = _make_collected_question()
        mock_shared = _call_write_embedding(question)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["payload"]["source_tool"] == "stackexchange"

    def test_output_path_not_in_payload_dict(self) -> None:
        """The output_path should be passed as a separate kwarg, not inside the payload dict."""
        question = _make_collected_question()
        mock_shared = _call_write_embedding(question)
        call_kwargs = mock_shared.call_args.kwargs
        assert "output_path" not in call_kwargs["payload"]

    def test_output_path_passed_as_kwarg(self) -> None:
        """The output_path kwarg must match the question's output_path field."""
        question = _make_collected_question()
        mock_shared = _call_write_embedding(question)
        call_kwargs = mock_shared.call_args.kwargs
        assert call_kwargs["output_path"] == question.output_path

    def test_payload_contains_required_fields(self) -> None:
        """The payload must contain all fields required by the shared embedding infrastructure."""
        question = _make_collected_question()
        mock_shared = _call_write_embedding(question)
        payload = mock_shared.call_args.kwargs["payload"]
        for required_field in ["source_tool", "source_type", "rule_name", "collected_date"]:
            assert required_field in payload, f"Missing required field: {required_field}"

    def test_payload_source_type_is_q_and_a(self) -> None:
        """Stack Exchange always uses source_type='q_and_a'."""
        question = _make_collected_question()
        mock_shared = _call_write_embedding(question)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["source_type"] == "q_and_a"

    def test_payload_rule_name_matches_question(self) -> None:
        """The payload's rule_name must match the question's rule_name field."""
        question = _make_collected_question(rule_name="my_custom_rule")
        mock_shared = _call_write_embedding(question)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["rule_name"] == "my_custom_rule"

    def test_payload_question_id_matches_question(self) -> None:
        """The payload must carry the question_id field."""
        question = _make_collected_question(question_id=99999)
        mock_shared = _call_write_embedding(question)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["question_id"] == 99999

    def test_payload_site_matches_question(self) -> None:
        """The payload must carry the site field."""
        question = _make_collected_question(site="superuser")
        mock_shared = _call_write_embedding(question)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["site"] == "superuser"

    def test_payload_score_matches_question(self) -> None:
        """The payload's score must match the question's score field."""
        question = _make_collected_question(score=777)
        mock_shared = _call_write_embedding(question)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["score"] == 777

    def test_payload_answer_count_matches_question(self) -> None:
        """The payload's answer_count must match the question's answer_count field."""
        question = _make_collected_question(answer_count=12)
        mock_shared = _call_write_embedding(question)
        payload = mock_shared.call_args.kwargs["payload"]
        assert payload["answer_count"] == 12

    def test_content_passed_through_to_shared(self) -> None:
        """The content string must be forwarded unchanged to the shared write_embedding function."""
        question = _make_collected_question()
        unique_content = "Title: Unique assertion content\n\nBody text for this specific test."
        mock_shared = _call_write_embedding(question, content=unique_content)
        assert mock_shared.call_args.kwargs["content"] == unique_content
