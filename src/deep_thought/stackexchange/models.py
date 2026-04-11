"""Data models for the Stack Exchange Tool.

This module contains only dataclasses — no API calls, no Pydantic, no I/O.
All models are plain Python dataclasses that represent either API-sourced data
or local database state.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any


@dataclass
class CollectedQuestionLocal:
    """Local state for a collected Stack Exchange question."""

    state_key: str
    question_id: int
    site: str
    rule_name: str
    title: str
    link: str
    tags: str  # JSON-encoded list
    score: int
    answer_count: int
    accepted_answer_id: int | None
    output_path: str
    status: str
    created_at: str
    updated_at: str

    @classmethod
    def from_api(
        cls,
        api_question: dict[str, Any],
        rule_name: str,
        site: str,
        output_path: str,
    ) -> CollectedQuestionLocal:
        """Construct a CollectedQuestionLocal from a raw Stack Exchange API question dict.

        Args:
            api_question: Raw question object from the Stack Exchange API response.
            rule_name: The name of the collection rule that retrieved this question.
            site: The Stack Exchange site (e.g., "stackoverflow").
            output_path: The filesystem path where the exported markdown will be written.

        Returns:
            A fully populated CollectedQuestionLocal with state_key set to
            "{question_id}:{site}:{rule_name}".
        """
        now_iso = datetime.now(UTC).isoformat()
        question_id = int(api_question["question_id"])
        state_key = f"{question_id}:{site}:{rule_name}"
        tags_list = api_question.get("tags", [])
        return cls(
            state_key=state_key,
            question_id=question_id,
            site=site,
            rule_name=rule_name,
            title=str(api_question.get("title", "")),
            link=str(api_question.get("link", "")),
            tags=json.dumps(tags_list),
            score=int(api_question.get("score", 0)),
            answer_count=int(api_question.get("answer_count", 0)),
            accepted_answer_id=api_question.get("accepted_answer_id"),
            output_path=output_path,
            status="ok",
            created_at=now_iso,
            updated_at=now_iso,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation suitable for passing to query functions."""
        return asdict(self)


@dataclass
class QuotaUsageLocal:
    """Daily API quota usage tracking."""

    date: str
    requests_used: int
    quota_remaining: int
    created_at: str
    updated_at: str

    @classmethod
    def from_api(cls, quota_remaining: int, requests_delta: int = 1) -> QuotaUsageLocal:
        """Construct a QuotaUsageLocal from an API quota_remaining value.

        Args:
            quota_remaining: The quota_remaining value returned by the Stack Exchange API.
            requests_delta: Number of API requests consumed in this batch. Defaults to 1.

        Returns:
            A QuotaUsageLocal for today's date.
        """
        now_iso = datetime.now(UTC).isoformat()
        today = datetime.now(UTC).strftime("%Y-%m-%d")
        return cls(
            date=today,
            requests_used=requests_delta,
            quota_remaining=quota_remaining,
            created_at=now_iso,
            updated_at=now_iso,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a plain dict representation suitable for passing to query functions."""
        return asdict(self)
