from __future__ import annotations

import json
import tempfile
import unittest
from unittest import mock
import zipfile
from pathlib import Path
from unittest.mock import patch

from dds_companion import __version__
from dds_companion.core.settings import SettingsStore
from dds_companion.services.branch_maintenance_service import BranchMaintenanceService
from dds_companion.services.export_package_service import ExportPackageService
from dds_companion.services.import_service import ImportService
from dds_companion.services.library_service import LibraryService
from dds_companion.storage.database import connect_database
from dds_companion.tests.test_imports import sample_capture


class Export062Tests(unittest.TestCase):
    THREAD_ID = "333333333333333333"
    CHANNEL_ID = "222222222222222222"

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.db = self.root / "dds.sqlite3"
        self.media = self.root / "media"
        self.media.mkdir()
        self.conn = connect_database(self.db)
        self.importer = ImportService(self.conn)

    def tearDown(self):
        self.conn.close()
        self.tmp.cleanup()

    def _import(self, *, thread: bool, message_id: str, attachment_id: str, content: str = "hello"):
        payload = sample_capture(thread=thread, content=content)
        payload["messages"][0]["id"] = message_id
        payload["messages"][0]["attachments"][0]["id"] = attachment_id
        payload["oldestMessageId"] = message_id
        payload["newestMessageId"] = message_id
        path = self.root / ("thread.json" if thread else "channel.json")
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.importer.import_file(path)
        return payload

    def _cache_attachment(self, attachment_id: str, *, data: bytes = b"image-bytes") -> Path:
        row = self.conn.execute(
            "SELECT media_key FROM media_objects WHERE attachment_id=?", (attachment_id,)
        ).fetchone()
        self.assertIsNotNone(row)
        path = self.media / "objects" / f"{attachment_id}.png"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        self.conn.execute(
            """
            UPDATE media_objects
            SET state='CACHED', local_relpath=?, local_size=?, sha256='test-sha',
                cached_at='2026-09-21T00:00:00+00:00'
            WHERE media_key=?
            """,
            (path.relative_to(self.media).as_posix(), len(data), row["media_key"]),
        )
        self.conn.commit()
        return path

    def test_text_only_package_has_no_media_bytes_and_does_not_change_export_rule(self):
        self._import(thread=True, message_id="444444444444444401", attachment_id="666666666666666601")
        LibraryService(self.conn).set_export_rule("thread", self.THREAD_ID, "EXCLUDE")
        result = ExportPackageService(self.conn, self.media).package(
            "thread", self.THREAD_ID, mode="TEXT_ONLY",
            output_dir=self.root / "exports", app_version=__version__,
        )
        with zipfile.ZipFile(result.output_path) as archive:
            names = set(archive.namelist())
            self.assertIn("content.md", names)
            self.assertIn("manifest.json", names)
            self.assertFalse(any(name.startswith("media/") for name in names))
            manifest = json.loads(archive.read("manifest.json"))
            self.assertTrue(manifest["complete"])
            self.assertEqual(manifest["counts"]["media_included"], 0)
        rule = self.conn.execute(
            "SELECT mode FROM archive_export_rules WHERE scope_kind='thread' AND scope_id=?",
            (self.THREAD_ID,),
        ).fetchone()
        self.assertEqual(rule[0], "EXCLUDE")

    def test_text_and_cache_package_contains_cached_media_and_relative_reference(self):
        self._import(thread=True, message_id="444444444444444402", attachment_id="666666666666666602", content="mechanic")
        self._cache_attachment("666666666666666602", data=b"PNGDATA")
        result = ExportPackageService(self.conn, self.media).package(
            "thread", self.THREAD_ID, mode="TEXT_AND_CACHE",
            output_dir=self.root / "exports", app_version=__version__,
        )
        self.assertTrue(result.complete)
        self.assertEqual(result.media_included, 1)
        with zipfile.ZipFile(result.output_path) as archive:
            names = archive.namelist()
            media_names = [name for name in names if name.startswith("media/")]
            self.assertEqual(len(media_names), 1)
            markdown = archive.read("content.md").decode("utf-8")
            self.assertIn("mechanic", markdown)
            self.assertIn(f"]({media_names[0]})", markdown)
            media_index = json.loads(archive.read("media_index.json"))
            self.assertEqual(media_index[0]["package_state"], "included")
            self.assertEqual(media_index[0]["package_relpath"], media_names[0])

    def test_text_and_cache_declares_missing_media_instead_of_hiding_it(self):
        self._import(thread=True, message_id="444444444444444403", attachment_id="666666666666666603")
        result = ExportPackageService(self.conn, self.media).package(
            "thread", self.THREAD_ID, mode="TEXT_AND_CACHE",
            output_dir=self.root / "exports", app_version=__version__,
        )
        self.assertFalse(result.complete)
        self.assertEqual(result.media_total, 1)
        self.assertEqual(result.media_missing, 1)
        with zipfile.ZipFile(result.output_path) as archive:
            manifest = json.loads(archive.read("manifest.json"))
            index = json.loads(archive.read("media_index.json"))
            self.assertFalse(manifest["complete"])
            self.assertEqual(index[0]["package_state"], "not_cached")

    def test_duplicate_original_filenames_cannot_collide_in_media_directory(self):
        payload = sample_capture(thread=True, content="two files")
        payload["messages"][0]["id"] = "444444444444444409"
        first = dict(payload["messages"][0]["attachments"][0])
        first["id"] = "666666666666666609"
        first["filename"] = "same.png"
        second = dict(first)
        second["id"] = "666666666666666610"
        payload["messages"][0]["attachments"] = [first, second]
        payload["oldestMessageId"] = payload["newestMessageId"] = payload["messages"][0]["id"]
        path = self.root / "dupes.json"
        path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        self.importer.import_file(path)
        self._cache_attachment(first["id"], data=b"one")
        self._cache_attachment(second["id"], data=b"two")
        result = ExportPackageService(self.conn, self.media).package(
            "thread", self.THREAD_ID, mode="TEXT_AND_CACHE",
            output_dir=self.root / "exports", app_version=__version__,
        )
        with zipfile.ZipFile(result.output_path) as archive:
            media_names = [name for name in archive.namelist() if name.startswith("media/")]
            self.assertEqual(len(media_names), 2)
            self.assertEqual(len(set(media_names)), 2)

    def test_failed_package_leaves_no_false_success_zip(self):
        self._import(
            thread=True, message_id="444444444444444411",
            attachment_id="666666666666666611",
        )
        out = self.root / "exports"
        with patch(
            "dds_companion.services.export_package_service._json_dump",
            side_effect=RuntimeError("forced write failure"),
        ):
            with self.assertRaises(RuntimeError):
                ExportPackageService(self.conn, self.media).package(
                    "thread", self.THREAD_ID, mode="TEXT_ONLY",
                    output_dir=out, app_version=__version__,
                )
        self.assertFalse(list(out.glob("*.zip")))
        self.assertFalse(list(out.glob("*.tmp")))

    def test_branch_cache_clear_keeps_archive_structure_and_rule(self):
        self._import(thread=True, message_id="444444444444444404", attachment_id="666666666666666604")
        cached = self._cache_attachment("666666666666666604")
        LibraryService(self.conn).set_export_rule("thread", self.THREAD_ID, "INCLUDE")
        result = BranchMaintenanceService(self.conn, self.media).clear_media_cache(
            "thread", self.THREAD_ID
        )
        self.assertEqual(result.media_files_removed, 1)
        self.assertFalse(cached.exists())
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0], 1)
        self.assertEqual(
            self.conn.execute(
                "SELECT mode FROM archive_export_rules WHERE scope_kind='thread' AND scope_id=?",
                (self.THREAD_ID,),
            ).fetchone()[0],
            "INCLUDE",
        )
        state = self.conn.execute("SELECT state, failure_class FROM media_objects").fetchone()
        self.assertEqual(tuple(state), ("EVICTED", "evicted_manual_clear"))

    def test_delete_data_keeps_structural_node_and_export_rule(self):
        self._import(thread=True, message_id="444444444444444405", attachment_id="666666666666666605")
        self._cache_attachment("666666666666666605")
        LibraryService(self.conn).set_export_rule("thread", self.THREAD_ID, "INCLUDE")
        result = BranchMaintenanceService(self.conn, self.media).delete_data("thread", self.THREAD_ID)
        self.assertEqual(result.messages_removed, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM threads WHERE id=?", (self.THREAD_ID,)).fetchone()[0], 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM media_objects").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM archive_export_rules").fetchone()[0], 1)

    def test_full_delete_thread_removes_node_content_cache_and_rule(self):
        self._import(thread=True, message_id="444444444444444406", attachment_id="666666666666666606")
        cached = self._cache_attachment("666666666666666606")
        LibraryService(self.conn).set_export_rule("thread", self.THREAD_ID, "INCLUDE")
        result = BranchMaintenanceService(self.conn, self.media).delete_branch("thread", self.THREAD_ID)
        self.assertEqual(result.structural_nodes_removed, 1)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM threads WHERE id=?", (self.THREAD_ID,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM archive_export_rules").fetchone()[0], 0)
        self.assertFalse(cached.exists())

    def test_full_delete_channel_removes_child_thread_and_its_rule(self):
        self._import(thread=True, message_id="444444444444444407", attachment_id="666666666666666607")
        self._import(thread=False, message_id="444444444444444408", attachment_id="666666666666666608")
        lib = LibraryService(self.conn)
        lib.set_export_rule("channel", self.CHANNEL_ID, "INCLUDE")
        lib.set_export_rule("thread", self.THREAD_ID, "EXCLUDE")
        result = BranchMaintenanceService(self.conn, self.media).delete_branch("channel", self.CHANNEL_ID)
        self.assertGreaterEqual(result.structural_nodes_removed, 2)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM channels WHERE id=?", (self.CHANNEL_ID,)).fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM threads").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM messages").fetchone()[0], 0)
        self.assertEqual(self.conn.execute("SELECT COUNT(*) FROM archive_export_rules").fetchone()[0], 0)


