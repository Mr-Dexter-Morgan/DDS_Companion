from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


MEDIA_STATES = {
    "KNOWN",
    "QUEUED",
    "DOWNLOADING",
    "CACHED",
    "SKIPPED",
    "TOO_LARGE",
    "FAILED_RETRYABLE",
    "FAILED_PERMANENT",
    "STALE_URL",
    "EVICTED",
}


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def media_key_for(*, message_id: str, position: int, attachment_id: str | None) -> str:
    """Return a stable media identity without trusting filenames or URLs.

    Discord attachment snowflakes are globally stable when present. Older or
    malformed captures may omit them, so the message/position tuple is the safe
    deterministic fallback.
    """
    if attachment_id:
        return f"attachment:{attachment_id}"
    return f"message:{message_id}:position:{int(position)}"


@dataclass(frozen=True)
class MediaRegistryRecord:
    media_key: str
    state: str
    attachment_id: str | None
    filename: str | None
    content_type: str | None
    expected_size: int | None
    current_url: str | None
    proxy_url: str | None
    local_relpath: str | None
    local_size: int | None
    sha256: str | None
    attempt_count: int
    next_retry_at: str | None
    last_error: str | None
    failure_class: str | None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "MediaRegistryRecord":
        return cls(
            media_key=row["media_key"],
            state=row["state"],
            attachment_id=row["attachment_id"],
            filename=row["filename"],
            content_type=row["content_type"],
            expected_size=row["expected_size"],
            current_url=row["current_url"],
            proxy_url=row["proxy_url"],
            local_relpath=row["local_relpath"],
            local_size=row["local_size"],
            sha256=row["sha256"],
            attempt_count=int(row["attempt_count"] or 0),
            next_retry_at=row["next_retry_at"],
            last_error=row["last_error"],
            failure_class=row["failure_class"],
        )


