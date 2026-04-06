# Reddit Tool — Issues

Outstanding issues from the 2026-03-23 code review. Critical and high severity issues were resolved in the same review cycle.

## Closed — Won't Fix

### L-03: `count_words` in output.py uses `len(text.split())`

- **File:** `output.py` (line ~81)
- `text.split()` already omits empty strings, so the implementation is correct. However, markdown syntax tokens (e.g., `#`, `**`, `---`) are counted as words.
- **Rationale:** Acceptable for estimation/display purposes. No change planned.

### L-05: `format_duration` in llms.py drops seconds for durations >= 1 hour

- **File:** `llms.py`
- A 1h 30s recording displays as "1h 0m". Acceptable for display purposes.
- **Rationale:** Acceptable for estimation/display purposes. No change planned.

## Resolved (2026-04-02)

| ID   | Severity | File                       | Issue                                                                                                                                                                              | Resolution                                                                                                                                                                                                                                                                                   |
| ---- | -------- | -------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| M-11 | Medium   | `config.py`                | Rule names not validated for filesystem safety — a rule name containing path separators or traversal sequences could escape the output directory when used as a subdirectory path. | Added `_SAFE_RULE_NAME_PATTERN` validation in `validate_config()`: rule names must match `^[a-zA-Z0-9_-]+$`. Error raised at config load time.                                                                                                                                               |
| M-12 | Medium   | `image_extractor.py` (new) | include_images config flag parsed and stored but never acted on — no image download code existed.                                                                                  | Implemented `image_extractor.py`: downloads direct image links (jpg/png/gif/webp/jpeg) to `img/` subdirectory, rewrites markdown references to local paths, handles failures gracefully. Called from `processor.py` after `write_post_file()` when `include_images` is True and not dry-run. |
| M-13 | Low      | `utils.py`                 | `slugify_title()` implemented independently in reddit/utils.py; diverged from web tool's implementation.                                                                           | `slugify_title()` now delegates to `deep_thought.text_utils.slugify` (shared canonical implementation). Behavior preserved; `max_length=80` passed explicitly.                                                                                                                               |

## Resolved (2026-04-01)

| ID   | Severity | File                        | Issue                                                                                                                                                                                                                                                                                | Resolution                                                                                                                                                                                                                       |
| ---- | -------- | --------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| H-01 | High     | `processor.py`              | No retry or backoff on 429 — all subsequent rules fail instantly after rate limit is hit. Secondary bug caught in code review: `rate_limited` was initially set on every 429 (not just final failure), causing the inter-rule cooldown to trigger on recoverable rate limits.        | Added exponential backoff retry (up to 3 attempts) on `TooManyRequests` in `process_rule`, plus 60s inter-rule cooldown in `run_collection` when rate limited. `rate_limited` flag corrected to set only on final retry failure. |
| H-02 | High     | `client.py`, `processor.py` | Per-post 429s during comment fetching were swallowed silently — `get_comments()` caught `TooManyRequests` in a broad `except Exception`, so the rate limit was invisible to the orchestration layer. The next post was tried immediately, exhausting the budget for the entire rule. | `get_comments()` now re-raises `TooManyRequests`; `process_rule()` catches it specifically, sleeps with backoff before the next post, and sets `rate_limited = True` to trigger the inter-rule cooldown.                         |

## Resolved (2026-03-30)

