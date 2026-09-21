import copy
import json
import math
import os
import sys
import tempfile
import unittest
import unittest.mock

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QFontDatabase, QImage, QPainter
from PyQt6.QtCore import QPointF, QRectF

from src.model.data_model import (
    Cell, GroupLabel, PiPItem, Project, RowTemplate, TextItem,
)
from src.model.migrations import (
    PROJECT_SCHEMA_VERSION, ProjectMigrationError, UnsupportedProjectVersion,
    migrate_project_data,
)

_app = QApplication.instance() or QApplication(sys.argv)
for _f in ("arial.ttf", "arialbd.ttf", "ariali.ttf", "arialbi.ttf"):
    _p = os.path.join(os.environ.get("WINDIR", r"C:\Windows"), "Fonts", _f)
    if os.path.isfile(_p):
        QFontDatabase.addApplicationFont(_p)

PT_TO_MM = 25.4 / 72.0
MM_TO_PT = 72.0 / 25.4

_MEASUREMENTS = {}
_WHITE_PNG = None


def _record(key, value):
    _MEASUREMENTS[key] = value


def tearDownModule():
    out = os.environ.get("ILM_TYPOGRAPHY_MEASUREMENTS")
    if not out:
        fd, out = tempfile.mkstemp(prefix="ilm_measurements_", suffix=".json")
        os.close(fd)
    else:
        os.makedirs(os.path.dirname(out), exist_ok=True)
    with open(out, "w", encoding="utf-8") as fh:
        json.dump(_MEASUREMENTS, fh, indent=2, sort_keys=True)
    print("measurements:", out)
    if _WHITE_PNG and os.path.isfile(_WHITE_PNG):
        os.remove(_WHITE_PNG)


def _white_png():
    global _WHITE_PNG
    if _WHITE_PNG is None or not os.path.isfile(_WHITE_PNG):
        fd, _WHITE_PNG = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        img = QImage(400, 300, QImage.Format.Format_RGB32)
        img.fill(0xFFFFFFFF)
        img.save(_WHITE_PNG)
    return _WHITE_PNG


def _pdf_lines(path):
    import fitz
    doc = fitz.open(path)
    lines = []
    for page in doc:
        for block in page.get_text("dict")["blocks"]:
            if block.get("type") != 0:
                continue
            for line in block["lines"]:
                text = "".join(s["text"] for s in line["spans"])
                lines.append((text, line["spans"]))
    doc.close()
    return lines


def _pdf_spans(path):
    return [s for _t, spans in _pdf_lines(path) for s in spans]


def _find_span(spans, token):
    return [s for s in spans if token in s["text"]]


def _new_points_project(dpi=300, page_width_mm=120):
    return Project(name="Typography", page_width_mm=page_width_mm,
                   page_height_mm=100,
                   margin_left_mm=5, margin_right_mm=5,
                   margin_top_mm=5, margin_bottom_mm=5, dpi=dpi)


def _export_pdf(project):
    from src.export.pdf_exporter import PdfExporter
    fd, path = tempfile.mkstemp(suffix=".pdf")
    os.close(fd)
    PdfExporter.export(project, path)
    return path


def _export_png(project):
    from src.export.image_exporter import ImageExporter
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    ImageExporter.export(project, path, format="PNG")
    return path


def _export_svg(project):
    from src.export.svg_exporter import SvgExporter
    fd, path = tempfile.mkstemp(suffix=".svg")
    os.close(fd)
    SvgExporter.export(project, path)
    return path


def _ink_bbox_mm(png_path, dpi):
    img = QImage(png_path)
    xs, ys = [], []
    for y in range(img.height()):
        for x in range(img.width()):
            if (img.pixel(x, y) & 0xFFFFFF) != 0xFFFFFF:
                xs.append(x)
                ys.append(y)
    if not xs:
        return None
    px_per_mm = dpi / 25.4
    return ((max(xs) - min(xs) + 1) / px_per_mm,
            (max(ys) - min(ys) + 1) / px_per_mm)


def _svg_mapped_positions(svg_bytes):
    import re
    import xml.etree.ElementTree as ET
    from src.utils.svg_text_utils import _parse_transform_matrix
    root = ET.fromstring(svg_bytes)
    parents = {c: p for p in root.iter() for c in p}
    def mul(a, b):
        return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
                a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
                a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])
    num = r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?'
    out = []
    for el in root.iter():
        if el.tag.rsplit('}', 1)[-1] not in ('text', 'tspan'):
            continue
        if not (el.text or '').strip():
            continue
        if 'x' not in el.attrib and 'y' not in el.attrib:
            continue
        chain = []
        node = el
        while node is not None:
            chain.append(node.get('transform', ''))
            node = parents.get(node)
        m = (1, 0, 0, 1, 0, 0)
        for s in reversed(chain):
            m = mul(m, tuple(_parse_transform_matrix(s)))
        xs = [float(v) for v in re.findall(num, el.get('x', '') or '0')]
        ys = [float(v) for v in re.findall(num, el.get('y', '') or '0')]
        points = []
        for i in range(max(len(xs), len(ys))):
            x = xs[min(i, len(xs) - 1)]
            y = ys[min(i, len(ys) - 1)]
            points.append((m[0]*x + m[2]*y + m[4], m[1]*x + m[3]*y + m[5]))
        out.append(points)
    return out


def _svg_mupdf_spans(svg_bytes):
    import fitz
    doc = fitz.open(stream=svg_bytes, filetype='svg')
    spans = []
    for page in doc:
        for block in page.get_text('dict')['blocks']:
            if block.get('type') != 0:
                continue
            for line in block['lines']:
                spans.extend(line['spans'])
    doc.close()
    return spans


def _svg_font_points(path, token):
    import re
    import xml.etree.ElementTree as ET
    root = ET.parse(path).getroot()
    width_mm = float(root.get('width').removesuffix('mm'))
    height_mm = float(root.get('height').removesuffix('mm'))
    vb = [float(x) for x in root.get('viewBox').replace(',', ' ').split()]
    def mul(a, b):
        return (a[0]*b[0]+a[2]*b[1], a[1]*b[0]+a[3]*b[1],
                a[0]*b[2]+a[2]*b[3], a[1]*b[2]+a[3]*b[3],
                a[0]*b[4]+a[2]*b[5]+a[4], a[1]*b[4]+a[3]*b[5]+a[5])
    def transform(s):
        out = (1,0,0,1,0,0)
        for name, raw in re.findall(r'([A-Za-z]+)\s*\(([^)]*)\)', s):
            v = [float(x) for x in re.findall(r'[-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?',raw)]
            if name == 'matrix':
                m = tuple(v)
            elif name == 'translate':
                m = (1,0,0,1,v[0],v[1] if len(v)>1 else 0)
            elif name == 'scale':
                m = (v[0],0,0,v[1] if len(v)>1 else v[0],0,0)
            elif name == 'rotate':
                c,sn = math.cos(math.radians(v[0])), math.sin(math.radians(v[0]))
                m = (c,sn,-sn,c,0,0)
                if len(v)==3:
                    m = mul(mul((1,0,0,1,v[1],v[2]),m),(1,0,0,1,-v[1],-v[2]))
            else:
                raise AssertionError(f'Unexpected SVG transform {name}')
            out = mul(out,m)
        return out
    found = []
    def walk(el, matrix, font_size):
        matrix = mul(matrix, transform(el.get('transform','')))
        style = dict(re.findall(r'([\w-]+)\s*:\s*([^;]+)', el.get('style','')))
        raw = style.get('font-size',el.get('font-size'))
        if raw is not None:
            match = re.fullmatch(r'\s*([0-9.]+)(px|pt)?\s*',raw)
            if match is None:
                raise AssertionError(f'Unexpected SVG font size {raw}')
            font_size = float(match[1]) * (4/3 if match[2]=='pt' else 1)
        if el.tag.rsplit('}',1)[-1]=='text' and token in ''.join(el.itertext()):
            if font_size is None:
                raise AssertionError('No inherited SVG font size')
            found.append(font_size * math.hypot(matrix[2],matrix[3]) * 72/25.4)
        for child in el:
            walk(child,matrix,font_size)
    walk(root,(width_mm/vb[2],0,0,height_mm/vb[3],0,0),None)
    return found


