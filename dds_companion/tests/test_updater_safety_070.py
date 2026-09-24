from __future__ import annotations

import hashlib
import shutil
import tempfile
import unittest
import uuid
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from dds_companion.core.paths import build_runtime_paths
from dds_companion.core.settings import SettingsStore
from dds_companion.gui.pages import SettingsPage
from dds_companion.updater.client import UpdateCheckResult
from dds_companion.updater.controller import UpdateController
from dds_companion.updater.event_log import UpdateLog
from dds_companion.updater.journal import JournalStore
from dds_companion.updater.external import install_candidate
import dds_companion.updater.external as updater_external
from dds_companion.updater.integrity import sha256_file
from dds_companion.updater.lock import UpdateFileLock, UpdateLockError
from dds_companion.updater.models import ReleaseManifest
from dds_companion.updater.paths import build_updater_paths
from dds_companion.updater.payload import create_install_manifest, write_install_manifest
from dds_companion.updater.pointer import CURRENT_POINTER, PENDING_UPDATE, PREVIOUS_POINTER, PendingUpdate, VersionPointer, read_json, read_pointer, write_pointer
from dds_companion.updater.release_source import ReleaseDescriptor
from dds_companion.updater.space import require_free_space
from dds_companion.updater.staging import PackageStager
from dds_companion import launcher as dds_launcher


