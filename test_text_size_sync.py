"""One text group must render at the same size in SVG and raster panels.

The group size is defined as points in the final figure, so these tests
measure the composed page rather than trusting intermediate numbers.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from pathlib import Path
import tempfile
import unittest

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtWidgets import QApplication

from src.export.image_exporter import ImageExporter
from src.model.data_model import (
    Cell, Project, RasterTextRegion, RowTemplate, SvgTextGroup, SvgTextMember,
)
from src.model.layout_engine import LayoutEngine
from src.utils.raster_text_utils import (
    ASCENDER_RATIO, CAP_HEIGHT_RATIO, CJK_RATIO, DESCENDER_RATIO,
    X_HEIGHT_RATIO, analyze_region, ink_ratio_for_text,
)
from src.utils.svg_text_utils import get_svg_override_bytes_for_cell, svg_mm_per_unit

FONT = os.path.join(os.environ.get('WINDIR', 'C:\\Windows'), 'Fonts', 'arial.ttf')
VIEW_W, VIEW_H = 720, 480


def _chart_svg(font_px, label='Time'):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{VIEW_W}" height="{VIEW_H}" '
            f'viewBox="0 0 {VIEW_W} {VIEW_H}"><rect width="{VIEW_W}" height="{VIEW_H}" fill="white"/>'
            f'<path d="M100 110 V370 H630" stroke="#444" fill="none" stroke-width="3"/>'
            f'<g font-family="Arial" fill="#222" font-size="{font_px}">'
            f'<text id="axis" x="300" y="430">{label}</text></g></svg>')


class InkRatioTests(unittest.TestCase):
    def test_ratio_follows_the_characters_present(self):
        self.assertAlmostEqual(ink_ratio_for_text('HH'), CAP_HEIGHT_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text('Time'), ASCENDER_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text('concentration'), ASCENDER_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text('sumac'), X_HEIGHT_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text('Response'), CAP_HEIGHT_RATIO + DESCENDER_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text('Time (s)'), ASCENDER_RATIO + DESCENDER_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text('时间'), CJK_RATIO)
        self.assertAlmostEqual(ink_ratio_for_text('时间 (s)'), CJK_RATIO)
        for unknown in ('', '   ', None, '—', '···'):
            self.assertAlmostEqual(ink_ratio_for_text(unknown), CAP_HEIGHT_RATIO)

    def test_estimate_recovers_the_true_em_for_varied_strings(self):
        if not os.path.isfile(FONT):
            self.skipTest('Arial not available')
        em = 200
        font = ImageFont.truetype(FONT, em)
        for text in ('HH', 'Time', 'Response', 'sumac', 'Time (s)', 'gjpqy'):
            with self.subTest(text=text):
                image = Image.new('RGB', (2600, 700), 'white')
                ImageDraw.Draw(image).text((60, 500), text, font=font, fill='black', anchor='ls')
                arr = np.asarray(image)
                info = analyze_region(arr, 0, 0, arr.shape[1], arr.shape[0])
                _gx, _gy, _gw, gh = info['glyph_box']
                estimate = gh / ink_ratio_for_text(text)
                self.assertLess(abs(estimate / em - 1), 0.05,
                                f'{text!r}: estimated {estimate:.1f} px for a {em} px em')


class GroupRenderSizeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        QFontDatabase.addApplicationFont(FONT)

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def _raster_panel(self, name, font_px, scale, label='Time'):
        path = self.root / name
        image = Image.new('RGB', (VIEW_W * scale, VIEW_H * scale), 'white')
        draw = ImageDraw.Draw(image)
        draw.line([(100 * scale, 370 * scale), (630 * scale, 370 * scale)],
                  fill='#444', width=3 * scale)
        font = ImageFont.truetype(FONT, font_px * scale)
        draw.text((300 * scale, 430 * scale), label, font=font, fill='#222', anchor='ls')
        image.save(path)
        cell = Cell(row_index=0, col_index=0, image_path=str(path))
        cell._probe_scale = scale
        return cell

    def _assign_region(self, project, cell, label):
        arr = np.asarray(Image.open(cell.image_path).convert('RGB'))
        scale = cell._probe_scale
        info = analyze_region(arr, 280 * scale, 395 * scale, 130 * scale, 45 * scale)
        gx, gy, gw, gh = info['glyph_box']
        cell.raster_text_regions.append(RasterTextRegion(
            x=gx - 4, y=gy - 4, w=gw + 8, h=gh + 8, text=label,
            font_size_px=round(gh / ink_ratio_for_text(label), 2),
            group_id=project.svg_text_groups[0].id, enabled=True, background=info['bg']))

    def _build(self, target_pt, svg_font_px=20, raster_font_px=26, raster_scale=2):
        svg_path = self.root / 'panel.svg'
        svg_path.write_text(_chart_svg(svg_font_px), encoding='utf-8')

        project = Project(page_width_mm=180, page_height_mm=72, margin_left_mm=6, margin_right_mm=6,
                          margin_top_mm=6, margin_bottom_mm=6, gap_mm=4, dpi=600)
        project.rows = [RowTemplate(index=0, column_count=2)]
        raster_cell = self._raster_panel('panel.png', raster_font_px, raster_scale)
        raster_cell.col_index = 1
        project.cells = [Cell(row_index=0, col_index=0, image_path=str(svg_path)), raster_cell]
        group = SvgTextGroup(name='Axis', font_size_pt=target_pt,
                             members=[SvgTextMember(str(svg_path), 'axis')])
        project.svg_text_groups.append(group)
        self._assign_region(project, raster_cell, 'Time')
        return project

    def _cap_heights_mm(self, project):
        layout = LayoutEngine.calculate_layout(project)
        output = self.root / 'page.png'
        ImageExporter.export(project, str(output), format='PNG')
        page = np.asarray(Image.open(output).convert('L')) < 128
        scale = project.dpi / 25.4
        heights = []
        for cell in project.cells:
            x_mm, y_mm, w_mm, h_mm = layout.cell_rects[cell.id]
            panel = page[int(y_mm * scale):int((y_mm + h_mm) * scale),
                         int(x_mm * scale):int((x_mm + w_mm) * scale)]
            axis = np.nonzero(panel.sum(axis=1) > panel.shape[1] * 0.4)[0]
            self.assertTrue(len(axis), 'axis line not found; panel did not render')
            band = panel[axis[-1] + 3:, int(panel.shape[1] * 0.25):int(panel.shape[1] * 0.75)]
            rows = np.nonzero(band.any(axis=1))[0]
            self.assertTrue(len(rows), 'label ink not found')
            heights.append((rows[-1] - rows[0] + 1) / scale)
        return heights

    def test_svg_and_raster_panels_land_close_to_the_target(self):
        """End-to-end check.

        A few percent of residual is expected and not a code defect: the
        raster side can only infer the em from pixels, and the vector
        renderer's glyph metrics need not match the rasteriser that produced
        the source image. Before the unit/character fixes this gap was 25-30%
        for common labels, so the bound here is what the pipeline can honestly
        promise.
        """
        for target_pt in (7.0, 9.0, 12.0):
            with self.subTest(target_pt=target_pt):
                project = self._build(target_pt)
                svg_mm, raster_mm = self._cap_heights_mm(project)
                # 'Time' has no descender, so its ink height is the ascender.
                expected_mm = target_pt * 25.4 / 72 * ASCENDER_RATIO
                self.assertLess(abs(svg_mm / raster_mm - 1), 0.08,
                                f'svg {svg_mm:.3f} mm vs raster {raster_mm:.3f} mm')
                for measured, name in ((svg_mm, 'svg'), (raster_mm, 'raster')):
                    self.assertLess(abs(measured / expected_mm - 1), 0.08,
                                    f'{name} {measured:.3f} mm, expected ~{expected_mm:.3f} mm')

    def test_raster_panels_converge_regardless_of_source_resolution(self):
        """Two raster panels share one rasteriser, so the pipeline alone
        decides the result — this is the tight, deterministic guarantee."""
        project = self._build(9.0, raster_font_px=26, raster_scale=2)
        second = self._raster_panel('panel-b.png', font_px=11, scale=4)
        second.col_index = 2
        project.rows[0].column_count = 3
        project.cells.append(second)
        self._assign_region(project, second, 'Time')
        heights = self._cap_heights_mm(project)
        raster_a, raster_b = heights[1], heights[2]
        self.assertLess(abs(raster_a / raster_b - 1), 0.03,
                        f'{raster_a:.3f} mm vs {raster_b:.3f} mm')

    def test_group_size_is_written_in_user_units_not_points(self):
        project = self._build(9.0)
        cell = project.cells[0]
        data = get_svg_override_bytes_for_cell(project, cell)
        self.assertIsNotNone(data)
        text = data.decode('utf-8')
        self.assertIn('font-size:', text)
        self.assertNotIn('pt', text.split('font-size:')[1][:24])
        mm_per_unit = svg_mm_per_unit(project, cell, _chart_svg(20).encode('utf-8'))
        written = float(text.split('font-size:')[1].split('px')[0])
        self.assertAlmostEqual(written * mm_per_unit, 9.0 * 25.4 / 72, places=3)

    def test_both_pipelines_target_the_same_em_on_the_page(self):
        """The contract is the em size on the page, which both pipelines can
        hit exactly. (Glyph *ink* within that em is up to the rasteriser:
        QtSvg hints vector text, so its ink runs a few percent shorter.)"""
        from src.utils.panel_scale import panel_mm_per_unit
        from src.utils.raster_text_utils import build_raster_override_spec

        for target_pt, svg_font_px, raster_font_px, raster_scale in (
                (9.0, 20, 26, 2), (7.0, 40, 14, 3), (12.0, 12, 40, 1)):
            with self.subTest(target_pt=target_pt, raster_scale=raster_scale):
                project = self._build(target_pt, svg_font_px, raster_font_px, raster_scale)
                layout = LayoutEngine.calculate_layout(project)
                target_mm = target_pt * 25.4 / 72

                svg_cell = project.cells[0]
                data = get_svg_override_bytes_for_cell(project, svg_cell, layout)
                written = float(data.decode('utf-8').split('font-size:')[1].split('px')[0])
                mm_per_unit = svg_mm_per_unit(
                    project, svg_cell, _chart_svg(svg_font_px).encode('utf-8'), layout)
                self.assertAlmostEqual(written * mm_per_unit, target_mm, places=3)

                raster_cell = project.cells[1]
                spec = build_raster_override_spec(project, raster_cell, layout)
                entry = spec['regions'][0]
                region = raster_cell.raster_text_regions[0]
                with Image.open(raster_cell.image_path) as image:
                    mm_per_px = panel_mm_per_unit(
                        project, raster_cell, image.width, image.height, layout)
                rendered_mm = region.font_size_px * entry['scale'] * mm_per_px
                self.assertAlmostEqual(rendered_mm, target_mm, places=2)


if __name__ == '__main__':
    unittest.main()
