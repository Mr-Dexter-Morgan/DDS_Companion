from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dds_companion.services.activity_service import ActivityService
from dds_companion.services.health_service import HealthService
from dds_companion.services.import_service import ImportService
from dds_companion.services.runtime_monitor import RuntimeMonitor
from dds_companion.services.stats_service import StatsService
from dds_companion.storage.database import connect_database
from dds_companion.storage.migrations import BASE_SCHEMA_SQL, apply_migrations
from dds_companion.tests.test_imports import sample_capture
from dds_companion.watcher.file_events import WatcherEvent


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dds = self.root / "DDS_Data"
        self.dds.mkdir(parents=True)
        (self.dds / "manifest.json").write_text('{"storageSchemaVersion":1}', encoding="utf-8")
        self.app = self.root / "app"
        self.db = self.app / "database" / "dds.sqlite3"
        self.cache = self.app / "cache"
        self.media = self.app / "media"
        self.logs = self.app / "logs"
        for path in (self.cache, self.media, self.logs):
            path.mkdir(parents=True, exist_ok=True)
        self.conn = connect_database(self.db)
        self.importer = ImportService(self.conn)
        self.activity = ActivityService(self.conn)
        self.health = HealthService(self.conn, self.dds)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def write_capture(self, content: str = "hello") -> Path:
        base = self.dds / "guilds" / "111111111111111111" / "channels" / "222222222222222222"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "capture.json"
        path.write_text(json.dumps(sample_capture(content=content), ensure_ascii=False), encoding="utf-8")
        return path

    def test_activity_is_persisted_and_subscribers_are_isolated(self):
        received = []
        self.activity.subscribe(lambda event: (_ for _ in ()).throw(RuntimeError("UI exploded")))
        self.activity.subscribe(received.append)
        record = self.activity.publish(
            subsystem="runtime",
            event_type="test_event",
            summary="hello activity",
            details={"x": 1},
        )
        self.assertTrue(record.persisted)
        self.assertIsNotNone(record.id)
        self.assertEqual(len(received), 1)
        self.assertEqual(self.activity.count(), 1)
        self.assertEqual(self.activity.recent(1)[0].summary, "hello activity")

    def test_import_activity_carries_context_and_counts(self):
        path = self.write_capture()
        result = self.importer.import_file(path)
        record = self.activity.publish_import_result(capture_path=path, result=result)
        self.assertEqual(record.guild_id, "111111111111111111")
        self.assertEqual(record.parent_channel_id, "222222222222222222")
        self.assertEqual(record.messages_new, 1)
        self.assertEqual(record.attachments_registered, 1)
        self.assertIn("+1 messages imported", record.summary)

    def test_health_reports_core_subsystems(self):
        self.health.refresh_core(watcher_expected=True, watcher_state="RUNNING")
        self.health.set_subsystem("importer", "RUNNING", "ok")
        snapshot = self.health.snapshot(watcher_expected=True)
        self.assertEqual(snapshot["state"], "RUNNING")
        self.assertEqual(snapshot["subsystems"]["database"]["state"], "RUNNING")
        self.assertEqual(snapshot["subsystems"]["dds_data"]["state"], "RUNNING")
        self.assertEqual(snapshot["subsystems"]["watcher"]["state"], "RUNNING")

    def test_stale_watcher_is_degraded(self):
        self.health.refresh_core(watcher_expected=True, watcher_state="RUNNING")
        stale = (datetime.now(timezone.utc) - timedelta(minutes=5)).isoformat()
        with self.conn:
            self.conn.execute(
                "UPDATE subsystem_health SET updated_at=? WHERE subsystem='watcher'",
                (stale,),
            )
        snapshot = self.health.snapshot(watcher_expected=True, stale_after_seconds=30)
        self.assertEqual(snapshot["subsystems"]["watcher"]["state"], "DEGRADED")
        self.assertTrue(snapshot["subsystems"]["watcher"]["stale"])
        self.assertEqual(snapshot["state"], "DEGRADED")

    def test_runtime_monitor_degrades_then_recovers_importer(self):
        monitor = RuntimeMonitor(self.activity, self.health)
        good_path = self.write_capture("recovered")
        self.importer.record_failure("watcher_import", str(good_path), ValueError("bad capture"))
        monitor.handle_watcher_event(
            WatcherEvent(kind="failed", path=good_path, detail="ValueError: bad capture")
        )
        self.assertEqual(
            self.health.snapshot(watcher_expected=False)["subsystems"]["importer"]["state"],
            "DEGRADED",
        )

        result = self.importer.import_file(good_path)
        monitor.handle_watcher_event(WatcherEvent(kind="imported", path=good_path, result=result))
        self.assertEqual(
            self.health.snapshot(watcher_expected=False)["subsystems"]["importer"]["state"],
            "RUNNING",
        )
        self.assertEqual(self.activity.recent(1)[0].event_type, "capture_imported")

    def test_stats_session_baseline_and_media_split(self):
        stats = StatsService(
            self.conn,
            self.db,
            self.dds,
            cache_path=self.cache,
            media_path=self.media,
            logs_path=self.logs,
        )
        path = self.write_capture()
        self.importer.import_file(path)
        self.activity.publish(subsystem="test", event_type="x", summary="x")
        snapshot = stats.snapshot()
        self.assertEqual(snapshot.messages, 1)
        self.assertEqual(snapshot.session_messages_added, 1)
        self.assertEqual(snapshot.session_imports_added, 1)
        self.assertEqual(snapshot.known_media, 1)
        self.assertEqual(snapshot.cached_media_files, 0)
        self.assertGreaterEqual(snapshot.session_activity_events_added, 1)

    def test_schema_v1_archive_upgrades_additively_to_v2(self):
        legacy_db = self.root / "legacy.sqlite3"
        legacy = sqlite3.connect(legacy_db)
        legacy.row_factory = sqlite3.Row
        legacy.execute("PRAGMA foreign_keys=ON")
        legacy.executescript(BASE_SCHEMA_SQL)
        legacy.execute("INSERT INTO schema_meta(key, value) VALUES('schema_version', '1')")
        legacy.execute(
            "INSERT INTO guilds(id, name, last_seen_at) VALUES('1','keep-me','2026-09-13T00:00:00Z')"
        )
        legacy.commit()
        apply_migrations(legacy)
        self.assertEqual(legacy.execute("SELECT value FROM schema_meta WHERE key='schema_version'").fetchone()[0], "2")
        self.assertEqual(legacy.execute("SELECT name FROM guilds WHERE id='1'").fetchone()[0], "keep-me")
        tables = {row[0] for row in legacy.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("activity_events", tables)
        self.assertIn("subsystem_health", tables)
        legacy.close()


if __name__ == "__main__":
    unittest.main()
