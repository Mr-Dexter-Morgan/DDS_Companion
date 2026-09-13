from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from dds_companion.services.import_service import ImportService
from dds_companion.storage.database import connect_database
from dds_companion.tests.test_imports import sample_capture
from dds_companion.watcher.capture_watcher import CaptureWatcher


class WatcherTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dds = self.root / "DDS_Data"
        self.db = self.root / "db.sqlite3"
        self.conn = connect_database(self.db)
        self.importer = ImportService(self.conn)
        self.events = []
        self.watcher = CaptureWatcher(
            self.dds,
            self.importer,
            self.conn,
            settle_seconds=0.5,
            heartbeat_seconds=9999,
            on_event=self.events.append,
        )

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def capture_path(self, *, thread: bool = False) -> Path:
        base = self.dds / "guilds" / "111111111111111111" / "channels" / "222222222222222222"
        if thread:
            base = base / "threads" / "333333333333333333"
        base.mkdir(parents=True, exist_ok=True)
        return base / "capture.json"

    def write_capture(self, data: dict, *, thread: bool = False) -> Path:
        path = self.capture_path(thread=thread)
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_changed_capture_waits_for_settle_then_imports(self):
        path = self.write_capture(sample_capture(content="v1"))
        self.importer.import_file(path)
        self.watcher.prime()

        self.write_capture(sample_capture(content="v2 with different length"))
        first = self.watcher.scan_once(now=1.0)
        self.assertIn("changed", [event.kind for event in first])
        self.assertNotIn("imported", [event.kind for event in first])

        second = self.watcher.scan_once(now=1.6)
        self.assertIn("imported", [event.kind for event in second])
        content = self.conn.execute(
            "SELECT content FROM messages WHERE id='444444444444444444'"
        ).fetchone()[0]
        self.assertEqual(content, "v2 with different length")

    def test_new_capture_is_discovered_and_imported(self):
        self.watcher.prime()
        self.write_capture(sample_capture())
        self.watcher.scan_once(now=2.0)
        events = self.watcher.scan_once(now=2.6)
        self.assertIn("imported", [event.kind for event in events])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)

    def test_removed_capture_preserves_archive(self):
        path = self.write_capture(sample_capture())
        self.importer.import_file(path)
        self.watcher.prime()
        path.unlink()
        events = self.watcher.scan_once(now=3.0)
        self.assertIn("deleted", [event.kind for event in events])
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)

    def test_bad_capture_is_isolated_then_resolves_after_fix(self):
        path = self.write_capture(sample_capture())
        self.importer.import_file(path)
        self.watcher.prime()

        path.write_text("{bad json", encoding="utf-8")
        self.watcher.scan_once(now=4.0)
        failed = self.watcher.scan_once(now=4.6)
        self.assertIn("failed", [event.kind for event in failed])
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM failed_jobs WHERE resolved_at IS NULL").fetchone()[0],
            1,
        )

        self.write_capture(sample_capture(content="recovered and valid"))
        self.watcher.scan_once(now=5.0)
        recovered = self.watcher.scan_once(now=5.6)
        self.assertIn("imported", [event.kind for event in recovered])
        self.assertEqual(
            self.conn.execute("SELECT COUNT(*) FROM failed_jobs WHERE resolved_at IS NULL").fetchone()[0],
            0,
        )
        self.assertIsNone(
            self.conn.execute("SELECT value FROM application_state WHERE key='last_error'").fetchone()
        )


if __name__ == "__main__":
    unittest.main()
