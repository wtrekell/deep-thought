# Reddit Tool — Changelog

All notable changes to the Reddit Tool will be documented in this file.

---

## [0.1.0] — 2026-03-22

### Added

- Initial implementation: rule-based collection from subreddits via PRAW
- SQLite state tracking with composite key (`post_id:subreddit:rule_name`)
- Incremental update detection via comment count comparison
- Configurable filtering: score, age, keywords, flair
- Markdown output with YAML frontmatter
- Optional `.llms.txt` / `.llms-full.txt` generation
- CLI entry point with `config`, `init`, `--dry-run`, `--force`, `--rule` support
