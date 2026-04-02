# Agent Design

## Context

This document captures the agent role design across the full deep-thought system as of April 2026. It covers two categories: build-side agents that live in deep-thought, and usage-side agents that live in consuming repos (magrathea, quiet-evolution) — though some usage agents are also present in deep-thought where the work warrants it.

The build-side replaces the original three-agent design (python-app-developer, sqlite-schema-expert, code-quality-integration) built when the repository contained a single tool (Todoist) under active development.

The repository now has 8 tools in production and a pipeline of additional tools with completed requirements. New requirements — cross-tool workflows and embeddings-based semantic retrieval — require a revised design.

---

## What Changed

**Repository scope.** A tool implementation standard outline now codifies the build pattern. New tools are an exercise in applying a known recipe to a new API, not open-ended design work.

**Semantic retrieval requirement.** At the scale of 1000+ collected documents across tools, Claude cannot read everything. Embeddings + vector search (Qdrant, local MLX embedding model) are required to retrieve relevant content before Claude reads it. This adds an embedding step to the collection pipeline for tools that produce knowledge content, and requires shared vector infrastructure that spans those tools.

**Cross-tool workflows.** Pipelines that query or combine data across multiple tools are anticipated. No current agent is designed for this.

---

## Why the Original Design Mostly Holds

The python-app-developer / sqlite-schema-expert split enforced a useful boundary and remains the right model. Python expertise (application logic, CLI, data models) and data architecture expertise (relational schema, vector store design) are genuinely different domains. Collapsing them into one agent produces worse work in both areas.

What changes: both agents expand their scope to all tools in the namespace, not just Todoist. The Schema and Data Agent adds Qdrant to its domain alongside SQLite. A new Workflow Architect role handles cross-tool work that neither existing agent was designed for.

The code-quality-integration agent was blocked at ruff formatting in 6 of 13 runs — a process failure in the implementing agent's definition, not a role problem. The agent's genuinely valuable work (deep code review, catching critical bugs) is unaffected by fixing this.

---

## Agent Roles

### Python Developer

Owns all Python application code across every tool in the `deep_thought` namespace. Same role as before, expanded scope.

**In scope**
- Python application code for any tool: business logic, CLI, data models, config loading, output formatting, progress display
- Embedding integration: at collection time, calling the embedding model and writing to Qdrant — following patterns established by the Workflow Architect
- Tests for all new and modified functionality
- CHANGELOG and ISSUES updates

**Out of scope**
- Raw SQL — no schema decisions, no migration files, no query authoring
- Qdrant collection design or index configuration (Schema and Data Agent)
- Cross-tool design or shared infrastructure (Workflow Architect)
- Quality audit (Quality Gate)

---

### Schema and Data Agent

Owns the structure of all stored data: SQLite schemas and Qdrant collection design. Expanded from the original sqlite-schema-expert role, which was SQLite only.

**In scope**
- SQLite: table design, migrations, query authoring, index strategy
- Qdrant: collection configuration, payload schema, which fields are indexed for filtering, embedding storage patterns
- Handoff to the Python Developer: Python-facing interfaces showing how to call queries and upsert to the vector store

**Out of scope**
- Python application code (Python Developer)
- Cross-tool design (Workflow Architect)
- Quality audit (Quality Gate)

---

### Workflow Architect

Designs and implements work that spans multiple tools: the shared Qdrant collection, cross-tool pipelines, and the retrieval interface Claude uses to query the corpus.

**In scope**
- Shared Qdrant collection: design, setup, index management
- Embedding model: selection and MLX integration, establishing the pattern individual tools follow
- Retrieval layer: the query interface that embeds a user query, searches Qdrant, and returns relevant document paths for Claude to read
- Cross-tool pipeline design: how multiple tools' outputs combine or sequence
- Shared utilities consumed by multiple tools

**Out of scope**
- Individual tool implementation (Python Developer and Schema and Data Agent)
- Per-tool embedding calls within each collection pipeline (Python Developer, following patterns Workflow Architect establishes)
- Quality audit (Quality Gate)

