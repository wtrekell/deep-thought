"""Database initialization and migration runner for the Gmail Tool.

Responsibilities:
- Locate the SQLite database file
- Open connections with the correct pragma settings
- Apply forward-only .sql migrations in numbered order
- Track the applied migration version in the key_value table
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _project_root() -> Path:
    """Return the absolute path to the repository root.

    Determined by walking up from this file until we find pyproject.toml,
    which is a reliable anchor for the monorepo root.
    """
    current = Path(__file__)
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: use the directory four levels up (db/ -> gmail/ -> deep_thought/ -> src/ -> root)
    return current.parents[4]


def get_data_dir() -> Path:
    """Return the base data directory for Gmail tool storage.

    Checks DEEP_THOUGHT_DATA_DIR env var first; falls back to
    <project_root>/data/gmail.
    """
    env_override = os.environ.get("DEEP_THOUGHT_DATA_DIR")
    if env_override:
        return Path(env_override) / "gmail"
    return _project_root() / "data" / "gmail"


def get_database_path() -> Path:
    """Return the canonical path to the SQLite database file.

    Path: <data_dir>/gmail.db
    The parent directory is created if it does not already exist.
    """
    database_path = get_data_dir() / "gmail.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return database_path


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open and return a configured SQLite connection.

    Args:
        db_path: Path to the database file. Defaults to the canonical path
                 returned by get_database_path(). Pass Path(':memory:') or
                 the string ':memory:' for in-memory use in tests.

    Returns:
        An sqlite3.Connection with:
        - row_factory set to sqlite3.Row (columns accessible by name)
        - WAL journal mode enabled (better concurrent read performance)
        - Foreign key enforcement enabled
    """
    resolved_path: Path | str = db_path if db_path is not None else get_database_path()
    connection = sqlite3.connect(str(resolved_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


# ---------------------------------------------------------------------------
# Schema version tracking
# ---------------------------------------------------------------------------

_SCHEMA_VERSION_KEY = "schema_version"


def get_schema_version(conn: sqlite3.Connection) -> int:
    """Read the current schema version from the key_value table.

    Returns 0 if the table does not yet exist or no version row is present,
    which signals that no migrations have been applied.

    Args:
        conn: An open SQLite connection.

    Returns:
        The integer schema version, or 0 if none has been recorded.
    """
    try:
        cursor = conn.execute(
            "SELECT value FROM key_value WHERE key = ?;",
            (_SCHEMA_VERSION_KEY,),
        )
        row = cursor.fetchone()
        return int(row["value"]) if row is not None else 0
    except sqlite3.OperationalError:
        # key_value table does not exist yet — no migrations applied
        return 0


def _set_schema_version(conn: sqlite3.Connection, version: int) -> None:
    """Persist the current schema version into key_value.

    Args:
        conn: An open SQLite connection (within an active transaction).
        version: The migration number that was just applied.
    """
    from datetime import UTC, datetime

    now_iso = datetime.now(UTC).isoformat()
    conn.execute(
        """
        INSERT INTO key_value (key, value, updated_at)
        VALUES (?, ?, ?)
        ON CONFLICT (key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at;
        """,
        (_SCHEMA_VERSION_KEY, str(version), now_iso),
    )


# ---------------------------------------------------------------------------
# Migration runner
# ---------------------------------------------------------------------------


def run_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    """Apply all unapplied .sql migration files in ascending numeric order.

    Migration files must follow the naming pattern NNN_description.sql where
    NNN is a zero-padded integer (e.g., 001_init_schema.sql). Files are
    sorted lexicographically, which keeps them in numeric order as long as
    the prefix width is consistent.

    Each migration is applied inside its own transaction. If a migration
    fails, the transaction is rolled back and the error is re-raised, leaving
    the database in the last successfully applied state.

    Args:
        conn: An open SQLite connection.
        migrations_dir: Directory containing the .sql migration files.

    Raises:
        FileNotFoundError: If migrations_dir does not exist.
        sqlite3.Error: If any migration statement fails.
    """
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    current_version = get_schema_version(conn)

    migration_files = sorted(migrations_dir.glob("*.sql"))

    for migration_file in migration_files:
        # Extract the numeric prefix (e.g., "001" → 1)
        numeric_prefix = migration_file.stem.split("_")[0]
        try:
            migration_number = int(numeric_prefix)
        except ValueError:
            # Skip files that do not start with an integer prefix
            continue

        if migration_number <= current_version:
            # Already applied
            continue

        migration_sql = migration_file.read_text(encoding="utf-8")

        # Strip SQL line comments before splitting on semicolons so that
        # comment text containing semicolons does not produce false statement
        # fragments.
        sql_lines_without_comments = [line for line in migration_sql.splitlines() if not line.strip().startswith("--")]
        migration_sql_stripped = "\n".join(sql_lines_without_comments)

        try:
            conn.execute("BEGIN;")
            for raw_statement in migration_sql_stripped.split(";"):
                statement = raw_statement.strip()
                if statement:
                    conn.execute(statement)
            _set_schema_version(conn, migration_number)
            conn.commit()
        except sqlite3.Error as database_error:
            conn.rollback()
            raise sqlite3.Error(f"Migration {migration_file.name} failed: {database_error}") from database_error


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def initialize_database(db_path: Path | str | None = None) -> sqlite3.Connection:
    """Create the database file (if needed), run pending migrations, and return a connection.

    This is the primary entry point for setting up the database. Call this
    once at application startup. The returned connection is ready for use.

    Args:
        db_path: Path to the database file. Accepts a Path, a string path,
                 or the special string ':memory:' for in-memory databases
                 (useful in tests). Defaults to the canonical data/ location.

    Returns:
        A fully initialized sqlite3.Connection with row_factory and pragmas set.
    """
    resolved_path: Path | None = None
    if db_path is not None:
        resolved_path = Path(db_path) if not isinstance(db_path, Path) else db_path

    connection = get_connection(resolved_path)

    migrations_directory = Path(__file__).parent / "migrations"
    run_migrations(connection, migrations_directory)

    return connection
