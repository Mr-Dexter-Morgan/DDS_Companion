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
        self.assertIn("DDS Companion 0.5.4", normal)
        self.assertIn("python -m dds_companion.gui.app", debug)
        self.assertIn("DDS Companion 0.5.4", debug)

    def test_050_first_run_gui_dependency_bootstrap_is_automatic(self):
        normal = (self.root / "run_companion.bat").read_text(encoding="utf-8")
        installer = (self.root / "install_gui_dependencies.bat").read_text(encoding="utf-8")
        self.assertIn("goto bootstrap_gui", normal)
        self.assertIn("install_gui_dependencies.bat --no-pause", normal)
        self.assertIn("No user action is required", normal)
        self.assertNotIn("choice /C", normal)
        self.assertNotIn("Install it now?", normal)
        self.assertIn("pip install --disable-pip-version-check -r requirements-gui.txt", installer)
        self.assertNotIn("pip install --upgrade", installer)

    def test_duplicate_library_buttons_are_removed_from_topbar_and_dashboard(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        self.assertNotIn('QPushButton("Open library")', window)
        self.assertEqual(pages.count('QPushButton("Открыть папку библиотеки")'), 0)

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
        self.assertIn('("media", "Media Backfill")', pages)
        self.assertIn('scrollable=True', pages[pages.index("class HealthPage"):pages.index("class SettingsPage")])
        self.assertIn('Last attempt:', pages)

    def test_045_startup_foreground_is_one_shot_and_not_persistent_topmost(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        self.assertIn("self._startup_foreground_attempted = False", window)
        self.assertIn("QTimer.singleShot(75, self._bring_to_front_once)", window)
        self.assertIn("if self._startup_foreground_attempted:", window)
        self.assertIn("user32.SetWindowPos(hwnd, HWND_TOPMOST", window)
        self.assertIn("user32.SetWindowPos(hwnd, HWND_NOTOPMOST", window)
        self.assertNotIn("WindowStaysOnTopHint", window)

    def test_050_dashboard_keeps_storage_product_surface(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        dashboard = pages[pages.index("class DashboardPage"):pages.index("class LibraryPage")]
        self.assertNotIn("self.health_card", dashboard)
        self.assertNotIn('QPushButton("Open DDS_Data")', dashboard)
        self.assertNotIn('QPushButton("Open logs")', dashboard)
        self.assertIn("StorageDonut", dashboard)
        self.assertIn('StorageRow("Медиакэш", SUCCESS)', dashboard)

    def test_050_global_health_status_is_a_shortcut(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        self.assertIn('self.top_status = QPushButton("STARTING")', window)
        self.assertIn("self.top_status.clicked.connect(self._open_health_from_status)", window)
        self.assertIn('self.PAGE_NAMES.index("Health")', window)

    def test_050_settings_has_real_storage_media_and_diagnostics_sections(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        theme = (self.root / "dds_companion/gui/theme.py").read_text(encoding="utf-8")
        self.assertIn("QTabWidget", pages)
        self.assertIn('self.tabs.addTab(general, "Общие")', pages)
        self.assertIn('self.tabs.addTab(storage, "Хранилище")', pages)
        self.assertIn('self.tabs.addTab(archive, "Архив")', pages)
        self.assertIn('self.tabs.addTab(diagnostics, "Диагностика")', pages)
        self.assertIn('SectionHeader(\n            "Хранение медиа"', pages)
        self.assertIn('QPushButton("Очистить медиакэш")', pages)
        self.assertIn('QPushButton("Запустить диагностику")', pages)
        self.assertIn("QTabWidget#SettingsTabs", theme)
        self.assertIn('QFrame[settingRow="true"]', theme)


    def test_050_media_toggle_logs_both_directions_and_manual_requeue_is_explicit(self):
        media_runtime = (self.root / "dds_companion/services/media_runtime.py").read_text(encoding="utf-8")
        gui_runtime = (self.root / "dds_companion/gui/runtime.py").read_text(encoding="utf-8")
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        self.assertIn('event_type="media_backfill_enabled"', media_runtime)
        self.assertIn('event_type="media_backfill_disabled"', media_runtime)
        self.assertIn("requeue_manual_clear_evictions", media_runtime)
        self.assertIn("control_queue.get_nowait", media_runtime)
        self.assertIn("request_media_autodownload_change", gui_runtime)
        self.assertIn("request_media_autodownload_change(bool(value))", window)

    def test_050_storage_rows_match_donut_category_colors(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        widgets = (self.root / "dds_companion/gui/widgets.py").read_text(encoding="utf-8")
        self.assertIn('StorageRow("База данных", ACCENT)', pages)
        self.assertIn('StorageRow("Данные DDS", INFO)', pages)
        self.assertIn('StorageRow("Медиакэш", SUCCESS)', pages)
        self.assertIn('StorageRow("Прочее", WARNING)', pages)
        self.assertIn('StorageRow("Логи", MUTED)', pages)
        self.assertIn("QProgressBar::chunk", widgets)
        self.assertIn("background:{self.color}", widgets)

    def test_050_only_real_new_media_toggle_is_exposed(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        self.assertNotIn('QCheckBox("Start with Windows")', pages)
        self.assertIn('Автоматическая загрузка медиа', pages)
        self.assertIn('media_autodownload_enabled', pages)
        self.assertNotIn('QPushButton("Check for updates")', pages)

    def test_051_navigation_is_localized_without_renaming_internal_page_ids(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        self.assertIn('PAGE_NAMES = ("Dashboard", "Library", "Activity", "Health", "Settings")', window)
        self.assertIn('PAGE_LABELS = ("Главная", "Библиотека", "Активность", "Статус", "Настройки")', window)
        self.assertIn('"Главная"', pages)
        self.assertIn('"Библиотека"', pages)
        self.assertIn('"Активность"', pages)
        self.assertIn('"Статус"', pages)
        self.assertIn('"Настройки"', pages)

    def test_051_dashboard_has_no_manual_refresh_but_refreshes_when_reopened(self):
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        dashboard = pages[pages.index("class DashboardPage"):pages.index("class LibraryPage")]
        self.assertNotIn('Обновить', dashboard)
        self.assertIn('if index == self.PAGE_NAMES.index("Dashboard"):', window)
        self.assertIn('self.runtime.request_refresh()', window)

    def test_051_general_owns_media_behavior_toggles_with_existing_backend_keys(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        general_start = pages.index('general, general_layout = self._make_scroll_page()')
        storage_start = pages.index('storage, storage_layout = self._make_scroll_page()')
        archive_start = pages.index('archive, archive_layout = self._make_scroll_page()')
        general = pages[general_start:storage_start]
        storage = pages[storage_start:archive_start]
        self.assertIn('Автоматическая загрузка медиа', general)
        self.assertIn('Подтверждать очистку кэша', general)
        self.assertIn('media_autodownload_enabled', general)
        self.assertIn('confirm_media_cache_clear', general)
        self.assertNotIn('media_autodownload_enabled', storage)
        self.assertNotIn('confirm_media_cache_clear', storage)

    def test_051_storage_sections_are_ordered_by_user_importance(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        start = pages.index('storage, storage_layout = self._make_scroll_page()')
        end = pages.index('archive, archive_layout = self._make_scroll_page()')
        storage = pages[start:end]
        policy = storage.index('"Хранение медиа"')
        usage = storage.index('"Использование хранилища"')
        paths = storage.index('"Расположение файлов"')
        self.assertLess(policy, usage)
        self.assertLess(usage, paths)




class LibraryUx054SourceContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root = Path(__file__).resolve().parents[2]

    def test_054_library_is_navigation_plus_message_viewer_without_search_or_ids(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        library = pages[pages.index("class LibraryPage"):pages.index("class ActivityPage")]
        self.assertIn('self.tree.setHeaderLabels(["Раздел", "Сообщений", "Медиа", "Выгрузка"])', library)
        self.assertIn('QSplitter(Qt.Horizontal)', library)
        self.assertIn('QPushButton("Показать ещё")', library)
        self.assertIn('PAGE_SIZE = 50', library)
        self.assertNotIn('Поиск по серверу, каналу или теме…', library)
        self.assertNotIn('Технический ID', library)
        self.assertNotIn('Копировать ID', library)
        self.assertNotIn('Последняя активность', library)

    def test_054_library_has_three_state_future_export_rule(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        service = (self.root / "dds_companion/services/library_service.py").read_text(encoding="utf-8")
        migrations = (self.root / "dds_companion/storage/migrations.py").read_text(encoding="utf-8")
        self.assertIn('"По умолчанию — выгружать"', pages)
        self.assertIn('"По умолчанию — не выгружать"', pages)
        self.assertIn('combo.addItem("Выгружать", "INCLUDE")', pages)
        self.assertIn('combo.addItem("Не выгружать", "EXCLUDE")', pages)
        self.assertIn('archive_export_rules', service)
        self.assertIn('archive_export_rules', migrations)

    def test_054_dashboard_localizes_user_facing_storage_and_snatcher_labels(self):
        pages = (self.root / "dds_companion/gui/pages.py").read_text(encoding="utf-8")
        window = (self.root / "dds_companion/gui/window.py").read_text(encoding="utf-8")
        dashboard = pages[pages.index("class DashboardPage"):pages.index("class LibraryPage")]
        self.assertIn('StorageRow("База данных", ACCENT)', dashboard)
        self.assertIn('StorageRow("Данные DDS", INFO)', dashboard)
        self.assertIn('Найдено / Стырено', dashboard)
        self.assertIn('Вложения', dashboard)
        self.assertIn('импортов', dashboard)
        self.assertIn('событий активности', dashboard)
        self.assertNotIn('LOCAL FIRST', window)


if __name__ == "__main__":
    unittest.main()
