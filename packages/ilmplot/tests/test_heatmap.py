"""Heatmap (imshow / pcolormesh) kind: document, render, fit and bridge."""
import json
import unittest
from unittest import mock

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from matplotlib.backends.backend_agg import FigureCanvasAgg  # noqa: E402
from matplotlib.cm import ScalarMappable  # noqa: E402
from matplotlib.colors import Normalize  # noqa: E402

from ilmplot import bridge  # noqa: E402
from ilmplot import document as document_module  # noqa: E402
from ilmplot import render  # noqa: E402
from ilmplot.document import (HeatmapOptions, LineSeries,  # noqa: E402
                              PlotDocument, PlotDocumentError,
                              PlotVersionError, document_from_svg,
                              required_capabilities)

GRID = [[0.0, 1.0, None, 3.0],
        [4.0, 5.0, 6.0, 7.0],
        [8.0, 9.0, 10.0, 11.0]]


def _doc(**kw):
    heat = {'values': GRID}
    heat.update(kw.pop('heat', {}))
    d = PlotDocument(kind='heatmap', series=[],
                     heatmap=HeatmapOptions(**heat))
    for k, v in kw.items():
        setattr(d, k, v)
    return d


def _mut(mutate, **heat):
    """Serialized heatmap document with *mutate* applied to its dict."""
    d = _doc(heat=heat).to_dict()
    mutate(d)
    return d


class HeatmapDocumentTests(unittest.TestCase):

    def test_round_trip_all_options(self):
        doc = _doc(heat=dict(
            extent=[0.0, 4.0, 0.0, 3.0], cmap='RdBu_r', vmin=-1.0,
            vmax=12.0, aspect='equal', colorbar=False,
            colorbar_label='Value', mask_color='#0000ff80'))
        d = json.loads(json.dumps(doc.to_dict()))
        back = PlotDocument.from_dict(d)
        self.assertEqual(back.to_dict(), d)
        self.assertEqual(back.heatmap.cmap, 'RdBu_r')
        self.assertEqual(back.heatmap.values[0][2], None)

    def test_defaults_emit_only_values(self):
        d = _doc().to_dict()
        self.assertEqual(sorted(d['heatmap']), ['values'])
        self.assertEqual(d['kind'], 'heatmap')
        self.assertEqual(d['series'], [])

    def test_strict_from_dict_errors(self):
        cases = {
            'ragged': _mut(lambda d: d['heatmap']['values'].__setitem__(
                1, [1.0, 2.0])),
            'nan': _mut(lambda d: d['heatmap']['values'].__setitem__(
                0, [float('nan'), 1.0, None, 3.0])),
            'bool': _mut(lambda d: d['heatmap']['values'].__setitem__(
                0, [True, 1.0, None, 3.0])),
            'bad cmap': _mut(lambda d: d['heatmap'].update(cmap='cubehelix')),
            'vmin>=vmax': _mut(lambda d: d['heatmap'].update(
                vmin=2.0, vmax=2.0)),
            'degenerate extent': _mut(lambda d: d['heatmap'].update(
                extent=[0, 0, 0, 3])),
            'labels length': _mut(lambda d: d['heatmap'].update(
                x_cell_labels=['a', 'b'])),
            'labels with extent': _mut(lambda d: d['heatmap'].update(
                extent=[0, 4, 0, 3],
                y_cell_labels=['a', 'b', 'c'])),
            'unknown key': _mut(lambda d: d['heatmap'].update(zz=1)),
            'bad aspect': _mut(lambda d: d['heatmap'].update(aspect='big')),
            'empty values': _mut(lambda d: d['heatmap'].update(values=[])),
        }
        for name, data in cases.items():
            with self.subTest(name):
                with self.assertRaises(PlotDocumentError):
                    PlotDocument.from_dict(data)

    def test_validate_rules(self):
        with self.assertRaises(PlotDocumentError):
            PlotDocument(kind='heatmap', series=[]).validate()
        with self.assertRaisesRegex(PlotDocumentError, 'series'):
            PlotDocument(kind='heatmap', heatmap=HeatmapOptions(
                values=GRID)).validate()
        with self.assertRaisesRegex(PlotDocumentError, 'groups'):
            _doc(groups=[document_module.ViolinGroup(
                id='g', label='g', values=[1.0])]).validate()
        with self.assertRaisesRegex(PlotDocumentError, 'x_cell_labels'):
            _doc(x_tick_labels=[[0.0, 'a']]).validate()
        with self.assertRaisesRegex(PlotDocumentError, 'options only apply'):
            PlotDocument(kind='histogram', series=[],
                         groups=[document_module.ViolinGroup(
                             id='g', label='g', values=[1.0])],
                         heatmap=HeatmapOptions(values=GRID)).validate()
        with self.assertRaisesRegex(PlotDocumentError, 'options only apply'):
            PlotDocument(kind='line', heatmap=HeatmapOptions(
                values=GRID)).validate()

    def test_total_cells_limit(self):
        big = [[0.0] * 317 for _ in range(317)]   # 100489 > 100000
        with self.assertRaisesRegex(PlotDocumentError, 'too many data'):
            _doc(heat=dict(values=big)).validate()

    def test_annotations_allowed(self):
        from ilmplot.document import Annotation
        doc = _doc(annotations=[Annotation(text='3', x=0.5, y=0.5)])
        self.assertEqual(doc.validate().annotations[0].text, '3')


