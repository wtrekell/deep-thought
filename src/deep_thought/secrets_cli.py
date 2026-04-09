"""CLI tool for managing secrets in macOS Keychain.

Provides subcommands to migrate secrets from .env to Keychain, check the
status of all known secrets, and manually set or delete individual secrets.
"""

from __future__ import annotations

import argparse
import getpass
import sys

import keyring
import keyring.backends.fail
import keyring.errors
from dotenv import dotenv_values

from deep_thought.secrets import delete_secret, keychain_available, set_secret

# ---------------------------------------------------------------------------
# Secret registry — maps tool names to (service, key_name, default_env_var)
# ---------------------------------------------------------------------------

_SECRET_REGISTRY: dict[str, list[tuple[str, str, str]]] = {
    "todoist": [("todoist", "api-token", "TODOIST_API_TOKEN")],
    "reddit": [
        ("reddit", "client-id", "REDDIT_CLIENT_ID"),
        ("reddit", "client-secret", "REDDIT_CLIENT_SECRET"),
        ("reddit", "user-agent", "REDDIT_USER_AGENT"),
    ],
    "research": [("research", "api-key", "PERPLEXITY_API_KEY")],
    "audio": [("audio", "hf-token", "HF_TOKEN")],
    "gmail": [("gmail", "gemini-api-key", "GEMINI_API_KEY")],
    # OAuth tokens for gmail/gcal/gdrive are managed by their auth flows, not here.
}


def _all_entries() -> list[tuple[str, str, str, str]]:
    """Flatten the registry into (tool, service, key_name, env_var) tuples."""
    entries: list[tuple[str, str, str, str]] = []
    for tool_name, secrets_list in _SECRET_REGISTRY.items():
        for service, key_name, env_var in secrets_list:
            entries.append((tool_name, service, key_name, env_var))
    return entries


# ---------------------------------------------------------------------------
# Subcommands
# ---------------------------------------------------------------------------


def cmd_status(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Report where each known secret is currently stored."""
    has_keychain = keychain_available()

    print(f"Keychain backend: {'available' if has_keychain else 'NOT available (using FailKeyring)'}")
    print()

    env_values = dotenv_values()

    for tool_name, service, key_name, env_var in _all_entries():
        full_service = f"deep-thought-{service}"
        in_keychain = False
        in_env = bool(env_values.get(env_var))

        if has_keychain:
            try:
                keychain_value = keyring.get_password(full_service, key_name)
                in_keychain = keychain_value is not None and keychain_value != ""
            except keyring.errors.KeyringLocked:
                in_keychain = False

        location_parts: list[str] = []
        if in_keychain:
            location_parts.append("keychain")
        if in_env:
            location_parts.append(".env")

        location = ", ".join(location_parts) if location_parts else "MISSING"
        print(f"  {tool_name:10s}  {key_name:20s}  {env_var:25s}  {location}")


def cmd_migrate(args: argparse.Namespace) -> None:  # noqa: ARG001
    """Read .env and store each known secret in Keychain."""
    if not keychain_available():
        print("ERROR: No keychain backend available. Cannot migrate secrets.", file=sys.stderr)
        sys.exit(1)

    env_values = dotenv_values()
    migrated_count = 0

    for tool_name, service, key_name, env_var in _all_entries():
        value = env_values.get(env_var)
        if not value:
            print(f"  SKIP  {tool_name}/{key_name} — {env_var} not found in .env")
            continue

        set_secret(service, key_name, value)
        migrated_count += 1
        print(f"  OK    {tool_name}/{key_name} — migrated from {env_var}")

    print()
    if migrated_count > 0:
        print(f"Migrated {migrated_count} secret(s) to Keychain.")
        print("You can now remove these entries from .env if desired.")
    else:
        print("No secrets found in .env to migrate.")


def cmd_set(args: argparse.Namespace) -> None:
    """Store a single secret in Keychain."""
    if not keychain_available():
        print("ERROR: No keychain backend available.", file=sys.stderr)
        sys.exit(1)

    service = args.tool
    key_name = args.key_name

    value = args.value if args.value is not None else getpass.getpass(f"Enter value for {service}/{key_name}: ")

    if not value:
        print("ERROR: Empty value. Secret not stored.", file=sys.stderr)
        sys.exit(1)

    set_secret(service, key_name, value)
    print(f"Secret stored: deep-thought-{service}/{key_name}")


def cmd_delete(args: argparse.Namespace) -> None:
    """Remove a single secret from Keychain."""
    if not keychain_available():
        print("ERROR: No keychain backend available.", file=sys.stderr)
        sys.exit(1)

    delete_secret(args.tool, args.key_name)
    print(f"Secret removed: deep-thought-{args.tool}/{args.key_name}")


# ---------------------------------------------------------------------------
# Argument parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser for the secrets CLI."""
    parser = argparse.ArgumentParser(
        prog="secrets",
        description="Manage secrets in macOS Keychain for deep-thought tools.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show where each known secret is stored")
    subparsers.add_parser("migrate", help="Migrate all .env secrets to Keychain")

    set_parser = subparsers.add_parser("set", help="Store a secret in Keychain")
    set_parser.add_argument("tool", help="Tool identifier (e.g., todoist, reddit)")
    set_parser.add_argument("key_name", help="Key name (e.g., api-token, client-id)")
    set_parser.add_argument("--value", help="Secret value (prompted if omitted)")

    delete_parser = subparsers.add_parser("delete", help="Remove a secret from Keychain")
    delete_parser.add_argument("tool", help="Tool identifier")
    delete_parser.add_argument("key_name", help="Key name")

    return parser


def main() -> None:
    """Entry point for the secrets CLI."""
    parser = build_parser()
    args = parser.parse_args()

    handlers = {
        "status": cmd_status,
        "migrate": cmd_migrate,
        "set": cmd_set,
        "delete": cmd_delete,
    }

    handler = handlers[args.command]
    handler(args)


if __name__ == "__main__":
    main()