**Status.** This agent does not yet exist. It should be defined and built when the retrieval layer or first cross-tool workflow is ready to implement.

---

### Quality Gate

Independent quality audit after any implementation work. Diagnoses issues with clear, actionable output. Does not implement fixes — with one exception.

**In scope**
- Full toolchain in order: `ruff check` → `ruff format` → `mypy` → `pytest`
- Auto-applying `ruff format` and `ruff check --fix` — mechanical corrections, not logic changes
- CLI smoke tests across all tools (not hardcoded Todoist commands)
- Schema-code consistency checks
- Deep code review: correctness, edge cases, boundary violations
- Classifying issues by owner (Python Developer, Schema and Data Agent, Workflow Architect, or spec issue)

**Out of scope**
- Implementing any fix beyond auto-fixable formatting
- Modifying tests to pass, relaxing type annotations, skipping failures

**Change from previous design.** Auto-applying formatting removes the recurring bottleneck (6 blocked runs) without compromising the agent's neutrality. The valuable work — the deep review pass that catches correctness issues — is unchanged.

---

---

## Usage Agents

These agents operate against collected data rather than building the tools that collect it. Configuration and Collection live in all repos. Context lives in all repos. Research lives in consuming repos.

---

### Configuration Agent

Owns setup and ongoing maintenance of tool configuration across any repo. Knows every tool's YAML schema, how rules work, and how consuming repos are initialized.

**In scope**
- Creating and modifying tool YAML configs: rules, filters, limits, API key env var references
- Validating configs against tool schemas — catching errors before a collection run fails
- Per-repo initialization: `npm install`, `.vale.ini`, Prettier config, `lint.config.yaml`, `.env` structure with `DEEP_THOUGHT_DATA_DIR`
- Adding new sources to existing configs (new subreddit, new site, new Stack Exchange site)
- Tuning rules based on collection results — adjusting filters, limits, age windows

**Out of scope**
- Running the tools (Collection Agent)
- Writing Python code or modifying tool source (Python Developer)
- Schema or DB changes (Schema and Data Agent)

**Lives in:** All repos. Deep-thought for tool config files in `src/config/`. Consuming repos for their own config files and initialization.

---

### Context Agent

Autonomous scheduler and dispatcher. Reads the Todoist work queue, decides what to run based on priority, timing, and resource state, dispatches work to the appropriate repo and agent, and surfaces only what genuinely needs a human decision. Runs on a launchd schedule rather than waiting to be invoked.

**In scope**
- Reading the Todoist queue via the existing SQLite database or markdown export
- Categorizing work: autonomous (Claude can execute without input) vs. human-required (needs a decision or review)
- Dispatching autonomous work to the correct repo by invoking `claude --directory /path/to/repo` with a prompt derived from the task
- Resource-aware scheduling: running lower-priority autonomous work when usage would otherwise expire (e.g. priority 3 items Wednesday night before the usage period resets)
- Reporting outcomes back to Todoist or surfacing results for review
- Escalating blocked or ambiguous tasks clearly rather than stalling

**Out of scope**
- Executing the work itself — it dispatches, it does not implement
- Collecting content (Collection Agent)
- Querying the knowledge base (Research Agent)

**Trigger mechanism.** Runs on a launchd schedule (macOS equivalent of cron). Also triggered by Collection Agent after a run completes when new items or errors need routing.

**Todoist label convention.** Tasks intended for autonomous dispatch carry labels that encode:
- Target repo — `deep-thought`, `magrathea`, or `quiet-evolution` (exact repo names, already in use)
- Autonomy flag — whether Claude can execute without human input
- Priority (Todoist p1–p4 maps directly to dispatch urgency)
- Any agent or workflow hint the task carries

**Repo path resolution.** Labels are repo names. The `DEEP_THOUGHT_REPOS_DIR` environment variable points to the parent directory containing all repos. Context Agent derives the dispatch path as `$DEEP_THOUGHT_REPOS_DIR/{label}` — no hardcoded paths in the agent definition. Adding a new repo requires only a matching label and a directory under `DEEP_THOUGHT_REPOS_DIR`. Both `DEEP_THOUGHT_REPOS_DIR` and `DEEP_THOUGHT_DATA_DIR` are set in `.zshrc` and available to all shell sessions, Claude Code, and the tools without needing to be in `.env`.

