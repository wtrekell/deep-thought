# Reddit Tool — Changelog

All notable changes to the Reddit Tool will be documented in this file.

---

## [0.1.3] — 2026-04-01

### Added

- Per-post rate-limit handling in `process_rule()`: a specific `except prawcore.exceptions.TooManyRequests` clause now fires before the generic per-post error handler. When a 429 hits during comment fetching, the tool sleeps for the `Retry-After` duration (or 10s base backoff), sets `result.rate_limited = True` to trigger the inter-rule cooldown, and counts the post as an error so it is retried on the next run.
- `get_comments()` in `client.py` now re-raises `TooManyRequests` instead of swallowing it with a generic warning, so rate-limit events are visible to the orchestration layer. Non-429 errors from `replace_more()` retain the existing warn-and-continue behaviour.
- `import prawcore.exceptions` added to `client.py`.
- Tests: `TestGetComments` in `test_client.py` (propagation and non-429 fallback); `TestProcessRulePerPostRateLimit` in `test_processor.py` (flag, sleep value, error count, continuation).

## [0.1.2] — 2026-04-01

### Added

- `rate_limited: bool` field on `CollectionResult` (default `False`); set to `True` only on final retry failure, not on transient 429s.
- Retry logic in `process_rule()`: `get_submissions` retried up to 3 times on `TooManyRequests` with exponential backoff (10s, 20s, 40s) or the `Retry-After` header value when present.
- Inter-rule cooldown in `run_collection()`: sleeps 60s before the next rule when the previous rule's `rate_limited` flag is set.
- `_get_retry_delay(retry_after, attempt)` helper encapsulates backoff calculation; accepts `retry_after: str | None` directly rather than the raw exception, keeping the function independent of prawcore's type stubs.
- Tests covering retry behaviour, `_get_retry_delay`, and the inter-rule cooldown.

### Fixed

- `_build_output_path()` date format corrected from `%Y-%m-%d` / `_` separator to `%y%m%d` / `-` separator, matching the `YYMMDD-` prefix used by `write_post_file()`.
- `rate_limited` flag now set only on final retry failure; previously set on every 429, which incorrectly triggered the inter-rule cooldown on recoverable rate limits.
- URL YAML escaping in `output.py` frontmatter changed from `%22` to `\"` to match the escaping already applied to the title field.
- `2**attempt` changed to `2.0**attempt` in `_get_retry_delay` so mypy strict mode can verify the `float` return type (`int.__pow__(int)` is typed as `Any` due to negative-exponent ambiguity).

## [0.1.1] — 2026-03-30

### Changed

- Standardized export filename date prefix from `YYYY-MM-DD_` to `YYMMDD-` (e.g., `260322-abc123_post-title.md`).
- Renamed `requirements.md` to `260322-requirements.md` to follow repository naming convention.

## [0.1.0] — 2026-03-22

### Added

- Initial implementation: rule-based collection from subreddits via PRAW
- SQLite state tracking with composite key (`post_id:subreddit:rule_name`)
- Incremental update detection via comment count comparison
- Configurable filtering: score, age, keywords, flair
- Markdown output with YAML frontmatter
- Optional `.llms.txt` / `.llms-full.txt` generation
- CLI entry point with `config`, `init`, `--dry-run`, `--force`, `--rule` support
