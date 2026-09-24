from __future__ import annotations

import io
import json
import os
import stat
import tempfile
import unittest
import urllib.error
import uuid
from unittest.mock import MagicMock, patch
import zipfile
from pathlib import Path

from dds_companion.core.paths import build_runtime_paths
from dds_companion.core.settings import SettingsStore
from dds_companion.updater.cancel import UpdateCancelled
from dds_companion.updater.check_state import CheckStateStore
from dds_companion.updater.client import UpdateClient
from dds_companion.updater.downloader import DownloadError, PackageDownloader
from dds_companion.updater.integrity import (
    PackageValidationError,
    sha256_file,
    validate_update_zip,
)
from dds_companion.updater.journal import JournalStore, UpdateStateMachine
from dds_companion.updater.models import ReleaseManifest, UpdateState
from dds_companion.updater.paths import build_updater_paths
from dds_companion.updater.payload import InstallManifest, create_install_manifest, write_install_manifest
from dds_companion.updater.pointer import (
    CURRENT_POINTER,
    PENDING_UPDATE,
    PREVIOUS_POINTER,
    PendingUpdate,
    VersionPointer,
    read_json,
    read_pointer,
    write_pending,
    write_pointer,
)
from dds_companion.updater.release_source import GitHubReleaseSource

def canonical_path(path: Path) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(path)))


from dds_companion.updater.versioning import is_newer
from dds_companion.updater.staging import PackageStager, StageError
from dds_companion.updater.external import install_candidate
from dds_companion import launcher as dds_launcher


class UpdaterFoundationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def make_zip(self, entries: dict[str, bytes], name: str = "DDS-update.zip") -> Path:
        path = self.root / name
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
            for entry, data in entries.items():
                archive.writestr(entry, data)
        return path

    def make_update_package(self, version: str = "0.7.0") -> Path:
        payload = self.root / f"payload-{uuid.uuid4().hex}"
        payload.mkdir()
        (payload / "DDSApp.exe").write_bytes(b"app-executable")
        internal = payload / "_internal"
        internal.mkdir()
        (internal / "runtime.bin").write_bytes(b"runtime")
        write_install_manifest(payload, create_install_manifest(payload, version))
        package = self.root / f"DDS-{version}-{uuid.uuid4().hex}.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in payload.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(payload).as_posix())
        return package

    def manifest_for(self, package: Path, **changes) -> ReleaseManifest:
        values = {
            "version": "0.7.0",
            "channel": "preview",
            "asset": package.name,
            "sha256": sha256_file(package),
            "size_bytes": package.stat().st_size,
            "updater_protocol": 1,
            "package_format": 1,
        }
        values.update(changes)
        return ReleaseManifest(**values)

    def test_manifest_accepts_supported_contract(self):
        package = self.make_zip({"DDS.exe": b"exe"})
        manifest = self.manifest_for(package)
        manifest.validate()
        self.assertEqual(manifest.channel, "preview")

    def test_manifest_rejects_asset_paths_and_bad_hash(self):
        package = self.make_zip({"DDS.exe": b"exe"})
        with self.assertRaises(ValueError):
            self.manifest_for(package, asset="../DDS.zip").validate()
        with self.assertRaises(ValueError):
            self.manifest_for(package, sha256="bad").validate()

    def test_zip_validator_accepts_current_onedir_shape(self):
        package = self.make_zip({
            "DDS.exe": b"exe",
            "_internal/python311.dll": b"dll",
            "_internal/PySide6/Qt6Core.dll": b"qt",
        })
        inventory = validate_update_zip(package)
        self.assertIn("DDS.exe", inventory.entries)
        self.assertGreater(inventory.uncompressed_bytes, 0)

    def test_zip_validator_rejects_traversal(self):
        package = self.make_zip({"DDS.exe": b"exe", "../escape.txt": b"x"})
        with self.assertRaises(PackageValidationError):
            validate_update_zip(package)

    def test_zip_validator_rejects_protected_data_roots(self):
        for protected in ("Data/settings.json", "database/dds.sqlite3", "DDS_Data/capture.json"):
            package = self.make_zip({"DDS.exe": b"exe", protected: b"x"}, name=f"{uuid.uuid4().hex}.zip")
            with self.assertRaises(PackageValidationError):
                validate_update_zip(package)

    def test_zip_validator_rejects_casefold_duplicates(self):
        package = self.make_zip({"DDS.exe": b"one", "dds.EXE": b"two"})
        with self.assertRaises(PackageValidationError):
            validate_update_zip(package)

    def test_zip_validator_rejects_symlink(self):
        package = self.root / "symlink.zip"
        with zipfile.ZipFile(package, "w") as archive:
            archive.writestr("DDS.exe", b"exe")
            info = zipfile.ZipInfo("link")
            info.create_system = 3
            info.external_attr = (stat.S_IFLNK | 0o777) << 16
            archive.writestr(info, "DDS.exe")
        with self.assertRaises(PackageValidationError):
            validate_update_zip(package)

    def test_zip_validator_requires_dds_exe_at_root(self):
        package = self.make_zip({"bin/DDS.exe": b"exe"})
        with self.assertRaises(PackageValidationError):
            validate_update_zip(package)

    def test_portable_workspace_is_outside_application_directory(self):
        app_dir = self.root / "DDS"
        paths = build_runtime_paths(portable=True, app_dir=app_dir)
        updater = build_updater_paths(paths)
        self.assertEqual(canonical_path(updater.workspace.parent), canonical_path(app_dir.parent))
        self.assertNotEqual(updater.workspace, paths.app_data)
        self.assertFalse(str(updater.workspace).startswith(str(paths.app_data)))

    def test_installed_or_custom_workspace_lives_under_data_root(self):
        app_data = self.root / "AppData"
        paths = build_runtime_paths(app_data=app_data, app_dir=self.root / "Program")
        updater = build_updater_paths(paths)
        self.assertEqual(canonical_path(updater.workspace), canonical_path(app_data / "update"))

    def test_state_machine_persists_valid_transition(self):
        store = JournalStore(self.root / "journal.json")
        machine = UpdateStateMachine(store, current_version="0.7.0.dev0")
        entry = machine.transition(
            UpdateState.IDLE,
            UpdateState.VERIFYING,
            target_version="0.7.0",
            detail="manual package",
        )
        loaded = store.load()
        self.assertEqual(entry.state, UpdateState.VERIFYING)
        self.assertEqual(loaded, entry)

    def test_state_machine_rejects_invalid_transition(self):
        store = JournalStore(self.root / "journal.json")
        machine = UpdateStateMachine(store, current_version="0.7.0.dev0")
        with self.assertRaises(ValueError):
            machine.transition(UpdateState.IDLE, UpdateState.PROMOTING, target_version="0.7.0")

    def test_stager_verifies_and_extracts_package(self):
        package = self.make_update_package()
        paths = build_runtime_paths(app_data=self.root / "DataRoot", app_dir=self.root / "Program")
        updater_paths = build_updater_paths(paths)
        target, inventory = PackageStager(updater_paths).stage(package, self.manifest_for(package))
        self.assertTrue((target / "DDSApp.exe").is_file())
        self.assertIn("_internal/runtime.bin", inventory.entries)

    def test_stager_rejects_wrong_hash_without_creating_target(self):
        package = self.make_update_package()
        paths = build_runtime_paths(app_data=self.root / "DataRoot", app_dir=self.root / "Program")
        updater_paths = build_updater_paths(paths)
        manifest = self.manifest_for(package, sha256="0" * 64)
        with self.assertRaises(StageError):
            PackageStager(updater_paths).stage(package, manifest)
        self.assertFalse((updater_paths.staging / manifest.version).exists())

    def test_stager_rejects_unsupported_protocol(self):
        package = self.make_update_package()
        paths = build_runtime_paths(app_data=self.root / "DataRoot", app_dir=self.root / "Program")
        updater_paths = build_updater_paths(paths)
        with self.assertRaises(StageError):
            PackageStager(updater_paths).stage(package, self.manifest_for(package, updater_protocol=2))


    def test_version_comparison_treats_final_as_newer_than_same_dev_line(self):
        self.assertTrue(is_newer("0.7.0", "0.7.0.dev0"))
        self.assertTrue(is_newer("0.7.1", "0.7.0"))
        self.assertFalse(is_newer("0.6.2", "0.7.0.dev0"))

    def test_release_source_uses_release_asset_not_source_archive(self):
        release_payload = [{
            "tag_name": "v0.7.0",
            "draft": False,
            "prerelease": True,
            "html_url": "https://example.invalid/release",
            "body": "notes",
            "published_at": "2026-09-24T00:00:00Z",
            "assets": [
                {
                    "name": "DDS-0.7.0-update.json",
                    "browser_download_url": "https://example.invalid/update.json",
                },
                {
                    "name": "DDS-0.7.0-windows-x64.zip",
                    "browser_download_url": "https://example.invalid/dds.zip",
                },
            ],
        }]
        package = self.make_zip({"DDS.exe": b"exe"})
        manifest = self.manifest_for(package, version="0.7.0")
        responses = [
            json.dumps(release_payload).encode("utf-8"),
            json.dumps(manifest.to_dict()).encode("utf-8"),
        ]

        def opener(_request, timeout):
            self.assertGreaterEqual(timeout, 1)
            return io.BytesIO(responses.pop(0))

        source = GitHubReleaseSource(opener=opener)
        descriptor = source.latest(channel="preview")
        self.assertEqual(descriptor.manifest_url, "https://example.invalid/update.json")
        loaded = source.manifest(descriptor)
        self.assertEqual(loaded.version, "0.7.0")

    def test_stable_channel_skips_preview_release(self):
        payload = [{
            "tag_name": "v0.7.0",
            "draft": False,
            "prerelease": True,
            "assets": [{
                "name": "DDS-0.7.0-update.json",
                "browser_download_url": "https://example.invalid/update.json",
            }],
        }]
        source = GitHubReleaseSource(
            opener=lambda _request, timeout: io.BytesIO(json.dumps(payload).encode("utf-8"))
        )
        self.assertIsNone(source.latest(channel="stable"))

    def test_update_client_returns_newer_release_only(self):
        package = self.make_zip({"DDS.exe": b"exe"})
        manifest = self.manifest_for(package, version="0.7.0")

        class Source:
            def latest(self, channel="preview"):
                from dds_companion.updater.release_source import ReleaseDescriptor
                return ReleaseDescriptor(
                    version="0.7.0",
                    prerelease=True,
                    manifest_url="memory://manifest",
                    release_url="memory://release",
                    notes="notes",
                    published_at=None,
                    asset_urls={manifest.asset: "https://example.invalid/dds.zip"},
                )

            def manifest(self, _descriptor):
                return manifest

        client = UpdateClient(Source())
        self.assertTrue(client.check("0.7.0.dev0").update_available)
        self.assertFalse(client.check("0.8.0").update_available)

    def test_check_state_enforces_daily_interval(self):
        from datetime import datetime, timedelta, timezone

        store = CheckStateStore(self.root / "check.json")
        now = datetime(2026, 9, 24, 12, 0, tzinfo=timezone.utc)
        self.assertTrue(store.due(now=now))
        store.mark_checked(now=now)
        self.assertFalse(store.due(now=now + timedelta(hours=23, minutes=59)))
        self.assertTrue(store.due(now=now + timedelta(hours=24)))

    def test_downloader_atomically_verifies_package(self):
        package = self.make_zip({"DDS.exe": b"payload"})
        data = package.read_bytes()
        manifest = self.manifest_for(package)
        target = self.root / "downloads" / manifest.asset
        downloader = PackageDownloader(opener=lambda _request, timeout: io.BytesIO(data))
        result = downloader.download("https://example.invalid/dds.zip", target, manifest)
        self.assertEqual(result.read_bytes(), data)
        self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_downloader_rejects_truncated_package_and_cleans_partial(self):
        package = self.make_zip({"DDS.exe": b"payload"})
        data = package.read_bytes()
        manifest = self.manifest_for(package)
        target = self.root / "downloads" / manifest.asset
        downloader = PackageDownloader(opener=lambda _request, timeout: io.BytesIO(data[:-3]))
        with self.assertRaises(DownloadError):
            downloader.download("https://example.invalid/dds.zip", target, manifest)
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_downloader_retries_one_transient_failure_then_succeeds(self):
        package = self.make_zip({"DDS.exe": b"payload"})
        data = package.read_bytes()
        manifest = self.manifest_for(package)
        target = self.root / "downloads-retry" / manifest.asset
        calls = []

        def opener(_request, timeout):
            calls.append(timeout)
            if len(calls) == 1:
                raise urllib.error.URLError("temporary")
            return io.BytesIO(data)

        downloader = PackageDownloader(
            opener=opener,
            max_attempts=2,
            retry_delay_seconds=0,
        )
        result = downloader.download("https://example.invalid/dds.zip", target, manifest)
        self.assertEqual(result.read_bytes(), data)
        self.assertEqual(len(calls), 2)

    def test_downloader_cancel_removes_partial_file(self):
        package = self.make_zip({"DDS.exe": b"payload"})
        data = package.read_bytes()
        manifest = self.manifest_for(package)
        target = self.root / "downloads-cancel" / manifest.asset
        checks = 0

        def cancel_check():
            nonlocal checks
            checks += 1
            return checks >= 2

        downloader = PackageDownloader(
            opener=lambda _request, timeout: io.BytesIO(data),
            max_attempts=2,
            retry_delay_seconds=0,
        )
        with self.assertRaises(UpdateCancelled):
            downloader.download(
                "https://example.invalid/dds.zip",
                target,
                manifest,
                cancel_check=cancel_check,
            )
        self.assertFalse(target.exists())
        self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_stager_cancel_removes_partial_candidate(self):
        payload = self.root / "cancel-payload"
        payload.mkdir()
        (payload / "DDSApp.exe").write_bytes(b"app")
        write_install_manifest(payload, create_install_manifest(payload, "0.7.0"))
        package = self.root / "cancel-stage.zip"
        with zipfile.ZipFile(package, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in payload.rglob("*"):
                if item.is_file():
                    archive.write(item, item.relative_to(payload).as_posix())
        manifest = self.manifest_for(package, version="0.7.0")
        paths = build_updater_paths(build_runtime_paths(
            app_data=self.root / "cancel-data",
            app_dir=self.root / "cancel-program",
        ))
        checks = 0

        def cancel_check():
            nonlocal checks
            checks += 1
            return checks >= 3

        with self.assertRaises(UpdateCancelled):
            PackageStager(paths).stage(package, manifest, cancel_check=cancel_check)
        self.assertFalse((paths.staging / "0.7.0").exists())

    def test_release_source_retries_transient_transport_failure(self):
        payload = [{
            "tag_name": "v0.7.0",
            "draft": False,
            "prerelease": True,
            "html_url": "https://example.invalid/release",
            "body": "notes",
            "published_at": "2026-09-24T00:00:00Z",
            "assets": [{
                "name": "DDS-0.7.0-update.json",
                "browser_download_url": "https://example.invalid/update.json",
            }],
        }]
        calls = 0

        def opener(_request, timeout):
            nonlocal calls
            calls += 1
            if calls == 1:
                raise urllib.error.URLError("temporary")
            return io.BytesIO(json.dumps(payload).encode("utf-8"))

        source = GitHubReleaseSource(
            opener=opener,
            max_attempts=2,
            retry_delay_seconds=0,
        )
        descriptor = source.latest(channel="preview")
        self.assertIsNotNone(descriptor)
        self.assertEqual(descriptor.version, "0.7.0")
        self.assertEqual(calls, 2)

    def test_auto_install_setting_implies_auto_download(self):
        store = SettingsStore(self.root / "settings.json")
        settings = store.update(
            update_auto_download_enabled=False,
            update_auto_install_enabled=True,
        )
        self.assertTrue(settings.update_auto_install_enabled)
        self.assertTrue(settings.update_auto_download_enabled)


    def test_install_manifest_detects_payload_tampering(self):
        payload = self.root / "payload"
        payload.mkdir()
        app = payload / "DDSApp.exe"
        app.write_bytes(b"good")
        write_install_manifest(payload, create_install_manifest(payload, "0.7.0"))
        loaded = InstallManifest.load(payload / "DDS.install.json")
        loaded.verify(payload)
        app.write_bytes(b"tampered")
        with self.assertRaises(ValueError):
            loaded.verify(payload)

    def test_version_pointer_is_restricted_to_its_version_directory(self):
        good = VersionPointer("0.7.0", "versions/0.7.0")
        good.validate()
        with self.assertRaises(ValueError):
            VersionPointer("0.7.0", "../0.7.0").validate()
        with self.assertRaises(ValueError):
            VersionPointer("0.7.0", "versions/0.7.1").validate()

    def test_external_installer_commits_complete_version_by_pointer(self):
        app_root = self.root / "DDS"
        versions = app_root / "versions"
        old_payload = versions / "0.7.0.dev0"
        old_payload.mkdir(parents=True)
        (old_payload / "DDSApp.exe").write_bytes(b"old")
        write_install_manifest(
            old_payload,
            create_install_manifest(old_payload, "0.7.0.dev0"),
        )
        old_pointer = VersionPointer("0.7.0.dev0", "versions/0.7.0.dev0")
        write_pointer(app_root / CURRENT_POINTER, old_pointer)
        (app_root / "DDS.exe").write_bytes(b"launcher")

        staged = self.root / "staged"
        staged.mkdir()
        (staged / "DDSApp.exe").write_bytes(b"new")
        write_install_manifest(staged, create_install_manifest(staged, "0.7.0"))

        ack = self.root / "ack.ok"
        with patch("dds_companion.updater.external.subprocess.Popen") as popen:
            install_candidate(
                application_dir=app_root,
                staged_dir=staged,
                target_version="0.7.0",
                parent_pid=0,
                ack_path=ack,
                resume_state=None,
            )
        self.assertEqual(read_pointer(app_root / CURRENT_POINTER).version, "0.7.0")
        # previous.json is committed history and is updated only after startup ACK.
        self.assertFalse((app_root / PREVIOUS_POINTER).exists())
        pending = read_json(app_root / PENDING_UPDATE)
        self.assertEqual(pending["candidate"]["version"], "0.7.0")
        self.assertTrue((versions / "0.7.0" / "DDSApp.exe").is_file())
        popen.assert_called_once()

    def test_launcher_ack_keeps_candidate_and_clears_pending(self):
        root = self.root / "app"
        root.mkdir()
        previous = VersionPointer("0.7.0", "versions/0.7.0")
        candidate = VersionPointer("0.7.1", "versions/0.7.1")
        (root / "versions" / "0.7.0").mkdir(parents=True)
        (root / "versions" / "0.7.1").mkdir(parents=True)
        ack = self.root / "startup.ok"
        pending = PendingUpdate(previous, candidate, str(ack), None, timeout_seconds=5)
        write_pointer(root / CURRENT_POINTER, candidate)
        write_pending(root / PENDING_UPDATE, pending)

        class AckProcess:
            def poll(self):
                ack.write_text("ok", encoding="utf-8")
                return None

        with patch("dds_companion.launcher._spawn", return_value=AckProcess()):
            result = dds_launcher._launch_pending(root, pending, [])
        self.assertEqual(result, 0)
        self.assertFalse((root / PENDING_UPDATE).exists())
        self.assertEqual(read_pointer(root / CURRENT_POINTER), candidate)
        self.assertEqual(read_pointer(root / PREVIOUS_POINTER), previous)



    def test_launcher_recovery_removes_only_orphan_versions_and_incoming_dirs(self):
        root = self.root / "recovery-app"
        versions = root / "versions"
        for name in ("0.7.0", "0.6.9", "0.7.1", ".0.7.2.incoming-dead"):
            (versions / name).mkdir(parents=True, exist_ok=True)
        write_pointer(root / CURRENT_POINTER, VersionPointer("0.7.0", "versions/0.7.0"))
        write_pointer(root / PREVIOUS_POINTER, VersionPointer("0.6.9", "versions/0.6.9"))

        dds_launcher._recover_orphan_versions(root)

        self.assertTrue((versions / "0.7.0").is_dir())
        self.assertTrue((versions / "0.6.9").is_dir())
        self.assertFalse((versions / "0.7.1").exists())
        self.assertFalse((versions / ".0.7.2.incoming-dead").exists())

    def test_launcher_recovery_preserves_active_pending_versions(self):
        root = self.root / "recovery-pending-app"
        versions = root / "versions"
        for name in ("0.7.0", "0.7.1", "0.6.9", "0.8.0"):
            (versions / name).mkdir(parents=True, exist_ok=True)
        current = VersionPointer("0.7.0", "versions/0.7.0")
        previous = VersionPointer("0.6.9", "versions/0.6.9")
        candidate = VersionPointer("0.7.1", "versions/0.7.1")
        write_pointer(root / CURRENT_POINTER, current)
        write_pointer(root / PREVIOUS_POINTER, previous)
        write_pending(root / PENDING_UPDATE, PendingUpdate(
            previous=current,
            candidate=candidate,
            ack_path=str(self.root / "pending-recovery.ok"),
            resume_state_path=None,
        ))

        dds_launcher._recover_orphan_versions(root)

        self.assertTrue((versions / "0.7.0").is_dir())
        self.assertTrue((versions / "0.7.1").is_dir())
        self.assertTrue((versions / "0.6.9").is_dir())
        self.assertFalse((versions / "0.8.0").exists())

    def test_launcher_recovery_fails_safe_without_valid_authority(self):
        root = self.root / "recovery-no-authority"
        versions = root / "versions"
        (versions / "mystery").mkdir(parents=True)
        (versions / ".incoming-mystery").mkdir()
        (root / CURRENT_POINTER).write_text("{broken", encoding="utf-8")

        dds_launcher._recover_orphan_versions(root)

        self.assertTrue((versions / "mystery").is_dir())
        self.assertTrue((versions / ".incoming-mystery").is_dir())

    def test_launcher_ack_repairs_power_loss_between_pending_and_current_pointer(self):
        root = self.root / "crash-window-app"
        root.mkdir()
        previous = VersionPointer("0.7.0", "versions/0.7.0")
        candidate = VersionPointer("0.7.1", "versions/0.7.1")
        (root / "versions" / "0.7.0").mkdir(parents=True)
        (root / "versions" / "0.7.1").mkdir(parents=True)
        ack = self.root / "crash-window.ok"
        pending = PendingUpdate(previous, candidate, str(ack), None, timeout_seconds=5)

        # Simulate power loss after pending_update.json was durable but before
        # external updater switched current.json to candidate.
        write_pointer(root / CURRENT_POINTER, previous)
        write_pending(root / PENDING_UPDATE, pending)

        class AckProcess:
            def poll(self):
                ack.write_text("ok", encoding="utf-8")
                return None

        with patch("dds_companion.launcher._spawn", return_value=AckProcess()):
            result = dds_launcher._launch_pending(root, pending, [])

        self.assertEqual(result, 0)
        self.assertEqual(read_pointer(root / CURRENT_POINTER), candidate)
        self.assertEqual(read_pointer(root / PREVIOUS_POINTER), previous)
        self.assertFalse((root / PENDING_UPDATE).exists())

    def test_launcher_failed_candidate_rolls_pointer_back(self):
        root = self.root / "app"
        root.mkdir()
        older = VersionPointer("0.6.9", "versions/0.6.9")
        previous = VersionPointer("0.7.0", "versions/0.7.0")
        candidate = VersionPointer("0.7.1", "versions/0.7.1")
        (root / "versions" / "0.6.9").mkdir(parents=True)
        (root / "versions" / "0.7.0").mkdir(parents=True)
        (root / "versions" / "0.7.1").mkdir(parents=True)
        write_pointer(root / PREVIOUS_POINTER, older)
        pending = PendingUpdate(previous, candidate, str(self.root / "never.ok"), None, timeout_seconds=5)
        write_pointer(root / CURRENT_POINTER, candidate)
        write_pending(root / PENDING_UPDATE, pending)

        failed = MagicMock()
        failed.poll.return_value = 1
        fallback = MagicMock()
        with patch("dds_companion.launcher._spawn", side_effect=[failed, fallback]) as spawn:
            result = dds_launcher._launch_pending(root, pending, [])
        self.assertEqual(result, 10)
        self.assertEqual(read_pointer(root / CURRENT_POINTER), previous)
        self.assertEqual(read_pointer(root / PREVIOUS_POINTER), older)
        self.assertTrue((root / "versions" / "0.6.9").is_dir())
        self.assertTrue((root / "versions" / "0.7.0").is_dir())
        self.assertFalse((root / "versions" / "0.7.1").exists())
        self.assertFalse((root / PENDING_UPDATE).exists())
        self.assertEqual(spawn.call_count, 2)



if __name__ == "__main__":
    unittest.main()