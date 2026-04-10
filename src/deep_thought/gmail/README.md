# Gmail Tool

Rule-based email collection from Gmail with OAuth 2.0, optional AI extraction, and post-collection actions.

## Overview

The Gmail Tool authenticates with Gmail, pulls emails matching configured rules, optionally extracts structured data via Gemini AI, generates LLM-optimized markdown, applies post-collection actions (archive, label, forward, delete), and stores metadata in SQLite. Designed for selective email harvesting into knowledge bases.

## Data Flow

```
Gmail API → Fetch (by rule) → Clean HTML → [Optional: Gemini extraction] → Markdown Export
                                                                              ↓
                                                                    Post-actions (archive, label, forward, delete)
                                                                              ↓
                                                                         SQLite DB
```

## Setup

1. Authenticate with Google OAuth 2.0:

   ```bash
   gmail auth
   ```

2. Configure which emails to fetch and actions to apply in `src/config/gmail-configuration.yaml`.

3. Initialize the database:

   ```bash
   gmail init
   ```

4. Collect emails:

   ```bash
   gmail
   ```

5. (Optional) Send an email from markdown:

   ```bash
   gmail send message.md
   ```

## CLI

```
gmail [--dry-run] [--force] [--rule NAME] [--output PATH] [--max-emails INT] [--config PATH] [--verbose]
gmail init
gmail auth
gmail config [--config PATH]
gmail send [message_path]
gmail --save-config PATH
```

| Flag                 | Description                                                               |
| -------------------- | ------------------------------------------------------------------------- |
| `--dry-run`          | Preview what would be collected without writing files or applying actions |
| `--force`            | Clear state and reprocess all matching emails                             |
| `--rule NAME`        | Run only the named rule (default: all rules)                              |
| `--output PATH`      | Override the output directory from configuration                          |
| `--max-emails INT`   | Override `max_emails_per_run` for this invocation                         |
| `--config PATH`      | Override the default configuration file path                              |
| `--verbose` / `-v`   | Increase log output to DEBUG level                                        |
| `--save-config PATH` | Write the default config template to PATH and exit                        |

## Configuration

Configuration lives at `src/config/gmail-configuration.yaml`. Key settings:

- **rules** — List of collection rules. Each rule has `name`, `query`, `ai_instructions` (or `null`), `actions`, and `append_mode`
- **max_emails_per_run** — Global cap on emails processed per invocation (must be > 0)
- **clean_newsletters** — Strip tracking pixels, social buttons, and boilerplate from email bodies
- **decision_cache_ttl** — Seconds to cache AI extraction decisions per message (0 disables caching)
- **gemini_model** — Gemini model used for AI extraction (e.g. `gemini-2.5-flash`)
- **gemini_api_key_env** — Name of the environment variable holding the Gemini API key
- **gemini_rate_limit_rpm** / **gmail_rate_limit_rpm** — Per-service rate limit caps
- **credentials_path** / **token_path** — Paths to the OAuth 2.0 client secret and cached token

Per-rule actions: `archive`, `mark_read`, `trash`, `delete`, `label:<name>`, `remove_label:<name>`, `forward:<address>`

## Module Structure

| Module         | Role                                                                         |
| -------------- | ---------------------------------------------------------------------------- |
| `cli.py`       | CLI entry point with argparse subcommands                                    |
| `client.py`    | Gmail API v1 wrapper with OAuth 2.0 lifecycle                                |
| `config.py`    | YAML config loader and Gemini API key resolver                               |
| `models.py`    | Local dataclasses for emails and extraction results                          |
| `processor.py` | Orchestration: fetch by rule → clean → extract → export → actions → DB write |
| `extractor.py` | Optional Gemini-powered structured extraction                                |
| `cleaner.py`   | HTML → plain text conversion and newsletter cleanup                          |
| `filters.py`   | Cache and deduplication logic                                                |
| `output.py`    | Markdown generation with email metadata and body                             |
| `llms.py`      | LLM-specific output aggregation                                              |
| `db/`          | SQLite schema, migrations, and query functions                               |

## Data Storage

All paths are rooted at `data/gmail/` by default. Set `DEEP_THOUGHT_DATA_DIR` to redirect.

- **SQLite database** — `<data_dir>/gmail.db` (canonical store)
- **Markdown export** — `<data_dir>/export/<rule_name>/<message_id>.md`

## Tool-Specific Notes

- **OAuth 2.0 flow:** Credentials are cached locally; refresh tokens handled automatically
- **Rule-based collection:** Each rule is a Gmail query (e.g., `from:alice@example.com after:2025-01-01`)
- **Gemini extraction:** Optional structured extraction (requires `google-genai` extra and API key); skipped gracefully if unavailable
- **Post-actions:** Applied after markdown export; one failing action does not block others
- **HTML cleaning:** Removes styles, scripts, and promotional content; plain text body is extracted
- **Rate limiting:** Gmail API quotas respected; backoff applied on 429 responses