def _figure_project(dpi=300):
    p = _new_points_project(dpi=dpi)
    cells = [Cell(row_index=0, col_index=i) for i in range(5)]
    for c in cells:
        c.is_placeholder = True
    cells[0].image_path = _white_png()
    cells[0].is_placeholder = False
    cells[0].scale_bar_enabled = True
    cells[0].scale_bar_show_text = True
    cells[0].scale_bar_custom_text = "BAR825"
    cells[0].scale_bar_text_size_pt = 8.25
    cells[0].scale_bar_color = "#000000"
    pip = PiPItem(pip_type="external")
    pip.scale_bar_enabled = True
    pip.scale_bar_show_text = True
    pip.scale_bar_custom_text = "PIP825"
    pip.scale_bar_text_size_pt = 8.25
    pip.scale_bar_color = "#000000"
    cells[1].pip_items = [pip]
    p.cells = cells
    p.rows = [RowTemplate(index=0, column_count=5)]
    p.label_col_width = 18.0
    p.label_row_height = 18.0
    p.label_placement = "in_cell"
    p.label_font_size = 8.25
    p.text_items = [
        TextItem(text="GLOB825", font_size_pt=8.25, x=10, y=85),
        TextItem(text="CELL825", font_size_pt=8.25, scope="cell",
                 parent_id=cells[0].id, subtype="numbering",
                 anchor="top_left_inside"),
        TextItem(text="STPA825", font_size_pt=8.25, scope="cell",
                 parent_id=cells[1].id, subtype="numbering",
                 placement="label_row_above", rotation=0),
        TextItem(text="STPB825", font_size_pt=8.25, scope="cell",
                 parent_id=cells[2].id, subtype="numbering",
                 placement="label_row_below", rotation=90),
        TextItem(text="STPL825", font_size_pt=8.25, scope="cell",
                 parent_id=cells[3].id, subtype="numbering",
                 placement="label_col_left", rotation=270),
        TextItem(text="STPR825", font_size_pt=8.25, scope="cell",
                 parent_id=cells[4].id, subtype="numbering",
                 placement="label_col_right", rotation=0),
        TextItem(text="$x^2$", font_size_pt=9.0, x=80, y=85),
    ]
    p.group_labels = [
        GroupLabel(text="GRPT825", cell_ids=[cells[0].id, cells[1].id],
                   side="top", font_size_pt=8.25),
        GroupLabel(text="GRPL825", row_index=0, side="left",
                   font_size_pt=8.25),
    ]
    return p


_FIGURE_TOKENS = ["GLOB825", "CELL825", "STPA825", "STPB825", "STPL825",
                  "STPR825", "GRPT825", "GRPL825", "BAR825", "PIP825"]


class TestSchemaMigrations(unittest.TestCase):

    def _legacy_dict(self, schema):
        data = Project().to_dict()
        data.pop("typography_mode", None)
        data["schema_version"] = schema
        if schema < 3:
            data.pop("label_valign", None)
            for item in data.get("text_items", []):
                for k in ("label_align", "label_valign",
                          "label_offset_x", "label_offset_y"):
                    item.pop(k, None)
        if schema < 1:
            for key in ("label_align", "label_offset_x", "label_offset_y",
                        "label_row_height"):
                data.pop(key, None)
            data.pop("plot_alignment_groups", None)
        return data

    def test_schema_0_to_3_become_legacy(self):
        for schema in (0, 1, 2, 3):
            data = self._legacy_dict(schema)
            original = copy.deepcopy(data)
            migrated = migrate_project_data(data)
            self.assertEqual(migrated["typography_mode"], "legacy")
            self.assertEqual(migrated["schema_version"], PROJECT_SCHEMA_VERSION)
            self.assertEqual(data, original)
            p = Project.from_dict(copy.deepcopy(original))
            self.assertEqual(p.typography_mode, "legacy")
            self.assertEqual(p.to_dict()["typography_mode"], "legacy")

    def test_new_project_is_points_and_roundtrips(self):
        p = Project()
        self.assertEqual(p.typography_mode, "points")
        d = p.to_dict()
        self.assertEqual(d["schema_version"], PROJECT_SCHEMA_VERSION)
        self.assertEqual(d["typography_mode"], "points")
        p2 = Project.from_dict(copy.deepcopy(d))
        self.assertEqual(p2.typography_mode, "points")

    def test_schema4_missing_or_invalid_mode_rejected(self):
        d = Project().to_dict()
        d.pop("typography_mode")
        with self.assertRaises(ProjectMigrationError):
            migrate_project_data(d)
        for bad in ("bogus", None, True, 1, [], {}):
            d = Project().to_dict()
            d["typography_mode"] = bad
            with self.assertRaises(ProjectMigrationError,
                                   msg=f"mode={bad!r}"):
                migrate_project_data(d)

    def test_future_schema_rejected(self):
        d = Project().to_dict()
        d["schema_version"] = PROJECT_SCHEMA_VERSION + 1
        with self.assertRaises(UnsupportedProjectVersion):
            migrate_project_data(d)

    def test_points_mode_invalid_sizes_rejected(self):
        bads = (0, -1, float("nan"), float("inf"), True, None, "8")
        base = Project().to_dict()
        base["text_items"] = [{"id": "t1", "text": "X", "font_size_pt": 8.0,
                               "x": 1, "y": 1, "scope": "global"}]
        base["group_labels"] = [{"id": "g1", "text": "G", "cell_ids": [],
                                 "font_size_pt": 8.0}]
        base["svg_text_groups"] = [{"id": "s1", "name": "s", "members": [],
                                    "font_size_pt": 8.0}]
        base["cells"] = [{"id": "c1", "row_index": 0, "col_index": 0,
                          "scale_bar_text_size_pt": 8.0,
                          "svg_normalize_text_pt": 8.0,
                          "pip_items": [{"id": "p1",
                                         "scale_bar_text_size_pt": 8.0}]}]

        def setters(d, bad):
            yield ("label_font_size", dict(d, label_font_size=bad))
            yield ("title_label_font_size",
                   dict(d, title_label_font_size=bad))
            yield ("corner_label_font_size",
                   dict(d, corner_label_font_size=bad))
            t = copy.deepcopy(d)
            t["text_items"][0]["font_size_pt"] = bad
            yield ("text_items.font_size_pt", t)
            t = copy.deepcopy(d)
            t["group_labels"][0]["font_size_pt"] = bad
            yield ("group_labels.font_size_pt", t)
            t = copy.deepcopy(d)
            t["svg_text_groups"][0]["font_size_pt"] = bad
            yield ("svg_text_groups.font_size_pt", t)
            t = copy.deepcopy(d)
            t["cells"][0]["scale_bar_text_size_pt"] = bad
            yield ("cell.scale_bar_text_size_pt", t)
            t = copy.deepcopy(d)
            t["cells"][0]["svg_normalize_text_pt"] = bad
            yield ("cell.svg_normalize_text_pt", t)
            t = copy.deepcopy(d)
            t["cells"][0]["pip_items"][0]["scale_bar_text_size_pt"] = bad
            yield ("pip.scale_bar_text_size_pt", t)

        for bad in bads:
            for where, d in setters(base, bad):
                with self.assertRaises(ProjectMigrationError,
                                       msg=f"{where}={bad!r}"):
                    migrate_project_data(d)

    def test_legacy_mode_invalid_raw_sizes_untouched(self):
        bads = (0, -1, float("nan"), float("inf"), True, None, "8")
        for bad in bads:
            d = Project().to_dict()
            d["typography_mode"] = "legacy"
            d["label_font_size"] = bad
            d["text_items"] = [{"id": "t1", "text": "X", "font_size_pt": bad,
                                "x": 1, "y": 1, "scope": "global"}]
            d["cells"] = [{"id": "c1", "row_index": 0, "col_index": 0,
                           "scale_bar_text_size_pt": bad}]
            migrated = migrate_project_data(d)
            for got in (migrated["label_font_size"],
                        migrated["text_items"][0]["font_size_pt"]):
                if isinstance(bad, float) and math.isnan(bad):
                    self.assertTrue(math.isnan(got))
                else:
                    self.assertEqual(got, bad)

    def test_nested_scale_bar_pt_fields_roundtrip(self):
        p = Project()
        cell = Cell(row_index=0, col_index=0)
        cell.scale_bar_text_size_pt = 8.25
        pip = PiPItem(pip_type="external")
        pip.scale_bar_text_size_pt = 7.5
        cell.pip_items = [pip]
        p.cells = [cell]
        p.rows = [RowTemplate(index=0, column_count=1)]
        p2 = Project.from_dict(copy.deepcopy(p.to_dict()))
        c2 = p2.get_all_leaf_cells()[0]
        self.assertAlmostEqual(c2.scale_bar_text_size_pt, 8.25)
        self.assertAlmostEqual(c2.pip_items[0].scale_bar_text_size_pt, 7.5)
        self.assertAlmostEqual(c2.scale_bar_text_size_mm, 2.0)

    def test_float_font_fields_roundtrip(self):
        p = Project()
        p.label_font_size = 8.25
        p.title_label_font_size = 7.5
        p.corner_label_font_size = 6.5
        p.text_items = [TextItem(text="X", font_size_pt=8.25)]
        p.group_labels = [GroupLabel(text="G", row_index=0,
                                     font_size_pt=9.5)]
        p2 = Project.from_dict(copy.deepcopy(p.to_dict()))
        self.assertAlmostEqual(p2.label_font_size, 8.25)
        self.assertAlmostEqual(p2.title_label_font_size, 7.5)
        self.assertAlmostEqual(p2.corner_label_font_size, 6.5)
        self.assertAlmostEqual(p2.text_items[0].font_size_pt, 8.25)
        self.assertAlmostEqual(p2.group_labels[0].font_size_pt, 9.5)


