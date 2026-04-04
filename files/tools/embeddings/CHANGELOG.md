# Embeddings Infrastructure Changelog

## 2026-04-04

### Changed

- Updated Qdrant server binary from v1.14.0 to v1.17.1 to match the installed `qdrant-client` version and resolve a compatibility warning raised on every connection. The 3-minor-version gap exceeded Qdrant's supported tolerance (client and server major versions must match; minor version difference must not exceed 1). Old binary retained at `~/bin/qdrant.1.14.0.bak`.
- `qdrant-client` 1.17.1 is now the confirmed working client version (installed via `uv sync --extra embeddings`).
- Configured Qdrant to start automatically at login via a macOS LaunchAgent (`~/Library/LaunchAgents/com.williamtrekell.qdrant.plist`). The service runs from `~/qdrant_storage`, restarts automatically on crash, and logs to `~/qdrant_storage/qdrant.log`. No manual startup required after this change.
