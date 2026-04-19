# Reddit Tool — Changelog

All notable changes to the Reddit Tool will be documented in this file.

---

## [Unreleased]

### Fixed

- `QdrantClient` created in `cmd_collect` is now closed explicitly in the `finally` block alongside the SQLite connection, eliminating the `RuntimeWarning: Unable to close http connection` that Qdrant's `__del__` emits at interpreter shutdown. Close failures are logged at DEBUG rather than surfaced to the user (#37).

### Changed

- Secret retrieval now checks macOS Keychain first, falling back to environment variables. Uses the shared `deep_thought.secrets` module.

## [0.1.5] — 2026-04-05

### Added

- `qdrant_collection` config option in `reddit-configuration.yaml`: name of the Qdrant collection to write embeddings to (default: `"deep_thought_db"`). Enables routing Reddit posts to a separate collection from other tools.

## [0.1.4] — 2026-04-03

### Added

- `permalink` field to YAML frontmatter: full Reddit thread URL (`https://reddit.com{submission.permalink}`). Previously the `url` field held only the external link target (e.g., a YouTube video URL), making it impossible to navigate back to the original thread without manually constructing the URL.
- `upvote_ratio` field to YAML frontmatter and SQLite `collected_posts` table: PRAW `float` representing the fraction of votes that are upvotes (e.g., `0.970`). DB migration `002_add_upvote_ratio.sql` adds the column (`REAL NOT NULL DEFAULT 0.0`) to existing databases. Also included in the Qdrant embedding payload.
- `exclude_stickied` rule filter (default `false`): when `true`, skips mod-pinned posts. Implemented in `filters.py` as `passes_stickied_filter()`.
- `exclude_locked` rule filter (default `false`): when `true`, skips locked posts. Locked posts cannot receive new comments, so the incremental update logic is wasted on them. Implemented in `filters.py` as `passes_locked_filter()`.
- `replace_more_limit` rule config (default `32`): controls how many `MoreComments` placeholder nodes PRAW expands per post. `0` restores the previous skip-all behaviour; `null` expands every node (unlimited API calls). Previously hardcoded to `0`, which silently dropped a large share of comments on high-activity posts. Threaded through `client.get_comments()` and both call sites in `processor.py`.

### Removed

- `generate_llms_files` config option and `llms.py` module. The option existed in config but was never wired into the processor — setting it to `true` silently had no effect. Removed to eliminate dead configuration surface. `llms.py` and `tests/reddit/test_llms.py` deleted.

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