class TestPhysicalPdf(unittest.TestCase):

    def test_point_sizes_across_dpi(self):
        results = {}
        sizes = {}
        for pt in (5.0, 7.5, 8.25, 12.0):
            for dpi in (150, 300, 600):
                p = _new_points_project(dpi=dpi)
                p.text_items = [TextItem(text="POINTTEST", font_size_pt=pt,
                                         x=10, y=10)]
                path = _export_pdf(p)
                try:
                    spans = _find_span(_pdf_spans(path), "POINTTEST")
                finally:
                    os.remove(path)
                self.assertTrue(spans, f"no POINTTEST span at {pt}pt/{dpi}dpi")
                for s in spans:
                    self.assertAlmostEqual(s["size"], pt, delta=0.08,
                                           msg=f"pt={pt} dpi={dpi}")
                results.setdefault(pt, []).append(spans[0]["bbox"])
                sizes.setdefault(pt, {})[dpi] = [round(s["size"], 4)
                                                 for s in spans]
        for pt, boxes in results.items():
            wh = [((b[2] - b[0]) * PT_TO_MM, (b[3] - b[1]) * PT_TO_MM)
                  for b in boxes]
            for w, h in wh:
                self.assertAlmostEqual(w, wh[0][0], delta=0.08,
                                       msg=f"pt={pt} width drift")
                self.assertAlmostEqual(h, wh[0][1], delta=0.08,
                                       msg=f"pt={pt} height drift")
        _record("pdf_span_sizes", sizes)
        _record("pdf_bboxes_mm",
                {str(pt): [[round((b[2] - b[0]) * PT_TO_MM, 4),
                            round((b[3] - b[1]) * PT_TO_MM, 4)]
                           for b in boxes]
                 for pt, boxes in results.items()})
        for pt in results:
            print(f"POINTTEST {pt}pt sizes:", sizes[pt],
                  "bboxes:", [tuple(round(v, 3) for v in b)
                              for b in results[pt]])

    def test_html_font_size_normalized_and_bold_kept(self):
        p = _new_points_project()
        p.text_items = [TextItem(
            text='<p style="font-size:24pt"><b>POINTTEST</b></p>',
            font_size_pt=8.25, x=10, y=10)]
        path = _export_pdf(p)
        try:
            spans = _find_span(_pdf_spans(path), "POINTTEST")
        finally:
            os.remove(path)
        self.assertTrue(spans)
        self.assertAlmostEqual(spans[0]["size"], 8.25, delta=0.08)
        self.assertTrue(spans[0]["flags"] & 16 or "bold" in
                        spans[0]["font"].lower(),
                        msg="bold weight lost")

    def test_html_no_drift_across_save_load(self):
        html = '<p style="font-size:24pt"><b>POINTTEST</b></p>'
        p = _new_points_project()
        p.text_items = [TextItem(text=html, font_size_pt=8.25, x=10, y=10)]
        with tempfile.TemporaryDirectory() as td:
            for _ in range(2):
                f = os.path.join(td, "p.json")
                p.save_to_file(f)
                p = Project.load_from_file(f)
            self.assertAlmostEqual(p.text_items[0].font_size_pt, 8.25)
            path = _export_pdf(p)
            try:
                spans = _find_span(_pdf_spans(path), "POINTTEST")
            finally:
                os.remove(path)
        self.assertTrue(spans)
        self.assertAlmostEqual(spans[0]["size"], 8.25, delta=0.08)

    def test_rotated_text_keeps_size(self):
        p = _new_points_project()
        p.text_items = [TextItem(text="POINTTEST", font_size_pt=8.25,
                                 x=10, y=10, rotation=90)]
        path = _export_pdf(p)
        try:
            spans = _find_span(_pdf_spans(path), "POINTTEST")
        finally:
            os.remove(path)
        self.assertTrue(spans)
        self.assertAlmostEqual(spans[0]["size"], 8.25, delta=0.08)


class TestFigurePdf(unittest.TestCase):

    def test_figure_text_sizes(self):
        try:
            import matplotlib
        except ImportError:
            self.skipTest("matplotlib unavailable for math text")
        measured = {}
        for dpi in (150, 300, 600):
            p = _figure_project(dpi)
            path = _export_pdf(p)
            try:
                lines = _pdf_lines(path)
            finally:
                os.remove(path)
            for token in _FIGURE_TOKENS:
                hits = [(t, sp) for t, sp in lines if token in t]
                self.assertTrue(hits, f"{token} missing at {dpi}dpi: "
                                f"{[t for t, _ in lines]}")
                for _t, spans in hits:
                    for s in spans:
                        self.assertAlmostEqual(s["size"], 8.25, delta=0.08,
                                               msg=f"{token} at {dpi}dpi")
                measured.setdefault(token, {})[dpi] = round(
                    hits[0][1][0]["size"], 4)
            spans = [s for _t, sp in lines for s in sp]
            xs = [s for s in spans if s["text"].strip() == "x"]
            self.assertTrue(xs, f"math base x missing at {dpi}dpi: "
                            f"{[s['text'] for s in spans]}")
            self.assertAlmostEqual(xs[0]["size"], 9.0, delta=0.08)
        _record("figure_pdf_span_sizes", measured)
        print("figure spans:", measured)


class TestSvgExport(unittest.TestCase):

    def test_exported_svg_point_text(self):
        measured = {}
        for rot in (0, 90, 270):
            for dpi in (150, 600):
                p = _new_points_project(dpi=dpi)
                p.text_items = [TextItem(text="POINTTEST", font_size_pt=8.25,
                                         x=10, y=10, rotation=rot)]
                path = _export_svg(p)
                try:
                    sizes = _svg_font_points(path, "POINTTEST")
                finally:
                    os.remove(path)
                self.assertTrue(sizes, f"no POINTTEST text rot={rot} dpi={dpi}")
                for v in sizes:
                    self.assertAlmostEqual(v, 8.25, delta=0.08,
                                           msg=f"rot={rot} dpi={dpi}")
                measured[f"rot{rot}_dpi{dpi}"] = [round(v, 4) for v in sizes]
        _record("svg_export_sizes", measured)
        print("svg sizes:", measured)

    def test_exported_svg_figure_text(self):
        p = _figure_project(300)
        path = _export_svg(p)
        try:
            measured = {}
            for token in _FIGURE_TOKENS:
                sizes = _svg_font_points(path, token)
                self.assertTrue(sizes, f"{token} missing from SVG")
                for v in sizes:
                    self.assertAlmostEqual(v, 8.25, delta=0.08,
                                           msg=f"{token}")
                measured[token] = [round(v, 4) for v in sizes]
        finally:
            os.remove(path)
        _record("svg_figure_sizes", measured)
        print("svg figure:", measured)


