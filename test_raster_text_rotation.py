"""Rotated raster text regions (schema 8): text-frame geometry, rotated
analysis/extraction, dash-tick trim, µ ink ratio, and migration/validation.

Synthetic PIL images only — no OCR, no Qt.
"""

import math
import os
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.utils.raster_text_frame import (
    image_bounds, quad_angle, quad_box, snap_angle, to_image, to_text,
)
from src.utils.raster_text_ocr import DetectedText
from src.utils.raster_text_utils import (
    CAP_HEIGHT_RATIO, DESCENDER_RATIO, apply_raster_text_overrides,
    build_raster_override_spec, ink_ratio_for_text, regions_from_detections,
)
from src.model.data_model import RasterTextRegion
from src.model.migrations import (
    PROJECT_SCHEMA_VERSION, ProjectMigrationError, migrate_project_data,
)

FONT_PATH = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", "arial.ttf")


def _font(px):
    return ImageFont.truetype(FONT_PATH, px)


def _ink_bbox(img):
    arr = np.asarray(img.convert("RGB")).astype(np.int16)
    ys, xs = np.nonzero(arr.max(axis=2) < 200)
    if not len(xs):
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def _text_frame_aabb(img, angle):
    """AABB of the image's ink measured in the text frame of *angle*."""
    arr = np.asarray(img.convert("RGB")).astype(np.int16)
    ys, xs = np.nonzero(arr.max(axis=2) < 200)
    us = xs * math.cos(math.radians(angle)) + ys * math.sin(math.radians(angle))
    vs = -xs * math.sin(math.radians(angle)) + ys * math.cos(math.radians(angle))
    return (int(math.floor(us.min())), int(math.floor(vs.min())),
            int(math.ceil(us.max()) - math.floor(us.min())),
            int(math.ceil(vs.max()) - math.floor(vs.min())))


