from __future__ import annotations

import queue
import time
from pathlib import Path
from threading import Event
from typing import Callable

from dds_companion import __version__
from dds_companion.core.paths import RuntimePaths, build_runtime_paths, ensure_runtime_dirs
from dds_companion.services.activity_service import ActivityRecord, ActivityService
from dds_companion.services.health_service import HealthService
from dds_companion.services.import_service import ImportService
from dds_companion.services.library_service import LibraryService
from dds_companion.services.media_runtime import MediaBackfillRuntime
from dds_companion.services.runtime_monitor import RuntimeMonitor
from dds_companion.services.stats_service import StatsService
from dds_companion.storage.database import connect_database
from dds_companion.watcher.capture_watcher import CaptureWatcher
from dds_companion.watcher.file_events import WatcherEvent

SnapshotSink = Callable[[dict], None]
ActivitySink = Callable[[dict], None]
WatchSink = Callable[[dict], None]
ErrorSink = Callable[[str], None]
StoppedSink = Callable[[], None]
LibraryMessageSink = Callable[[dict], None]


class GuiRuntime:
    """Own the archive runtime on one background thread.

    SQLite remains thread-confined. The Qt thread only receives plain dicts through
    signal callbacks and can therefore never accidentally issue archive writes.
    """

    def __init__(
        self,
        *,
        dds_data: str | Path | None = None,
        app_data: str | Path | None = None,
        poll_ms: int = 750,
        settle_ms: int = 500,
        snapshot_sink: SnapshotSink | None = None,
        activity_sink: ActivitySink | None = None,
        watch_sink: WatchSink | None = None,
        error_sink: ErrorSink | None = None,
        stopped_sink: StoppedSink | None = None,
        library_message_sink: LibraryMessageSink | None = None,
    ):
        self.paths: RuntimePaths = build_runtime_paths(dds_data, app_data)
        self.poll_ms = max(100, int(poll_ms))
        self.settle_ms = max(50, int(settle_ms))
        self.snapshot_sink = snapshot_sink
        self.activity_sink = activity_sink
        self.watch_sink = watch_sink
        self.error_sink = error_sink
        self.stopped_sink = stopped_sink
        self.library_message_sink = library_message_sink
        self.stop_event = Event()
        self.refresh_event = Event()
        self.media_wake_event = Event()
        self.media_control_queue: queue.Queue[object] = queue.Queue()
        self.library_control_queue: queue.Queue[dict] = queue.Queue()
        self._last_snapshot_at = 0.0
        self._last_library_refresh_at = 0.0
        self._library_cache: list[dict] = []
        self._last_health_state: str | None = None
        self._last_health_reason_signature: tuple[tuple[str, str], ...] = ()

    def request_refresh(self) -> None:
        self.refresh_event.set()

    def request_media_wake(self) -> None:
        self.media_wake_event.set()

    def request_media_autodownload_change(self, enabled: bool) -> None:
        self.media_control_queue.put(bool(enabled))
        self.media_wake_event.set()

    def request_media_retry(self, media_key: str) -> None:
        self.media_control_queue.put({"action": "retry", "media_key": str(media_key)})
        self.media_wake_event.set()

    def request_media_ignore(self, media_key: str) -> None:
        self.media_control_queue.put({"action": "ignore", "media_key": str(media_key)})
        self.media_wake_event.set()

    def request_media_ignore_all(self) -> None:
        self.media_control_queue.put({"action": "ignore_all"})
        self.media_wake_event.set()

    def request_media_clear_processed(self) -> None:
        self.media_control_queue.put({"action": "clear_processed"})
        self.media_wake_event.set()

    def request_library_messages(self, request: dict) -> None:
        self.library_control_queue.put({"action": "messages", **dict(request)})
        self.refresh_event.set()

    def request_export_rule_change(self, scope_kind: str, scope_id: str, mode: str) -> None:
        self.library_control_queue.put({
            "action": "export_rule",
            "scope_kind": str(scope_kind),
            "scope_id": str(scope_id),
            "mode": str(mode),
        })
        self.refresh_event.set()

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        ensure_runtime_dirs(self.paths)
        connection = None
        activity: ActivityService | None = None
        health: HealthService | None = None
        media_thread = None
        try:
            connection = connect_database(self.paths.database)
            importer = ImportService(connection)
            stats = StatsService(
                connection,
                self.paths.database,
                self.paths.dds_data,
                cache_path=self.paths.cache,
                media_path=self.paths.media,
                logs_path=self.paths.logs,
                backups_path=self.paths.backups,
                config_path=self.paths.config,
            )
            activity = ActivityService(connection)
            health = HealthService(connection, self.paths.dds_data)
            library = LibraryService(connection)
            monitor = RuntimeMonitor(activity, health)

            if self.activity_sink is not None:
                activity.subscribe(lambda record: self._safe(self.activity_sink, record.to_dict()))

            health.refresh_core(watcher_expected=True, watcher_state="STARTING")
            health.set_subsystem("importer", "STARTING", "initial DDS_Data synchronization")
            activity.publish(
                subsystem="runtime",
                event_type="session_started",
                summary=f"DDS Companion {__version__} GUI session started",
                details={"mode": "gui"},
            )

            watcher = CaptureWatcher(
                self.paths.dds_data,
                importer,
                connection,
                poll_interval=self.poll_ms / 1000.0,
                settle_seconds=self.settle_ms / 1000.0,
                on_event=None,
                on_state=monitor.watcher_state,
                on_heartbeat=monitor.watcher_heartbeat,
            )
            watcher.prime()

            import_result = importer.import_all(self.paths.dds_data)
            if import_result.failed:
                health.set_subsystem(
                    "importer",
                    "LIMITED",
                    f"initial sync completed with {import_result.failed} failed capture(s)",
                )
            else:
                health.set_subsystem("importer", "RUNNING", "initial sync completed successfully")

            activity.publish(
                level="WARNING" if import_result.failed else "INFO",
                subsystem="importer",
                event_type="startup_sync",
                summary=(
                    f"Initial sync: +{import_result.messages_inserted} new, "
                    f"{import_result.messages_updated} refreshed, {import_result.failed} failed"
                ),
                details={
                    "files_seen": import_result.files_seen,
                    "imported": import_result.imported,
                    "unchanged": import_result.skipped_unchanged,
                    "failed": import_result.failed,
                },
                messages_new=import_result.messages_inserted,
                messages_refreshed=import_result.messages_updated,
                attachments_registered=import_result.attachments_registered,
                embeds_registered=import_result.embeds_registered,
            )
            health.set_subsystem("watcher", "RUNNING", "watcher armed and ready")

            # Media backfill owns a separate SQLite connection/thread. Slow CDN or
            # disk work can therefore never stall capture watcher/import/UI snapshots.
            media_runtime = MediaBackfillRuntime(
                database_path=self.paths.database,
                media_root=self.paths.media,
                settings_path=self.paths.settings,
                dds_data_path=self.paths.dds_data,
                stop_event=self.stop_event,
                wake_event=self.media_wake_event,
                control_queue=self.media_control_queue,
            )
            import threading
            media_thread = threading.Thread(
                target=media_runtime.run, name="dds-media-backfill", daemon=True
            )
            media_thread.start()
            self.media_wake_event.set()

            self._library_cache = library.snapshot()
            self._last_library_refresh_at = time.monotonic()
            self._emit_snapshot(stats, health, activity, library, force=True)

            def on_watcher_event(event: WatcherEvent) -> None:
                monitor.handle_watcher_event(event)
                if self.watch_sink is not None:
                    self._safe(
                        self.watch_sink,
                        {
                            "kind": event.kind,
                            "path": str(event.path),
                            "detail": event.detail,
                            "result": event.result.__dict__ if event.result else None,
                        },
                    )
                if event.kind == "imported":
                    self.media_wake_event.set()
                if event.kind in {"imported", "failed", "deleted"}:
                    # Structural changes are uncommon; refresh the Library only on
                    # meaningful archive events, not on every filesystem scan.
                    self._library_cache = library.snapshot()
                    self._last_library_refresh_at = time.monotonic()
                    self._emit_snapshot(stats, health, activity, library, force=True)

            watcher.on_event = on_watcher_event
            watcher.scan_once()

            def tick() -> None:
                force = self.refresh_event.is_set()
                if force:
                    self.refresh_event.clear()
                library_changed = self._process_library_commands(library)
                if library_changed:
                    self._library_cache = library.snapshot()
                    self._last_library_refresh_at = time.monotonic()
                self._emit_snapshot(
                    stats, health, activity, library, force=force or library_changed
                )

            watcher.run(self.stop_event, on_tick=tick)

            final_stats = stats.snapshot(force_storage=True).to_dict()
            final_health = health.snapshot(watcher_expected=False)
            activity.publish(
                subsystem="runtime",
                event_type="session_stopped",
                summary=(
                    f"GUI session stopped cleanly; session messages "
                    f"+{final_stats['session_messages_added']}"
                ),
                details={"health": final_health["state"]},
            )
            self._emit_snapshot(stats, health, activity, library, force=True, watcher_expected=False)
        except Exception as exc:
            if health is not None:
                health.set_subsystem(
                    "runtime",
                    "ERROR",
                    "GUI runtime stopped after an unexpected error",
                    error=f"{type(exc).__name__}: {exc}",
                )
            if activity is not None:
                activity.publish(
                    level="ERROR",
                    subsystem="runtime",
                    event_type="gui_runtime_crashed",
                    summary="GUI runtime stopped after an unexpected error",
                    details={"error_type": type(exc).__name__, "error": str(exc)},
                )
            self._safe(self.error_sink, f"{type(exc).__name__}: {exc}")
        finally:
            # A media subsystem failure must never outlive the archive runtime.
            self.stop_event.set()
            self.media_wake_event.set()
            if media_thread is not None and media_thread.is_alive():
                media_thread.join(timeout=5.0)
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
            self._safe(self.stopped_sink)


    def _process_library_commands(self, library: LibraryService) -> bool:
        changed = False
        while True:
            try:
                command = self.library_control_queue.get_nowait()
            except queue.Empty:
                break
            action = str(command.get("action") or "")
            try:
                if action == "export_rule":
                    library.set_export_rule(
                        str(command.get("scope_kind") or ""),
                        str(command.get("scope_id") or ""),
                        str(command.get("mode") or "DEFAULT"),
                    )
                    changed = True
                elif action == "messages":
                    payload = library.message_page(
                        str(command.get("scope_kind") or ""),
                        str(command.get("scope_id") or ""),
                        limit=int(command.get("limit") or 50),
                        before_timestamp=command.get("before_timestamp"),
                        before_id=command.get("before_id"),
                    )
                    payload.update({
                        "scope_kind": str(command.get("scope_kind") or ""),
                        "scope_id": str(command.get("scope_id") or ""),
                        "generation": command.get("generation"),
                        "reset": bool(command.get("reset", False)),
                    })
                    self._safe(self.library_message_sink, payload)
            except Exception as exc:
                if action == "messages":
                    self._safe(
                        self.library_message_sink,
                        {
                            "scope_kind": str(command.get("scope_kind") or ""),
                            "scope_id": str(command.get("scope_id") or ""),
                            "generation": command.get("generation"),
                            "reset": bool(command.get("reset", False)),
                            "messages": [],
                            "has_more": False,
                            "error": f"{type(exc).__name__}: {exc}",
                        },
                    )
                else:
                    self._safe(self.error_sink, f"Library command failed: {type(exc).__name__}: {exc}")
        return changed

    def _emit_snapshot(
        self,
        stats: StatsService,
        health: HealthService,
        activity: ActivityService,
        library: LibraryService,
        *,
        force: bool = False,
        watcher_expected: bool = True,
    ) -> None:
        now = time.monotonic()
        if not force and now - self._last_snapshot_at < 2.0:
            return
        self._last_snapshot_at = now

        # Refresh the Library cache occasionally even if no import event was emitted;
        # this also makes manual Refresh useful after future DB maintenance tools.
        if force or now - self._last_library_refresh_at > 15.0:
            self._library_cache = library.snapshot()
            self._last_library_refresh_at = now

        health_snapshot = health.snapshot(watcher_expected=watcher_expected)
        self._record_health_transition(activity, health_snapshot)

        payload = {
            "version": __version__,
            "paths": {
                "dds_data": str(self.paths.dds_data),
                "app_data": str(self.paths.app_data),
                "database": str(self.paths.database),
                "logs": str(self.paths.logs),
                "cache": str(self.paths.cache),
                "media": str(self.paths.media),
                "backups": str(self.paths.backups),
                "config": str(self.paths.config),
                "settings": str(self.paths.settings),
            },
            "watcher": {"poll_ms": self.poll_ms, "settle_ms": self.settle_ms},
            "stats": stats.snapshot(force_storage=force).to_dict(),
            "health": health_snapshot,
            "activity": [record.to_dict() for record in activity.recent(100)],
            "library": self._library_cache,
        }
        self._safe(self.snapshot_sink, payload)

    def _record_health_transition(self, activity: ActivityService, health_snapshot: dict) -> None:
        state = str(health_snapshot.get("state") or "UNKNOWN").upper()
        reasons = health_snapshot.get("reasons") or []
        reason_signature = tuple(
            (str(item.get("subsystem") or "unknown"), str(item.get("message") or ""))
            for item in reasons
        )

        previous_state = self._last_health_state
        previous_reasons = self._last_health_reason_signature
        self._last_health_state = state
        self._last_health_reason_signature = reason_signature

        if previous_state is None:
            if state != "RUNNING":
                activity.publish(
                    level="ERROR" if state == "ERROR" else "WARNING",
                    subsystem="health",
                    event_type="health_initial_state",
                    summary=f"Health initial state: {state} — {health_snapshot.get('summary', 'attention required')}",
                    details={"state": state, "reasons": reasons},
                )
            return

        if previous_state == state and previous_reasons == reason_signature:
            return

        if state == "RUNNING":
            summary = f"Health: {previous_state} → RUNNING — all monitored components recovered"
            level = "INFO"
            event_type = "health_recovered"
        elif previous_state != state:
            summary = f"Health: {previous_state} → {state} — {health_snapshot.get('summary', 'attention required')}"
            level = "ERROR" if state == "ERROR" else "WARNING"
            event_type = "health_state_changed"
        else:
            summary = f"Health {state} reason changed — {health_snapshot.get('summary', 'attention required')}"
            level = "ERROR" if state == "ERROR" else "WARNING"
            event_type = "health_reason_changed"

        activity.publish(
            level=level,
            subsystem="health",
            event_type=event_type,
            summary=summary,
            details={
                "previous_state": previous_state,
                "state": state,
                "reasons": reasons,
            },
        )

    @staticmethod
    def _safe(callback: Callable | None, *args) -> None:
        if callback is None:
            return
        try:
            callback(*args)
        except Exception:
            # GUI transport is an observer. Presentation bugs must never interrupt
            # the archive pipeline or prevent a clean shutdown.
            pass