class TestSvgNormalization(unittest.TestCase):

    _SVG = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" '
        'viewBox="0 0 100 50">'
        '<g transform="scale(2)">'
        '<text id="svgtxt" x="5" y="20" font-size="24" '
        'font-family="Arial">SVGTXT</text></g></svg>'
    )

    _SVG_TSPANS = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" '
        'viewBox="0 0 100 50"><g transform="scale(2)">'
        '<text id="svgtxt" x="5" y="10" font-family="Arial" font-size="24">'
        '<tspan x="5" y="10">ALPHA</tspan>'
        '<tspan x="5" y="20">BETA</tspan></text></g></svg>'
    )

    _SVG_ANCHOR = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" '
        'viewBox="0 0 100 50"><g transform="rotate(90 25 25)">'
        '<text id="anch" x="30" y="12" text-anchor="middle" '
        'font-family="Arial" font-size="18">MID</text></g></svg>'
    )

    _SVG_MULTIX = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" '
        'viewBox="0 0 100 50"><g transform="scale(2)">'
        '<text id="multi" x="5 15 25" y="20" font-family="Arial" '
        'font-size="24">ABC</text></g></svg>'
    )

    _SVG_SHORTHAND = (
        '<svg xmlns="http://www.w3.org/2000/svg" width="100" height="50" '
        'viewBox="0 0 100 50"><g transform="scale(2)">'
        '<text id="svgtxt" x="5" y="20" style="font: italic 6px Arial"'
        '>SHORTX</text></g></svg>'
    )

    def _project_with_svg(self, tmpdir, normalize_pt=9.0,
                          page_width_mm=120):
        svg_path = os.path.join(tmpdir, "panel.svg")
        with open(svg_path, "w", encoding="utf-8") as fh:
            fh.write(self._SVG)
        p = _new_points_project(page_width_mm=page_width_mm)
        cell = Cell(row_index=0, col_index=0, image_path=svg_path,
                    is_placeholder=False)
        cell.svg_normalize_text = True
        cell.svg_normalize_text_pt = normalize_pt
        p.cells = [cell]
        p.rows = [RowTemplate(index=0, column_count=1)]
        return p, cell, svg_path

    def _effective_pt(self, project, cell, layout_result):
        import re
        import xml.etree.ElementTree as ET
        from src.utils.svg_text_utils import (
            get_svg_override_bytes_for_cell, svg_mm_per_unit,
            _parse_transform_matrix, _matrix_effective_scale,
        )
        data = get_svg_override_bytes_for_cell(project, cell, layout_result)
        self.assertIsNotNone(data)
        root = ET.fromstring(data)
        parents = {c: p for p in root.iter() for c in p}
        target = None
        for elem in root.iter():
            local = elem.tag.split("}")[-1]
            if local == "text" and "SVGTXT" in (elem.text or ""):
                target = elem
        self.assertIsNotNone(target)
        style = target.get("style", "")
        m = re.search(r"font-size\s*:\s*([\d.]+)(px|pt)", style)
        self.assertIsNotNone(m, f"no font-size in style {style!r}")
        written = float(m.group(1))
        transforms = [target.get("transform", "")]
        node = parents.get(target)
        while node is not None:
            transforms.append(node.get("transform", ""))
            node = parents.get(node)
        acc = _parse_transform_matrix(" ".join(reversed(transforms)))
        inner_scale = _matrix_effective_scale(acc)
        mm_per_unit = svg_mm_per_unit(project, cell, data, layout_result)
        return written * inner_scale * mm_per_unit * MM_TO_PT

    def test_normalized_effective_size_is_real_points(self):
        from src.model.layout_engine import LayoutEngine
        with tempfile.TemporaryDirectory() as td:
            p, cell, svg_path = self._project_with_svg(td)
            with open(svg_path, "rb") as fh:
                src_before = fh.read()
            layout = LayoutEngine.calculate_layout(p)
            eff = self._effective_pt(p, cell, layout)
            self.assertAlmostEqual(eff, 9.0, delta=0.08,
                                   msg=f"effective={eff}")
            with open(svg_path, "rb") as fh:
                self.assertEqual(fh.read(), src_before)
            _record("svg_normalized_effective_pt", round(eff, 4))

    def test_group_override_takes_precedence(self):
        from src.model.data_model import SvgTextGroup, SvgTextMember
        from src.model.layout_engine import LayoutEngine
        with tempfile.TemporaryDirectory() as td:
            p, cell, svg_path = self._project_with_svg(td)
            group = SvgTextGroup(name="g", font_size_pt=7.5)
            group.members = [SvgTextMember(svg_path=svg_path,
                                           element_key="svgtxt")]
            p.svg_text_groups = [group]
            layout = LayoutEngine.calculate_layout(p)
            eff = self._effective_pt(p, cell, layout)
            self.assertAlmostEqual(eff, 7.5, delta=0.08,
                                   msg=f"effective={eff}")
            _record("svg_override_effective_pt", round(eff, 4))

    def test_pdf_rendered_normalized_sizes(self):
        import hashlib
        from src.model.data_model import SvgTextGroup, SvgTextMember
        measured = {}
        for page_w in (120, 180):
            with tempfile.TemporaryDirectory() as td:
                p, cell, svg_path = self._project_with_svg(
                    td, page_width_mm=page_w)
                with open(svg_path, "rb") as fh:
                    src_hash = hashlib.sha256(fh.read()).hexdigest()
                path = _export_pdf(p)
                try:
                    spans = _find_span(_pdf_spans(path), "SVGTXT")
                finally:
                    os.remove(path)
                self.assertTrue(spans, f"no SVGTXT span at width {page_w}")
                for s in spans:
                    self.assertAlmostEqual(s["size"], 9.0, delta=0.08,
                                           msg=f"page_w={page_w}")
                measured[f"norm_w{page_w}"] = [round(s["size"], 4)
                                               for s in spans]
                group = SvgTextGroup(name="g", font_size_pt=7.5)
                group.members = [SvgTextMember(svg_path=svg_path,
                                               element_key="svgtxt")]
                p.svg_text_groups = [group]
                path = _export_pdf(p)
                try:
                    spans = _find_span(_pdf_spans(path), "SVGTXT")
                finally:
                    os.remove(path)
                self.assertTrue(spans, f"no SVGTXT span override {page_w}")
                for s in spans:
                    self.assertAlmostEqual(s["size"], 7.5, delta=0.08,
                                           msg=f"override page_w={page_w}")
                measured[f"override_w{page_w}"] = [round(s["size"], 4)
                                                  for s in spans]
                with open(svg_path, "rb") as fh:
                    self.assertEqual(hashlib.sha256(fh.read()).hexdigest(),
                                     src_hash)
        _record("svg_pdf_rendered_sizes", measured)
        print("svg pdf:", measured)

    def test_legacy_px_and_pt_paths_unchanged(self):
        import re
        import xml.etree.ElementTree as ET
        from src.model.data_model import SvgTextGroup, SvgTextMember
        from src.model.layout_engine import LayoutEngine
        from src.utils.svg_text_utils import (
            apply_svg_font_overrides_from_bytes,
            get_svg_override_bytes_for_cell, svg_mm_per_unit,
        )
        with tempfile.TemporaryDirectory() as td:
            svg_path = os.path.join(td, "panel.svg")
            with open(svg_path, "w", encoding="utf-8") as fh:
                fh.write(self._SVG)
            d = Project().to_dict()
            d.pop("typography_mode")
            d["schema_version"] = 3
            p = Project.from_dict(d)
            self.assertEqual(p.typography_mode, "legacy")
            cell = Cell(row_index=0, col_index=0, image_path=svg_path,
                        is_placeholder=False)
            cell.svg_normalize_text = True
            cell.svg_normalize_text_pt = 9.0
            p.cells = [cell]
            p.rows = [RowTemplate(index=0, column_count=1)]
            layout = LayoutEngine.calculate_layout(p)
            data = get_svg_override_bytes_for_cell(p, cell, layout)
            root = ET.fromstring(data)
            target = next(e for e in root.iter()
                          if e.tag.rsplit("}", 1)[-1] == "text")
            self.assertIsNone(target.get("transform"))
            m = re.search(r"font-size\s*:\s*([\d.]+)pt",
                          target.get("style", ""))
            self.assertIsNotNone(m)
            self.assertAlmostEqual(float(m.group(1)), 9.0 / 2)

            cell.svg_normalize_text = False
            g = SvgTextGroup(name="g", font_size_pt=7.5)
            g.members = [SvgTextMember(svg_path=svg_path,
                                       element_key="svgtxt")]
            p.svg_text_groups = [g]
            data = get_svg_override_bytes_for_cell(p, cell, layout)
            root = ET.fromstring(data)
            target = next(e for e in root.iter()
                          if e.tag.rsplit("}", 1)[-1] == "text")
            self.assertIsNone(target.get("transform"))
            m = re.search(r"font-size\s*:\s*([\d.]+)px",
                          target.get("style", ""))
            self.assertIsNotNone(m)
            expected = (7.5 * PT_TO_MM) / svg_mm_per_unit(
                p, cell, data, layout) / 2
            self.assertAlmostEqual(float(m.group(1)), expected)

            out = apply_svg_font_overrides_from_bytes(
                self._SVG.encode("utf-8"), {"svgtxt": 1.4432}, unit="px")
            root = ET.fromstring(out)
            target = next(e for e in root.iter()
                          if e.tag.rsplit("}", 1)[-1] == "text")
            self.assertIsNone(target.get("transform"))
            m = re.search(r"font-size\s*:\s*([\d.]+)px",
                          target.get("style", ""))
            self.assertAlmostEqual(float(m.group(1)), 1.4432 / 2)

    def test_positioned_tspans_preserve_layout(self):
        import hashlib
        from src.model.data_model import SvgTextGroup, SvgTextMember
        from src.model.layout_engine import LayoutEngine
        from src.utils.svg_text_utils import (
            get_svg_override_bytes_for_cell, svg_mm_per_unit)
        measured = {}
        for page_w in (120, 180):
            with tempfile.TemporaryDirectory() as td:
                svg_path = os.path.join(td, "panel.svg")
                with open(svg_path, "w", encoding="utf-8") as fh:
                    fh.write(self._SVG_TSPANS)
                p = _new_points_project(page_width_mm=page_w)
                cell = Cell(row_index=0, col_index=0, image_path=svg_path,
                            is_placeholder=False)
                cell.svg_normalize_text = True
                cell.svg_normalize_text_pt = 9.0
                p.cells = [cell]
                p.rows = [RowTemplate(index=0, column_count=1)]
                layout = LayoutEngine.calculate_layout(p)
                with open(svg_path, "rb") as fh:
                    src_bytes = fh.read()
                src_hash = hashlib.sha256(src_bytes).hexdigest()
                mm_per_unit = svg_mm_per_unit(p, cell, src_bytes, layout)

                before = _svg_mapped_positions(src_bytes)
                data = get_svg_override_bytes_for_cell(p, cell, layout)
                after = _svg_mapped_positions(data)
                self.assertEqual(len(before), len(after))
                for pts0, pts1 in zip(before, after):
                    self.assertEqual(len(pts0), len(pts1))
                    for p0, p1 in zip(pts0, pts1):
                        self.assertAlmostEqual(p0[0], p1[0], delta=1e-8)
                        self.assertAlmostEqual(p0[1], p1[1], delta=1e-8)

                expect_units = 9.0 * PT_TO_MM / mm_per_unit
                mu = _svg_mupdf_spans(data)
                a = [s for s in mu if "ALP" in s["text"]]
                b = [s for s in mu if "BET" in s["text"]]
                self.assertTrue(a and b, f"MuPDF spans: {[s['text'] for s in mu]}")
                self.assertAlmostEqual(a[0]["size"], expect_units, delta=0.02)
                self.assertAlmostEqual(b[0]["size"], expect_units, delta=0.02)
                self.assertAlmostEqual(a[0]["origin"][0],
                                       b[0]["origin"][0], delta=0.02)
                sep = b[0]["origin"][1] - a[0]["origin"][1]
                self.assertAlmostEqual(sep, 20.0, delta=0.08)
                measured[f"mupdf_norm_w{page_w}"] = {
                    "units": [round(a[0]["size"], 4), round(b[0]["size"], 4)],
                    "expected_units": round(expect_units, 4),
                    "sep_units": round(sep, 4),
                    "sep_pt_equiv": round(sep * mm_per_unit * MM_TO_PT, 4)}

                path = _export_pdf(p)
                try:
                    qt = _pdf_spans(path)
                finally:
                    os.remove(path)
                a_qt = [s for s in qt if 'ALPHA' in s['text']]
                b_qt = [s for s in qt if 'BETA' in s['text']]
                measured[f"qt_norm_w{page_w}"] = {
                    "sizes": [round(a_qt[0]["size"], 4),
                              round(b_qt[0]["size"], 4)] if a_qt and b_qt else [],
                    "origins": [list(a_qt[0]["origin"]),
                                list(b_qt[0]["origin"])] if a_qt and b_qt else [],
                    "expect_sep_pt": round(20.0 * mm_per_unit * MM_TO_PT, 4),
                    "all_texts": [s["text"] for s in qt]}
                _record("svg_tspan_positions", measured)
                self.assertTrue(a_qt and b_qt, [s['text'] for s in qt])
                for hit in (a_qt[0], b_qt[0]):
                    self.assertAlmostEqual(hit['size'], 9.0, delta=0.08)
                self.assertAlmostEqual(a_qt[0]['origin'][0], b_qt[0]['origin'][0], delta=0.02)
                self.assertAlmostEqual(b_qt[0]['origin'][1]-a_qt[0]['origin'][1],
                                       20.0 * mm_per_unit * MM_TO_PT, delta=0.08)

                g = SvgTextGroup(name="g", font_size_pt=7.5)
                g.members = [SvgTextMember(svg_path=svg_path,
                                           element_key="svgtxt")]
                p.svg_text_groups = [g]
                data = get_svg_override_bytes_for_cell(p, cell, layout)
                after = _svg_mapped_positions(data)
                self.assertEqual(len(before), len(after))
                for pts0, pts1 in zip(before, after):
                    for p0, p1 in zip(pts0, pts1):
                        self.assertAlmostEqual(p0[0], p1[0], delta=1e-8)
                        self.assertAlmostEqual(p0[1], p1[1], delta=1e-8)
                expect_units = 7.5 * PT_TO_MM / mm_per_unit
                mu = _svg_mupdf_spans(data)
                a = [s for s in mu if "ALP" in s["text"]]
                b = [s for s in mu if "BET" in s["text"]]
                self.assertTrue(a and b)
                self.assertAlmostEqual(a[0]["size"], expect_units, delta=0.02)
                self.assertAlmostEqual(b[0]["size"], expect_units, delta=0.02)
                sep = b[0]["origin"][1] - a[0]["origin"][1]
                self.assertAlmostEqual(sep, 20.0, delta=0.08)
                path = _export_pdf(p)
                try:
                    qt = _pdf_spans(path)
                finally:
                    os.remove(path)
                a_qt = [s for s in qt if 'ALPHA' in s['text']]
                b_qt = [s for s in qt if 'BETA' in s['text']]
                measured[f"qt_override_w{page_w}"] = {
                    "sizes": [round(a_qt[0]["size"], 4),
                              round(b_qt[0]["size"], 4)] if a_qt and b_qt else [],
                    "origins": [list(a_qt[0]["origin"]),
                                list(b_qt[0]["origin"])] if a_qt and b_qt else [],
                    "expect_sep_pt": round(20.0 * mm_per_unit * MM_TO_PT, 4),
                    "all_texts": [s["text"] for s in qt]}
                _record("svg_tspan_positions", measured)
                self.assertTrue(a_qt and b_qt, [s['text'] for s in qt])
                for hit in (a_qt[0], b_qt[0]):
                    self.assertAlmostEqual(hit['size'], 7.5, delta=0.08)
                self.assertAlmostEqual(a_qt[0]['origin'][0], b_qt[0]['origin'][0], delta=0.02)
                self.assertAlmostEqual(b_qt[0]['origin'][1]-a_qt[0]['origin'][1],
                                       20.0 * mm_per_unit * MM_TO_PT, delta=0.08)
                with open(svg_path, "rb") as fh:
                    self.assertEqual(hashlib.sha256(fh.read()).hexdigest(),
                                     src_hash)
        _record("svg_tspan_positions", measured)
        print("svg tspans:", measured)

    def test_precise_normalize_preserves_positions(self):
        from src.utils.svg_text_utils import normalize_svg_text
        measured = {}
        for svg, elem_id in ((self._SVG_ANCHOR, "anch"),
                             (self._SVG_MULTIX, "multi"),
                             (self._SVG_TSPANS, "svgtxt")):
            src = svg.encode("utf-8")
            out = normalize_svg_text(src, 9.0, unit="px", precise=True)
            before = _svg_mapped_positions(src)
            after = _svg_mapped_positions(out)
            self.assertEqual(len(before), len(after))
            for pts0, pts1 in zip(before, after):
                self.assertEqual(len(pts0), len(pts1))
                for p0, p1 in zip(pts0, pts1):
                    self.assertAlmostEqual(p0[0], p1[0], delta=1e-8)
                    self.assertAlmostEqual(p0[1], p1[1], delta=1e-8)
            measured[elem_id] = {"before": before, "after": after}
        _record("svg_mapped_positions", measured)

    def test_positioned_runs_flatten_only_in_precise_path(self):
        import xml.etree.ElementTree as ET
        from src.utils.svg_text_utils import (
            _positioned_text_runs, apply_svg_font_overrides_from_bytes,
            normalize_svg_text)
        src = self._SVG_TSPANS.encode("utf-8")
        legacy = apply_svg_font_overrides_from_bytes(
            src, {"svgtxt": 1.4432}, unit="px")
        self.assertIn(b"<tspan", legacy)
        text_el = [el for el in ET.fromstring(legacy).iter()
                   if el.get("id") == "svgtxt"][0]
        self.assertIsNone(text_el.get("transform"))
        norm = normalize_svg_text(src, 1.4432, unit="px", precise=True)
        self.assertIn(b"<tspan", norm)
        flat = _positioned_text_runs(norm)
        root = ET.fromstring(flat)
        group = [el for el in root.iter()
                 if el.get("id") == "svgtxt"]
        self.assertEqual(len(group), 1)
        self.assertEqual(group[0].tag.rsplit("}", 1)[-1], "g")
        runs = [el for el in group[0]
                if el.tag.rsplit("}", 1)[-1] == "text"]
        self.assertEqual([r.text for r in runs], ["ALPHA", "BETA"])
        inline = ('<svg xmlns="http://www.w3.org/2000/svg" width="100" '
                  'height="50" viewBox="0 0 100 50">'
                  '<text x="5" y="20">H<tspan dy="-2">2</tspan>O</text>'
                  '</svg>').encode("utf-8")
        out = _positioned_text_runs(inline)
        self.assertEqual(out.count(b"<text"), 1)
        self.assertIn(b"<tspan", out)
        unmodified = _positioned_text_runs(inline)
        self.assertEqual(unmodified, inline)

    def test_font_shorthand_keeps_target_size(self):
        import hashlib
        from src.model.data_model import SvgTextGroup, SvgTextMember
        from src.model.layout_engine import LayoutEngine
        from src.utils.svg_text_utils import (
            get_svg_override_bytes_for_cell, svg_mm_per_unit)
        measured = {}
        for page_w in (120, 180):
            with tempfile.TemporaryDirectory() as td:
                svg_path = os.path.join(td, "panel.svg")
                with open(svg_path, "w", encoding="utf-8") as fh:
                    fh.write(self._SVG_SHORTHAND)
                p = _new_points_project(page_width_mm=page_w)
                cell = Cell(row_index=0, col_index=0, image_path=svg_path,
                            is_placeholder=False)
                cell.svg_normalize_text = True
                cell.svg_normalize_text_pt = 9.0
                p.cells = [cell]
                p.rows = [RowTemplate(index=0, column_count=1)]
                layout = LayoutEngine.calculate_layout(p)
                with open(svg_path, "rb") as fh:
                    src_hash = hashlib.sha256(fh.read()).hexdigest()
                mm_per_unit = svg_mm_per_unit(
                    p, cell, self._SVG_SHORTHAND.encode("utf-8"), layout)
                data = get_svg_override_bytes_for_cell(p, cell, layout)
                self.assertIn("italic", data.decode("utf-8"))
                mu = [s for s in _svg_mupdf_spans(data)
                      if "SHORTX" in s["text"]]
                self.assertTrue(mu)
                self.assertAlmostEqual(mu[0]["size"],
                                       9.0 * PT_TO_MM / mm_per_unit,
                                       delta=0.02)
                path = _export_pdf(p)
                try:
                    qt = _pdf_spans(path)
                finally:
                    os.remove(path)
                hit = [s for s in qt if "SHORTX" in s["text"]]
                self.assertTrue(hit, [s["text"] for s in qt])
                self.assertAlmostEqual(hit[0]["size"], 9.0, delta=0.08)
                measured[f"norm_w{page_w}"] = {
                    "qt_size": round(hit[0]["size"], 4),
                    "mu_units": round(mu[0]["size"], 4)}
                g = SvgTextGroup(name="g", font_size_pt=7.5)
                g.members = [SvgTextMember(svg_path=svg_path,
                                           element_key="svgtxt")]
                p.svg_text_groups = [g]
                data = get_svg_override_bytes_for_cell(p, cell, layout)
                self.assertIn("italic", data.decode("utf-8"))
                mu = [s for s in _svg_mupdf_spans(data)
                      if "SHORTX" in s["text"]]
                self.assertTrue(mu)
                self.assertAlmostEqual(mu[0]["size"],
                                       7.5 * PT_TO_MM / mm_per_unit,
                                       delta=0.02)
                path = _export_pdf(p)
                try:
                    qt = _pdf_spans(path)
                finally:
                    os.remove(path)
                hit = [s for s in qt if "SHORTX" in s["text"]]
                self.assertTrue(hit)
                self.assertAlmostEqual(hit[0]["size"], 7.5, delta=0.08)
                measured[f"override_w{page_w}"] = {
                    "qt_size": round(hit[0]["size"], 4),
                    "mu_units": round(mu[0]["size"], 4)}
                with open(svg_path, "rb") as fh:
                    self.assertEqual(
                        hashlib.sha256(fh.read()).hexdigest(), src_hash)
        _record("svg_font_shorthand", measured)
        print("svg shorthand:", measured)


