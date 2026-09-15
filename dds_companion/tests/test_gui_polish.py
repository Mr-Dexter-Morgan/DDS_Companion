from __future__ import annotations

import unittest
from pathlib import Path

from dds_companion.gui.layout_profile import choose_layout_profile


class LayoutProfileTests(unittest.TestCase):
    def test_1366x768_prefers_compact(self):
        self.assertEqual(
            choose_layout_profile(
                available_width=1366,
                available_height=728,
                logical_dpi=96,
                device_pixel_ratio=1,
                window_width=1280,
            ),
            "compact",
        )

    def test_1080p_prefers_standard(self):
        self.assertEqual(
            choose_layout_profile(
                available_width=1920,
                available_height=1040,
                logical_dpi=96,
                device_pixel_ratio=1,
                window_width=1320,
            ),
            "standard",
        )

    def test_dense_4k_prefers_large(self):
        self.assertEqual(
            choose_layout_profile(
                available_width=1920,
                available_height=1040,
                logical_dpi=192,
                device_pixel_ratio=2,
                window_width=1500,
            ),
            "large",
        )


class GuiPolishSourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]

    def test_normal_launcher_uses_pythonw_and_debug_launcher_uses_python(self):
        normal = (self.root / "run_companion.bat").read_text(encoding="utf-8")
        debug = (self.root / "run_companion_debug.bat").read_text(encoding="utf-8")
        self.assertIn("pythonw.exe", normal)
        self.assertIn("run_companion.pyw", normal)
        self.assertIn("python -m dds_companion.gui.app", debug)

    def test_duplicate_library_buttons_are_removed_from_topbar_and_dashboard(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        self.assertNotIn('QPushButton("Open library")', window)
        self.assertEqual(pages.count('QPushButton("Open library folder")'), 1)

    def test_dashboard_is_scroll_safe(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        self.assertIn("scrollable=True", pages)
        self.assertIn("QScrollArea", pages)


    def test_044_health_surface_and_compact_brand_contract(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        self.assertIn("self.sidebar.setFixedWidth(210)", window)
        self.assertIn('("discord", "Discord")', pages)
        self.assertIn('("plugin", "DDS Plugin")', pages)
        self.assertIn('("updates", "Update check")', pages)
        self.assertIn('scrollable=True', pages[pages.index("class HealthPage"):pages.index("class SettingsPage")])
        self.assertIn('Last attempt:', pages)

    def test_settings_separates_primary_controls_from_paths_and_storage(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        theme = (self.root / "dds_companion/gui/theme.py").read_text(encoding="utf-8")
        self.assertIn("QTabWidget", pages)
        self.assertIn('self.tabs.addTab(general, "Основные")', pages)
        self.assertIn('self.tabs.addTab(paths_page, "Paths & Storage")', pages)
        self.assertIn('SectionHeader("Watcher policy"', pages)
        self.assertIn('SectionHeader("Paths & Storage"', pages)
        self.assertIn("QTabWidget#SettingsTabs", theme)


if __name__ == "__main__":
    unittest.main()
