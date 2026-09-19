from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable

from dds_companion.core.settings import CompanionSettings
from dds_companion.services.activity_service import ActivityService
from dds_companion.services.media_registry_service import MediaRegistryService, utc_now


ALLOWED_ATTACHMENT_HOSTS = {
    "cdn.discordapp.com",
    "media.discordapp.net",
}


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _is_allowed_discord_url(url: str | None) -> bool:
    if not url:
        return False
    try:
        parsed = urllib.parse.urlsplit(url)
    except ValueError:
        return False
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        return False
    host = parsed.hostname.lower().rstrip(".")
    return (
        host in ALLOWED_ATTACHMENT_HOSTS
        or host.endswith(".discordapp.com")
        or host.endswith(".discordapp.net")
    )


def _safe_suffix(filename: str | None) -> str:
    if not filename:
        return ""
    suffix = Path(filename).suffix.lower()
    if not suffix or len(suffix) > 12:
        return ""
    allowed = ".abcdefghijklmnopqrstuvwxyz0123456789"
    return suffix if all(ch in allowed for ch in suffix) else ""


def _retry_delay(attempt_count: int) -> int:
    # 15s, 30s, 60s, 120s, 240s; capped to avoid runaway waits.
    return min(15 * (2 ** max(0, int(attempt_count) - 1)), 15 * 60)


@dataclass(frozen=True)
class MediaPlanResult:
    recovered_abandoned: int = 0
    missing_cache_healed: int = 0
    queued: int = 0
    skipped: int = 0
    too_large: int = 0
    retry_promoted: int = 0

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class DownloadSpec:
    media_key: str
    url: str
    filename: str | None
    expected_size: int | None
    content_type: str | None
    attempt_count: int


@dataclass(frozen=True)
class DownloadOutcome:
    media_key: str
    state: str
    local_relpath: str | None = None
    local_size: int | None = None
    sha256: str | None = None
    http_status: int | None = None
    error: str | None = None
    failure_class: str | None = None
    retry_after_seconds: int | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class MediaCycleResult:
    planned: MediaPlanResult
    claimed: int = 0
    cached: int = 0
    retryable_failed: int = 0
    permanent_failed: int = 0
    stale_url: int = 0
    too_large: int = 0
    skipped: int = 0

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["planned"] = self.planned.to_dict()
        return payload


@dataclass(frozen=True)
class TransportResult:
    bytes_written: int
    sha256: str
    http_status: int | None = None
    announced_size: int | None = None


Transport = Callable[[DownloadSpec, Path, int | None, float], TransportResult]