class CapabilityTests(unittest.TestCase):

    def test_stamped_for_kind(self):
        doc = _doc()
        self.assertEqual(required_capabilities(doc), ['heatmap'])
        self.assertIn('heatmap', doc.to_dict()['requires'])

    def test_old_reader_rejects(self):
        d = _doc().to_dict()
        old = document_module.CAPABILITIES - {'heatmap'}
        with mock.patch.object(document_module, 'CAPABILITIES', old):
            with self.assertRaises(PlotVersionError) as cm:
                PlotDocument.from_dict(d)
        self.assertEqual(cm.exception.missing, ['heatmap'])


class RenderTests(unittest.TestCase):

    def test_deterministic_and_embedded(self):
        doc = _doc(heat=dict(colorbar_label='Value'))
        a = render.render_document(doc).svg
        b = render.render_document(doc).svg
        self.assertEqual(a, b)
        back = document_from_svg(a)
        self.assertEqual(back.to_dict(), doc.to_dict())

    def test_colorbar_is_child_axes(self):
        _f, ax = render._build_figure(_doc(), 1.0, 60., 40.)
        self.assertEqual(len(ax.child_axes), 1)
        _f, ax = render._build_figure(_doc(heat=dict(colorbar=False)),
                                      1.0, 60., 40.)
        self.assertEqual(len(ax.child_axes), 0)

    def test_colorbar_label_and_cell_labels(self):
        doc = _doc(heat=dict(colorbar_label='Value',
                             x_cell_labels=['a', 'b', 'c', 'd'],
                             y_cell_labels=['r0', 'r1', 'r2']))
        _f, ax = render._build_figure(doc, 1.0, 90., 65.)
        self.assertEqual(ax.child_axes[0].get_ylabel(), 'Value')
        self.assertEqual([t.get_text() for t in ax.get_xticklabels()],
                         ['a', 'b', 'c', 'd'])
        self.assertEqual([t.get_text() for t in ax.get_yticklabels()],
                         ['r0', 'r1', 'r2'])

    def test_grid_is_honoured_without_error(self):
        svg = render.render_document(_doc(grid=True)).svg
        self.assertIn(b'ilmplot-heatmap', svg)

    def _fitted(self, doc, w, h):
        with matplotlib.rc_context(render._deterministic_rc(doc)):
            fig, ax = render._build_figure(doc, 1.0, w, h)
            render._fit_axes(fig, ax, render.FIT_PAD_MM / 25.4 * fig.dpi)
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            tb = fig.get_tightbbox(canvas.get_renderer())
            dpi = fig.dpi
            bounds = (tb.x0 * dpi, tb.y0 * dpi, tb.x1 * dpi, tb.y1 * dpi)
            size = (fig.get_figwidth() * dpi, fig.get_figheight() * dpi)
            pos = ax.get_position()
            fig.clear()
        return bounds, size, pos

    def test_fitted_odd_sizes_no_clipping(self):
        doc = _doc(heat=dict(aspect='equal', colorbar_label='Value'),
                   title='Heat', xlabel='columns', ylabel='rows')
        for w, h in ((60., 40.), (180., 40.)):
            with self.subTest(size=(w, h)):
                (x0, y0, x1, y1), (W, H), _pos = self._fitted(doc, w, h)
                self.assertGreaterEqual(x0, -0.5)
                self.assertGreaterEqual(y0, -0.5)
                self.assertLessEqual(x1, W + 0.5)
                self.assertLessEqual(y1, H + 0.5)

    def test_equal_aspect_keeps_cells_square(self):
        doc = _doc(heat=dict(aspect='equal'), title='Heat')
        _b, (W, H), pos = self._fitted(doc, 180., 40.)
        ratio = (pos.width * W) / (pos.height * H)
        self.assertAlmostEqual(ratio, 4 / 3, places=2)

    def test_fitted_plot_area_is_the_image_box(self):
        doc = _doc(heat=dict(aspect='equal'))
        r = render.render_document_fitted(doc, 90., 65.)
        _b, (W, H), pos = self._fitted(doc, 90., 65.)
        self.assertAlmostEqual(r.plot_area[0], pos.x0, places=6)
        self.assertAlmostEqual(r.plot_area[2], pos.x1, places=6)
        self.assertAlmostEqual(r.plot_area[1], 1.0 - pos.y1, places=6)
        self.assertAlmostEqual(r.plot_area[3], 1.0 - pos.y0, places=6)


