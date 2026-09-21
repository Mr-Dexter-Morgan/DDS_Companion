from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dds_companion import __version__
from dds_companion.core import paths
from dds_companion.core.identity import (
    APPLICATION_DISPLAY_NAME,
    APP_USER_MODEL_ID,
    EXECUTABLE_NAME,
    PRODUCT_NAME,
    resource_path,
)


class DataRoot060Tests(unittest.TestCase):
    def test_061_version_is_bumped(self):
        self.assertEqual(__version__, "0.6.1")

    def test_installed_profile_preserves_localappdata_contract(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(paths.sys, "platform", "win32"), patch.dict(
                os.environ, {"LOCALAPPDATA": temp, "APPDATA": str(Path(temp) / "Roaming")}, clear=False
            ):
                runtime = paths.build_runtime_paths(dds_data=Path(temp) / "DDS_Data")
        self.assertEqual(runtime.deployment_profile, "installed")
        self.assertEqual(runtime.app_data, Path(temp).resolve() / "DDS_Companion")
        self.assertEqual(runtime.database, Path(temp).resolve() / "DDS_Companion" / "database" / "dds.sqlite3")

    def test_portable_profile_uses_data_next_to_application(self):
        with tempfile.TemporaryDirectory() as temp:
            app_dir = Path(temp) / "DDS"
            runtime = paths.build_runtime_paths(
                dds_data=Path(temp) / "DDS_Data",
                portable=True,
                app_dir=app_dir,
            )
        self.assertEqual(runtime.deployment_profile, "portable")
        self.assertEqual(runtime.app_data, app_dir.resolve() / "Data")
        self.assertEqual(runtime.settings, app_dir.resolve() / "Data" / "config" / "settings.json")
        self.assertEqual(runtime.media, app_dir.resolve() / "Data" / "media")

    def test_explicit_data_root_remains_supported_and_wins_over_portable(self):
        with tempfile.TemporaryDirectory() as temp:
            custom = Path(temp) / "CustomRoot"
            runtime = paths.build_runtime_paths(
                dds_data=Path(temp) / "DDS_Data",
                app_data=custom,
                portable=True,
                app_dir=Path(temp) / "App",
            )
        self.assertEqual(runtime.deployment_profile, "custom")
        self.assertEqual(runtime.app_data, custom.resolve())

    def test_runtime_directories_are_all_derived_from_one_data_root(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp) / "DataRoot"
            runtime = paths.build_runtime_paths(Path(temp) / "DDS_Data", root)
            paths.ensure_runtime_dirs(runtime)
            expected_dirs = [
                root,
                root / "database",
                root / "logs",
                root / "cache",
                root / "media",
                root / "backups",
                root / "config",
            ]
            for directory in expected_dirs:
                self.assertTrue(directory.exists(), directory)


class Branding060Tests(unittest.TestCase):
    def test_approved_product_identity_contract(self):
        self.assertEqual(PRODUCT_NAME, "DDS — Discord Data Snatcher")
        self.assertEqual(APPLICATION_DISPLAY_NAME, PRODUCT_NAME)
        self.assertEqual(EXECUTABLE_NAME, "DDS.exe")
        self.assertEqual(APP_USER_MODEL_ID, "DDS.DiscordDataSnatcher.Companion")

    def test_approved_icon_assets_exist(self):
        icon = resource_path("assets/DDS.ico")
        master = resource_path("assets/DDS_app_icon_master.png")
        self.assertTrue(icon.is_file())
        self.assertTrue(master.is_file())
        self.assertGreater(icon.stat().st_size, 1024)
        self.assertGreater(master.stat().st_size, 1024)

    def test_gui_uses_packaged_icon_and_sets_identity_before_qapplication(self):
        root = Path(__file__).resolve().parents[2]
        source = (root / "dds_companion" / "gui" / "app.py").read_text(encoding="utf-8")
        self.assertIn('resource_path("assets/DDS.ico")', source)
        identity_call = source.index("set_windows_app_user_model_id()")
        qapp_call = source.index("QApplication(sys.argv[:1])")
        self.assertLess(identity_call, qapp_call)

    def test_pyinstaller_contract_builds_dds_exe_with_icon_and_version_resource(self):
        project = Path(__file__).resolve().parents[2]
        spec = (project / "DDS.spec").read_text(encoding="utf-8")
        version = (project / "build" / "windows_version_info.txt").read_text(encoding="utf-8")
        self.assertIn('name="DDS"', spec)
        self.assertIn('icon=str(ROOT / "assets" / "DDS.ico")', spec)
        self.assertIn('version=str(ROOT / "build" / "windows_version_info.txt")', spec)
        self.assertIn("DDS.exe", version)
        self.assertIn("DDS — Discord Data Snatcher", version)
        self.assertIn("0.6.1", version)


if __name__ == "__main__":
    unittest.main()
