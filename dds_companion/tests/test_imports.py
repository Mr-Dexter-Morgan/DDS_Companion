from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dds_companion.services.import_service import ImportService
from dds_companion.storage.database import connect_database


def sample_capture(*, thread: bool = False, content: str = "hello") -> dict:
    guild_id = "111111111111111111"
    parent_id = "222222222222222222"
    effective_id = "333333333333333333" if thread else parent_id
    return {
        "schemaVersion": 2,
        "ddsVersion": "0.5.2",
        "captureRevision": 7,
        "capturedAt": "2026-09-13T12:00:00.000Z",
        "reason": "test",
        "source": {"kind": "discord-client-message-store", "localOnly": True, "loading": False},
        "account": {"id": "999999999999999999", "username": "dexter", "globalName": "Dexter"},
        "guild": {"id": guild_id, "name": "Guild"},
        "channel": {
            "id": effective_id,
            "name": "thread-name" if thread else "general",
            "type": 11 if thread else 0,
            "guildId": guild_id,
            "parentId": parent_id if thread else None,
        },
        "thread": {
            "id": effective_id,
            "name": "thread-name",
            "parentChannelId": parent_id,
            "parentChannelName": "forum",
            "parentChannelType": 15,
        } if thread else None,
        "route": {"path": "/channels/x/y", "selectedChannelId": parent_id, "effectiveChannelId": effective_id},
        "messageCount": 1,
        "oldestMessageId": "444444444444444444",
        "newestMessageId": "444444444444444444",
        "messages": [{
            "id": "444444444444444444",
            "channelId": effective_id,
            "guildId": guild_id,
            "type": 0,
            "timestamp": "2026-09-13T11:59:00.000Z",
            "editedTimestamp": None,
            "author": {
                "id": "555555555555555555",
                "username": "user",
                "globalName": "User",
                "displayName": "User",
                "bot": False,
            },
            "content": content,
            "pinned": False,
            "tts": False,
            "attachments": [{
                "id": "666666666666666666",
                "filename": "image.png",
                "title": None,
                "description": None,
                "contentType": "image/png",
                "size": 123,
                "url": "https://cdn.example/image.png",
                "proxyUrl": None,
                "width": 10,
                "height": 20,
                "ephemeral": False,
            }],
            "embeds": [{
                "type": "rich",
                "url": None,
                "title": "T",
                "description": "D",
                "timestamp": None,
                "color": None,
                "provider": None,
                "author": None,
                "thumbnail": None,
                "image": None,
                "fields": [],
                "footer": None,
            }],
            "messageReference": None,
        }],
    }


class ImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "db.sqlite3"
        self.conn = connect_database(self.db)
        self.service = ImportService(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def write_capture(self, data: dict, *, thread: bool = False) -> Path:
        base = self.root / "DDS_Data" / "guilds" / "111111111111111111" / "channels" / "222222222222222222"
        if thread:
            base = base / "threads" / "333333333333333333"
        base.mkdir(parents=True, exist_ok=True)
        path = base / "capture.json"
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        return path

    def test_channel_import_and_dedup(self):
        path = self.write_capture(sample_capture())
        first = self.service.import_file(path)
        second = self.service.import_file(path)
        self.assertEqual(first.messages_inserted, 1)
        self.assertEqual(second.skipped_unchanged, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM attachments").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM embeds").fetchone()[0], 1)

    def test_changed_capture_updates_message_without_losing_archive(self):
        path = self.write_capture(sample_capture(content="v1"))
        self.service.import_file(path)
        path.write_text(json.dumps(sample_capture(content="v2"), ensure_ascii=False), encoding="utf-8")
        result = self.service.import_file(path)
        self.assertEqual(result.messages_updated, 1)
        row = self.conn.execute("SELECT content FROM messages WHERE id='444444444444444444'").fetchone()
        self.assertEqual(row[0], "v2")
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM capture_imports").fetchone()[0], 2)

    def test_thread_import_preserves_parent_relationship(self):
        path = self.write_capture(sample_capture(thread=True), thread=True)
        self.service.import_file(path)
        thread = self.conn.execute("SELECT parent_channel_id FROM threads WHERE id='333333333333333333'").fetchone()
        message = self.conn.execute("SELECT parent_channel_id, thread_id FROM messages").fetchone()
        self.assertEqual(thread[0], "222222222222222222")
        self.assertEqual(message[0], "222222222222222222")
        self.assertEqual(message[1], "333333333333333333")

    def test_bad_file_isolated_in_import_all(self):
        good = self.write_capture(sample_capture())
        bad_dir = good.parent / "threads" / "777777777777777777"
        bad_dir.mkdir(parents=True)
        (bad_dir / "capture.json").write_text("{bad json", encoding="utf-8")
        result = self.service.import_all(self.root / "DDS_Data")
        self.assertEqual(result.failed, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM failed_jobs").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
