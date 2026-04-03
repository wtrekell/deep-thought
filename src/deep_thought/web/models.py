"""Local dataclasses for the web crawl tool.

CrawledPageLocal mirrors the crawled_pages database table and represents
the state of a single crawled page, including its conversion outcome and
output file path.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class CrawledPageLocal:
    """Local representation of a crawled and converted web page.

    Mirrors the crawled_pages database table. All timestamp fields are ISO 8601 strings.
    """

    url: str
    rule_name: str | None
    title: str | None
    status_code: int | None  # None when no HTTP response (e.g. DNS failure, connection refused)
    word_count: int
    output_path: str
    status: str  # 'success', 'error', or 'skipped'
    created_at: str
    updated_at: str
    synced_at: str

    def to_dict(self) -> dict[str, object]:
        """Return a flat dict keyed by database column names.

        Returns:
            A plain dictionary representation of this dataclass suitable
            for passing to database query functions.
        """
        return asdict(self)
