"""Non-UI checks for the optional per-element style schema and renderer."""

import os
import tempfile
import unittest
import xml.etree.ElementTree as ET

from src.plot_editor import render
from src.plot_editor.document import (AxisStyle, FrameStyle, GridStyle,
                                      LegendStyle, LineSeries,
                                      PlotDocument, PlotDocumentError,
                                      PlotStyle, TextStyle, TitleStyle)

FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        'test_fixtures')


def full_style():
    st = PlotStyle()
    st.title = TitleStyle(family='DejaVu Sans', size_pt=14, bold=True,
                          italic=True, underline=True, color='#112233',
                          align='left')
    st.xlabel = TextStyle(size_pt=9, italic=True, color='#223344')
    st.ylabel = TextStyle(bold=True, color='#334455')
    st.xaxis = AxisStyle(
        ticks=TextStyle(size_pt=7, bold=True, color='#445566'),
        rotation=30, prefix='~', suffix='u', decimals=2, step=0.5,
        minor=True, direction='in', length_pt=5, scale='linear',
        reversed=False)
    st.yaxis = AxisStyle(rotation=-20, suffix='%', decimals=1,
                         minor=True, direction='inout', length_pt=2,
                         scale='linear', reversed=True)
    st.grid = GridStyle(axis='x', which='both', color='#123456',
                        linestyle='--', linewidth_pt=0.7, alpha=0.9)
    st.legend = LegendStyle(frame=True, frame_color='#654321', ncols=2,
                            text=TextStyle(size_pt=6, italic=True,
                                           color='#777777'))
    st.frame = FrameStyle(color='#990000', linewidth_pt=1.2,
                          hide_top=True, hide_right=True)
    return st


def full_doc():
    doc = PlotDocument()
    doc.title = 'Styled'
    doc.series = [LineSeries(id='a', label='A', x=[0., 1., 2.],
                             y=[0., 1., 0.]),
                  LineSeries(id='b', label='B', x=[0., 1., 2.],
                             y=[1., 0., 1.])]
    doc.style = full_style()
    doc.validate()
    return doc


