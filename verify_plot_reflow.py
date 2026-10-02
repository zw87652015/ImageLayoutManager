import hashlib
import math
import os
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase
from PyQt6.QtCore import QByteArray
from PyQt6.QtSvg import QSvgRenderer

_app = QApplication.instance() or QApplication(sys.argv)
for _f in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"):
    _p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", _f)
    if os.path.isfile(_p):
        QFontDatabase.addApplicationFont(_p)

from src.model.data_model import Cell, PlotAlignmentGroup, Project, RowTemplate
from src.model.layout_engine import LayoutEngine
from src.plot_editor import render
from src.plot_editor.document import (
    PlotDocument, PlotDocumentError, document_from_svg,
)
from src.plot_editor.render import render_document, render_document_fitted
from src.utils.editable_plot import (
    plot_reflows, reflow_figure_size_mm, resolve_plot_row_frames,
    store_plot_document,
)
from src.utils.plot_alignment import resolve_image_placements
from src.utils.svg_text_utils import get_svg_override_bytes_for_cell

# Captured from the pre-refactor render path for the fixed document built
# in test_render_document_bytes_unchanged.
GOLDEN_RENDER_SHA256 = (
    "470f5dbd42258557217d6a4330a5aac9c6458808c84260fa295a21eb317b17c7")


def _svg_wh_pt(svg):
    root = ET.fromstring(svg)
    strip = lambda v: float(v.rstrip("pt"))
    return strip(root.get("width")), strip(root.get("height"))


def _viewbox_aspect(svg):
    r = QSvgRenderer(QByteArray(svg))
    box = r.viewBoxF()
    return box.width() / box.height()


class FittedRenderTests(unittest.TestCase):

    def test_svg_size_attributes(self):
        doc = PlotDocument()
        for w, h in ((180.0, 40.0), (40.0, 120.0)):
            r = render_document_fitted(doc, w, h)
            sw, sh = _svg_wh_pt(r.svg)
            self.assertAlmostEqual(sw, w / 25.4 * 72.0, places=2)
            self.assertAlmostEqual(sh, h / 25.4 * 72.0, places=2)

    def test_metadata_roundtrips_original_document(self):
        doc = PlotDocument(title="T", xlabel="Abscissa", ylabel="Ordinate")
        r = render_document_fitted(doc, 137.0, 41.0)
        self.assertEqual(document_from_svg(r.svg).to_dict(), doc.to_dict())

    def test_deterministic_and_cached(self):
        doc = PlotDocument()
        a = render_document_fitted(doc, 100.0, 50.0)
        b = render_document_fitted(doc, 100.0, 50.0)
        self.assertIs(a, b)
        c = render_document_fitted(doc, 100.004, 50.0)
        self.assertEqual(c.svg, a.svg)  # 0.01 mm quantization

    def test_no_text_clipped(self):
        doc = PlotDocument(
            title="A fairly long figure title",
            xlabel="A long x axis label with units (mm)",
            ylabel="A long y axis label with units (counts)",
            font_size_pt=11.0, title_size_pt=13.0)
        r = render_document_fitted(doc, 60.0, 45.0)
        # Rebuild the same figure and verify the fitted axes leaves the
        # tight bbox inside the figure.
        import matplotlib
        from matplotlib.backends.backend_agg import FigureCanvasAgg
        with matplotlib.rc_context(render._deterministic_rc(doc)):
            fig, ax = render._build_figure(doc, 1.0, 60.0, 45.0)
            try:
                render._fit_axes(fig, ax, render.FIT_PAD_MM / 25.4 * fig.dpi)
                renderer = fig.canvas.get_renderer()
                tight = ax.get_tightbbox(renderer)
                W = fig.get_figwidth() * fig.dpi
                H = fig.get_figheight() * fig.dpi
                self.assertGreaterEqual(tight.x0, -0.1)
                self.assertGreaterEqual(tight.y0, -0.1)
                self.assertLessEqual(tight.x1, W + 0.1)
                self.assertLessEqual(tight.y1, H + 0.1)
            finally:
                fig.clear()
        self.assertIsNotNone(r.plot_area)

    def test_plot_area_follows_aspect(self):
        doc = PlotDocument()
        wide = render_document_fitted(doc, 180.0, 40.0).plot_area
        tall = render_document_fitted(doc, 40.0, 120.0).plot_area
        self.assertNotEqual(wide, tall)
        for area in (wide, tall):
            for v in area:
                self.assertGreater(v, 0.0)
                self.assertLess(v, 1.0)

    def test_tiny_size_keeps_min_axes(self):
        doc = PlotDocument()
        r = render_document_fitted(doc, 10.0, 8.0)
        self.assertTrue(r.svg)
        l, t, rr, b = r.plot_area
        self.assertGreaterEqual(rr - l, render.MIN_AXES_FRACTION - 1e-6)
        self.assertGreaterEqual(b - t, render.MIN_AXES_FRACTION - 1e-6)

    def test_invalid_sizes_rejected(self):
        doc = PlotDocument()
        for bad in (0.0, -1.0, float("inf"), float("nan"), 1000.1):
            with self.assertRaises(PlotDocumentError):
                render_document_fitted(doc, bad, 50.0)
            with self.assertRaises(PlotDocumentError):
                render_document_fitted(doc, 50.0, bad)

    def test_render_document_bytes_unchanged(self):
        doc = PlotDocument()
        doc.series[0].id = 'golden-series-id'
        digest = hashlib.sha256(render_document(doc).svg).hexdigest()
        self.assertEqual(digest, GOLDEN_RENDER_SHA256)


