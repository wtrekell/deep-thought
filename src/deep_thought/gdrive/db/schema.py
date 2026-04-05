"""Database initialization and migration runner for the GDrive Tool.

Responsibilities:
- Locate the SQLite database file
- Open connections with correct pragma settings (WAL mode, foreign keys)
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

    Determined by walking up from this file until a pyproject.toml is found,
    which is a reliable anchor for the monorepo root.
    """
    current = Path(__file__)
    for parent in current.parents:
        if (parent / "pyproject.toml").exists():
            return parent
    # Fallback: five levels up (migrations/ -> db/ -> gdrive/ -> deep_thought/ -> src/ -> root)
    return current.parents[5]


def get_data_dir() -> Path:
    """Return the base data directory for GDrive tool storage.

    Checks DEEP_THOUGHT_DATA_DIR env var first; falls back to
    <project_root>/data/gdrive.
    """
    env_override = os.environ.get("DEEP_THOUGHT_DATA_DIR")
    if env_override:
        return Path(env_override) / "gdrive"
    return _project_root() / "data" / "gdrive"


def get_database_path() -> Path:
    """Return the canonical path to the SQLite database file.

    Path: <data_dir>/gdrive.db
    The parent directory is created if it does not already exist.
    """
    database_path = get_data_dir() / "gdrive.db"
    database_path.parent.mkdir(parents=True, exist_ok=True)
    return database_path


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def _get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    """Open and return a configured SQLite connection.

    Args:
        db_path: Path to the database file. Defaults to the canonical path
                 returned by get_database_path(). Pass Path(':memory:') for
                 in-memory use in tests.

    Returns:
        An sqlite3.Connection with:
        - row_factory set to sqlite3.Row (columns accessible by name)
        - WAL journal mode enabled
        - Foreign key enforcement enabled
    """
    resolved_path: Path = db_path if db_path is not None else get_database_path()
    connection = sqlite3.connect(str(resolved_path))
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode = WAL;")
    connection.execute("PRAGMA foreign_keys = ON;")
    return connection


# ---------------------------------------------------------------------------
# Schema version tracking
# ---------------------------------------------------------------------------

_SCHEMA_VERSION_KEY = "schema_version"
_MIGRATIONS_DIR = Path(__file__).parent / "migrations"


def _get_schema_version(conn: sqlite3.Connection) -> int:
    """Read the current schema version from the key_value table.

    Returns 0 if the table does not exist yet or no version row is present.

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
        # key_value table does not exist yet
        return 0


def _run_migrations(conn: sqlite3.Connection, migrations_dir: Path) -> None:
    """Apply all unapplied .sql migration files in ascending numeric order.

    Migration files must follow the pattern NNN_description.sql where NNN is
    a zero-padded integer. Each migration runs inside executescript(), which
    issues an implicit COMMIT before running the full SQL text atomically.

    Args:
        conn: An open SQLite connection.
        migrations_dir: Directory containing the .sql migration files.

    Raises:
        FileNotFoundError: If migrations_dir does not exist.
        sqlite3.Error: If any migration statement fails.
    """
    if not migrations_dir.exists():
        raise FileNotFoundError(f"Migrations directory not found: {migrations_dir}")

    current_version = _get_schema_version(conn)
    migration_files = sorted(migrations_dir.glob("*.sql"))

    for migration_file in migration_files:
        numeric_prefix = migration_file.stem.split("_")[0]
        try:
            migration_number = int(numeric_prefix)
        except ValueError:
            continue

        if migration_number <= current_version:
            continue

        migration_sql = migration_file.read_text(encoding="utf-8")

        try:
            conn.executescript(migration_sql)
            conn.commit()
        except sqlite3.Error as database_error:
            conn.rollback()
            raise sqlite3.Error(f"Migration {migration_file.name} failed: {database_error}") from database_error


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------


def init_db(conn: sqlite3.Connection) -> None:
    """Apply all pending migrations to an open database connection.

    Enables WAL mode and foreign keys, then runs any unapplied .sql
    migration files from the bundled migrations directory.

    This is the primary public entry point for schema setup. Pass an
    in-memory connection (sqlite3.connect(':memory:')) for tests.

    Args:
        conn: An open sqlite3.Connection to initialize.
    """
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    _run_migrations(conn, _MIGRATIONS_DIR)


def open_database(db_path: Path | None = None) -> sqlite3.Connection:
    """Open and initialize the GDrive database, returning a ready connection.

    Creates the database file if it does not exist, runs all pending
    migrations, and returns a connection ready for use.

    Args:
        db_path: Optional explicit path. Defaults to the canonical data/gdrive
                 location. Pass Path(':memory:') for in-memory test databases.

    Returns:
        A fully initialized sqlite3.Connection.
    """
    connection = _get_connection(db_path)
    init_db(connection)
    return connection
