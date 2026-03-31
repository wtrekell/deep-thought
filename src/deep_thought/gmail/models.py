"""Local dataclasses for the Gmail Tool.

ProcessedEmailLocal mirrors the processed_emails database table and represents
the state of a single collected email, including its processing outcome and
output file path.

DecisionCacheLocal mirrors the decision_cache table and represents a cached
Gemini AI extraction result.

CollectResult and SendResult are returned from collect and send operations
to summarise what happened.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _slugify_subject(subject: str, max_length: int = 80) -> str:
    """Convert an email subject line to a filesystem-safe slug.

    Lowercases, replaces non-alphanumeric characters with hyphens, collapses
    repeated hyphens, strips leading/trailing hyphens, and truncates.

    Args:
        subject: The raw subject string.
        max_length: Maximum length of the resulting slug.

    Returns:
        A cleaned slug suitable for use in a filename.
    """
    slug = subject.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_length] if len(slug) > max_length else slug


def _extract_header(message: dict[str, Any], header_name: str) -> str | None:
    """Extract a header value from a Gmail API message dict.

    Searches the payload.headers list for a matching header name
    (case-insensitive comparison).

    Args:
        message: A Gmail API message dict with a payload.headers structure.
        header_name: The header name to look for (e.g., 'Subject', 'From').

    Returns:
        The header value string, or None if not found.
    """
    payload = message.get("payload", {})
    headers = payload.get("headers", [])
    header_name_lower = header_name.lower()
    for header in headers:
        if header.get("name", "").lower() == header_name_lower:
            value: str | None = header.get("value")
            return value
    return None


def _parse_email_address(from_header: str) -> str:
    """Extract just the email address from a From header value.

    Handles formats like:
    - "Name <email@example.com>" → "email@example.com"
    - "email@example.com" → "email@example.com"

    Args:
        from_header: The raw From header value.

    Returns:
        The extracted email address string.
    """
    match = re.search(r"<([^>]+)>", from_header)
    if match:
        return match.group(1)
    return from_header.strip()


# ---------------------------------------------------------------------------
# ProcessedEmailLocal
# ---------------------------------------------------------------------------


@dataclass
class ProcessedEmailLocal:
    """Local representation of a collected and processed email.

    Mirrors the processed_emails database table. All timestamp fields are
    ISO 8601 strings.
    """

    message_id: str
    rule_name: str
    subject: str
    from_address: str
    output_path: str
    actions_taken: str
    status: str
    created_at: str
    updated_at: str
    synced_at: str

    @classmethod
    def from_message(
        cls,
        message: dict[str, Any],
        rule_name: str,
        output_path: str,
        actions: list[str],
    ) -> ProcessedEmailLocal:
        """Convert a Gmail API message dict into a ProcessedEmailLocal.

        Extracts the Subject and From headers from the message payload.
        Timestamps are set to the current UTC time.

        Args:
            message: A Gmail API message dict (format='full').
            rule_name: The name of the rule that triggered collection.
            output_path: Path to the generated markdown file on disk.
            actions: List of action strings that were applied.

        Returns:
            A ProcessedEmailLocal with all fields populated.
        """
        import json

        message_id: str = message.get("id", "")
        subject: str = _extract_header(message, "Subject") or "(no subject)"
        raw_from_header: str = _extract_header(message, "From") or "(unknown sender)"
        from_address: str = _parse_email_address(raw_from_header)
        current_timestamp: str = datetime.now(tz=UTC).isoformat()

        return cls(
            message_id=message_id,
            rule_name=rule_name,
            subject=subject,
            from_address=from_address,
            output_path=output_path,
            actions_taken=json.dumps(actions),
            status="ok",
            created_at=current_timestamp,
            updated_at=current_timestamp,
            synced_at=current_timestamp,
        )

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by database column names.

        Returns:
            A plain dictionary representation suitable for passing to
            database query functions.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# DecisionCacheLocal
# ---------------------------------------------------------------------------


@dataclass
class DecisionCacheLocal:
    """Local representation of a cached AI extraction decision.

    Mirrors the decision_cache database table. This is purely local state —
    it is never synced from an external API.
    """

    cache_key: str
    decision: str
    ttl_seconds: int
    created_at: str
    updated_at: str

    def to_dict(self) -> dict[str, Any]:
        """Return a flat dict keyed by database column names.

        Returns:
            A plain dictionary representation suitable for passing to
            database query functions.
        """
        return asdict(self)


# ---------------------------------------------------------------------------
# Result dataclasses
# ---------------------------------------------------------------------------


@dataclass
class CollectResult:
    """Summary of an email collection run (one or more rules)."""

    processed: int = 0
    skipped: int = 0
    errors: int = 0
    actions_taken: dict[str, int] = field(default_factory=dict)
    error_messages: list[str] = field(default_factory=list)


@dataclass
class SendResult:
    """Summary of a send operation."""

    message_id: str = ""
    thread_id: str = ""
