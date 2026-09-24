from __future__ import annotations

import copy
import json
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from datetime import datetime, timezone
from pathlib import Path

from dds_companion.gui.runtime import GuiRuntime
from dds_companion.services.discord_probe import DiscordProbeResult
from dds_companion.services.import_service import ImportResult, ImportService
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


    def test_library_snapshot_exposes_media_lifecycle_per_branch(self):
        channel_capture = sample_capture()
        self.importer.import_file(self._write(channel_capture))

        thread_capture = copy.deepcopy(sample_capture(thread=True))
        thread_capture["messages"][0]["id"] = "777777777777777777"
        thread_capture["messages"][0]["attachments"][0]["id"] = "888888888888888888"
        thread_capture["messages"][0]["attachments"][0]["url"] = "https://cdn.example/thread.png"
        self.importer.import_file(self._write(thread_capture, thread=True))

        rows = self.conn.execute(
            "SELECT media_key, attachment_id FROM media_objects ORDER BY attachment_id"
        ).fetchall()
        by_attachment = {str(row["attachment_id"]): str(row["media_key"]) for row in rows}
        self.conn.execute(
            "UPDATE media_objects SET state='UNRESOLVED', current_url=NULL WHERE media_key=?",
            (by_attachment["666666666666666666"],),
        )
        self.conn.execute(
            "UPDATE media_objects SET state='CACHED', local_relpath='aa/thread.png', local_size=123 WHERE media_key=?",
            (by_attachment["888888888888888888"],),
        )
        self.conn.commit()

        tree = LibraryService(self.conn).snapshot()
        guild = tree[0]
        channel = guild["channels"][0]
        thread = channel["threads"][0]

        self.assertEqual((guild["media_known"], guild["media_cached"], guild["media_unresolved"]), (1, 1, 1))
        self.assertEqual((channel["media_known"], channel["media_cached"], channel["media_unresolved"]), (1, 1, 1))
        self.assertEqual((thread["media_known"], thread["media_cached"], thread["media_unresolved"]), (1, 1, 0))

    def test_export_rules_default_and_nearest_explicit_override(self):
        self.importer.import_file(self._write(sample_capture()))
        thread_capture = copy.deepcopy(sample_capture(thread=True))
        thread_capture["messages"][0]["id"] = "777777777777777777"
        self.importer.import_file(self._write(thread_capture, thread=True))
        service = LibraryService(self.conn)

        tree = service.snapshot()
        guild = tree[0]
        channel = guild["channels"][0]
        thread = channel["threads"][0]
        self.assertEqual(guild["effective_export_rule"], "EXCLUDE")
        self.assertEqual(channel["effective_export_rule"], "EXCLUDE")
        self.assertEqual(thread["effective_export_rule"], "EXCLUDE")

        service.set_export_rule("guild", guild["id"], "INCLUDE")
        tree = service.snapshot()
        guild = tree[0]
        channel = guild["channels"][0]
        thread = channel["threads"][0]
        self.assertEqual(guild["export_rule"], "INCLUDE")
        self.assertEqual(channel["export_rule"], "DEFAULT")
        self.assertEqual(channel["effective_export_rule"], "INCLUDE")
        self.assertEqual(thread["effective_export_rule"], "INCLUDE")

        service.set_export_rule("channel", channel["id"], "EXCLUDE")
        service.set_export_rule("thread", thread["id"], "INCLUDE")
        tree = service.snapshot()
        channel = tree[0]["channels"][0]
        thread = channel["threads"][0]
        self.assertEqual(channel["effective_export_rule"], "EXCLUDE")
        self.assertEqual(thread["effective_export_rule"], "INCLUDE")

        service.set_export_rule("thread", thread["id"], "DEFAULT")
        tree = service.snapshot()
        self.assertEqual(tree[0]["channels"][0]["threads"][0]["effective_export_rule"], "EXCLUDE")

    def test_message_page_is_bounded_to_50_and_keeps_thread_messages_separate(self):
        capture = sample_capture()
        messages = []
        for index in range(55):
            message = copy.deepcopy(capture["messages"][0])
            message["id"] = f"{700000000000000000 + index}"
            message["timestamp"] = f"2026-09-13T11:{index:02d}:00.000Z"
            message["content"] = f"message {index}"
            message["attachments"] = []
            message["embeds"] = []
            messages.append(message)
        capture["messages"] = messages
        capture["messageCount"] = len(messages)
        capture["oldestMessageId"] = messages[0]["id"]
        capture["newestMessageId"] = messages[-1]["id"]
        self.importer.import_file(self._write(capture))

        thread_capture = copy.deepcopy(sample_capture(thread=True, content="thread only"))
        thread_capture["messages"][0]["id"] = "999999999999999998"
        self.importer.import_file(self._write(thread_capture, thread=True))

        service = LibraryService(self.conn)
        first = service.message_page("channel", "222222222222222222", limit=50)
        self.assertEqual(len(first["messages"]), 50)
        self.assertTrue(first["has_more"])
        self.assertEqual(first["messages"][0]["content"], "message 5")
        self.assertEqual(first["messages"][-1]["content"], "message 54")
        self.assertNotIn("thread only", [item["content"] for item in first["messages"]])

        second = service.message_page(
            "channel",
            "222222222222222222",
            limit=50,
            before_timestamp=first["oldest_timestamp"],
            before_id=first["oldest_id"],
        )
        self.assertEqual([item["content"] for item in second["messages"]], [f"message {i}" for i in range(5)])
        self.assertFalse(second["has_more"])

        thread_page = service.message_page("thread", "333333333333333333", limit=50)
        self.assertEqual([item["content"] for item in thread_page["messages"]], ["thread only"])


class GuiRuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.discord_probe = patch(
            "dds_companion.services.health_service.probe_discord_process",
            return_value=DiscordProbeResult(
                state="UNKNOWN",
                summary="Discord process probe isolated for tests",
                checked_at="2026-09-21T00:00:00+00:00",
            ),
        )
        self.discord_probe.start()
        self.addCleanup(self.discord_probe.stop)

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

    def _start_runtime(self, runtime: GuiRuntime) -> threading.Thread:
        thread = threading.Thread(target=runtime.run)
        thread.start()
        # unittest cleanups run LIFO: stop first, then join, then temp-dir cleanup.
        self.addCleanup(thread.join, 5.0)
        self.addCleanup(runtime.stop)
        return thread

    def test_runtime_ready_does_not_wait_for_initial_full_import(self):
        ready = threading.Event()
        import_entered = threading.Event()
        release_import = threading.Event()

        def blocked_import(_service, _dds_root):
            import_entered.set()
            release_import.wait(3.0)
            return ImportResult()

        runtime = GuiRuntime(
            dds_data=self.dds,
            app_data=self.app_data,
            poll_ms=100,
            settle_ms=50,
            ready_sink=ready.set,
        )
        with patch("dds_companion.gui.runtime.ImportService.import_all", new=blocked_import):
            thread = self._start_runtime(runtime)
            try:
                self.assertTrue(import_entered.wait(2.0), "initial import was not reached")
                self.assertTrue(
                    ready.is_set(),
                    "runtime-ready must be emitted before the potentially long initial import completes",
                )
            finally:
                release_import.set()
            runtime.stop()
            thread.join(3.0)
            self.assertFalse(thread.is_alive())

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
        thread = self._start_runtime(runtime)
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

    def test_health_transition_dedup_ignores_dynamic_reason_age(self):
        runtime = GuiRuntime(dds_data=self.dds, app_data=self.app_data)

        class Collector:
            def __init__(self):
                self.events = []

            def publish(self, **kwargs):
                self.events.append(kwargs)

        activity = Collector()
        first = {
            "state": "LIMITED",
            "summary": "DDS Plugin heartbeat stopped 100 s ago",
            "reasons": [{
                "subsystem": "plugin",
                "code": "plugin-not-ready",
                "message": "DDS Plugin heartbeat stopped 100 s ago",
            }],
            "subsystems": {"plugin": {"state": "NOT RUNNING"}},
        }
        second = copy.deepcopy(first)
        second["summary"] = "DDS Plugin heartbeat stopped 102 s ago"
        second["reasons"][0]["message"] = "DDS Plugin heartbeat stopped 102 s ago"

        runtime._record_health_transition(activity, first)
        runtime._record_health_transition(activity, second)
        self.assertEqual(len(activity.events), 1)
        self.assertEqual(activity.events[0]["event_type"], "health_initial_state")

        recovered = {
            "state": "RUNNING",
            "summary": "All capture and archive subsystems are operational",
            "reasons": [],
            "subsystems": {"plugin": {"state": "RUNNING"}},
        }
        runtime._record_health_transition(activity, recovered)
        self.assertEqual(len(activity.events), 2)
        self.assertEqual(activity.events[-1]["event_type"], "health_recovered")

    def test_runtime_serves_library_pages_and_persists_export_rule(self):
        running = threading.Event()
        page_ready = threading.Event()
        rule_ready = threading.Event()
        pages: list[dict] = []

        def on_snapshot(snapshot: dict) -> None:
            if snapshot.get("health", {}).get("state") == "RUNNING":
                running.set()
            library = snapshot.get("library") or []
            if library and library[0].get("export_rule") == "INCLUDE":
                rule_ready.set()

        def on_page(payload: dict) -> None:
            pages.append(payload)
            page_ready.set()

        runtime = GuiRuntime(
            dds_data=self.dds,
            app_data=self.app_data,
            poll_ms=100,
            settle_ms=50,
            snapshot_sink=on_snapshot,
            library_message_sink=on_page,
        )
        thread = self._start_runtime(runtime)
        self.assertTrue(running.wait(3.0), "runtime did not start")

        runtime.request_library_messages({
            "scope_kind": "channel",
            "scope_id": "222222222222222222",
            "limit": 50,
            "generation": 1,
            "reset": True,
        })
        self.assertTrue(page_ready.wait(3.0), "message page was not returned")
        self.assertEqual([item["content"] for item in pages[-1]["messages"]], ["hello"])

        runtime.request_export_rule_change("guild", "111111111111111111", "INCLUDE")
        self.assertTrue(rule_ready.wait(3.0), "export rule snapshot was not refreshed")

        runtime.stop()
        thread.join(3.0)
        self.assertFalse(thread.is_alive())

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
        thread = self._start_runtime(runtime)

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