class TestRasterDpiInvariance(unittest.TestCase):

    def test_ink_bbox_stable_across_dpi(self):
        bboxes = []
        for dpi in (150, 300, 600):
            p = _new_points_project(dpi=dpi)
            p.text_items = [TextItem(text="POINTTEST", font_size_pt=8.25,
                                     color="#000000", x=10, y=10)]
            path = _export_png(p)
            try:
                bbox = _ink_bbox_mm(path, dpi)
            finally:
                os.remove(path)
            self.assertIsNotNone(bbox)
            bboxes.append(bbox)
        for w, h in bboxes[1:]:
            self.assertAlmostEqual(w, bboxes[0][0], delta=0.35)
            self.assertAlmostEqual(h, bboxes[0][1], delta=0.35)
        _record("png_ink_bbox_mm",
                [[round(w, 4), round(h, 4)] for w, h in bboxes])
        print("PNG ink bbox mm:", [tuple(round(v, 3) for v in b)
                                   for b in bboxes])

    def test_canvas_zoom_invariance(self):
        from src.canvas.canvas_scene import CanvasScene
        p = _new_points_project()
        p.text_items = [TextItem(text="POINTTEST", font_size_pt=8.25,
                                 color="#000000", x=10, y=10)]
        scene = CanvasScene()
        scene.set_project(p)
        try:
            item = next(iter(scene.text_items.values()))
            item.setSelected(False)
            extents = []
            inks = []
            source = item.sceneBoundingRect().adjusted(-1, -1, 1, 1)
            for zoom in (2, 4, 8):
                sb = item.sceneBoundingRect()
                extents.append((sb.width(), sb.height()))
                px_per_mm = 96 / 25.4 * zoom
                w = max(1, math.ceil(source.width() * px_per_mm))
                h = max(1, math.ceil(source.height() * px_per_mm))
                img = QImage(w, h, QImage.Format.Format_RGB32)
                img.fill(0xFFFFFFFF)
                painter = QPainter(img)
                scene.render(painter, QRectF(0, 0, w, h), source)
                painter.end()
                xs, ys = [], []
                for yy in range(h):
                    for xx in range(w):
                        if (img.pixel(xx, yy) & 0xFFFFFF) != 0xFFFFFF:
                            xs.append(xx)
                            ys.append(yy)
                self.assertTrue(xs)
                ink_w = (max(xs) - min(xs) + 1) / px_per_mm
                ink_h = (max(ys) - min(ys) + 1) / px_per_mm
                self.assertLess(ink_w, 50.0)
                inks.append((ink_w, ink_h))
            for w, h in extents[1:]:
                self.assertAlmostEqual(w, extents[0][0], delta=0.01)
                self.assertAlmostEqual(h, extents[0][1], delta=0.01)
            for w, h in inks[1:]:
                self.assertAlmostEqual(w, inks[0][0], delta=0.35)
                self.assertAlmostEqual(h, inks[0][1], delta=0.35)
            _record("canvas_ink_mm",
                    [[round(w, 4), round(h, 4)] for w, h in inks])
            print("canvas ink mm:", [tuple(round(v, 3) for v in b)
                                     for b in inks])
        finally:
            scene.clear()
            scene.deleteLater()
            _app.processEvents()


