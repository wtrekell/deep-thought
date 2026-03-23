# Gmail Tool — Issues

Findings from code review on 2026-03-23. Critical and high severity issues were fixed inline. Medium and low severity issues are documented here for future work.

---

## Medium Severity

### M1: Expired decision cache entries never cleaned up

**File:** `processor.py` (entire codebase)

`delete_expired_cache()` exists in `db/queries.py` but is never called. Expired cache entries accumulate indefinitely, growing the database over time.

**Fix:** Call `delete_expired_cache(db_conn)` once per collection run at the start of `cmd_collect()` or inside `run_collection()`.

---

### M2: Filename collision when subjects differ only after 80 characters

**File:** `models.py:26-42`, `output.py:162-163`

`_slugify_subject()` truncates to 80 characters. Two emails with subjects identical up to that point produce the same filename and overwrite each other.

**Fix:** Add collision detection in `write_email_file()` — append a counter suffix (`_1`, `_2`) when the target file already exists.

---

### M3: Label cache has no TTL or invalidation

**File:** `client.py` (`get_or_create_label`)

The label name-to-ID cache lives for the entire client lifetime. If a label is deleted from Gmail during a long-running operation, the cached ID becomes invalid. Two concurrent processes may also fight over label creation.

**Fix:** Add a TTL (e.g., 1 hour) to the label cache or clear it between rules.

---

### M4: GeminiExtractor silently catches all exceptions

**File:** `extractor.py:84-90`

The `extract()` method catches `Exception` and returns an empty string. This masks auth failures, invalid model names, and network errors. Callers cannot distinguish "no content" from "API completely broken."

**Fix:** Catch specific expected exceptions (generation errors, rate limits) and re-raise unexpected ones.

---

### M5: HTML cleaning regexes are bypassable

**File:** `cleaner.py:30-110`

Tracking pixel removal only matches `width="1" height="1"` with double quotes in a specific order. Doesn't handle single quotes, `width=1` (unquoted), or values like `width="01"`. Unsubscribe section regex also has gaps.

**Fix:** Replace regex-based cleaning with a proper HTML parser (e.g., `beautifulsoup4`).

---

### M6: Retry logic ignores HTTP `Retry-After` header

**File:** `client.py:28, 66-74`

When Gmail returns 429 with a `Retry-After` header specifying a longer wait, the code ignores it and retries with a fixed 1s/2s/4s backoff. This almost guarantees subsequent failures.

**Fix:** Parse `Retry-After` from the HTTP response and use `max(retry_after, exponential_delay)`.

---

### M7: No end-to-end integration tests

**File:** All test files

The test suite has no integration tests covering the full pipeline: email collection -> database storage -> markdown output -> LLM file generation. Force mode and append mode are only tested in isolation.

**Fix:** Add a `TestCollectionIntegration` class with realistic multi-step scenarios using in-memory DB and mock client.

---

### M8: Incomplete test coverage for `authenticate()` method

**File:** `test_client.py`

The OAuth flow (`authenticate()`) is untested. No tests for token loading, token refresh, browser flow, or `FileNotFoundError` on missing credentials.

**Fix:** Add tests using mocked `Credentials.from_authorized_user_file()`, `InstalledAppFlow`, and file operations.

---

### M9: Rate limiting methods untested

**File:** `test_client.py`, `test_extractor.py`

`GmailClient._rate_limit()` and `GeminiExtractor._rate_limit()` have zero test coverage. Rate limit enforcement could silently fail.

**Fix:** Add tests with mocked `time.time()` and `time.sleep()` verifying delay calculation.

---

## Low Severity

### L1: Credentials path resolved relative to CWD

**File:** `client.py:116, 150`

Relative credential paths (e.g., `src/config/gmail/credentials.json`) resolve against the current working directory, not the project root. Running the CLI from a different directory causes confusing path failures.

**Fix:** Resolve relative paths to absolute at config load time using `_PROJECT_ROOT`.

---

### L2: Inconsistent timestamp formats across modules

**File:** `processor.py:60, 238, 221`

Timestamps use three different formats: `%Y-%m-%dT%H%M%S` (snapshots), `%Y-%m-%d` (filenames), `.isoformat()` (database). Not a bug but hurts maintainability.

**Fix:** Create a shared `_utc_now_iso()` helper for the ISO format and keep the others only where the specific format is intentional.

---

### L3: No logging of successfully applied actions

**File:** `processor.py:94-128`

`_apply_actions` logs failures (warnings) but not successes. Users cannot verify which actions were applied without reading database records.

**Fix:** Add `logger.debug("Action '%s' applied to %s", action, message_id)` after each successful action.

---

### L4: `_parse_email_address()` is defined but never called

**File:** `models.py:68-84`

The helper function to extract just the email address from a From header exists but is unused. `from_address` in `ProcessedEmailLocal` stores the full raw header instead.

**Fix:** Either call it in `from_message()` or remove the dead code.

---

### L5: `--save-config` help text doesn't explain it overrides other commands

**File:** `cli.py:352-357`

Users might expect `--save-config` to combine with subcommands. It actually exits early, silently ignoring any subcommand.

**Fix:** Update help text: `"Write a default example configuration file to PATH and exit (overrides other commands)."`.

---

### L6: Transaction boundary documentation missing on query functions

**File:** `db/queries.py` (all functions)

Query functions execute SQL without calling `commit()`. The caller (`cli.py`) manages transactions, but this contract is implicit. Future callers could lose data by forgetting to commit.

**Fix:** Add a note to the module docstring explaining that callers manage transaction boundaries.

---

### L7: `google.generativeai` package is deprecated

**File:** `extractor.py:32`

The `google.generativeai` package shows a `FutureWarning` recommending migration to `google.genai`. The old package will stop receiving updates.

**Fix:** Migrate to `google.genai` SDK. This affects the constructor, `configure()`, and `GenerativeModel` usage patterns.

---

### L8: Missing `get_raw_message()` empty response validation in tests

**File:** `test_client.py`

No test validates the behavior when `get_raw_message()` receives a response without a `raw` field (now raises `ValueError` after fix). The new validation path is untested.

**Fix:** Add a test case with a mock response missing the `raw` key.
