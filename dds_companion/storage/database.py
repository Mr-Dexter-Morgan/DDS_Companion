from __future__ import annotations

import sqlite3
import time
from pathlib import Path

from .migrations import apply_migrations


def connect_database(path: str | Path) -> sqlite3.Connection:
    db_path = Path(path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(db_path, timeout=10.0)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    # Install the busy timeout before WAL negotiation; concurrent first-open
    # callers can contend while journal mode itself is being established.
    connection.execute("PRAGMA busy_timeout = 10000")

    # GUI startup may open the same archive from multiple workers at once.
    # A transient lock can surface during WAL negotiation *or* during additive
    # migrations, so treat the whole startup setup as one retryable unit.  Retry
    # only the exact SQLite busy condition; every other failure remains fatal.
    deadline = time.monotonic() + 10.0
    while True:
        try:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = NORMAL")
            apply_migrations(connection)
            break
        except sqlite3.OperationalError as exc:
            if "database is locked" not in str(exc).lower() or time.monotonic() >= deadline:
                connection.close()
                raise
            try:
                connection.rollback()
            except sqlite3.Error:
                pass
            time.sleep(0.05)
    return connection
