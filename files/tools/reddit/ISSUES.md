# Reddit Tool — Issues

Outstanding issues from the 2026-03-23 code review. Critical and high severity issues were resolved in the same review cycle.

## Resolved (2026-03-23)

| ID   | Severity | File            | Issue                                                                                                                                                                     | Resolution                                                                             |
| ---- | -------- | --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| R-01 | High     | `db/queries.py` | `INSERT OR REPLACE` destroys `created_at` on re-process                                                                                                                   | Replaced with `INSERT ... ON CONFLICT(state_key) DO UPDATE SET` excluding `created_at` |
| R-02 | High     | `cli.py`        | DB writes never committed — `connection.close()` without `connection.commit()` silently discards all records                                                              | Added `connection.commit()` before `connection.close()` in `cmd_collect`               |
| R-03 | High     | `db/schema.py`  | `get_data_dir()` env var path missing `/reddit` subdirectory — `DEEP_THOUGHT_DATA_DIR` returns path directly without appending `/reddit`, inconsistent with fallback path | Changed to `Path(env_override) / "reddit"`                                             |
| R-04 | High     | `output.py`     | `_get_comment_depth` only returns 0 or 1 — all replies deeper than one level render at depth=1, losing thread structure                                                   | Implemented parent-chain traversal via `comment_lookup` dict with safety cap of 10     |

## Open — Medium

### M-01: Duplicate `_slugify_title` function across modules

- **File:** `models.py` (line ~32), `output.py` (line ~23)
- Both modules define `_slugify_title` with identical logic but different `max_length` defaults (80 in models.py, 60 in output.py). Changes to one are easily missed in the other.
- **Recommendation:** Extract to a shared utility module (e.g., `utils.py`) with a single `slugify_title(title, max_length)` function.

### M-02: Duplicate `_get_author_name` function across modules

- **File:** `models.py` (line ~15), `output.py` (line ~42)
- Both modules define `_get_author_name`. The implementations are slightly different (models.py checks `hasattr` then `name`, output.py uses `getattr` and `str()`).
- **Recommendation:** Consolidate into a single shared function.

### M-03: Cross-module import of private `_slugify_title`

- **File:** `processor.py` (line ~43), `llms.py` (line ~42)
- Both import `_slugify_title` from `output.py`. The `_` prefix indicates a private function; linters flag this.
- **Recommendation:** Make it public (`slugify_title`) or move to a shared utility module (see M-01).

### M-04: No `validate_config` call before collection in `cmd_collect`

- **File:** `cli.py` (lines ~171-196)
- `cmd_config` validates configuration, but `cmd_collect` does not. Invalid config values (e.g., bad sort order, negative limits) can reach the processor.
- **Recommendation:** Call `validate_config` after `_load_config_from_args` in `cmd_collect` and abort if issues are found.

### M-05: Migration SQL splitting is fragile

- **File:** `db/schema.py` (lines ~186-195)
- Comment stripping (`--` prefix) and statement splitting (`;`) are naive. Would break on semicolons or `--` inside string literals.
- **Recommendation:** Use `conn.executescript()` or document the constraint for migration authors.

### M-06: YAML frontmatter `url` value is not quoted

- **File:** `output.py` (line ~127)
- URLs containing `:`, `#`, or other YAML-special characters are written unquoted. While `title` is properly quoted, `url` is not.
- **Recommendation:** Quote the url value or use a YAML serializer for all frontmatter fields.

### M-07: `_PROJECT_ROOT` in config.py uses fragile parent traversal

- **File:** `config.py` (line ~46)
- `Path(__file__).parent.parent.parent.parent` assumes exact directory depth. Fragile to refactoring. Note that `db/schema.py` already uses the safer `pyproject.toml` walk-up approach.
- **Recommendation:** Use the same `pyproject.toml` walk-up approach as `db/schema.py`, or extract a shared utility.

### M-08: No `conn.commit()` in write query functions

- **File:** `db/queries.py`
- `upsert_collected_post`, `delete_all_posts`, and `delete_posts_by_rule` execute writes but never call `conn.commit()`. Caller responsibility is undocumented.
- **Recommendation:** Document caller commit responsibility or add commits to write functions.

### M-09: `_strip_frontmatter` does not handle `---` inside content

- **File:** `llms.py` (lines ~27-50)
- Searches for closing `---` starting from line 1 and takes the first found. Content containing `---` on a line would truncate prematurely.
- **Recommendation:** Low risk given controlled frontmatter generation. Add a comment acknowledging the limitation.

### M-10: LLM file naming uses leading dot (hidden on Unix)

- **File:** `llms.py`
- Files named `.llms.txt` / `.llms-full.txt` (leading dot). The requirements show `llms.txt` without a leading dot.
- **Recommendation:** Align implementation with requirements or update requirements.

## Open — Low

### L-01: `_VERSION` hardcoded rather than read from package metadata

- **File:** `cli.py` (line ~36)
- Version `"0.1.0"` is hardcoded. Could drift from `pyproject.toml`.
- **Recommendation:** Use `importlib.metadata.version()` when the tool matures.

### L-02: `_get_author_name` in models.py accesses `.name` attribute

- **File:** `models.py` (line ~19)
- Uses `getattr(submission.author, "name", str(submission.author))` which may fail if `submission.author` has no `.name` — would fall back to `str()` which triggers a PRAW API call.
- **Recommendation:** Use `str(submission.author)` directly, consistent with output.py's approach.

### L-03: `count_words` in output.py uses `len(text.split())`

- **File:** `output.py` (line ~81)
- `text.split()` already omits empty strings, so the implementation is correct. However, markdown syntax tokens (e.g., `#`, `**`, `---`) are counted as words.
- **Recommendation:** Acceptable for estimation purposes. No change needed.

### L-04: `_handle_save_config` does not honour `--force` flag

- **File:** `cli.py` (lines ~363-364)
- Error message says "Use --force to overwrite" but the function does not check `args.force` (it only receives the path string).
- **Recommendation:** Either remove the --force suggestion from the error message, or pass and check the force flag.

### L-05: `format_duration` in llms.py drops seconds for durations >= 1 hour

- **File:** `llms.py`
- A 1h 30s recording displays as "1h 0m". Acceptable for display purposes.

## Open — Test Coverage

### T-01: No test file for `db/queries.py`

`upsert_collected_post`, `get_collected_post`, `get_posts_by_rule`, `delete_all_posts`, `set_key_value` — all untested directly. Only exercised indirectly via processor tests.

### T-02: No test file for `db/schema.py`

`get_data_dir`, `get_database_path`, `initialize_database`, `run_migrations` — directory creation, migration application, and pragma setup untested.

### T-03: No test file for `client.py`

`RedditClient`, `get_submissions`, `get_comments`, `_flatten_comment_tree` — PRAW wrapper logic including recursion depth/count limits untested.

### T-04: No test file for `llms.py`

`write_llms_index`, `write_llms_full`, `write_post_llms_files`, `_strip_frontmatter` — LLM context file generation entirely untested.

### T-05: No tests for `cmd_collect` integration path

- **File:** `test_cli.py`
- `cmd_collect` (the primary user-facing command) has no tests. Database commit, error exit codes, and partial failure handling are unexercised.

### T-06: No tests for `_get_comment_depth` parent-chain traversal

- **File:** `test_output.py`
- The newly implemented depth calculation via `comment_lookup` has no tests. Only the rendering of comments at depth 0 and 1 is tested.

### T-07: No tests for `_render_comments_section` with nested comments

- **File:** `test_output.py`
- Comment rendering tests cover individual comments at depth 0 and 1, but the section-level function with multiple nested comments is untested.
