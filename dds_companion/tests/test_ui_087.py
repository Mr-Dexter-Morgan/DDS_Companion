from __future__ import annotations

import unittest
from pathlib import Path


class Ui087SourceContracts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]
        cls.pages = (cls.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")

    def test_dashboard_owns_eight_media_lifecycle_cards_in_2x4_grid(self):
        dashboard = self.pages[self.pages.index("class DashboardPage"):self.pages.index("class LibraryPage")]
        for label in (
            "Всего вложений", "Известно", "Кэшировано", "Кэш очищен",
            "Требует внимания", "Обработано", "Ждёт переобнаружения", "Источник удалён",
        ):
            self.assertIn(f'"{label}"', dashboard)
        self.assertGreaterEqual(dashboard.count('LifecycleMetricCard('), 8)
        self.assertIn("i // 4, i % 4", dashboard)
        self.assertIn("grid.addWidget(self.session_card, 1, 0, 1, 2)", dashboard)
        self.assertIn("grid.addWidget(self.activity_card, 1, 2, 1, 2)", dashboard)


    def test_r2_dashboard_visual_hierarchy_and_icons_are_local(self):
        dashboard = self.pages[self.pages.index("class DashboardPage"):self.pages.index("class LibraryPage")]
        for label in ("Общее хранилище", "Сообщения", "Структура", "Медиа"):
            self.assertIn(f'"{label}"', dashboard)
        self.assertGreaterEqual(dashboard.count('SummaryMetricCard('), 4)
        self.assertIn('self.lifecycle_panel = Card()', dashboard)
        self.assertIn('self.lifecycle_panel.setProperty("dashboardGroup", True)', dashboard)
        self.assertIn('session_strip.setProperty("dashboardInset", True)', dashboard)
        self.assertIn('activity_strip.setProperty("dashboardInset", True)', dashboard)
        self.assertIn('"session", background="#132A4E"', dashboard)
        self.assertIn('"recent", background="#132A4E"', dashboard)

        widgets = (self.root / "dds_companion/gui/widgets.py").read_text(encoding="utf-8")
        self.assertIn("class IconBadge", widgets)
        self.assertIn('resource_path(f"assets/icons/{icon_name}.svg")', widgets)
        icon_dir = self.root / "assets/icons"
        for icon in ("storage", "messages", "structure", "media", "home", "library", "status", "settings"):
            self.assertTrue((icon_dir / f"{icon}.svg").is_file(), icon)

    def test_r2_sidebar_and_runtime_cache_use_icons(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        self.assertIn('nav_icons = ("home", "library", "activity", "status", "settings")', window)
        self.assertIn('button.setIcon(QIcon(str(resource_path(f"assets/icons/{nav_icons[index]}.svg"))))', window)
        overlay = (self.root / "dds_companion_patchxx.py").read_text(encoding="utf-8")
        self.assertIn("from dds_companion.gui.widgets import IconBadge", overlay)
        self.assertIn('"storage", background="#162A4C"', overlay)

    def test_status_is_single_page_and_contains_media_runtime_error_and_attention(self):
        health = self.pages[self.pages.index("class HealthPage"):self.pages.index("class SettingsPage")]
        self.assertNotIn("HealthTabs", health)
        self.assertNotIn('addTab(lifecycle', health)
        runtime = health.index('runtime_title = QLabel("Загрузка медиа")')
        critical = health.index('"Последняя критическая ошибка"')
        attention = health.index('"Медиафайлы, требующие внимания"')
        self.assertLess(runtime, critical)
        self.assertLess(critical, attention)

    def test_library_is_full_width_navigation_and_viewer_tabs(self):
        library = self.pages[self.pages.index("class LibraryPage"):self.pages.index("class ActivityPage")]
        self.assertNotIn("QSplitter(Qt.Horizontal)", library)
        self.assertIn('self.library_tabs.addTab(self.navigation_tab, "НАВИГАЦИЯ")', library)
        self.assertIn('self.library_tabs.addTab(self.viewer_tab, "ПРОСМОТР")', library)
        self.assertIn('self.library_tabs.setCurrentWidget(self.viewer_tab)', library)
        self.assertIn('self.breadcrumb = QLabel', library)
        self.assertIn('MetricCard("Сообщения"', library)
        self.assertIn('MetricCard("Медиа"', library)
        theme = (self.root / "dds_companion/gui/theme.py").read_text(encoding="utf-8")
        self.assertIn("QTabWidget#LibraryTabs", theme)

    def test_runtime_overlay_is_087_and_uses_new_dashboard_grid(self):
        overlay = (self.root / "dds_companion_patchxx.py").read_text(encoding="utf-8")
        self.assertIn('dds_companion.__version__ = "0.8.7"', overlay)
        self.assertIn("self.dashboard_grid.indexOf", overlay)
        self.assertNotIn("self.lower_grid", overlay)


if __name__ == "__main__":
    unittest.main()
