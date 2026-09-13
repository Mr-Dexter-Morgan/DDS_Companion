from __future__ import annotations

import json
import sqlite3
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Callable

from dds_companion.parser.validation import CaptureValidationError
from dds_companion.services.import_service import ImportResult, ImportService
from dds_companion.watcher.file_events import FileSignature, WatcherEvent


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PendingFile:
    signature: FileSignature
    ready_at: float
    kind: str


@dataclass
class WatcherCounters:
    scans: int = 0
    discovered: int = 0
    changed: int = 0
    deleted: int = 0
    imported: int = 0
    unchanged: int = 0
    failed: int = 0


class CaptureWatcher:
    """Continuously watches DDS capture.json files using a conservative polling loop.

    The watcher intentionally uses only Python's standard library. DDS runs on top of
    BetterDiscord and may publish JSON using either rename or a direct-write fallback,
    so a settle window is used before reading a changed file.
    """

    TRANSIENT_ERRORS = (OSError, UnicodeDecodeError, json.JSONDecodeError)

    def __init__(
        self,
        dds_data_root: str | Path,
        importer: ImportService,
        connection: sqlite3.Connection,
        *,
        poll_interval: float = 0.75,
        settle_seconds: float = 0.50,
        retry_count: int = 3,
        retry_delay: float = 0.15,
        heartbeat_seconds: float = 10.0,
        on_event: Callable[[WatcherEvent], None] | None = None,
    ):
        self.dds_data_root = Path(dds_data_root)
        self.importer = importer
        self.connection = connection
        self.poll_interval = max(0.10, float(poll_interval))
        self.settle_seconds = max(0.05, float(settle_seconds))
        self.retry_count = max(1, int(retry_count))
        self.retry_delay = max(0.01, float(retry_delay))
        self.heartbeat_seconds = max(1.0, float(heartbeat_seconds))
        self.on_event = on_event
        self.known: dict[Path, FileSignature] = {}
        self.pending: dict[Path, PendingFile] = {}
        self.counters = WatcherCounters()
        self._last_heartbeat_monotonic = 0.0

    def discover(self) -> dict[Path, FileSignature]:
        guilds = self.dds_data_root / "guilds"
        if not guilds.is_dir():
            return {}

        found: dict[Path, FileSignature] = {}
        for path in guilds.glob("**/capture.json"):
            try:
                stat = path.stat()
            except OSError:
                continue
            found[path.resolve()] = FileSignature(size=stat.st_size, mtime_ns=stat.st_mtime_ns)
        return found

    def prime(self) -> int:
        """Capture the current filesystem state before the initial full import."""
        self.known = self.discover()
        self.pending.clear()
        return len(self.known)

    def scan_once(self, now: float | None = None) -> list[WatcherEvent]:
        now_mono = time.monotonic() if now is None else float(now)
        self.counters.scans += 1
        current = self.discover()
        events: list[WatcherEvent] = []

        removed = set(self.known) - set(current)
        for path in sorted(removed):
            self.known.pop(path, None)
            self.pending.pop(path, None)
            self.counters.deleted += 1
            event = WatcherEvent(
                kind="deleted",
                path=path,
                detail="capture removed from DDS_Data; archived SQLite data was preserved",
            )
            events.append(event)
            self._emit(event)

        for path, signature in current.items():
            previous = self.known.get(path)
            if previous == signature:
                continue

            kind = "created" if previous is None else "changed"
            pending = self.pending.get(path)
            if pending is None or pending.signature != signature:
                self.pending[path] = PendingFile(
                    signature=signature,
                    ready_at=now_mono + self.settle_seconds,
                    kind=kind,
                )
                if kind == "created":
                    self.counters.discovered += 1
                else:
                    self.counters.changed += 1
                event = WatcherEvent(kind=kind, path=path, detail="waiting for file to settle")
                events.append(event)
                self._emit(event)

        for path, pending in list(self.pending.items()):
            if now_mono < pending.ready_at:
                continue

            current_signature = current.get(path)
            if current_signature is None:
                self.pending.pop(path, None)
                continue

            if current_signature != pending.signature:
                self.pending[path] = PendingFile(
                    signature=current_signature,
                    ready_at=now_mono + self.settle_seconds,
                    kind=pending.kind,
                )
                continue

            event = self._import_pending(path, pending.signature)
            events.append(event)
            self._emit(event)
            self.known[path] = pending.signature
            self.pending.pop(path, None)

        self._maybe_heartbeat(now_mono)
        return events

    def run(self, stop_event: Event | None = None) -> WatcherCounters:
        stop = stop_event or Event()
        self._set_state("watcher_state", "RUNNING")
        self._set_state("watcher_started_at", utc_now())
        self._heartbeat()

        try:
            while not stop.is_set():
                self.scan_once()
                stop.wait(self.poll_interval)
        finally:
            self._set_state("watcher_state", "STOPPED")
            self._set_state("watcher_stopped_at", utc_now())
            self._heartbeat()

        return self.counters

    def _import_pending(self, path: Path, signature: FileSignature) -> WatcherEvent:
        last_error: Exception | None = None

        for attempt in range(1, self.retry_count + 1):
            try:
                result = self.importer.import_file(path)
                if result.skipped_unchanged:
                    self.counters.unchanged += 1
                    self._set_state("watcher_last_event", f"unchanged:{path}")
                    return WatcherEvent(kind="unchanged", path=path, result=result)

                self.counters.imported += 1
                self._set_state("watcher_last_event", f"imported:{path}")
                return WatcherEvent(kind="imported", path=path, result=result)
            except CaptureValidationError as exc:
                # A schema/semantic error will not heal through a short retry.
                last_error = exc
                break
            except self.TRANSIENT_ERRORS as exc:
                last_error = exc
                if attempt < self.retry_count:
                    time.sleep(self.retry_delay)
                    continue
                break
            except Exception as exc:
                # ImportService uses a transaction; an unexpected failure is isolated
                # to this file and must not terminate the watcher loop.
                last_error = exc
                break

        assert last_error is not None
        self.counters.failed += 1
        self.importer.record_failure("watcher_import", str(path), last_error)
        self._set_state("watcher_last_event", f"failed:{path}")
        return WatcherEvent(
            kind="failed",
            path=path,
            detail=f"{type(last_error).__name__}: {last_error}",
        )

    def _set_state(self, key: str, value: str) -> None:
        with self.connection:
            self.connection.execute(
                """
                INSERT INTO application_state(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                (key, value, utc_now()),
            )

    def _heartbeat(self) -> None:
        stamp = utc_now()
        self._set_state("watcher_last_heartbeat", stamp)
        self._last_heartbeat_monotonic = time.monotonic()

    def _maybe_heartbeat(self, now_mono: float) -> None:
        if now_mono - self._last_heartbeat_monotonic >= self.heartbeat_seconds:
            self._heartbeat()

    def _emit(self, event: WatcherEvent) -> None:
        if self.on_event is not None:
            self.on_event(event)
