# Specifications

The `spec/` directory contains architecture and design documents that explain how the deep-thought system works and how decisions are made. These are not binding contracts — they are reference documents that capture reasoning, context, and technical choices.

## What's Here

| Document | Purpose |
|---|---|
| [`260401-agent-design.md`](260401-agent-design.md) | Defines agent roles and responsibilities across the project. Explains the split between Python Developer, Schema and Data Agent, Workflow Architect, and Quality Gate. |
| [`260402-tooling-evolution.md`](260402-tooling-evolution.md) | Documents changes to tool architecture as of April 2026. Introduces the tool taxonomy, identifies what each type requires, and specifies how the standard outline should evolve. |

## How to Use These Specs

### I need to understand how work is organized

Read [`260401-agent-design.md`](260401-agent-design.md). It explains:
- Why some roles are split (e.g., Python expertise vs. data architecture)
- What each agent is responsible for (in scope / out of scope)
- How the team is structured and who does what

### I'm designing a new tool or feature

Start with [`260402-tooling-evolution.md`](260402-tooling-evolution.md). It explains:
- The four tool types (Collector, Bidirectional Collector, Converter, Generative)
- What requirements apply to each type
- When embeddings are needed
- How to apply the tool implementation standard

Then refer to:
- [`../tool-implementation-standard-outline.md`](../tool-implementation-standard-outline.md) for the full standard
- [`../templates/tool-requirements/requirements-template.md`](../templates/tool-requirements/requirements-template.md) to write your requirements document

### I'm debugging or evaluating architecture changes

Both specs document decision-making at different phases of the project:
- `260401-agent-design.md` (April 2026) — revised the agent model to handle semantic retrieval and cross-tool workflows
- `260402-tooling-evolution.md` (April 2026) — standardized the tool taxonomy and updated implementation requirements

These are point-in-time documents. Check CHANGELOG files for subsequent changes.

## Related Documents

- **Tool-specific design:** See [`../tools/{tool}/260XXX-requirements.md`](../tools/) for individual tool briefs
- **Implementation standard:** [`../tool-implementation-standard-outline.md`](../tool-implementation-standard-outline.md) codifies the pattern that all tools follow
- **Vector search:** [`../tools/embeddings/260402-qdrant-schema.md`](../tools/embeddings/260402-qdrant-schema.md) documents the Qdrant vector store used by knowledge-content tools
