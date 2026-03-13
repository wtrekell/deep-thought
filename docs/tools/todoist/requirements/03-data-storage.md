# Perplexity Query

## For a daily sync where the AI is the only consumer, the sweet spot is a small structured store that mirrors Todoist’s schema: usually SQLite (or another embedded DB) with a few well‑designed tables, plus a simple metadata store for sync state.

### What to optimize for

Because the tool is AI‑facing, the storage choice should prioritize:

- Fast, flexible querying over many fields (project, labels, due dates, completion, etc.).
- Easy schema evolution as you change how the AI reasons about tasks.
- Simple deployment/ops (ideally, just a file on disk or a single lightweight service).

Todoist’s own client libraries already assume a structured view of data (projects, sections, tasks, labels, comments, etc.), and the official Python SDK exposes a local “state” object after sync, which you can persist however you like. [pypi](https://pypi.org/project/todoist-python/)

### Recommended approach

1. Use **SQLite** as the primary store:
   - Single file, no server, perfectly adequate for daily sync volumes.
   - Good indexing and SQL queries for arbitrary AI prompts (e.g., “all overdue work tasks with label @deep_work due this week”).
   - Plays nicely with Python ORMs like SQLAlchemy if you want migrations and models.

2. Design tables around Todoist entities:
   - `projects`, `sections`, `tasks`, `labels`, `task_labels` (many‑to‑many), `comments`.
   - Include Todoist IDs and timestamps so you can map remote objects and reason about changes.
   - Keep a `sync_state` or `metadata` table that stores:
     - Last sync token from the SDK.
     - Versioning info in case you change your schema.

3. Persist the raw SDK state if helpful:
   - Optionally store a **JSON blob** of the full Todoist state per sync (e.g., in a `snapshots` table or as a flat file) as a debugging/backup mechanism, but treat the relational schema as canonical for queries.
   - This gives you a quick escape hatch if you later need fields you didn’t model.

4. Only consider a server DB or KV store if:
   - You’ll scale to multiple AI agents or services needing concurrent access (then Postgres is a natural upgrade).
   - You need cross‑machine or multi‑user access; otherwise SQLite is simpler than Redis or a full DB. A Redis approach is more common when you’re primarily caching short‑lived state for high‑frequency syncs or serverless environments, not a low‑frequency daily sync. [coreyseliger](https://coreyseliger.me/2017/12/03/Using-Redis-to-Cache-the-Todoist-Python-API/)

### How this plays with the Python SDK

- Use the Todoist Python SDK’s sync to retrieve the latest state, then:
  - Upsert entities into your SQLite tables keyed by Todoist IDs.
  - Store/refresh the sync token in `sync_state` for efficient subsequent syncs using the API’s partial sync mechanism. [pypi](https://pypi.org/project/todoist-python/)
- Have the AI read only from SQLite, never directly from Todoist, so its view is stable and you don’t burn API quota.

A simple example: a single `todoist.db` file with a `tasks` table (indexed on `due_date`, `project_id`, and `completed`) will let your AI answer almost any structured query quickly and without extra network calls. [lib](https://lib.rs/crates/todoist-cli-rs)

Would you rather keep this entirely local to a single machine, or do you expect multiple services/hosts to read the same Todoist mirror? That choice may tilt things between SQLite and a small Postgres instance.