class ReflowPlacementTests(unittest.TestCase):

    def _project(self, tmpdir, **cell_kwargs):
        doc = PlotDocument()
        path, _rendered = store_plot_document(doc, root=tmpdir)
        p = Project(name="reflow", page_width_mm=160, page_height_mm=40,
                    margin_left_mm=5, margin_right_mm=5,
                    margin_top_mm=5, margin_bottom_mm=5)
        cell = Cell(row_index=0, col_index=0, image_path=path, **cell_kwargs)
        p.cells = [cell]
        p.rows = [RowTemplate(index=0, column_count=1)]
        return p, cell, doc

    def _clip(self, p, cell, layout):
        x, y, w, h = layout.cell_rects[cell.id]
        w -= cell.padding_left + cell.padding_right
        h -= cell.padding_top + cell.padding_bottom
        return x + cell.padding_left, y + cell.padding_top, w, h

    def test_reflow_placement_fills_clip(self):
        with tempfile.TemporaryDirectory() as td:
            p, cell, doc = self._project(td)
            self.assertTrue(plot_reflows(p, cell))
            layout = LayoutEngine.calculate_layout(p)
            res = resolve_image_placements(p, layout)
            pl = res.placements[cell.id]
            clip = self._clip(p, cell, layout)
            self.assertEqual(pl.clip_rect, clip)
            for got, want in zip(pl.rect, clip):
                self.assertAlmostEqual(got, want, delta=1e-6)

    def test_aspect_locked_keeps_fixed_aspect(self):
        with tempfile.TemporaryDirectory() as td:
            p, cell, doc = self._project(td, aspect_ratio_locked=True)
            self.assertFalse(plot_reflows(p, cell))
            layout = LayoutEngine.calculate_layout(p)
            res = resolve_image_placements(p, layout)
            pl = res.placements[cell.id]
            file_aspect = doc.width_mm / doc.height_mm
            self.assertAlmostEqual(pl.rect[2] / pl.rect[3], file_aspect,
                                   delta=5e-3)
            self.assertLessEqual(pl.rect[2], pl.clip_rect[2] + 1e-6)
            data = get_svg_override_bytes_for_cell(p, cell, layout)
            self.assertIsNotNone(data)
            self.assertAlmostEqual(_viewbox_aspect(data), file_aspect,
                                   delta=1e-3)

    def test_alignment_group_member_not_reflowing(self):
        with tempfile.TemporaryDirectory() as td:
            p, cell, doc = self._project(td)
            p.plot_alignment_groups = [PlotAlignmentGroup(
                cell_ids=[cell.id, "other-cell"], reference_id=cell.id)]
            self.assertFalse(plot_reflows(p, cell))

    def test_override_viewbox_matches_clip_aspect(self):
        with tempfile.TemporaryDirectory() as td:
            p, cell, doc = self._project(td)
            layout = LayoutEngine.calculate_layout(p)
            clip = self._clip(p, cell, layout)
            data = get_svg_override_bytes_for_cell(p, cell, layout)
            self.assertIsNotNone(data)
            self.assertAlmostEqual(_viewbox_aspect(data),
                                   clip[2] / clip[3], delta=1e-3)
            cell.rotation = 90
            data = get_svg_override_bytes_for_cell(p, cell, layout)
            self.assertIsNotNone(data)
            self.assertAlmostEqual(_viewbox_aspect(data),
                                   clip[3] / clip[2], delta=1e-3)

    def test_plain_svg_unaffected(self):
        with tempfile.TemporaryDirectory() as td:
            path = os.path.join(td, "plain.svg")
            with open(path, "w", encoding="utf-8") as fh:
                fh.write('<svg xmlns="http://www.w3.org/2000/svg" '
                         'width="100" height="50"/>')
            p = Project(name="plain", page_width_mm=160, page_height_mm=40,
                        margin_left_mm=5, margin_right_mm=5,
                        margin_top_mm=5, margin_bottom_mm=5)
            cell = Cell(row_index=0, col_index=0, image_path=path)
            p.cells = [cell]
            p.rows = [RowTemplate(index=0, column_count=1)]
            self.assertFalse(plot_reflows(p, cell))
            self.assertIsNone(get_svg_override_bytes_for_cell(p, cell))

    def test_crop_scales_figure_size(self):
        cell = Cell(crop_right=0.5)
        w, h = reflow_figure_size_mm(cell, 20.0, 10.0)
        self.assertAlmostEqual(w, 40.0)
        self.assertAlmostEqual(h, 10.0)


