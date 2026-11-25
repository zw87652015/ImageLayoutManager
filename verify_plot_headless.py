"""Headless Plot Editor engine + CLI + agent tools (Qt-free)."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__),
                                'packages', 'ilmplot', 'src'))

from src.plot_editor import headless
from src.plot_editor.headless import HeadlessError
from src.plot_editor.plot_file import load_plot_file


def _spec(**kw):
    spec = {'chart': 'pure_line',
            'columns': [
                {'designation': 'X', 'values': [0, 1, 2, 3, 4]},
                {'designation': 'Y', 'comments': 'data',
                 'values': [1, 3, 2, 5, 4]},
            ]}
    spec.update(kw)
    return spec


class HeadlessCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = self._tmp.name

    def tearDown(self):
        self._tmp.cleanup()

    def path(self, name='plot.ilmplot.svg'):
        return os.path.join(self.dir, name)


class CreateTests(HeadlessCase):
    def test_create_line_with_function_and_overrides(self):
        spec = _spec(columns=[
            {'designation': 'X', 'values': [0, 1, 2, 3, 4]},
            {'designation': 'Y', 'comments': 'data',
             'values': [1, 3, 2, 5, 4]},
            {'designation': 'yErr', 'values': [0.1, 0.2, 0.1, 0.3, 0.2]},
            {'designation': 'Function', 'values': ['2*x']},
        ], overrides={
            'xlabel': 'Time', 'xlim': [0, 10],
            'series': {'1': {'color': '#d62728', 'legend': False}},
            'legend_text': '\\l(2) %(2)',
        })
        result = headless.create(spec, self.path('a'))
        self.assertTrue(result['path'].endswith('.ilmplot.svg'))
        self.assertEqual(result['kind'], 'line')
        self.assertEqual(result['items'], 2)
        pf = load_plot_file(result['path'])
        self.assertTrue(pf.has_worksheet)
        doc = pf.document
        self.assertEqual(doc.kind, 'line')
        self.assertEqual(len(doc.series), 2)
        self.assertEqual(doc.series[0].label, 'data')
        self.assertEqual(doc.series[0].color, '#d62728')
        self.assertEqual(doc.series[0].yerr, [0.1, 0.2, 0.1, 0.3, 0.2])
        self.assertEqual(doc.series[1].label, '2*x')
        self.assertEqual(doc.xlabel, 'Time')
        self.assertEqual(list(doc.xlim), [0.0, 10.0])
        # The function curve re-sampled over the explicit xlim.
        self.assertAlmostEqual(max(doc.series[1].x), 10.0, places=6)
        self.assertAlmostEqual(doc.series[1].y[-1], 20.0, places=6)
        self.assertEqual(doc.legend_text, '\\l(2) %(2)')
        # legend_hidden carries the series override (column 1 → s0).
        self.assertIn('series:s0', doc.legend_hidden)

    def test_inspect_round_trip(self):
        spec = _spec(overrides={'ylabel': 'v'})
        headless.create(spec, self.path())
        expected = headless.spec_from_state(headless.state_from_spec(spec))
        got = headless.inspect(self.path())
        self.assertEqual(got, expected)
        self.assertEqual(got['info']['has_worksheet'], True)
        self.assertEqual(got['info']['kind'], 'line')
        self.assertEqual([i['column'] for i in got['info']['items']],
                         [1])

    def test_chart_families(self):
        cases = [
            ('pure_scatters', _spec(chart='pure_scatters')),
            ('column', _spec(
                chart='column',
                columns=[
                    {'designation': 'Label', 'values': ['a', 'b']},
                    {'designation': 'Y', 'comments': 'c1',
                     'values': [1, 2]},
                    {'designation': 'Y', 'comments': 'c2',
                     'values': [3, 1]},
                ])),
            ('histogram', _spec(
                chart='histogram',
                columns=[
                    {'designation': 'Y', 'comments': 'g1',
                     'values': [1, 2, 3, 1]},
                    {'designation': 'Y', 'comments': 'g2',
                     'values': [2, 2, 1, 4]},
                ])),
            ('box', _spec(
                chart='box',
                columns=[
                    {'designation': 'Y', 'comments': 'g1',
                     'values': [1, 2, 3, 1, 5]},
                ])),
            ('heatmap', _spec(
                chart='heatmap',
                columns=[
                    {'designation': 'Label', 'values': ['r1', 'r2']},
                    {'designation': 'Y', 'comments': 'c1',
                     'values': [1, 2]},
                    {'designation': 'Y', 'comments': 'c2',
                     'values': [3, 4]},
                ])),
        ]
        kinds = {'pure_scatters': 'line', 'column': 'stacked_column',
                 'histogram': 'histogram', 'box': 'violin',
                 'heatmap': 'heatmap'}
        for i, (chart, spec) in enumerate(cases):
            with self.subTest(chart=chart):
                out = self.path('f%d.ilmplot.svg' % i)
                headless.create(spec, out)
                got = headless.inspect(out)
                self.assertEqual(got['chart'], chart)
                self.assertEqual(got['info']['kind'], kinds[chart])

    def test_spec_reference_examples_create(self):
        for name, spec in headless.SPEC_EXAMPLES.items():
            with self.subTest(example=name):
                out = self.path('%s.ilmplot.svg' % name)
                result = headless.create(dict(spec), out)
                self.assertTrue(os.path.isfile(result['path']))

    def test_function_only_and_bad_function(self):
        spec = _spec(columns=[{'designation': 'Function',
                               'values': ['x^2']}])
        result = headless.create(spec, self.path('fn'))
        got = headless.inspect(result['path'])
        self.assertEqual(got['info']['kind'], 'line')
        self.assertEqual(len(got['info']['items']), 1)
        # Invalid formula with no other series → HeadlessError.
        bad = _spec(columns=[{'designation': 'Function',
                              'values': ['2*']}])
        with self.assertRaises(HeadlessError):
            headless.create(bad, self.path('bad'))
        # Invalid formula alongside a valid Y is skipped, not fatal.
        mixed = _spec(columns=[
            {'designation': 'X', 'values': [0, 1]},
            {'designation': 'Y', 'values': [1, 2]},
            {'designation': 'Function', 'values': ['2*']},
        ])
        result = headless.create(mixed, self.path('mixed'))
        self.assertEqual(result['items'], 1)


class StateTests(HeadlessCase):
    def test_numeric_strings_behave_like_typed_cells(self):
        spec = _spec(columns=[
            {'designation': 'X', 'values': ['0', '1', '2']},
            {'designation': 'Y', 'values': ['1', '4', '9']},
        ])
        headless.create(spec, self.path())
        got = headless.inspect(self.path())
        self.assertEqual(got['columns'][0]['values'], [0.0, 1.0, 2.0])
        pf = load_plot_file(self.path())
        self.assertEqual(list(pf.document.series[0].x), [0.0, 1.0, 2.0])

    def test_state_from_spec_rejects_bad_input(self):
        with self.assertRaises(HeadlessError):
            headless.state_from_spec('nope')
        with self.assertRaises(HeadlessError):
            headless.state_from_spec(_spec(bogus=1))
        with self.assertRaises(HeadlessError):
            headless.state_from_spec(_spec(chart='not_a_chart'))
        with self.assertRaises(HeadlessError):
            headless.state_from_spec(_spec(columns=[
                {'designation': 'QQ', 'values': [1]}]))
        with self.assertRaises(HeadlessError):
            headless.state_from_spec(_spec(plot_columns=[0, 99]))
        with self.assertRaises(HeadlessError):
            headless.state_from_spec(_spec(columns=[]))


class EditTests(HeadlessCase):
    def setUp(self):
        super().setUp()
        self.src = self.path('src.ilmplot.svg')
        headless.create(_spec(title='orig'), self.src)
        with open(self.src, 'rb') as fh:
            self.before = fh.read()

    def test_merge_patch_semantics(self):
        out = self.path('out.ilmplot.svg')
        headless.edit(self.src, {
            'title': 'new',
            'overrides': {'xlim': [0, 50], 'grid': True},
            'columns': {'1': {'values': [9, 8, 7, 6, 5]}},
        }, out)
        got = headless.inspect(out)
        self.assertEqual(got['title'], 'new')
        self.assertEqual(got['overrides']['xlim'], [0.0, 50.0])
        self.assertEqual(got['overrides']['grid'], True)
        self.assertEqual(got['columns'][1]['values'],
                         [9.0, 8.0, 7.0, 6.0, 5.0])
        # Original untouched when -o is used.
        with open(self.src, 'rb') as fh:
            self.assertEqual(fh.read(), self.before)
        # null deletes a key.
        headless.edit(out, {'title': None,
                            'overrides': {'xlim': None}},
                      self.path('out2.ilmplot.svg'))
        got2 = headless.inspect(self.path('out2.ilmplot.svg'))
        self.assertEqual(got2['title'], '')
        self.assertNotIn('xlim', got2.get('overrides', {}))
        self.assertIn('grid', got2['overrides'])

    def test_append_and_replace_chart(self):
        out = self.path('out.ilmplot.svg')
        headless.edit(self.src, {
            'chart': 'pure_scatters',
            'columns': {'2': {'designation': 'Y', 'comments': 'extra',
                              'values': [1, 1, 1, 1, 1]}},
        }, out)
        got = headless.inspect(out)
        self.assertEqual(got['chart'], 'pure_scatters')
        self.assertEqual(len(got['columns']), 3)
        self.assertEqual(got['columns'][2]['designation'], 'Y')
        # Column-index gaps are rejected.
        with self.assertRaises(HeadlessError):
            headless.apply_patch(got, {'columns': {'5': {'designation': 'Y'}}})
        # Appending without a designation is rejected.
        with self.assertRaises(HeadlessError):
            headless.apply_patch(got, {'columns': {'3': {'values': [1]}}})
        # Non-object patch rejected.
        with self.assertRaises(HeadlessError):
            headless.apply_patch(got, [1, 2])

    def test_in_place_edit(self):
        headless.edit(self.src, {'title': 'inplace'}, None)
        got = headless.inspect(self.src)
        self.assertEqual(got['title'], 'inplace')

    def test_read_only_source(self):
        # Corrupt the worksheet node → rebuilt sheet, read-only source.
        with open(self.src, 'rb') as fh:
            raw = fh.read().decode('utf-8')
        import xml.etree.ElementTree as ET
        root = ET.fromstring(raw)
        ns = ''
        if root.tag.startswith('{'):
            ns = root.tag[:root.tag.index('}') + 1]
        for meta in root:
            if meta.tag == '%smetadata' % ns \
                    and meta.get('id') == 'ilm-plot-worksheet':
                meta.text = '{corrupt'
        bad = self.path('bad.ilmplot.svg')
        with open(bad, 'wb') as fh:
            fh.write(ET.tostring(root, encoding='unicode')
                     .encode('utf-8'))
        with self.assertRaises(HeadlessError):
            headless.edit(bad, {'title': 'x'}, None)
        out = headless.edit(bad, {'title': 'x'},
                            self.path('rescued.ilmplot.svg'))
        self.assertTrue(os.path.isfile(out['path']))
        self.assertTrue(load_plot_file(out['path']).has_worksheet)


class LegacyTests(HeadlessCase):
    def test_legacy_document_round_trip(self):
        import ilmplot.render as render
        spec = _spec(overrides={
            'series': {'1': {'color': '#00aa00', 'linewidth_pt': 3.5}},
        })
        headless.create(spec, self.path('styled'))
        pf = load_plot_file(self.path('styled.ilmplot.svg'))
        legacy = self.path('legacy.ilmplot.svg')
        render.save_document(pf.document, legacy)
        state = headless.load_state(legacy)
        self.assertFalse(state.has_worksheet)
        got = headless.inspect(legacy)
        self.assertFalse(got['info']['has_worksheet'])
        self.assertTrue(got['columns'])
        # Edit keeps the base document's colours/linewidths.
        out = headless.edit(legacy, {'title': 'legacy+',
                                     'overrides': {'grid': True}},
                            self.path('edited.ilmplot.svg'))
        pf2 = load_plot_file(out['path'])
        self.assertTrue(pf2.has_worksheet)
        self.assertEqual(pf2.document.series[0].color, '#00aa00')
        self.assertAlmostEqual(pf2.document.series[0].linewidth_pt,
                               3.5)
        self.assertEqual(pf2.document.title, 'legacy+')


class ExportTests(HeadlessCase):
    def setUp(self):
        super().setUp()
        self.src = self.path('src.ilmplot.svg')
        headless.create(_spec(), self.src)

    def test_export_formats(self):
        png = self.path('fig.png')
        r = headless.export(self.src, png)
        self.assertTrue(os.path.isfile(r['path']))
        self.assertGreater(os.path.getsize(r['path']), 100)
        with open(r['path'], 'rb') as fh:
            self.assertEqual(fh.read(8), b'\x89PNG\r\n\x1a\n')
        for ext in ('.pdf', '.svg'):
            out = self.path('fig' + ext)
            headless.export(self.src, out)
            self.assertGreater(os.path.getsize(out), 100)
        # Unknown extension without -f → HeadlessError.
        with self.assertRaises(HeadlessError):
            headless.export(self.src, self.path('fig.xyz'))
        # Explicit fmt overrides/extends the suffix.
        r = headless.export(self.src, self.path('fig2'), fmt='png')
        self.assertTrue(r['path'].endswith('.png'))


class ErrorTests(HeadlessCase):
    def test_export_missing_file(self):
        with self.assertRaises(FileNotFoundError):
            headless.inspect(self.path('nope.ilmplot.svg'))


class CliTests(HeadlessCase):
    def _main(self, argv, stdin_text=None):
        from src.cli.main import main
        out, err = io.StringIO(), io.StringIO()
        stdin = io.StringIO(stdin_text) if stdin_text is not None \
            else sys.stdin
        code = None
        with contextlib.redirect_stdout(out), \
                contextlib.redirect_stderr(err):
            old = sys.stdin
            if stdin_text is not None:
                sys.stdin = stdin
            try:
                code = main(argv)
            finally:
                sys.stdin = old
        return code, out.getvalue(), err.getvalue()

    def test_cli_create_inspect_edit_export_schema(self):
        spec_path = self.path('spec.json')
        with open(spec_path, 'w', encoding='utf-8') as fh:
            json.dump(_spec(), fh)
        plot = self.path('cli.ilmplot.svg')
        code, out, _ = self._main(
            ['plot', 'create', spec_path, '-o', plot, '--json'])
        self.assertEqual(code, 0)
        report = json.loads(out)
        self.assertTrue(report['ok'])
        self.assertTrue(report['path'].endswith('.ilmplot.svg'))
        # create from stdin
        code, out, _ = self._main(
            ['plot', 'create', '-', '-o',
             self.path('stdin.ilmplot.svg')],
            stdin_text=json.dumps(_spec()))
        self.assertEqual(code, 0)
        self.assertTrue(out.strip().endswith('.ilmplot.svg'))
        # inspect --no-values
        code, out, _ = self._main(
            ['plot', 'inspect', plot, '--no-values'])
        self.assertEqual(code, 0)
        spec = json.loads(out)
        self.assertIn('n_values', spec['columns'][0])
        self.assertNotIn('values', spec['columns'][0])
        # edit --patch to a new path
        code, out, _ = self._main(
            ['plot', 'edit', plot, '--patch',
             '{"title": "cli"}', '-o', self.path('edited.ilmplot.svg')])
        self.assertEqual(code, 0)
        code, out, _ = self._main(
            ['plot', 'inspect', self.path('edited.ilmplot.svg')])
        self.assertEqual(json.loads(out)['title'], 'cli')
        # export + schema
        code, out, _ = self._main(
            ['plot', 'export', plot, '-o', self.path('fig.png')])
        self.assertEqual(code, 0)
        code, out, _ = self._main(['plot', 'schema'])
        self.assertIn('Plot spec reference', out)
        # --json error envelope + exit 1
        bad = self.path('bad.json')
        with open(bad, 'w') as fh:
            json.dump({'chart': 'nope', 'columns': [
                {'designation': 'Y', 'values': [1]}]}, fh)
        code, out, _ = self._main(
            ['plot', 'create', bad, '-o', self.path('x'), '--json'])
        self.assertEqual(code, 1)
        self.assertFalse(json.loads(out)['ok'])
        # usage error → SystemExit(2)
        with self.assertRaises(SystemExit) as cm:
            self._main(['plot', 'edit', plot])
        self.assertEqual(cm.exception.code, 2)

    def test_plot_commands_never_import_qt(self):
        repo = os.path.dirname(os.path.abspath(__file__))
        spec_path = self.path('spec.json')
        with open(spec_path, 'w', encoding='utf-8') as fh:
            json.dump(_spec(), fh)
        plot = self.path('q.ilmplot.svg')
        code = (
            "import sys; sys.path.insert(0, %r);"
            "from src.cli.main import main;"
            "main(['plot', 'create', %r, '-o', %r]);"
            "main(['plot', 'schema']);"
            "sys.exit(3 if 'PyQt6.QtWidgets' in sys.modules else 0)"
            % (repo, spec_path, plot))
        proc = subprocess.run([sys.executable, '-c', code],
                              capture_output=True, text=True,
                              cwd=repo)
        self.assertEqual(proc.returncode, 0,
                         proc.stdout + proc.stderr)


class ToolTests(HeadlessCase):
    def test_dispatch_envelopes(self):
        from src.agent.tools import ToolContext, dispatch
        ctx = ToolContext(project=None)
        spec = _spec()
        env = dispatch('plot_create',
                       {'spec': spec, 'path': self.path('t')}, ctx)
        self.assertTrue(env['ok'], env)
        created = env['result']['path']
        self.assertTrue(created.endswith('.ilmplot.svg'))
        env = dispatch('plot_inspect',
                       {'path': created, 'include_values': False}, ctx)
        self.assertTrue(env['ok'])
        self.assertIn('n_values', env['result']['columns'][0])
        env = dispatch('plot_edit',
                       {'path': created,
                        'patch': {'title': 'tool'},
                        'output_path': self.path('t2')}, ctx)
        self.assertTrue(env['ok'], env)
        edited = env['result']['path']
        env = dispatch('plot_export',
                       {'path': edited,
                        'output_path': self.path('t.png')}, ctx)
        self.assertTrue(env['ok'], env)
        # Error envelope.
        env = dispatch('plot_inspect',
                       {'path': self.path('missing.ilmplot.svg')}, ctx)
        self.assertFalse(env['ok'])
        self.assertEqual(env['error'], 'file_not_found')
        env = dispatch('plot_create',
                       {'spec': {'chart': 'bogus', 'columns': [
                           {'designation': 'Y', 'values': [1]}]},
                        'path': self.path('bad')}, ctx)
        self.assertFalse(env['ok'])
        self.assertEqual(env['error'], 'plot_error')

    def test_specs_cover_registry(self):
        from src.agent.tool_specs import TOOL_SPECS
        from src.agent.tools import list_tools
        names = {s['name'] for s in TOOL_SPECS}
        for tool in ('plot_create', 'plot_inspect', 'plot_edit',
                     'plot_export'):
            self.assertIn(tool, names)
            self.assertIn(tool, list_tools())
        for name in list_tools():
            if name.startswith('plot_'):
                self.assertIn(name, names)


if __name__ == '__main__':
    unittest.main()
