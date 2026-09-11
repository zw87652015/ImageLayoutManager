import os
import re
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtWidgets import QApplication
from src.model.data_model import Cell, Project, SvgTextGroup, SvgTextMember
from src.utils.svg_text_utils import get_svg_override_bytes_for_cell


class SvgTextGroupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        from PyQt6.QtGui import QFontDatabase
        if not QFontDatabase.families() and os.name == 'nt':
            QFontDatabase.addApplicationFont(str(Path(os.environ['WINDIR']) / 'Fonts' / 'arial.ttf'))

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'panel.svg'
        self.source = ('<svg xmlns="http://www.w3.org/2000/svg" width="200" height="100" '
                       'viewBox="0 0 400 200"><g transform="scale(2)">'
                       '<text id="label" x="20" y="40" font-size="12">'
                       '<tspan style="font-size:6pt">Panel</tspan></text></g>'
                       '<text id="untouched" x="10" y="90" font-size="7">Other</text></svg>')
        self.path.write_text(self.source, encoding='utf-8')
        self.cells = [Cell(image_path=str(self.path), freeform_w_mm=w,
                           freeform_h_mm=w / 2, padding_top=0, padding_right=0,
                           padding_bottom=0, padding_left=0) for w in (50.0, 100.0)]
        self.group = SvgTextGroup(font_size_pt=12, members=[
            SvgTextMember(svg_path=str(self.path), element_key='label')])
        self.project = Project(layout_mode='freeform', cells=self.cells,
                               svg_text_groups=[self.group])

    def font_size(self, root, tag):
        elem = root.find('.//{http://www.w3.org/2000/svg}' + tag)
        return float(re.search(r'font-size:([\d.e+-]+)pt', elem.get('style', '')).group(1))

    def test_group_size_is_in_final_figure_points(self):
        for cell in self.cells:
            with self.subTest(width=cell.freeform_w_mm):
                root = ET.fromstring(get_svg_override_bytes_for_cell(self.project, cell))
                size = self.font_size(root, 'text')
                final_points = size * (96 / 72) * 2 * (cell.freeform_w_mm / 400) * (72 / 25.4)
                self.assertAlmostEqual(final_points, 12, places=4)
                self.assertAlmostEqual(self.font_size(root, 'tspan'), size)
                untouched = root.find('.//*[@id="untouched"]')
                self.assertEqual(untouched.get('font-size'), '7')
                self.assertIsNone(untouched.get('style'))
        self.assertEqual(self.path.read_text(encoding='utf-8'), self.source)

    def test_group_overrides_normalized_tspans(self):
        self.cells[0].svg_normalize_text = True
        root = ET.fromstring(get_svg_override_bytes_for_cell(self.project, self.cells[0]))
        self.assertAlmostEqual(self.font_size(root, 'text'), self.font_size(root, 'tspan'))

    def test_pdf_exports_group_at_same_physical_size(self):
        import fitz
        from src.export.pdf_exporter import PdfExporter
        self.cells[1].freeform_x_mm = 70
        for dpi in (96, 300):
            with self.subTest(dpi=dpi):
                self.project.dpi = dpi
                output = str(Path(self.temp.name) / f'figure-{dpi}.pdf')
                PdfExporter.export(self.project, output)
                with fitz.open(output) as doc:
                    spans = [span for block in doc[0].get_text('dict')['blocks']
                             for line in block.get('lines', []) for span in line['spans']
                             if span['text'] == 'Panel']
                    self.assertEqual(len(spans), 2, doc[0].get_text('dict'))
                    for span in spans:
                        self.assertAlmostEqual(span['size'], 12, delta=0.15)

    def test_grid_crop_rotation_and_cover_scale(self):
        from src.model.layout_engine import LayoutResult
        cell = self.cells[0]
        self.project.layout_mode = 'grid'
        cell.padding_left = cell.padding_right = 5
        cell.padding_top = cell.padding_bottom = 2.5
        cell.crop_right = 0.5
        cell.rotation = 90
        layout = LayoutResult(cell_rects={cell.id: (0, 0, 60, 105)}, row_heights={})
        for mode, ratio in [('contain', 0.5), ('cover', 1.0)]:
            cell.fit_mode = mode
            root = ET.fromstring(get_svg_override_bytes_for_cell(self.project, cell, layout))
            final_points = self.font_size(root, 'text') * (96 / 72) * 2 * 0.5 * ratio * (72 / 25.4)
            self.assertAlmostEqual(final_points, 12)

    def test_distinct_files_share_group_and_survive_roundtrip(self):
        other = Path(self.temp.name) / 'other.svg'
        other.write_text(self.source, encoding='utf-8')
        self.cells[1].image_path = str(other)
        self.group.members.append(SvgTextMember(svg_path=str(other), element_key='label'))
        self.project = Project.from_dict(self.project.to_dict())
        self.project.svg_text_groups[0].font_size_pt = 9
        for cell in self.project.cells:
            root = ET.fromstring(get_svg_override_bytes_for_cell(self.project, cell))
            final_points = self.font_size(root, 'text') * (96 / 72) * 2 * (cell.freeform_w_mm / 400) * (72 / 25.4)
            self.assertAlmostEqual(final_points, 9)

    def test_thumbnail_variants_and_stale_completion(self):
        from unittest.mock import patch
        from PyQt6.QtGui import QImage
        from src.utils.image_proxy import ImageProxy
        proxy = ImageProxy(max_cache_items=2)
        proxy._thread_pool = type('Pool', (), {'start': lambda self, worker: None})()
        path = str(self.path)
        callbacks = []
        for content in (b'first', b'second'):
            proxy.get_pixmap(path, callbacks.append, content)
        self.assertEqual(len(proxy._loading), 2)
        old_tokens = dict(proxy._request_tokens)
        proxy.invalidate(path)
        proxy.get_pixmap(path, callbacks.append, b'first')
        image = QImage(10, 10, QImage.Format.Format_ARGB32)
        for key, token in old_tokens.items():
            proxy._on_thumbnail_finished(path, image, key, token)
        self.assertEqual(len(proxy._cache), 0)
        self.assertEqual(callbacks, [])
        key, token = next(iter(proxy._request_tokens.items()))
        proxy._on_thumbnail_finished(path, image, key, token)
        self.assertEqual(callbacks, [path])
        self.assertIsNotNone(proxy.get_pixmap(path, svg_override_bytes=b'first'))
        self.assertIsNone(proxy.get_pixmap(path, svg_override_bytes=b'second'))

    def test_canvas_refresh_detects_group_changes_and_removal(self):
        from src.canvas.canvas_scene import CanvasScene
        from src.utils.image_proxy import get_image_proxy
        scene = CanvasScene()
        self.addCleanup(get_image_proxy().shutdown)
        scene.set_project(self.project)
        before = dict(scene._cell_data_cache)
        self.group.font_size_pt = 18
        scene.refresh_layout()
        for cell in self.cells:
            self.assertNotEqual(before[cell.id], scene._cell_data_cache[cell.id])
        before = dict(scene._cell_data_cache)
        self.project.svg_text_groups.clear()
        scene.refresh_layout()
        for cell in self.cells:
            self.assertNotEqual(before[cell.id], scene._cell_data_cache[cell.id])


if __name__ == '__main__':
    unittest.main()