class TestCanvasInteraction(unittest.TestCase):

    def _release(self, item):
        from PyQt6.QtWidgets import QGraphicsTextItem
        ev = unittest.mock.MagicMock()
        with unittest.mock.patch.object(
                QGraphicsTextItem, "mouseReleaseEvent", lambda s, e: None):
            item.mouseReleaseEvent(ev)

    def test_anchored_release_offsets_ignore_background(self):
        from src.canvas.canvas_scene import CanvasScene
        p = _new_points_project()
        cell = Cell(row_index=0, col_index=0)
        cell.is_placeholder = True
        p.cells = [cell]
        p.rows = [RowTemplate(index=0, column_count=1)]
        t = TextItem(text="ANCH", font_size_pt=8.25, scope="cell",
                     parent_id=cell.id, subtype="numbering",
                     anchor="bottom_right_inside",
                     offset_x=2.0, offset_y=3.0)
        t.bg_enabled = True
        t.bg_padding_mm = 0.6
        p.text_items = [t]
        scene = CanvasScene()
        scene.set_project(p)
        try:
            item = scene.text_items[t.id]
            captured = []
            item.item_changed.connect(lambda _tid, d: captured.append(d))
            self._release(item)
            self.assertTrue(captured)
            self.assertAlmostEqual(captured[-1]["offset_x"], 2.0)
            self.assertAlmostEqual(captured[-1]["offset_y"], 3.0)
            item.setPos(item.pos() + QPointF(1, 2))
            self._release(item)
            self.assertAlmostEqual(captured[-1]["offset_x"], 1.0)
            self.assertAlmostEqual(captured[-1]["offset_y"], 1.0)
            t.offset_x = 1.0
            t.offset_y = 1.0
            scene.refresh_layout()
            item = scene.text_items[t.id]
            cx, cy, cw, ch = item.cell_bounds
            scale = item.scale()
            text_w = item.content_rect().width() * scale
            text_h = item.content_rect().height() * scale
            self.assertAlmostEqual(item.pos().x(), cx + cw - 1.0 - text_w)
            self.assertAlmostEqual(item.pos().y(), cy + ch - 1.0 - text_h)
        finally:
            scene.clear()
            scene.deleteLater()
            _app.processEvents()

    def test_global_move_and_serialization(self):
        from src.canvas.canvas_scene import CanvasScene
        p = _new_points_project()
        t = TextItem(text="MOVE", font_size_pt=8.25, x=20.0, y=15.0)
        p.text_items = [t]
        scene = CanvasScene()
        scene.set_project(p)
        try:
            item = scene.text_items[t.id]
            captured = []
            item.item_changed.connect(lambda _tid, d: captured.append(d))
            self._release(item)
            self.assertTrue(captured)
            self.assertAlmostEqual(captured[-1]["x"], 20.0)
            self.assertAlmostEqual(captured[-1]["y"], 15.0)
            item.setPos(item.pos() + QPointF(3, 4))
            self._release(item)
            self.assertAlmostEqual(captured[-1]["x"], 23.0)
            self.assertAlmostEqual(captured[-1]["y"], 19.0)
        finally:
            scene.clear()
            scene.deleteLater()
            _app.processEvents()
        t.x = 23.0
        t.y = 19.0
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "p.json")
            p.save_to_file(f)
            p2 = Project.load_from_file(f)
        self.assertAlmostEqual(p2.text_items[0].x, 23.0)
        self.assertAlmostEqual(p2.text_items[0].y, 19.0)

    def test_tohtml_save_load_no_reference_leak(self):
        from src.canvas.canvas_scene import CanvasScene
        p = _new_points_project()
        t = TextItem(text='<p style="font-size:24pt"><b>POINTTEST</b></p>',
                     font_size_pt=8.25, x=10, y=10)
        p.text_items = [t]
        with tempfile.TemporaryDirectory() as td:
            for _ in range(2):
                scene = CanvasScene()
                scene.set_project(p)
                item = scene.text_items[p.text_items[0].id]
                p.text_items[0].text = item.toHtml()
                scene.clear()
                scene.deleteLater()
                _app.processEvents()
                f = os.path.join(td, "p.json")
                p.save_to_file(f)
                p = Project.load_from_file(f)
            t = p.text_items[0]
            self.assertAlmostEqual(t.x, 10.0)
            self.assertAlmostEqual(t.y, 10.0)
            self.assertAlmostEqual(t.font_size_pt, 8.25)
            path = _export_pdf(p)
            try:
                spans = _find_span(_pdf_spans(path), "POINTTEST")
            finally:
                os.remove(path)
        self.assertTrue(spans)
        self.assertAlmostEqual(spans[0]["size"], 8.25, delta=0.08)

    def test_math_pixmap_drawn_at_fractional_rect(self):
        try:
            import matplotlib
        except ImportError:
            self.skipTest("matplotlib unavailable for math text")
        from src.canvas.text_graphics_item import TextGraphicsItem
        item = TextGraphicsItem("m", "$x^2$")
        item.update_style("Arial", 9.0, "normal", "#000000",
                          typography_mode="points")
        self.assertIsNotNone(item._math_pixmap)
        self.assertIsNotNone(item._math_rect)
        painter = unittest.mock.MagicMock()
        item.paint(painter, None, None)
        calls = [c for c in painter.mock_calls if c[0] == "drawPixmap"]
        self.assertTrue(calls)
        dest = calls[0].args[0]
        self.assertIsInstance(dest, QRectF)
        self.assertEqual(dest, item._math_rect)
        _record("math_rect", [item._math_rect.x(), item._math_rect.y(),
                              item._math_rect.width(),
                              item._math_rect.height()])