class _SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001 - urllib signature
        if not _is_allowed_discord_url(newurl):
            raise urllib.error.URLError("redirect target is outside Discord media hosts")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class MediaBackfillService:
    """Plan and execute bounded, failure-isolated attachment backfill.

    The service treats capture metadata as source of truth and media binaries as
    replaceable cache. It never mutates messages/attachments while downloading.
    Network work is bounded by both a worker count and per-request timeout.
    """

    MAX_ATTEMPTS = 5
    ABANDONED_DOWNLOAD_SECONDS = 5 * 60
    DEFAULT_TIMEOUT_SECONDS = 15.0
    DEFAULT_WORKERS = 2

    def __init__(
        self,
        connection: sqlite3.Connection,
        media_root: str | Path,
        *,
        activity: ActivityService | None = None,
        transport: Transport | None = None,
        max_workers: int = DEFAULT_WORKERS,
        timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    ):
        self.connection = connection
        self.registry = MediaRegistryService(connection)
        self.media_root = Path(media_root)
        self.activity = activity
        self.transport = transport or self._urllib_transport
        self.max_workers = max(1, min(int(max_workers), 4))
        self.timeout_seconds = max(2.0, min(float(timeout_seconds), 60.0))

    def plan(self, settings: CompanionSettings, *, now: datetime | None = None, limit: int = 200) -> MediaPlanResult:
        stamp_dt = now or datetime.now(timezone.utc)
        stamp = stamp_dt.isoformat()
        recovered = self._recover_abandoned(stamp_dt)
        healed = self.registry.reconcile_cached_files(self.media_root)

        queued = skipped = too_large = retry_promoted = 0
        safe_limit = max(1, min(int(limit), 2000))
        rows = self.connection.execute(
            """
            SELECT mo.*
            FROM media_objects mo
            WHERE EXISTS(SELECT 1 FROM media_refs mr WHERE mr.media_key=mo.media_key)
              AND mo.state IN ('KNOWN', 'FAILED_RETRYABLE', 'TOO_LARGE')
            ORDER BY mo.first_seen_at, mo.media_key
            LIMIT ?
            """,
            (safe_limit,),
        ).fetchall()

        with self.connection:
            for row in rows:
                state = str(row["state"] or "KNOWN")
                if state == "FAILED_RETRYABLE":
                    due = _parse_iso(row["next_retry_at"])
                    if due is not None and due > stamp_dt:
                        continue
                    if int(row["attempt_count"] or 0) >= self.MAX_ATTEMPTS:
                        self._set_state(
                            row["media_key"],
                            "FAILED_PERMANENT",
                            stamp=stamp,
                            error="retry limit exhausted",
                            failure_class="retry_exhausted",
                        )
                        continue
                    retry_promoted += 1

                expected_size = row["expected_size"]
                too_big = False
                too_big_reason = None
                if expected_size is not None:
                    expected_size = int(expected_size)
                    if settings.media_max_file_bytes is not None and expected_size > settings.media_max_file_bytes:
                        too_big = True
                        too_big_reason = "attachment exceeds max single media file policy"
                    elif settings.media_cache_limit_bytes is not None and expected_size > settings.media_cache_limit_bytes:
                        too_big = True
                        too_big_reason = "attachment exceeds total media cache capacity"

                if too_big:
                    if state != "TOO_LARGE":
                        self._set_state(
                            row["media_key"],
                            "TOO_LARGE",
                            stamp=stamp,
                            error=too_big_reason,
                            failure_class="policy_too_large",
                        )
                        too_large += 1
                    continue

                url = row["current_url"]
                if not url:
                    self._set_state(
                        row["media_key"],
                        "SKIPPED",
                        stamp=stamp,
                        error="attachment has no downloadable URL",
                        failure_class="missing_url",
                    )
                    skipped += 1
                    continue
                if not _is_allowed_discord_url(str(url)):
                    self._set_state(
                        row["media_key"],
                        "SKIPPED",
                        stamp=stamp,
                        error="URL is outside allowed Discord media hosts",
                        failure_class="unsupported_url",
                    )
                    skipped += 1
                    continue

                cursor = self.connection.execute(
                    """
                    UPDATE media_objects
                    SET state='QUEUED', updated_at=?, next_retry_at=NULL,
                        last_error=NULL, failure_class=NULL
                    WHERE media_key=? AND state IN ('KNOWN', 'FAILED_RETRYABLE', 'TOO_LARGE')
                    """,
                    (stamp, row["media_key"]),
                )
                queued += int(cursor.rowcount or 0)

        return MediaPlanResult(
            recovered_abandoned=recovered,
            missing_cache_healed=healed,
            queued=queued,
            skipped=skipped,
            too_large=too_large,
            retry_promoted=retry_promoted,
        )

    def process_once(self, settings: CompanionSettings, *, now: datetime | None = None) -> MediaCycleResult:
        planned = self.plan(settings, now=now)
        specs = self._claim(self.max_workers)
        if not specs:
            return MediaCycleResult(planned=planned)

        outcomes: list[DownloadOutcome] = []
        with ThreadPoolExecutor(max_workers=self.max_workers, thread_name_prefix="dds-media-fetch") as executor:
            future_map = {executor.submit(self._download_one, spec, settings): spec for spec in specs}
            for future in as_completed(future_map):
                spec = future_map[future]
                try:
                    outcomes.append(future.result())
                except Exception as exc:  # last-resort worker isolation
                    outcomes.append(
                        DownloadOutcome(
                            media_key=spec.media_key,
                            state="FAILED_RETRYABLE",
                            error=f"{type(exc).__name__}: {exc}",
                            failure_class="worker_exception",
                        )
                    )

        counters = {
            "cached": 0,
            "retryable_failed": 0,
            "permanent_failed": 0,
            "stale_url": 0,
            "too_large": 0,
            "skipped": 0,
        }
        for outcome in outcomes:
            self._apply_outcome(outcome)
            if outcome.state == "CACHED":
                counters["cached"] += 1
            elif outcome.state == "FAILED_RETRYABLE":
                counters["retryable_failed"] += 1
            elif outcome.state == "FAILED_PERMANENT":
                counters["permanent_failed"] += 1
            elif outcome.state == "STALE_URL":
                counters["stale_url"] += 1
            elif outcome.state == "TOO_LARGE":
                counters["too_large"] += 1
            elif outcome.state == "SKIPPED":
                counters["skipped"] += 1

        return MediaCycleResult(planned=planned, claimed=len(specs), **counters)

    def counts(self) -> dict[str, int]:
        counts = self.registry.state_counts()
        attention = counts.get("FAILED_PERMANENT", 0) + counts.get("STALE_URL", 0)
        return {
            "total": self.registry.referenced_count(),
            "known": self.registry.known_count(),
            "cached": counts.get("CACHED", 0),
            "queued": counts.get("QUEUED", 0),
            "downloading": counts.get("DOWNLOADING", 0),
            "retryable_failed": counts.get("FAILED_RETRYABLE", 0),
            "permanent_failed": counts.get("FAILED_PERMANENT", 0),
            "stale_url": counts.get("STALE_URL", 0),
            "too_large": counts.get("TOO_LARGE", 0),
            "skipped": counts.get("SKIPPED", 0),
            "evicted": counts.get("EVICTED", 0),
            "ignored": counts.get("IGNORED", 0),
            "unresolved": counts.get("UNRESOLVED", 0),
            "attention": attention,
        }

    def issue_items(self, *, limit: int = 50) -> list[dict]:
        return self.registry.issue_items(limit=limit, include_ignored=True)

    def retry_media_once(self, media_key: str, settings: CompanionSettings) -> DownloadOutcome | None:
        """Execute one explicit user-requested retry, independent of auto mode."""
        if not self.registry.prepare_manual_retry(media_key):
            return None
        spec = self._claim_one(media_key)
        if spec is None:
            return None
        outcome = self._download_one(spec, settings)
        self._apply_outcome(outcome)
        return outcome

    def ignore_issue(self, media_key: str) -> bool:
        return self.registry.ignore_issue(media_key)

    def ignore_all_issues(self) -> int:
        return self.registry.ignore_all_issues()

    def clear_processed_issues(self) -> int:
        return self.registry.clear_processed_issues()

    def _recover_abandoned(self, now: datetime) -> int:
        cutoff = (now - timedelta(seconds=self.ABANDONED_DOWNLOAD_SECONDS)).isoformat()
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE media_objects
                SET state='QUEUED', updated_at=?, last_error='recovered abandoned download claim',
                    failure_class='abandoned_claim'
                WHERE state='DOWNLOADING' AND (last_attempt_at IS NULL OR last_attempt_at < ?)
                """,
                (now.isoformat(), cutoff),
            )
        return int(cursor.rowcount or 0)

    def _claim(self, limit: int) -> list[DownloadSpec]:
        stamp = utc_now()
        rows = self.connection.execute(
            """
            SELECT media_key, current_url, filename, expected_size, content_type, attempt_count
            FROM media_objects
            WHERE state='QUEUED'
            ORDER BY first_seen_at, media_key
            LIMIT ?
            """,
            (max(1, int(limit)),),
        ).fetchall()
        claimed: list[DownloadSpec] = []
        with self.connection:
            for row in rows:
                cursor = self.connection.execute(
                    """
                    UPDATE media_objects
                    SET state='DOWNLOADING', last_attempt_at=?, updated_at=?,
                        attempt_count=attempt_count+1
                    WHERE media_key=? AND state='QUEUED'
                    """,
                    (stamp, stamp, row["media_key"]),
                )
                if not cursor.rowcount:
                    continue
                claimed.append(
                    DownloadSpec(
                        media_key=row["media_key"],
                        url=row["current_url"],
                        filename=row["filename"],
                        expected_size=int(row["expected_size"]) if row["expected_size"] is not None else None,
                        content_type=row["content_type"],
                        attempt_count=int(row["attempt_count"] or 0) + 1,
                    )
                )
        return claimed

    def _claim_one(self, media_key: str) -> DownloadSpec | None:
        stamp = utc_now()
        row = self.connection.execute(
            """
            SELECT media_key, current_url, filename, expected_size, content_type, attempt_count
            FROM media_objects
            WHERE media_key=? AND state='QUEUED'
            """,
            (str(media_key),),
        ).fetchone()
        if row is None:
            return None
        with self.connection:
            cursor = self.connection.execute(
                """
                UPDATE media_objects
                SET state='DOWNLOADING', last_attempt_at=?, updated_at=?, attempt_count=attempt_count+1
                WHERE media_key=? AND state='QUEUED'
                """,
                (stamp, stamp, str(media_key)),
            )
        if not cursor.rowcount:
            return None
        return DownloadSpec(
            media_key=row["media_key"],
            url=row["current_url"],
            filename=row["filename"],
            expected_size=int(row["expected_size"]) if row["expected_size"] is not None else None,
            content_type=row["content_type"],
            attempt_count=int(row["attempt_count"] or 0) + 1,
        )

    def _download_one(self, spec: DownloadSpec, settings: CompanionSettings) -> DownloadOutcome:
        if not _is_allowed_discord_url(spec.url):
            return DownloadOutcome(
                media_key=spec.media_key,
                state="SKIPPED",
                error="URL is outside allowed Discord media hosts",
                failure_class="unsupported_url",
            )

        max_bytes = settings.media_max_file_bytes
        if settings.media_cache_limit_bytes is not None:
            max_bytes = (
                settings.media_cache_limit_bytes
                if max_bytes is None
                else min(max_bytes, settings.media_cache_limit_bytes)
            )
        if spec.expected_size is not None and max_bytes is not None and spec.expected_size > max_bytes:
            return DownloadOutcome(
                media_key=spec.media_key,
                state="TOO_LARGE",
                error="attachment exceeds configured cache policy",
                failure_class="policy_too_large",
            )

        self.media_root.mkdir(parents=True, exist_ok=True)
        root_resolved = self.media_root.resolve()
        staging = self.media_root / ".staging"
        staging.mkdir(parents=True, exist_ok=True)
        key_hash = hashlib.sha256(spec.media_key.encode("utf-8")).hexdigest()
        suffix = _safe_suffix(spec.filename)
        relpath = Path("objects") / key_hash[:2] / f"{key_hash}{suffix}"
        final_path = self.media_root / relpath
        final_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            staging.resolve().relative_to(root_resolved)
            final_path.resolve().relative_to(root_resolved)
        except ValueError:
            return DownloadOutcome(
                media_key=spec.media_key,
                state="FAILED_PERMANENT",
                error="media cache path escaped configured media root",
                failure_class="unsafe_cache_path",
            )

        expected_for_space = spec.expected_size or min(max_bytes or 32 * 1024**2, 32 * 1024**2)
        try:
            free = shutil.disk_usage(self.media_root).free
        except OSError:
            free = None
        if free is not None and free < int(expected_for_space) + 8 * 1024**2:
            return DownloadOutcome(
                media_key=spec.media_key,
                state="FAILED_RETRYABLE",
                error="insufficient free disk space for bounded media download",
                failure_class="disk_space",
            )

        fd, temp_name = tempfile.mkstemp(prefix=f"{key_hash}.", suffix=".part", dir=staging)
        os.close(fd)
        temp_path = Path(temp_name)
        try:
            try:
                result = self.transport(spec, temp_path, max_bytes, self.timeout_seconds)
            except urllib.error.HTTPError as exc:
                if exc.code in {401, 403, 404}:
                    return DownloadOutcome(
                        media_key=spec.media_key,
                        state="STALE_URL",
                        http_status=int(exc.code),
                        error=f"HTTP {exc.code}: signed/media URL unavailable",
                        failure_class="stale_url",
                    )
                if exc.code == 429 or 500 <= exc.code <= 599:
                    retry_after = None
                    if exc.code == 429:
                        try:
                            retry_after = int((exc.headers or {}).get("Retry-After", ""))
                        except (TypeError, ValueError):
                            retry_after = None
                    return DownloadOutcome(
                        media_key=spec.media_key,
                        state="FAILED_RETRYABLE",
                        http_status=int(exc.code),
                        error=f"HTTP {exc.code}",
                        failure_class="http_retryable",
                        retry_after_seconds=retry_after,
                    )
                return DownloadOutcome(
                    media_key=spec.media_key,
                    state="FAILED_PERMANENT",
                    http_status=int(exc.code),
                    error=f"HTTP {exc.code}",
                    failure_class="http_permanent",
                )
            except ValueError as exc:
                return DownloadOutcome(
                    media_key=spec.media_key,
                    state="TOO_LARGE" if "size limit" in str(exc).lower() else "FAILED_PERMANENT",
                    error=f"ValueError: {exc}",
                    failure_class="policy_too_large" if "size limit" in str(exc).lower() else "invalid_response",
                )
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                return DownloadOutcome(
                    media_key=spec.media_key,
                    state="FAILED_RETRYABLE",
                    error=f"{type(exc).__name__}: {exc}",
                    failure_class="network_or_io",
                )

            if spec.expected_size is not None and result.bytes_written != spec.expected_size:
                # If HTTP announced exactly the payload we received, the transfer is
                # complete and retrying it five times will only reproduce the same
                # metadata-vs-CDN disagreement. Surface it once for user attention.
                stable_mismatch = (
                    result.announced_size is not None
                    and result.announced_size == result.bytes_written
                )
                return DownloadOutcome(
                    media_key=spec.media_key,
                    state="FAILED_PERMANENT" if stable_mismatch else "FAILED_RETRYABLE",
                    http_status=result.http_status,
                    error=f"size mismatch: expected {spec.expected_size}, got {result.bytes_written}",
                    failure_class="metadata_size_mismatch" if stable_mismatch else "size_mismatch",
                )

            os.replace(temp_path, final_path)
            try:
                with final_path.open("rb") as handle:
                    os.fsync(handle.fileno())
            except OSError:
                # os.replace already made the file durable enough for normal cache
                # semantics; fsync failure should not discard a valid cache file.
                pass
            return DownloadOutcome(
                media_key=spec.media_key,
                state="CACHED",
                local_relpath=relpath.as_posix(),
                local_size=result.bytes_written,
                sha256=result.sha256,
                http_status=result.http_status,
            )
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass

    def _apply_outcome(self, outcome: DownloadOutcome) -> None:
        stamp = utc_now()
        row = self.connection.execute(
            "SELECT attempt_count FROM media_objects WHERE media_key=?",
            (outcome.media_key,),
        ).fetchone()
        attempts = int(row["attempt_count"] or 0) if row else 0
        state = outcome.state
        next_retry_at = None
        if state == "FAILED_RETRYABLE":
            if attempts >= self.MAX_ATTEMPTS:
                state = "FAILED_PERMANENT"
                outcome = DownloadOutcome(
                    media_key=outcome.media_key,
                    state=state,
                    http_status=outcome.http_status,
                    error=outcome.error or "retry limit exhausted",
                    failure_class="retry_exhausted",
                    retry_after_seconds=outcome.retry_after_seconds,
                )
            else:
                delay = _retry_delay(attempts)
                if outcome.retry_after_seconds is not None:
                    delay = max(delay, min(max(0, int(outcome.retry_after_seconds)), 60 * 60))
                next_retry_at = (
                    datetime.now(timezone.utc) + timedelta(seconds=delay)
                ).isoformat()

        with self.connection:
            if state == "CACHED":
                self.connection.execute(
                    """
                    UPDATE media_objects
                    SET state='CACHED', local_relpath=?, local_size=?, sha256=?,
                        cached_at=?, last_access_at=?, updated_at=?, next_retry_at=NULL,
                        last_http_status=?, last_error=NULL, failure_class=NULL
                    WHERE media_key=?
                    """,
                    (
                        outcome.local_relpath,
                        outcome.local_size,
                        outcome.sha256,
                        stamp,
                        stamp,
                        stamp,
                        outcome.http_status,
                        outcome.media_key,
                    ),
                )
            else:
                self.connection.execute(
                    """
                    UPDATE media_objects
                    SET state=?, updated_at=?, next_retry_at=?, last_http_status=?,
                        last_error=?, failure_class=?,
                        local_relpath=NULL, local_size=NULL, sha256=NULL, cached_at=NULL
                    WHERE media_key=?
                    """,
                    (
                        state,
                        stamp,
                        next_retry_at,
                        outcome.http_status,
                        outcome.error,
                        outcome.failure_class,
                        outcome.media_key,
                    ),
                )

        self._publish_outcome(outcome, effective_state=state, next_retry_at=next_retry_at)

    def _publish_outcome(self, outcome: DownloadOutcome, *, effective_state: str, next_retry_at: str | None) -> None:
        if self.activity is None:
            return
        if effective_state == "CACHED":
            self.activity.publish(
                subsystem="media",
                event_type="media_cached",
                summary=f"Media cached: {outcome.local_size or 0} bytes",
                details={
                    "media_key": outcome.media_key,
                    "local_relpath": outcome.local_relpath,
                    "sha256": outcome.sha256,
                },
                storage_delta_bytes=int(outcome.local_size or 0),
            )
            return

        level = "WARNING"
        if effective_state in {"FAILED_PERMANENT"}:
            level = "ERROR"
        event_type = {
            "STALE_URL": "media_url_stale",
            "FAILED_RETRYABLE": "media_retry_scheduled",
            "FAILED_PERMANENT": "media_failed_permanent",
            "TOO_LARGE": "media_skipped_too_large",
            "SKIPPED": "media_skipped",
        }.get(effective_state, "media_state_changed")
        self.activity.publish(
            level=level,
            subsystem="media",
            event_type=event_type,
            summary=f"Media {effective_state.lower().replace('_', ' ')}: {outcome.error or 'no detail'}",
            details={
                "media_key": outcome.media_key,
                "state": effective_state,
                "failure_class": outcome.failure_class,
                "http_status": outcome.http_status,
                "next_retry_at": next_retry_at,
            },
        )

    def _set_state(
        self,
        media_key: str,
        state: str,
        *,
        stamp: str,
        error: str | None,
        failure_class: str | None,
    ) -> None:
        self.connection.execute(
            """
            UPDATE media_objects
            SET state=?, updated_at=?, last_error=?, failure_class=?,
                next_retry_at=CASE WHEN ?='FAILED_RETRYABLE' THEN next_retry_at ELSE NULL END
            WHERE media_key=?
            """,
            (state, stamp, error, failure_class, state, media_key),
        )

    @staticmethod
    def _urllib_transport(
        spec: DownloadSpec,
        temp_path: Path,
        max_bytes: int | None,
        timeout_seconds: float,
    ) -> TransportResult:
        opener = urllib.request.build_opener(_SafeRedirectHandler())
        request = urllib.request.Request(
            spec.url,
            headers={
                "User-Agent": "DDS-Companion/0.5 media-backfill",
                "Accept": "*/*",
            },
            method="GET",
        )
        with opener.open(request, timeout=timeout_seconds) as response:
            status = int(getattr(response, "status", 200) or 200)
            final_url = response.geturl()
            if not _is_allowed_discord_url(final_url):
                raise urllib.error.URLError("final URL is outside Discord media hosts")
            length_header = response.headers.get("Content-Length")
            if length_header:
                try:
                    announced = int(length_header)
                except ValueError:
                    announced = None
                if announced is not None and max_bytes is not None and announced > max_bytes:
                    raise ValueError("response exceeds configured media size limit")
            else:
                announced = None

            digest = hashlib.sha256()
            total = 0
            with temp_path.open("wb") as handle:
                while True:
                    chunk = response.read(256 * 1024)
                    if not chunk:
                        break
                    total += len(chunk)
                    if max_bytes is not None and total > max_bytes:
                        raise ValueError("response exceeded configured media size limit while streaming")
                    handle.write(chunk)
                    digest.update(chunk)
                handle.flush()
                os.fsync(handle.fileno())
            if announced is not None and total != announced:
                raise OSError(f"truncated response: announced {announced}, received {total}")
            return TransportResult(
                bytes_written=total,
                sha256=digest.hexdigest(),
                http_status=status,
                announced_size=announced,
            )