**Lives in:** All repos. Deep-thought for development work dispatch. Consuming repos for their own work queues.

---

### Collection Agent

Runs the deep-thought CLI tools for a given repo's configuration. Knows the entry points, flags, and expected output for every tool. Surfaces what's new after a run and hands off to Context when items need attention.

**In scope**
- Running tools: deciding which tools to run, in what order, with what flags
- Interpreting run output: what was collected, what was skipped, what errored
- Handling partial failures: rate limits, API errors, retry decisions
- Dry-run previews before committing a full collection run
- Triggering Context after a run completes when new items or errors need attention

**Out of scope**
- Modifying config to change what gets collected (Configuration Agent)
- Writing or modifying tool source code (Python Developer)
- Querying or synthesizing collected content (Research Agent)

**Lives in:** Consuming repos primarily. May be used in deep-thought for testing tools during development.

---

## Boundaries and Handoffs

```
BUILD SIDE

Python Developer ───────────────────→ Quality Gate
  After any tool implementation or modification.
  Python Developer acts on Quality Gate findings.

Schema and Data Agent ──────────────→ Quality Gate
  After any schema or collection design work.

Workflow Architect ─────────────────→ Python Developer
  Workflow Architect establishes shared patterns (embedding model calls,
  Qdrant upsert interface). Python Developer applies those patterns per tool.

Workflow Architect ─────────────────→ Quality Gate
  Cross-tool work is validated the same way individual tool work is.

USAGE SIDE

Configuration Agent ────────────────→ Collection Agent
  Config is in place before Collection runs.

Collection Agent ───────────────────→ Context Agent
  After a run completes, Collection hands off to Context when there are
  new items, errors, or anything requiring attention.

Context Agent ──────────────────────→ Repo agents (cross-repo dispatch)
  Context reads Todoist, builds dispatch list, invokes Claude in the
  target repo directory with task-derived prompts. Launchd schedule
  drives the trigger; Collection Agent triggers it post-run.
```

---

## Retrieval Architecture

The retrieval layer is Workflow Architect territory, but the design is captured here for reference.

**Embedding model.** Local MLX model (e.g. `nomic-embed-text`) running on the M4 Pro Neural Engine. Fast, private, zero API cost. The audio tool's MLX infrastructure is the precedent.

**Vector store.** One shared Qdrant collection. Not per-tool collections — cross-referencing across source types is the primary use case, so all knowledge content lives in one queryable space. Source type is a payload field used for filtering when needed.

**Which tools write to the vector store.**

| Tool | State DB | Embeddings | Rationale |
|---|---|---|---|
| Reddit | Yes | Yes | Community knowledge and discussion |
| Web | Yes | Yes | Blogs (expert writing) and official articles |
| Stack Exchange | Yes | Yes | Technical Q&A |
| Research | No | Yes | Curated knowledge, already stateless |
| Gmail | Yes | No | Personal and operational |
| GCal | Yes | No | Personal and operational |
| YouTube | Yes | TBD | Depends on content type |
| Audio | Yes | No | Converter behavior |
| File-txt | No | No | Pure converter, no state needed |
| Krea / generative | Yes | No | Tracks output, not knowledge content |

**Payload fields on each embedded document.**

- `source_tool` — which tool collected it (reddit, web, stackexchange, research)
- `source_type` — content category (blog, article, forum_post, q_and_a, research)
- `output_path` — path to the full markdown file Claude reads
- `rule_name` — which configuration rule collected it
- `collected_date` — when it was collected
- Tool-specific fields indexed for filtering (e.g. `subreddit`, `site`, `domain`)

**Query flow.**
1. User query is embedded using the same local model
2. Qdrant searches the single shared collection, optionally filtered by `source_type` or tool
3. Top-N most semantically similar document paths are returned
4. Claude reads those markdown files

Cross-referencing — blogs, official articles, and community discussion on the same topic — happens in a single query by default. Filtering by source type is available when a specific perspective is needed.
