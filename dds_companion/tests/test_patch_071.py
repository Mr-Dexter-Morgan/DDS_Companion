from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from dds_companion.core.fs_scan import iter_regular_files
from dds_companion.services.stats_service import directory_file_count, directory_size


class Patch071FilesystemRaceTests(unittest.TestCase):
    def test_stats_scan_survives_media_shard_disappearing_mid_walk(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            stable = root / "aa"
            vanishing = root / "bc"
            stable.mkdir()
            vanishing.mkdir()
            (stable / "ok.bin").write_bytes(b"ok")
            doomed = vanishing / "gone.bin"
            doomed.write_bytes(b"gone")

            real_scandir = os.scandir
            vanished = False

            def racing_scandir(path):
                nonlocal vanished
                current = Path(path)
                if current == vanishing and not vanished:
                    vanished = True
                    doomed.unlink()
                    vanishing.rmdir()
                    raise FileNotFoundError(3, "simulated concurrent cache prune", str(vanishing))
                return real_scandir(path)

            with patch("dds_companion.core.fs_scan.os.scandir", side_effect=racing_scandir):
                self.assertEqual(directory_size(root), 2)

            self.assertTrue(vanished)
            self.assertEqual(directory_file_count(root), 1)

    def test_file_iterator_treats_missing_root_as_empty(self):
        with tempfile.TemporaryDirectory() as temp:
            missing = Path(temp) / "already-pruned"
            self.assertEqual(list(iter_regular_files(missing)), [])


if __name__ == "__main__":
    unittest.main()
