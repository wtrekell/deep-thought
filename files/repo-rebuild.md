# Setup

## Repo

1. **2026-01-02** — Basic repo with Python tooling configuration (pyproject.toml, ruff, mypy, pytest)
1. **2026-02-19** — Updated .gitignore for Claude Code files
1. **2026-03-07** — Prettier setup for markdown, JSON, YAML (package.json, .prettierrc, .prettierignore)
1. **2026-03-13** — Built AI-for-IA (info-architect) agent, v1
1. **2026-03-13** — Todoist tool requirements written and finalized (`docs/tools/todoist/260313-requirements.md`)
1. **2026-03-13** — Initial Todoist tool build: CLI (8 subcommands), SDK wrapper, SQLite layer with migrations, local models, filter engine, pull/push/sync, markdown export, full test suite
1. **2026-03-13** — First live Todoist sync test; added command reference (`42.md`), Todoist README, API model docs, and YAML configuration
1. **2026-03-14** — Added Claude Code enhancement recommendations and tool implementation standard outline; updated info-architect agent with gitignore and secrets/PII reporting rules; LLM-friendly text skill
1. **2026-03-15** — Cleaned up stray files from prior repo; moved tool implementation standard to `docs/templates/`
1. **2026-03-19** — Reorganized non-code docs from `docs/` into `files/`: repo-rebuild log, future-enhancements, templates, and Todoist-specific docs (requirements, changelog, API model) now live under `files/`
1. **2026-03-19** — Moved Todoist YAML configuration to `src/config/todoist_configuration.yaml`
1. **2026-03-19** — Added `todoist create` subcommand: `create.py` business logic, `cmd_create` in `cli.py`, `upsert_task_with_labels` in `queries.py`, and supporting tests in `test_create.py`
1. **2026-03-19** — Added `DEEP_THOUGHT_DATA_DIR` env var support via `get_data_dir()` in `schema.py`; updated CLI help text and added `test_schema.py`
1. **2026-03-21** — Updated `.gitignore`: added `00-*` noise rule and `files/tools/google/` to prevent credential files from being committed
