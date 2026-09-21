from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path

from dds_companion import __version__
from dds_companion.core.paths import build_runtime_paths, ensure_runtime_dirs
from dds_companion.core.settings import SettingsStore
from dds_companion.core.formatting import human_storage_delta
from dds_companion.services.archive_reset_service import (
    load_capture_not_before_ns,
    reset_local_archive,
    reset_marker_path,
)
from dds_companion.services.import_service import ImportService
from dds_companion.services.media_cache_service import MediaCacheService
from dds_companion.storage.database import connect_database
from dds_companion.tests.test_imports import sample_capture


class ArchiveReset061Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.dds_data = self.root / "DDS_Data"
        self.app_data = self.root / "AppData"
        self.paths = build_runtime_paths(self.dds_data, self.app_data)
        ensure_runtime_dirs(self.paths)
        self.capture = (
            self.dds_data
            / "guilds"
            / "111111111111111111"
            / "channels"
            / "222222222222222222"
            / "capture.json"
        )
        self.capture.parent.mkdir(parents=True, exist_ok=True)
        self.capture.write_text(json.dumps(sample_capture()), encoding="utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def test_full_reset_removes_archive_and_media_preserves_settings_and_blocks_old_captures(self):
        settings = SettingsStore(self.paths.settings)
        settings.update(media_autodownload_enabled=True, confirm_media_cache_clear=False)

        connection = connect_database(self.paths.database)
        importer = ImportService(connection)
        imported = importer.import_all(self.paths.dds_data)
        self.assertEqual(imported.imported, 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)
        connection.close()

        media_file = self.paths.media / "objects" / "aa" / "cached.bin"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"cached-payload")

        result = reset_local_archive(self.paths)
        self.assertTrue(result.database_recreated)
        self.assertTrue(result.marker_written)
        self.assertGreaterEqual(result.database_files_removed, 1)
        self.assertEqual(result.media_files_removed, 1)
        self.assertFalse(media_file.exists())
        self.assertTrue(reset_marker_path(self.paths).is_file())

        after = SettingsStore(self.paths.settings).settings
        self.assertTrue(after.media_autodownload_enabled)
        self.assertFalse(after.confirm_media_cache_clear)

        clean = connect_database(self.paths.database)
        self.assertEqual(clean.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        clean.close()

        boundary = load_capture_not_before_ns(self.paths)
        self.assertIsNotNone(boundary)
        connection = connect_database(self.paths.database)
        guarded = ImportService(connection, capture_not_before_ns=boundary)
        skipped = guarded.import_all(self.paths.dds_data)
        self.assertEqual(skipped.imported, 0)
        self.assertEqual(skipped.skipped_before_boundary, 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)

        changed = sample_capture()
        changed["captureRevision"] = 99
        self.capture.write_text(json.dumps(changed), encoding="utf-8")
        os.utime(self.capture, ns=(boundary + 1_000_000, boundary + 1_000_000))
        refreshed = guarded.import_file(self.capture)
        self.assertEqual(refreshed.imported, 1)
        self.assertEqual(connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)
        connection.close()

    def test_cache_clear_never_deletes_archive_database(self):
        connection = connect_database(self.paths.database)
        ImportService(connection).import_file(self.capture)
        connection.close()
        db_size_before = self.paths.database.stat().st_size

        media_file = self.paths.media / "objects" / "bb" / "cached.bin"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"123456")
        result = MediaCacheService(self.paths.media, self.paths.database).clear()

        self.assertEqual(result.files_removed, 1)
        self.assertTrue(self.paths.database.is_file())
        self.assertGreaterEqual(self.paths.database.stat().st_size, db_size_before)
        check = connect_database(self.paths.database)
        self.assertEqual(check.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)
        check.close()


class UiPolish061Tests(unittest.TestCase):
    def test_version_and_semantic_storage_delta(self):
        self.assertEqual(__version__, "0.6.1")
        self.assertEqual(human_storage_delta(-(496 * 1024**2)), "Освобождено за сессию: 496.00 MB")
        self.assertEqual(human_storage_delta(24 * 1024**2), "Добавлено за сессию: 24.00 MB")
        self.assertEqual(human_storage_delta(0), "Без изменений за сессию")

    def test_window_reset_stops_runtime_before_deleting_archive(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "dds_companion" / "gui" / "window.py").read_text(encoding="utf-8")
        method = source[source.index("def _reset_local_archive"):source.index("def _clear_media_cache")]
        self.assertLess(method.index("runtime.stop()"), method.index("thread.join(timeout=10.0)"))
        self.assertLess(method.index("thread.join(timeout=10.0)"), method.index("reset_local_archive(self.paths)"))
        self.assertIn("Сбросить локальный архив", (root / "dds_companion" / "gui" / "pages.py").read_text(encoding="utf-8"))

    def test_product_ui_does_not_use_companion_as_sidebar_brand(self):
        root = Path(__file__).resolve().parents[2]
        window = (root / "dds_companion" / "gui" / "window.py").read_text(encoding="utf-8")
        brand = window[window.index("brand_text = QVBoxLayout()"):window.index("side.addLayout(brand)")]
        self.assertNotIn('QLabel("Companion")', brand)
        self.assertIn('Discord Data Snatcher · v', brand)
        app = (root / "dds_companion" / "gui" / "app.py").read_text(encoding="utf-8")
        self.assertIn("app.setApplicationDisplayName(APPLICATION_NAME)", app)


if __name__ == "__main__":
    unittest.main()
