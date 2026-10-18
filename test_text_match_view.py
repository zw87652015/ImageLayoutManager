"""Qt-free tests for the Match Text Size view helpers:
ZoomPan (preview zoom/pan) and the chip layout/stepper math."""

import unittest

from src.app.preview_zoom import MARGIN, ZOOM_MAX, ZOOM_MIN, ZoomPan
from src.app.text_group_chip_layout import (
    SIZE_MAX, SIZE_MIN, STEP_W, chip_regions, chip_width, step_size,
)


def _overlaps(a, b):
    return not (a[0] + a[2] <= b[0] or b[0] + b[2] <= a[0]
                or a[1] + a[3] <= b[1] or b[1] + b[3] <= a[1])


class TestZoomPan(unittest.TestCase):
    VW, VH, IW, IH = 800, 600, 400, 300

    def test_fitted_transform_centres(self):
        z = ZoomPan()
        scale, left, top = z.transform(self.VW, self.VH, self.IW, self.IH)
        # fit scale = min((800-16)/400, (600-16)/300) = 1.9466
        self.assertAlmostEqual(scale, min((self.VW - 2 * MARGIN) / self.IW,
                                          (self.VH - 2 * MARGIN) / self.IH))
        self.assertAlmostEqual(left + self.IW * scale / 2, self.VW / 2)
        self.assertAlmostEqual(top + self.IH * scale / 2, self.VH / 2)
        self.assertTrue(z.fitted)

    def test_zoom_at_keeps_anchor(self):
        z = ZoomPan()
        px, py = 500.0, 250.0
        s0, l0, t0 = z.transform(self.VW, self.VH, self.IW, self.IH)
        ix, iy = (px - l0) / s0, (py - t0) / s0
        z.zoom_at(px, py, 3, self.VW, self.VH, self.IW, self.IH)
        self.assertAlmostEqual(z.zoom, 1.2 ** 3)
        s1, l1, t1 = z.transform(self.VW, self.VH, self.IW, self.IH)
        self.assertAlmostEqual(l1 + ix * s1, px, places=6)
        self.assertAlmostEqual(t1 + iy * s1, py, places=6)
        self.assertFalse(z.fitted)

    def test_zoom_clamps(self):
        z = ZoomPan()
        z.zoom_at(400, 300, 100, self.VW, self.VH, self.IW, self.IH)
        self.assertEqual(z.zoom, ZOOM_MAX)
        z.zoom_at(400, 300, -1000, self.VW, self.VH, self.IW, self.IH)
        self.assertEqual(z.zoom, ZOOM_MIN)
        self.assertEqual(z.pan, (0.0, 0.0))
        self.assertTrue(z.fitted)

    def test_pan_clamps_at_edges(self):
        z = ZoomPan()
        z.zoom_at(400, 300, 2, self.VW, self.VH, self.IW, self.IH)
        z.pan_by(-100000, -100000, self.VW, self.VH, self.IW, self.IH)
        s, left, top = z.transform(self.VW, self.VH, self.IW, self.IH)
        self.assertLessEqual(left + self.IW * s, self.VW + 0.001)
        self.assertGreaterEqual(left + self.IW * s, self.VW - MARGIN - 0.001)
        z.pan_by(100000, 100000, self.VW, self.VH, self.IW, self.IH)
        s, left, top = z.transform(self.VW, self.VH, self.IW, self.IH)
        self.assertGreaterEqual(left, -0.001)
        self.assertLessEqual(left, MARGIN + 0.001)

    def test_pan_pinned_when_fitting(self):
        z = ZoomPan()
        # At zoom 1 the scaled image fits within view - 2*MARGIN, so pan
        # stays pinned to the centred position.
        z.pan_by(50, 50, self.VW, self.VH, self.IW, self.IH)
        self.assertEqual(z.pan, (0.0, 0.0))

    def test_reset(self):
        z = ZoomPan()
        z.zoom_at(400, 300, 5, self.VW, self.VH, self.IW, self.IH)
        z.reset()
        self.assertTrue(z.fitted)

    def test_degenerate_sizes(self):
        z = ZoomPan()
        self.assertEqual(z.transform(0, 600, 400, 300), (1.0, 0.0, 0.0))
        self.assertEqual(z.transform(800, 600, 0, 300), (1.0, 0.0, 0.0))
        z.zoom_at(10, 10, 3, 0, 600, 400, 300)     # no raise
        z.pan_by(10, 10, 800, 600, 400, 0)         # no raise
        self.assertTrue(z.fitted)


class TestChipRegions(unittest.TestCase):
    def test_layout(self):
        for size_w in (30.0, 55.0, 80.0):
            width = chip_width(90.0, size_w)
            r = chip_regions(4.0, 6.0, width, 28.0, size_w)
            parts = [r["name"], r["size"], r["up"], r["down"], r["x"]]
            for part in parts:
                self.assertGreaterEqual(part[0], 4.0 - 1e-9)
                self.assertLessEqual(part[0] + part[2], 4.0 + width + 1e-9)
                self.assertGreaterEqual(part[1], 6.0 - 1e-9)
                self.assertLessEqual(part[1] + part[3], 6.0 + 28.0 + 1e-9)
            for i, a in enumerate(parts):
                for b in parts[i + 1:]:
                    self.assertFalse(_overlaps(a, b), f"{size_w}: {a} vs {b}")
            # left -> right order
            self.assertLess(r["name"][0] + r["name"][2], r["size"][0] + r["size"][2])
            self.assertLess(r["size"][0] + r["size"][2], r["up"][0] + r["up"][2])
            self.assertLess(r["up"][0] + r["up"][2], r["x"][0] + r["x"][2])
            # up above down
            self.assertLess(r["up"][1] + r["up"][3], r["down"][1] + r["down"][3] + 1e-9)
            self.assertEqual(r["up"][2], STEP_W)

    def test_chip_width_gives_name_room(self):
        for name_w in (20.0, 90.0, 200.0):
            width = chip_width(name_w, 55.0)
            r = chip_regions(0.0, 0.0, width, 28.0, 55.0)
            self.assertGreaterEqual(r["name"][2], name_w)


class TestStepSize(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(step_size(12.0, 1), 13.0)
        self.assertEqual(step_size(12.0, -1), 11.0)

    def test_clamps(self):
        self.assertEqual(step_size(SIZE_MIN, -1), SIZE_MIN)
        self.assertEqual(step_size(SIZE_MAX, 1), SIZE_MAX)
        self.assertEqual(step_size(0.2, -1), SIZE_MIN)
        self.assertEqual(step_size(500, 1), SIZE_MAX)

    def test_rounds(self):
        self.assertEqual(step_size(10.005, 0.001), 10.01)


if __name__ == "__main__":
    unittest.main()
