from __future__ import annotations

import os
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from dds_companion.gui.pages import SettingsPage


class DiagnosticsIdentityRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.app = QApplication.instance() or QApplication([])

    def test_settings_snapshot_populates_identity_and_capture_contract(self):
        page = SettingsPage(
            on_setting_changed=lambda *_: None,
            on_clear_media_cache=lambda: None,
            on_reset_local_archive=lambda: None,
            on_choose_export_folder=lambda: None,
            on_check_updates=lambda: None,
            on_download_update=lambda: None,
            on_install_update=lambda: None,
            on_cancel_update=lambda: None,
            on_run_diagnostics=lambda: None,
            on_database_check=lambda: None,
            on_copy_report=lambda: None,
        )
        snapshot = {
            "version": "0.7.2",
            "paths": {},
            "watcher": {"poll_ms": 750, "settle_ms": 500},
            "stats": {
                "messages": 80,
                "guilds": 1,
                "channels": 2,
                "threads": 3,
                "total_known_storage_bytes": 0,
                "sqlite_bytes": 0,
                "dds_json_bytes": 0,
                "media_bytes": 0,
                "other_bytes": 0,
                "logs_bytes": 0,
            },
            "settings": {
                "media_cache_limit_bytes": 5 * 1024**3,
                "media_max_file_bytes": 250 * 1024**2,
                "media_retention_days": 30,
                "media_autodownload_enabled": False,
                "confirm_media_cache_clear": True,
                "update_background_check_enabled": True,
                "update_auto_download_enabled": False,
                "update_auto_install_enabled": False,
            },
            "health": {
                "subsystems": {
                    "plugin": {
                        "details": {
                            "plugin_version": "0.5.3",
                            "capture_schema_version": 2,
                            "heartbeat_schema_version": "plugin-heartbeat-v1",
                        }
                    }
                }
            },
        }

        page.update_snapshot(snapshot)

        self.assertEqual(page.version_value.text(), "0.7.2")
        self.assertEqual(page.plugin_value.text(), "0.5.3")
        self.assertEqual(
            page.contract_value.text(),
            "capture-v2 · plugin-heartbeat-v1",
        )


if __name__ == "__main__":
    unittest.main()
