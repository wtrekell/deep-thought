"""Post-fetch filtering for the Gmail Tool.

Applies deduplication and per-run cap enforcement after Gmail API results
are returned but before processing. Gmail's search query syntax handles
most filtering server-side; these functions handle the remaining local checks.
"""

from __future__ import annotations

import sqlite3  # noqa: TC003

from deep_thought.gmail.db.queries import get_processed_email


def is_already_processed(message_id: str, conn: sqlite3.Connection) -> bool:
    """Check if a message has already been collected with status 'ok'.

    Args:
        message_id: The Gmail message ID to check.
        conn: An open SQLite connection.

    Returns:
        True if the message exists in processed_emails with status 'ok'.
    """
    existing = get_processed_email(conn, message_id)
    if existing is None:
        return False
    return existing.get("status") == "ok"


def is_within_max_emails(current_count: int, max_emails: int) -> bool:
    """Check if the current count is still under the per-run email cap.

    Args:
        current_count: Number of emails processed so far in this run.
        max_emails: Maximum number of emails allowed per run.

    Returns:
        True if current_count < max_emails.
    """
    return current_count < max_emails