class UpdaterSafety070Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def _seed_user_data(self, app_root: Path) -> dict[str, str]:
        records = {
            "Data/settings.json": b'{"theme":"dark","sentinel":"settings"}',
            "Data/archive.sqlite3": b"sqlite-sentinel-\x00\x01\x02",
            "DDS_Data/capture.json": b'{"messages":["user-data-sentinel"]}',
            "media/aa/cache.bin": bytes(range(64)),
            "exports/manual.zip": b"PK\x03\x04user-export-sentinel",
        }
        for rel, data in records.items():
            path = app_root / Path(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        return self._snapshot_files(app_root, records)

    @staticmethod
    def _snapshot_files(app_root: Path, records: dict[str, bytes]) -> dict[str, str]:
        return {
            rel: hashlib.sha256((app_root / Path(rel)).read_bytes()).hexdigest()
            for rel in records
        }

    def _make_payload(self, version: str = "0.7.0") -> Path:
        payload = self.root / f"payload-{uuid.uuid4().hex}"
        payload.mkdir()
        (payload / "DDSApp.exe").write_bytes(b"app-executable")
        internal = payload / "_internal"
        internal.mkdir()
        (internal / "runtime.bin").write_bytes(b"runtime")
        write_install_manifest(payload, create_install_manifest(payload, version))
        return payload

    def _make_package(self, version: str = "0.7.0") -> tuple[Path, ReleaseManifest]:
        payload = self._make_payload(version)
        package = self.root / f"DDS-{version}-{uuid.uuid4().hex}.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in payload.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(payload).as_posix())
        manifest = ReleaseManifest(
            version=version,
            channel="preview",
            asset=package.name,
            sha256=sha256_file(package),
            size_bytes=package.stat().st_size,
            updater_protocol=1,
            package_format=1,
        )
        return package, manifest

    def _make_install_fixture(self, target_version: str = "0.7.0"):
        app_root = self.root / f"DDS-{uuid.uuid4().hex}"
        current_dir = app_root / "versions" / "0.7.0.dev0"
        current_dir.mkdir(parents=True)
        (current_dir / "DDSApp.exe").write_bytes(b"old")
        write_install_manifest(
            current_dir,
            create_install_manifest(current_dir, "0.7.0.dev0"),
        )
        current = VersionPointer("0.7.0.dev0", "versions/0.7.0.dev0")
        write_pointer(app_root / CURRENT_POINTER, current)
        (app_root / "DDS.exe").write_bytes(b"launcher")
        staged = self._make_payload(target_version)
        return app_root, staged, current

    def test_file_lock_rejects_second_owner_and_releases_cleanly(self):
        lock_path = self.root / "update.lock"
        first = UpdateFileLock(lock_path)
        second = UpdateFileLock(lock_path)
        self.assertTrue(first.acquire())
        self.assertFalse(second.acquire())
        first.release()
        self.assertTrue(second.acquire())
        second.release()

    def test_updater_log_records_lifecycle_event(self):
        log_path = self.root / "logs" / "updater.log"
        UpdateLog(log_path).write("VERIFYING", "target=0.7.0")
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("[VERIFYING]", text)
        self.assertIn("target=0.7.0", text)

    def test_free_space_guard_fails_closed(self):
        target = self.root / "workspace"
        target.mkdir()
        with patch("dds_companion.updater.space.shutil.disk_usage", return_value=SimpleNamespace(free=5)):
            with self.assertRaises(OSError):
                require_free_space(target, 10, margin_bytes=0)
        with patch("dds_companion.updater.space.shutil.disk_usage", return_value=SimpleNamespace(free=20)):
            require_free_space(target, 10, margin_bytes=0)


    def test_failed_background_check_still_throttles_next_attempt_for_24h(self):
        runtime = build_runtime_paths(
            app_data=self.root / "DataRoot-check-throttle",
            app_dir=self.root / "Program-check-throttle",
        )
        paths = build_updater_paths(runtime)
        settings = SettingsStore(self.root / "settings-check-throttle.json")
        client = MagicMock()
        client.check.side_effect = OSError("offline")
        events: list[dict] = []
        controller = UpdateController(
            paths=paths,
            current_version="0.7.0.dev0",
            settings_getter=lambda: settings.settings,
            status_sink=events.append,
            client=client,
        )

        # _check_worker normally owns an already-acquired operation lock.
        controller._operation_lock.acquire()
        controller._check_worker(manual=False)

        client.check.assert_called_once()
        self.assertFalse(controller.check_state.due(interval_hours=24))
        self.assertEqual(events[-1]["state"], "ERROR")

    def test_controller_preflight_stops_download_when_space_is_low(self):
        package, manifest = self._make_package()
        runtime = build_runtime_paths(
            app_data=self.root / "DataRoot",
            app_dir=self.root / "Program",
        )
        paths = build_updater_paths(runtime)
        settings = SettingsStore(self.root / "settings.json")
        downloader = MagicMock()
        stager = MagicMock()
        controller = UpdateController(
            paths=paths,
            current_version="0.7.0.dev0",
            settings_getter=lambda: settings.settings,
            status_sink=lambda _payload: None,
            downloader=downloader,
            stager=stager,
        )
        descriptor = ReleaseDescriptor(
            version="0.7.0",
            prerelease=True,
            manifest_url="memory://manifest",
            release_url="memory://release",
            notes="",
            published_at=None,
            asset_urls={manifest.asset: "https://example.invalid/update.zip"},
        )
        result = UpdateCheckResult(
            True,
            "0.7.0.dev0",
            descriptor=descriptor,
            manifest=manifest,
        )
        with patch("dds_companion.updater.controller.require_free_space", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                controller._download_and_stage(result)
        downloader.download.assert_not_called()
        stager.stage.assert_not_called()

    def test_stager_checks_exact_uncompressed_space_before_extract(self):
        package, manifest = self._make_package()
        runtime = build_runtime_paths(
            app_data=self.root / "DataRoot",
            app_dir=self.root / "Program",
        )
        paths = build_updater_paths(runtime)
        with patch("dds_companion.updater.staging.require_free_space") as gate:
            _target, inventory = PackageStager(paths).stage(package, manifest)
        gate.assert_called_once_with(paths.staging, inventory.uncompressed_bytes)

    def test_external_installer_lock_blocks_duplicate_commit(self):
        app_root, staged, current = self._make_install_fixture()
        lock_path = self.root / "update.lock"
        owner = UpdateFileLock(lock_path)
        self.assertTrue(owner.acquire())
        self.addCleanup(owner.release)

        with self.assertRaises(UpdateLockError):
            install_candidate(
                application_dir=app_root,
                staged_dir=staged,
                target_version="0.7.0",
                parent_pid=0,
                ack_path=self.root / "ack.ok",
                resume_state=None,
                lock_path=lock_path,
                log_path=self.root / "updater.log",
            )
        self.assertEqual(read_pointer(app_root / CURRENT_POINTER), current)
        self.assertFalse((app_root / "versions" / "0.7.0").exists())

    def test_external_installer_low_space_keeps_current_version_intact(self):
        app_root, staged, current = self._make_install_fixture()
        with patch("dds_companion.updater.external.require_free_space", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                install_candidate(
                    application_dir=app_root,
                    staged_dir=staged,
                    target_version="0.7.0",
                    parent_pid=0,
                    ack_path=self.root / "ack.ok",
                    resume_state=None,
                    lock_path=self.root / "update.lock",
                    log_path=self.root / "updater.log",
                )
        self.assertEqual(read_pointer(app_root / CURRENT_POINTER), current)
        self.assertFalse((app_root / "versions" / "0.7.0").exists())
        log_text = (self.root / "updater.log").read_text(encoding="utf-8")
        self.assertIn("[INSTALL_FAILED]", log_text)

    def test_external_installer_logs_successful_promotion(self):
        app_root, staged, _current = self._make_install_fixture()
        log_path = self.root / "updater.log"
        with patch("dds_companion.updater.external.subprocess.Popen") as popen:
            install_candidate(
                application_dir=app_root,
                staged_dir=staged,
                target_version="0.7.0",
                parent_pid=0,
                ack_path=self.root / "ack.ok",
                resume_state=None,
                lock_path=self.root / "update.lock",
                log_path=log_path,
            )
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("[INSTALL_START]", text)
        self.assertIn("[PAYLOAD_VERIFIED]", text)
        self.assertIn("[SPACE_OK]", text)
        self.assertIn("[PROMOTED]", text)
        self.assertIn("[LAUNCHED_CANDIDATE]", text)
        popen.assert_called_once()

    def test_external_main_accepts_utf8_bom_launch_args(self):
        args_file = self.root / "args.json"
        args_file.write_bytes(
            b"\xef\xbb\xbf" + b'{"args":["--dds-data","C:/test"]}'
        )
        log_path = self.root / "bootstrap.log"
        argv = [
            "--application-dir", str(self.root / "app"),
            "--staged-dir", str(self.root / "stage"),
            "--target-version", "0.7.0",
            "--parent-pid", "0",
            "--ack-path", str(self.root / "ack.ok"),
            "--launch-args-file", str(args_file),
            "--log-path", str(log_path),
        ]
        with patch("dds_companion.updater.external.install_candidate") as install:
            result = updater_external.main(argv)
        self.assertEqual(result, 0)
        self.assertEqual(install.call_args.kwargs["launch_args"], ("--dds-data", "C:/test"))

    def test_external_main_logs_bootstrap_failure(self):
        args_file = self.root / "bad-args.json"
        args_file.write_text("{not-json", encoding="utf-8")
        log_path = self.root / "bootstrap.log"
        result = updater_external.main([
            "--application-dir", str(self.root / "app"),
            "--staged-dir", str(self.root / "stage"),
            "--target-version", "0.7.0",
            "--parent-pid", "0",
            "--ack-path", str(self.root / "ack.ok"),
            "--launch-args-file", str(args_file),
            "--log-path", str(log_path),
        ])
        self.assertEqual(result, 20)
        text = log_path.read_text(encoding="utf-8")
        self.assertIn("[UPDATER_FAILED]", text)
        self.assertIn("JSONDecodeError", text)

    def test_successful_update_preserves_user_data_byte_for_byte_and_commits_journal(self):
        app_root, staged, current = self._make_install_fixture()
        user_records = {
            "Data/settings.json": b'{"theme":"dark","sentinel":"settings"}',
            "Data/archive.sqlite3": b"sqlite-sentinel-\x00\x01\x02",
            "DDS_Data/capture.json": b'{"messages":["user-data-sentinel"]}',
            "media/aa/cache.bin": bytes(range(64)),
            "exports/manual.zip": b"PK\x03\x04user-export-sentinel",
        }
        for rel, data in user_records.items():
            path = app_root / Path(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        before = self._snapshot_files(app_root, user_records)

        journal_path = self.root / "journal-success.json"
        log_path = self.root / "updater-success.log"
        ack_path = self.root / "success.ok"

        # External updater completes the promotion transaction and leaves startup
        # verification to the stable launcher.
        with patch("dds_companion.updater.external.subprocess.Popen"):
            install_candidate(
                application_dir=app_root,
                staged_dir=staged,
                target_version="0.7.0",
                parent_pid=0,
                ack_path=ack_path,
                resume_state=None,
                lock_path=self.root / "success.lock",
                log_path=log_path,
                journal_path=journal_path,
            )

        pending = PendingUpdate.from_dict(read_json(app_root / PENDING_UPDATE))
        self.assertEqual(JournalStore(journal_path).load().state.value, "VERIFYING_STARTUP")

        class AckProcess:
            def poll(self):
                ack_path.write_text("ok", encoding="utf-8")
                return None

        with patch("dds_companion.launcher._spawn", return_value=AckProcess()):
            result = dds_launcher._launch_pending(app_root, pending, [])

        self.assertEqual(result, 0)
        self.assertEqual(read_pointer(app_root / CURRENT_POINTER).version, "0.7.0")
        self.assertEqual(read_pointer(app_root / PREVIOUS_POINTER), current)
        self.assertEqual(JournalStore(journal_path).load().state.value, "COMPLETE")
        self.assertIn("[STARTUP_CONFIRMED]", log_path.read_text(encoding="utf-8"))
        self.assertEqual(self._snapshot_files(app_root, user_records), before)

    def test_failed_update_rolls_back_and_preserves_user_data_byte_for_byte(self):
        app_root, staged, current = self._make_install_fixture()
        older_dir = app_root / "versions" / "0.6.9"
        older_dir.mkdir(parents=True)
        (older_dir / "DDSApp.exe").write_bytes(b"older")
        older = VersionPointer("0.6.9", "versions/0.6.9")
        write_pointer(app_root / PREVIOUS_POINTER, older)

        user_records = {
            "Data/settings.json": b'{"sentinel":"settings-failure"}',
            "Data/archive.sqlite3": b"archive-must-not-change",
            "DDS_Data/capture.json": b'{"sentinel":"capture-failure"}',
            "media/aa/cache.bin": b"media-cache-must-not-change",
            "exports/manual.zip": b"export-must-not-change",
        }
        for rel, data in user_records.items():
            path = app_root / Path(rel)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        before = self._snapshot_files(app_root, user_records)

        journal_path = self.root / "journal-failure.json"
        log_path = self.root / "updater-failure.log"
        ack_path = self.root / "never.ok"

        with patch("dds_companion.updater.external.subprocess.Popen"):
            install_candidate(
                application_dir=app_root,
                staged_dir=staged,
                target_version="0.7.0",
                parent_pid=0,
                ack_path=ack_path,
                resume_state=None,
                lock_path=self.root / "failure.lock",
                log_path=log_path,
                journal_path=journal_path,
            )

        pending = PendingUpdate.from_dict(read_json(app_root / PENDING_UPDATE))
        failed = MagicMock()
        failed.poll.return_value = 1
        fallback = MagicMock()
        with patch("dds_companion.launcher._spawn", side_effect=[failed, fallback]):
            result = dds_launcher._launch_pending(app_root, pending, [])

        self.assertEqual(result, 10)
        self.assertEqual(read_pointer(app_root / CURRENT_POINTER), current)
        self.assertEqual(read_pointer(app_root / PREVIOUS_POINTER), older)
        self.assertTrue((app_root / "versions" / "0.6.9").is_dir())
        self.assertTrue((app_root / "versions" / current.version).is_dir())
        self.assertFalse((app_root / "versions" / "0.7.0").exists())
        self.assertEqual(JournalStore(journal_path).load().state.value, "FAILED")
        log_text = log_path.read_text(encoding="utf-8")
        self.assertIn("[ROLLBACK_START]", log_text)
        self.assertIn("[ROLLBACK_COMPLETE]", log_text)
        self.assertEqual(self._snapshot_files(app_root, user_records), before)


    def test_release_notes_formatter_normalizes_and_bounds_text(self):
        notes = "  First line\r\nSecond line\r\n" + ("x" * 2000)
        formatted = SettingsPage._format_release_notes(notes, limit=120)
        self.assertTrue(formatted.startswith("First line\nSecond line\n"))
        self.assertLessEqual(len(formatted), 120)
        self.assertTrue(formatted.endswith("…"))



if __name__ == "__main__":
    unittest.main()
