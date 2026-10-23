from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sqlite3
import tempfile
import threading
import unittest
from unittest import mock
import urllib.error
from pathlib import Path

from dds_companion.core.settings import CompanionSettings
from dds_companion.services.import_service import ImportService
from dds_companion.services.library_service import LibraryService
from dds_companion.services.media_backfill_service import (
    DownloadSpec,
    MediaBackfillService,
    TransportResult,
)
from dds_companion.storage.database import connect_database
from dds_companion.storage import database as database_mod
from dds_companion.storage import migrations
from dds_companion.tests.test_imports import sample_capture


ALLOWED_URL = "https://cdn.discordapp.com/attachments/1/2/file.png?ex=test"


class ManualRecache088Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "database" / "dds.sqlite3"
        self.media = self.root / "media"
        self.dds = self.root / "DDS_Data"
        self.conn = connect_database(self.db)
        self.importer = ImportService(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _capture(
        self,
        *,
        revision: int = 1,
        channel_id: str = "222222222222222222",
        message_id: str = "444444444444444444",
        attachment_id: str = "666666666666666666",
        url: str | None = ALLOWED_URL,
        size: int = 4,
    ) -> Path:
        data = sample_capture()
        data["captureRevision"] = revision
        data["channel"]["id"] = channel_id
        data["messages"][0]["id"] = message_id
        data["messages"][0]["channelId"] = channel_id
        data["messages"][0]["attachments"][0]["id"] = attachment_id
        data["messages"][0]["attachments"][0]["url"] = url
        data["messages"][0]["attachments"][0]["size"] = size
        base = self.dds / "guilds" / "111111111111111111" / "channels" / channel_id
        base.mkdir(parents=True, exist_ok=True)
        path = base / f"capture-{revision}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    @staticmethod
    def _success_transport(payload: bytes = b"data"):
        def transport(
            spec: DownloadSpec,
            temp_path: Path,
            max_bytes: int | None,
            timeout_seconds: float,
        ) -> TransportResult:
            temp_path.write_bytes(payload)
            return TransportResult(
                bytes_written=len(payload),
                sha256=hashlib.sha256(payload).hexdigest(),
                http_status=200,
                announced_size=len(payload),
            )

        return transport

    def _import_one(self, **kwargs) -> str:
        self.importer.import_file(self._capture(**kwargs))
        return self.conn.execute("SELECT media_key FROM media_objects LIMIT 1").fetchone()[0]

    def _evict(self, media_key: str, *, current_url: str | None = ALLOWED_URL) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE media_objects
                SET state='EVICTED', current_url=?, local_relpath=NULL, local_size=NULL,
                    cached_at='2020-01-01T00:00:00+00:00', failure_class='evicted_policy',
                    manual_recache_requested=0
                WHERE media_key=?
                """,
                (current_url, media_key),
            )

    def test_schema_v6_persists_manual_recache_flag(self):
        columns = {
            row[1]: row for row in self.conn.execute("PRAGMA table_info(media_objects)").fetchall()
        }
        self.assertIn("manual_recache_requested", columns)
        self.assertEqual(columns["manual_recache_requested"][4], "0")
        self.assertEqual(
            self.conn.execute(
                "SELECT value FROM schema_meta WHERE key='schema_version'"
            ).fetchone()[0],
            "6",
        )

    def test_connect_database_retries_transient_schema_lock(self):
        retry_db = self.root / "retry-lock.sqlite3"
        real_apply = database_mod.apply_migrations
        calls = {"count": 0}

        def flaky_apply(connection):
            calls["count"] += 1
            if calls["count"] == 1:
                raise sqlite3.OperationalError("database is locked")
            return real_apply(connection)

        with mock.patch.object(database_mod, "apply_migrations", flaky_apply), mock.patch.object(
            database_mod.time, "sleep", return_value=None
        ):
            connection = database_mod.connect_database(retry_db)
        try:
            self.assertEqual(calls["count"], 2)
            self.assertEqual(
                connection.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0],
                "6",
            )
        finally:
            connection.close()

    def test_schema_v6_parallel_startup_migration_is_race_safe(self):
        legacy_db = self.root / "parallel-v5.sqlite3"
        legacy = sqlite3.connect(legacy_db)
        try:
            legacy.executescript(migrations.BASE_SCHEMA_SQL)
            legacy.executescript(migrations.V2_SCHEMA_SQL)
            legacy.executescript(migrations.V3_SCHEMA_SQL)
            legacy.executescript(migrations.V4_SCHEMA_SQL)
            legacy.executescript(migrations.V5_SCHEMA_SQL)
            legacy.execute(
                "INSERT INTO schema_meta(key, value) VALUES('schema_version', '5') "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value"
            )
            legacy.commit()
        finally:
            legacy.close()

        barrier = threading.Barrier(2)
        seen_threads: set[int] = set()
        seen_lock = threading.Lock()
        original_columns = migrations._media_object_columns

        def synchronized_columns(connection):
            columns = original_columns(connection)
            thread_id = threading.get_ident()
            with seen_lock:
                first_read = thread_id not in seen_threads
                if first_read:
                    seen_threads.add(thread_id)
            if first_read:
                barrier.wait(timeout=5.0)
            return columns

        errors: list[BaseException] = []

        def open_archive():
            connection = None
            try:
                connection = connect_database(legacy_db)
            except BaseException as exc:  # surfaced below with both worker results
                errors.append(exc)
            finally:
                if connection is not None:
                    connection.close()

        with mock.patch.object(migrations, "_media_object_columns", synchronized_columns):
            workers = [threading.Thread(target=open_archive) for _ in range(2)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join(timeout=10.0)
            self.assertTrue(all(not worker.is_alive() for worker in workers))

        self.assertEqual(errors, [])
        check = sqlite3.connect(legacy_db)
        try:
            columns = {row[1] for row in check.execute("PRAGMA table_info(media_objects)")}
            self.assertIn("manual_recache_requested", columns)
            self.assertEqual(
                check.execute(
                    "SELECT value FROM schema_meta WHERE key='schema_version'"
                ).fetchone()[0],
                "6",
            )
        finally:
            check.close()

    def test_download_again_caches_and_clears_intent_even_with_auto_off(self):
        key = self._import_one()
        self._evict(key)
        service = MediaBackfillService(
            self.conn, self.media, transport=self._success_transport(), max_workers=1
        )
        outcome = service.recache_media_once(
            key, CompanionSettings(media_autodownload_enabled=False)
        )
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.state, "CACHED")
        row = self.conn.execute(
            "SELECT state, manual_recache_requested, cached_at, local_relpath FROM media_objects WHERE media_key=?",
            (key,),
        ).fetchone()
        self.assertEqual(row["state"], "CACHED")
        self.assertEqual(row["manual_recache_requested"], 0)
        self.assertNotEqual(row["cached_at"], "2020-01-01T00:00:00+00:00")
        self.assertTrue((self.media / row["local_relpath"]).is_file())

    def test_expired_url_keeps_intent_and_fresh_rediscovery_finishes_with_auto_off(self):
        key = self._import_one()
        self._evict(key)

        def expired(*_args):
            raise urllib.error.HTTPError(ALLOWED_URL, 403, "expired", {}, None)

        service = MediaBackfillService(self.conn, self.media, transport=expired, max_workers=1)
        outcome = service.recache_media_once(
            key, CompanionSettings(media_autodownload_enabled=False)
        )
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.state, "UNRESOLVED")
        row = self.conn.execute(
            "SELECT state, current_url, manual_recache_requested FROM media_objects WHERE media_key=?",
            (key,),
        ).fetchone()
        self.assertEqual(row["state"], "UNRESOLVED")
        self.assertIsNone(row["current_url"])
        self.assertEqual(row["manual_recache_requested"], 1)

        fresh = ALLOWED_URL + "&fresh=1"
        self.importer.import_file(self._capture(revision=2, url=fresh))
        rediscovered = self.conn.execute(
            "SELECT state, current_url, manual_recache_requested FROM media_objects WHERE media_key=?",
            (key,),
        ).fetchone()
        self.assertEqual(rediscovered["state"], "KNOWN")
        self.assertEqual(rediscovered["current_url"], fresh)
        self.assertEqual(rediscovered["manual_recache_requested"], 1)

        service.transport = self._success_transport()
        cycle = service.process_manual_recache_pending(
            CompanionSettings(media_autodownload_enabled=False)
        )
        self.assertEqual(cycle.cached, 1)
        final = self.conn.execute(
            "SELECT state, manual_recache_requested FROM media_objects WHERE media_key=?",
            (key,),
        ).fetchone()
        self.assertEqual(final["state"], "CACHED")
        self.assertEqual(final["manual_recache_requested"], 0)

    def test_retryable_failure_keeps_intent_and_retries_with_auto_off(self):
        key = self._import_one()
        self._evict(key)
        calls = {"n": 0}

        def flaky(spec, temp_path, max_bytes, timeout_seconds):
            calls["n"] += 1
            if calls["n"] == 1:
                raise urllib.error.URLError("temporary outage")
            temp_path.write_bytes(b"data")
            return TransportResult(
                bytes_written=4, sha256=hashlib.sha256(b"data").hexdigest(),
                http_status=200, announced_size=4,
            )

        service = MediaBackfillService(self.conn, self.media, transport=flaky, max_workers=1)
        first = service.recache_media_once(key, CompanionSettings(media_autodownload_enabled=False))
        self.assertEqual(first.state, "FAILED_RETRYABLE")
        row = self.conn.execute(
            "SELECT state, manual_recache_requested FROM media_objects WHERE media_key=?", (key,)
        ).fetchone()
        self.assertEqual((row["state"], row["manual_recache_requested"]), ("FAILED_RETRYABLE", 1))
        with self.conn:
            self.conn.execute("UPDATE media_objects SET next_retry_at=NULL WHERE media_key=?", (key,))
        cycle = service.process_manual_recache_pending(CompanionSettings(media_autodownload_enabled=False))
        self.assertEqual(cycle.cached, 1)
        row = self.conn.execute(
            "SELECT state, manual_recache_requested FROM media_objects WHERE media_key=?", (key,)
        ).fetchone()
        self.assertEqual((row["state"], row["manual_recache_requested"]), ("CACHED", 0))

    def test_terminal_policy_result_clears_recache_intent(self):
        key = self._import_one(size=100)
        self._evict(key)
        service = MediaBackfillService(self.conn, self.media, transport=self._success_transport(), max_workers=1)
        outcome = service.recache_media_once(
            key,
            CompanionSettings(
                media_autodownload_enabled=False,
                media_max_file_bytes=10,
                media_cache_limit_bytes=1024,
            ),
        )
        self.assertEqual(outcome.state, "TOO_LARGE")
        row = self.conn.execute(
            "SELECT state, manual_recache_requested FROM media_objects WHERE media_key=?", (key,)
        ).fetchone()
        self.assertEqual((row["state"], row["manual_recache_requested"]), ("TOO_LARGE", 0))

    def test_missing_url_waits_for_rediscovery_instead_of_losing_request(self):
        key = self._import_one()
        self._evict(key, current_url=None)
        service = MediaBackfillService(
            self.conn, self.media, transport=self._success_transport(), max_workers=1
        )
        outcome = service.recache_media_once(
            key, CompanionSettings(media_autodownload_enabled=False)
        )
        self.assertIsNotNone(outcome)
        self.assertEqual(outcome.state, "UNRESOLVED")
        record = service.registry.get(key)
        self.assertEqual(record.state, "UNRESOLVED")
        self.assertTrue(record.manual_recache_requested)

    def test_evicted_without_explicit_request_stays_evicted_after_rotated_url(self):
        key = self._import_one()
        self._evict(key)
        self.importer.import_file(self._capture(revision=2, url=ALLOWED_URL + "&rotated=1"))
        row = self.conn.execute(
            "SELECT state, manual_recache_requested FROM media_objects WHERE media_key=?",
            (key,),
        ).fetchone()
        self.assertEqual(row["state"], "EVICTED")
        self.assertEqual(row["manual_recache_requested"], 0)

    def test_bulk_recache_marks_only_selected_channel_branch(self):
        first = self._import_one(
            channel_id="222222222222222222",
            message_id="444444444444444444",
            attachment_id="666666666666666666",
        )
        self.importer.import_file(
            self._capture(
                channel_id="333333333333333333",
                message_id="555555555555555555",
                attachment_id="777777777777777777",
            )
        )
        second = "attachment:777777777777777777"
        self._evict(first)
        self._evict(second)
        service = MediaBackfillService(self.conn, self.media, max_workers=1)
        changed = service.request_recache_scope("channel", "222222222222222222")
        self.assertEqual(changed, 1)
        states = {
            row["media_key"]: (row["state"], row["manual_recache_requested"])
            for row in self.conn.execute(
                "SELECT media_key, state, manual_recache_requested FROM media_objects"
            )
        }
        self.assertEqual(states[first], ("QUEUED", 1))
        self.assertEqual(states[second], ("EVICTED", 0))

    @unittest.skipUnless(importlib.util.find_spec("PySide6"), "PySide6 unavailable in sandbox")
    def test_library_exposes_download_again_button_and_pending_copy(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QPushButton, QLabel
        from dds_companion.gui.pages import LibraryPage

        key = self._import_one()
        self._evict(key)
        attachment = LibraryService(self.conn).message_page(
            "channel", "222222222222222222"
        )["messages"][0]["attachments"][0]
        called: list[str] = []
        app = QApplication.instance() or QApplication([])
        page = LibraryPage(on_media_recache=called.append)
        widget = page._attachment_widget(attachment)
        buttons = [b for b in widget.findChildren(QPushButton) if b.text() == "Скачать снова"]
        self.assertEqual(len(buttons), 1)
        buttons[0].click()
        self.assertEqual(called, [key])

        with self.conn:
            self.conn.execute(
                "UPDATE media_objects SET state='UNRESOLVED', manual_recache_requested=1 WHERE media_key=?",
                (key,),
            )
        pending = LibraryService(self.conn).message_page(
            "channel", "222222222222222222"
        )["messages"][0]["attachments"][0]
        pending_widget = page._attachment_widget(pending)
        labels = [label.text() for label in pending_widget.findChildren(QLabel)]
        self.assertTrue(any("ждёт свежую ссылку" in label for label in labels))
        page.close()


if __name__ == "__main__":
    unittest.main()