class TestInspectorUi(unittest.TestCase):

    def _inspector(self):
        from src.app.inspector import Inspector
        ins = Inspector()
        self.addCleanup(ins.deleteLater)
        self.addCleanup(_app.processEvents)
        return ins

    def test_fractional_font_values_preserved(self):
        ins = self._inspector()
        for spin in (ins.font_size, ins.label_size, ins.gl_size_spin,
                     ins.corner_label_size, ins.title_label_size,
                     ins.scale_bar_text_size):
            spin.setValue(8.25)
            self.assertAlmostEqual(spin.value(), 8.25)
            spin.setValue(7.5)
            self.assertAlmostEqual(spin.value(), 7.5)

    def test_mode_switch_updates_labels(self):
        from src.app.i18n import tr
        ins = self._inspector()
        ins.set_typography_mode("points")
        self.assertEqual(ins.font_size.suffix(), " pt")
        self.assertTrue(ins.typography_notice.isHidden())
        self.assertEqual(ins.typography_mode_value.text(),
                         tr("typography_points"))
        ins.set_typography_mode("legacy")
        self.assertEqual(ins.font_size.suffix(), tr("typography_legacy_suffix"))
        self.assertFalse(ins.typography_notice.isHidden())
        self.assertEqual(ins.scale_bar_text_size.suffix(),
                         tr("typography_legacy_suffix"))
        self.assertEqual(ins.svg_normalize_pt.suffix(),
                         tr("typography_source_pt_suffix"))

    def test_set_selection_consumes_mode(self):
        ins = self._inspector()
        ins.set_typography_mode("legacy")
        ins.set_selection("text", {"font_size_pt": 8.25},
                          project_data={"typography_mode": "points"})
        self.assertEqual(ins._typography_mode, "points")
        self.assertAlmostEqual(ins.font_size.value(), 8.25)
        ins.set_typography_mode("legacy")
        ins.set_selection("text", {"font_size_pt": 4})
        self.assertEqual(ins._typography_mode, "legacy")

    def test_math_text_keeps_pt_suffix_in_legacy(self):
        ins = self._inspector()
        ins.set_typography_mode("legacy")
        ins.set_selection("text", {"text": "$x^2$", "font_size_pt": 9.0,
                                   "scope": "global"})
        self.assertEqual(ins.font_size.suffix(), " pt")
        ins.set_selection("text", {"text": "plain", "font_size_pt": 4.0,
                                   "scope": "global"})
        self.assertNotEqual(ins.font_size.suffix(), " pt")

    def test_math_suffix_survives_retranslate(self):
        from src.app.i18n import set_language, tr
        ins = self._inspector()
        emissions = []
        ins.text_property_changed.connect(lambda d: emissions.append(d))
        try:
            for lang in ("en", "zh"):
                set_language(lang)
                ins.retranslate_ui()
                ins.set_typography_mode("legacy")
                ins.set_selection("text", {"text": "$x^2$",
                                           "font_size_pt": 9.0,
                                           "scope": "global"})
                self.assertEqual(ins.font_size.suffix(), " pt")
                ins.retranslate_ui()
                self.assertEqual(ins.font_size.suffix(), " pt")
                ins.set_selection("text", {"text": "plain",
                                           "font_size_pt": 4.0,
                                           "scope": "global"})
                self.assertEqual(ins.font_size.suffix(),
                                 tr("typography_legacy_suffix"))
        finally:
            set_language("en")
        self.assertEqual(emissions, [])

    def test_mode_and_language_emit_no_signals(self):
        from src.app.i18n import set_language
        ins = self._inspector()
        emissions = []
        for sig in (ins.text_property_changed, ins.project_property_changed,
                    ins.cell_property_changed):
            sig.connect(lambda d: emissions.append(d))
        try:
            for lang in ("en", "zh"):
                set_language(lang)
                ins.retranslate_ui()
                ins.set_typography_mode("legacy")
                ins.retranslate_ui()
                ins.set_typography_mode("points")
        finally:
            set_language("en")
        self.assertEqual(emissions, [])


