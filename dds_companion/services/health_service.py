from __future__ import annotations

import json
import re
import sqlite3
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dds_companion.parser.validation import CAPTURE_SCHEMA_VERSION
from dds_companion.updater.check_state import CheckStateStore
from dds_companion.services.discord_probe import probe_discord_process

VALID_STATES = {
    "RUNNING",
    "LIMITED",
    "DEGRADED",  # legacy 0.4.3 DB rows are normalized on read
    "STALE",
    "ERROR",
    "STOPPED",
    "STARTING",
    "UNKNOWN",
}
CRITICAL_SUBSYSTEMS = {"database", "dds_data", "importer", "watcher", "runtime"}
DEFAULT_UPDATE_INTERVAL_HOURS = 24
PLUGIN_HEARTBEAT_MIN_VERSION = (0, 5, 3)
PLUGIN_HEARTBEAT_FILE = "plugin_heartbeat.json"


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except (ValueError, TypeError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _normalize_state(value: str | None) -> str:
    state = str(value or "UNKNOWN").upper()
    return "LIMITED" if state == "DEGRADED" else state


def _version_tuple(value: str | None) -> tuple[int, int, int] | None:
    if not value:
        return None
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", str(value))
    if not match:
        return None
    return tuple(int(part) for part in match.groups())


class HealthService:
    """Own subsystem state and compute the single overall Companion health."""

    def __init__(
        self,
        connection: sqlite3.Connection,
        dds_data_path: str | Path,
        *,
        update_check_state_path: str | Path | None = None,
    ):
        self.connection = connection
        self.dds_data_path = Path(dds_data_path)
        self.update_check_state_path = (
            Path(update_check_state_path) if update_check_state_path else None
        )
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
        normalized = _normalize_state(state)
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
        if normalized in {"LIMITED", "STALE", "ERROR"}:
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

        dds_ok = self._dds_data_available()
        self.set_subsystem(
            "dds_data",
            "RUNNING" if dds_ok else "LIMITED",
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
            state = _normalize_state(row["state"])
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

        dds_ok = self._dds_data_available()
        # Database and DDS_Data are cheap live probes. Their cards describe the
        # filesystem/database now, not merely the state recorded at startup.
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
            "state": "RUNNING" if dds_ok else "LIMITED",
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

        # The watcher thread may still be alive while its source folder is missing.
        # Surface that honestly as WAITING rather than a misleading RUNNING state.
        watcher_info = subsystems.get("watcher")
        if watcher_expected and not dds_ok and watcher_info:
            watcher_info = dict(watcher_info)
            watcher_info["details"] = dict(watcher_info.get("details") or {})
            watcher_info["details"]["underlying_state"] = watcher_info.get("state")
            watcher_info["state"] = "WAITING"
            watcher_info["summary"] = "waiting for DDS_Data source"
            watcher_info["stale"] = False
            subsystems["watcher"] = watcher_info

        subsystems["discord"] = self._discord_snapshot()
        subsystems["plugin"] = self._plugin_snapshot(now, dds_ok=dds_ok)

        # A fresh heartbeat may outlive the Discord process for a short time when
        # Discord is closed abruptly. In that window the heartbeat file is still
        # recent, but the BetterDiscord plugin cannot actually be executing.
        # Keep the heartbeat metadata for diagnostics while making the effective
        # process state truthful.
        if (
            subsystems["discord"].get("state") == "NOT RUNNING"
            and subsystems["plugin"].get("state") in {"RUNNING", "STALE"}
        ):
            plugin_info = dict(subsystems["plugin"])
            plugin_info["details"] = dict(plugin_info.get("details") or {})
            plugin_info["details"]["underlying_heartbeat_state"] = plugin_info.get("state")
            plugin_info["details"]["blocked_by"] = "discord-not-running"
            plugin_info["state"] = "NOT RUNNING"
            plugin_info["summary"] = "Discord is not running — DDS Plugin cannot be active"
            plugin_info["stale"] = False
            subsystems["plugin"] = plugin_info

        subsystems["updates"] = self._updates_snapshot(now)

        reasons: list[dict] = []
        critical_states = {
            name: data["state"]
            for name, data in subsystems.items()
            if name in CRITICAL_SUBSYSTEMS
        }

        overall = "RUNNING"
        if not db_ok or critical_states.get("database") == "ERROR":
            overall = "ERROR"
            reasons.append({
                "subsystem": "database",
                "code": "database-error",
                "message": subsystems["database"]["summary"],
            })
        else:
            if unresolved:
                reasons.append({
                    "subsystem": "importer",
                    "code": "unresolved-failures",
                    "message": f"{unresolved} unresolved import failure(s)",
                })
            if not dds_ok:
                reasons.append({
                    "subsystem": "dds_data",
                    "code": "source-missing",
                    "message": "DDS_Data source is unavailable; archived data remains available",
                })

            importer_state = critical_states.get("importer")
            if importer_state in {"LIMITED", "STALE", "ERROR"}:
                reasons.append({
                    "subsystem": "importer",
                    "code": "importer-limited",
                    "message": subsystems.get("importer", {}).get("summary", "Importer requires attention"),
                })

            watcher_state = critical_states.get("watcher")
            if watcher_expected and watcher_state in {"LIMITED", "STALE", "ERROR"}:
                reasons.append({
                    "subsystem": "watcher",
                    "code": "watcher-limited",
                    "message": subsystems.get("watcher", {}).get("summary", "Watcher requires attention"),
                })

            discord_state = subsystems["discord"]["state"]
            if discord_state == "NOT RUNNING":
                reasons.append({
                    "subsystem": "discord",
                    "code": "discord-not-running",
                    "message": "Discord is not running; live capture is unavailable",
                })

            plugin_state = subsystems["plugin"]["state"]
            if plugin_state in {"UPDATE AVAILABLE", "LIMITED", "STALE", "NOT RUNNING", "ERROR"}:
                reasons.append({
                    "subsystem": "plugin",
                    "code": "plugin-not-ready",
                    "message": subsystems["plugin"]["summary"],
                })

            if reasons:
                overall = "LIMITED"

        if overall == "RUNNING":
            overall_summary = "All capture and archive subsystems are operational"
            tooltip = overall_summary
        elif overall == "ERROR":
            overall_summary = "Critical local archive failure"
            tooltip = "\n".join(f"• {item['message']}" for item in reasons) or overall_summary
        else:
            first = reasons[0]["message"] if reasons else "Some capture features are unavailable"
            extra = len(reasons) - 1
            overall_summary = first if extra <= 0 else f"{first} · +{extra} more"
            tooltip = "\n".join(f"• {item['message']}" for item in reasons)

        last_error_info = self._latest_unresolved_error()
        return {
            "state": overall,
            "summary": overall_summary,
            "tooltip": tooltip,
            "reasons": reasons,
            "database_ok": db_ok,
            "sqlite_quick_check": quick_check,
            "dds_data_found": dds_ok,
            "unresolved_failed_jobs": unresolved,
            "last_error": last_error_info["message"] if last_error_info else None,
            "last_error_info": last_error_info,
            "subsystems": subsystems,
        }

    def _dds_data_available(self) -> bool:
        return self.dds_data_path.is_dir() and (self.dds_data_path / "manifest.json").exists()

    def _manifest_snapshot(self) -> dict:
        path = self.dds_data_path / "manifest.json"
        if not path.is_file():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            return {}
        return value if isinstance(value, dict) else {}

    def _plugin_snapshot(self, now: datetime, *, dds_ok: bool) -> dict:
        heartbeat_path = self.dds_data_path / PLUGIN_HEARTBEAT_FILE
        manifest = self._manifest_snapshot()
        manifest_version = manifest.get("ddsVersion")
        capabilities = manifest.get("capabilities") if isinstance(manifest.get("capabilities"), list) else []
        supports_heartbeat = "plugin-heartbeat-v1" in capabilities
        version_tuple = _version_tuple(manifest_version)
        if version_tuple is not None and version_tuple >= PLUGIN_HEARTBEAT_MIN_VERSION:
            supports_heartbeat = True

        base_details = {
            "heartbeat_file": str(heartbeat_path),
            "manifest_version": manifest_version,
            "supports_heartbeat": supports_heartbeat,
            "required_version": ".".join(str(v) for v in PLUGIN_HEARTBEAT_MIN_VERSION),
            "capture_schema_version": CAPTURE_SCHEMA_VERSION,
            "heartbeat_schema_version": "plugin-heartbeat-v1",
        }

        if not dds_ok:
            return {
                "state": "WAITING",
                "summary": "waiting for DDS_Data before probing DDS Plugin",
                "last_ok_at": None,
                "last_error_at": None,
                "updated_at": None,
                "stale": False,
                "details": base_details,
            }

        if not heartbeat_path.is_file():
            if version_tuple is not None and version_tuple < PLUGIN_HEARTBEAT_MIN_VERSION:
                return {
                    "state": "UPDATE AVAILABLE",
                    "summary": f"DDS Plugin {manifest_version} has no heartbeat support — update recommended",
                    "last_ok_at": None,
                    "last_error_at": None,
                    "updated_at": None,
                    "stale": False,
                    "details": base_details,
                }
            if supports_heartbeat:
                return {
                    "state": "LIMITED",
                    "summary": "DDS Plugin heartbeat file is missing",
                    "last_ok_at": None,
                    "last_error_at": now.isoformat(),
                    "updated_at": None,
                    "stale": False,
                    "details": base_details,
                }
            return {
                "state": "UNKNOWN",
                "summary": "DDS Plugin heartbeat support could not be determined",
                "last_ok_at": None,
                "last_error_at": None,
                "updated_at": None,
                "stale": False,
                "details": base_details,
            }

        try:
            payload = json.loads(heartbeat_path.read_text(encoding="utf-8"))
            if not isinstance(payload, dict):
                raise ValueError("heartbeat JSON root must be an object")
        except (OSError, json.JSONDecodeError, UnicodeDecodeError, ValueError) as exc:
            details = dict(base_details)
            details["error"] = f"{type(exc).__name__}: {exc}"
            return {
                "state": "LIMITED",
                "summary": "DDS Plugin heartbeat is unreadable",
                "last_ok_at": None,
                "last_error_at": now.isoformat(),
                "updated_at": None,
                "stale": False,
                "details": details,
            }

        updated_at = payload.get("updatedAt")
        updated = _parse_iso(updated_at)
        plugin_version = payload.get("pluginVersion") or manifest_version
        state = str(payload.get("state") or "UNKNOWN").upper()
        try:
            interval_ms = max(1000, int(payload.get("heartbeatIntervalMs") or 30000))
        except (TypeError, ValueError):
            interval_ms = 30000
        interval_seconds = interval_ms / 1000.0
        stale_after = max(45.0, interval_seconds * 2.5)
        offline_after = max(90.0, interval_seconds * 5.0)
        age_seconds = None
        if updated is not None:
            age_seconds = max(0.0, (now - updated).total_seconds())

        details = {
            **base_details,
            "plugin_version": plugin_version,
            "reported_state": state,
            "heartbeat_interval_ms": interval_ms,
            "age_seconds": round(age_seconds, 1) if age_seconds is not None else None,
            "stale_after_seconds": stale_after,
            "offline_after_seconds": offline_after,
            "schema_version": payload.get("schemaVersion"),
        }

        if state == "STOPPED":
            return {
                "state": "NOT RUNNING",
                "summary": f"DDS Plugin {plugin_version or 'unknown'} reported STOPPED",
                "last_ok_at": None,
                "last_error_at": None,
                "updated_at": updated_at,
                "stale": False,
                "details": details,
            }

        if updated is None:
            return {
                "state": "LIMITED",
                "summary": "DDS Plugin heartbeat has no valid timestamp",
                "last_ok_at": None,
                "last_error_at": now.isoformat(),
                "updated_at": updated_at,
                "stale": False,
                "details": details,
            }

        if age_seconds is not None and age_seconds > offline_after:
            return {
                "state": "NOT RUNNING",
                "summary": f"DDS Plugin heartbeat stopped {int(age_seconds)} s ago",
                "last_ok_at": updated_at,
                "last_error_at": None,
                "updated_at": updated_at,
                "stale": True,
                "details": details,
            }

        if age_seconds is not None and age_seconds > stale_after:
            return {
                "state": "STALE",
                "summary": f"DDS Plugin heartbeat is stale ({int(age_seconds)} s)",
                "last_ok_at": updated_at,
                "last_error_at": None,
                "updated_at": updated_at,
                "stale": True,
                "details": details,
            }

        return {
            "state": "RUNNING",
            "summary": f"DDS Plugin {plugin_version or 'unknown'} heartbeat active",
            "last_ok_at": updated_at,
            "last_error_at": None,
            "updated_at": updated_at,
            "stale": False,
            "details": details,
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
        interval_hours = DEFAULT_UPDATE_INTERVAL_HOURS
        last_attempt = last_success = last_error = None

        # 0.7.1: Status and updater share one source of truth. The updater owns
        # check_state.json; Health only observes it and never performs networking.
        if self.update_check_state_path is not None and self.update_check_state_path.is_file():
            check_state = CheckStateStore(self.update_check_state_path).load()
            last_attempt = check_state.last_attempt_at
            last_success = check_state.last_success_at
            last_error = check_state.last_error

        if not any((last_attempt, last_success, last_error)):
            # Backward-compatible fallback for pre-0.7.1 databases. New updater
            # checks no longer depend on SQLite telemetry.
            keys = {
                row["key"]: row["value"]
                for row in self.connection.execute(
                    "SELECT key, value FROM application_state WHERE key LIKE 'update_%'"
                ).fetchall()
            }
            try:
                interval_hours = max(
                    1,
                    int(keys.get("update_interval_hours") or DEFAULT_UPDATE_INTERVAL_HOURS),
                )
            except (TypeError, ValueError):
                interval_hours = DEFAULT_UPDATE_INTERVAL_HOURS
            last_attempt = keys.get("update_last_attempt")
            last_success = keys.get("update_last_success")
            last_error = keys.get("update_last_error")
            next_check = keys.get("update_next_check")
        else:
            next_check = None

        if next_check is None and last_attempt:
            parsed = _parse_iso(last_attempt)
            if parsed is not None:
                next_check = (parsed + timedelta(hours=interval_hours)).isoformat()

        attempt_dt = _parse_iso(last_attempt)
        success_dt = _parse_iso(last_success)
        if last_error and last_attempt:
            state = "FAILED"
            summary = f"Last update check failed · interval {interval_hours} h"
        elif last_success and (
            attempt_dt is None or success_dt is None or success_dt >= attempt_dt
        ):
            state = "OK"
            summary = f"Last update check succeeded · interval {interval_hours} h"
        elif last_attempt:
            state = "UNKNOWN"
            summary = f"Last update check has no recorded result · interval {interval_hours} h"
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
