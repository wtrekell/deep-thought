# File-Txt Tool — Issues

No outstanding issues. Last verified 2026-04-03.

## Resolved (2026-04-02)

| ID | Severity | File | Issue | Resolution |
|---|---|---|---|---|
| A-01 | Low | engines/marker_engine.py | Dead code: marker_engine.py remained in the repository after the PDF engine was switched from marker-pdf to pymupdf4llm. The file was never imported or reachable from any code path. | Deleted. Active PDF engine is engines/pymupdf_engine.py. |
