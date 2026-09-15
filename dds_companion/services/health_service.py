from __future__ import annotations

import json
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dds_companion.services.discord_probe import probe_discord_process

VALID_STATES = {"RUNNING", "DEGRADED", "STALE", "ERROR", "STOPPED", "STARTING", "UNKNOWN"}
CRITICAL_SUBSYSTEMS = {"database", "dds_data", "importer", "watcher", "runtime"}
DEFAULT_UPDATE_INTERVAL_HOURS = 6


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
    """Own subsystem state and compute the single overall Companion health."""

    def __init__(self, connection: sqlite3.Connection, dds_data_path: str | Path):
        self.connection = connection
        self.dds_data_path = Path(dds_data_path)
        self._discord_probe_monotonic = 0.0
        self._discord_cache: dict | None = None

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
        if normalized in {"DEGRADED", "STALE", "ERROR"}:
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
                    state = "STALE"
                    stale = True
                    details = dict(details)
                    details["stale_after_seconds"] = stale_after_seconds
            subsystems[row["subsystem"]] = {
                "state": state,
                "summary": "watcher heartbeat is stale" if stale else row["summary"],
                "last_ok_at": row["last_ok_at"],
                "last_error_at": row["last_error_at"],
                "updated_at": row["updated_at"],
                "stale": stale,
                "details": details,
            }

        dds_ok = self.dds_data_path.is_dir() and (self.dds_data_path / "manifest.json").exists()
        # Database and DDS_Data are cheap live probes.  Their cards must describe the
        # filesystem/database *now*, not merely repeat the state recorded at startup.
        database_previous = subsystems.get("database", {})
        subsystems["database"] = {
            "state": "RUNNING" if db_ok else "ERROR",
            "summary": "SQLite quick_check ok" if db_ok else f"SQLite quick_check failed: {quick_check}",
            "stale": False,
            "details": {"quick_check": quick_check},
            "last_ok_at": now.isoformat() if db_ok else database_previous.get("last_ok_at"),
            "last_error_at": database_previous.get("last_error_at"),
            "updated_at": now.isoformat(),
        }
        dds_previous = subsystems.get("dds_data", {})
        subsystems["dds_data"] = {
            "state": "RUNNING" if dds_ok else "DEGRADED",
            "summary": "DDS_Data available" if dds_ok else "DDS_Data or manifest.json is missing",
            "stale": False,
            "details": {
                "path": str(self.dds_data_path),
                "manifest_found": (self.dds_data_path / "manifest.json").exists(),
            },
            "last_ok_at": now.isoformat() if dds_ok else dds_previous.get("last_ok_at"),
            "last_error_at": dds_previous.get("last_error_at"),
            "updated_at": now.isoformat(),
        }

        # Informational probes live in the Health view but must never turn the archive
        # red merely because Discord is closed or update checking is not configured yet.
        subsystems["discord"] = self._discord_snapshot()
        subsystems["updates"] = self._updates_snapshot(now)

        overall = "RUNNING"
        critical_states = {
            name: data["state"]
            for name, data in subsystems.items()
            if name in CRITICAL_SUBSYSTEMS
        }
        if not db_ok or critical_states.get("database") == "ERROR":
            overall = "ERROR"
        elif unresolved or not dds_ok or any(
            state in {"DEGRADED", "STALE", "ERROR"} for state in critical_states.values()
        ):
            overall = "DEGRADED"
        elif watcher_expected and critical_states.get("watcher") not in {"RUNNING", "STARTING"}:
            overall = "DEGRADED"

        last_error_info = self._latest_unresolved_error()
        return {
            "state": overall,
            "database_ok": db_ok,
            "sqlite_quick_check": quick_check,
            "dds_data_found": dds_ok,
            "unresolved_failed_jobs": unresolved,
            "last_error": last_error_info["message"] if last_error_info else None,
            "last_error_info": last_error_info,
            "subsystems": subsystems,
        }

    def _discord_snapshot(self, probe_interval_seconds: float = 5.0) -> dict:
        now_mono = time.monotonic()
        if self._discord_cache is None or now_mono - self._discord_probe_monotonic >= probe_interval_seconds:
            result = probe_discord_process()
            self._discord_probe_monotonic = now_mono
            self._discord_cache = {
                "state": result.state,
                "summary": result.summary,
                "last_ok_at": result.checked_at if result.state == "RUNNING" else None,
                "last_error_at": None,
                "updated_at": result.checked_at,
                "stale": False,
                "details": {"detected_processes": list(result.detected_processes)},
            }
        return dict(self._discord_cache)

    def _updates_snapshot(self, now: datetime) -> dict:
        keys = {
            row["key"]: row["value"]
            for row in self.connection.execute(
                "SELECT key, value FROM application_state WHERE key LIKE 'update_%'"
            ).fetchall()
        }
        try:
            interval_hours = max(1, int(keys.get("update_interval_hours") or DEFAULT_UPDATE_INTERVAL_HOURS))
        except (TypeError, ValueError):
            interval_hours = DEFAULT_UPDATE_INTERVAL_HOURS

        last_attempt = keys.get("update_last_attempt")
        last_success = keys.get("update_last_success")
        next_check = keys.get("update_next_check")
        last_error = keys.get("update_last_error")
        if next_check is None and last_attempt:
            parsed = _parse_iso(last_attempt)
            if parsed is not None:
                next_check = (parsed + timedelta(hours=interval_hours)).isoformat()

        if last_error and last_attempt:
            state = "FAILED"
            summary = f"Last update check failed · interval {interval_hours} h"
        elif last_success:
            state = "OK"
            summary = f"Last update check succeeded · interval {interval_hours} h"
        else:
            state = "NEVER"
            summary = f"No update checks recorded yet · interval {interval_hours} h"

        return {
            "state": state,
            "summary": summary,
            "last_ok_at": last_success,
            "last_error_at": last_attempt if last_error else None,
            "updated_at": last_attempt or last_success,
            "stale": False,
            "details": {
                "interval_hours": interval_hours,
                "last_attempt_at": last_attempt,
                "last_success_at": last_success,
                "next_check_at": next_check,
                "error": last_error,
                "scheduler_now": now.isoformat(),
            },
        }

    def _latest_unresolved_error(self) -> dict | None:
        row = self.connection.execute(
            """
            SELECT job_kind, target, error_type, error_message, created_at
            FROM failed_jobs
            WHERE resolved_at IS NULL
            ORDER BY created_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
        if row is None:
            return None
        return {
            "subsystem": row["job_kind"],
            "target": row["target"],
            "error_type": row["error_type"],
            "message": f"{row['error_type']}: {row['error_message']}",
            "occurred_at": row["created_at"],
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