| ID   | Severity | File                      | Issue                                                        | Resolution                                                                                                                                  |
| ---- | -------- | ------------------------- | ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------- |
| M-01 | Medium   | `models.py`, `output.py`  | Duplicate `_slugify_title` across modules                    | Extracted to `utils.py` as `slugify_title(title, max_length=80)`. Both modules now import from there.                                       |
| M-02 | Medium   | `models.py`, `output.py`  | Duplicate `_get_author_name` across modules                  | Extracted to `utils.py` as `get_author_name(author_object)`. Both modules now import from there.                                            |
| M-03 | Medium   | `processor.py`, `llms.py` | Cross-module import of private `_slugify_title`              | Both modules updated to import `slugify_title` from `utils.py`; `# noqa` comments removed.                                                  |
| M-04 | Medium   | `cli.py`                  | No `validate_config` call before collection in `cmd_collect` | Added `validate_config` call after `_load_config_from_args`; exits with code 1 and prints each issue to stderr if invalid.                  |
| M-05 | Medium   | `db/schema.py`            | Migration SQL splitting fragile                              | Replaced comment-stripping + manual split with `conn.executescript()`. `_set_schema_version` and `conn.commit()` called after.              |
| M-06 | Medium   | `output.py`               | YAML frontmatter `url` value not quoted                      | URL now written as `url: "..."` with `"` encoded as `%22`.                                                                                  |
| M-07 | Medium   | `config.py`               | `_PROJECT_ROOT` fragile parent traversal                     | Not present in `config.py`; the fragile traversal was only in `db/schema.py`, which already uses pyproject.toml walk-up. No change needed.  |
| M-08 | Medium   | `db/queries.py`           | No `conn.commit()` docs in write query functions             | Added module-level docstring: "Callers are responsible for committing transactions."                                                        |
| M-09 | Medium   | `llms.py`                 | `_strip_frontmatter` does not handle `---` inside content    | Added docstring comment acknowledging the limitation. Low risk given controlled frontmatter generation.                                     |
| M-10 | Medium   | `llms.py`                 | LLM file naming uses leading dot                             | Renamed `.llms.txt` / `.llms-full.txt` to `-llms.txt` / `-llms-full.txt` in `write_post_llms_files`.                                        |
| L-01 | Low      | `cli.py`                  | `_VERSION` hardcoded                                         | Replaced with `_get_version()` using `importlib.metadata.version("deep-thought")` with fallback to `"0.1.0"`.                               |
| L-02 | Low      | `models.py`               | `_get_author_name` accesses `.name` attribute                | Consolidated into shared `utils.get_author_name(author_object)` which uses `str()` directly. `models.py` passes `submission.author`.        |
| L-04 | Low      | `cli.py`                  | `_handle_save_config` doesn't honour `--force`               | Removed the misleading "Use --force to overwrite" suggestion from the error message. User must remove the file manually.                    |
| T-01 | Test     | —                         | No test file for `db/queries.py`                             | Created `tests/reddit/test_queries.py` covering upsert, get, delete, key-value functions with in-memory SQLite.                             |
| T-02 | Test     | —                         | No test file for `db/schema.py`                              | Created `tests/reddit/test_schema.py` covering `get_data_dir`, `initialize_database`, `run_migrations`, idempotency.                        |
| T-03 | Test     | —                         | No test file for `client.py`                                 | Created `tests/reddit/test_client.py` covering `RedditClient`, `get_submissions` sort routing, `_flatten_comment_tree`.                     |
| T-04 | Test     | —                         | No test file for `llms.py`                                   | Created `tests/reddit/test_llms.py` covering `strip_frontmatter`, `generate_llms_index`, `generate_llms_full`, file writing.                |
| T-05 | Test     | `test_cli.py`             | No tests for `cmd_collect` integration path                  | Added `TestCmdCollect` with 7 tests: summary output, DB commit, DB close-on-error, exit codes 1/2, config validation abort, dry-run prefix. |
| T-06 | Test     | `test_output.py`          | No tests for `_get_comment_depth` parent-chain traversal     | Added `TestGetCommentDepth` with 6 tests covering depth 0-3, safety cap at 10, missing-parent termination.                                  |
| T-07 | Test     | `test_output.py`          | No tests for `_render_comments_section` with nested comments | Added `TestRenderCommentsSection` with 6 tests covering empty, single, nested, multiple top-level, and deep nesting.                        |

## Resolved (2026-03-23)

| ID   | Severity | File            | Issue                                                                                                                                                                     | Resolution                                                                             |
| ---- | -------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| R-01 | High     | `db/queries.py` | `INSERT OR REPLACE` destroys `created_at` on re-process                                                                                                                   | Replaced with `INSERT ... ON CONFLICT(state_key) DO UPDATE SET` excluding `created_at` |
| R-02 | High     | `cli.py`        | DB writes never committed — `connection.close()` without `connection.commit()` silently discards all records                                                              | Added `connection.commit()` before `connection.close()` in `cmd_collect`               |
| R-03 | High     | `db/schema.py`  | `get_data_dir()` env var path missing `/reddit` subdirectory — `DEEP_THOUGHT_DATA_DIR` returns path directly without appending `/reddit`, inconsistent with fallback path | Changed to `Path(env_override) / "reddit"`                                             |
| R-04 | High     | `output.py`     | `_get_comment_depth` only returns 0 or 1 — all replies deeper than one level render at depth=1, losing thread structure                                                   | Implemented parent-chain traversal via `comment_lookup` dict with safety cap of 10     |