class TestPersistence(unittest.TestCase):

    def test_plain_roundtrip(self):
        p = _new_points_project()
        p.label_font_size = 8.25
        p.text_items = [TextItem(text="T", font_size_pt=7.5)]
        p.cells = [Cell(row_index=0, col_index=0)]
        p.cells[0].scale_bar_text_size_pt = 8.25
        p.rows = [RowTemplate(index=0, column_count=1)]
        with tempfile.TemporaryDirectory() as td:
            f = os.path.join(td, "proj.json")
            p.save_to_file(f)
            p2 = Project.load_from_file(f)
        self.assertEqual(p2.typography_mode, "points")
        self.assertAlmostEqual(p2.label_font_size, 8.25)
        self.assertAlmostEqual(p2.text_items[0].font_size_pt, 7.5)
        self.assertAlmostEqual(
            p2.get_all_leaf_cells()[0].scale_bar_text_size_pt, 8.25)

    def test_bundle_roundtrip(self):
        from src.utils.figpack import open_bundle, pack_project
        p = _new_points_project()
        p.label_font_size = 8.25
        p.text_items = [TextItem(text="T", font_size_pt=7.5)]
        with tempfile.TemporaryDirectory() as td:
            pack_path = os.path.join(td, "proj.figpack")
            pack_project(p, pack_path)
            wd, result = open_bundle(pack_path, cache_root=td)
            try:
                p2 = Project.from_dict(result.project_data,
                                       project_dir=result.target_dir)
            finally:
                wd.release()
        self.assertEqual(p2.typography_mode, "points")
        self.assertAlmostEqual(p2.label_font_size, 8.25)
        self.assertAlmostEqual(p2.text_items[0].font_size_pt, 7.5)


class TestAgentValidation(unittest.TestCase):

    def _ctx(self, mode="points"):
        from src.agent.tools import ToolContext
        p = _new_points_project()
        p.typography_mode = mode
        cell = Cell(row_index=0, col_index=0)
        p.cells = [cell]
        p.rows = [RowTemplate(index=0, column_count=1)]
        return ToolContext(project=p), p, cell

    def test_font_size_validation(self):
        from src.agent.tools import ToolError, text_add
        ctx, p, _ = self._ctx()
        for bad in (0, -1, float("nan"), float("inf"), True, "12"):
            with self.assertRaises(ToolError, msg=f"bad={bad!r}"):
                text_add(ctx, "x", font_size_pt=bad)
        res = text_add(ctx, "x", font_size_pt=8.25)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(p.text_items[-1].font_size_pt, 8.25)

    def test_scale_bar_mode_gating(self):
        from src.agent.tools import (
            ToolError, cell_set_scale_bar, pip_set_properties,
        )
        ctx, p, cell = self._ctx("points")
        pip = PiPItem(pip_type="external")
        cell.pip_items = [pip]
        with self.assertRaises(ToolError):
            cell_set_scale_bar(ctx, cell.id, text_size_mm=2.0)
        res = cell_set_scale_bar(ctx, cell.id, text_size_pt=8.25)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(cell.scale_bar_text_size_pt, 8.25)
        with self.assertRaises(ToolError):
            pip_set_properties(ctx, pip.id, scale_bar_text_size_mm=2.0)
        res = pip_set_properties(ctx, pip.id, scale_bar_text_size_pt=7.5)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(pip.scale_bar_text_size_pt, 7.5)

        ctx2, p2, cell2 = self._ctx("legacy")
        with self.assertRaises(ToolError):
            cell_set_scale_bar(ctx2, cell2.id, text_size_pt=8.0)
        res = cell_set_scale_bar(ctx2, cell2.id, text_size_mm=2.5)
        self.assertTrue(res["ok"])
        self.assertAlmostEqual(cell2.scale_bar_text_size_mm, 2.5)


class TestLegacyPreserved(unittest.TestCase):

    def test_legacy_project_dict_unchanged_values(self):
        d = Project().to_dict()
        d.pop("typography_mode")
        d["schema_version"] = 3
        d["label_font_size"] = 3
        d["text_items"] = [{"id": "t1", "text": "LEGACY", "font_size_pt": 3,
                            "x": 12, "y": 65, "scope": "global"}]
        p = Project.from_dict(copy.deepcopy(d))
        self.assertEqual(p.typography_mode, "legacy")
        self.assertEqual(p.label_font_size, 3)
        self.assertEqual(p.text_items[0].font_size_pt, 3)
        out = p.to_dict()
        self.assertEqual(out["schema_version"], 4)
        self.assertEqual(out["typography_mode"], "legacy")
        self.assertEqual(out["label_font_size"], 3)


if __name__ == "__main__":
    unittest.main()
