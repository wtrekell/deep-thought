# Stack Exchange Tool Changelog

## 0.1.0 (2026-04-11)

- Initial release: rule-based Q&A collection from Stack Exchange API v2.3
- Tag-based discovery with AND/OR semantics (include tags via API, any tags client-side)
- Incremental updates based on answer count changes
- LLM-optimized markdown output with YAML frontmatter
- Qdrant embedding integration (source_tool: stackexchange, source_type: q_and_a)
- .llms.txt / .llms-full.txt generation per rule
- SQLite state tracking with quota management
- Rate limiting with 3-retry exponential backoff and API backoff field support
- Comment fetching for questions and answers (configurable per rule)
- CLI: init, config, collect (default), --dry-run, --force, --rule, --save-config
