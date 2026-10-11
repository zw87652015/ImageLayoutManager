"""Effective text sizes of native plots and SVG panels, no Qt.

``svg_text_rows`` / ``svg_text_effective_sizes`` report the point size each
``<text>`` has in the bytes the canvas draws. Reflow ON keeps the document's
sizes at any cell size; Reflow OFF scales with the panel. Byte output of
``get_svg_override_bytes_for_cell`` is pinned by hash.
"""
import hashlib
import os
import re
import tempfile
import unittest
from unittest import mock

import src  # noqa: F401  -- puts packages/ilmplot/src on sys.path

from ilmplot.document import (AxisStyle, Annotation, HeatmapOptions,
                              LegendStyle, LineSeries, PlotDocument,
                              PlotStyle, TextStyle)
from ilmplot.render import render_document

from src.model.data_model import (Cell, Project, SvgTextGroup,
                                  SvgTextMember)
from src.app.i18n import _T as _STRINGS
from src.utils import svg_text_utils as stu
from src.utils.svg_text_utils import (describe_text_sizes,
                                      format_text_size,
                                      get_svg_override_bytes_for_cell,
                                      get_svg_text_elements,
                                      svg_text_effective_sizes,
                                      svg_text_rows)

PLAIN = b"""<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="100mm" height="50mm" viewBox="0 0 100 50">
<g transform="scale(2)"><text id="t1" x="1" y="2" style="font-size:5px">Hi</text></g>
<g transform="translate(3 4)"><g transform="scale(0.5)"><text x="2" y="10" font-size="12">Deep</text></g></g>
<text id="t3" x="5" y="30" style="font: 7px 'DejaVu Sans'">Shorthand</text></svg>"""

HASHES = {
    'reflow_on_120': '179b8f029daf0534916c9ef07b76dcb67d3b9871f8518361169c59237b49bb69',
    'reflow_on_60': '0303065660439ce910e7af1161e8165e1d906d0ddb6718bccddd476dbbdbda26',
    'reflow_off_60': '3d51d475eab74bbd5121681cf510a010bed4ae39687cf762eda15f691fe0a4dc',
    'heat_reflow_on': 'f1223c278e573d9399a7a118aeacfc5f01908075507c63f1d2865999c0230b09',
    'plain_normalize_points': '36f0e342808df82de87aeab5de29db72e2ef4ea2ac996c67384468855aaf7d50',
    'plain_group': 'b99dc70391372c923041c194002ff306ba72d35c2932d3074d5cbe94257d9e4a',
    'plain_normalize_legacy': '1d75173fdb64d4018c6137955e0642fe2a9337c72bd5d766fe367f1ece6ef003',
}


def _mm_stub(project, cell, svg_bytes, layout_result=None,
             content_size_mm=None):
    """Page mm per SVG user unit when the content width is the image width."""
    m = re.search(rb'viewBox="([\d.\s-]+)"', svg_bytes)
    vb_w = float(m.group(1).split()[2]) if m else 1.0
    width = content_size_mm[0] if content_size_mm else 1.0
    return width / vb_w


def _line_doc():
    doc = PlotDocument(
        series=[LineSeries(id='s0', label='Signal', x=[0., 1., 2., 3.],
                           y=[1., 3., 2., 4.])],
        title='Growth', xlabel='Time (s)', ylabel='Signal (mV)',
        legend=True)
    doc.annotations = [Annotation(id='a0', text='peak',
                                  anchor='upper right')]
    return doc


def _styled_doc():
    doc = PlotDocument(
        series=[LineSeries(id='s0', label='Signal', x=[0., 1., 2., 3.],
                           y=[1., 3., 2., 4.])],
        title='Growth', xlabel='Time (s)', ylabel='Signal (mV)',
        legend=True, font_size_pt=9.0, title_size_pt=13.0)
    doc.style = PlotStyle(
        xaxis=AxisStyle(ticks=TextStyle(size_pt=7.0)),
        legend=LegendStyle(text=TextStyle(size_pt=8.0)))
    doc.annotations = [Annotation(id='a0', text='peak',
                                  anchor='upper right')]
    return doc


