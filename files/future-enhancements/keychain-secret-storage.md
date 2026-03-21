# Keychain-Based Secret Storage

## Current State

API tokens are stored in a plaintext `.env` file at the project root. The file is excluded from git via `.gitignore` and the token has never been committed. The codebase correctly references tokens by env var name, not by value.

## Problem

A `.env` file is readable by any process running on the machine. Its presence also exposes the fact that a token exists, even to tools that only scan filenames.

## Proposed Enhancement

Replace `.env`-based secret storage with macOS Keychain Access. Tokens would be stored in the system keychain and retrieved at runtime using `security find-generic-password` or the `keyring` Python library.

### Benefits

- Token never exists as a readable file on disk
- No file to accidentally copy, share, or expose via filename alone
- Leverages OS-level encryption and access controls
- Keychain prompts provide an audit trail of access

### Considerations

- macOS-specific unless a cross-platform library like `keyring` is used
- Adds a setup step: users must store the token in keychain before first use
- CI/CD environments would still need env vars or a secrets manager
- The `config.py` token retrieval (`get_api_token()`) is the single point of change

## Scope

Affects `config.py` and the setup instructions in the README. No changes to database, sync logic, or CLI interface.
