from __future__ import annotations

import sqlite3
from pathlib import Path


def collect_health(connection: sqlite3.Connection, dds_data_path: Path) -> dict[str, str | bool | int | None]:
    quick_check = connection.execute("PRAGMA quick_check").fetchone()[0]
    unresolved = connection.execute(
        "SELECT COUNT(*) FROM failed_jobs WHERE resolved_at IS NULL"
    ).fetchone()[0]
    last_error = connection.execute(
        "SELECT value FROM application_state WHERE key='last_error'"
    ).fetchone()

    dds_ok = dds_data_path.is_dir() and (dds_data_path / "manifest.json").exists()
    db_ok = quick_check == "ok"

    state = "RUNNING"
    if not db_ok:
        state = "ERROR"
    elif not dds_ok or unresolved:
        state = "DEGRADED"

    return {
        "state": state,
        "database_ok": db_ok,
        "sqlite_quick_check": quick_check,
        "dds_data_found": dds_ok,
        "unresolved_failed_jobs": int(unresolved),
        "last_error": last_error[0] if last_error else None,
    }
