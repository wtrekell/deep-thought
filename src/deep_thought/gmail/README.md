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

## Configuration

Configuration lives at `src/config/gmail-configuration.yaml`. Key settings:

- **rules** — List of collection rules (each with a name, query, and actions)
- **max_emails_per_rule** — Limit results per rule
- **use_gemini** — Enable AI extraction via Gemini API
- **actions** — Post-collection actions: archive, label, forward, delete
- **clean_html** — Remove styles, scripts, and unwanted tags from email bodies

## Module Structure

| Module | Role |
| --- | --- |
| `cli.py` | CLI entry point with argparse subcommands |
| `client.py` | Gmail API v1 wrapper with OAuth 2.0 lifecycle |
| `config.py` | YAML config loader and Gemini API key resolver |
| `models.py` | Local dataclasses for emails and extraction results |
| `processor.py` | Orchestration: fetch by rule → clean → extract → export → actions → DB write |
| `extractor.py` | Optional Gemini-powered structured extraction |
| `cleaner.py` | HTML → plain text conversion and newsletter cleanup |
| `filters.py` | Cache and deduplication logic |
| `output.py` | Markdown generation with email metadata and body |
| `llms.py` | LLM-specific output aggregation |
| `db/` | SQLite schema, migrations, and query functions |

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
