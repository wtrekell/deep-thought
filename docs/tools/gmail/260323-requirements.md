# Product Brief — Gmail Tool

## Name and Purpose

**Gmail Tool** — collects, processes, and optionally sends email via Gmail using OAuth 2.0. Rule-based collection applies Gmail search queries, optional Gemini AI extraction, and post-collection actions (archive, label, forward, delete). Supports append mode for incremental collection into running files.

## Sync Modes

1. **CLI Command** — `gmail` (entry point)
2. **Collect** — Fetch emails matching rule queries, run AI extraction, apply actions (default operation)
3. **Send** — Send an email composed from a markdown file with YAML frontmatter
4. **Auth** — Run or refresh the OAuth 2.0 browser flow

## Requirements

1. Python 3.12 using `uv` as the package manager.
2. **Google API Python Client** ([`google-api-python-client`](https://github.com/googleapis/google-api-python-client)) for Gmail API access. API reference: [Gmail API v1](https://developers.google.com/workspace/gmail/api/reference/rest/v1).
3. **Google Auth** ([`google-auth-oauthlib`](https://google-auth-oauthlib.readthedocs.io/), `google-auth-httplib2`) for OAuth 2.0.
4. **Google Generative AI** ([`google-generativeai`](https://ai.google.dev/gemini-api/docs)) for Gemini AI extraction.
5. **html2text** for newsletter HTML-to-text conversion.
6. SQLite for local state tracking (WAL mode, foreign keys enabled).
7. `credentials.json` (OAuth 2.0 client secret) — see [Google Cloud Setup](#google-cloud-setup) below.
8. `GEMINI_API_KEY` stored in `.env` or system environment (optional; required only for AI extraction). Loaded via `load_dotenv()`.
9. A changelog is maintained in `files/tools/gmail/CHANGELOG.md`.

## Google Cloud Setup

A one-time setup is required before the tool can authenticate:

1. Create a project in Google Cloud Console.
2. Enable the **Gmail API** for the project.
3. Configure the **OAuth consent screen** — set the user type to "External" (personal Gmail) or "Internal" (Workspace). Add the scopes listed below.
4. Create an **OAuth 2.0 Client ID** with application type **Desktop app**.
5. Download the resulting `credentials.json` into `src/config/gmail/`.

### Publishing Status and Token Expiry

Google Cloud projects default to **Testing** publishing status. In Testing mode, OAuth refresh tokens expire after **7 days**, requiring re-consent via `gmail auth`. To avoid this, publish the app to **Production** in the OAuth consent screen settings. For a single-user personal tool, Google does not require verification for Production status.

## OAuth 2.0 Scopes

The tool requests the following scope:

| Scope                      | Why                                                                                                                                                                                                |
| -------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `https://mail.google.com/` | Full Gmail access — required because the `delete` action permanently removes messages, which the narrower `gmail.modify` scope does not permit. Also covers read, send, label, archive, and trash. |

If the `delete` action is not needed, the scope can be narrowed to `https://www.googleapis.com/auth/gmail.modify` (read, send, label, archive, trash — but no permanent delete).

**Scope changes:** If scopes are changed after initial authorization, `token.json` must be deleted so the next `gmail auth` run triggers a new consent screen with the updated permissions.

## Data Storage

### State Database

Located at `data/gmail/gmail.db` by default; respects the `DEEP_THOUGHT_DATA_DIR` env var to redirect the data root at runtime.

- Table: `processed_emails` — columns: `message_id TEXT PRIMARY KEY`, `rule_name TEXT`, `subject TEXT`, `from_address TEXT`, `output_path TEXT`, `actions_taken TEXT`, `status TEXT`, `created_at TEXT`, `updated_at TEXT`, `synced_at TEXT`
- Table: `decision_cache` — columns: `cache_key TEXT PRIMARY KEY`, `decision TEXT`, `ttl_seconds INT`, `created_at TEXT`, `updated_at TEXT`
- Table: `key_value` — schema version tracking
- State key: Gmail message ID
- Use `INSERT OR REPLACE` for upsert operations
- Add indexes on `processed_emails.rule_name` and `decision_cache.created_at` for query performance
- Schema version tracked in a `key_value` table
- Migrations stored in `db/migrations/` with numeric prefixes

## Data Models

### ProcessedEmailLocal

| Field           | Type  | Description                                |
| --------------- | ----- | ------------------------------------------ |
| `message_id`    | `str` | Gmail message ID (primary key)             |
| `rule_name`     | `str` | Name of the rule that collected this email |
| `subject`       | `str` | Email subject line                         |
| `from_address`  | `str` | Sender address                             |
| `output_path`   | `str` | Path to the generated markdown file        |
| `actions_taken` | `str` | Serialized list of actions applied         |
| `status`        | `str` | Processing status (e.g., `ok`, `error`)    |
| `created_at`    | `str` | ISO 8601 timestamp of first collection     |
| `updated_at`    | `str` | ISO 8601 timestamp of last update          |
| `synced_at`     | `str` | ISO 8601 timestamp of last API sync        |

Methods: `from_message()` for Gmail API message dict conversion, `to_dict()` for database insertion.

### DecisionCacheLocal

| Field         | Type  | Description                                |
| ------------- | ----- | ------------------------------------------ |
| `cache_key`   | `str` | Cache key (primary key)                    |
| `decision`    | `str` | Serialized AI extraction decision          |
| `ttl_seconds` | `int` | Seconds until this cache entry expires     |
| `created_at`  | `str` | ISO 8601 timestamp of cache entry creation |
| `updated_at`  | `str` | ISO 8601 timestamp of last update          |

Methods: `to_dict()` for database insertion.

### CollectResult

| Field           | Type             | Description                                                                      |
| --------------- | ---------------- | -------------------------------------------------------------------------------- |
| `processed`     | `int`            | Number of emails successfully processed                                          |
| `skipped`       | `int`            | Number of emails skipped (already processed or filtered out)                     |
| `errors`        | `int`            | Number of emails that failed processing                                          |
| `actions_taken` | `dict[str, int]` | Count of each action type applied (e.g., `{"archive": 5, "label:Processed": 5}`) |

Printed to stdout on collect completion. Used to determine exit code (0 if `errors == 0`, 2 if `errors > 0`).

### SendResult

| Field        | Type  | Description                        |
| ------------ | ----- | ---------------------------------- |
| `message_id` | `str` | Gmail message ID of the sent email |
| `thread_id`  | `str` | Gmail thread ID                    |

Printed to stdout on send completion.

## Command List

Running `gmail` with no arguments shows help. Collect is the default operation — no subcommand required.

| Subcommand     | Description                                                                                                                                                                                                                                                                                                             |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `gmail config` | Validate and display current YAML configuration                                                                                                                                                                                                                                                                         |
| `gmail init`   | Create data directories (`data/gmail/`, `data/gmail/export/`, `data/gmail/input/`, `data/gmail/snapshots/`), generate a starter `gmail-configuration.yaml` if missing, and verify that `credentials.json` exists at the configured path                                                                                 |
| `gmail send`   | Send an email composed from a markdown file                                                                                                                                                                                                                                                                             |
| `gmail auth`   | Run the OAuth 2.0 Desktop app flow — opens a browser for consent on first run, refreshes the token silently on subsequent runs. Stores the resulting access + refresh token in `token.json`. Re-run after scope changes or token expiry (see [Publishing Status and Token Expiry](#publishing-status-and-token-expiry)) |

| Flag                 | Description                                                              |
| -------------------- | ------------------------------------------------------------------------ |
| `--config PATH`      | YAML configuration file (default: `src/config/gmail-configuration.yaml`) |
| `--output PATH`      | Output directory override                                                |
| `--max-emails INT`   | Max emails to process per run                                            |
| `--dry-run`          | Preview without taking actions or writing files                          |
| `--verbose`, `-v`    | Detailed logging                                                         |
| `--force`            | Clear state and reprocess                                                |
| `--save-config PATH` | Generate example config and exit                                         |
| `--version`          | Show version and exit                                                    |

### Send Subcommand

```
gmail send message.md
```

Accepts a positional path to the markdown file. If omitted, defaults to looking in `data/gmail/input/`. The markdown file must have a YAML frontmatter block with `to`, `subject`, and optionally `cc`, `bcc`.

## File & Output Map

```
files/tools/gmail/
├── 260323-requirements.md       # This document
└── CHANGELOG.md                 # Release history

src/deep_thought/gmail/
├── __init__.py
├── cli.py                       # CLI entry point (collect + send subcommands)
├── config.py                    # YAML config loader and rule validation
├── models.py                    # Local dataclasses for email processing state
├── processor.py                 # Rule engine, action dispatch, output orchestration
├── db/
│   ├── __init__.py
│   ├── schema.py                # Table creation and migration runner
│   ├── queries.py               # All SQL operations
│   └── migrations/
│       └── 001_init_schema.sql
├── filters.py                   # Post-fetch filtering: applies include/exclude logic on email metadata (sender, subject, labels) after Gmail query returns results but before database write
├── output.py                    # Markdown + YAML frontmatter generation
├── llms.py                      # .llms.txt / .llms-full.txt generation
├── client.py                    # Gmail API client wrapper (OAuth 2.0); collapses paginated list responses into flat lists
├── cleaner.py                   # Newsletter HTML cleaning (tracking pixels, scripts)
└── extractor.py                 # Gemini 2.5 Flash AI extraction

data/gmail/
├── gmail.db                     # SQLite state database
├── token.json                   # OAuth 2.0 access + refresh token (auto-managed, NEVER committed — contains sensitive refresh token)
├── input/                       # Default location for send input files
├── snapshots/                   # Raw JSON blobs per collect run (YYYY-MM-DDTHHMMSS.json)
└── export/                      # Generated markdown files

src/config/
├── gmail-configuration.yaml     # Tool configuration and rules
└── gmail/
    └── credentials.json         # OAuth 2.0 client secret (from Google Cloud Console)
```

## Configuration

Configuration is stored in `src/config/gmail-configuration.yaml`. All values below are required unless marked optional.

```yaml
# Auth
credentials_path: "src/config/gmail/credentials.json"
token_path: "data/gmail/token.json"
scopes:
  - "https://mail.google.com/" # Use 'gmail.modify' if permanent delete is not needed

# Gemini AI
gemini_api_key_env: "GEMINI_API_KEY"
gemini_model: "gemini-2.5-flash"
gemini_rate_limit_rpm: 15

# Gmail API
gmail_rate_limit_rpm: 250 # Gmail API default quota; lower to be conservative
retry_max_attempts: 3 # Retry failed Gmail API calls with exponential backoff
retry_base_delay_seconds: 1 # Initial delay doubles on each retry

# Collection
max_emails_per_run: 100
clean_newsletters: true # Strip tracking pixels, social buttons (50-70% reduction)
decision_cache_ttl: 3600 # Seconds to cache AI extraction decisions

# Output
output_dir: "data/gmail/export/"
generate_llms_files: false # Set true to generate .llms.txt / .llms-full.txt files
flat_output: false # true = all files in one directory

rules:
  - name: "newsletters"
    query: "label:newsletter"
    ai_instructions: "Extract the main content and key takeaways. Ignore promotional sections."
    actions:
      - archive
      - label:Processed
    append_mode: true # Append to existing file rather than create new

  - name: "receipts"
    query: "subject:receipt OR subject:invoice newer_than:7d"
    ai_instructions: "Extract order number, total, merchant, and item list."
    actions:
      - archive
      - label:Receipts
    append_mode: false

  - name: "readwise"
    query: "label:newsletter -label:Forwarded newer_than:7d"
    ai_instructions: null # No AI extraction — forward only
    actions:
      - forward:yourname@feed.readwise.io
      - label:Forwarded
      - archive
    append_mode: false
```

### Available Actions

| Action                | Description                                                                                                   |
| --------------------- | ------------------------------------------------------------------------------------------------------------- |
| `archive`             | Remove from inbox (add `ARCHIVE` label)                                                                       |
| `label:{name}`        | Apply a Gmail label                                                                                           |
| `remove_label:{name}` | Remove a Gmail label                                                                                          |
| `forward:{address}`   | Forward email to address (e.g., Readwise Reader). See [Forward Implementation](#forward-implementation) below |
| `mark_read`           | Mark email as read                                                                                            |
| `trash`               | Move to Gmail Trash                                                                                           |
| `delete`              | Permanently delete (bypasses Trash — requires `https://mail.google.com/` scope)                               |

### Per-rule Fields

| Field                | Type     | Default        | Description                                                                                                                                                                                                                                                                                                                                                                              |
| -------------------- | -------- | -------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `save_mode`          | string   | `"individual"` | Output mode. One of `individual` (one markdown file per email), `append` (all emails appended to `{rule_name}.md` with `---` separators and frontmatter), `both` (individual + append), `none` (no file written; actions still apply), or `raw` (bare AI output written to `{rule_name}.txt` with line-level dedup — no frontmatter or markdown; intended for handoff to other tools).   |
| `include_spam_trash` | bool     | `false`        | When `true`, the Gmail API is called with `includeSpamTrash=True`, which surfaces messages in Trash and Spam. Required for any query that targets `in:trash` or `in:spam` (e.g., a scheduled cleanup rule that deletes trashed mail older than two weeks). Leave at `false` for collection rules — enabling it will include trashed/spammed mail in normal output.                       |

`raw` note: when `ai_instructions` is `null`, `raw` writes the cleaned email body verbatim — typically not useful. Combine `raw` with explicit `ai_instructions` that produce line-oriented output (one URL per line, one line-item per line, etc.). Embeddings are not written for `raw` rules. The `.txt` extension is deliberate to signal the output is not markdown.

### Forward Implementation

The `forward:{address}` action must preserve the original email without mangling HTML, inline images, or attachments. To achieve this:

1. Fetch the message with `format='raw'` to get the full RFC 2822 content as a base64url-encoded blob.
2. Decode with Python's `email` library (which preserves MIME structure without re-encoding).
3. Modify only routing headers: set `To` to the forward address, remove `DKIM-Signature` (which would fail validation after header changes), optionally strip `Cc`/`Bcc`.
4. Re-encode the modified message as base64url and send via `users().messages().send()`.

This keeps all MIME parts intact. Do **not** reconstruct the message from extracted text/HTML parts — that approach loses multipart boundaries and content-transfer encodings.

**Primary use case:** Forwarding newsletters to Readwise Reader (e.g., `forward:yourname@feed.readwise.io`). Reader expects unmodified emails; the raw forwarding technique ensures formatting is preserved.

## Data Format

### Markdown Output

```
data/gmail/export/{rule_name}/
├── {YYMMDD}-{subject_slug}.md           # Email content with YAML frontmatter
└── llm/
    ├── {YYMMDD}-{subject_slug}.llms.txt
    └── {YYMMDD}-{subject_slug}.llms-full.txt
```

In append mode, all emails for a rule accumulate in one file.

**Filename sanitization:** `{subject_slug}` is generated by lowercasing, replacing non-alphanumeric characters with hyphens, collapsing consecutive hyphens, stripping leading/trailing hyphens, and truncating to 80 characters. Only include metadata fields with non-null, non-empty values in the frontmatter.

### Frontmatter Schema

```markdown
---
tool: gmail
message_id: 18d4a3b2c1e0f9a8
rule: newsletters
from: "Newsletter <news@example.com>"
subject: "Weekly Digest"
date: "2026-03-15T09:00:00Z"
actions_taken:
  - archive
  - label:Processed
processed_date: 2026-03-18T10:00:00Z
---
```

### Send Message Frontmatter

```markdown
---
to: recipient@example.com
subject: "Following up on our meeting"
cc: manager@example.com
---

Email body here in markdown. Will be sent as plain text.
```

## Error Handling

- `Google API authentication errors` — caught at the client level; surfaces descriptive message and exits with code 1.
- `OAuth token refresh failures` — caught during client initialization; prompts user to re-run `gmail auth`.
- `Gemini API errors` — caught per-email during AI extraction; email is written without extracted content and a warning is logged.
- `Gmail action failures` (label, archive, delete) — caught per-email; action is skipped, failure recorded in `processed_emails.status`, processing continues.
- `Gmail API rate limit / transient errors` (HTTP 429, 500, 503) — retried with exponential backoff up to `retry_max_attempts` (default 3). Initial delay is `retry_base_delay_seconds`, doubling on each retry. Permanent failures (4xx other than 429) are not retried.
- Missing config file raises `FileNotFoundError`. Invalid config content raises `ValueError`. Missing required env vars raise `OSError`.
- Top-level `try/except` in CLI entry point catches all above and prints descriptive messages.
- Exit codes: `0` all items succeeded, `1` fatal error, `2` partial failure (some items errored)

## Testing

- Use in-memory SQLite for all database tests.
- Provide populated database fixtures with seed data (sample processed emails, cached decisions).
- Mock targets: `google-api-python-client`, `google-auth`, `google-generativeai` — use `MagicMock` for SDK objects.
- Create helper functions for building test email objects (e.g., `make_email(subject=..., from_address=..., labels=...)`).
- Test fixtures: sample email message objects covering plain text, HTML newsletters, and multipart MIME.
- Organize tests in classes by feature area (collection, AI extraction, actions, send, auth).
- Mark slow or network-dependent tests with `@pytest.mark.integration`.
- Mark error path tests with `@pytest.mark.error_handling`.
- Write docstrings on every test method.
- Test directory: `tests/gmail/` with `conftest.py` for shared fixtures
- Fixture data files stored in `tests/gmail/fixtures/`

## User Questions

_(None yet — record questions raised during requirements gathering and their answers here.)_

## Claude Questions

_(None yet — record questions Claude asked during planning and the decisions made here.)_

## Pre-Build Tasks

1. Create Google Cloud project and enable Gmail API
2. Configure OAuth consent screen and create Desktop app credential
3. Download `credentials.json` into `src/config/gmail/`
4. Publish app to Production to avoid 7-day token expiry
5. Add `GEMINI_API_KEY` to `.env` (if using AI extraction)
6. Verify `.gitignore` covers `token.json`, `credentials.json`, and `data/gmail/`