class ExportSettings062Tests(unittest.TestCase):
    def test_manual_export_path_persists(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "settings.json"
            store = SettingsStore(path)
            chosen = str(Path(td) / "my exports")
            store.update(manual_export_path=chosen)
            self.assertEqual(SettingsStore(path).settings.manual_export_path, chosen)

    def test_manual_export_path_rejects_non_string(self):
        with tempfile.TemporaryDirectory() as td:
            store = SettingsStore(Path(td) / "settings.json")
            with self.assertRaises(ValueError):
                store.update(manual_export_path=123)


class ExportDefaultPath062Tests(unittest.TestCase):
    def test_installed_default_uses_redirected_windows_documents_known_folder(self):
        from dds_companion.core import paths as paths_module

        runtime = paths_module.build_runtime_paths(app_data=Path("/tmp/dds-test"))
        runtime = paths_module.RuntimePaths(
            **{**runtime.__dict__, "deployment_profile": "installed"}
        )
        redirected = Path("D:/Redirected Documents")
        with mock.patch.object(paths_module.sys, "platform", "win32"), mock.patch.object(
            paths_module, "_windows_documents_path", return_value=redirected
        ):
            self.assertEqual(
                paths_module.default_manual_export_path(runtime),
                redirected / "DDS Exports",
            )

    def test_portable_default_stays_inside_portable_data_root(self):
        from dds_companion.core import paths as paths_module

        runtime = paths_module.build_runtime_paths(
            app_data=Path("/tmp/dds-portable"),
        )
        runtime = paths_module.RuntimePaths(
            **{**runtime.__dict__, "deployment_profile": "portable"}
        )
        self.assertEqual(
            paths_module.default_manual_export_path(runtime),
            runtime.app_data / "exports",
        )


class UiContracts062Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]

    def test_window_title_and_brand_contract(self):
        source = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        self.assertIn("self.setWindowTitle(APPLICATION_DISPLAY_NAME)", source)
        self.assertNotIn('setWindowTitle(f"{APPLICATION_DISPLAY_NAME} · v', source)
        self.assertIn('subtitle = QLabel("Discord\\nData\\nSnatcher")', source)
        self.assertIn("title.setAlignment(Qt.AlignHCenter", source)

    def test_library_context_menu_exposes_manual_package_and_branch_actions(self):
        source = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        self.assertIn('package = menu.addMenu("Упаковать")', source)
        self.assertIn('package.addAction("Только текст")', source)
        self.assertIn('package.addAction("Текст + кэш")', source)
        self.assertIn('menu.addAction("Очистить медиакэш этой ветки")', source)
        self.assertIn('menu.addAction("Удалить данные ветки")', source)
        self.assertIn('menu.addAction("Полностью удалить ветку")', source)


if __name__ == "__main__":
    unittest.main()
