from __future__ import annotations

import hashlib
import unittest
from pathlib import Path

from dds_companion import __version__


ROOT = Path(__file__).resolve().parents[2]


class Release085SourceContractTests(unittest.TestCase):
    def test_current_version_is_085(self):
        self.assertEqual(__version__, "0.8.5")

    def test_accepted_overlay_is_the_runtime_boot_hook(self):
        launcher = (ROOT / "run_companion.pyw").read_text(encoding="utf-8")
        overlay = (ROOT / "dds_companion_patchxx.py").read_text(encoding="utf-8")
        self.assertIn("from dds_companion_patchxx import main", launcher)
        for needle in (
            "_TETROMINO_BLOCK_PATTERNS",
            "_rearm_due_transient_network_failures",
            "_is_webp_metadata_size_variance_spec",
            'self.tabs.addTab(page, "О программе")',
        ):
            self.assertIn(needle, overlay)

    def test_accepted_visual_assets_are_exact(self):
        expected = {
            "DDS_brand_header_v1.png": "09d3875993a829a40fd3ab05016f7ad9284d48c259cf7d87f636f3241ef10ffa",
            "DDS_about_banner_v1.png": "1ac7c2514c069e1e185cf26987f45877f4a0d3829cfcfe735d30ea95172a6be9",
        }
        for name, digest in expected.items():
            path = ROOT / "assets" / name
            self.assertTrue(path.is_file(), path)
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), digest)

    def test_branding_and_update_copy_match_accepted_081_baseline(self):
        window = (ROOT / "dds_companion" / "gui" / "window.py").read_text(encoding="utf-8")
        theme = (ROOT / "dds_companion" / "gui" / "theme.py").read_text(encoding="utf-8")
        pages = (ROOT / "dds_companion" / "gui" / "pages.py").read_text(encoding="utf-8")
        self.assertIn('resource_path("assets/DDS_brand_header_v1.png")', window)
        self.assertIn("mark.setFixedSize(72, 92)", window)
        self.assertIn("brand_pixmap.scaled(68, 88", window)
        self.assertIn("font-size: 22pt", theme)
        for text in (
            "Автоматически проверять наличие обновлений не чаще одного раза в сутки.",
            "Если найдена новая версия, DDS загрузит её заранее и проверит целостность.",
            "Автоматически установить уже загруженное и проверенное обновление.",
            "Проверить обновления вручную в любой момент.",
            "Обновления устанавливаются безопасно. Ваши данные и настройки сохраняются.",
        ):
            self.assertIn(text, pages)
        for old in ("GitHub Releases", "staging и проверить SHA-256", "updater-процессом", "update payload"):
            self.assertNotIn(old, pages)

    def test_build_and_release_contract_is_stable(self):
        spec = (ROOT / "DDSApp.spec").read_text(encoding="utf-8")
        assemble = (ROOT / "tools" / "assemble_windows_dist.py").read_text(encoding="utf-8")
        release = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
        self.assertIn("DDS_brand_header_v1.png", spec)
        self.assertIn("DDS_about_banner_v1.png", spec)
        self.assertIn('channel="stable"', assemble)
        self.assertIn("Publish GitHub Stable Release", release)
        self.assertNotIn("--prerelease", release)


if __name__ == "__main__":
    unittest.main()
