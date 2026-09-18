from __future__ import annotations

import copy
import json
import tempfile
import threading
import time
import unittest
from datetime import datetime, timezone
from pathlib import Path

from dds_companion.gui.runtime import GuiRuntime
from dds_companion.services.import_service import ImportService
from dds_companion.services.library_service import LibraryService
from dds_companion.storage.database import connect_database
from dds_companion.tests.test_imports import sample_capture


class LibraryServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.conn = connect_database(self.root / "archive.sqlite3")
        self.importer = ImportService(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _write(self, data: dict, *, thread: bool = False) -> Path:
        base = self.root / "DDS_Data" / "guilds" / "111111111111111111" / "channels" / "222222222222222222"
        if thread:
            base = base / "threads" / "333333333333333333"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "capture.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_library_snapshot_preserves_guild_channel_thread_hierarchy(self):
        channel_capture = sample_capture()
        self.importer.import_file(self._write(channel_capture))

        thread_capture = copy.deepcopy(sample_capture(thread=True))
        thread_capture["messages"][0]["id"] = "777777777777777777"
        thread_capture["oldestMessageId"] = "777777777777777777"
        thread_capture["newestMessageId"] = "777777777777777777"
        self.importer.import_file(self._write(thread_capture, thread=True))

        tree = LibraryService(self.conn).snapshot()
        self.assertEqual(len(tree), 1)
        self.assertEqual(tree[0]["message_count"], 2)
        self.assertEqual(tree[0]["media_count"], 2)
        self.assertEqual(tree[0]["last_activity"], "2026-09-13T11:59:00.000Z")
        self.assertEqual(len(tree[0]["channels"]), 1)
        channel = tree[0]["channels"][0]
        self.assertEqual(channel["direct_message_count"], 1)
        self.assertEqual(channel["message_count"], 2)
        self.assertEqual(channel["media_count"], 2)
        self.assertEqual(len(channel["threads"]), 1)
        self.assertEqual(channel["threads"][0]["message_count"], 1)
        self.assertEqual(channel["threads"][0]["media_count"], 1)
        self.assertEqual(channel["threads"][0]["last_activity"], "2026-09-13T11:59:00.000Z")


class GuiRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dds = self.root / "DDS_Data"
        self.app_data = self.root / "Companion"
        self.dds.mkdir(parents=True)
        (self.dds / "manifest.json").write_text(
            json.dumps({
                "storageSchemaVersion": 1,
                "captureSchemaVersion": 2,
                "ddsVersion": "0.5.3",
                "capabilities": ["plugin-heartbeat-v1"],
            }),
            encoding="utf-8",
        )
        (self.dds / "plugin_heartbeat.json").write_text(
            json.dumps({
                "schemaVersion": 1,
                "pluginVersion": "0.5.3",
                "state": "RUNNING",
                "updatedAt": datetime.now(timezone.utc).isoformat(),
                "heartbeatIntervalMs": 30000,
            }),
            encoding="utf-8",
        )
        capture_dir = self.dds / "guilds" / "111111111111111111" / "channels" / "222222222222222222"
        capture_dir.mkdir(parents=True)
        self.capture_path = capture_dir / "capture.json"
        self.capture_path.write_text(json.dumps(sample_capture()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_runtime_emits_real_snapshot_and_stops_cleanly(self):
        snapshots: list[dict] = []
        activities: list[dict] = []
        ready = threading.Event()
        stopped = threading.Event()

        def on_snapshot(snapshot: dict) -> None:
            snapshots.append(snapshot)
            if snapshot.get("health", {}).get("state") == "RUNNING":
                ready.set()

        runtime = GuiRuntime(
            dds_data=self.dds,
            app_data=self.app_data,
            poll_ms=100,
            settle_ms=50,
            snapshot_sink=on_snapshot,
            activity_sink=activities.append,
            stopped_sink=stopped.set,
        )
        thread = threading.Thread(target=runtime.run)
        thread.start()
        self.assertTrue(ready.wait(3.0), "GUI runtime did not reach RUNNING")
        runtime.stop()
        thread.join(3.0)
        self.assertFalse(thread.is_alive())
        self.assertTrue(stopped.is_set())
        self.assertGreaterEqual(len(snapshots), 1)
        first_running = next(s for s in snapshots if s["health"]["state"] == "RUNNING")
        self.assertEqual(first_running["stats"]["messages"], 1)
        self.assertEqual(first_running["stats"]["guilds"], 1)
        self.assertEqual(len(first_running["library"]), 1)
        self.assertTrue(any(a.get("event_type") == "startup_sync" for a in activities))

    def test_runtime_detects_live_capture_change(self):
        activity_event = threading.Event()
        imported: list[dict] = []

        def on_activity(record: dict) -> None:
            if record.get("event_type") == "capture_imported" and record.get("messages_new") == 1:
                imported.append(record)
                activity_event.set()

        runtime = GuiRuntime(
            dds_data=self.dds,
            app_data=self.app_data,
            poll_ms=100,
            settle_ms=50,
            activity_sink=on_activity,
        )
        thread = threading.Thread(target=runtime.run)
        thread.start()

        # Wait until the initial import is complete before publishing a changed
        # snapshot with one additional Discord message.
        deadline = time.time() + 3.0
        db_path = self.app_data / "database" / "dds.sqlite3"
        while time.time() < deadline:
            if db_path.exists():
                try:
                    conn = connect_database(db_path)
                    count = conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                    conn.close()
                    if count == 1:
                        break
                except Exception:
                    pass
            time.sleep(0.05)
        else:
            runtime.stop()
            thread.join(2.0)
            self.fail("initial import did not complete")

        changed = copy.deepcopy(sample_capture())
        second = copy.deepcopy(changed["messages"][0])
        second["id"] = "888888888888888888"
        second["content"] = "second message"
        changed["messages"].append(second)
        changed["messageCount"] = 2
        changed["newestMessageId"] = second["id"]
        changed["captureRevision"] = 8
        self.capture_path.write_text(json.dumps(changed), encoding="utf-8")

        self.assertTrue(activity_event.wait(4.0), "live capture change was not imported")
        runtime.stop()
        thread.join(3.0)
        self.assertFalse(thread.is_alive())
        self.assertEqual(imported[-1]["messages_new"], 1)
        self.assertEqual(imported[-1]["messages_refreshed"], 1)


if __name__ == "__main__":
    unittest.main()