def _make_rotated_label(text="x: 40 µm", font_px=40, rot_deg=35.0, line_gap=14,
                        canvas=(860, 640)):
    """Render *text* rotated by ``-rot_deg`` (PIL rotate is visual CCW, so
    rotate(rot_deg) gives baseline angle -rot_deg in image coords), on white,
    with a dark axis line parallel to the baseline below the glyphs.

    Returns (image RGBA, DetectedText) with the box in the text frame.
    """
    layer = Image.new("RGBA", (700, 200), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.text((40, 60), text, font=_font(font_px), fill=(0, 0, 0, 255))
    text_ink = _ink_bbox(layer)
    line_layer = Image.new("RGBA", layer.size, (0, 0, 0, 0))
    dl = ImageDraw.Draw(line_layer)
    ly = text_ink[3] + line_gap
    dl.line([(text_ink[0] - 10, ly), (text_ink[2] + 10, ly)], fill=(0, 0, 0, 255), width=3)
    angle = -rot_deg
    img = Image.new("RGBA", canvas, (255, 255, 255, 255))
    rot_text = layer.rotate(rot_deg, expand=True, resample=Image.Resampling.BICUBIC)
    rot_line = line_layer.rotate(rot_deg, expand=True, resample=Image.Resampling.BICUBIC)
    px = (canvas[0] - rot_text.width) // 2
    py = (canvas[1] - rot_text.height) // 2
    img.alpha_composite(rot_line, (px, py))
    img.alpha_composite(rot_text, (px, py))
    # Shift the text-frame origin: ink coords in the final image are the
    # rotated layer's ink offset by (px, py).
    u0, v0, uw, uh = _text_frame_aabb(rot_text, angle)
    cx, cy = rot_text.width / 2, rot_text.height / 2
    # The rotated layer's own coordinates are offset by (px, py) in img.
    x = u0 + px * math.cos(math.radians(angle)) + py * math.sin(math.radians(angle))
    y = v0 - px * math.sin(math.radians(angle)) + py * math.cos(math.radians(angle))
    det = DetectedText(int(math.floor(x)), int(math.floor(y)), uw, uh,
                       text=text, chars=[], angle=angle)
    return img, det, rot_line, (px, py)


class TestFrameMath(unittest.TestCase):
    def test_snap_angle(self):
        self.assertEqual(snap_angle(3), 0.0)
        self.assertEqual(snap_angle(-4.9), 0.0)
        self.assertEqual(snap_angle(88), 0.0)
        self.assertEqual(snap_angle(-87), 0.0)
        self.assertEqual(snap_angle(36), 36.0)
        self.assertEqual(snap_angle(-34.567), -34.57)

    def test_quad_angle(self):
        # Axis-aligned
        self.assertAlmostEqual(quad_angle([(0, 0), (10, 0), (10, 5), (0, 5)]), 0.0)
        # Top edge pointing at 150° normalises to -30
        q = [(0, 0), (math.cos(math.radians(150)), math.sin(math.radians(150))),
             (0, 1), (-1, 1)]
        self.assertAlmostEqual(quad_angle(q), -30.0, places=6)
        self.assertAlmostEqual(quad_angle([(0, 0), (math.cos(math.radians(36)),
                                                    math.sin(math.radians(36))),
                                           (1, 1), (0, 1)]), 36.0, places=6)

    def test_round_trip(self):
        for a in (0.0, -35.0, 36.5, 89.0, -89.9):
            u, v = to_text(123.4, -56.7, a)
            px, py = to_image(u, v, a)
            self.assertAlmostEqual(px, 123.4, places=6)
            self.assertAlmostEqual(py, -56.7, places=6)

    def test_image_bounds_identity(self):
        self.assertEqual(image_bounds(10, 20, 30, 40, 0), (10, 20, 30, 40))
        bx, by, bw, bh = image_bounds(0, 0, 10, 4, 90)
        self.assertEqual((bx, by, bw, bh), (-4, 0, 4, 10))


class TestRotatedRegion(unittest.TestCase):
    def test_detection_analysis_and_font(self):
        img, det, _line, _off = _make_rotated_label()
        (region, reason), = [(r, rs) for r, rs in regions_from_detections(img, [det])]
        self.assertIsNone(reason)
        self.assertAlmostEqual(region.angle, -35.0, places=2)
        self.assertFalse(region.vertical)
        # Horizontal reference through the angle-0 path.
        flat = Image.new("RGBA", (700, 200), (255, 255, 255, 255))
        ImageDraw.Draw(flat).text((40, 60), "x: 40 µm", font=_font(40),
                                  fill=(0, 0, 0, 255))
        fx0, fy0, fx1, fy1 = _ink_bbox(flat)
        fdet = DetectedText(fx0 - 2, fy0 - 2, fx1 - fx0 + 4, fy1 - fy0 + 4,
                            text="x: 40 µm", chars=[], angle=0.0)
        (fregion, freason), = [(r, rs) for r, rs in regions_from_detections(flat, [fdet])]
        self.assertIsNone(freason)
        self.assertGreater(fregion.font_size_px, 0)
        self.assertAlmostEqual(region.font_size_px, fregion.font_size_px,
                               delta=0.10 * fregion.font_size_px)

    def test_apply_scale(self):
        img, det, line_layer, off = _make_rotated_label()
        (region, reason), = [(r, rs) for r, rs in regions_from_detections(img, [det])]
        self.assertIsNone(reason)
        spec = {"regions": [{
            "id": region.id, "x": region.x, "y": region.y, "w": region.w,
            "h": region.h, "scale": 1.5, "anchor": "center",
            "background": region.background, "angle": region.angle,
            "chars": [list(c) for c in region.chars],
        }]}
        out, report = apply_raster_text_overrides(img, spec)
        self.assertEqual(report[0]["status"], "applied")
        src = np.asarray(img.convert("RGB"))
        dst = np.asarray(out.convert("RGB"))
        # Axis-line pixels unchanged.
        la = np.asarray(line_layer.convert("RGBA"))
        lys, lxs = np.nonzero(la[..., 3] > 128)
        px, py = off
        changed = np.abs(dst.astype(np.int16) - src.astype(np.int16)).max(axis=2) > 8
        for yy, xx in zip(lys, lxs):
            self.assertFalse(changed[yy + py, xx + px],
                             f"axis line pixel {(xx + px, yy + py)} changed")
        # Pixels far outside the scaled footprint unchanged.
        self.assertFalse(changed[:20].any())
        self.assertFalse(changed[-20:].any())
        # Ink extent along the baseline direction grew ~1.5x. Restrict to
        # the glyph band (in the text frame) so the parallel axis line —
        # deliberately left out of the region — doesn't dominate.
        cy = region.y + region.h / 2.0
        band = 0.75 * region.h

        def _extent(a):
            ys, xs = np.nonzero(a.max(axis=2) < 200)
            ra = math.radians(-35)
            u = xs * math.cos(ra) + ys * math.sin(ra)
            v = -xs * math.sin(ra) + ys * math.cos(ra)
            u = u[(v >= cy - band) & (v <= cy + band)]
            return u.max() - u.min()
        before = _extent(src)
        after = _extent(dst)
        self.assertAlmostEqual(after / before, 1.5, delta=0.15)

    def test_collision_skip_restores(self):
        img, det, _line, off = _make_rotated_label()
        (region, reason), = [(r, rs) for r, rs in regions_from_detections(img, [det])]
        self.assertIsNone(reason)
        # Block the landing zone: the 1.8x-scaled label must land on this.
        d = ImageDraw.Draw(img)
        bx, by, bw, bh = image_bounds(region.x, region.y, region.w, region.h,
                                      region.angle)
        d.rectangle([bx + bw // 2, by + bh // 2, bx + bw + 40, by + bh + 90],
                    fill=(0, 0, 0, 255))
        spec = {"regions": [{
            "id": region.id, "x": region.x, "y": region.y, "w": region.w,
            "h": region.h, "scale": 1.8, "anchor": "center",
            "background": region.background, "angle": region.angle,
            "chars": [list(c) for c in region.chars],
        }]}
        out, report = apply_raster_text_overrides(img, spec)
        self.assertEqual(report[0]["status"], "skipped_collision")
        np.testing.assert_array_equal(np.asarray(out), np.asarray(img))


class TestDashTrim(unittest.TestCase):
    def _make_tick(self, with_dash_char=True):
        img = Image.new("RGBA", (400, 200), (255, 255, 255, 255))
        d = ImageDraw.Draw(img)
        d.rectangle([180, 40, 190, 160], fill=(30, 30, 30, 255))  # colorbar
        f = _font(30)
        # tick line from the bar toward the label (~4 px gap to the "6")
        d.line([(191, 100), (206, 100)], fill=(30, 30, 30, 255), width=3)
        d.text((214, 84), "6.5", font=f, fill=(0, 0, 0, 255))
        ink = _ink_bbox(img)
        # detection box starts at the tick and covers tick + digits
        x0, y0 = 191, ink[1] - 2
        x1, y1 = ink[2] + 2, ink[3] + 2
        chars = []
        if with_dash_char:
            chars = [["-", 191, 98, 16, 5]]
            for ch, (cx0, cx1) in zip("6.5", ((214, 231), (232, 239), (240, 257))):
                chars.append([ch, cx0, 86, cx1 - cx0, 30])
        return img, DetectedText(x0, y0, x1 - x0, y1 - y0, text="-6.5",
                                 chars=chars, angle=0.0)

    def test_trim_with_chars(self):
        img, det = self._make_tick(with_dash_char=True)
        (region, reason), = [(r, rs) for r, rs in regions_from_detections(img, [det])]
        self.assertIsNone(reason)
        self.assertEqual(region.text, "6.5")
        self.assertGreater(region.x, 206)   # box starts past the tick

    def test_trim_geometric(self):
        img, det = self._make_tick(with_dash_char=False)
        (region, reason), = [(r, rs) for r, rs in regions_from_detections(img, [det])]
        self.assertIsNone(reason)
        self.assertEqual(region.text, "6.5")
        self.assertGreater(region.x, 206)

    def test_real_minus_untouched(self):
        img = Image.new("RGBA", (300, 120), (255, 255, 255, 255))
        ImageDraw.Draw(img).text((60, 40), "-5", font=_font(30), fill=(0, 0, 0, 255))
        x0, y0, x1, y1 = _ink_bbox(img)
        det = DetectedText(x0 - 3, y0 - 3, x1 - x0 + 6, y1 - y0 + 6,
                           text="-5", chars=[], angle=0.0)
        (region, reason), = [(r, rs) for r, rs in regions_from_detections(img, [det])]
        self.assertIsNone(reason)
        self.assertEqual(region.text, "-5")


class TestInkRatio(unittest.TestCase):
    def test_micro_descender(self):
        self.assertAlmostEqual(ink_ratio_for_text("0.0 µm"),
                               CAP_HEIGHT_RATIO + DESCENDER_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text("0.0 μm"),
                               CAP_HEIGHT_RATIO + DESCENDER_RATIO)


class TestSchema8(unittest.TestCase):
    def test_version(self):
        self.assertEqual(PROJECT_SCHEMA_VERSION, 8)

    def _project(self, regions):
        return {"schema_version": 7, "typography_mode": "legacy",
                "cells": [{"raster_text_regions": regions}]}

    def test_migration_adds_angle(self):
        data = self._project([{"x": 1, "y": 2, "w": 3, "h": 4, "text": "a"}])
        out = migrate_project_data(data)
        self.assertEqual(out["schema_version"], 8)
        self.assertEqual(out["cells"][0]["raster_text_regions"][0]["angle"], 0.0)

    def test_invalid_angles(self):
        for bad in (120, "a", float("nan"), True, -90, 90.5):
            data = self._project([{"x": 1, "y": 2, "w": 3, "h": 4, "angle": bad}])
            with self.assertRaises(ProjectMigrationError, msg=f"angle={bad}"):
                migrate_project_data(data)

    def test_region_roundtrip(self):
        r = RasterTextRegion(x=-5, y=-900, w=200, h=40, text="x", angle=-34.57)
        r2 = RasterTextRegion.from_dict(r.to_dict())
        self.assertEqual(r2.angle, -34.57)
        self.assertEqual(RasterTextRegion.from_dict({"x": 1}).angle, 0.0)


class TestSpecAngle(unittest.TestCase):
    def test_angle_only_when_rotated(self):
        from src.model.data_model import Cell, Project, SvgTextGroup
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "p.png")
            Image.new("RGB", (200, 100), (255, 255, 255)).save(path)
            project = Project()
            project.svg_text_groups = [
                SvgTextGroup(id="g1", name="G", font_size_pt=12.0)]
            cell = Cell(image_path=path)
            cell.raster_text_regions = [
                RasterTextRegion(id="flat", x=10, y=10, w=50, h=20,
                                 font_size_px=20.0, group_id="g1", enabled=True),
                RasterTextRegion(id="rot", x=-300, y=100, w=80, h=20,
                                 font_size_px=20.0, group_id="g1", enabled=True,
                                 angle=-35.0),
            ]
            spec = build_raster_override_spec(project, cell,
                                              content_size_mm=(50.0, 25.0))
            by_id = {e["id"]: e for e in spec["regions"]}
            self.assertNotIn("angle", by_id["flat"])
            self.assertEqual(by_id["rot"]["angle"], -35.0)


if __name__ == "__main__":
    unittest.main()
