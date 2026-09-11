import os
import tempfile
import unittest
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from PyQt6.QtWidgets import QApplication

from src.model.data_model import Cell, Project, RasterTextRegion, SvgTextGroup
from src.utils.raster_text_ocr import DetectedText, RapidOcrBackend
from src.utils.raster_text_utils import (
    apply_raster_text_overrides, build_raster_override_spec, regions_from_detections,
    load_raster_with_overrides, analyze_region,
)


def glyph_bbox(arr, box, threshold=40):
    x, y, w, h = box
    crop = arr[y:y + h, x:x + w, :3]
    ys, xs = np.nonzero(np.max(np.abs(crop.astype(int) - 255), axis=2) > threshold)
    return xs.min(), ys.min(), xs.max() - xs.min() + 1, ys.max() - ys.min() + 1


class RasterTextTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'panel.png'
        img = Image.new('RGB', (600, 400), 'white')
        d = ImageDraw.Draw(img)
        font = ImageFont.truetype(str(Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts' / 'arial.ttf'), 28)
        d.text((40, 40), 'TIME', font=font, fill='black')
        d.text((300, 300), 'AXIS', font=font, fill=(200, 0, 0))
        d.line((280, 318, 480, 318), fill='black', width=2)   # crosses straight through the AXIS box
        d.text((40, 330), 'TICK', font=font, fill='black')
        d.line((20, 320, 200, 320), fill='black', width=3)    # axis line 6 px ABOVE the TICK box: outside it
        d.rectangle((26, 326, 31, 370), fill='black')          # tick mark 2 px left of the box, still outside
        img.save(self.path)
        self.original = self.path.read_bytes()
        self.detections = [DetectedText(40, 40, 90, 32, 'TIME', 0.99),
                           DetectedText(300, 300, 80, 32, 'AXIS', 0.99),
                           DetectedText(37, 330, 94, 32, 'TICK', 0.99)]

    def make_project(self, region, width_mm):
        cell = Cell(image_path=str(self.path), freeform_w_mm=width_mm, freeform_h_mm=width_mm * 400 / 600,
                    raster_text_regions=[region])
        group = SvgTextGroup(font_size_pt=8)
        region.group_id = group.id
        return Project(layout_mode='freeform', cells=[cell], svg_text_groups=[group]), cell

    def test_detections_become_regions_with_safety_check(self):
        with Image.open(self.path) as im:
            results = regions_from_detections(im, self.detections)
        (time_region, time_reason), (axis_region, axis_reason), (tick_region, tick_reason) = results
        self.assertIsNone(time_reason)
        self.assertTrue(time_region.enabled)
        self.assertAlmostEqual(time_region.font_size_px, 20 / 0.72, delta=2)  # cap height of 28px Arial ~ 20px
        self.assertEqual(time_region.background, '#ffffff')
        # A line cutting through the box is a genuine hazard -> flagged, but still a usable region.
        self.assertEqual(axis_reason, 'touching')
        self.assertEqual(axis_region.warning, 'touching')
        self.assertFalse(axis_region.enabled)
        # Content right next to (but outside) the box must NOT flag it: only the box interior counts.
        self.assertIsNone(tick_reason, 'clean box flagged because of content outside it')
        self.assertTrue(tick_region.enabled)
        self.assertEqual(tick_region.background, '#ffffff')

    def test_noise_does_not_flag_clean_box(self):
        from src.utils.raster_text_utils import analyze_region
        rng = np.random.default_rng(0)
        arr = np.full((120, 300, 3), 255, np.uint8)
        arr[40:60, 60:200] = 0                                  # a solid "glyph" bar
        noise = rng.integers(-25, 26, arr.shape, dtype=np.int16)  # JPEG-like speckle everywhere
        arr = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
        arr[5, 5] = 0                                           # one stray black pixel in the corner
        self.assertIsNone(analyze_region(arr, 0, 0, 300, 120)['reason'])

    def test_gradient_background_is_flagged(self):
        from src.utils.raster_text_utils import analyze_region
        arr = np.zeros((100, 300, 3), np.uint8)
        arr[:] = np.linspace(150, 255, 300, dtype=np.uint8)[None, :, None]
        arr[40:60, 100:200] = 0
        self.assertEqual(analyze_region(arr, 0, 0, 300, 100)['reason'], 'background')

    def test_flagged_region_can_still_be_enabled_and_applied(self):
        with Image.open(self.path) as im:
            (_, _), (axis_region, _), (_, _) = regions_from_detections(im, self.detections)
            img = im.convert('RGBA')
        axis_region.enabled = True
        spec = {"regions": [{"id": axis_region.id, "x": axis_region.x, "y": axis_region.y, "w": axis_region.w,
                             "h": axis_region.h, "scale": 0.8, "anchor": "center",
                             "background": axis_region.background}]}
        _processed, report = apply_raster_text_overrides(img, spec)
        self.assertEqual(report[0]['status'], 'applied')

    def test_scale_matches_group_size_in_final_points(self):
        with Image.open(self.path) as im:
            region, _ = regions_from_detections(im, self.detections[:1])[0]
        for width_mm in (60, 120):
            project, cell = self.make_project(region, width_mm)
            spec = build_raster_override_spec(project, cell)
            current_pt = region.font_size_px * (width_mm / 600) * 72 / 25.4
            self.assertAlmostEqual(spec['regions'][0]['scale'], 8 / current_pt, places=4)

    def test_apply_resizes_glyphs_and_keeps_file(self):
        with Image.open(self.path) as im:
            region, _ = regions_from_detections(im, self.detections[:1])[0]
            arr = np.asarray(im.convert('RGB'))
        before = glyph_bbox(arr, (0, 0, 300, 200))
        for scale in (0.5, 1.6):
            spec = {"regions": [{"id": region.id, "x": region.x, "y": region.y, "w": region.w, "h": region.h,
                                 "scale": scale, "anchor": "left", "background": region.background}]}
            processed = load_raster_with_overrides(str(self.path), spec)
            after = glyph_bbox(np.asarray(processed), (0, 0, 300, 200))
            self.assertAlmostEqual(after[2], before[2] * scale, delta=2)
            self.assertAlmostEqual(after[3], before[3] * scale, delta=2)
            self.assertEqual(after[0], before[0])  # left anchor keeps the left edge
        self.assertEqual(self.path.read_bytes(), self.original)

    def test_collision_is_skipped_and_reported(self):
        with Image.open(self.path) as im:
            region, _ = regions_from_detections(im, self.detections[:1])[0]
            img = im.convert('RGBA')
        spec = {"regions": [{"id": region.id, "x": region.x, "y": region.y, "w": region.w, "h": region.h,
                             "scale": 6.0, "anchor": "center", "background": region.background}]}
        processed, report = apply_raster_text_overrides(img, spec)
        self.assertIn(report[0]['status'], ('skipped_collision', 'skipped_bounds'))
        self.assertTrue(np.array_equal(np.asarray(processed), np.asarray(img)))

    def test_regions_roundtrip_in_project_file(self):
        region = RasterTextRegion(x=1, y=2, w=3, h=4, text='a', font_size_px=5.5, group_id='g', vertical=True)
        project, cell = self.make_project(region, 60)
        loaded = Project.from_dict(project.to_dict())
        self.assertEqual(loaded.cells[0].raster_text_regions[0].to_dict(), region.to_dict())

    def test_export_matches_physical_size_across_panels(self):
        from src.export.image_exporter import ImageExporter
        with Image.open(self.path) as im:
            region, _ = regions_from_detections(im, self.detections[:1])[0]
        group = SvgTextGroup(font_size_pt=10)
        cells = []
        for i, width_mm in enumerate((60.0, 120.0)):
            r = RasterTextRegion(**{**region.to_dict(), 'id': f'r{i}', 'group_id': group.id, 'anchor': 'left'})
            cells.append(Cell(image_path=str(self.path), freeform_x_mm=10 + i * 70, freeform_y_mm=10,
                              freeform_w_mm=width_mm, freeform_h_mm=width_mm * 400 / 600, raster_text_regions=[r]))
        project = Project(layout_mode='freeform', cells=cells, svg_text_groups=[group], dpi=300,
                          page_width_mm=210, page_height_mm=120)
        qimg = ImageExporter.render_to_qimage(project)
        ptr = qimg.bits(); ptr.setsize(qimg.sizeInBytes())
        arr = np.frombuffer(bytes(ptr), np.uint8).reshape(qimg.height(), qimg.width(), 4)[..., :3][..., ::-1]
        scale = 300 / 25.4
        heights_mm = []
        for cell in cells:
            x0, y0 = int(cell.freeform_x_mm * scale), int(cell.freeform_y_mm * scale)
            w, h = int(cell.freeform_w_mm * scale), int(cell.freeform_h_mm * scale)
            # TIME sits in the top-left quarter of the panel
            box = (x0, y0, w // 2, h // 2)
            # Measure the glyph core (near-black) so resampling halos do not
            # inflate the bbox of the panel drawn at the coarser mm/px.
            heights_mm.append(glyph_bbox(arr, box, threshold=200)[3] / scale)
        cap_height_mm = 10 * 0.72 * 25.4 / 72
        self.assertAlmostEqual(heights_mm[0], heights_mm[1], delta=0.2)
        for hmm in heights_mm:
            self.assertAlmostEqual(hmm, cap_height_mm, delta=0.3)

    def test_canvas_fingerprint_tracks_raster_regions(self):
        from src.canvas.canvas_scene import CanvasScene
        from src.utils.image_proxy import get_image_proxy
        with Image.open(self.path) as im:
            region, _ = regions_from_detections(im, self.detections[:1])[0]
        project, cell = self.make_project(region, 60)
        scene = CanvasScene()

        def _teardown():
            get_image_proxy().shutdown()
            scene.clear()
            self.app.processEvents()
        self.addCleanup(_teardown)
        scene.set_project(project)
        before = scene._cell_data_cache[cell.id]
        project.svg_text_groups[0].font_size_pt = 14
        scene.refresh_layout()
        self.assertNotEqual(before, scene._cell_data_cache[cell.id])

    def test_mixed_case_label_not_flagged_by_its_own_baseline(self):
        # A label mixing capitals/ascenders with plain lowercase (varying
        # glyph heights) whose tight bounding box is flush against the ink
        # on some side — the label's own baseline/apex touching the box
        # edge must never look like "something else is in the box".
        font = ImageFont.truetype(str(Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'), 28)
        img = Image.new('RGB', (300, 100), 'white')
        ImageDraw.Draw(img).text((20, 20), 'Area (mm)', font=font, fill='black')
        arr = np.asarray(img)
        ys, xs = np.nonzero(np.max(np.abs(arr.astype(int) - 255), axis=2) > 40)
        x0, y0 = int(xs.min()), int(ys.min())
        w, h = int(xs.max() - x0 + 1), int(ys.max() - y0 + 1)
        for pad in (0, 1, 2, 3):        # 0 = box flush with the ink, no room to breathe
            with self.subTest(pad=pad):
                info = analyze_region(arr, x0 - pad, y0 - pad, w + 2 * pad, h + 2 * pad)
                self.assertIsNone(info['reason'])

    def test_foreign_content_in_height_gap_is_excluded_not_destroyed(self):
        # A box's height follows its tallest letters, so a line mixing
        # capitals with plain lowercase opens dead space above the short
        # ones. A diagram pointer sitting in exactly that gap — clean
        # background around it, not touching any glyph or any box edge —
        # must be classified as foreign and left untouched, not swept into
        # the extracted "text" layer and dragged along when resizing.
        font = ImageFont.truetype(str(Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'), 36)
        img = Image.new('RGB', (500, 250), 'white')
        d = ImageDraw.Draw(img)
        d.text((120, 100), 'AAAaaaa', font=font, fill='black')
        arr = np.asarray(img)
        ys, xs = np.nonzero(np.max(np.abs(arr.astype(int) - 255), axis=2) > 40)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1

        img2 = img.copy()
        gx0 = x0 + 85   # squarely above the lowercase run, 2px+ clear of any glyph
        ImageDraw.Draw(img2).polygon(
            [(gx0, y0 + 1), (gx0 + 8, y0 + 1), (gx0 + 4, y0 + 4)], fill=(200, 0, 0))
        arr2 = np.asarray(img2)
        box = (x0 - 2, y0 - 2, (x1 - x0) + 4, (y1 - y0) + 4)

        info = analyze_region(arr2, *box)
        self.assertIsNone(info['reason'])
        self.assertTrue(info['foreign_excluded'])

        spec = {"regions": [{"id": "r1", "x": box[0], "y": box[1], "w": box[2], "h": box[3],
                             "scale": 1.3, "anchor": "left", "background": info['bg']}]}
        processed, report = apply_raster_text_overrides(Image.fromarray(arr2).convert('RGBA'), spec)
        self.assertEqual(report[0]['status'], 'applied')
        out = np.asarray(processed.convert('RGB'))
        region = out[box[1]:box[1] + box[3], box[0]:box[0] + box[2]]
        red = ((region[..., 0].astype(int) - 200) ** 2 + region[..., 1].astype(int) ** 2
              + region[..., 2].astype(int) ** 2 < 3000)
        self.assertEqual(int(red.sum()), 20, 'the pointer must survive untouched at its original spot')

    def test_hyphen_and_i_dots_are_text_with_ocr_chars(self):
        # A "-" sits mid-height and an i-dot floats above the stem: neither
        # reaches the baseline, so geometry alone can't prove they're text.
        # With OCR per-character boxes as the judge, both must be kept.
        from src.utils.raster_text_utils import _dominant_color, _alpha, _distance, _classify_text_pixels
        font = ImageFont.truetype(str(Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'), 30)
        img = Image.new('RGB', (500, 100), 'white')
        ImageDraw.Draw(img).text((40, 30), 'BTO-np in', font=font, fill='black')
        arr = np.asarray(img)
        ys, xs = np.nonzero(np.max(np.abs(arr.astype(int) - 255), axis=2) > 40)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        box = (x0 - 2, y0 - 2, (x1 - x0) + 4, (y1 - y0) + 4)
        crop = arr[box[1]:box[1] + box[3], box[0]:box[0] + box[2], :3]
        alpha = _alpha(_distance(crop, _dominant_color(crop)[0]))
        # Synthetic per-character columns (what RapidOCR's word boxes give):
        # split the ink extent evenly across the 9 characters incl. the space.
        text = 'BTO-np in'
        step = (x1 - x0) / len(text)
        chars = [[ch, int(x0 + i * step), y0, int(step) + 1, y1 - y0] for i, ch in enumerate(text)]
        _ta, foreign, _tight = _classify_text_pixels(alpha, chars=chars, origin=(box[0], box[1]))
        self.assertEqual(int(foreign.sum()), 0, 'hyphen / i-dot wrongly excluded despite OCR chars')
        # Geometric fallback (no chars) must keep them too: the hyphen is in
        # the x-height band, the dot is small and centred over its stem.
        _ta, foreign2, _tight = _classify_text_pixels(alpha)
        self.assertEqual(int(foreign2.sum()), 0, 'hyphen / i-dot wrongly excluded by geometric fallback')

    def test_pointer_under_plain_letter_is_foreign_with_ocr_chars(self):
        from src.utils.raster_text_utils import _dominant_color, _alpha, _distance, _classify_text_pixels
        font = ImageFont.truetype(str(Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'), 36)
        img = Image.new('RGB', (500, 250), 'white')
        d = ImageDraw.Draw(img)
        d.text((120, 100), 'AAAaaaa', font=font, fill='black')
        arr0 = np.asarray(img)
        ys, xs = np.nonzero(np.max(np.abs(arr0.astype(int) - 255), axis=2) > 40)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        gx0 = x0 + 85
        d.polygon([(gx0, y0 + 1), (gx0 + 8, y0 + 1), (gx0 + 4, y0 + 4)], fill=(200, 0, 0))
        arr = np.asarray(img)
        box = (x0 - 2, y0 - 2, (x1 - x0) + 4, (y1 - y0) + 4)
        crop = arr[box[1]:box[1] + box[3], box[0]:box[0] + box[2], :3]
        alpha = _alpha(_distance(crop, _dominant_color(crop)[0]))
        step = (x1 - x0) / 7
        chars = [[ch, int(x0 + i * step), y0, int(step) + 1, y1 - y0] for i, ch in enumerate('AAAaaaa')]
        _ta, foreign, _tight = _classify_text_pixels(alpha, chars=chars, origin=(box[0], box[1]))
        self.assertGreater(int(foreign.sum()), 0, 'pointer over a plain "a" must be foreign')
        # …but the very same blob over a hyphen column would be text.
        chars_hyphen = [[('-' if ch == 'a' else ch), cx, cy, cw, chh] for ch, cx, cy, cw, chh in chars]
        _ta, foreign_h, _tight = _classify_text_pixels(alpha, chars=chars_hyphen, origin=(box[0], box[1]))
        self.assertEqual(int(foreign_h.sum()), 0)

    def test_rapidocr_detects_labels(self):
        if RapidOcrBackend.available():
            self.skipTest('rapidocr not installed')
        with Image.open(self.path) as im:
            found = RapidOcrBackend.detect(im)
        texts = {d.text.upper() for d in found}
        self.assertTrue({'TIME', 'AXIS'} <= texts, texts)


if __name__ == '__main__':
    unittest.main()
