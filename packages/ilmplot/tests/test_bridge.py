"""Unit tests for ilmplot — document model, bridge, packaging rules.

Runs standalone: ``python -m unittest discover -s tests`` from the
package root with ``packages/ilmplot/src`` on PYTHONPATH.
"""

import os
import subprocess
import sys
import tempfile
import unittest
import warnings

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt          # noqa: E402
import numpy as np                       # noqa: E402
from matplotlib.ticker import (          # noqa: E402
    FormatStrFormatter, MultipleLocator)

import ilmplot                           # noqa: E402
from ilmplot import bridge               # noqa: E402
from ilmplot import messages             # noqa: E402
from ilmplot.document import (           # noqa: E402
    PlotDocument, document_from_svg)


def line_fig(**kw):
    fig, ax = plt.subplots(figsize=(4, 3))
    ax.plot([0, 1, 2], [1, 4, 2], label='a', color='red',
            linestyle='--', marker='o')
    ax.plot([0, 1, 2], [2, 1, 3], label='b')
    ax.set_xlabel('X')
    ax.set_ylabel('Y')
    ax.set_xlim(-1, 3)
    ax.set_ylim(0, 5)
    for k, v in kw.items():
        getattr(ax, 'set_' + k)(v)
    return fig, ax


class ConvertTests(unittest.TestCase):

    def test_line_round_trip(self):
        fig, ax = line_fig()
        ax.legend(loc='upper left')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        doc = res.document
        self.assertIsNotNone(doc)
        self.assertEqual(doc.kind, 'line')
        self.assertEqual(len(doc.series), 2)
        s = doc.series[0]
        self.assertEqual(s.label, 'a')
        self.assertEqual(s.x, [0., 1., 2.])
        self.assertEqual(s.y, [1., 4., 2.])
        self.assertEqual(s.color, '#ff0000')
        self.assertEqual(s.linestyle, '--')
        self.assertEqual(s.marker, 'o')
        self.assertEqual(doc.series[1].label, 'b')
        self.assertEqual(doc.xlim, [-1., 3.])
        self.assertEqual(doc.ylim, [0., 5.])
        self.assertEqual(doc.xlabel, 'X')
        self.assertTrue(doc.legend)
        self.assertEqual(doc.legend_location, 'upper left')
        plt.close(fig)

    def test_native_output_parses(self):
        fig, _ = line_fig()
        res = bridge.convert(fig)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'a.ilmplot.svg')
            out = bridge.savefig(fig, p)
            self.assertTrue(out.native)
            with open(p, 'rb') as fh:
                doc = document_from_svg(fh.read())
            self.assertEqual(len(doc.series), 2)
        plt.close(fig)

    def test_log_y_and_symlog(self):
        fig, ax = plt.subplots()
        ax.plot([1, 2], [10, 100])
        ax.set_yscale('log')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual(res.document.style.yaxis.scale, 'log')
        plt.close(fig)
        fig, ax = plt.subplots()
        ax.plot([1, 2], [1, 2])
        ax.set_yscale('symlog')
        res = bridge.convert(fig)
        self.assertIsNone(res.document)
        self.assertTrue(any('symlog' in r for r in res.reasons))
        plt.close(fig)

    def test_errorbar_symmetric(self):
        fig, ax = plt.subplots()
        ax.errorbar([0, 1, 2], [1, 2, 1], yerr=0.2)
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual(len(res.document.series), 1)
        self.assertIsNotNone(res.document.series[0].yerr)
        self.assertTrue(all(abs(v - 0.2) < 1e-6
                            for v in res.document.series[0].yerr))
        plt.close(fig)

    def test_errorbar_asymmetric(self):
        fig, ax = plt.subplots()
        ax.errorbar([0, 1, 2], [1, 2, 1], yerr=[[0.1] * 3, [0.3] * 3])
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        s = res.document.series[0]
        self.assertIsNone(s.yerr)
        self.assertTrue(all(abs(v - 0.1) < 1e-6 for v in s.yerr_minus))
        self.assertTrue(all(abs(v - 0.3) < 1e-6 for v in s.yerr_plus))
        plt.close(fig)

    def test_errorbar_caps_note(self):
        fig, ax = plt.subplots()
        ax.errorbar([0, 1], [1, 2], yerr=0.1, capsize=3)
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertTrue(any('cap' in n for n in res.notes))
        plt.close(fig)

    def test_xerr_reason(self):
        fig, ax = plt.subplots()
        ax.errorbar([0, 1], [1, 2], xerr=0.1)
        res = bridge.convert(fig)
        self.assertIsNone(res.document)
        self.assertTrue(any('xerr' in r for r in res.reasons))
        plt.close(fig)

    def _labels_round_trip(self, fig, expected):
        """Convert → native doc, save, re-parse; labels must match."""
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        doc = res.document
        self.assertIsNotNone(doc)
        self.assertTrue(doc.legend)
        self.assertEqual([s.label for s in doc.series], expected)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'e.ilmplot.svg')
            out = bridge.savefig(fig, p)
            self.assertTrue(out.native)
            with open(p, 'rb') as fh:
                doc2 = document_from_svg(fh.read())
            self.assertEqual([s.label for s in doc2.series],
                             expected)

    def test_errorbar_label_legend(self):
        # The label lives on the ErrorbarContainer, not the Line2D.
        fig, ax = plt.subplots()
        ax.errorbar([0, 1, 2], [1, 2, 1], yerr=0.2, label='Control')
        ax.legend()
        self._labels_round_trip(fig, ['Control'])
        plt.close(fig)

    def test_errorbar_label_fmt_caps(self):
        fig, ax = plt.subplots()
        ax.errorbar([0, 1, 2], [1, 2, 1], yerr=0.2, fmt='o-',
                    capsize=3, label='Control')
        ax.legend()
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertTrue(any('cap' in n for n in res.notes))
        self.assertEqual([s.label for s in res.document.series],
                         ['Control'])
        plt.close(fig)

    def test_two_errorbars_labels(self):
        fig, ax = plt.subplots()
        ax.errorbar([0, 1], [1, 2], yerr=0.1, label='A')
        ax.errorbar([0, 1], [2, 3], yerr=0.1, label='B')
        ax.legend()
        self._labels_round_trip(fig, ['A', 'B'])
        plt.close(fig)

    def test_plot_and_errorbar_labels(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [1, 2, 1], label='Fit')
        ax.errorbar([0, 1], [0.5, 1.5], yerr=0.1, fmt='o',
                    label='Data')
        ax.legend()
        self._labels_round_trip(fig, ['Fit', 'Data'])
        plt.close(fig)

    def test_plot_and_errorbar_same_data(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [1, 2, 1], label='mean')
        ax.errorbar([0, 1, 2], [1, 2, 1], yerr=0.2, label='err')
        ax.legend()
        self._labels_round_trip(fig, ['mean', 'err'])
        plt.close(fig)

    def test_errorbar_no_legend_still_native(self):
        fig, ax = plt.subplots()
        ax.errorbar([0, 1, 2], [1, 2, 1], yerr=0.2, label='Control')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual([s.label for s in res.document.series],
                         ['Control'])
        self.assertFalse(res.document.legend)
        plt.close(fig)

    def test_errorbar_private_label_ignored(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [0, 1], label='L')
        ax.errorbar([0, 1], [0.5, 1.5], yerr=0.1,
                    label='_nolegend_')
        ax.legend()
        self._labels_round_trip(fig, ['L', ''])
        plt.close(fig)

    def test_scatter_markers(self):
        for marker in ('o', 's', '^', 'D'):
            fig, ax = plt.subplots()
            ax.scatter([0, 1, 2], [1, 2, 3], marker=marker, s=25,
                       label='pts')
            res = bridge.convert(fig)
            self.assertEqual(res.reasons, [], marker)
            s = res.document.series[0]
            self.assertEqual(s.linestyle, '')
            self.assertEqual(s.marker, marker)
            self.assertAlmostEqual(s.markersize_pt, 5.0, places=6)
            self.assertEqual(s.label, 'pts')
            plt.close(fig)

    def test_scatter_colormapped_reason(self):
        fig, ax = plt.subplots()
        ax.scatter([0, 1], [1, 2], c=[0.1, 0.9])
        res = bridge.convert(fig)
        self.assertIsNone(res.document)
        self.assertTrue(any('colormap' in r for r in res.reasons))
        plt.close(fig)

    def test_bar_single(self):
        fig, ax = plt.subplots()
        ax.bar(['a', 'b', 'c'], [1, 2, 3])
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        doc = res.document
        self.assertEqual(doc.kind, 'stacked_column')
        self.assertEqual(len(doc.categories), 1)
        self.assertEqual(doc.categories[0].values, [1., 2., 3.])
        self.assertTrue(doc.stacked.grouped)
        self.assertEqual(
            [l for _p, l in doc.x_tick_labels], ['a', 'b', 'c'])
        plt.close(fig)

    def test_bar_grouped(self):
        x = np.arange(3)
        fig, ax = plt.subplots()
        ax.bar(x - 0.2, [1, 2, 3], 0.4, label='m')
        ax.bar(x + 0.2, [2, 1, 2], 0.4, label='f')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        doc = res.document
        self.assertTrue(doc.stacked.grouped)
        self.assertFalse(doc.stacked.percent)
        self.assertTrue(0 < doc.stacked.bar_width <= 1)
        self.assertEqual([c.label for c in doc.categories], ['m', 'f'])
        plt.close(fig)

    def test_bar_stacked(self):
        x = np.arange(3)
        fig, ax = plt.subplots()
        ax.bar(x, [1, 2, 3], 0.5, label='a')
        ax.bar(x, [2, 1, 2], 0.5, bottom=[1, 2, 3], label='b')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertFalse(res.document.stacked.grouped)
        plt.close(fig)

    def test_bar_yerr(self):
        fig, ax = plt.subplots()
        ax.bar([0, 1], [1, 2], yerr=0.1)
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertTrue(all(abs(v - 0.1) < 1e-6
                            for v in res.document.categories[0].yerr))
        plt.close(fig)

    def test_barh_and_negative_reasons(self):
        fig, ax = plt.subplots()
        ax.barh([0, 1], [1, 2])
        res = bridge.convert(fig)
        self.assertTrue(any('horizontal' in r for r in res.reasons))
        plt.close(fig)
        fig, ax = plt.subplots()
        ax.bar([0, 1], [1, -2])
        res = bridge.convert(fig)
        self.assertTrue(any('negative' in r for r in res.reasons))
        plt.close(fig)

    def test_bars_plus_line_reason(self):
        fig, ax = plt.subplots()
        ax.bar([0, 1], [1, 2])
        ax.plot([0, 1], [3, 3])
        res = bridge.convert(fig)
        self.assertIsNone(res.document)
        self.assertTrue(any('mix' in r for r in res.reasons))
        plt.close(fig)

    def test_text_annotation_centre(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        t = ax.text(0.5, 0.6, 'note', transform=ax.transAxes)
        fig.canvas.get_renderer()  # ensure renderer exists
        renderer = fig.canvas.get_renderer()
        bb = t.get_window_extent(renderer)
        expect = ax.transAxes.inverted().transform(
            bb.corners().mean(axis=0))
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        a = res.document.annotations[0]
        self.assertEqual(a.text, 'note')
        self.assertAlmostEqual(a.x, expect[0], delta=1e-3)
        self.assertAlmostEqual(a.y, expect[1], delta=1e-3)
        plt.close(fig)

    def test_annotate_arrow_reason(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.annotate('p', xy=(1, 2), xytext=(0.5, 0.5),
                    arrowprops=dict(arrowstyle='->'))
        res = bridge.convert(fig)
        self.assertTrue(any('arrow' in r for r in res.reasons))
        plt.close(fig)

    def test_title_left(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.set_title('Lefty', loc='left')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual(res.document.title, 'Lefty')
        self.assertEqual(res.document.style.title.align, 'left')
        plt.close(fig)

    def test_hidden_spines(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertTrue(res.document.style.frame.hide_top)
        self.assertTrue(res.document.style.frame.hide_right)
        self.assertFalse(res.document.style.frame.hide_left)
        plt.close(fig)

    def test_tick_direction_minor_step_decimals(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1, 2], [1, 2, 1])
        ax.tick_params(axis='x', direction='in', length=6)
        ax.minorticks_on()
        ax.xaxis.set_major_locator(MultipleLocator(0.5))
        ax.xaxis.set_major_formatter(FormatStrFormatter('%.2f'))
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        st = res.document.style.xaxis
        self.assertEqual(st.direction, 'in')
        self.assertEqual(st.length_pt, 6)
        self.assertTrue(st.minor)
        self.assertEqual(st.step, 0.5)
        self.assertEqual(st.decimals, 2)
        plt.close(fig)

    def test_serif_family(self):
        with matplotlib.rc_context({'font.family': 'serif'}):
            fig, ax = plt.subplots()
            ax.plot([0, 1], [1, 2])
            res = bridge.convert(fig)
            self.assertEqual(res.reasons, [])
            self.assertIn('serif', res.document.font_family.lower())
            plt.close(fig)

    def test_xlabel_style(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.set_xlabel('Big', fontsize=20)
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual(res.document.style.xlabel.size_pt, 20)
        plt.close(fig)

    def test_two_problems_two_reasons(self):
        fig, ax = plt.subplots()
        ax.set_yscale('symlog')
        ax.errorbar([0, 1], [1, 2], xerr=0.1)
        res = bridge.convert(fig)
        self.assertIsNone(res.document)
        self.assertGreaterEqual(len(res.reasons), 2)
        plt.close(fig)

    def test_figure_rcparams_canvas_unchanged(self):
        fig, ax = line_fig()
        before_rc = dict(matplotlib.rcParams)
        canvas = fig.canvas
        bridge.convert(fig)
        with tempfile.TemporaryDirectory() as d:
            bridge.savefig(fig, os.path.join(d, 'a.ilmplot.svg'))
        self.assertIs(fig.canvas, canvas)
        self.assertEqual(dict(matplotlib.rcParams), before_rc)
        plt.close(fig)

    def test_axvspan_and_fill_reasons(self):
        # axvspan/axhspan map to document spans (see test_spans.py);
        # other patches stay reasons.
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.axvspan(0.2, 0.8)
        res = bridge.convert(fig)
        self.assertIsNotNone(res.document)
        self.assertEqual(len(res.document.spans), 1)
        plt.close(fig)
        fig, ax = plt.subplots()
        ax.fill([0, 1, 1], [0, 0, 1])
        res = bridge.convert(fig)
        self.assertTrue(any('patch' in r.lower() for r in res.reasons))
        plt.close(fig)
        fig, ax = plt.subplots()
        ax.bar([0, 1], [1, 2])   # bar patches stay native
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        plt.close(fig)

    def test_text_annotation_bare_figure(self):
        import matplotlib.figure
        fig = matplotlib.figure.Figure()
        ax = fig.add_subplot()
        ax.plot([0, 1], [1, 2])
        t = ax.text(0.5, 0.6, 'note', transform=ax.transAxes)
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        bb = t.get_window_extent()
        expect = ax.transAxes.inverted().transform(
            bb.corners().mean(axis=0))
        a = res.document.annotations[0]
        self.assertAlmostEqual(a.x, expect[0], delta=1e-3)
        self.assertAlmostEqual(a.y, expect[1], delta=1e-3)

    def test_tick_direction_from_rcparams(self):
        with matplotlib.rc_context({'xtick.direction': 'in',
                                    'ytick.direction': 'in'}):
            fig, ax = plt.subplots()
            ax.plot([0, 1], [1, 2])
            res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual(res.document.style.xaxis.direction, 'in')
        self.assertEqual(res.document.style.yaxis.direction, 'in')
        plt.close(fig)

    def test_bar_tick_labels_set_xticks(self):
        fig, ax = plt.subplots()
        ax.bar([0, 1, 2], [1, 2, 3])
        ax.set_xticks([0, 1, 2], ['A', 'B', 'C'])
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual([l for _p, l in res.document.x_tick_labels],
                         ['A', 'B', 'C'])
        plt.close(fig)

    def test_bar_tick_labels_numeric(self):
        fig, ax = plt.subplots()
        ax.bar([1, 2, 3], [1, 2, 3])
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual([l for _p, l in res.document.x_tick_labels],
                         ['1.0', '2.0', '3.0'])  # axis's own labels
        plt.close(fig)

    def test_grouped_bar_order(self):
        x = np.arange(3)
        fig, ax = plt.subplots()
        ax.bar(x + 0.2, [2, 1, 2], 0.4, label='right')
        ax.bar(x - 0.2, [1, 2, 3], 0.4, label='left')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual([c.label for c in res.document.categories],
                         ['left', 'right'])
        plt.close(fig)

    def test_background_and_tick_position_notes(self):
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.set_facecolor('#eeeeee')
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertTrue(any('background' in n for n in res.notes))
        plt.close(fig)
        fig, ax = plt.subplots()
        ax.plot([0, 1], [1, 2])
        ax.xaxis.tick_top()
        res = bridge.convert(fig)
        self.assertTrue(any('ticks on top/right' in n
                            for n in res.notes))
        plt.close(fig)

    def test_categorical_line(self):
        fig, ax = plt.subplots()
        ax.plot(['a', 'b', 'c'], [1, 2, 1])
        res = bridge.convert(fig)
        self.assertEqual(res.reasons, [])
        self.assertEqual(res.document.x_tick_labels,
                         [[0., 'a'], [1., 'b'], [2., 'c']])
        self.assertEqual(res.document.series[0].x, [0., 1., 2.])
        plt.close(fig)


class SavefigTests(unittest.TestCase):

    def test_fallback_plain_svg(self):
        fig, axs = plt.subplots(1, 2)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'o.svg')
            with warnings.catch_warnings(record=True) as ws:
                warnings.simplefilter('always')
                res = bridge.savefig(fig, p)
            self.assertFalse(res.native)
            self.assertTrue(res.reasons)
            self.assertTrue(any(issubclass(w.category,
                                           bridge.FallbackWarning)
                                for w in ws))
            with open(p, 'rb') as fh:
                blob = fh.read()
            self.assertNotIn(b'ilm-plot-document', blob)
            self.assertIn(b'<text', blob)
        plt.close(fig)

    def test_strict_leaves_file_untouched(self):
        fig, axs = plt.subplots(1, 2)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'o.svg')
            with open(p, 'wb') as fh:
                fh.write(b'EXISTING')
            with self.assertRaises(bridge.UnsupportedFigureError) as cm:
                bridge.savefig(fig, p, strict=True)
            self.assertTrue(cm.exception.reasons)
            with open(p, 'rb') as fh:
                self.assertEqual(fh.read(), b'EXISTING')
        plt.close(fig)

    def test_savefig_kwargs_forwarded(self):
        fig, axs = plt.subplots(1, 2)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, 'o.svg')
            with warnings.catch_warnings():
                warnings.simplefilter('ignore')
                bridge.savefig(fig, p, bbox_inches='tight',
                               transparent=True)
            self.assertTrue(os.path.isfile(p))
        plt.close(fig)

    def test_legacy_api(self):
        fig, ax = line_fig()
        doc = bridge.document_from_figure(fig)
        self.assertIsInstance(doc, PlotDocument)
        plt.close(fig)
        fig, axs = plt.subplots(1, 2)
        with self.assertRaises(bridge.UnsupportedFigureError):
            bridge.document_from_figure(fig)
        plt.close(fig)


class PackageShapeTests(unittest.TestCase):

    def test_import_does_not_pull_matplotlib(self):
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = ('import sys; sys.path.insert(0, %r); import ilmplot; '
                'print("matplotlib" in sys.modules)' % os.path.join(
                    src, 'src'))
        out = subprocess.check_output([sys.executable, '-c', code],
                                      text=True)
        self.assertEqual(out.strip(), 'False')

    def test_bridge_leaves_no_src_module(self):
        src = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        code = ('import sys; sys.path.insert(0, %r); '
                'import ilmplot, ilmplot.bridge; '
                'print("src" in sys.modules)' % os.path.join(
                    src, 'src'))
        out = subprocess.check_output([sys.executable, '-c', code],
                                      text=True)
        self.assertEqual(out.strip(), 'False')

    def test_lazy_exports(self):
        self.assertTrue(ilmplot.__version__)
        self.assertTrue(ilmplot.SCHEMA_VERSION)
        self.assertIs(ilmplot.convert, bridge.convert)
        self.assertIs(ilmplot.savefig, bridge.savefig)
        self.assertIs(ilmplot.FallbackWarning, bridge.FallbackWarning)
        self.assertIs(ilmplot.UnsupportedFigureError,
                      bridge.UnsupportedFigureError)

    def test_messages_translator_hook(self):
        orig = messages._translator
        try:
            messages.set_translator(
                lambda key, **fmt: 'zh:' + key)
            self.assertEqual(messages.text('err_svg_entities'),
                             'zh:err_svg_entities')

            def partial(key, **fmt):
                if key == 'err_svg_entities':
                    return 'zh:' + key
                raise KeyError(key)
            messages.set_translator(partial)
            self.assertEqual(
                messages.text('err_plot_newer_schema', found=2,
                              supported=1),
                messages._ENGLISH['err_plot_newer_schema'].format(
                    found=2, supported=1))
        finally:
            messages.set_translator(orig)
        out = messages.text('err_plot_newer_schema', found='2',
                            supported='1')
        self.assertIn('2', out)
        self.assertNotIn('{found}', out)


if __name__ == '__main__':
    unittest.main()