def _heat_doc():
    return PlotDocument(
        kind='heatmap', series=[], xlabel='columns', ylabel='rows',
        heatmap=HeatmapOptions(values=[[0., 1.], [2., 3.]],
                               colorbar_label='Value'))


def _sizes_by_text(rows):
    return {row['text']: None if row['size_pt'] is None
            else round(row['size_pt'], 4) for row in rows}


class _Fixture(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name
        self.patch = mock.patch.object(stu, 'svg_mm_per_unit', _mm_stub)
        self.patch.start()
        self.project = Project()
        self.project.typography_mode = 'points'

    def tearDown(self):
        self.patch.stop()
        self._tmp.cleanup()

    def write(self, name, data):
        path = os.path.join(self.dir, name)
        with open(path, 'wb') as fh:
            fh.write(data)
        return path

    def native(self, name, doc):
        return self.write(name, render_document(doc).svg)

    def plain(self):
        return self.write('plain.svg', PLAIN)


class ReflowSizeTests(_Fixture):

    def test_reflow_on_sizes_are_fixed_at_any_cell_size(self):
        path = self.native('styled.ilmplot.svg', _styled_doc())
        small = svg_text_rows(self.project,
                              Cell(id='c', image_path=path, plot_reflow=True),
                              None, (60., 40.))
        large = svg_text_rows(self.project,
                              Cell(id='c', image_path=path, plot_reflow=True),
                              None, (150., 90.))
        for rows in (small, large):
            sizes = _sizes_by_text(rows)
            self.assertEqual(sizes['Growth'], 13.0)
            self.assertEqual(sizes['Time (s)'], 9.0)
            self.assertEqual(sizes['Signal (mV)'], 9.0)
            self.assertEqual(sizes['Signal'], 8.0)
            self.assertEqual(sizes['peak'], 9.0)
            ticks = [r['size_pt'] for r in rows
                     if re.fullmatch(r'-?\d+(\.\d+)?', r['text'])]
            self.assertTrue(ticks)
            self.assertEqual({round(v, 4) for v in ticks}, {7.0, 9.0})
        self.assertEqual({round(r['size_pt'], 3) for r in small},
                         {round(r['size_pt'], 3) for r in large})

    def test_default_document_sizes_are_body_10_title_12(self):
        path = self.native('plain_line.ilmplot.svg', _line_doc())
        sizes = _sizes_by_text(svg_text_rows(
            self.project, Cell(id='c', image_path=path, plot_reflow=True),
            None, (60., 40.)))
        self.assertEqual(sizes['Growth'], 12.0)
        self.assertEqual(sizes['Time (s)'], 10.0)
        self.assertEqual(sizes['Signal'], 10.0)

    def test_heatmap_colorbar_label_and_note(self):
        path = self.native('heat.ilmplot.svg', _heat_doc())
        sizes = _sizes_by_text(svg_text_rows(
            self.project, Cell(id='c', image_path=path, plot_reflow=True),
            None, (90., 65.)))
        self.assertEqual(sizes['Value'], 10.0)
        self.assertEqual(sizes['columns'], 10.0)

    def test_reflow_off_scales_with_the_panel(self):
        path = self.native('styled.ilmplot.svg', _styled_doc())
        cell = Cell(id='c', image_path=path, plot_reflow=False)
        narrow = _sizes_by_text(svg_text_rows(self.project, cell, None,
                                              (60., 40.)))
        wide = _sizes_by_text(svg_text_rows(self.project, cell, None,
                                            (120., 80.)))
        self.assertAlmostEqual(wide['Growth'], 2 * narrow['Growth'], 3)
        self.assertAlmostEqual(wide['Time (s)'], 2 * narrow['Time (s)'], 3)


class PlainSvgTests(_Fixture):

    def test_nested_transform_and_units(self):
        path = self.plain()
        rows = svg_text_rows(self.project, Cell(id='c', image_path=path),
                             None, (100., 50.))
        sizes = {row['key']: row['size_pt'] for row in rows}
        self.assertAlmostEqual(sizes['t1'], 10.0 * 72 / 25.4, 6)
        self.assertAlmostEqual(sizes['_pos_1'], 6.0 * 72 / 25.4, 6)
        self.assertAlmostEqual(sizes['t3'], 7.0 * 72 / 25.4, 6)

    def test_keys_match_get_svg_text_elements(self):
        path = self.plain()
        rows = svg_text_rows(self.project, Cell(id='c', image_path=path),
                             None, (100., 50.))
        self.assertEqual([row['key'] for row in rows],
                         [e['key'] for e in get_svg_text_elements(path)])

    def test_normalize_sets_target_points(self):
        path = self.plain()
        cell = Cell(id='c', image_path=path, svg_normalize_text=True,
                    svg_normalize_text_pt=8.0)
        sizes = svg_text_effective_sizes(self.project, cell, None,
                                         (100., 50.))
        self.assertEqual(sorted(set(round(v, 6) for v in sizes.values())),
                         [8.0])
        self.assertEqual(set(sizes), {'t1', '_pos_1', 't3'})

    def test_group_override_size_is_reported(self):
        path = self.plain()
        self.project.svg_text_groups = [SvgTextGroup(
            id='g', name='G', font_size_pt=9.0,
            members=[SvgTextMember(svg_path=path, element_key='t1')])]
        sizes = svg_text_effective_sizes(
            self.project, Cell(id='c', image_path=path), None, (100., 50.))
        self.assertAlmostEqual(sizes['t1'], 9.0, 6)
        self.assertAlmostEqual(sizes['_pos_1'], 6.0 * 72 / 25.4, 6)

    def test_unknown_units_are_omitted_not_guessed(self):
        path = self.write('odd.svg', b'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10" width="10mm" height="10mm"><text id="a" style="font-size:large">x</text><text id="b" font-size="2em">y</text></svg>')
        sizes = svg_text_effective_sizes(
            self.project, Cell(id='c', image_path=path), None, (10., 10.))
        self.assertEqual(sizes, {})
        rows = svg_text_rows(self.project, Cell(id='c', image_path=path),
                             None, (10., 10.))
        self.assertEqual([row['key'] for row in rows], ['a', 'b'])

    def test_missing_or_non_svg_gives_no_rows(self):
        self.assertEqual(svg_text_rows(
            self.project, Cell(id='c', image_path=os.path.join(self.dir,
                                                              'nope.svg')),
            None, (10., 10.)), [])
        self.assertEqual(svg_text_rows(
            self.project, Cell(id='c', image_path='x.png'), None,
            (10., 10.)), [])


class KeyParityTests(_Fixture):

    def test_reflow_off_native_keys_equal_stored_snapshot(self):
        path = self.native('styled.ilmplot.svg', _styled_doc())
        rows = svg_text_rows(self.project,
                             Cell(id='c', image_path=path, plot_reflow=False),
                             None, (60., 40.))
        self.assertEqual([r['key'] for r in rows],
                         [e['key'] for e in get_svg_text_elements(path)])

    def test_reflow_on_keys_keep_stable_ids(self):
        path = self.native('styled.ilmplot.svg', _styled_doc())
        keys = [r['key'] for r in svg_text_rows(
            self.project, Cell(id='c', image_path=path, plot_reflow=True),
            None, (60., 40.))]
        self.assertIn('ilmplot-xlabel-text-0', keys)
        self.assertIn('ilmplot-title-text-0', keys)


class DescribeTests(unittest.TestCase):

    def test_groups_rounded_sorted_with_examples(self):
        rows = [{'size_pt': 10.04, 'text': 'a'},
                {'size_pt': 8.0, 'text': 'b'},
                {'size_pt': 10.0, 'text': 'c'},
                {'size_pt': None, 'text': 'skip'}]
        self.assertEqual(describe_text_sizes(rows),
                         [(8.0, 1, 'b'), (10.0, 2, 'a')])

    def test_format_text_size(self):
        self.assertEqual(format_text_size(10.0), '10')
        self.assertEqual(format_text_size(8.25), '8.25')
        self.assertEqual(format_text_size(7.3333), '7.33')


class ByteIdentityTests(unittest.TestCase):

    def _run(self, name, project, cell, content):
        with mock.patch.object(stu, 'svg_mm_per_unit', _mm_stub):
            out = get_svg_override_bytes_for_cell(project, cell, None,
                                                  content)
        return out

    def test_public_output_is_unchanged(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        nat = os.path.join(tmp.name, 'n.ilmplot.svg')
        with open(nat, 'wb') as fh:
            fh.write(render_document(_line_doc()).svg)
        heat = os.path.join(tmp.name, 'h.ilmplot.svg')
        with open(heat, 'wb') as fh:
            fh.write(render_document(_heat_doc()).svg)
        pl = os.path.join(tmp.name, 'p.svg')
        with open(pl, 'wb') as fh:
            fh.write(PLAIN)
        p = Project()
        p.typography_mode = 'points'
        cases = {
            'reflow_on_120': (p, Cell(id='c1', image_path=nat,
                                      plot_reflow=True), (120., 80.)),
            'reflow_on_60': (p, Cell(id='c1', image_path=nat,
                                     plot_reflow=True), (60., 40.)),
            'reflow_off_60': (p, Cell(id='c2', image_path=nat,
                                      plot_reflow=False), (60., 40.)),
            'heat_reflow_on': (p, Cell(id='c3', image_path=heat,
                                       plot_reflow=True), (90., 65.)),
            'plain_normalize_points': (p, Cell(
                id='c4', image_path=pl, svg_normalize_text=True,
                svg_normalize_text_pt=8.0), (60., 30.)),
        }
        p5 = Project()
        p5.typography_mode = 'points'
        p5.svg_text_groups = [SvgTextGroup(
            id='g', name='G', font_size_pt=9.0,
            members=[SvgTextMember(svg_path=pl, element_key='t1'),
                     SvgTextMember(svg_path=pl, element_key='_pos_1')])]
        cases['plain_group'] = (p5, Cell(id='c5', image_path=pl),
                                (60., 30.))
        p6 = Project()
        p6.typography_mode = 'legacy'
        cases['plain_normalize_legacy'] = (p6, Cell(
            id='c6', image_path=pl, svg_normalize_text=True,
            svg_normalize_text_pt=8.0), (60., 30.))
        for name, (project, cell, content) in cases.items():
            with self.subTest(name=name):
                out = self._run(name, project, cell, content)
                self.assertEqual(hashlib.sha256(out).hexdigest(),
                                 HASHES[name])
        self.assertIsNone(self._run('plain_none', p6,
                                    Cell(id='c7', image_path=pl),
                                    (60., 30.)))


class StringTests(unittest.TestCase):

    NEW_KEYS = ('svgtxt_size_reflow_on', 'svgtxt_size_reflow_off',
                'svgtxt_new_group_size_btn', 'svgtxt_plot_group_name',
                'plot_text_sizes_header', 'plot_text_role_line',
                'plot_text_role_tip_line', 'plot_text_role_other',
                'btn_match_text_size', 'tip_match_text_size')

    def test_new_keys_are_bilingual(self):
        for key in self.NEW_KEYS:
            with self.subTest(key=key):
                entry = _STRINGS[key]
                self.assertTrue(entry.get('en'), key)
                self.assertTrue(entry.get('zh'), key)

    def test_every_app_string_has_en_and_zh(self):
        missing = [key for key, entry in _STRINGS.items()
                   if not entry.get('en') or not entry.get('zh')]
        self.assertEqual(missing, [])

    def test_placeholders_match_between_languages(self):
        for key in ('svgtxt_plot_group_name', 'plot_text_role_line',
                    'plot_text_role_tip_line'):
            en = set(re.findall(r'\{(\w+)\}', _STRINGS[key]['en']))
            zh = set(re.findall(r'\{(\w+)\}', _STRINGS[key]['zh']))
            self.assertEqual(en, zh, key)


if __name__ == '__main__':
    unittest.main()