class RowFrameTests(unittest.TestCase):

    def _docs(self):
        plain = PlotDocument(title="A fairly long figure title")
        two_line = PlotDocument(title="", xlabel="first line\nsecond line")
        big = PlotDocument()
        big.series[0].y = [0.0, 1e5, 5e4, 2e5]
        return [plain, two_line, big]

    def _row_project(self, tmpdir, docs):
        paths = [store_plot_document(d, root=tmpdir)[0] for d in docs]
        p = Project(name="row", page_width_mm=210, page_height_mm=60,
                    margin_left_mm=5, margin_right_mm=5,
                    margin_top_mm=5, margin_bottom_mm=5)
        cells = [Cell(row_index=0, col_index=i, image_path=path)
                 for i, path in enumerate(paths)]
        p.cells = cells
        p.rows = [RowTemplate(index=0, column_count=len(cells))]
        return p, cells

    def _clip(self, p, cell, layout):
        x, y, w, h = layout.cell_rects[cell.id]
        return (x + cell.padding_left, y + cell.padding_top,
                w - cell.padding_left - cell.padding_right,
                h - cell.padding_top - cell.padding_bottom)

    def _page_frame(self, p, cell, doc, layout):
        cx, cy, cw, ch = self._clip(p, cell, layout)
        v = resolve_plot_row_frames(p, layout)[cell.id]
        pa = render_document_fitted(doc, cw, ch, v_span_mm=v).plot_area
        return pa, cy + pa[1] * ch, cy + pa[3] * ch, (cw, ch, v)

    def test_shared_axes_frame(self):
        with tempfile.TemporaryDirectory() as td:
            docs = self._docs()
            p, cells = self._row_project(td, docs)
            layout = LayoutEngine.calculate_layout(p)
            frames = resolve_plot_row_frames(p, layout)
            self.assertEqual(set(frames), {c.id for c in cells})
            tops, bottoms, lefts = [], [], []
            for cell, doc in zip(cells, docs):
                pa, top, bottom, (cw, ch, v) = self._page_frame(
                    p, cell, doc, layout)
                tops.append(top)
                bottoms.append(bottom)
                lefts.append(pa[0] * cw)
                expected = render_document_fitted(
                    doc, cw, ch, v_span_mm=v).svg
                data = get_svg_override_bytes_for_cell(p, cell, layout)
                self.assertIsNotNone(data)
                from src.utils.svg_text_utils import _positioned_text_runs
                self.assertEqual(data, _positioned_text_runs(expected))
            for i in (1, 2):
                self.assertAlmostEqual(tops[i], tops[0], delta=0.01)
                self.assertAlmostEqual(bottoms[i], bottoms[0], delta=0.01)
            # Left margins stay per-plot: the 1e5 tick labels widen cell 2.
            self.assertNotAlmostEqual(lefts[2], lefts[0], delta=0.5)

    def test_no_vertical_clipping_with_shared_frame(self):
        import matplotlib
        with tempfile.TemporaryDirectory() as td:
            docs = self._docs()
            p, cells = self._row_project(td, docs)
            layout = LayoutEngine.calculate_layout(p)
            for cell, doc in zip(cells, docs):
                _pa, _t, _b, (cw, ch, v) = self._page_frame(
                    p, cell, doc, layout)
                with matplotlib.rc_context(
                        render._deterministic_rc(doc)):
                    fig, ax = render._build_figure(doc, 1.0, cw, ch)
                    try:
                        render._fit_axes(
                            fig, ax,
                            render.FIT_PAD_MM / 25.4 * fig.dpi,
                            render._fixed_y_px(fig, v))
                        renderer = fig.canvas.get_renderer()
                        tight = ax.get_tightbbox(renderer)
                        W = fig.get_figwidth() * fig.dpi
                        H = fig.get_figheight() * fig.dpi
                        self.assertGreaterEqual(tight.y0, -0.1)
                        self.assertLessEqual(tight.y1, H + 0.1)
                        self.assertGreaterEqual(tight.x0, -0.1)
                        self.assertLessEqual(tight.x1, W + 0.1)
                    finally:
                        fig.clear()

    def test_different_paddings_still_align(self):
        with tempfile.TemporaryDirectory() as td:
            docs = self._docs()
            p, cells = self._row_project(td, docs)
            cells[1].padding_top = 8.0
            cells[1].padding_bottom = 2.0
            layout = LayoutEngine.calculate_layout(p)
            frames = resolve_plot_row_frames(p, layout)
            self.assertEqual(set(frames), {c.id for c in cells})
            tops, bottoms = [], []
            for cell, doc in zip(cells, docs):
                _pa, top, bottom, _geom = self._page_frame(
                    p, cell, doc, layout)
                tops.append(top)
                bottoms.append(bottom)
            for i in (1, 2):
                self.assertAlmostEqual(tops[i], tops[0], delta=0.01)
                self.assertAlmostEqual(bottoms[i], bottoms[0], delta=0.01)

    def test_exclusions(self):
        with tempfile.TemporaryDirectory() as td:
            docs = self._docs()
            p, cells = self._row_project(td, docs)
            cells[0].aspect_ratio_locked = True
            cells[1].rotation = 90
            cells[2].crop_right = 0.5
            layout = LayoutEngine.calculate_layout(p)
            self.assertEqual(resolve_plot_row_frames(p, layout), {})

            p2, cells2 = self._row_project(
                os.path.join(td, "b"), docs)
            p2.layout_mode = "freeform"
            layout2 = LayoutEngine.calculate_layout(p2)
            self.assertEqual(resolve_plot_row_frames(p2, layout2), {})

            p3, cells3 = self._row_project(
                os.path.join(td, "c"), docs[:1])
            layout3 = LayoutEngine.calculate_layout(p3)
            self.assertEqual(resolve_plot_row_frames(p3, layout3), {})

    def test_stacked_subcells_do_not_share(self):
        with tempfile.TemporaryDirectory() as td:
            docs = self._docs()
            paths = [store_plot_document(d, root=td + str(i))[0]
                     for i, d in enumerate(docs)]
            p = Project(name="nested", page_width_mm=140,
                        page_height_mm=80, margin_left_mm=5,
                        margin_right_mm=5, margin_top_mm=5,
                        margin_bottom_mm=5)
            parent = Cell(row_index=0, col_index=0,
                          split_direction="vertical")
            parent.children = [
                Cell(row_index=0, col_index=0, image_path=paths[0]),
                Cell(row_index=0, col_index=1, image_path=paths[1]),
            ]
            sibling = Cell(row_index=0, col_index=1,
                           image_path=paths[2])
            p.cells = [parent, sibling]
            p.rows = [RowTemplate(index=0, column_count=2)]
            layout = LayoutEngine.calculate_layout(p)
            frames = resolve_plot_row_frames(p, layout)
            self.assertNotIn(parent.children[0].id, frames)
            self.assertNotIn(parent.children[1].id, frames)

    def test_v_span_validation_and_measure_parity(self):
        doc = PlotDocument()
        base = render_document_fitted(doc, 80.0, 50.0)
        self.assertEqual(base.plot_area, render.fit_plot_area(doc, 80.0, 50.0))
        self.assertIs(render_document_fitted(doc, 80.0, 50.0), base)
        for bad in ((-1.0, 40.0), (10.0, 5.0), (5.0, 60.0),
                    (0.0, float("nan")), (float("inf"), 40.0)):
            with self.assertRaises(PlotDocumentError):
                render_document_fitted(doc, 80.0, 50.0, v_span_mm=bad)

    def test_row_frame_cache_on_layout_result(self):
        with tempfile.TemporaryDirectory() as td:
            docs = self._docs()
            p, cells = self._row_project(td, docs)
            layout = LayoutEngine.calculate_layout(p)
            a = resolve_plot_row_frames(p, layout)
            self.assertIs(resolve_plot_row_frames(p, layout), a)


if __name__ == "__main__":
    unittest.main()
