# Documentation

This is the documentation hub for **deep-thought**, a Python 3.12 monorepo housing 8 CLI tools that collect, convert, and structure data from external services into LLM-optimized markdown.

## What's Here

The `docs/` directory contains:

- **`tools/`** — Documentation for each of the 8 CLI tools: architecture, usage, requirements, and known issues
- **`spec/`** — Architecture and design documents for system-wide concerns (agent design, tooling evolution, vector embeddings)
- **`templates/`** — Reusable templates for tool requirements, documentation structure, and standards
- **Loose reference files** — API models, configuration guides, platform specifications, and research documents

## How to Use This Documentation

### I want to use a tool

Start in [`tools/README.md`](tools/README.md). It lists all 8 tools with their CLI entry points and one-line descriptions. Click through to the tool you need.

Each tool has:
- A `CHANGELOG.md` tracking all changes and fixes
- An `ISSUES.md` for known bugs and workarounds  
- A `260XXX-requirements.md` file documenting the tool's design and API model
- Some tools have additional files like `api-model.md` or `ENHANCEMENTS.md`

### I'm building a new tool

1. Read [`spec/260401-agent-design.md`](spec/260401-agent-design.md) to understand the agent roles and architecture
2. Review [`spec/260402-tooling-evolution.md`](spec/260402-tooling-evolution.md) to understand the tool taxonomy and what's required for each type
3. Use the [`templates/tool-requirements/requirements-template.md`](templates/tool-requirements/requirements-template.md) as your starting point
4. Reference [`tool-implementation-standard-outline.md`](tool-implementation-standard-outline.md) for the standard structure every tool follows

### I want to understand the architecture

- **Agent roles:** [`spec/260401-agent-design.md`](spec/260401-agent-design.md) explains how work is divided between Python Developer, Schema and Data Agent, Workflow Architect, and Quality Gate
- **Tool types:** [`spec/260402-tooling-evolution.md`](spec/260402-tooling-evolution.md) and [`tool-implementation-standard-outline.md`](tool-implementation-standard-outline.md) define the four tool types (Collector, Bidirectional Collector, Converter, Generative) and what each requires
- **Embeddings:** [`tools/embeddings/260402-qdrant-schema.md`](tools/embeddings/260402-qdrant-schema.md) documents the vector store used by knowledge-content tools (Reddit, Web, Research)
- **Data flow:** Each tool follows this pattern: External source → SQLite (canonical store) → Markdown export → AI consumption

### I need to troubleshoot or check status

Look for the tool's `ISSUES.md` file. Known bugs, workarounds, and version-specific notes are maintained there.

## Directory Structure

```
docs/
├── README.md                                    (you are here)
├── tools/                                       (8 tool directories)
│   ├── README.md                                (overview of all tools)
│   ├── audio/                                   (Audio transcription tool)
│   ├── embeddings/                              (Qdrant vector store schema)
│   ├── file-txt/                                (PDF/Office to markdown converter)
│   ├── gcal/                                    (Google Calendar tool)
│   ├── gdrive/                                  (Google Drive backup tool)
│   ├── gmail/                                   (Gmail collection tool)
│   ├── reddit/                                  (Reddit collection tool)
│   ├── research/                                (Web research via Perplexity API)
│   ├── web/                                     (Web crawler tool)
│   └── todoist/                                 (Todoist task management tool)
├── spec/                                        (system design)
│   ├── README.md                                (overview of specs)
│   ├── 260401-agent-design.md                   (agent roles and responsibilities)
│   └── 260402-tooling-evolution.md              (tool taxonomy and requirements)
├── templates/                                   (reusable templates)
│   └── tool-requirements/
│       └── requirements-template.md             (template for new tool briefs)
├── tool-implementation-standard-outline.md      (standard structure for all tools)
└── (other reference files)                      (API models, guides, research)
```

## Quick Reference

| If you need to… | Start here |
|---|---|
| Collect data from Reddit | [`tools/README.md`](tools/README.md) → Reddit tool |
| Transcribe audio | [`tools/README.md`](tools/README.md) → Audio tool |
| Crawl web pages | [`tools/README.md`](tools/README.md) → Web tool |
| Check if something is a known bug | `tools/{tool}/ISSUES.md` |
| Understand the tool taxonomy | [`spec/260402-tooling-evolution.md`](spec/260402-tooling-evolution.md) |
| Create a new tool | [`templates/tool-requirements/requirements-template.md`](templates/tool-requirements/requirements-template.md) |
| Find agent role definitions | [`spec/260401-agent-design.md`](spec/260401-agent-design.md) |
