from __future__ import annotations

from pathlib import Path

from dds_companion.services.activity_service import ActivityRecord, ActivityService
from dds_companion.services.health_service import HealthService
from dds_companion.watcher.file_events import WatcherEvent


class RuntimeMonitor:
    """Translate low-level watcher facts into durable human activity + health state."""

    def __init__(self, activity: ActivityService, health: HealthService):
        self.activity = activity
        self.health = health

    def watcher_state(self, state: str) -> None:
        normalized = state.upper()
        summary = {
            "STARTING": "watcher starting",
            "RUNNING": "watcher active",
            "STOPPED": "watcher stopped cleanly",
            "ERROR": "watcher stopped with an error",
        }.get(normalized, f"watcher {normalized.lower()}")
        self.health.set_subsystem("watcher", normalized, summary)

    def watcher_heartbeat(self) -> None:
        self.health.heartbeat("watcher", "watcher active")

    def handle_watcher_event(self, event: WatcherEvent) -> ActivityRecord | None:
        if event.kind == "imported" and event.result is not None:
            unresolved = self.health.unresolved_failed_jobs()
            if unresolved:
                self.health.set_subsystem(
                    "importer",
                    "LIMITED",
                    f"last capture imported; {unresolved} unresolved failure(s) remain",
                )
            else:
                self.health.set_subsystem("importer", "RUNNING", "last capture imported successfully")
            return self.activity.publish_import_result(capture_path=event.path, result=event.result)

        if event.kind == "failed":
            self.health.set_subsystem(
                "importer",
                "LIMITED",
                "one capture failed; watcher continues",
                error=event.detail,
                details={"capture_path": str(Path(event.path).resolve())},
            )
            return self.activity.publish(
                level="ERROR",
                subsystem="importer",
                event_type="capture_failed",
                summary=f"Capture import failed: {Path(event.path).name}",
                details={"error": event.detail},
                capture_path=event.path,
            )

        if event.kind == "deleted":
            return self.activity.publish(
                level="INFO",
                subsystem="watcher",
                event_type="capture_removed",
                summary="Source capture removed; archived data preserved",
                details={"archive_preserved": True},
                capture_path=event.path,
            )

        # created/changed are transient settling signals, and unchanged snapshots are
        # intentionally not persisted to avoid turning Activity into filesystem spam.
        return None
