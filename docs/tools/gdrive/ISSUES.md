# GDrive Tool — Issues

## Open

No open issues.

---

## Resolved (2026-04-04)

### Skipped files not persisted to database — FIXED

**File:** `uploader.py` (~line 168)

When a file's mtime was unchanged, the skip branch incremented `backup_result.skipped` but never called `mark_file_status()`. The file's `status` in `backed_up_files` remained whatever it was set to on the last upload or update run, so `gdrive status` could not accurately report which files were evaluated on a given run.

**Trade-off considered:** Writing a `"skipped"` DB row on every unchanged file adds one `UPDATE` per file per run. For very large source directories this adds latency proportional to directory size. The alternative (documenting the behavior and leaving the DB stale) was rejected because it makes `gdrive status` unreliable as a post-run health check.

Fixed (2026-04-04): Added `mark_file_status(db_conn, relative_file_path, "skipped")` and `db_conn.commit()` in the skip branch of `run_backup()` in `uploader.py`. Test `test_unchanged_mtime_is_skipped` updated to assert `record.status == "skipped"` after the second run.

---

### `upload_file` used string split to extract filename — FIXED

**File:** `client.py` (line 192)

`local_path.split("/")[-1]` was used to extract the filename when constructing Drive file metadata. This works on macOS but is fragile on Windows paths and inconsistent with `pathlib.Path` usage elsewhere in the codebase.

Fixed (2026-04-04): Replaced with `Path(local_path).name`. Added `from pathlib import Path` import to `client.py`.
