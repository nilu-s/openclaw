"""SQLite connection helpers for Nexusctl SQLite storage workflow.

The storage layer deliberately stays small: connection management, migrations,
and repositories are separate modules so no single storage god-object emerges.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import sqlite3
from typing import Iterator

DEFAULT_DB_NAME = "nexus.db"


def connect_database(path: str | Path = DEFAULT_DB_NAME, *, read_only: bool = False) -> sqlite3.Connection:
    """Open a configured SQLite connection.

    Parameters
    ----------
    path:
        Database path. Parent directories are created for writable connections.
    read_only:
        Use SQLite URI read-only mode. This is useful for status commands later.
    """

    db_path = Path(path)
    if read_only:
        uri = f"file:{db_path.as_posix()}?mode=ro"
        connection = sqlite3.connect(uri, uri=True)
    else:
        if db_path.parent and db_path.parent != Path(""):
            db_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(db_path)

    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA journal_mode = WAL")
    connection.execute("PRAGMA synchronous = NORMAL")
    return connection


@contextmanager
def transaction(connection: sqlite3.Connection) -> Iterator[sqlite3.Connection]:
    """Run a transaction and rollback on any exception."""

    try:
        connection.execute("BEGIN")
        yield connection
    except Exception:
        connection.rollback()
        raise
    else:
        connection.commit()


def close_quietly(connection: sqlite3.Connection | None) -> None:
    """Close a connection while ignoring shutdown-time sqlite errors."""

    if connection is None:
        return
    try:
        connection.close()
    except sqlite3.Error:
        pass
