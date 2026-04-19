#!/usr/bin/env python3
"""Pre-commit audit via the Gemini API.

Replaces the previous ``gemini -p`` CLI invocation inside
``dont-panic/scripts/gemini-pre-commit.sh``. The CLI crashes with a Node
out-of-memory error on realistic diffs because it bootstraps the full
interactive agent runtime (context files, skills, MCP servers, workspace
indexing) just to make one API call. This script calls the Gemini REST API
directly via the ``google-genai`` SDK — same model, same prompt, a tiny
fraction of the memory footprint, and none of the CLI's auth/quota failure
modes.

Usage (inside the pre-commit hook):

    printf '%s\\n' "$STAGED_DIFF" | .venv/bin/python scripts/gemini-audit.py

Stdin: the staged diff text (already collected by the hook's
``git diff --cached``).

Stdout: exactly one line beginning with ``APPROVE:`` or ``REJECT:``, matching
the verdict contract the hook already parses. The hook logs stdout verbatim,
so any additional status lines written here will be visible to the user.

Exit codes:
  0 — script ran successfully and produced a verdict line (the verdict
      itself may be APPROVE or REJECT; the hook decides what to do with it).
  1 — script failed before producing a verdict (missing API key, network
      error, malformed API response, etc.). The hook's fail-closed behavior
      will block the commit.

Secrets:
  The script forces ``DEEP_THOUGHT_NO_KEYCHAIN=1`` and loads
  ``deep-thought/.env`` on startup, so the Gemini API key is read from the
  ``GEMINI_API_KEY`` entry in that ``.env`` file — never from the macOS
  keychain. This is deliberate: git hooks run non-interactively and must
  never block on a keychain password prompt. Set the key with::

      GEMINI_API_KEY="..."   # in deep-thought/.env

  A free-tier key from https://aistudio.google.com/apikey is plenty for
  pre-commit rate.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import NoReturn

from dotenv import load_dotenv

# Suppress macOS keychain prompts before any keychain-aware code is imported
# or called. Git hooks run non-interactively and must never block on a UI
# prompt, so the audit relies exclusively on GEMINI_API_KEY from .env.
os.environ.setdefault("DEEP_THOUGHT_NO_KEYCHAIN", "1")

# Load deep-thought/.env so GEMINI_API_KEY is available via os.environ for
# get_secret()'s env-var fallback path. Path: scripts/../.env = deep-thought/.env.
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# The hook runs this script via ``.venv/bin/python``, so ``deep_thought`` and
# ``google.genai`` are both on sys.path without any manipulation here.
from deep_thought.secrets import get_secret  # noqa: E402 — import after env setup

_MODEL_NAME = "gemini-2.5-flash"

_AUDIT_INSTRUCTIONS = """You are a commit-time security auditor. A git diff is provided below.

Check it for:
1. PII — secrets, API keys, tokens, passwords, personal emails, physical addresses, personal names of family members, phone numbers, or any identifier that ties the diff to a specific private individual.
2. Sensitive data — internal codenames, private URLs, credentials of any kind, or content that should not live in a shared repository.

Respond with exactly one line, starting with one of:
  APPROVE: <short reason>
  REJECT: <short reason>

Do not output anything before the verdict line. Do not echo the diff back in your response.
"""


def _emit_failure(reason: str) -> NoReturn:
    """Print a REJECT line to stdout and exit 1.

    The hook's fail-closed policy treats exit 1 as a blocked commit, and it
    prints our stdout verbatim, so the REJECT line also functions as the
    user-facing error message.
    """
    print(f"REJECT: gemini-audit script error — {reason}")
    sys.exit(1)


def main() -> None:
    diff_text = sys.stdin.read()
    if not diff_text.strip():
        # Nothing to audit — approve a no-op. The hook already short-circuits
        # the empty-diff case on its own, so this branch is defensive only.
        print("APPROVE: empty diff")
        return

    try:
        api_key = get_secret("gemini", "api-key", env_var="GEMINI_API_KEY")
    except OSError as secret_error:
        _emit_failure(f"API key not found ({secret_error})")

    try:
        import google.genai  # noqa: PLC0415 — deferred until after the secret lookup
    except ImportError as import_error:
        _emit_failure(f"google-genai not installed in venv ({import_error})")

    try:
        genai_client = google.genai.Client(api_key=api_key)
        response = genai_client.models.generate_content(
            model=_MODEL_NAME,
            contents=f"{_AUDIT_INSTRUCTIONS}\n\n---\n\n{diff_text}",
        )
    except Exception as api_error:  # noqa: BLE001 — any failure must fail-closed
        _emit_failure(f"API call failed ({type(api_error).__name__}: {api_error})")

    verdict_text = (response.text or "").strip()
    if not verdict_text:
        _emit_failure("API returned empty response")

    # The hook parses the first line starting with APPROVE: or REJECT:.
    # Collapse any leading blank lines or banners the model might emit.
    for response_line in verdict_text.splitlines():
        stripped_line = response_line.strip()
        if stripped_line.startswith(("APPROVE:", "REJECT:")):
            print(stripped_line)
            return

    _emit_failure(f"API response contained no verdict line: {verdict_text[:200]}")


if __name__ == "__main__":
    main()
