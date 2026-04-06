# Gmail Tool — Issues

Findings from code review on 2026-03-23. Critical and high severity issues were fixed inline. Medium and low severity issues are documented here for future work.

---

## Open

### L7: `google.generativeai` package is deprecated

**File:** `extractor.py:32`

The `google.generativeai` package shows a `FutureWarning` recommending migration to `google.genai`. The old package will stop receiving updates.

**Fix:** Migrate to `google.genai` SDK. This affects the constructor, `configure()`, and `GenerativeModel` usage patterns.

---

## Resolved (2026-04-02)

### Service init guard missing in client.\_execute() — FIXED

**File:** `client.py`

`self._service` is initialized to `None` in `__init__` but `_execute()` dereferenced it without checking, raising `AttributeError: 'NoneType' object has no attribute 'users'()` if any API method was called before `authenticate()`. The error message gave no indication that authentication was the cause.

Fixed (2026-04-02): Added a `None` check at the top of `_execute()` that raises `RuntimeError("Must call authenticate() before making API requests.")`. Test added in `tests/gmail/test_client.py`.

---

## Resolved (2026-03-30)

### M1: Expired decision cache entries never cleaned up

**File:** `cli.py`

`delete_expired_cache()` exists in `db/queries.py` but was never called. Fixed by calling it at the start of `cmd_collect()` before the collection run begins.

---

### M2: Filename collision when subjects differ only after 80 characters

**File:** `output.py`

Added collision detection in `write_email_file()` — appends a counter suffix (`_1`, `_2`, ...) when the target file already exists.

---

### M3: Label cache has no TTL or invalidation

**File:** `client.py`

Added a 1-hour TTL (`_LABEL_CACHE_TTL_SECONDS = 3600.0`) to the label cache in `GmailClient`. The entire cache is discarded when the TTL elapses so stale label IDs do not persist.

---

### M4: `GeminiExtractor` silently catches all exceptions

**File:** `extractor.py`

Now catches only the expected error types (`ValueError`, `AttributeError`, `RuntimeError`, `OSError`) and logs them as warnings. All other exceptions are re-raised so callers can see auth failures, SDK bugs, etc.

---

### M5: HTML cleaning regexes bypassable

**File:** `cleaner.py`

Replaced the pure-regex tracking pixel removal with a tag-scanning approach using `re.sub` with a callback function. The new `_attr_value_is_one()` helper handles single quotes, unquoted attributes, and numerically-equal strings like `"01"`.

---

### M6: Retry logic ignores HTTP `Retry-After` header

**File:** `client.py`

`_retry_with_backoff()` now reads the `Retry-After` response header and sleeps for `max(retry_after, exponential_delay)` seconds.

---

### M7: No end-to-end integration tests

**File:** `tests/gmail/test_processor.py`

Added `TestCollectionIntegration` class with four realistic multi-step scenarios: full pipeline with DB verification, force mode reprocessing, append mode accumulation, and dry-run producing no side effects.

---

### M8: Incomplete test coverage for `authenticate()` method

**File:** `tests/gmail/test_client.py`

Added `TestGmailClientAuthenticate` with four tests covering: valid token loading, expired token refresh, browser flow when no token exists, and `FileNotFoundError` when credentials file is missing.

---

### M9: Rate limiting methods untested

**File:** `tests/gmail/test_client.py`

Added `TestGmailClientRateLimit` and `TestGeminiExtractorRateLimit` classes. Both test three cases: no sleep on first call, correct sleep duration when within the minimum interval, and no-op when rate limit is disabled (rpm=0).

---

### L1: Credentials path resolved relative to CWD

**File:** `config.py`

`load_config()` now resolves relative `credentials_path` and `token_path` values to absolute paths using `Path.cwd()` at config load time.

---

### L2: Inconsistent timestamp formats across modules

**File:** `processor.py`

Added `_utc_now_iso()` helper function. Replaced inline `datetime.now(tz=UTC).isoformat()` calls with it in `_process_single_email()`.

---

### L3: No logging of successfully applied actions

**File:** `processor.py`

Added `logger.debug("Action '%s' applied to %s", action, message_id)` after each successful action in `_apply_actions`.

---

### L4: `_parse_email_address()` is defined but never called

**File:** `models.py`

`ProcessedEmailLocal.from_message()` now calls `_parse_email_address()` to extract the bare email address from the raw `From` header before storing it in `from_address`.

---

### L5: `--save-config` help text doesn't explain it overrides other commands

**File:** `cli.py`

Updated help text to: `"Write a default example configuration file to PATH and exit (overrides other commands)."`.

---

### L6: Transaction boundary documentation missing on query functions

**File:** `db/queries.py`

Added a "Transaction boundaries" section to the module docstring explaining that callers manage `commit()`.

---

### L8: Missing `get_raw_message()` empty response validation in tests

**File:** `tests/gmail/test_client.py`

Added `TestGmailClientGetRawMessageMissingField` with a test verifying that `ValueError` is raised when the API response lacks the `raw` field.

---

### Migration parsing improvement

**File:** `db/schema.py`

Replaced the manual statement-splitting loop in `run_migrations()` with `conn.executescript()`, which handles multi-statement SQL files correctly in a single implicit transaction.

---

### `_strip_frontmatter` renamed to `strip_frontmatter`

**File:** `llms.py`

Renamed `_strip_frontmatter` to `strip_frontmatter` (public API). Updated all internal callers and the test file.

---

### `_VERSION` uses dynamic version lookup

**File:** `cli.py`

Replaced hardcoded `_VERSION = "0.1.0"` with a `_get_version()` function that reads the installed package version via `importlib.metadata.version("deep-thought")` with a `PackageNotFoundError` fallback to `"0.0.0-dev"`.
