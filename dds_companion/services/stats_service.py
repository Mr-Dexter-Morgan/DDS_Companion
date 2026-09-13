from __future__ import annotations

import sqlite3
from pathlib import Path


def _count(connection: sqlite3.Connection, table: str) -> int:
    return int(connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for item in path.rglob("*"):
        try:
            if item.is_file():
                total += item.stat().st_size
        except OSError:
            continue
    return total


def collect_stats(connection: sqlite3.Connection, database_path: Path, dds_data_path: Path) -> dict[str, int | str | None]:
    last_import_row = connection.execute(
        "SELECT value FROM application_state WHERE key='last_successful_import'"
    ).fetchone()

    db_size = database_path.stat().st_size if database_path.exists() else 0
    dds_size = directory_size(dds_data_path)

    return {
        "messages": _count(connection, "messages"),
        "guilds": _count(connection, "guilds"),
        "channels": _count(connection, "channels"),
        "threads": _count(connection, "threads"),
        "users": _count(connection, "users"),
        "attachments": _count(connection, "attachments"),
        "embeds": _count(connection, "embeds"),
        "imports": _count(connection, "capture_imports"),
        "failed_jobs": _count(connection, "failed_jobs"),
        "sqlite_bytes": db_size,
        "dds_json_bytes": dds_size,
        "total_known_storage_bytes": db_size + dds_size,
        "last_successful_import": last_import_row[0] if last_import_row else None,
    }
