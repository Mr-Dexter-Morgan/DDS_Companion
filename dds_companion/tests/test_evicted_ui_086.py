from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from dds_companion.services.import_service import ImportService
from dds_companion.services.library_service import LibraryService
from dds_companion.services.media_backfill_service import MediaBackfillService
from dds_companion.services.stats_service import collect_stats
from dds_companion.storage.database import connect_database
from dds_companion.tests.test_imports import sample_capture


class EvictedUi086Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "db.sqlite3"
        self.data = self.root / "DDS_Data"
        self.data.mkdir()
        self.conn = connect_database(self.db)
        self.importer = ImportService(self.conn)
        self.service = MediaBackfillService(
            self.conn,
            self.root / "media",
            transport=lambda *args: self.fail("unexpected network request"),
        )
        capture = sample_capture()
        self.channel_id = str(capture["channel"]["id"])
        path = self.data / "capture.json"
        path.write_text(json.dumps(capture), encoding="utf-8")
        self.importer.import_file(path)
        self.media_key = self.conn.execute("SELECT media_key FROM media_objects LIMIT 1").fetchone()[0]

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _evict(self, failure_class: str = "evicted_policy") -> None:
        with self.conn:
            self.conn.execute(
                "UPDATE media_objects SET state='EVICTED', failure_class=?, local_relpath=NULL, local_size=NULL WHERE media_key=?",
                (failure_class, self.media_key),
            )

    def test_evicted_is_observable_but_not_requeued(self):
        self._evict()
        counts = self.service.counts()
        self.assertEqual(counts["evicted"], 1)
        self.assertEqual(counts["known"], 1)
        self.assertEqual(counts["queued"], 0)

        stats = collect_stats(self.conn, self.db, self.data)
        self.assertEqual(stats["media_evicted"], 1)
        self.assertEqual(stats["known_media"], 1)

        branch = LibraryService(self.conn).snapshot()[0]
        self.assertEqual(branch["media_evicted"], 1)
        self.assertEqual(branch["media_known"], 1)

        class Settings:
            media_max_file_bytes = None
            media_cache_limit_bytes = None

        self.service.plan(Settings())
        row = self.conn.execute(
            "SELECT state FROM media_objects WHERE media_key=?", (self.media_key,)
        ).fetchone()
        self.assertEqual(row[0], "EVICTED")

    def test_library_exposes_eviction_reason_and_human_copy(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication, QLabel
        from dds_companion.gui.pages import LibraryPage

        self._evict("evicted_policy")
        page_data = LibraryService(self.conn).message_page("channel", self.channel_id)
        attachment = page_data["messages"][0]["attachments"][0]
        self.assertEqual(attachment["media_state"], "EVICTED")
        self.assertEqual(attachment["media_failure_class"], "evicted_policy")

        app = QApplication.instance() or QApplication([])
        page = LibraryPage()
        widget = page._attachment_widget(attachment)
        labels = [label.text() for label in widget.findChildren(QLabel)]
        self.assertTrue(any("кэш очищен по настройкам хранения" in label for label in labels))

        manual = dict(attachment, media_failure_class="evicted_manual_clear")
        manual_widget = page._attachment_widget(manual)
        manual_labels = [label.text() for label in manual_widget.findChildren(QLabel)]
        self.assertTrue(any("кэш очищен вручную" in label for label in manual_labels))

        summary = {
            "media_count": 149,
            "media_known": 143,
            "media_cached": 30,
            "media_evicted": 113,
            "media_unresolved": 6,
        }
        self.assertIn("113 кэш очищен", page._media_cell_text(summary))
        self.assertIn("Кэш очищен: 113", page._media_tooltip(summary))
        page.close()

    def test_dashboard_shows_separate_evicted_counter_for_real_case(self):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PySide6.QtWidgets import QApplication
        from dds_companion.gui.pages import DashboardPage

        app = QApplication.instance() or QApplication([])
        page = DashboardPage()
        page.update_snapshot({
            "health": {
                "state": "RUNNING",
                "subsystems": {
                    "media": {
                        "state": "RUNNING",
                        "details": {
                            "total": 149,
                            "known": 143,
                            "cached": 30,
                            "evicted": 113,
                            "queued": 0,
                            "downloading": 0,
                            "attention": 0,
                            "attention_count": 0,
                            "ignored": 0,
                            "unresolved": 6,
                            "source_gone": 0,
                            "attention_items": [],
                        },
                    }
                },
            },
            "stats": {},
        })

        self.assertEqual(page.media_known_card.value_label.text(), "143")
        self.assertEqual(page.media_cached_card.value_label.text(), "30")
        self.assertEqual(page.media_evicted_card.title_label.text(), "Кэш очищен")
        self.assertEqual(page.media_evicted_card.value_label.text(), "113")
        self.assertIn("метаданные сохранены", page.media_evicted_card.hint_label.text())
        self.assertEqual(page.media_unresolved_card.value_label.text(), "6")
        self.assertEqual(page.media_source_gone_card.value_label.text(), "0")
        page.close()

    def test_runtime_health_summary_mentions_evicted_counter(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "dds_companion" / "services" / "media_runtime.py").read_text(encoding="utf-8")
        self.assertIn("кэш очищен: {counts['evicted']}", source)


if __name__ == "__main__":
    unittest.main()
