from __future__ import annotations

import unittest
from pathlib import Path

import dds_companion_patchxx as overlay


ROOT = Path(__file__).resolve().parents[2]


class MediaCacheVisual088Tests(unittest.TestCase):
    def test_tetris_layout_is_full_16x12_square_board(self):
        pieces = overlay._build_tetromino_piece_layout()
        self.assertEqual(len(pieces), 48)
        cells = [cell for _shape, piece_cells in pieces for cell in piece_cells]
        self.assertEqual(len(cells), 192)
        self.assertEqual(len(set(cells)), 192)
        self.assertEqual(min(x for x, _y in cells), 0)
        self.assertEqual(max(x for x, _y in cells), 15)
        self.assertEqual(min(y for _x, y in cells), 0)
        self.assertEqual(max(y for _x, y in cells), 11)

    def test_low_occupancy_has_jagged_tetris_skyline(self):
        pieces = overlay._build_tetromino_piece_layout()[:7]
        occupied = {cell for _shape, cells in pieces for cell in cells}
        columns = sorted({x for x, _y in occupied})
        self.assertEqual(columns[0], 0)
        self.assertLessEqual(columns[-1], 7)
        heights = []
        for x in columns:
            ys = [y for cx, y in occupied if cx == x]
            heights.append(12 - min(ys))
        self.assertGreaterEqual(len(set(heights)), 3)
        # At ~14% the board should not already look like a completed rectangle.
        bounding_cells = (columns[-1] - columns[0] + 1) * (max(y for _x, y in occupied) - min(y for _x, y in occupied) + 1)
        self.assertLess(len(occupied), bounding_cells)

    def test_limited_cache_visual_uses_real_limit(self):
        mib = 1024**2
        percent, scale = overlay._cache_visual_percent(139 * mib, 1024 * mib)
        self.assertIsNone(scale)
        self.assertAlmostEqual(percent, 13.57421875)

    def test_unlimited_cache_visual_uses_explicit_virtual_scale(self):
        mib = 1024**2
        percent, scale = overlay._cache_visual_percent(139 * mib, None)
        self.assertEqual(scale, 1024 * mib)
        self.assertAlmostEqual(percent, 13.57421875)
        percent2, scale2 = overlay._cache_visual_percent(1025 * mib, None)
        self.assertEqual(scale2, 2048 * mib)
        self.assertAlmostEqual(percent2, 50.048828125)

    def test_source_contract_keeps_cells_square_not_capsules(self):
        source = (ROOT / "dds_companion_patchxx.py").read_text(encoding="utf-8")
        self.assertIn("COLS = 16", source)
        self.assertIn("ROWS = 12", source)
        self.assertIn("cell_w = cell_h = cell_size", source)
        self.assertIn("preserving 1:1 cells", source)
        self.assertNotIn("Bridge only cells that belong to the same tetromino", source)
        self.assertIn('self.percent.setText(f"масштаб до {_human_bytes(display_scale)}")', source)


if __name__ == "__main__":
    unittest.main()