def _raster(fig):
    canvas = FigureCanvasAgg(fig)
    canvas.draw()
    return np.asarray(canvas.buffer_rgba()).copy()


def _pixel(img, ax, x, y):
    px, py = ax.transData.transform((x, y))
    h = img.shape[0]
    return img[int(h - py), int(px)].astype(int)


class BridgeTests(unittest.TestCase):

    def _convert(self, fig):
        res = bridge.convert(fig)
        plt.close(fig)
        return res

    def test_imshow_converts_with_colorbar_label(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        im = ax.imshow(np.arange(12.).reshape(3, 4),
                       interpolation='nearest', cmap='plasma')
        fig.colorbar(im, ax=ax, label='Value')
        res = self._convert(fig)
        self.assertFalse(res.reasons, res.reasons)
        doc = res.document
        self.assertEqual(doc.kind, 'heatmap')
        self.assertEqual(doc.heatmap.cmap, 'plasma')
        self.assertTrue(doc.heatmap.colorbar)
        self.assertEqual(doc.heatmap.colorbar_label, 'Value')
        self.assertEqual(doc.heatmap.aspect, 'equal')
        self.assertEqual(doc.heatmap.extent, [-0.5, 3.5, 2.5, -0.5])
        self.assertEqual(doc.heatmap.values[0], [0.0, 1.0, 2.0, 3.0])

    def test_lower_origin_masked_and_limits(self):
        arr = np.ma.masked_array(np.arange(12.).reshape(3, 4),
                                 np.arange(12.).reshape(3, 4) == 5)
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.imshow(arr, origin='lower', interpolation='nearest',
                  vmin=1, vmax=10)
        res = self._convert(fig)
        self.assertFalse(res.reasons, res.reasons)
        h = res.document.heatmap
        self.assertEqual(h.values[0], [8.0, 9.0, 10.0, 11.0])
        self.assertEqual(h.values[1][1], None)   # value 5 was masked
        self.assertEqual(h.vmin, 1.0)
        self.assertEqual(h.vmax, 10.0)           # explicit, below data max
        self.assertEqual(h.extent, [-0.5, 3.5, -0.5, 2.5])

    def test_pcolormesh_converts_and_flips_descending_rows(self):
        grid = np.arange(12.).reshape(3, 4)
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.pcolormesh(grid)
        res = self._convert(fig)
        self.assertFalse(res.reasons, res.reasons)
        self.assertEqual(res.document.heatmap.values[0], [8.0, 9.0, 10.0,
                                                          11.0])
        self.assertEqual(res.document.heatmap.extent, [0.0, 4.0, 0.0, 3.0])

    def test_default_imshow_converts_with_parity(self):
        fig, ax = plt.subplots(figsize=(4, 3))
        ax.imshow(np.arange(12.).reshape(3, 4))
        res = self._assert_pixel_parity(fig, ax)
        self.assertTrue(any('rendered as nearest' in n for n in res.notes),
                        res.notes)

    def test_pixel_parity_with_matplotlib(self):
        rng = np.random.default_rng(2)
        data = rng.uniform(0, 1, (5, 7))
        data[1, 2] = np.nan
        fig, ax = plt.subplots(figsize=(4, 3))
        im = ax.imshow(np.ma.masked_invalid(data), origin='lower',
                       interpolation='nearest', cmap='viridis',
                       vmin=0.1, vmax=0.9)
        fig.colorbar(im, ax=ax, label='Value')
        self._assert_pixel_parity(fig, ax)

    def _assert_pixel_parity(self, fig, ax):
        orig_img = _raster(fig)
        res = bridge.convert(fig)
        self.assertFalse(res.reasons, res.reasons)
        doc = res.document
        rfig, rax = render._build_figure(doc, 1.0, doc.width_mm,
                                         doc.height_mm)
        rimg = _raster(rfig)
        ext = doc.heatmap.extent
        nr, nc = len(doc.heatmap.values), len(doc.heatmap.values[0])
        colours = set()
        for i in range(nr):
            for j in range(nc):
                x = ext[0] + (j + 0.5) * (ext[1] - ext[0]) / nc
                y = ext[3] + (i + 0.5) * (ext[2] - ext[3]) / nr
                want = _pixel(orig_img, ax, x, y)
                got = _pixel(rimg, rax, x, y)
                colours.add(tuple(want))
                self.assertLessEqual(np.abs(want - got).max(), 2,
                                     msg=(i, j, want.tolist(), got.tolist()))
        self.assertGreater(len(colours), 10)
        plt.close(fig)
        return res

    def test_rejections(self):
        A = np.arange(12.).reshape(3, 4)

        def conv(build):
            fig, ax = plt.subplots()
            build(fig, ax)
            return self._convert(fig)

        cases = [
            ('large matrix in a small axes',
             lambda f, a: a.imshow(np.zeros((400, 400))),
             'only converted when upsampled more than 3x'),
            ('bilinear', lambda f, a: a.imshow(
                A, interpolation='bilinear'),
             "image interpolation 'bilinear'"),
            ('colormap', lambda f, a: a.imshow(
                A, interpolation='nearest', cmap='cubehelix'),
             "colormap 'cubehelix'"),
            ('log norm', lambda f, a: a.imshow(
                A + 1, interpolation='nearest', norm='log'),
             'LogNorm'),
            ('rgb', lambda f, a: a.imshow(
                np.zeros((3, 4, 3)), interpolation='nearest'),
             'RGB(A)'),
            ('alpha', lambda f, a: a.imshow(
                A, interpolation='nearest', alpha=0.5),
             'image alpha 0.5'),
            ('mixed line', lambda f, a: (a.imshow(
                A, interpolation='nearest'), a.plot([0, 1], [0, 1])),
             'cannot be mixed'),
            ('two images', lambda f, a: (a.imshow(
                A, interpolation='nearest'), a.pcolormesh(A)),
             'multiple images'),
            ('two axes', lambda f, a: None, None),
            ('numeric aspect', lambda f, a: a.imshow(
                A, interpolation='nearest', aspect=2.0),
             'aspect ratio 2.0'),
            ('custom ticks', lambda f, a: (a.imshow(
                A, interpolation='nearest'),
                a.set_yticks([0, 1, 2], ['a', 'b', 'c'])),
             'custom tick positions'),
            ('too many annotations', lambda f, a: (a.imshow(
                np.zeros((5, 5)), interpolation='nearest'),
                [a.text(j, i, '1') for i in range(5) for j in range(5)]),
             'more than 20 text annotations'),
            ('horizontal colorbar', lambda f, a: f.colorbar(
                a.imshow(A, interpolation='nearest'), ax=a,
                orientation='horizontal'),
             'horizontal colorbars'),
            ('extended colorbar', lambda f, a: f.colorbar(
                a.imshow(A, interpolation='nearest'), ax=a,
                extend='both'),
             'extensions'),
            ('shaded pcolormesh', lambda f, a: a.pcolormesh(
                np.arange(12.).reshape(3, 4), shading='gouraud'),
             'flat pcolormesh shading'),
            ('non-uniform pcolormesh', lambda f, a: a.pcolormesh(
                [0, 1, 3, 4, 6], [0, 1, 2, 3], np.zeros((3, 4))),
             'non-uniform pcolormesh'),
            ('foreign colorbar', lambda f, a: (
                a.imshow(A, interpolation='nearest'),
                f.colorbar(ScalarMappable(Normalize(0, 1)),
                           cax=f.add_axes([0.9, 0.1, 0.05, 0.8]))),
             'own colorbar'),
        ]
        for name, build, want in cases:
            with self.subTest(name):
                if want is None:
                    fig, axs = plt.subplots(1, 2)
                    axs[0].imshow(A, interpolation='nearest')
                    axs[1].imshow(A, interpolation='nearest')
                    res = self._convert(fig)
                    self.assertIsNone(res.document)
                    self.assertTrue(any('multiple images' in r
                                        for r in res.reasons), res.reasons)
                    continue
                res = conv(build)
                self.assertIsNone(res.document, name)
                self.assertTrue(any(want in r for r in res.reasons),
                                (name, res.reasons))


if __name__ == '__main__':
    unittest.main()
