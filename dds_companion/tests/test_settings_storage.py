from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from dds_companion.core.settings import CompanionSettings, DEFAULT_SETTINGS, SettingsStore
from dds_companion.services.media_cache_service import MediaCacheService


class SettingsStoreTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.path = self.root / "config" / "settings.json"

    def tearDown(self):
        self.tmp.cleanup()

    def test_defaults_load_without_creating_fake_state(self):
        store = SettingsStore(self.path)
        self.assertEqual(store.settings, DEFAULT_SETTINGS)
        self.assertFalse(self.path.exists())

    def test_update_persists_atomically_and_reloads(self):
        store = SettingsStore(self.path)
        store.update(media_cache_limit_bytes=2 * 1024**3, media_retention_days=7)
        self.assertTrue(self.path.exists())
        self.assertFalse(any(self.path.parent.glob("*.tmp")))
        reloaded = SettingsStore(self.path)
        self.assertEqual(reloaded.settings.media_cache_limit_bytes, 2 * 1024**3)
        self.assertEqual(reloaded.settings.media_retention_days, 7)

    def test_media_autodownload_toggle_persists(self):
        store = SettingsStore(self.path)
        store.update(media_autodownload_enabled=True)
        self.assertTrue(SettingsStore(self.path).settings.media_autodownload_enabled)

    def test_corrupt_json_falls_back_to_defaults(self):
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{bad json", encoding="utf-8")
        store = SettingsStore(self.path)
        self.assertEqual(store.settings, DEFAULT_SETTINGS)
        self.assertIsNotNone(store.last_load_error)

    def test_invalid_setting_is_rejected_without_overwriting_file(self):
        store = SettingsStore(self.path)
        store.update(media_retention_days=30)
        before = self.path.read_text(encoding="utf-8")
        with self.assertRaises(ValueError):
            store.update(media_retention_days=0)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)


class MediaCacheServiceTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.media = self.root / "media"
        self.media.mkdir()
        self.service = MediaCacheService(self.media)
        self.store = SettingsStore(self.root / "config" / "settings.json")

    def tearDown(self):
        self.tmp.cleanup()

    def _file(self, name: str, size: int, *, age_days: int = 0) -> Path:
        path = self.media / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"x" * size)
        stamp = time.time() - age_days * 86400
        os.utime(path, (stamp, stamp))
        return path

    def test_clear_removes_only_media_tree_files(self):
        self._file("a.bin", 10)
        outside = self.root / "database.sqlite3"
        outside.write_text("archive", encoding="utf-8")
        result = self.service.clear()
        self.assertEqual(result.files_removed, 1)
        self.assertTrue(outside.exists())
        self.assertFalse((self.media / "a.bin").exists())

    def test_enforce_removes_oversized_and_expired_files(self):
        self._file("oversized.bin", 200)
        self._file("expired.bin", 20, age_days=10)
        self._file("keep.bin", 20)
        settings = CompanionSettings(
            media_cache_limit_bytes=1000,
            media_max_file_bytes=100,
            media_retention_days=3,
        )
        result = self.service.enforce(settings)
        self.assertEqual(result.oversized_removed, 1)
        self.assertEqual(result.expired_removed, 1)
        self.assertTrue((self.media / "keep.bin").exists())

    def test_enforce_size_limit_evicts_oldest_first(self):
        oldest = self._file("old.bin", 60, age_days=2)
        newest = self._file("new.bin", 60, age_days=0)
        settings = CompanionSettings(
            media_cache_limit_bytes=100,
            media_max_file_bytes=None,
            media_retention_days=None,
        )
        result = self.service.enforce(settings)
        self.assertEqual(result.limit_evicted, 1)
        self.assertFalse(oldest.exists())
        self.assertTrue(newest.exists())

    def test_unlimited_policy_keeps_files(self):
        path = self._file("keep.bin", 32, age_days=500)
        settings = self.store.update(
            media_cache_limit_bytes=None,
            media_max_file_bytes=None,
            media_retention_days=None,
        )
        result = self.service.enforce(settings)
        self.assertEqual(result.files_removed, 0)
        self.assertTrue(path.exists())


if __name__ == "__main__":
    unittest.main()
