from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

VALID_STATES = {"RUNNING", "DEGRADED", "ERROR", "STOPPED", "STARTING", "UNKNOWN"}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


class HealthService:
    """Owns subsystem state and computes the single overall Companion health."""

    def __init__(self, connection: sqlite3.Connection, dds_data_path: str | Path):
        self.connection = connection
        self.dds_data_path = Path(dds_data_path)

    def set_subsystem(
        self,
        subsystem: str,
        state: str,
        summary: str,
        *,
        details: dict | None = None,
        error: str | None = None,
    ) -> bool:
        normalized = state.upper()
        if normalized not in VALID_STATES:
            raise ValueError(f"Unsupported health state: {state}")
        stamp = utc_now()
        previous = self.connection.execute(
            "SELECT last_ok_at, last_error_at FROM subsystem_health WHERE subsystem=?",
            (subsystem,),
        ).fetchone()
        last_ok_at = previous["last_ok_at"] if previous else None
        last_error_at = previous["last_error_at"] if previous else None
        if normalized == "RUNNING":
            last_ok_at = stamp
        if normalized in {"DEGRADED", "ERROR"}:
            last_error_at = stamp

        payload = dict(details or {})
        if error:
            payload["error"] = error
        try:
            with self.connection:
                self.connection.execute(
                    """
                    INSERT INTO subsystem_health(
                        subsystem, state, summary, last_ok_at, last_error_at, updated_at, details_json
                    ) VALUES(?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(subsystem) DO UPDATE SET
                        state=excluded.state,
                        summary=excluded.summary,
                        last_ok_at=excluded.last_ok_at,
                        last_error_at=excluded.last_error_at,
                        updated_at=excluded.updated_at,
                        details_json=excluded.details_json
                    """,
                    (
                        subsystem,
                        normalized,
                        summary,
                        last_ok_at,
                        last_error_at,
                        stamp,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                    ),
                )
        except sqlite3.Error:
            return False
        return True

    def heartbeat(self, subsystem: str, summary: str = "heartbeat ok", *, details: dict | None = None) -> bool:
        return self.set_subsystem(subsystem, "RUNNING", summary, details=details)

    def refresh_core(self, *, watcher_expected: bool, watcher_state: str | None = None) -> dict:
        db_ok, quick_check = self._database_check()
        self.set_subsystem(
            "database",
            "RUNNING" if db_ok else "ERROR",
            "SQLite quick_check ok" if db_ok else f"SQLite quick_check failed: {quick_check}",
            details={"quick_check": quick_check},
            error=None if db_ok else str(quick_check),
        )

        dds_ok = self.dds_data_path.is_dir() and (self.dds_data_path / "manifest.json").exists()
        self.set_subsystem(
            "dds_data",
            "RUNNING" if dds_ok else "DEGRADED",
            "DDS_Data available" if dds_ok else "DDS_Data or manifest.json is missing",
            details={"path": str(self.dds_data_path), "manifest_found": (self.dds_data_path / "manifest.json").exists()},
        )

        if watcher_expected and watcher_state:
            self.set_subsystem("watcher", watcher_state, f"watcher {watcher_state.lower()}")
        elif not watcher_expected:
            self.set_subsystem("watcher", "STOPPED", "watcher disabled by --once")

        return self.snapshot(watcher_expected=watcher_expected)

    def unresolved_failed_jobs(self) -> int:
        return int(
            self.connection.execute("SELECT COUNT(*) FROM failed_jobs WHERE resolved_at IS NULL").fetchone()[0]
        )

    def snapshot(self, *, watcher_expected: bool = True, stale_after_seconds: float = 30.0) -> dict:
        db_ok, quick_check = self._database_check()
        unresolved = self.unresolved_failed_jobs()
        last_error_row = self.connection.execute(
            "SELECT value FROM application_state WHERE key='last_error'"
        ).fetchone()
        rows = self.connection.execute(
            "SELECT * FROM subsystem_health ORDER BY subsystem"
        ).fetchall()

        now = datetime.now(timezone.utc)
        subsystems: dict[str, dict] = {}
        for row in rows:
            details = {}
            try:
                details = json.loads(row["details_json"] or "{}")
            except json.JSONDecodeError:
                details = {"raw_details": row["details_json"]}
            state = row["state"]
            stale = False
            if row["subsystem"] == "watcher" and watcher_expected and state == "RUNNING":
                updated = _parse_iso(row["updated_at"])
                if updated is not None and (now - updated).total_seconds() > stale_after_seconds:
                    state = "DEGRADED"
                    stale = True
            subsystems[row["subsystem"]] = {
                "state": state,
                "summary": row["summary"],
                "last_ok_at": row["last_ok_at"],
                "last_error_at": row["last_error_at"],
                "updated_at": row["updated_at"],
                "stale": stale,
                "details": details,
            }

        dds_ok = self.dds_data_path.is_dir() and (self.dds_data_path / "manifest.json").exists()
        # Database health is authoritative even if the health table itself could not
        # be updated, so compute it independently as part of every snapshot.
        if "database" not in subsystems:
            subsystems["database"] = {
                "state": "RUNNING" if db_ok else "ERROR",
                "summary": f"SQLite quick_check: {quick_check}",
                "stale": False,
                "details": {"quick_check": quick_check},
                "last_ok_at": None,
                "last_error_at": None,
                "updated_at": None,
            }
        if "dds_data" not in subsystems:
            subsystems["dds_data"] = {
                "state": "RUNNING" if dds_ok else "DEGRADED",
                "summary": "DDS_Data available" if dds_ok else "DDS_Data or manifest.json is missing",
                "stale": False,
                "details": {"path": str(self.dds_data_path)},
                "last_ok_at": None,
                "last_error_at": None,
                "updated_at": None,
            }

        overall = "RUNNING"
        states = {name: data["state"] for name, data in subsystems.items()}
        if not db_ok or states.get("database") == "ERROR":
            overall = "ERROR"
        elif unresolved or not dds_ok or any(state in {"DEGRADED", "ERROR"} for state in states.values()):
            overall = "DEGRADED"
        elif watcher_expected and states.get("watcher") not in {"RUNNING", "STARTING"}:
            overall = "DEGRADED"

        return {
            "state": overall,
            "database_ok": db_ok,
            "sqlite_quick_check": quick_check,
            "dds_data_found": dds_ok,
            "unresolved_failed_jobs": unresolved,
            "last_error": last_error_row[0] if last_error_row else None,
            "subsystems": subsystems,
        }

    def _database_check(self) -> tuple[bool, str]:
        try:
            quick_check = str(self.connection.execute("PRAGMA quick_check").fetchone()[0])
            return quick_check == "ok", quick_check
        except sqlite3.Error as exc:
            return False, f"{type(exc).__name__}: {exc}"


def collect_health(connection: sqlite3.Connection, dds_data_path: Path) -> dict:
    """Compatibility wrapper for 0.1/0.2 callers."""
    return HealthService(connection, dds_data_path).snapshot(watcher_expected=False)
