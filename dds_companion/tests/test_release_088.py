from __future__ import annotations

import os
import tempfile
import unittest
from unittest import mock

from dds_companion import __version__
from dds_companion.updater.integrity import sha256_file
from tools.assemble_windows_dist import zip_tree
from tools.generate_windows_version_info import numeric_version, render_version_info


class Release088Tests(unittest.TestCase):
    def test_version_is_088(self):
        self.assertEqual(__version__, "0.8.8")

    def test_windows_build_uses_selected_python_and_reproducible_controls(self):
        from pathlib import Path

        root = Path(__file__).resolve().parents[2]
        script = (root / "build_windows.bat").read_text(encoding="utf-8")
        self.assertIn("python -m venv .venv-build", script)
        self.assertNotIn("py -3 -m venv .venv-build", script)
        self.assertIn("PYTHONHASHSEED=1", script)
        self.assertIn("SOURCE_DATE_EPOCH=315532800", script)

    def test_windows_version_metadata_generator_is_088(self):
        self.assertEqual(numeric_version(__version__), (0, 8, 8, 0))
        metadata = render_version_info(
            description="DDS Application Runtime",
            internal_name="DDSApp",
            filename="DDSApp.exe",
        )
        self.assertIn("0.8.8", metadata)
        self.assertNotIn("0.8.7", metadata)

    def test_zip_tree_is_deterministic(self):
        from pathlib import Path

        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            payload = root / "payload"
            payload.mkdir()
            (payload / "a.txt").write_text("alpha\n", encoding="utf-8")
            (payload / "b.bin").write_bytes(b"\x00\xff\x10")
            first = root / "first.zip"
            second = root / "second.zip"
            with mock.patch.dict(os.environ, {"SOURCE_DATE_EPOCH": "315532800"}):
                zip_tree(payload, first)
                zip_tree(payload, second)
            self.assertEqual(sha256_file(first), sha256_file(second))


if __name__ == "__main__":
    unittest.main()
