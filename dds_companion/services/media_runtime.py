from __future__ import annotations

import queue
import threading
import time
from pathlib import Path

from dds_companion.core.settings import SettingsStore
from dds_companion.services.activity_service import ActivityService
from dds_companion.services.health_service import HealthService
from dds_companion.services.media_backfill_service import MediaBackfillService
from dds_companion.services.media_cache_service import MediaCacheService
from dds_companion.storage.database import connect_database


class MediaBackfillRuntime:
    """Independent media worker that cannot block archive import/UI runtime."""

    def __init__(
        self,
        *,
        database_path: str | Path,
        media_root: str | Path,
        settings_path: str | Path,
        dds_data_path: str | Path,
        stop_event: threading.Event,
        wake_event: threading.Event | None = None,
        control_queue: queue.Queue[bool] | None = None,
    ):
        self.database_path = Path(database_path)
        self.media_root = Path(media_root)
        self.settings_path = Path(settings_path)
        self.dds_data_path = Path(dds_data_path)
        self.stop_event = stop_event
        self.wake_event = wake_event or threading.Event()
        self.control_queue = control_queue if control_queue is not None else queue.Queue()

    def wake(self) -> None:
        self.wake_event.set()

    def run(self) -> None:
        connection = None
        try:
            connection = connect_database(self.database_path)
            activity = ActivityService(connection)
            health = HealthService(connection, self.dds_data_path)
            settings_store = SettingsStore(self.settings_path)
            service = MediaBackfillService(connection, self.media_root, activity=activity)
            cache_maintenance = MediaCacheService(self.media_root, self.database_path)
            health.set_subsystem("media", "STARTING", "media backfill worker starting")
            projected = service.registry.bootstrap_from_archive()
            if projected:
                activity.publish(
                    subsystem="media",
                    event_type="media_registry_bootstrap",
                    summary=f"Media registry projected {projected} existing attachment(s)",
                    details={"attachments_projected": projected},
                )
            last_enabled: bool | None = None
            last_maintenance = 0.0

            while not self.stop_event.is_set():
                # GUI control changes are queued, not represented by a single Event.
                # Rapid Off -> On -> Off actions therefore cannot be coalesced and
                # Activity records every user-visible transition in order.
                while True:
                    try:
                        requested_enabled = bool(self.control_queue.get_nowait())
                    except queue.Empty:
                        break
                    if requested_enabled:
                        requeued = service.registry.requeue_manual_clear_evictions()
                        activity.publish(
                            subsystem="media",
                            event_type="media_backfill_enabled",
                            summary="Automatic media backfill enabled",
                        )
                        if requeued:
                            activity.publish(
                                subsystem="media",
                                event_type="media_manual_clear_requeued",
                                summary=f"Manual media cache clear re-queued {requeued} attachment(s)",
                                details={"requeued": requeued},
                            )
                    else:
                        activity.publish(
                            subsystem="media",
                            event_type="media_backfill_disabled",
                            summary="Automatic media backfill disabled",
                        )
                    last_enabled = requested_enabled

                settings = settings_store.load()
                enabled = bool(settings.media_autodownload_enabled)
                if not enabled:
                    # External config edits still get truthful state even when no
                    # GUI command was queued. GUI changes were already logged above.
                    if last_enabled is True:
                        activity.publish(
                            subsystem="media",
                            event_type="media_backfill_disabled",
                            summary="Automatic media backfill disabled",
                        )
                    if last_enabled is not False:
                        health.set_subsystem(
                            "media",
                            "STOPPED",
                            "automatic media backfill is disabled",
                            details=service.counts(),
                        )
                    last_enabled = False
                    self._wait(2.0)
                    continue

                if last_enabled is not True:
                    activity.publish(
                        subsystem="media",
                        event_type="media_backfill_enabled",
                        summary="Automatic media backfill enabled",
                    )
                last_enabled = True

                try:
                    cycle = service.process_once(settings)
                    now_mono = time.monotonic()
                    if cycle.cached or now_mono - last_maintenance >= 60.0:
                        maintenance = cache_maintenance.enforce(settings)
                        last_maintenance = now_mono
                        if maintenance.files_removed or maintenance.errors:
                            activity.publish(
                                level="WARNING" if maintenance.errors else "INFO",
                                subsystem="media",
                                event_type="media_cache_maintenance",
                                summary=(
                                    f"Media cache maintenance: removed {maintenance.files_removed} file(s), "
                                    f"errors {maintenance.errors}"
                                ),
                                details=maintenance.to_dict(),
                                storage_delta_bytes=-int(maintenance.bytes_removed),
                            )
                    counts = service.counts()
                    limited = counts["retryable_failed"] + counts["permanent_failed"] + counts["stale_url"]
                    state = "LIMITED" if limited else "RUNNING"
                    summary = (
                        f"media cache {counts['cached']}/{counts['known']} · "
                        f"queued {counts['queued']} · downloading {counts['downloading']}"
                    )
                    if limited:
                        summary += (
                            f" · retry {counts['retryable_failed']} · stale {counts['stale_url']}"
                            f" · failed {counts['permanent_failed']}"
                        )
                    health.set_subsystem("media", state, summary, details={**counts, "last_cycle": cycle.to_dict()})
                    # Keep draining a non-empty queue briskly; idle workers back off.
                    busy = cycle.claimed > 0 or cycle.planned.queued > 0
                    self._wait(0.25 if busy else 2.0)
                except Exception as exc:
                    health.set_subsystem(
                        "media",
                        "LIMITED",
                        "media worker iteration failed; archive runtime continues",
                        error=f"{type(exc).__name__}: {exc}",
                    )
                    activity.publish(
                        level="ERROR",
                        subsystem="media",
                        event_type="media_worker_iteration_failed",
                        summary="Media worker iteration failed; retrying later",
                        details={"error_type": type(exc).__name__, "error": str(exc)},
                    )
                    self._wait(5.0)

            health.set_subsystem("media", "STOPPED", "media backfill worker stopped cleanly")
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass

    def _wait(self, seconds: float) -> None:
        deadline = time.monotonic() + max(0.0, seconds)
        while not self.stop_event.is_set():
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return
            if self.wake_event.wait(timeout=min(remaining, 0.5)):
                self.wake_event.clear()
                return
