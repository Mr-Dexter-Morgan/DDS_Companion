from __future__ import annotations

import copy
import hashlib
import json
import queue
import tempfile
import threading
import time
import unittest
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

from dds_companion.core.settings import CompanionSettings, SettingsStore
from dds_companion.services.activity_service import ActivityService
from dds_companion.services.import_service import ImportService
from dds_companion.services.media_backfill_service import (
    DownloadSpec,
    MediaBackfillService,
    TransportResult,
)
from dds_companion.services.media_cache_service import MediaCacheService
from dds_companion.services.media_registry_service import MediaRegistryService, utc_now
from dds_companion.services.media_runtime import MediaBackfillRuntime
from dds_companion.storage.database import connect_database
from dds_companion.tests.test_imports import sample_capture


ALLOWED_URL = "https://cdn.discordapp.com/attachments/1/2/image.png?ex=test"


class MediaBackfillTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "database" / "dds.sqlite3"
        self.media = self.root / "media"
        self.dds = self.root / "DDS_Data"
        self.conn = connect_database(self.db)
        self.importer = ImportService(self.conn)
        self.activity = ActivityService(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _capture(self, *, url: str = ALLOWED_URL, size: int = 4, attachment_id: str = "666666666666666666") -> Path:
        data = sample_capture()
        attachment = data["messages"][0]["attachments"][0]
        attachment["id"] = attachment_id
        attachment["url"] = url
        attachment["size"] = size
        base = self.dds / "guilds" / "111111111111111111" / "channels" / "222222222222222222"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "capture.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    @staticmethod
    def _success_transport(payload: bytes):
        def transport(spec: DownloadSpec, temp_path: Path, max_bytes: int | None, timeout_seconds: float) -> TransportResult:
            if max_bytes is not None and len(payload) > max_bytes:
                raise ValueError("response exceeded configured media size limit while streaming")
            temp_path.write_bytes(payload)
            return TransportResult(
                bytes_written=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                http_status=200,
            )
        return transport

    def test_import_registers_durable_media_identity_and_ref(self):
        path = self._capture()
        self.importer.import_file(path)
        row = self.conn.execute("SELECT * FROM media_objects").fetchone()
        self.assertEqual(row["media_key"], "attachment:666666666666666666")
        self.assertEqual(row["state"], "KNOWN")
        self.assertEqual(row["current_url"], ALLOWED_URL)
        ref = self.conn.execute("SELECT * FROM media_refs").fetchone()
        self.assertEqual(ref["message_id"], "444444444444444444")
        self.assertEqual(ref["media_key"], row["media_key"])

    def test_rotated_url_recovers_stale_but_does_not_resurrect_evicted_cache(self):
        path = self._capture(url=ALLOWED_URL)
        self.importer.import_file(path)
        self.conn.execute(
            "UPDATE media_objects SET state='STALE_URL', last_error='expired'"
        )
        self.conn.commit()
        changed = json.loads(path.read_text())
        changed["captureRevision"] = 8
        changed["messages"][0]["attachments"][0]["url"] = ALLOWED_URL + "&is=rotated"
        path.write_text(json.dumps(changed), encoding="utf-8")
        self.importer.import_file(path)
        row = self.conn.execute("SELECT state, current_url FROM media_objects").fetchone()
        self.assertEqual(row["state"], "KNOWN")
        self.assertIn("rotated", row["current_url"])

        self.conn.execute("UPDATE media_objects SET state='EVICTED'")
        self.conn.commit()
        changed["captureRevision"] = 9
        changed["messages"][0]["attachments"][0]["url"] = ALLOWED_URL + "&is=again"
        path.write_text(json.dumps(changed), encoding="utf-8")
        self.importer.import_file(path)
        self.assertEqual(self.conn.execute("SELECT state FROM media_objects").fetchone()[0], "EVICTED")


    def test_legacy_attachment_projection_bootstraps_registry_once(self):
        path = self._capture(size=4)
        self.importer.import_file(path)
        self.conn.execute("DELETE FROM media_refs")
        self.conn.execute("DELETE FROM media_objects")
        self.conn.execute("DELETE FROM application_state WHERE key='media_registry_bootstrap_v1'")
        self.conn.commit()
        registry = MediaRegistryService(self.conn)
        self.assertEqual(registry.bootstrap_from_archive(), 1)
        self.assertEqual(registry.referenced_count(), 1)
        self.assertEqual(registry.bootstrap_from_archive(), 0)

    def test_successful_cycle_caches_atomically_and_records_hash(self):
        path = self._capture(size=4)
        self.importer.import_file(path)
        service = MediaBackfillService(
            self.conn,
            self.media,
            activity=self.activity,
            transport=self._success_transport(b"data"),
            max_workers=2,
        )
        settings = CompanionSettings(
            media_cache_limit_bytes=1024,
            media_max_file_bytes=1024,
            media_retention_days=30,
            media_autodownload_enabled=True,
        )
        result = service.process_once(settings)
        self.assertEqual(result.cached, 1)
        row = self.conn.execute("SELECT * FROM media_objects").fetchone()
        self.assertEqual(row["state"], "CACHED")
        self.assertEqual(row["local_size"], 4)
        self.assertEqual(row["sha256"], hashlib.sha256(b"data").hexdigest())
        cached = self.media / row["local_relpath"]
        self.assertEqual(cached.read_bytes(), b"data")
        self.assertFalse(any((self.media / ".staging").glob("*.part")))
        events = [row[0] for row in self.conn.execute("SELECT event_type FROM activity_events")]
        self.assertIn("media_cached", events)


    def test_one_media_failure_does_not_block_another_download(self):
        data = sample_capture()
        message = data["messages"][0]
        message["attachments"] = [
            {**message["attachments"][0], "id": "media-ok", "size": 2, "url": ALLOWED_URL + "&id=ok"},
            {**message["attachments"][0], "id": "media-bad", "size": 2, "url": ALLOWED_URL + "&id=bad"},
        ]
        base = self.dds / "guilds" / "111111111111111111" / "channels" / "222222222222222222"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "capture.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        self.importer.import_file(path)

        def transport(spec, temp_path, max_bytes, timeout_seconds):
            if spec.media_key == "attachment:media-bad":
                raise urllib.error.URLError("simulated outage")
            payload = b"ok"
            temp_path.write_bytes(payload)
            return TransportResult(len(payload), hashlib.sha256(payload).hexdigest(), 200)

        service = MediaBackfillService(self.conn, self.media, transport=transport, max_workers=2)
        result = service.process_once(CompanionSettings(media_autodownload_enabled=True))
        self.assertEqual(result.cached, 1)
        self.assertEqual(result.retryable_failed, 1)
        states = {row["media_key"]: row["state"] for row in self.conn.execute("SELECT media_key, state FROM media_objects")}
        self.assertEqual(states["attachment:media-ok"], "CACHED")
        self.assertEqual(states["attachment:media-bad"], "FAILED_RETRYABLE")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)

    def test_oversized_policy_skips_without_calling_transport(self):
        self.importer.import_file(self._capture(size=500))
        called = False

        def transport(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("transport must not run")

        service = MediaBackfillService(self.conn, self.media, transport=transport)
        settings = CompanionSettings(
            media_cache_limit_bytes=1000,
            media_max_file_bytes=100,
            media_retention_days=30,
            media_autodownload_enabled=True,
        )
        result = service.process_once(settings)
        self.assertFalse(called)
        self.assertEqual(result.planned.too_large, 1)
        self.assertEqual(self.conn.execute("SELECT state FROM media_objects").fetchone()[0], "TOO_LARGE")

    def test_unsupported_host_is_skipped_without_network_ssrf_surface(self):
        self.importer.import_file(self._capture(url="https://127.0.0.1/private"))
        called = False

        def transport(*args, **kwargs):
            nonlocal called
            called = True
            raise AssertionError("transport must not run")

        service = MediaBackfillService(self.conn, self.media, transport=transport)
        result = service.process_once(CompanionSettings(media_autodownload_enabled=True))
        self.assertFalse(called)
        self.assertEqual(result.planned.skipped, 1)
        row = self.conn.execute("SELECT state, failure_class FROM media_objects").fetchone()
        self.assertEqual(row["state"], "SKIPPED")
        self.assertEqual(row["failure_class"], "unsupported_url")

    def test_403_marks_stale_url_without_poisoning_archive(self):
        self.importer.import_file(self._capture(size=4))

        def transport(spec, temp_path, max_bytes, timeout_seconds):
            raise urllib.error.HTTPError(spec.url, 403, "Forbidden", {}, None)

        service = MediaBackfillService(self.conn, self.media, transport=transport)
        result = service.process_once(CompanionSettings(media_autodownload_enabled=True))
        self.assertEqual(result.stale_url, 1)
        row = self.conn.execute("SELECT state, failure_class FROM media_objects").fetchone()
        self.assertEqual(row["state"], "STALE_URL")
        self.assertEqual(row["failure_class"], "stale_url")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)

    def test_network_failure_schedules_bounded_retry(self):
        self.importer.import_file(self._capture(size=4))

        def transport(spec, temp_path, max_bytes, timeout_seconds):
            raise urllib.error.URLError("offline")

        service = MediaBackfillService(self.conn, self.media, transport=transport)
        first = service.process_once(CompanionSettings(media_autodownload_enabled=True))
        self.assertEqual(first.retryable_failed, 1)
        row = self.conn.execute("SELECT state, attempt_count, next_retry_at FROM media_objects").fetchone()
        self.assertEqual(row["state"], "FAILED_RETRYABLE")
        self.assertEqual(row["attempt_count"], 1)
        self.assertIsNotNone(row["next_retry_at"])
        # Immediate planning must honor the backoff and not hammer the URL.
        second = service.process_once(CompanionSettings(media_autodownload_enabled=True))
        self.assertEqual(second.claimed, 0)
        self.assertEqual(self.conn.execute("SELECT attempt_count FROM media_objects").fetchone()[0], 1)

    def test_cache_eviction_stays_evicted_until_explicit_manual_requeue(self):
        self.importer.import_file(self._capture(size=4))
        service = MediaBackfillService(
            self.conn,
            self.media,
            transport=self._success_transport(b"data"),
        )
        settings = CompanionSettings(
            media_cache_limit_bytes=1024,
            media_max_file_bytes=1024,
            media_retention_days=30,
            media_autodownload_enabled=True,
        )
        self.assertEqual(service.process_once(settings).cached, 1)
        maintenance = MediaCacheService(self.media, self.db).clear()
        self.assertEqual(maintenance.files_removed, 1)
        self.assertEqual(maintenance.registry_rows_reset, 1)
        row = self.conn.execute("SELECT state, failure_class FROM media_objects").fetchone()
        self.assertEqual(row["state"], "EVICTED")
        self.assertEqual(row["failure_class"], "evicted_manual_clear")

        # A running planner must not immediately undo a user's Clear action.
        cycle = service.process_once(settings)
        self.assertEqual(cycle.claimed, 0)
        self.assertEqual(self.conn.execute("SELECT state FROM media_objects").fetchone()[0], "EVICTED")

        # An explicit UI Off -> On transition re-arms *manual-clear* evictions.
        self.assertEqual(service.registry.requeue_manual_clear_evictions(), 1)
        self.assertEqual(self.conn.execute("SELECT state FROM media_objects").fetchone()[0], "KNOWN")
        self.assertEqual(service.process_once(settings).cached, 1)
        self.assertEqual(self.conn.execute("SELECT state FROM media_objects").fetchone()[0], "CACHED")


    def test_explicit_requeue_recovers_legacy_r1_evicted_without_failure_class(self):
        self.importer.import_file(self._capture(size=4))
        self.conn.execute(
            "UPDATE media_objects SET state='EVICTED', failure_class=NULL, local_relpath=NULL"
        )
        self.conn.commit()
        registry = MediaRegistryService(self.conn)
        self.assertEqual(registry.requeue_manual_clear_evictions(), 1)
        row = self.conn.execute("SELECT state, failure_class FROM media_objects").fetchone()
        self.assertEqual(row["state"], "KNOWN")
        self.assertIsNone(row["failure_class"])

    def test_explicit_manual_requeue_does_not_resurrect_policy_eviction(self):
        self.importer.import_file(self._capture(size=4))
        service = MediaBackfillService(
            self.conn, self.media, transport=self._success_transport(b"data")
        )
        generous = CompanionSettings(
            media_cache_limit_bytes=1024,
            media_max_file_bytes=1024,
            media_retention_days=30,
            media_autodownload_enabled=True,
        )
        self.assertEqual(service.process_once(generous).cached, 1)
        # Force a policy eviction by setting the total cache limit below the file size.
        tiny = CompanionSettings(
            media_cache_limit_bytes=1,
            media_max_file_bytes=1024,
            media_retention_days=30,
            media_autodownload_enabled=True,
        )
        maintenance = MediaCacheService(self.media, self.db).enforce(tiny)
        self.assertEqual(maintenance.files_removed, 1)
        row = self.conn.execute("SELECT state, failure_class FROM media_objects").fetchone()
        self.assertEqual(row["state"], "EVICTED")
        self.assertEqual(row["failure_class"], "evicted_policy")
        self.assertEqual(service.registry.requeue_manual_clear_evictions(), 0)
        self.assertEqual(self.conn.execute("SELECT state FROM media_objects").fetchone()[0], "EVICTED")


    def test_media_runtime_records_rapid_explicit_toggle_commands_in_order(self):
        settings_path = self.root / "config" / "settings.json"
        store = SettingsStore(settings_path)
        stop_event = threading.Event()
        wake_event = threading.Event()
        controls: queue.Queue[bool] = queue.Queue()
        runtime = MediaBackfillRuntime(
            database_path=self.db,
            media_root=self.media,
            settings_path=settings_path,
            dds_data_path=self.dds,
            stop_event=stop_event,
            wake_event=wake_event,
            control_queue=controls,
        )
        thread = threading.Thread(target=runtime.run, daemon=True)
        thread.start()

        # Deliberately enqueue a fast sequence; a single Event would coalesce it.
        for value in (True, False, True):
            store.update(media_autodownload_enabled=value)
            controls.put(value)
        wake_event.set()

        deadline = time.monotonic() + 3.0
        event_types = []
        while time.monotonic() < deadline:
            event_types = [
                row[0]
                for row in self.conn.execute(
                    "SELECT event_type FROM activity_events "
                    "WHERE event_type IN ('media_backfill_enabled','media_backfill_disabled') "
                    "ORDER BY id"
                )
            ]
            if event_types[-3:] == [
                "media_backfill_enabled",
                "media_backfill_disabled",
                "media_backfill_enabled",
            ]:
                break
            time.sleep(0.03)

        stop_event.set()
        wake_event.set()
        thread.join(timeout=2.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(
            event_types[-3:],
            ["media_backfill_enabled", "media_backfill_disabled", "media_backfill_enabled"],
        )

    def test_abandoned_downloading_claim_recovers_to_queue(self):
        self.importer.import_file(self._capture(size=4))
        old = "2020-01-01T00:00:00+00:00"
        self.conn.execute(
            "UPDATE media_objects SET state='DOWNLOADING', last_attempt_at=?",
            (old,),
        )
        self.conn.commit()
        service = MediaBackfillService(self.conn, self.media, transport=self._success_transport(b"data"))
        plan = service.plan(
            CompanionSettings(media_autodownload_enabled=True),
            now=datetime(2026, 9, 17, 12, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(plan.recovered_abandoned, 1)
        self.assertEqual(self.conn.execute("SELECT state FROM media_objects").fetchone()[0], "QUEUED")



class MediaAttention052Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = self.root / "dds.sqlite3"
        self.media = self.root / "media"
        self.connection = connect_database(self.db)
        self.registry = MediaRegistryService(self.connection)
        self.settings = CompanionSettings(media_autodownload_enabled=True)

    def tearDown(self):
        self.connection.close()
        self.temp.cleanup()

    def _register(self, *, size=100, url="https://cdn.discordapp.com/attachments/a/b/file.png"):
        with self.connection:
            self.connection.execute("INSERT OR REPLACE INTO guilds(id,name,last_seen_at) VALUES('g','g',?)", (utc_now(),))
            self.connection.execute("INSERT OR REPLACE INTO channels(id,guild_id,name,type,last_seen_at) VALUES('c','g','c',0,?)", (utc_now(),))
            self.connection.execute("INSERT OR REPLACE INTO users(id,username,last_seen_at) VALUES('u','u',?)", (utc_now(),))
            self.connection.execute("""INSERT OR REPLACE INTO messages(id,guild_id,source_channel_id,parent_channel_id,author_id,content,first_seen_at,last_seen_at) VALUES('m','g','c','c','u','',?,?)""", (utc_now(), utc_now()))
            key = self.registry.register_attachment(message_id='m', position=0, attachment={
                'id':'a1','filename':'file.png','contentType':'image/png','size':size,'url':url,'proxyUrl':None
            })
        return key

    def test_stable_http_size_mismatch_is_terminal_after_one_complete_response(self):
        key = self._register(size=100)
        def transport(spec, temp_path, max_bytes, timeout):
            temp_path.write_bytes(b'x' * 25)
            return TransportResult(bytes_written=25, sha256='a'*64, http_status=200, announced_size=25)
        service = MediaBackfillService(self.connection, self.media, transport=transport, max_workers=1)
        result = service.process_once(self.settings)
        row = self.registry.get(key)
        self.assertEqual(result.permanent_failed, 1)
        self.assertEqual(row.state, 'FAILED_PERMANENT')
        self.assertEqual(row.attempt_count, 1)
        self.assertEqual(row.failure_class, 'metadata_size_mismatch')

    def test_ignore_removes_attention_but_remains_visible_and_retryable(self):
        key = self._register(size=100)
        with self.connection:
            self.connection.execute("UPDATE media_objects SET state='FAILED_PERMANENT', last_error='size mismatch: expected 100, got 25', failure_class='size_mismatch' WHERE media_key=?", (key,))
        service = MediaBackfillService(self.connection, self.media, max_workers=1)
        self.assertTrue(service.ignore_issue(key))
        counts = service.counts()
        self.assertEqual(counts['permanent_failed'], 0)
        self.assertEqual(counts['ignored'], 1)
        items = service.issue_items()
        self.assertEqual(items[0]['state'], 'IGNORED')
        self.assertTrue(self.registry.prepare_manual_retry(key))
        self.assertEqual(self.registry.get(key).state, 'QUEUED')

    def test_ignored_issue_survives_signed_url_rotation_until_user_retries(self):
        key = self._register(size=100)
        with self.connection:
            self.connection.execute(
                "UPDATE media_objects SET state='FAILED_PERMANENT', last_error='broken', failure_class='http_permanent' WHERE media_key=?",
                (key,),
            )
        service = MediaBackfillService(self.connection, self.media, max_workers=1)
        self.assertTrue(service.ignore_issue(key))
        with self.connection:
            self.registry.register_attachment(
                message_id='m',
                position=0,
                attachment={
                    'id':'a1','filename':'file.png','contentType':'image/png','size':100,
                    'url':'https://cdn.discordapp.com/attachments/a/b/file.png?rotated=1','proxyUrl':None
                },
            )
        self.assertEqual(self.registry.get(key).state, 'IGNORED')

    def test_manual_retry_runs_one_download_even_when_auto_mode_is_off(self):
        key = self._register(size=4)
        with self.connection:
            self.connection.execute(
                "UPDATE media_objects SET state='FAILED_PERMANENT', last_error='broken', failure_class='http_permanent' WHERE media_key=?",
                (key,),
            )
        def transport(spec, temp_path, max_bytes, timeout):
            temp_path.write_bytes(b'data')
            return TransportResult(bytes_written=4, sha256=hashlib.sha256(b'data').hexdigest(), http_status=200, announced_size=4)
        service = MediaBackfillService(self.connection, self.media, transport=transport, max_workers=1)
        outcome = service.retry_media_once(key, CompanionSettings(media_autodownload_enabled=False))
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.state, 'CACHED')
        self.assertEqual(self.registry.get(key).state, 'CACHED')

if __name__ == "__main__":
    unittest.main()