def build(doc):
    """``_build_figure`` + an Agg draw so ticks/labels materialize."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    fig, ax = render._build_figure(doc, 1.0, doc.width_mm,
                                   doc.height_mm)
    FigureCanvasAgg(fig)
    fig.canvas.draw()
    return fig, ax


class SchemaTests(unittest.TestCase):

    def test_full_roundtrip(self):
        doc = full_doc()
        out = PlotDocument.from_dict(doc.to_dict())
        self.assertEqual(out.style.to_dict(), doc.style.to_dict())

    def test_empty_style_omitted(self):
        doc = PlotDocument()
        self.assertNotIn('style', doc.to_dict())
        doc.style = PlotStyle()
        self.assertNotIn('style', doc.to_dict())

    def test_partial_style_emits_only_set_keys(self):
        doc = PlotDocument()
        doc.style = PlotStyle()
        doc.style.xaxis = AxisStyle(rotation=45)
        d = doc.to_dict()['style']
        self.assertEqual(d, {'xaxis': {'rotation': 45.0}})

    def test_default_subobject_omitted(self):
        doc = PlotDocument()
        doc.style = PlotStyle()
        doc.style.grid = GridStyle()  # all defaults → not emitted
        self.assertNotIn('style', doc.to_dict())

    def test_strictness(self):
        base = full_doc().to_dict()
        cases = [
            {'style': 7},
            {'style': {'bogus': 1}},
            {'style': {'title': {'align': 'middle'}}},
            {'style': {'title': {'size_pt': 0}}},
            {'style': {'title': {'size_pt': float('nan')}}},
            {'style': {'title': {'family': ''}}},
            {'style': {'title': {'family': 'x' * 101}}},
            {'style': {'title': {'bold': 'yes'}}},
            {'style': {'title': {'color': 'notacolor'}}},
            {'style': {'xaxis': {'rotation': 91}}},
            {'style': {'xaxis': {'decimals': -1}}},
            {'style': {'xaxis': {'decimals': 11}}},
            {'style': {'xaxis': {'decimals': 1.5}}},
            {'style': {'xaxis': {'step': 0}}},
            {'style': {'xaxis': {'step': float('inf')}}},
            {'style': {'xaxis': {'direction': 'side'}}},
            {'style': {'xaxis': {'length_pt': 21}}},
            {'style': {'xaxis': {'scale': 'sqrt'}}},
            {'style': {'xaxis': {'prefix': 'x' * 51}}},
            {'style': {'grid': {'axis': 'z'}}},
            {'style': {'grid': {'which': 'minor'}}},
            {'style': {'grid': {'linestyle': ''}}},
            {'style': {'grid': {'linewidth_pt': 0}}},
            {'style': {'grid': {'alpha': 1.5}}},
            {'style': {'legend': {'ncols': 0}}},
            {'style': {'legend': {'ncols': 11}}},
            {'style': {'legend': {'frame': 'no'}}},
            {'style': {'frame': {'linewidth_pt': -1}}},
        ]
        for patch in cases:
            data = dict(base)
            data.update(patch)
            with self.assertRaises(PlotDocumentError, msg=repr(patch)):
                PlotDocument.from_dict(data)

    def test_validate_rejects_bad_live_style(self):
        doc = full_doc()
        doc.style.xaxis.rotation = 200.0
        with self.assertRaises(PlotDocumentError):
            doc.validate()

    def test_clone_independence(self):
        doc = full_doc()
        clone = doc.clone()
        clone.style.title.color = '#ff0000'
        self.assertEqual(doc.style.title.color, '#112233')
        self.assertNotEqual(clone.to_dict(), doc.to_dict())


class GoldenTests(unittest.TestCase):

    def test_default_bytes_unchanged(self):
        doc = PlotDocument()
        doc.series[0].id = 'golden-fixed-id'
        golden = open(os.path.join(
            FIXTURES, 'golden_style_default.ilmplot.svg'), 'rb').read()
        self.assertEqual(render.render_document(doc).svg, golden)

    def test_filled_bytes_unchanged(self):
        doc = PlotDocument()
        doc.title = 'T'; doc.xlabel = 'XL'; doc.ylabel = 'YL'
        doc.width_mm = 120; doc.height_mm = 80
        doc.axes_rect = [.2, .15, .7, .75]
        doc.font_family = 'DejaVu Serif'; doc.font_size_pt = 9.5
        doc.title_size_pt = 12; doc.xlim = [0, 5]; doc.ylim = [-1, 2]
        doc.legend = True; doc.legend_location = 'upper left'
        doc.grid = True
        doc.series = [
            LineSeries(id='s0', label='A', x=[0., 1., 2.],
                       y=[0., 1., 0.5], color='#ff0000ff',
                       linewidth_pt=2.0, linestyle='--', marker='o',
                       markersize_pt=5.0),
            LineSeries(id='s1', label='B', x=[0., 2.], y=[1., 0.],
                       color='#00ff00')]
        golden = open(os.path.join(
            FIXTURES, 'golden_style_filled.ilmplot.svg'), 'rb').read()
        self.assertEqual(render.render_document(doc).svg, golden)


class RenderTests(unittest.TestCase):

    def test_text_styles_applied(self):
        doc = full_doc()
        _fig, ax = build(doc)
        title = ax._left_title  # align='left' moves the artist
        self.assertEqual(title.get_fontweight(), 'bold')
        self.assertEqual(title.get_fontstyle(), 'italic')
        self.assertEqual(title.get_fontsize(), 14.0)
        self.assertEqual(title.get_color(), '#112233')
        self.assertEqual(title.get_ha(), 'left')
        self.assertEqual(ax.xaxis.label.get_fontstyle(), 'italic')
        self.assertEqual(ax.yaxis.label.get_fontweight(), 'bold')

    def test_tick_style_rotation_anchor(self):
        doc = full_doc()
        _fig, ax = build(doc)
        lab = ax.get_xticklabels()[0]
        self.assertEqual(lab.get_fontweight(), 'bold')
        self.assertEqual(lab.get_color(), '#445566')
        self.assertEqual(lab.get_rotation(), 30)
        self.assertEqual(lab.get_ha(), 'right')

    def test_affix_and_decimals(self):
        doc = full_doc()
        doc.xlim = [0, 2]
        _fig, ax = build(doc)
        texts = [t.get_text() for t in ax.get_xticklabels()]
        self.assertTrue(all(t.startswith('~') and t.endswith('u')
                            for t in texts if t))
        self.assertTrue(all('.' in t and
                            len(t.split('.')[1][:-1]) == 2
                            for t in texts if t and '.' in t))
        ytexts = [t.get_text() for t in ax.get_yticklabels()]
        self.assertTrue(all(t.endswith('%') for t in ytexts if t))

    def test_step_locator(self):
        doc = full_doc()
        doc.xlim = [0, 2]
        _fig, ax = build(doc)
        ticks = [t for t in ax.get_xticks()]
        self.assertTrue(all(abs(t / 0.5 - round(t / 0.5)) < 1e-9
                            for t in ticks))

    def test_minor_locator(self):
        from matplotlib.ticker import AutoMinorLocator
        doc = full_doc()
        _fig, ax = build(doc)
        self.assertIsInstance(ax.xaxis.get_minor_locator(),
                              AutoMinorLocator)

    def test_log_scale(self):
        doc = full_doc()
        doc.style.xaxis.scale = 'log'
        doc.series = [LineSeries(id='a', x=[1., 10., 100.],
                                 y=[1., 2., 3.])]
        _fig, ax = build(doc)
        self.assertEqual(ax.get_xscale(), 'log')

    def test_reversed_y(self):
        doc = full_doc()
        _fig, ax = build(doc)
        self.assertTrue(ax.yaxis_inverted())
        self.assertFalse(ax.xaxis_inverted())

    def test_grid_style(self):
        doc = full_doc()
        doc.grid = True
        _fig, ax = build(doc)
        gridlines = ax.xaxis.get_gridlines()
        self.assertTrue(any(g.get_visible() for g in gridlines))
        g = next(g for g in gridlines if g.get_visible())
        self.assertEqual(g.get_color(), '#123456')
        self.assertEqual(g.get_linestyle(), '--')
        self.assertAlmostEqual(g.get_alpha(), 0.9)

    def test_legend_style(self):
        doc = full_doc()
        _fig, ax = build(doc)
        leg = ax.get_legend()
        self.assertIsNotNone(leg)
        self.assertEqual(leg._ncols, 2)
        self.assertTrue(leg.get_frame().get_visible())
        txt = leg.get_texts()[0]
        from matplotlib.colors import to_hex
        self.assertEqual(to_hex(txt.get_color()), '#777777')
        self.assertEqual(txt.get_fontstyle(), 'italic')

    def test_frame_style(self):
        doc = full_doc()
        _fig, ax = build(doc)
        self.assertFalse(ax.spines['top'].get_visible())
        self.assertFalse(ax.spines['right'].get_visible())
        from matplotlib.colors import to_hex as _th
        self.assertEqual(_th(ax.spines['left'].get_edgecolor()),
                         '#990000')
        self.assertAlmostEqual(ax.spines['left'].get_linewidth(), 1.2)

    def test_underline_draws(self):
        doc = full_doc()
        # title/legend underline come from full_style
        svg = render.render_document(doc).svg
        self.assertIn(b'<svg', svg)

    def test_per_element_family_survives_prepare(self):
        fams = render.available_font_families()
        # Prefer a text-capable family distinct from the default.
        other = 'DejaVu Serif' if 'DejaVu Serif' in fams else \
            next((f for f in fams if f != 'DejaVu Sans'), fams[0])
        doc = PlotDocument()
        doc.title = 'Fam'
        doc.style = PlotStyle()
        doc.style.title = TitleStyle(family=other)
        svg = render.render_document(doc).svg
        root = ET.fromstring(svg)
        title_group = None
        for elem in root.iter():
            if elem.get('id') == 'ilmplot-title':
                title_group = elem
                break
        self.assertIsNotNone(title_group)
        texts = [e for e in title_group.iter()
                 if e.tag.rsplit('}', 1)[-1] == 'text']
        self.assertTrue(any(t.get('font-family') == other
                            for t in texts))


class RegionTests(unittest.TestCase):

    def test_regions_keys_and_bounds(self):
        doc = full_doc()
        doc.grid = True
        regions = render.element_regions(doc)
        for key in ('title', 'xlabel', 'ylabel', 'xticks', 'yticks',
                    'legend', 'frame', 'grid', 'series'):
            self.assertIn(key, regions)
        for key, bb in regions.items():
            if key == 'series':
                continue
            x0, y0, x1, y1 = bb
            self.assertTrue(-0.05 <= x0 < x1 <= 1.05, (key, bb))
            self.assertTrue(-0.05 <= y0 < y1 <= 1.05, (key, bb))
        self.assertEqual(set(regions['series']), {'a', 'b'})
        for sid, info in regions['series'].items():
            self.assertLessEqual(len(info['points']), 2000)
            self.assertTrue(info['points'])

    def test_decimation(self):
        doc = PlotDocument()
        doc.series[0].x = list(range(5000))
        doc.series[0].y = [0.] * 5000
        regions = render.element_regions(doc)
        pts = regions['series'][doc.series[0].id]['points']
        self.assertLessEqual(len(pts), 2000)
        self.assertGreater(len(pts), 1500)

    def test_title_region_matches_svg(self):
        doc = PlotDocument()
        doc.series[0].id = 'fixed'
        doc.title = 'Where Is The Title'
        regions = render.element_regions(doc)
        svg = render.render_document(doc).svg
        root = ET.fromstring(svg)
        vb = [float(v) for v in
              root.get('viewBox').split()]
        W, H = vb[2], vb[3]
        title_text = None
        for elem in root.iter():
            if elem.get('id') == 'ilmplot-title':
                for node in elem.iter():
                    if node.tag.rsplit('}', 1)[-1] == 'text':
                        title_text = node
                        break
        self.assertIsNotNone(title_text)
        import re as _re
        tr = title_text.get('transform') or ''
        m = _re.search(r'translate\(([-\d. ]+)\)', tr)
        tx, ty = (float(v) for v in m.group(1).split()) if m else (0, 0)
        m = _re.search(r'scale\(([-\d.]+)\)', tr)
        sc = float(m.group(1)) if m else 1.0
        x = float(title_text.get('x', 0))
        y = float(title_text.get('y', 0))
        fx = (tx + sc * x) / W
        fy = (ty + sc * y) / H
        x0, y0, x1, y1 = regions['title']
        # Point is the title text position (top-origin svg units):
        # within ~1% of the figure around the measured bbox.
        self.assertTrue(x0 - 0.01 <= fx <= x1 + 0.01, (fx, regions['title']))
        self.assertTrue(y0 - 0.02 <= fy <= y1 + 0.02, (fy, regions['title']))


class AffixFormatterTests(unittest.TestCase):
    """_AffixFormatter must be a real Formatter: tick labels keep their
    numbers (no bare prefix+suffix)."""

    def _labels(self, *, prefix='', suffix='', decimals=None,
                scale='linear', categorical=False, axis='x'):
        doc = PlotDocument()
        if categorical:
            doc.series = [LineSeries(id='a', label='A',
                                     x=[1., 2., 3.], y=[0., 1., 0.])]
            doc.x_tick_labels = [[1., 'One'], [2., 'Two'], [3., 'Three']]
        else:
            doc.series = [LineSeries(id='a', label='A',
                                     x=[0., 1., 2.], y=[1., 10., 100.])]
        st = AxisStyle(prefix=prefix, suffix=suffix, decimals=decimals,
                       scale=scale)
        doc.style = PlotStyle()
        if axis == 'x':
            doc.style.xaxis = st
        else:
            doc.style.yaxis = st
        doc.validate()
        fig, ax = build(doc)
        labels = (ax.get_xticklabels() if axis == 'x'
                  else ax.get_yticklabels())
        return [l.get_text() for l in labels if l.get_text()]

    def test_numeric_prefix_suffix(self):
        texts = self._labels(prefix='t=', suffix=' s')
        self.assertTrue(texts)
        for t in texts:
            self.assertTrue(t.startswith('t='), t)
            self.assertTrue(t.endswith(' s'), t)
            self.assertTrue(any(c.isdigit() for c in t), t)

    def test_decimals(self):
        texts = self._labels(decimals=2)
        self.assertTrue(texts)
        for t in texts:
            self.assertIn('.', t)
            self.assertEqual(len(t.rsplit('.', 1)[1]), 2, t)

    def test_categorical_keeps_labels(self):
        texts = self._labels(prefix='[', suffix=']', categorical=True)
        self.assertEqual(texts, ['[One]', '[Two]', '[Three]'])

    def test_log_axis(self):
        texts = self._labels(prefix='>', scale='log', axis='y')
        self.assertTrue(texts)
        for t in texts:
            self.assertIn('>', t)
            self.assertTrue(any(c.isdigit() for c in t), t)


class ClipSeriesTests(unittest.TestCase):

    def test_fully_inside(self):
        xs, ys, mask = render.clip_series_to_view(
            [0, 1, 2], [0, 1, 0], (0, 2), (-1, 1))
        self.assertEqual(xs, [0, 1, 2])
        self.assertEqual(ys, [0, 1, 0])
        self.assertEqual(mask, [True, True, True])

    def test_fully_outside(self):
        xs, ys, mask = render.clip_series_to_view(
            [0, 1, 2], [5, 6, 5], (0, 2), (-1, 1))
        self.assertEqual(xs, [])
        self.assertEqual(mask, [])

    def test_crossing_segment_interpolates(self):
        xs, ys, mask = render.clip_series_to_view(
            [0, 2], [0, 2], (0, 2), (0, 1))
        # segment (0,0)-(2,2) clipped at y=1 → endpoint (1,1), then a
        # NaN break where the line leaves the box.
        self.assertEqual(xs[:2], [0, 1])
        self.assertEqual(ys[:2], [0, 1])
        self.assertEqual(mask[:2], [True, False])

    def test_nan_break_on_exit_and_reentry(self):
        xs, ys, mask = render.clip_series_to_view(
            [0, 1, 2, 3], [0, 5, 0, 0], (0, 3), (-1, 1))
        i = next(i for i, v in enumerate(xs) if v != v)  # nan
        self.assertTrue(any(v != v for v in xs))
        self.assertFalse(mask[i])
        # the re-entered tail continues after the break
        self.assertTrue(mask[-1])

    def test_log_axis(self):
        xs, ys, mask = render.clip_series_to_view(
            [1, 10, 100], [1, 2, 3], (1, 10), (0, 10),
            xlog=True, ylog=False)
        xs = [v for v in xs if v == v]
        self.assertEqual(xs[0], 1)
        self.assertAlmostEqual(xs[-1], 10)
        self.assertEqual(mask[:2], [True, True])
        # non-positive x on log axis drops out
        xs2, _ys2, mask2 = render.clip_series_to_view(
            [-1, 1, 10], [0, 0, 0], (0.5, 20), (-1, 1), xlog=True)
        self.assertNotIn(-1, xs2)
        self.assertEqual(xs2, [1, 10])
        self.assertEqual(mask2, [True, True])

    def test_render_clips_to_xlim(self):
        doc = PlotDocument()
        doc.series = [LineSeries(id='a', label='A', marker='o',
                                 x=[0., 1., 2., 3., 4.],
                                 y=[0., 1., 0., 1., 0.])]
        doc.xlim = [1.0, 3.0]
        doc.validate()
        fig, ax = build(doc)
        xs = [v for v in ax.lines[0].get_xdata() if v == v]
        self.assertTrue(all(1.0 - 1e-9 <= v <= 3.0 + 1e-9
                            for v in xs), xs)
        self.assertEqual(xs[0], 1.0)
        self.assertEqual(xs[-1], 3.0)
        self.assertIsNotNone(ax.lines[0].get_markevery())

    def test_no_limits_keeps_full_data(self):
        doc = PlotDocument()
        doc.series = [LineSeries(id='a', label='A',
                                 x=[0., 1., 2.], y=[0., 1., 0.])]
        doc.validate()
        fig, ax = build(doc)
        self.assertEqual(list(ax.lines[0].get_xdata()), [0.0, 1.0, 2.0])
        self.assertIsNone(ax.lines[0].get_markevery())


class ExportDocumentTests(unittest.TestCase):

    def test_all_formats_magic(self):
        doc = full_doc()
        with tempfile.TemporaryDirectory() as d:
            for fmt, magic in (('pdf', b'%PDF'), ('svg', b'<?xml'),
                               ('png', b'\x89PNG'), ('tiff', b'II'),
                               ('jpeg', b'\xff\xd8')):
                path = os.path.join(d, 'o.' + fmt)
                render.export_document(doc, path, fmt)
                with open(path, 'rb') as fh:
                    self.assertTrue(fh.read(8).startswith(magic), fmt)


if __name__ == '__main__':
    unittest.main()
