from __future__ import annotations

import json
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Callable, Iterable

from dds_companion.services.import_service import ImportResult


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class ActivityRecord:
    id: int | None
    occurred_at: str
    level: str
    subsystem: str
    event_type: str
    summary: str
    details: dict
    capture_path: str | None = None
    guild_id: str | None = None
    parent_channel_id: str | None = None
    thread_id: str | None = None
    messages_new: int = 0
    messages_refreshed: int = 0
    attachments_registered: int = 0
    embeds_registered: int = 0
    storage_delta_bytes: int = 0
    persisted: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


class ActivityService:
    """Durable + subscribable human activity stream for CLI today and GUI later.

    Observability must never be able to break the archive pipeline. A failed
    activity insert therefore returns a non-persisted record and still notifies
    in-memory subscribers; subscriber failures are isolated from one another.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection
        self._subscribers: list[Callable[[ActivityRecord], None]] = []
        self._lock = RLock()

    def subscribe(self, callback: Callable[[ActivityRecord], None]) -> Callable[[], None]:
        with self._lock:
            self._subscribers.append(callback)

        def unsubscribe() -> None:
            with self._lock:
                try:
                    self._subscribers.remove(callback)
                except ValueError:
                    pass

        return unsubscribe

    def publish(
        self,
        *,
        level: str = "INFO",
        subsystem: str,
        event_type: str,
        summary: str,
        details: dict | None = None,
        capture_path: str | Path | None = None,
        guild_id: str | None = None,
        parent_channel_id: str | None = None,
        thread_id: str | None = None,
        messages_new: int = 0,
        messages_refreshed: int = 0,
        attachments_registered: int = 0,
        embeds_registered: int = 0,
        storage_delta_bytes: int = 0,
        occurred_at: str | None = None,
    ) -> ActivityRecord:
        stamp = occurred_at or utc_now()
        normalized_level = level.upper()
        payload = details or {}
        path_text = str(Path(capture_path).resolve()) if capture_path else None
        record_id: int | None = None
        persisted = True

        try:
            with self.connection:
                cursor = self.connection.execute(
                    """
                    INSERT INTO activity_events(
                        occurred_at, level, subsystem, event_type, summary, details_json,
                        capture_path, guild_id, parent_channel_id, thread_id,
                        messages_new, messages_refreshed, attachments_registered,
                        embeds_registered, storage_delta_bytes
                    ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        stamp,
                        normalized_level,
                        subsystem,
                        event_type,
                        summary,
                        json.dumps(payload, ensure_ascii=False, sort_keys=True),
                        path_text,
                        guild_id,
                        parent_channel_id,
                        thread_id,
                        int(messages_new),
                        int(messages_refreshed),
                        int(attachments_registered),
                        int(embeds_registered),
                        int(storage_delta_bytes),
                    ),
                )
                record_id = int(cursor.lastrowid)
        except sqlite3.Error:
            persisted = False

        record = ActivityRecord(
            id=record_id,
            occurred_at=stamp,
            level=normalized_level,
            subsystem=subsystem,
            event_type=event_type,
            summary=summary,
            details=payload,
            capture_path=path_text,
            guild_id=guild_id,
            parent_channel_id=parent_channel_id,
            thread_id=thread_id,
            messages_new=int(messages_new),
            messages_refreshed=int(messages_refreshed),
            attachments_registered=int(attachments_registered),
            embeds_registered=int(embeds_registered),
            storage_delta_bytes=int(storage_delta_bytes),
            persisted=persisted,
        )
        self._notify(record)
        return record

    def publish_import_result(
        self,
        *,
        capture_path: str | Path,
        result: ImportResult,
        event_type: str = "capture_imported",
    ) -> ActivityRecord:
        path = str(Path(capture_path).resolve())
        row = self.connection.execute(
            """
            SELECT guild_id, parent_channel_id, thread_id, capture_revision, message_count
            FROM capture_imports
            WHERE capture_path=? AND status='imported'
            ORDER BY id DESC LIMIT 1
            """,
            (path,),
        ).fetchone()

        context = dict(row) if row else {}
        return self.publish(
            subsystem="importer",
            event_type=event_type,
            summary=(
                f"+{result.messages_inserted} messages imported, "
                f"{result.messages_updated} existing refreshed"
            ),
            details={
                "capture_revision": context.get("capture_revision"),
                "capture_message_count": context.get("message_count"),
            },
            capture_path=path,
            guild_id=context.get("guild_id"),
            parent_channel_id=context.get("parent_channel_id"),
            thread_id=context.get("thread_id"),
            messages_new=result.messages_inserted,
            messages_refreshed=result.messages_updated,
            attachments_registered=result.attachments_registered,
            embeds_registered=result.embeds_registered,
        )

    def recent(self, limit: int = 50) -> list[ActivityRecord]:
        safe_limit = max(1, min(int(limit), 1000))
        rows = self.connection.execute(
            "SELECT * FROM activity_events ORDER BY id DESC LIMIT ?",
            (safe_limit,),
        ).fetchall()
        return [self._from_row(row) for row in rows]

    def count(self) -> int:
        return int(self.connection.execute("SELECT COUNT(*) FROM activity_events").fetchone()[0])

    def _from_row(self, row: sqlite3.Row) -> ActivityRecord:
        try:
            details = json.loads(row["details_json"] or "{}")
        except json.JSONDecodeError:
            details = {"raw_details": row["details_json"]}
        return ActivityRecord(
            id=int(row["id"]),
            occurred_at=row["occurred_at"],
            level=row["level"],
            subsystem=row["subsystem"],
            event_type=row["event_type"],
            summary=row["summary"],
            details=details,
            capture_path=row["capture_path"],
            guild_id=row["guild_id"],
            parent_channel_id=row["parent_channel_id"],
            thread_id=row["thread_id"],
            messages_new=int(row["messages_new"]),
            messages_refreshed=int(row["messages_refreshed"]),
            attachments_registered=int(row["attachments_registered"]),
            embeds_registered=int(row["embeds_registered"]),
            storage_delta_bytes=int(row["storage_delta_bytes"]),
            persisted=True,
        )

    def _notify(self, record: ActivityRecord) -> None:
        with self._lock:
            subscribers: Iterable[Callable[[ActivityRecord], None]] = tuple(self._subscribers)
        for callback in subscribers:
            try:
                callback(record)
            except Exception:
                # A CLI printer or future GUI listener is presentation code and
                # must never be allowed to terminate archive processing.
                continue