class MediaRegistryService:
    """Durable attachment/media identity and state contract.

    The registry is deliberately separate from the existing ``attachments``
    metadata table. Attachment rows describe what a capture said. Registry rows
    describe local cache/backfill lifecycle. Clearing binary cache therefore
    never deletes message/attachment metadata.
    """

    def __init__(self, connection: sqlite3.Connection):
        self.connection = connection

    def bootstrap_from_archive(self) -> int:
        """Populate registry for pre-0.5 databases without reimporting captures.

        Capture deduplication intentionally skips already-imported JSON. Therefore a
        schema migration alone is not enough: existing ``attachments`` rows need a
        one-time registry projection. This runs on the isolated media thread and is
        idempotent.
        """
        marker = self.connection.execute(
            "SELECT value FROM application_state WHERE key='media_registry_bootstrap_v1'"
        ).fetchone()
        if marker:
            attachment_count = int(self.connection.execute("SELECT COUNT(*) FROM attachments").fetchone()[0])
            ref_count = int(self.connection.execute("SELECT COUNT(*) FROM media_refs").fetchone()[0])
            if ref_count >= attachment_count:
                return 0
        rows = self.connection.execute(
            """
            SELECT a.*, m.last_seen_at
            FROM attachments a
            JOIN messages m ON m.id=a.message_id
            ORDER BY a.message_id, a.position
            """
        ).fetchall()
        with self.connection:
            for row in rows:
                self.register_attachment(
                    message_id=row["message_id"],
                    position=int(row["position"]),
                    attachment={
                        "id": row["attachment_id"],
                        "filename": row["filename"],
                        "contentType": row["content_type"],
                        "size": row["size"],
                        "url": row["url"],
                        "proxyUrl": row["proxy_url"],
                    },
                    observed_at=row["last_seen_at"] or utc_now(),
                )
            self.connection.execute(
                """
                INSERT INTO application_state(key, value, updated_at) VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at
                """,
                ("media_registry_bootstrap_v1", str(len(rows)), utc_now()),
            )
        return len(rows)

    def remove_refs_for_message(self, message_id: str) -> None:
        self.connection.execute("DELETE FROM media_refs WHERE message_id=?", (str(message_id),))

    def register_attachment(
        self,
        *,
        message_id: str,
        position: int,
        attachment: dict[str, Any],
        observed_at: str | None = None,
    ) -> str:
        stamp = observed_at or utc_now()
        attachment_id = str(attachment["id"]) if attachment.get("id") is not None else None
        media_key = media_key_for(
            message_id=str(message_id),
            position=int(position),
            attachment_id=attachment_id,
        )
        current_url = attachment.get("url") or None
        proxy_url = attachment.get("proxyUrl") or None
        expected_size = attachment.get("size")
        if isinstance(expected_size, bool) or not isinstance(expected_size, int) or expected_size < 0:
            expected_size = None

        previous = self.connection.execute(
            "SELECT state, current_url, local_relpath FROM media_objects WHERE media_key=?",
            (media_key,),
        ).fetchone()

        state = "KNOWN"
        reset_attempts = True
        preserve_cache = False
        if previous:
            previous_state = str(previous["state"] or "KNOWN").upper()
            if previous_state == "EVICTED":
                # Policy/user eviction is intentional. A rotating signed URL must
                # not cause an endless download -> eviction -> redownload loop.
                state = "EVICTED"
                reset_attempts = False
            elif previous_state == "CACHED" and previous["local_relpath"]:
                # A refreshed CDN URL does not invalidate an already cached file.
                state = "CACHED"
                reset_attempts = False
                preserve_cache = True
            elif (previous["current_url"] or None) == current_url:
                # Preserve a meaningful existing lifecycle state when the capture
                # merely repeats the same attachment metadata.
                state = previous_state if previous_state in MEDIA_STATES else "KNOWN"
                reset_attempts = False
            else:
                # A new signed CDN URL is the recovery mechanism for stale/failed
                # media. Make it eligible for planning again automatically.
                state = "KNOWN"
                reset_attempts = True

        self.connection.execute(
            """
            INSERT INTO media_objects(
                media_key, attachment_id, filename, content_type, expected_size,
                current_url, proxy_url, url_observed_at, state,
                first_seen_at, last_seen_at, updated_at,
                attempt_count, next_retry_at, last_attempt_at,
                local_relpath, local_size, sha256, cached_at, last_access_at,
                last_http_status, last_error, failure_class
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, NULL,
                     NULL, NULL, NULL, NULL, NULL, NULL, NULL, NULL)
            ON CONFLICT(media_key) DO UPDATE SET
                attachment_id=excluded.attachment_id,
                filename=excluded.filename,
                content_type=excluded.content_type,
                expected_size=excluded.expected_size,
                current_url=excluded.current_url,
                proxy_url=excluded.proxy_url,
                url_observed_at=excluded.url_observed_at,
                state=?,
                last_seen_at=excluded.last_seen_at,
                updated_at=excluded.updated_at,
                attempt_count=CASE WHEN ? THEN 0 ELSE media_objects.attempt_count END,
                next_retry_at=CASE WHEN ? THEN NULL ELSE media_objects.next_retry_at END,
                last_attempt_at=CASE WHEN ? THEN NULL ELSE media_objects.last_attempt_at END,
                last_http_status=CASE WHEN ? THEN NULL ELSE media_objects.last_http_status END,
                last_error=CASE WHEN ? THEN NULL ELSE media_objects.last_error END,
                failure_class=CASE WHEN ? THEN NULL ELSE media_objects.failure_class END,
                local_relpath=CASE WHEN ? THEN media_objects.local_relpath ELSE NULL END,
                local_size=CASE WHEN ? THEN media_objects.local_size ELSE NULL END,
                sha256=CASE WHEN ? THEN media_objects.sha256 ELSE NULL END,
                cached_at=CASE WHEN ? THEN media_objects.cached_at ELSE NULL END,
                last_access_at=CASE WHEN ? THEN media_objects.last_access_at ELSE NULL END
            """,
            (
                media_key,
                attachment_id,
                attachment.get("filename"),
                attachment.get("contentType"),
                expected_size,
                current_url,
                proxy_url,
                stamp,
                state,
                stamp,
                stamp,
                stamp,
                state,
                int(reset_attempts),
                int(reset_attempts),
                int(reset_attempts),
                int(reset_attempts),
                int(reset_attempts),
                int(reset_attempts),
                int(preserve_cache),
                int(preserve_cache),
                int(preserve_cache),
                int(preserve_cache),
                int(preserve_cache),
            ),
        )
        self.connection.execute(
            """
            INSERT INTO media_refs(message_id, position, media_key, first_seen_at, last_seen_at)
            VALUES(?, ?, ?, ?, ?)
            ON CONFLICT(message_id, position) DO UPDATE SET
                media_key=excluded.media_key,
                last_seen_at=excluded.last_seen_at
            """,
            (str(message_id), int(position), media_key, stamp, stamp),
        )
        return media_key

    def get(self, media_key: str) -> MediaRegistryRecord | None:
        row = self.connection.execute(
            "SELECT * FROM media_objects WHERE media_key=?",
            (str(media_key),),
        ).fetchone()
        return MediaRegistryRecord.from_row(row) if row else None

    def state_counts(self) -> dict[str, int]:
        rows = self.connection.execute(
            "SELECT state, COUNT(*) AS n FROM media_objects GROUP BY state"
        ).fetchall()
        return {str(row["state"]): int(row["n"]) for row in rows}

    def referenced_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(DISTINCT media_key) FROM media_refs"
            ).fetchone()[0]
        )

    def cached_count(self) -> int:
        return int(
            self.connection.execute(
                "SELECT COUNT(*) FROM media_objects WHERE state='CACHED'"
            ).fetchone()[0]
        )

    def reset_removed_cache_paths(
        self,
        relative_paths: list[str] | tuple[str, ...],
        *,
        eviction_reason: str = "policy",
    ) -> int:
        """Mark removed binary cache rows without deleting archive metadata.

        The reason is persisted so a deliberate user clear can be distinguished
        from policy eviction. That distinction matters: policy-evicted files must
        not spring back automatically and create download/eviction thrash, while
        manually cleared files may be explicitly requested again by toggling
        Automatic media download back on.
        """
        paths = [str(item).replace("\\", "/") for item in relative_paths if item]
        if not paths:
            return 0
        reason = str(eviction_reason or "policy").strip().lower().replace(" ", "_")
        failure_class = f"evicted_{reason}"
        changed = 0
        stamp = utc_now()
        with self.connection:
            for relpath in paths:
                cursor = self.connection.execute(
                    """
                    UPDATE media_objects
                    SET state='EVICTED', local_relpath=NULL, local_size=NULL, sha256=NULL,
                        cached_at=NULL, last_access_at=NULL, updated_at=?,
                        last_error=NULL, failure_class=?, next_retry_at=NULL
                    WHERE local_relpath=? AND state='CACHED'
                    """,
                    (stamp, failure_class, relpath),
                )
                changed += int(cursor.rowcount or 0)
        return changed

    def requeue_manual_clear_evictions(self) -> int:
        """Re-arm cache rows on an explicit user autodownload enable action.

        Normal r2 rows are eligible only when they were removed by manual Clear.
        Candidate-r1 wrote EVICTED with a NULL failure_class for both manual and
        policy removal, so an explicit user Off -> On also re-arms those legacy
        ambiguous rows once. This compatibility path cannot loop indefinitely:
        any subsequent r2 policy eviction is tagged evicted_policy and excluded.

        This method is intentionally *not* called on startup or planner ticks.
        """
        stamp = utc_now()
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE media_objects
                SET state='KNOWN', updated_at=?, attempt_count=0, next_retry_at=NULL,
                    last_attempt_at=NULL, last_http_status=NULL, last_error=NULL, failure_class=NULL
                WHERE state='EVICTED'
                  AND (failure_class='evicted_manual_clear' OR failure_class IS NULL)
                  AND EXISTS(SELECT 1 FROM media_refs mr WHERE mr.media_key=media_objects.media_key)
                """,
                (stamp,),
            )
        return int(cursor.rowcount or 0)

    def reconcile_cached_files(self, media_root: str | Path) -> int:
        """Heal registry rows when cache files were removed outside Companion."""
        root = Path(media_root)
        rows = self.connection.execute(
            "SELECT media_key, local_relpath FROM media_objects WHERE state='CACHED'"
        ).fetchall()
        missing: list[str] = []
        for row in rows:
            rel = row["local_relpath"]
            if not rel:
                missing.append(row["media_key"])
                continue
            candidate = (root / Path(str(rel))).resolve()
            try:
                candidate.relative_to(root.resolve())
            except ValueError:
                missing.append(row["media_key"])
                continue
            if not candidate.is_file():
                missing.append(row["media_key"])

        if not missing:
            return 0
        stamp = utc_now()
        with self.connection:
            self.connection.executemany(
                """
                UPDATE media_objects
                SET state='KNOWN', local_relpath=NULL, local_size=NULL, sha256=NULL,
                    cached_at=NULL, last_access_at=NULL, updated_at=?,
                    last_error='cached file missing; registry healed',
                    failure_class='cache_missing', next_retry_at=NULL
                WHERE media_key=?
                """,
                [(stamp, key) for key in missing],
            )
        return len(missing)
