"""Render a :class:`PlotDocument` to deterministic SVG bytes.

Rendering goes through ``matplotlib.figure.Figure`` + ``backend_svg`` inside
``rc_context`` — pyplot and the global backend are never touched. The rc
context is seeded from ``matplotlib.rcParamsDefault`` (minus the backend)
so user rc files/styles cannot leak a dark background or foreign defaults
into exported plots. The SVG carries the *original* (unscaled) document
JSON in its metadata node, so the file remains editable no matter which
``style_scale`` produced the snapshot.

``style_scale`` multiplies every physical size (fonts, line/marker widths,
spine and tick lengths, paddings) without changing figure geometry or data.
ILM uses it to keep typography at true final-figure points when a panel is
placed larger or smaller than the document's native size.
"""

from __future__ import annotations

import functools
import io
import json
import math
import os
import re
import tempfile
import xml.etree.ElementTree as ET
from collections import OrderedDict
from dataclasses import dataclass

from .document import (
    MAX_DIMENSION_MM, MAX_FILE_BYTES, PlotDocument, PlotDocumentError,
    embed_metadata,
)
from matplotlib.ticker import Formatter

from .mathtext import safe_text

_HASHSALT = 'ilm-plot-editor-v1'

# Text ids: matplotlib lands set_gid() on a wrapping <g>; ILM text groups
# key individual <text> elements, so these get stable per-run element ids.
_TEXT_GROUPS = ('ilmplot-title', 'ilmplot-xlabel', 'ilmplot-ylabel')

_SVG_NS = 'http://www.w3.org/2000/svg'
_XLINK_NS = 'http://www.w3.org/1999/xlink'

# QtSvg parses small inline font sizes with integer rounding, so native
# text is emitted at a 128 px reference and compensated with a scale()
# transform — the same high-reference technique ILM uses for overrides.
_REF_FONT_PX = 128.0

_LEN_RE = re.compile(
    r'([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)(%|[A-Za-z]+)?')
_FONT_SIZE_STYLE_RE = re.compile(
    r'(?:^|;)\s*font-size\s*:\s*([-+]?(?:\d*\.\d+|\d+\.?)(?:[eE][-+]?\d+)?)'
    r'(px|pt)?')
_FONT_FAMILY_STYLE_RE = re.compile(r'font-family\s*:[^;]+;?')


def _local(elem) -> str:
    return elem.tag.rsplit('}', 1)[-1]


def _register_namespaces(svg: bytes) -> None:
    try:
        for _event, data in ET.iterparse(io.BytesIO(svg),
                                         events=['start-ns']):
            prefix, uri = data
            try:
                ET.register_namespace(prefix, uri)
            except Exception:
                pass
    except Exception:
        pass
    ET.register_namespace('', _SVG_NS)
    ET.register_namespace('xlink', _XLINK_NS)


def _flatten_positioned_runs(root):
    """Turn <text> elements that are pure lists of positioned <tspan>s into
    <g> containers of <text> runs (MathText emits these; flattening keeps
    per-run font sizes instead of normalizing superscripts).

    Returns the set of converted child elements — these are math runs and
    must keep their own Matplotlib math font families."""
    runs = set()
    for elem in list(root.iter()):
        if _local(elem) != 'text' or (elem.text or '').strip():
            continue
        children = list(elem)
        if not children or any(k in elem.attrib for k in
                               ('rotate', 'textLength')):
            continue
        if any(_local(c) != 'tspan' or 'x' not in c.attrib
               or 'y' not in c.attrib or 'transform' in c.attrib
               or (c.tail or '').strip()
               or any(_local(n) == 'textPath' for n in c.iter())
               for c in children):
            continue
        namespace = elem.tag[:-len('text')]
        parent_id = elem.get('id')
        elem.tag = namespace + 'g'
        for key in ('x', 'y', 'dx', 'dy'):
            elem.attrib.pop(key, None)
        for i, child in enumerate(children):
            child.tag = namespace + 'text'
            if parent_id and child.get('id') is None:
                child.set('id', f'{parent_id}-run-{i}')
            runs.add(child)
    return runs


def _assign_text_ids(root) -> bool:
    """Give <text> descendants of the labelled groups stable element ids."""
    changed = False
    for gid in _TEXT_GROUPS:
        for elem in root.iter():
            if elem.get('id') == gid:
                idx = 0
                for node in elem.iter():
                    if _local(node) == 'text':
                        node.set('id', f'{gid}-text-{idx}')
                        idx += 1
                        changed = True
    return changed


def _explicit_font_px(node):
    """Font size in px declared inline (style property or attribute)."""
    style = node.get('style') or ''
    m = _FONT_SIZE_STYLE_RE.search(style)
    if m:
        unit = m.group(2) or 'px'
        if unit == 'px':
            return float(m.group(1))
        return float(m.group(1)) * 96.0 / 72.0
    attr = node.get('font-size')
    if attr:
        m = _LEN_RE.fullmatch(attr.strip())
        if m:
            unit = m.group(2) or 'px'
            if unit == 'px':
                return float(m.group(1))
            if unit == 'pt':
                return float(m.group(1)) * 96.0 / 72.0
    return None


def _divide_font_px(node, comp: float) -> None:
    style = node.get('style')
    if style and _FONT_SIZE_STYLE_RE.search(style):
        def repl(m):
            unit = m.group(2) or 'px'
            return (m.group(0).replace(m.group(1),
                    f'{float(m.group(1)) / comp:.12g}', 1))
        node.set('style', _FONT_SIZE_STYLE_RE.sub(repl, style))
    elif node.get('font-size'):
        m = _LEN_RE.fullmatch(node.get('font-size').strip())
        if m:
            node.set('font-size',
                     f'{float(m.group(1)) / comp:.12g}{m.group(2) or ""}')


def _rescale_text_subtree(elem, comp: float) -> None:
    """Divide absolute lengths by *comp* (inverse of the scale transform)."""
    def inv(m):
        unit = m.group(2) or ''
        if unit in ('em', 'ex'):
            return m.group(0)
        return f'{float(m.group(1)) / comp:.12g}{unit}'
    for node in elem.iter():
        if _local(node) not in ('text', 'tspan'):
            continue
        for key in ('x', 'y', 'dx', 'dy', 'textLength',
                    'letter-spacing', 'word-spacing', 'stroke-width'):
            if key in node.attrib:
                node.set(key, _LEN_RE.sub(inv, node.get(key)))
        style = node.get('style')
        if style:
            node.set('style', re.sub(
                r'((?:letter-spacing|word-spacing|stroke-width)\s*:\s*)'
                r'([^;]+)',
                lambda m: m.group(1) + _LEN_RE.sub(inv, m.group(2)),
                style))
        if node is not elem:
            # Nested runs keep their size relative to the parent's 128 px.
            _divide_font_px(node, comp)


def _set_font_px_128(node) -> None:
    """Replace any font-size (px, pt or presentation attribute) with a
    literal ``font-size:128px`` appended after the other properties."""
    style = node.get('style') or ''
    if _FONT_SIZE_STYLE_RE.search(style):
        style = _FONT_SIZE_STYLE_RE.sub('', style).strip('; ')
    node.attrib.pop('font-size', None)
    node.set('style',
             f'{style};font-size:128px' if style else 'font-size:128px')


def _precise_text(root, font_family: str, math_runs) -> bool:
    """128 px reference fonts + a single explicit family for <text> roots.

    Qt misparses Matplotlib's CSS fallback list ('Arial', 'DejaVu Sans',
    sans-serif), so ordinary text elements get one presentation
    ``font-family`` attribute; flattened math runs (*math_runs*) keep
    their own Matplotlib math families and styles.
    """
    changed = False
    for node in root.iter():
        if _local(node) != 'text':
            continue
        px = _explicit_font_px(node)
        if px is not None and px > 0:
            comp = px / _REF_FONT_PX
            if abs(comp - 1.0) > 1e-12:
                _rescale_text_subtree(node, comp)
                node.set('transform',
                         (node.get('transform', '') +
                          f' scale({comp:.12g})').strip())
            _set_font_px_128(node)
            changed = True
        if node not in math_runs:
            style = node.get('style')
            family = None
            if style and _FONT_FAMILY_STYLE_RE.search(style):
                m = re.search(r'font-family\s*:\s*([^;]+)', style)
                if m:
                    # First family of the node's own CSS list wins, so
                    # per-element style families survive normalization.
                    family = m.group(1).split(',')[0] \
                        .strip().strip('"\'') or None
                node.set('style', _FONT_FAMILY_STYLE_RE.sub('', style)
                         .strip('; '))
            family = family or font_family
            if family:
                node.set('font-family', family)
        changed = True
    return changed


def _prepare_svg(svg: bytes, font_family: str) -> bytes:
    """Post-process raw Matplotlib SVG for Qt: flatten positioned runs,
    assign stable text ids, emit high-precision 128 px reference text and
    a single font family. Returns *svg* unchanged on any parse problem."""
    _register_namespaces(svg)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError:
        return svg
    math_runs = _flatten_positioned_runs(root)
    changed = bool(math_runs)
    changed |= _assign_text_ids(root)
    changed |= _precise_text(root, font_family, math_runs)
    if not changed:
        return svg
    try:
        return ET.tostring(root, encoding='unicode').encode('utf-8')
    except Exception:
        return svg


@dataclass(frozen=True)
class PlotRender:
    svg: bytes
    # normalized (left, top, right, bottom) of the axes rectangle — the
    # "plot interior" ILM alignment marks refer to.
    plot_area: tuple


def _canonical(document: PlotDocument) -> str:
    return json.dumps(document.to_dict(), sort_keys=True,
                      separators=(',', ':'))


_render_cache: OrderedDict = OrderedDict()
_RENDER_CACHE_MAX = 64


def _deterministic_rc(document: PlotDocument) -> dict:
    """rc seed built from matplotlib defaults, not the caller's rcParams."""
    import matplotlib
    rc = {k: v for k, v in matplotlib.rcParamsDefault.items()
          if not k.startswith('backend')}
    rc.update({
        'svg.fonttype': 'none',
        'text.usetex': False,
        'svg.hashsalt': _HASHSALT,
        'font.family': 'sans-serif',
        'font.sans-serif': [document.font_family, 'DejaVu Sans'],
        'axes.unicode_minus': False,
        'figure.dpi': 100,
    })
    return rc


def render_document(document: PlotDocument, *,
                    style_scale: float = 1.0) -> PlotRender:
    """Render *document* to SVG bytes with embedded metadata.

    ``style_scale`` scales typography/line weights only; figure size, axes
    rectangle and data are unchanged, so the SVG viewBox stays identical for
    every scale.
    """
    document.validate()
    if not (isinstance(style_scale, (int, float))
            and 0 < float(style_scale) < float('inf')):
        raise PlotDocumentError(
            f"style_scale must be a positive finite number, got {style_scale!r}")
    key = (_canonical(document), round(float(style_scale), 6))
    hit = _render_cache.get(key)
    if hit is not None:
        _render_cache.move_to_end(key)
        return hit

    import matplotlib

    s = float(style_scale)
    with matplotlib.rc_context(_deterministic_rc(document)):
        fig = None
        try:
            fig, ax = _build_figure(document, s, document.width_mm,
                                    document.height_mm)
            _fit_figure(document, fig, ax)
            pos = ax.get_position()
            buf = io.BytesIO()
            fig.savefig(buf, format='svg',
                        metadata={'Date': None,
                                  'Creator': 'ILM Plot Editor'})
        finally:
            if fig is not None:
                fig.clear()

    svg = embed_metadata(
        _prepare_svg(buf.getvalue(), document.font_family), document)
    if len(svg) > MAX_FILE_BYTES:
        raise PlotDocumentError(
            f"rendered SVG exceeds {MAX_FILE_BYTES // (1024 * 1024)} MiB — "
            f"reduce the number of data points")
    render = PlotRender(
        svg=svg, plot_area=(pos.x0, 1.0 - pos.y1, pos.x1, 1.0 - pos.y0))
    _render_cache[key] = render
    if len(_render_cache) > _RENDER_CACHE_MAX:
        _render_cache.popitem(last=False)
    return render


@functools.lru_cache(maxsize=1)
def available_font_families():
    """Sorted unique family names matplotlib can resolve."""
    from matplotlib import font_manager
    return tuple(sorted({f.name for f in font_manager.fontManager.ttflist}))


def resolve_font_family(text, families):
    """Typed font input → ``(family | None, ok)``.

    Empty means the default (``(None, True)``); a case-insensitive match
    resolves to the canonical family name; anything else is ``(None,
    False)`` so the caller can flag the field instead of applying.
    """
    text = (text or '').strip()
    if not text:
        return None, True
    lowered = text.lower()
    for fam in families:
        if fam.lower() == lowered:
            return fam, True
    return None, False


class _AffixFormatter(Formatter):
    """Wraps an axis formatter: prefix/suffix, optional fixed decimals.

    A real ``Formatter`` subclass — otherwise ``set_major_formatter``
    would wrap it in a ``FuncFormatter`` and the wrapped formatter would
    never see ``set_locs`` (categorical ``FixedFormatter`` would get
    ``pos=None`` too, yielding empty labels). ``set_axis``/``set_locs``/
    ``format_ticks``/``get_offset`` delegate so offset text and tick
    behaviour are unchanged.
    """
    def __init__(self, wrapped, prefix='', suffix='', decimals=None,
                 numeric=True):
        super().__init__()
        self._wrapped = wrapped
        self._prefix = prefix
        self._suffix = suffix
        self._decimals = decimals if numeric else None

    def _text(self, x, pos):
        if self._decimals is not None:
            try:
                return f'{float(x):.{self._decimals}f}'
            except (TypeError, ValueError):
                pass
        return self._wrapped(x, pos)

    def __call__(self, x, pos=None):
        return f'{self._prefix}{self._text(x, pos)}{self._suffix}'

    def set_axis(self, axis):
        super().set_axis(axis)
        if hasattr(self._wrapped, 'set_axis'):
            self._wrapped.set_axis(axis)

    def set_locs(self, locs):
        self._wrapped.set_locs(locs)

    def format_ticks(self, values):
        self.set_locs(values)
        if self._decimals is not None:
            texts = [self._text(v, None) for v in values]
        else:
            texts = [self._wrapped(v, pos=i)
                     for i, v in enumerate(values)]
        return [f'{self._prefix}{t}{self._suffix}' for t in texts]

    def get_offset(self):
        return self._wrapped.get_offset()


def clip_series_to_view(x, y, xlim, ylim, xlog=False, ylog=False):
    """Clip a polyline to a view box (Liang–Barsky, per segment).

    QtSvg ignores ``clipPath``, so data outside the axes box must be
    clipped in the data itself. Works in transformed space (log10 for
    log axes; non-positive inputs count as outside and are dropped).
    Returns ``(xs, ys, mask)`` — ``NaN`` breaks where the line leaves the
    box, interpolated boundary points where it crosses, and ``mask[i]``
    True only where ``(xs[i], ys[i])`` is an original in-view point (so
    callers can feed it to ``set_markevery`` to keep boundary points
    unmarked).
    """
    def bound(v, log, extreme):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return extreme
        if log:
            return math.log10(v) if v > 0 else extreme
        return v

    # Transform the limits into the same space as the points.
    x0 = bound(min(xlim), xlog, -math.inf)
    x1 = bound(max(xlim), xlog, math.inf)
    y0 = bound(min(ylim), ylog, -math.inf)
    y1 = bound(max(ylim), ylog, math.inf)

    pts = []
    for xv, yv in zip(x, y):
        try:
            xv, yv = float(xv), float(yv)
        except (TypeError, ValueError):
            pts.append(None)
            continue
        if xlog and xv <= 0 or ylog and yv <= 0:
            pts.append(None)  # untransformable → outside
            continue
        if xlog:
            xv = math.log10(xv)
        if ylog:
            yv = math.log10(yv)
        if math.isnan(xv) or math.isnan(yv):
            pts.append(None)
            continue
        pts.append((xv, yv))

    out_x, out_y, mask = [], [], []
    connected = False

    def emit(px, py, is_original):
        out_x.append(10 ** px if xlog else px)
        out_y.append(10 ** py if ylog else py)
        mask.append(is_original)

    def emit_break():
        nonlocal connected
        if connected:
            out_x.append(float('nan'))
            out_y.append(float('nan'))
            mask.append(False)
            connected = False

    prev = None
    for q in pts:
        if q is None:
            emit_break()
            prev = None
            continue
        if prev is None:
            prev = q
            continue
        p, prev = prev, q
        # Liang–Barsky on segment p→q in transformed space.
        t0, t1, ok = 0.0, 1.0, True
        for pv, qv, lo, hi in ((p[0], q[0], x0, x1),
                               (p[1], q[1], y0, y1)):
            d = qv - pv
            for p_, q_ in ((-d, pv - lo), (d, hi - pv)):
                if p_ == 0:
                    if q_ < 0:
                        ok = False
                        break
                    continue
                t = q_ / p_
                if p_ < 0:
                    if t > t1:
                        ok = False
                        break
                    t0 = max(t0, t)
                else:
                    if t < t0:
                        ok = False
                        break
                    t1 = min(t1, t)
            if not ok:
                break
        if ok and t0 <= t1:
            in_p = x0 <= p[0] <= x1 and y0 <= p[1] <= y1
            in_q = x0 <= q[0] <= x1 and y0 <= q[1] <= y1
            if not connected:
                emit_break()
            if t0 > 0 or not (out_x and connected):
                ax_ = p[0] + t0 * (q[0] - p[0])
                ay_ = p[1] + t0 * (q[1] - p[1])
                emit(ax_, ay_, t0 == 0 and in_p)
            bx_ = p[0] + t1 * (q[0] - p[0])
            by_ = p[1] + t1 * (q[1] - p[1])
            emit(bx_, by_, t1 == 1 and in_q)
            connected = True
            if t1 < 1:
                emit_break()
        else:
            emit_break()
    return out_x, out_y, mask


def clip_polygon_to_view(xs, ys, xlim, ylim, xlog=False, ylog=False):
    """Clip a closed polygon to a view box (Sutherland–Hodgman).

    QtSvg ignores ``clipPath``, so filled areas (violin bodies, stacked
    bars, ridgeline fills) are clipped in data space when the document
    pins a limit. Works in transformed space (log10 on log axes;
    non-positive vertices are dropped). Returns ``(xs, ys)`` — empty
    when the polygon lies fully outside.
    """
    def bound(v, log, extreme):
        try:
            v = float(v)
        except (TypeError, ValueError):
            return extreme
        if log:
            return math.log10(v) if v > 0 else extreme
        return v

    x0 = bound(min(xlim), xlog, -math.inf)
    x1 = bound(max(xlim), xlog, math.inf)
    y0 = bound(min(ylim), ylog, -math.inf)
    y1 = bound(max(ylim), ylog, math.inf)

    pts = []
    for xv, yv in zip(xs, ys):
        try:
            xv, yv = float(xv), float(yv)
        except (TypeError, ValueError):
            continue
        if xlog and xv <= 0 or ylog and yv <= 0:
            continue  # untransformable → outside
        if xlog:
            xv = math.log10(xv)
        if ylog:
            yv = math.log10(yv)
        if math.isnan(xv) or math.isnan(yv):
            continue
        pts.append((xv, yv))
    if len(pts) < 3:
        return [], []

    def clip_bound(points, axis, bound_v, is_lo):
        """Sequential Sutherland–Hodgman against one half-plane."""
        if bound_v in (-math.inf, math.inf):
            return points
        if (lo if is_lo else hi) is None:
            return points
        bound_v = lo if is_lo else hi
        if bound_v in (-math.inf, math.inf):
            return points
        out = []

        def inside(p):
            return p[axis] >= bound_v if is_lo else p[axis] <= bound_v

        for i, p in enumerate(points):
            q = points[i - 1]
            ip, iq = inside(p), inside(q)
            if ip:
                if not iq:
                    dq = p[axis] - q[axis]
                    t = (bound_v - q[axis]) / dq if dq else 0.0
                    out.append((q[0] + t * (p[0] - q[0]),
                                q[1] + t * (p[1] - q[1])))
                out.append(p)
            elif iq:
                dq = p[axis] - q[axis]
                t = (bound_v - q[axis]) / dq if dq else 0.0
                out.append((q[0] + t * (p[0] - q[0]),
                            q[1] + t * (p[1] - q[1])))
        return out

    for axis, lo, hi in ((0, x0, x1), (1, y0, y1)):
        pts = clip_bound(pts, axis, lo, True)
        pts = clip_bound(pts, axis, hi, False)
        if not pts:
            return [], []

    out_x = [10 ** p[0] if xlog else p[0] for p in pts]
    out_y = [10 ** p[1] if ylog else p[1] for p in pts]
    return out_x, out_y


def _add_underline(ax, get_texts):
    """Add an ``Artist`` that underlines text artists (matplotlib has none).

    ``get_texts`` is a callable returning the current texts to underline —
    for tick labels it resolves labels at draw time so the underline follows
    ``_fit_axes`` repositioning and only covers visible ticks. A line just
    below each visible text's window-extent bottom edge is drawn in the
    text's own colour at ≈ 0.06 × its fontsize.
    """
    from matplotlib.artist import Artist
    from matplotlib.path import Path
    from matplotlib.transforms import IdentityTransform

    class _Underline(Artist):
        def draw(self, renderer):
            gc = renderer.new_gc()
            try:
                for text in get_texts():
                    try:
                        if not text.get_visible() or not text.get_text():
                            continue
                        bb = text.get_window_extent(renderer=renderer)
                    except Exception:
                        continue
                    if bb.width <= 0:
                        continue
                    pad = max(0.04 * text.get_fontsize(), 0.5)
                    path = Path([(bb.x0, bb.y0 - pad),
                                 (bb.x1, bb.y0 - pad)])
                    gc.set_foreground(text.get_color())
                    gc.set_linewidth(
                        max(0.06 * text.get_fontsize(), 0.3))
                    renderer.draw_path(gc, path, IdentityTransform())
            finally:
                gc.restore()
            return super().draw(renderer)

    u = _Underline()
    u.axes = ax
    u.set_figure(ax.figure)
    u.set_zorder(10)
    ax.add_artist(u)


def _text_kwargs(ts, family, size_pt, s):
    """Font kwargs for a ``TextStyle`` override (may be None)."""
    kw = {}
    if ts is not None:
        kw['fontfamily'] = ts.family or family
        kw['fontweight'] = 'bold' if ts.bold else 'normal'
        kw['fontstyle'] = 'italic' if ts.italic else 'normal'
        kw['color'] = ts.color
        if ts.size_pt is not None:
            kw['fontsize'] = ts.size_pt * s
            return kw
    kw['fontsize'] = size_pt * s
    return kw


def _view_limits(document, ax, default_xlim, default_ylim):
    """Final (xlim, ylim): document pins win, else the computed default."""
    xlim = document.xlim if document.xlim is not None else default_xlim
    ylim = document.ylim if document.ylim is not None else default_ylim
    return xlim, ylim


def _clip_needed(document):
    return document.xlim is not None or document.ylim is not None


def _n_text(opt, group):
    return safe_text(opt.n_format.format(n=len(group.values)))


def _draw_violin(document, ax, s):
    """Violin bodies + inner box + jittered points (NCPlot port).

    ``opt.body`` swaps the density body for a plain box ('none') or a
    mean column ('bar'); the 'violin' path is byte-identical to the
    original.
    """
    from matplotlib.patches import Polygon
    from matplotlib.colors import to_rgb, to_rgba, rgb_to_hsv
    from . import stats
    opt = document.violin
    if opt is None:
        from .document import ViolinOptions
        opt = ViolinOptions()
    groups = document.groups
    n = len(groups)
    clip = _clip_needed(document)
    y_axis = getattr(document.style, 'yaxis', None) \
        if document.style is not None else None
    xlog = False   # violin x is always categorical positions
    ylog = y_axis is not None and y_axis.scale == 'log'
    body = opt.body
    box_full = opt.box_width if opt.box_width is not None \
        else (0.5 if body == 'none' else 0.16)
    box_w = box_full / 2.0
    extra = 0.45 if opt.show_points and opt.points_beside else 0.0
    default_xlim = (1 - 0.7, n + 0.7 + extra)
    all_vals = [v for g in groups for v in g.values]
    pad = (max(all_vals) - min(all_vals)) * 0.05 or 1.0
    bar_stats = None
    if body == 'bar':
        import numpy as np
        bar_stats = []
        for g in groups:
            n_v = len(g.values)
            mean = float(np.mean(g.values))
            sd = float(np.std(g.values, ddof=1)) if n_v >= 2 else 0.0
            if opt.bar_error == 'sem':
                err = sd / math.sqrt(n_v) if n_v else 0.0
            elif opt.bar_error == 'sd':
                err = sd
            else:
                err = None
            bar_stats.append((mean, err))
        top = max([max(all_vals)]
                  + [m + e for m, e in bar_stats if e is not None])
        default_ylim = (0.0 if min(all_vals) >= 0
                        else min(all_vals) - pad, top + pad)
    else:
        default_ylim = (min(all_vals) - pad, max(all_vals) + pad)
    xlim, ylim = _view_limits(document, ax, default_xlim, default_ylim)
    ax.set_xlim(xlim)
    ax.set_ylim(ylim)
    gid = 'ilmplot-violin-'
    tops = []
    for i, (g, pos) in enumerate(zip(groups, range(1, n + 1))):
        g_top = max(g.values) if g.values else 0.0
        edge = g.color
        fill_alpha = opt.fill_alpha
        edge_w = opt.edge_width_pt
        dot_edge = 'face'
        dot_alpha = opt.point_alpha
        dot_lw = opt.point_edge_width_pt
        if opt.enhance_contrast:
            hsv = rgb_to_hsv(to_rgb(g.color))
            if hsv[2] > 0.8 and hsv[1] < 0.5:
                edge = '#666666'
                fill_alpha = 0.7
                edge_w = 1.2
                dot_edge = '#666666'
                dot_alpha = 0.9
        if opt.edge_color is not None:
            edge = opt.edge_color
        if opt.point_edge_color is not None:
            dot_edge = opt.point_edge_color
        if body == 'violin':
            shape = stats.violin_shape(g.values, opt.bandwidth)
            if shape is not None:
                pts, half = shape
                g_top = float(pts[-1])
                xs = [pos + h for h in half] + \
                    [pos - h for h in half[::-1]]
                ys = list(pts) + list(pts[::-1])
                if clip:
                    xs, ys = clip_polygon_to_view(xs, ys, xlim, ylim,
                                                  xlog, ylog)
                if xs:
                    # QtSvg draws a 0-width stroke as a 1-px hairline —
                    # remove the edge instead of passing width 0.
                    patch = Polygon(list(zip(xs, ys)), closed=True,
                                    facecolor=g.color,
                                    edgecolor='none' if edge_w == 0
                                    else edge,
                                    alpha=fill_alpha,
                                    linewidth=edge_w * s)
                    patch.set_gid(gid + g.id)
                    ax.add_patch(patch)
        elif body == 'bar':
            mean, err = bar_stats[i]
            if err is not None and err > 0:
                g_top = max(g_top, mean + err)
            hw = opt.bar_width / 2.0
            base = min(ylim) if ylog else 0.0
            rx = [pos - hw, pos + hw, pos + hw, pos - hw]
            ry = [base, base, mean, mean]
            if clip:
                rx, ry = clip_polygon_to_view(rx, ry, xlim, ylim,
                                              xlog, ylog)
            if rx:
                patch = Polygon(list(zip(rx, ry)), closed=True,
                                facecolor=to_rgba(g.color, fill_alpha),
                                edgecolor='none' if edge_w == 0
                                else edge,
                                linewidth=edge_w * s, zorder=2)
                patch.set_gid(gid + g.id)
                ax.add_patch(patch)
            if err is not None and err > 0:
                lo_e, hi_e = mean - err, mean + err
                if ylog and lo_e <= 0:
                    lo_e = mean / 10.0
                in_view = True
                if clip:
                    if lo_e > max(ylim) or hi_e < min(ylim):
                        in_view = False
                    else:
                        lo_e = max(lo_e, min(ylim))
                        hi_e = min(hi_e, max(ylim))
                if in_view and hi_e >= lo_e:
                    from matplotlib.collections import LineCollection
                    coll = LineCollection(
                        [((pos, lo_e), (pos, hi_e))],
                        colors='#333333', linewidths=1.2 * s, zorder=3)
                    coll.set_gid(gid + g.id)
                    ax.add_collection(coll)
        box = None
        if opt.show_box or (body == 'none' and opt.show_outliers
                            and not opt.show_points):
            box = stats.box_stats(g.values)
        if opt.show_box:
            q1, med, q3, lo, hi = box
            gid_prefix = gid + g.id
            wl, = ax.plot([pos, pos], [lo, hi], color='#333333',
                          linewidth=1.2 * s, zorder=3)
            wl.set_gid(gid_prefix)
            rx, ry = ([pos - box_w, pos + box_w, pos + box_w,
                       pos - box_w], [q1, q1, q3, q3])
            if clip:
                rx, ry = clip_polygon_to_view(rx, ry, xlim, ylim,
                                              xlog, ylog)
            if rx:
                rect = Polygon(
                    list(zip(rx, ry)), closed=True,
                    facecolor=(to_rgba(g.color, opt.fill_alpha)
                               if body == 'none' else 'white'),
                    edgecolor='#333333',
                    linewidth=1.2 * s, zorder=4)
                rect.set_gid(gid_prefix)
                ax.add_patch(rect)
            ml, = ax.plot([pos - box_w, pos + box_w], [med, med],
                          color='#333333', linewidth=1.8 * s, zorder=5,
                          solid_capstyle='butt')
            ml.set_gid(gid_prefix)
            caps = []
            if body == 'none':
                for cv in (lo, hi):
                    cl, = ax.plot([pos - box_w / 2, pos + box_w / 2],
                                  [cv, cv], color='#333333',
                                  linewidth=1.2 * s, zorder=3,
                                  solid_capstyle='butt')
                    cl.set_gid(gid_prefix)
                    caps.append((cl, cv))
            if clip:
                cx, cy, _m = clip_series_to_view(
                    [pos, pos], [lo, hi], xlim, ylim, xlog, ylog)
                wl.set_data(cx, cy)
                mx, my, _m = clip_series_to_view(
                    [pos - box_w, pos + box_w], [med, med],
                    xlim, ylim, xlog, ylog)
                ml.set_data(mx, my)
                for cl, cv in caps:
                    cx, cy, _m = clip_series_to_view(
                        [pos - box_w / 2, pos + box_w / 2], [cv, cv],
                        xlim, ylim, xlog, ylog)
                    cl.set_data(cx, cy)
        if body == 'none' and opt.show_outliers and not opt.show_points:
            _q1, _med, _q3, lo, hi = box
            xs = [pos] * len(g.values)
            ys = [v for v in g.values if v < lo or v > hi]
            xs = xs[:len(ys)]
            if clip:
                pts_xy = [(x, y) for x, y in zip(xs, ys)
                          if min(xlim) <= x <= max(xlim)
                          and min(ylim) <= y <= max(ylim)]
                xs = [p[0] for p in pts_xy]
                ys = [p[1] for p in pts_xy]
            if xs:
                coll = ax.scatter(
                    xs, ys, s=(opt.point_size_pt * s) ** 2,
                    facecolors='none', edgecolors='#333333',
                    linewidths=1.0 * s, zorder=6)
                coll.set_gid(gid + g.id)
        if opt.show_points:
            jit = stats.jitter(len(g.values), opt.points_beside,
                               42 + i)
            xs = [pos + j for j in jit]
            ys = list(g.values)
            if clip:
                pts_xy = [(x, y) for x, y in zip(xs, ys)
                          if min(xlim) <= x <= max(xlim)
                          and min(ylim) <= y <= max(ylim)]
                xs = [p[0] for p in pts_xy]
                ys = [p[1] for p in pts_xy]
            coll = ax.scatter(
                xs, ys, s=(opt.point_size_pt * s) ** 2,
                color=g.color, alpha=dot_alpha,
                edgecolors='none' if dot_lw == 0 else dot_edge,
                linewidths=0.0 if dot_lw == 0 else dot_lw * s,
                zorder=6)
            coll.set_gid(gid + g.id)
        tops.append(g_top)
    if opt.show_n and opt.n_position in ('top', 'bottom'):
        y_rng = max(ylim) - min(ylim)
        for g, pos, g_top in zip(groups, range(1, n + 1), tops):
            if opt.n_position == 'top':
                y = g_top + 0.02 * y_rng
            else:
                y = min(ylim) + 0.02 * y_rng
            if clip and not (min(xlim) <= pos <= max(xlim)
                             and min(ylim) <= y <= max(ylim)):
                continue
            t = ax.text(pos, y, _n_text(opt, g), ha='center',
                        va='bottom',
                        fontsize=(opt.n_size_pt if opt.n_size_pt
                                  is not None else
                                  document.font_size_pt) * s,
                        color=opt.n_color or '#333333', zorder=7)
            t.set_gid(gid + g.id)


def _draw_ridgeline(document, ax, s, lines):
    """Ridgeline (mountain-stacked) series — NCPlot's generate_plot."""
    import types
    from matplotlib.patches import Polygon
    from .document import RidgeOptions
    opt = document.ridgeline or RidgeOptions()
    series = document.series
    n = len(series)
    max_range = 0.0
    all_x = []
    for s_ in series:
        if s_.y:
            max_range = max(max_range, max(s_.y) - min(s_.y))
        all_x.extend(s_.x)
    offset = opt.offset or (max_range * 1.05 if max_range > 0 else 1.0)
    diffs = sorted(set(all_x))
    steps = [b - a for a, b in zip(diffs, diffs[1:]) if b - a > 0]
    min_step = min(steps) if steps else 1.0
    half = min_step * 0.48
    indices = list(range(n))
    if opt.reverse:
        indices.reverse()
    clip = _clip_needed(document)
    x_axis = getattr(document.style, 'xaxis', None) \
        if document.style is not None else None
    y_axis = getattr(document.style, 'yaxis', None) \
        if document.style is not None else None
    xlog = x_axis is not None and x_axis.scale == 'log'
    ylog = y_axis is not None and y_axis.scale == 'log'
    tick_ts = getattr(getattr(document.style, 'yaxis', None),
                      'ticks', None) if document.style else None
    label_kw = _text_kwargs(tick_ts, document.font_family,
                            document.font_size_pt, s)
    y_top = 0.0
    x_min = min(all_x) if all_x else 0.0
    x_max = max(all_x) if all_x else 1.0
    for s_ in series:
        if s_.y:
            i = series.index(s_)
            y_top = max(y_top, i * offset + max(s_.y) - min(s_.y))
    pad = (x_max - x_min) * 0.04 if x_max > x_min else 0.5
    view_xlim = document.xlim or (x_min - pad, x_max + pad)
    view_ylim = document.ylim or (-offset * 0.15,
                                 y_top + offset * 0.25)
    ax.set_xlim(view_xlim)
    ax.set_ylim(view_ylim)
    for i in indices:
        s_ = series[i]
        ymin = min(s_.y)
        baseline = i * offset
        y_plot = [y - ymin + baseline for y in s_.y]
        y_top = max(y_top, max(y_plot))
        poly_x = list(s_.x) + list(s_.x[::-1])
        poly_y = list(y_plot) + [baseline] * len(s_.x)
        if clip:
            px, py = clip_polygon_to_view(poly_x, poly_y,
                                          view_xlim, view_ylim,
                                          xlog, ylog)
        else:
            px, py = poly_x, poly_y
        if px:
            patch = Polygon(list(zip(px, py)), closed=True,
                            facecolor=s_.color, alpha=opt.fill_alpha,
                            edgecolor='none', zorder=2 + i)
            patch.set_gid(f'ilmplot-series-{s_.id}')
            ax.add_patch(patch)
        line, = ax.plot(s_.x, y_plot, color=s_.color,
                        linewidth=max(s_.linewidth_pt * s, 1e-3),
                        linestyle='None' if s_.linewidth_pt == 0 else
                        (s_.linestyle if s_.linestyle else 'None'),
                        marker=s_.marker or None,
                        markersize=max(s_.markersize_pt * s, 0.0),
                        markeredgewidth=1.0 * s, zorder=3 + i,
                        label='_nolegend_')
        line.set_gid(f'ilmplot-series-{s_.id}')
        lines.append((line, types.SimpleNamespace(
            x=list(s_.x), y=list(y_plot), marker=s_.marker)))
        xmin, xmax = min(s_.x), max(s_.x)
        if opt.baseline_width_pt > 0:
            ax.plot([xmin - half, xmax + half], [baseline, baseline],
                    color=opt.baseline_color,
                    linewidth=opt.baseline_width_pt * s, zorder=1)
        if opt.labels:
            t = ax.text(xmin - half * 1.4,
                        baseline + (max(y_plot) - baseline) * 0.5,
                        safe_text(s_.label), ha='right', va='center',
                        **label_kw)
            t.set_gid(f'ilmplot-series-label-{s_.id}')
    ax.set_yticks([])


def _yerr_bounds(item):
    """Per-point (lower, upper) error extents from either
    representation, or None."""
    if item.yerr_minus is not None:
        return list(item.yerr_minus), list(item.yerr_plus)
    if item.yerr is not None:
        return list(item.yerr), list(item.yerr)
    return None


def _draw_series_yerr(document, ax, ser, s, gid):
    """Capless vertical error bars for a line series, in its colour."""
    from matplotlib.collections import LineCollection
    lower, upper = _yerr_bounds(ser)
    xlim = document.xlim
    ylim = document.ylim
    y_axis = getattr(document.style, 'yaxis', None) \
        if document.style is not None else None
    ylog = y_axis is not None and y_axis.scale == 'log'
    segs = []
    for x, y, lo_e, hi_e in zip(ser.x, ser.y, lower, upper):
        if xlim is not None and not (min(xlim) <= x <= max(xlim)):
            continue
        lo, hi = y - lo_e, y + hi_e
        if ylog and lo <= 0:
            lo = y / 10.0
        if ylim is not None:
            if lo > max(ylim) or hi < min(ylim):
                continue
            lo, hi = max(lo, min(ylim)), min(hi, max(ylim))
            if lo > hi:
                continue
        segs.append(((x, lo), (x, hi)))
    if not segs:
        return
    lw = (ser.linewidth_pt if ser.linewidth_pt > 0 else 1.5) * s
    coll = LineCollection(segs, colors=ser.color,
                          linewidths=max(lw, 1e-3), zorder=1.9)
    coll.set_gid(gid)
    ax.add_collection(coll)


def _series_errband_poly(document, ax, ser):
    """Shaded y±err band polygon for a line series, or ``None``.

    Returns ``(poly, xs, ys)``; the caller clips and finalises it when
    the document pins limits. Same gid as the error-bar collection so
    hit-testing is unchanged.
    """
    from matplotlib.colors import to_rgba
    from matplotlib.patches import Polygon
    bounds = _yerr_bounds(ser)
    if bounds is None:
        return None
    lower, upper = bounds
    y_axis = getattr(document.style, 'yaxis', None) \
        if document.style is not None else None
    ylog = y_axis is not None and y_axis.scale == 'log'
    lo_pts, hi_pts = [], []
    for x, y, lo_e, hi_e in zip(ser.x, ser.y, lower, upper):
        lo, hi = y - lo_e, y + hi_e
        if ylog and lo <= 0:
            lo = y / 10.0
        lo_pts.append((x, lo))
        hi_pts.append((x, hi))
    xs = [p[0] for p in lo_pts] + [p[0] for p in hi_pts][::-1]
    ys = [p[1] for p in lo_pts] + [p[1] for p in hi_pts][::-1]
    r, g, b, a = to_rgba(ser.color)
    poly = Polygon(list(zip(xs, ys)), closed=True,
                   facecolor=(r, g, b, a * ser.error_alpha),
                   edgecolor='none', linewidth=0, zorder=1.8)
    poly.set_gid(f'ilmplot-series-{ser.id}')
    ax.add_patch(poly)
    ax.update_datalim(poly.get_path().vertices)
    return poly, xs, ys


def _draw_stacked(document, ax, s):
    """Stacked or grouped columns (percent or absolute) — NCPlot
    port. With ``opt.horizontal`` the bars run left-to-right: all
    geometry below stays in (category c, value v) terms and ``P``
    swaps the axes at emit time."""
    from matplotlib.patches import Polygon
    from .document import StackOptions
    opt = document.stacked or StackOptions()
    horizontal = opt.horizontal
    cats = document.categories
    n_bars = len(cats[0].values)
    clip = _clip_needed(document)
    x_axis = getattr(document.style, 'xaxis', None) \
        if document.style is not None else None
    y_axis = getattr(document.style, 'yaxis', None) \
        if document.style is not None else None
    # The value axis carries the log scale — y for columns, x for bars.
    if horizontal:
        xlog = x_axis is not None and x_axis.scale == 'log'
        ylog = False
    else:
        xlog = False   # stacked x is always categorical positions
        ylog = y_axis is not None and y_axis.scale == 'log'

    def P(c, v):
        return (v, c) if horizontal else (c, v)
    totals = [sum(c.values[i] for c in cats) for i in range(n_bars)]
    widths = opt.bar_width / 2.0
    if opt.percent:
        y_max = 100.0
    elif opt.grouped:
        uppers = [(_yerr_bounds(c) or (None, [0.0] * n_bars))[1]
                  for c in cats]
        y_max = max(c.values[b] + uppers[i][b]
                    for i, c in enumerate(cats)
                    for b in range(n_bars)) * 1.02
    else:
        y_max = max(totals) * 1.02
    cat_lim = (-0.8, n_bars - 1 + 0.8)
    val_lim = (0.0, y_max)
    if horizontal:
        xlim = (document.xlim if document.xlim is not None
                else val_lim)
        ylim = (document.ylim if document.ylim is not None
                else cat_lim)
        ax.set_ylim(ylim)
        # Bars are bare Polygon patches, which never trigger
        # autoscaling, so the default range is set explicitly (a log
        # axis keeps matplotlib's own range: a 0 lower bound is
        # invalid there).
        if opt.percent or document.xlim is not None or not xlog:
            ax.set_xlim(xlim)
        cat_view, val_view = ylim, xlim
    else:
        xlim, ylim = _view_limits(document, ax, cat_lim, val_lim)
        ax.set_xlim(xlim)
        # Bars are bare Polygon patches, which never trigger y
        # autoscaling, so the default range is set explicitly (a log
        # axis keeps matplotlib's own range: a 0 lower bound is
        # invalid there).
        if opt.percent or document.ylim is not None or not ylog:
            ax.set_ylim(ylim)
        cat_view, val_view = xlim, ylim
    bottoms = [0.0] * n_bars
    value_fs = (opt.value_size_pt
                if opt.value_size_pt is not None
                else document.font_size_pt * 6.0 / 7.0)
    if opt.grouped:
        n_cats = len(cats)
        w = opt.bar_width / n_cats
        for i, c in enumerate(cats):
            gid = f'ilmplot-stack-{c.id}'
            err_segs = []
            bounds = _yerr_bounds(c)
            for b in range(n_bars):
                v = c.values[b]
                x = b - opt.bar_width / 2.0 + w * (i + 0.5)
                if bounds is not None and (bounds[0][b] > 0
                                           or bounds[1][b] > 0):
                    lo, hi = v - bounds[0][b], v + bounds[1][b]
                    in_x = not clip or (min(cat_view) <= x
                                        <= max(cat_view))
                    if in_x and clip:
                        if lo > max(val_view) or hi < min(val_view):
                            in_x = False
                        else:
                            lo = max(lo, min(val_view))
                            hi = min(hi, max(val_view))
                    if in_x and hi >= lo:
                        err_segs.append((P(x, lo), P(x, hi)))
                pts = [P(x - w / 2, 0.0), P(x + w / 2, 0.0),
                       P(x + w / 2, v), P(x - w / 2, v)]
                xs = [p[0] for p in pts]
                ys = [p[1] for p in pts]
                if clip:
                    xs, ys = clip_polygon_to_view(xs, ys, xlim, ylim,
                                                  xlog, ylog)
                if xs:
                    patch = Polygon(list(zip(xs, ys)), closed=True,
                                    facecolor=c.color,
                                    edgecolor='none'
                                    if opt.edge_width_pt == 0
                                    else opt.edge_color,
                                    linewidth=opt.edge_width_pt * s,
                                    zorder=2)
                    patch.set_gid(gid)
                    ax.add_patch(patch)
                if opt.show_values and v > 0:
                    if clip and not (min(val_view) <= v
                                     <= max(val_view)):
                        continue
                    text = f'{v:.{opt.value_decimals}f}'
                    # Labels sit past the bar end on the background:
                    # the default white (meant for inside stacked
                    # segments) would vanish, so it falls back to
                    # black.
                    tx, ty = P(x, v)
                    t = ax.text(tx, ty, safe_text(text),
                                ha='left' if horizontal else 'center',
                                va='center' if horizontal else 'bottom',
                                fontsize=value_fs * s,
                                color='#000000'
                                if opt.value_color == '#ffffff'
                                else opt.value_color,
                                fontweight='bold' if opt.value_bold
                                else 'normal', zorder=3)
                    t.set_gid(gid)
            if err_segs:
                from matplotlib.collections import LineCollection
                coll = LineCollection(err_segs, colors='#000000',
                                      linewidths=1.5 * s, zorder=3)
                coll.set_gid(gid)
                ax.add_collection(coll)
        return
    for c in cats:
        gid = f'ilmplot-stack-{c.id}'
        for b in range(n_bars):
            v = c.values[b]
            share = v / totals[b] * 100.0 if totals[b] else 0.0
            h = share if opt.percent else v
            y0, y1 = bottoms[b], bottoms[b] + h
            pts = [P(b - widths, y0), P(b + widths, y0),
                   P(b + widths, y1), P(b - widths, y1)]
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            if clip:
                xs, ys = clip_polygon_to_view(xs, ys, xlim, ylim,
                                              xlog, ylog)
            if xs:
                patch = Polygon(list(zip(xs, ys)), closed=True,
                                facecolor=c.color,
                                edgecolor='none'
                                if opt.edge_width_pt == 0
                                else opt.edge_color,
                                linewidth=opt.edge_width_pt * s,
                                zorder=2)
                patch.set_gid(gid)
                ax.add_patch(patch)
            bottoms[b] += h
            if opt.show_values and share >= opt.value_threshold \
                    and h > 0:
                mid = (y0 + y1) / 2.0
                if clip and not (min(val_view) <= mid
                                 <= max(val_view)):
                    continue
                text = (f'{share:.{opt.value_decimals}f}%'
                        if opt.percent
                        else f'{v:.{opt.value_decimals}f}')
                tx, ty = P(b, mid)
                t = ax.text(tx, ty, safe_text(text), ha='center',
                            va='center', fontsize=value_fs * s,
                            color=opt.value_color,
                            fontweight='bold' if opt.value_bold
                            else 'normal', zorder=3)
                t.set_gid(gid)


def _hist_bins(document):
    """Shared bin ``edges`` plus per-group counts/density.

    Every group in a histogram shares one edge list so the outlines
    compare directly.
    """
    import numpy as np
    from .document import HistOptions
    opt = document.histogram or HistOptions()
    pooled = np.asarray([v for g in document.groups
                         for v in g.values], dtype=float)
    lo, hi = float(pooled.min()), float(pooled.max())
    if lo == hi:
        edges = np.asarray([lo - 0.5, hi + 0.5])
    elif opt.bin_width:
        w = float(opt.bin_width)
        start = math.floor(lo / w) * w
        stop = math.ceil(hi / w) * w
        if stop <= start:
            stop = start + w
        edges = np.arange(start, stop + w / 2.0, w)
        if len(edges) > 2000:
            edges = np.linspace(start, stop, 2000)
    elif opt.bins:
        edges = np.linspace(lo, hi, opt.bins + 1)
    else:
        edges = np.histogram_bin_edges(pooled, bins='auto')
        if len(edges) > 2000:
            edges = np.linspace(lo, hi, 2000)
    counts = [np.histogram(g.values, edges, density=opt.density)[0]
              for g in document.groups]
    return list(edges), counts


def _hist_label(opt, g):
    label = safe_text(g.label)
    if opt.show_n:
        label = f"{label} ({safe_text(opt.n_format.format(n=len(g.values)))})"
    return label


def _draw_histogram(document, ax, s):
    """Overlaid group histograms (bars outline or step) + optional KDE."""
    import numpy as np
    from matplotlib.patches import Polygon
    from matplotlib.colors import to_rgba
    from . import stats
    from .document import HistOptions
    opt = document.histogram or HistOptions()
    clip = _clip_needed(document)
    x_axis = getattr(document.style, 'xaxis', None) \
        if document.style is not None else None
    y_axis = getattr(document.style, 'yaxis', None) \
        if document.style is not None else None
    xlog = x_axis is not None and x_axis.scale == 'log'
    ylog = y_axis is not None and y_axis.scale == 'log'
    edges, counts = _hist_bins(document)
    top = max((float(c.max()) for c in counts if len(c)), default=0.0)
    pad = (edges[-1] - edges[0]) * 0.02
    xlim, ylim = _view_limits(document, ax,
                              (edges[0] - pad, edges[-1] + pad),
                              (0.0, top * 1.05 or 1.0))
    ax.set_xlim(xlim)
    # Polygons don't autoscale: pin the default range (a log y axis
    # keeps matplotlib's own range unless the document pins one).
    if document.ylim is not None or not ylog:
        ax.set_ylim(ylim)
    for g, c in zip(document.groups, counts):
        gid = f'ilmplot-hist-{g.id}'
        xs = [e for e in edges for _ in (0, 1)]
        ys = [0.0] + [float(v) for v in c for _ in (0, 1)] + [0.0]
        if opt.style == 'step':
            if clip:
                xs_c, ys_c, _m = clip_series_to_view(
                    xs, ys, xlim, ylim, xlog, ylog)
            else:
                xs_c, ys_c = xs, ys
            line, = ax.plot(xs_c, ys_c, color=g.color,
                            linewidth=1.5 * s, zorder=2,
                            label=_hist_label(opt, g))
            line.set_gid(gid)
        else:
            px, py = xs, ys
            if clip:
                px, py = clip_polygon_to_view(px, py, xlim, ylim,
                                              xlog, ylog)
            if px:
                patch = Polygon(
                    list(zip(px, py)), closed=True,
                    facecolor=to_rgba(g.color, opt.fill_alpha),
                    edgecolor='none' if opt.edge_width_pt == 0
                    else (opt.edge_color or g.color),
                    linewidth=opt.edge_width_pt * s, zorder=2,
                    label=_hist_label(opt, g))
                patch.set_gid(gid)
                ax.add_patch(patch)
        if opt.kde and len(g.values) >= 2:
            sd = float(np.std(g.values, ddof=1))
            if sd > 0:
                evaluate, bw = stats.gaussian_kde(g.values,
                                                  opt.bandwidth)
                grid = np.linspace(edges[0], edges[-1], 200)
                scale = 1.0 if opt.density else \
                    len(g.values) * float(np.mean(np.diff(edges)))
                y = evaluate(grid) * scale
                gx, gy = list(grid), list(y)
                if clip:
                    gx, gy, _m = clip_series_to_view(
                        gx, gy, xlim, ylim, xlog, ylog)
                line, = ax.plot(gx, gy, color=g.color,
                                linewidth=1.5 * s, zorder=3,
                                label='_nolegend_')
                line.set_gid(gid)


_ANCHOR_XY = {
    'upper left': (0.02, 0.98, 'left', 'top'),
    'upper center': (0.5, 0.98, 'center', 'top'),
    'upper right': (0.98, 0.98, 'right', 'top'),
    'lower left': (0.02, 0.02, 'left', 'bottom'),
    'lower center': (0.5, 0.02, 'center', 'bottom'),
    'lower right': (0.98, 0.02, 'right', 'bottom'),
    'center left': (0.02, 0.5, 'left', 'center'),
    'center right': (0.98, 0.5, 'right', 'center'),
}


def _data_y_range(document):
    """(y_max, y_range) for bracket placement, per kind."""
    if document.kind == 'violin':
        vals = [v for g in document.groups for v in g.values]
        v_opt = document.violin
        if v_opt is not None and v_opt.body == 'bar':
            import numpy as np
            top = max(vals)
            for g in document.groups:
                mean = float(np.mean(g.values))
                n_v = len(g.values)
                sd = float(np.std(g.values, ddof=1)) if n_v >= 2 \
                    else 0.0
                if v_opt.bar_error == 'sem':
                    err = sd / math.sqrt(n_v) if n_v else 0.0
                elif v_opt.bar_error == 'sd':
                    err = sd
                else:
                    err = 0.0
                top = max(top, mean + err)
            rng = (top - min(0.0, min(vals))) or 1.0
            if v_opt.show_n and v_opt.n_position == 'top':
                top += 0.08 * rng
            return top, rng
        rng = (max(vals) - min(vals)) or 1.0
        top = max(vals)
        if v_opt is not None and v_opt.show_n \
                and v_opt.n_position == 'top':
            top += 0.08 * rng
        return top, rng
    if document.kind == 'histogram':
        _edges, counts = _hist_bins(document)
        top = max((float(c.max()) for c in counts if len(c)),
                  default=0.0)
        return top, top or 1.0
    if document.kind == 'stacked_column':
        opt = document.stacked
        percent = opt.percent if opt is not None else True
        if percent:
            return 100.0, 100.0
        if opt is not None and opt.grouped:
            uppers = [
                (_yerr_bounds(c)
                 or (None, [0.0] * len(c.values)))[1]
                for c in document.categories]
            top = max(v + uppers[j][i]
                      for j, c in enumerate(document.categories)
                      for i, v in enumerate(c.values))
            return top, top or 1.0
        n_bars = len(document.categories[0].values)
        totals = [sum(c.values[i] for c in document.categories)
                  for i in range(n_bars)]
        top = max(totals)
        return top, top or 1.0
    if document.kind == 'ridgeline':
        offset = _ridge_offset(document)
        top = 0.0
        for i, s_ in enumerate(document.series):
            if s_.y:
                top = max(top, i * offset + max(s_.y) - min(s_.y))
        return top, top or 1.0
    ys = [y for s_ in document.series for y in s_.y]
    for b_ in document.bands:
        ys += list(b_.y1) + list(b_.y2)
    return max(ys), (max(ys) - min(ys)) or 1.0


def _ridge_offset(document):
    opt = document.ridgeline
    if opt is not None and opt.offset:
        return opt.offset
    max_range = 0.0
    for s_ in document.series:
        if s_.y:
            max_range = max(max_range, max(s_.y) - min(s_.y))
    return max_range * 1.05 if max_range > 0 else 1.0


def _draw_annotations(document, ax, s):
    for ann in document.annotations:
        if ann.x is not None and ann.y is not None:
            x, y, ha, va = ann.x, ann.y, 'center', 'center'
        else:
            x, y, ha, va = _ANCHOR_XY[ann.anchor]
        kw = _text_kwargs(ann.style, document.font_family,
                          document.font_size_pt, s)
        if ann.box:
            kw['bbox'] = dict(boxstyle='round,pad=0.3',
                              facecolor='white', edgecolor='none',
                              alpha=0.8)
        t = ax.text(x, y, safe_text(ann.text), transform=ax.transAxes,
                    ha=ha, va=va, zorder=10, **kw)
        t.set_gid(f'ilmplot-annotation-{ann.id}')


def _draw_brackets(document, ax, s):
    if not document.brackets:
        return
    ymax, yrange = _data_y_range(document)
    index_kind = document.kind in ('violin', 'stacked_column')
    for br in document.brackets:
        pa = br.a + 1 if document.kind == 'violin' else br.a
        pb = br.b + 1 if document.kind == 'violin' else br.b
        y = ymax + yrange * br.offset
        tick = yrange * 0.01
        color = br.style.color if br.style is not None else '#333333'
        kw = _text_kwargs(br.style, document.font_family, 8.0, s)
        if br.style is None:
            kw['color'] = '#333333'
        gid = f'ilmplot-bracket-{br.id}'
        for xs, ys in (((pa, pb), (y, y)),
                       ((pa, pa), (y - tick, y)),
                       ((pb, pb), (y - tick, y))):
            line, = ax.plot(xs, ys, color=color, linewidth=1.0 * s,
                            zorder=10, clip_on=False)
            line.set_gid(gid)
        t = ax.text((pa + pb) / 2.0, y + yrange * 0.01,
                    safe_text(br.text), ha='center', va='bottom',
                    zorder=10, clip_on=False, **kw)
        t.set_gid(gid)


def _build_figure(document: PlotDocument, s: float,
                  width_mm: float, height_mm: float):
    """Build (Figure, Axes) for *document* at typography scale *s*."""
    from matplotlib.figure import Figure
    from matplotlib.ticker import (AutoMinorLocator, LogLocator,
                                   MultipleLocator, NullFormatter)
    style = document.style
    x_axis = getattr(style, 'xaxis', None) if style is not None else None
    y_axis = getattr(style, 'yaxis', None) if style is not None else None
    kind = document.kind
    horizontal_bars = kind == 'stacked_column' \
        and document.stacked is not None and document.stacked.horizontal
    categorical_y = horizontal_bars
    categorical_x = (bool(document.x_tick_labels) or kind in (
        'violin', 'stacked_column')) and not horizontal_bars
    fig = Figure(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax = fig.add_axes(list(document.axes_rect))
    lines = []
    span_polys = []
    band_polys = []
    err_polys = []
    if kind == 'violin':
        _draw_violin(document, ax, s)
    elif kind == 'ridgeline':
        _draw_ridgeline(document, ax, s, lines)
    elif kind == 'stacked_column':
        _draw_stacked(document, ax, s)
    elif kind == 'histogram':
        _draw_histogram(document, ax, s)
    else:
        for sp_ in document.spans:
            # Full-height/width strips sit below everything (zorder 0.9):
            # a unit rect through a blended axis transform.
            from matplotlib.patches import Polygon
            if sp_.axis == 'x':
                verts = [(sp_.lo, 0.0), (sp_.hi, 0.0),
                         (sp_.hi, 1.0), (sp_.lo, 1.0)]
                trans = ax.get_xaxis_transform()
                ax.update_datalim([(sp_.lo, 0.0), (sp_.hi, 0.0)],
                                  updatey=False)
            else:
                verts = [(0.0, sp_.lo), (1.0, sp_.lo),
                         (1.0, sp_.hi), (0.0, sp_.hi)]
                trans = ax.get_yaxis_transform()
                ax.update_datalim([(0.0, sp_.lo), (0.0, sp_.hi)],
                                  updatex=False)
            poly = Polygon(verts, closed=True, transform=trans,
                           facecolor=sp_.color, edgecolor='none',
                           linewidth=0, zorder=0.9)
            poly.set_gid(f'ilmplot-span-{sp_.id}')
            ax.add_patch(poly)
            span_polys.append((poly, sp_))
        # On a log axis non-positive band coordinates are excluded
        # from datalim (a baseline of 0 must not poison autoscale) and
        # clipped to the view once limits are final (below).
        xlog_d = x_axis is not None and x_axis.scale == 'log' \
            and not categorical_x
        ylog_d = y_axis is not None and y_axis.scale == 'log'
        for b_ in document.bands:
            from matplotlib.patches import Polygon
            xs = list(b_.x) + list(b_.x)[::-1]
            ys = list(b_.y1) + list(b_.y2)[::-1]
            poly = Polygon(list(zip(xs, ys)), closed=True,
                           facecolor=b_.color, edgecolor='none',
                           linewidth=0, zorder=1)
            poly.set_gid(f'ilmplot-band-{b_.id}')
            ax.add_patch(poly)
            ax.update_datalim([
                (x, y) for x, y in poly.get_path().vertices
                if (not xlog_d or x > 0) and (not ylog_d or y > 0)])
            band_polys.append((poly, b_))
        for s_ in document.series:
            # A 0-width stroke renders as a hairline under QtSvg — hide
            # the stroke instead (markers still draw).
            ls = s_.linestyle if s_.linestyle else 'None'
            line, = ax.plot(
                s_.x, s_.y,
                color=s_.color,
                linewidth=max(s_.linewidth_pt * s, 1e-3),
                linestyle='None' if s_.linewidth_pt == 0 else ls,
                marker=s_.marker or None,
                markersize=max(s_.markersize_pt * s, 0.0),
                markeredgewidth=1.0 * s,
                label=safe_text(s_.label) or '_nolegend_',
            )
            line.set_gid(f'ilmplot-series-{s_.id}')
            lines.append((line, s_))
            if _yerr_bounds(s_) is not None:
                if getattr(s_, 'error_style', 'bars') == 'band':
                    got = _series_errband_poly(document, ax, s_)
                    if got is not None:
                        err_polys.append(got)
                else:
                    _draw_series_yerr(document, ax, s_, s,
                                      f'ilmplot-series-{s_.id}')
    if kind == 'violin':
        v_opt = document.violin
        tick_n = v_opt is not None and v_opt.show_n \
            and v_opt.n_position == 'tick'
        ax.set_xticks(list(range(1, len(document.groups) + 1)),
                      [safe_text(g.label) + '\n' + _n_text(v_opt, g)
                       if tick_n else safe_text(g.label)
                       for g in document.groups])
    elif kind == 'stacked_column':
        n_bars = len(document.categories[0].values)
        if document.x_tick_labels:
            labels = {p: safe_text(l)
                      for p, l in document.x_tick_labels}
        else:
            labels = {}
        set_ticks = ax.set_yticks if horizontal_bars else ax.set_xticks
        set_ticks(list(range(n_bars)),
                  [labels.get(float(i), str(i))
                   for i in range(n_bars)])
    elif categorical_x:
        ax.set_xticks([p for p, _l in document.x_tick_labels],
                      [safe_text(l) for _p, l in document.x_tick_labels])
    # Axis scales first so locators/formatters see the right transform.
    if x_axis is not None and x_axis.scale != 'linear' and not categorical_x:
        ax.set_xscale(x_axis.scale)
    if y_axis is not None and y_axis.scale != 'linear' \
            and not categorical_y:
        ax.set_yscale(y_axis.scale)
    if document.xlim is not None:
        ax.set_xlim(document.xlim)
    if document.ylim is not None:
        ax.set_ylim(document.ylim)
    # Tick locators (need final limits for the step density check).
    for axis, ast, axis_obj in (
            (ax.xaxis, x_axis, 'x'), (ax.yaxis, y_axis, 'y')):
        if ast is None:
            continue
        categorical = (categorical_x and axis_obj == 'x') \
            or (categorical_y and axis_obj == 'y')
        if ast.step is not None and not categorical \
                and ast.scale == 'linear':
            lo, hi = (ax.get_xlim() if axis_obj == 'x'
                      else ax.get_ylim())
            if abs(hi - lo) / ast.step <= 1000:
                axis.set_major_locator(MultipleLocator(ast.step))
        if ast.minor:
            if ast.scale == 'log' and not categorical:
                axis.set_minor_locator(LogLocator(base=10.0, subs='auto'))
            elif not categorical:
                axis.set_minor_locator(AutoMinorLocator())
            axis.set_minor_formatter(NullFormatter())
        if ast.prefix or ast.suffix or ast.decimals is not None:
            axis.set_major_formatter(_AffixFormatter(
                axis.get_major_formatter(), ast.prefix, ast.suffix,
                ast.decimals, numeric=not categorical))
    # Reversed axes after limits are final.
    if x_axis is not None and x_axis.reversed \
            and not ax.xaxis_inverted():
        ax.invert_xaxis()
    if y_axis is not None and y_axis.reversed \
            and not ax.yaxis_inverted():
        ax.invert_yaxis()
    # QtSvg ignores clipPath: clip data to the axes box ourselves, but
    # only when the document pins a limit (unlimited docs keep the
    # autoscaled box that already contains every point → identical bytes).
    if document.xlim is not None or document.ylim is not None:
        ax.autoscale(False)
        xlog = ax.get_xscale() == 'log'
        ylog = ax.get_yscale() == 'log'
        for line, s_ in lines:
            xs, ys, mask = clip_series_to_view(
                s_.x, s_.y, ax.get_xlim(), ax.get_ylim(), xlog, ylog)
            line.set_data(xs, ys)
            if s_.marker:
                line.set_markevery(mask)
        for poly, b_ in band_polys:
            xs, ys = clip_polygon_to_view(
                list(b_.x) + list(b_.x)[::-1],
                list(b_.y1) + list(b_.y2)[::-1],
                ax.get_xlim(), ax.get_ylim(), xlog, ylog)
            if xs:
                poly.set_xy(list(zip(xs, ys)))
            else:
                poly.set_visible(False)
        for poly, xs0, ys0 in err_polys:
            xs, ys = clip_polygon_to_view(
                xs0, ys0, ax.get_xlim(), ax.get_ylim(), xlog, ylog)
            if xs:
                poly.set_xy(list(zip(xs, ys)))
            else:
                poly.set_visible(False)
    # Span strips draw through a blended axis transform, so their
    # data-axis extent is clipped to the final view limits by hand —
    # QtSvg ignores clipPath. ``get_xlim``/``get_ylim`` un-stale the
    # view (autoscale has already run when limits were pinned).
    if span_polys:
        ax.autoscale_view(tight=False)
        for poly, sp_ in span_polys:
            log = (ax.get_xscale() == 'log' if sp_.axis == 'x'
                   else ax.get_yscale() == 'log')
            view = (ax.get_xlim() if sp_.axis == 'x'
                    else ax.get_ylim())
            lo_v, hi_v = min(view), max(view)
            lo, hi = sp_.lo, sp_.hi
            if log and lo <= 0:
                lo = lo_v
            if hi < lo_v or lo > hi_v:
                poly.set_visible(False)
                continue
            lo, hi = max(lo, lo_v), min(hi, hi_v)
            if not lo < hi:
                poly.set_visible(False)
                continue
            if sp_.axis == 'x':
                poly.set_xy([(lo, 0.0), (hi, 0.0), (hi, 1.0),
                             (lo, 1.0)])
            else:
                poly.set_xy([(0.0, lo), (1.0, lo), (1.0, hi),
                             (0.0, hi)])
    # Bands on a log axis are clipped once limits are final even when
    # nothing is pinned (re-clipping a pinned band is idempotent).
    # Non-positive coordinates count as the view minimum, so a baseline
    # of 0 clamps to the bottom edge instead of being dropped.
    if band_polys:
        xlog_v = ax.get_xscale() == 'log'
        ylog_v = ax.get_yscale() == 'log'
        if xlog_v or ylog_v:
            ax.autoscale_view(tight=False)
            vx, vy = ax.get_xlim(), ax.get_ylim()
            for poly, b_ in band_polys:
                xs = [v if not xlog_v or v > 0 else min(vx)
                      for v in list(b_.x) + list(b_.x)[::-1]]
                ys = [v if not ylog_v or v > 0 else min(vy)
                      for v in list(b_.y1) + list(b_.y2)[::-1]]
                xs2, ys2 = clip_polygon_to_view(
                    xs, ys, vx, vy, xlog_v, ylog_v)
                if xs2:
                    poly.set_xy(list(zip(xs2, ys2)))
                else:
                    poly.set_visible(False)
    underlines = []
    t_style = getattr(style, 'title', None) if style is not None else None
    if document.title:
        kw = _text_kwargs(t_style, document.font_family,
                          document.title_size_pt, s)
        loc = t_style.align if t_style is not None else 'center'
        t = ax.set_title(safe_text(document.title), pad=6.0 * s,
                         loc=loc, **kw)
        t.set_gid('ilmplot-title')
        if t_style is not None and t_style.underline:
            underlines.append(lambda t=t: [t])
    xl_style = getattr(style, 'xlabel', None) if style is not None else None
    yl_style = getattr(style, 'ylabel', None) if style is not None else None
    if document.xlabel:
        xl = ax.set_xlabel(
            safe_text(document.xlabel),
            **_text_kwargs(xl_style, document.font_family,
                           document.font_size_pt, s))
        xl.set_gid('ilmplot-xlabel')
        if xl_style is not None and xl_style.underline:
            underlines.append(lambda t=xl: [t])
    if document.ylabel and kind != 'ridgeline':
        yl = ax.set_ylabel(
            safe_text(document.ylabel),
            **_text_kwargs(yl_style, document.font_family,
                           document.font_size_pt, s))
        yl.set_gid('ilmplot-ylabel')
        if yl_style is not None and yl_style.underline:
            underlines.append(lambda t=yl: [t])
    ax.tick_params(labelsize=document.font_size_pt * s,
                   length=3.5 * s, width=0.8 * s,
                   pad=3.5 * s)
    for axis_name, ast in (('x', x_axis), ('y', y_axis)):
        if ast is None:
            continue
        ax.tick_params(axis=axis_name, direction=ast.direction,
                       length=ast.length_pt * s,
                       labelrotation=ast.rotation or 0)
        ts = ast.ticks
        tick_labels = (ax.get_xticklabels() if axis_name == 'x'
                       else ax.get_yticklabels())
        if ts is not None:
            tick_kw = {}
            if ts.family is not None:
                tick_kw['labelfontfamily'] = ts.family
            if ts.size_pt is not None:
                tick_kw['labelsize'] = ts.size_pt * s
            tick_kw['labelcolor'] = ts.color
            ax.tick_params(axis=axis_name, **tick_kw)
            # weight/style are not tick_params keys: set them on the
            # (persistent, post-locator) tick label Text objects.
            for label in tick_labels:
                label.set_fontweight('bold' if ts.bold else 'normal')
                label.set_fontstyle('italic' if ts.italic else 'normal')
        if axis_name == 'x' and ast.rotation:
            ha = 'right' if ast.rotation > 0 else 'left'
            for label in tick_labels:
                label.set(ha=ha, rotation_mode='anchor')
        if ts is not None and ts.underline:
            labels = (ax.get_xticklabels if axis_name == 'x'
                      else ax.get_yticklabels)
            underlines.append(
                lambda labels=labels:
                [l for l in labels() if l.get_visible()])
    frame = getattr(style, 'frame', None) if style is not None else None
    # Ridgeline always drops left/top/right and its y axis, like NCPlot.
    forced = kind == 'ridgeline'
    hide = {
        'top': forced or (frame is not None and frame.hide_top),
        'right': forced or (frame is not None and frame.hide_right),
        'left': forced or (frame is not None and frame.hide_left),
        'bottom': frame is not None and frame.hide_bottom,
    }
    for name, spine in ax.spines.items():
        if hide.get(name):
            spine.set_visible(False)
            continue
        if frame is not None:
            spine.set_color(frame.color)
            if frame.linewidth_pt == 0:
                spine.set_visible(False)
            else:
                spine.set_linewidth(frame.linewidth_pt * s)
        else:
            spine.set_linewidth(0.8 * s)
    # A hidden left/bottom spine also hides that axis's ticks/labels.
    if hide['left']:
        ax.tick_params(axis='y', which='both',
                       left=False, labelleft=False)
    if hide['bottom']:
        ax.tick_params(axis='x', which='both',
                       bottom=False, labelbottom=False)
    ax.xaxis.labelpad = 4.0 * s
    ax.yaxis.labelpad = 4.0 * s
    # Tick offset / scientific-notation text is not covered by
    # tick_params labelsize — set it explicitly.
    for axis in (ax.xaxis, ax.yaxis):
        try:
            axis.get_offset_text().set_size(
                document.font_size_pt * s)
        except Exception:
            pass
    if document.grid:
        grid = getattr(style, 'grid', None) if style is not None else None
        if grid is None:
            ax.grid(True, color='#b0b0b0', linewidth=0.8 * s, alpha=1.0)
        else:
            if grid.which == 'both':
                for axis_name, ast in (('x', x_axis), ('y', y_axis)):
                    if grid.axis in ('both', axis_name) and (
                            ast is None or not ast.minor):
                        axis = ax.xaxis if axis_name == 'x' else ax.yaxis
                        categorical = (categorical_x
                                       and axis_name == 'x') or \
                            (categorical_y and axis_name == 'y')
                        if categorical:
                            continue
                        if ast is not None and ast.scale == 'log':
                            axis.set_minor_locator(
                                LogLocator(base=10.0, subs='auto'))
                        else:
                            axis.set_minor_locator(AutoMinorLocator())
                        axis.set_minor_formatter(NullFormatter())
            if grid.linewidth_pt > 0:
                ax.grid(True, which=grid.which, axis=grid.axis,
                        color=grid.color, linestyle=grid.linestyle,
                        linewidth=grid.linewidth_pt * s,
                        alpha=grid.alpha)
    if document.legend:
        from matplotlib.patches import Patch
        if kind == 'stacked_column':
            handles = [Patch(facecolor=c.color,
                             label=safe_text(c.label) or '_nolegend_')
                       for c in document.categories]
            patch_handles = True
        elif kind == 'histogram':
            h_opt = document.histogram
            if h_opt is not None and h_opt.show_n:
                h_labels = [_hist_label(h_opt, g)
                            for g in document.groups]
            else:
                h_labels = [safe_text(g.label)
                            for g in document.groups]
            if h_opt is not None and h_opt.style == 'step':
                from matplotlib.lines import Line2D
                handles = [Line2D([], [], color=g.color, linewidth=1.5,
                                  label=l or '_nolegend_')
                           for g, l in zip(document.groups, h_labels)]
            else:
                from matplotlib.colors import to_rgba
                alpha = h_opt.fill_alpha if h_opt is not None else 0.5
                handles = [
                    Patch(facecolor=to_rgba(g.color, alpha),
                          label=l or '_nolegend_')
                    for g, l in zip(document.groups, h_labels)]
            patch_handles = True
        else:
            patch_handles = False
            handles = [l for l in ax.get_lines()
                       if l.get_label()
                       and not l.get_label().startswith('_')]
            handles += [Patch(facecolor=b_.color,
                              label=safe_text(b_.label))
                        for b_ in document.bands if b_.label]
            handles += [Patch(facecolor=sp_.color,
                              label=safe_text(sp_.label))
                        for sp_ in document.spans if sp_.label]
        if handles:
            leg_style = getattr(style, 'legend', None) \
                if style is not None else None
            loc = document.legend_location
            leg_kw = {'loc': loc,
                      'fontsize': document.font_size_pt * s}
            if loc == 'outside right':
                leg_kw['loc'] = 'center left'
                leg_kw['bbox_to_anchor'] = (1.02, 0.5)
            if leg_style is not None:
                leg_kw['ncols'] = leg_style.ncols
                leg_kw['frameon'] = leg_style.frame
                if leg_style.frame_color != '#cccccc':
                    leg_kw['edgecolor'] = leg_style.frame_color
                if leg_style.text is not None:
                    from matplotlib.font_manager import FontProperties
                    ts = leg_style.text
                    # ``prop`` supersedes ``fontsize`` — drop it.
                    del leg_kw['fontsize']
                    leg_kw['prop'] = FontProperties(
                        family=ts.family or document.font_family,
                        size=(ts.size_pt * s if ts.size_pt is not None
                              else document.font_size_pt * s),
                        weight='bold' if ts.bold else 'normal',
                        style='italic' if ts.italic else 'normal')
                    leg_kw['labelcolor'] = ts.color
            leg = ax.legend(handles=handles, **leg_kw)
            if leg is not None:
                frame = leg.get_frame()
                frame.set_linewidth(frame.get_linewidth() * s)
                if leg_style is not None and leg_style.text is not None \
                        and leg_style.text.underline:
                    underlines.append(
                        lambda leg=leg: [t for t in leg.get_texts()
                                         if t.get_visible()])
    _draw_annotations(document, ax, s)
    _draw_brackets(document, ax, s)
    # Brackets sit above the data; auto-scaled y limits don't reach them.
    # Extend the top so the bracket line plus ~10% (its text) fits —
    # except percent-stacked bars, where 0–100 stays fixed like NCPlot.
    if document.brackets and document.ylim is None:
        percent = (kind == 'stacked_column'
                   and (document.stacked is None
                        or document.stacked.percent))
        if not percent:
            ymax, yrange = _data_y_range(document)
            top = ymax + yrange * (
                max(b.offset for b in document.brackets) + 0.10)
            lo, hi = ax.get_ylim()
            if top > hi:
                ax.set_ylim(lo, top)
    if underlines:
        _add_underline(ax, lambda: [t for get in underlines
                                    for t in get()])
    return fig, ax


_regions_cache: OrderedDict = OrderedDict()
_REGIONS_CACHE_MAX = 32


def element_regions(document: PlotDocument) -> dict:
    """Bounding boxes of every drawable element, in figure fractions.

    Coordinates are ``(x0, y0, x1, y1)`` with top-left origin (``x/W``,
    ``1 - y/H``) so the editor can map them onto the SVG item's rect.
    Cached by the canonical document like ``render_document``.
    """
    document.validate()
    key = ('regions', _canonical(document))
    hit = _regions_cache.get(key)
    if hit is not None:
        _regions_cache.move_to_end(key)
        return hit

    import matplotlib
    from matplotlib.backends.backend_agg import FigureCanvasAgg

    regions = {}
    with matplotlib.rc_context(_deterministic_rc(document)):
        fig = None
        try:
            fig, ax = _build_figure(document, 1.0, document.width_mm,
                                    document.height_mm)
            _fit_figure(document, fig, ax)
            canvas = FigureCanvasAgg(fig)
            canvas.draw()
            renderer = canvas.get_renderer()
            W, H = canvas.get_width_height()

            def frac(bb):
                # Hit-testing happens inside the canvas — clamp to it.
                return (max(0.0, min(1.0, bb.x0 / W)),
                        max(0.0, min(1.0, 1.0 - bb.y1 / H)),
                        max(0.0, min(1.0, bb.x1 / W)),
                        max(0.0, min(1.0, 1.0 - bb.y0 / H)))

            # loc='left'/'right' titles live on _left_title/_right_title.
            t_style = getattr(document.style, 'title', None) \
                if document.style is not None else None
            title_artist = {None: ax.title, 'center': ax.title,
                            'left': ax._left_title,
                            'right': ax._right_title}[
                getattr(t_style, 'align', None)]
            for name, artist in (('title', title_artist),
                                 ('xlabel', ax.xaxis.label),
                                 ('ylabel', ax.yaxis.label)):
                if artist.get_visible() and artist.get_text():
                    regions[name] = frac(
                        artist.get_window_extent(renderer))
            for name, labels in (('xticks', ax.get_xticklabels()),
                                 ('yticks', ax.get_yticklabels())):
                boxes = [l.get_window_extent(renderer) for l in labels
                         if l.get_visible() and l.get_text()]
                if boxes:
                    x0 = min(b.x0 for b in boxes)
                    y0 = min(b.y0 for b in boxes)
                    x1 = max(b.x1 for b in boxes)
                    y1 = max(b.y1 for b in boxes)

                    class _B:
                        pass
                    bb = _B()
                    bb.x0, bb.y0, bb.x1, bb.y1 = x0, y0, x1, y1
                    regions[name] = frac(bb)
            leg = ax.get_legend()
            if leg is not None:
                regions['legend'] = frac(leg.get_window_extent(renderer))
            rect = ax.get_position()
            regions['frame'] = (rect.x0, 1.0 - rect.y1,
                                rect.x1, 1.0 - rect.y0)
            if document.grid:
                regions['grid'] = regions['frame']
            series_regions = {}
            for line in ax.get_lines():
                gid = line.get_gid() or ''
                if not gid.startswith('ilmplot-series-'):
                    continue
                sid = gid[len('ilmplot-series-'):]
                try:
                    pts = ax.transData.transform(
                        list(zip(line.get_xdata(), line.get_ydata())))
                except Exception:
                    continue
                n = len(pts)
                if not n:
                    continue
                step = max(1, -(-n // 2000))
                sampled = pts[::step]
                fps = [(float(p[0]) / W, 1.0 - float(p[1]) / H)
                       for p in sampled]
                xs = [p[0] for p in fps]
                ys = [p[1] for p in fps]
                series_regions[sid] = {
                    'bbox': (min(xs), min(ys), max(xs), max(ys)),
                    'points': fps,
                }
            regions['series'] = series_regions
            # Kind-specific element groups keyed by id.
            for prefix, key in (('ilmplot-violin-', 'violins'),
                                ('ilmplot-stack-', 'stacks'),
                                ('ilmplot-hist-', 'hists'),
                                ('ilmplot-annotation-', 'annotations'),
                                ('ilmplot-bracket-', 'brackets'),
                                ('ilmplot-band-', 'bands'),
                                ('ilmplot-span-', 'spans')):
                grouped = {}
                points = {}
                for artist in ax.findobj():
                    gid = artist.get_gid() or ''
                    if not gid.startswith(prefix):
                        continue
                    aid = gid[len(prefix):]
                    if not artist.get_visible():
                        continue
                    try:
                        bb = artist.get_window_extent(renderer)
                    except Exception:
                        continue
                    if bb.width <= 0 and bb.height <= 0:
                        continue
                    if aid in grouped:
                        prev = grouped[aid]
                        bb = type(bb).from_extents(
                            min(prev.x0, bb.x0), min(prev.y0, bb.y0),
                            max(prev.x1, bb.x1), max(prev.y1, bb.y1))
                    grouped[aid] = bb
                    if key in ('bands', 'spans'):
                        # The region polygon for point-in-polygon picks.
                        try:
                            tp = artist.get_transform().transform(
                                artist.get_path().vertices)
                            points[aid] = [
                                (float(q[0]) / W,
                                 1.0 - float(q[1]) / H)
                                for q in tp]
                        except Exception:
                            pass
                if grouped:
                    regions[key] = {
                        aid: {'bbox': frac(bb),
                              'points': points.get(aid)}
                        for aid, bb in grouped.items()}
        finally:
            if fig is not None:
                fig.clear()
    _regions_cache[key] = regions
    if len(_regions_cache) > _REGIONS_CACHE_MAX:
        _regions_cache.popitem(last=False)
    return regions


def _atomic_write(path, write):
    """Temp-sibling write, fsync, ``os.replace`` (same pattern as
    ``export._atomic_write`` — duplicated to avoid an import cycle)."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent,
                               prefix='.' + os.path.basename(path),
                               suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as fh:
            write(fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def export_document(document: PlotDocument, path: str, fmt: str,
                    dpi: int = 300, *, transparent: bool = False):
    """Export *document* via the native figure to pdf/svg/png/tiff/jpeg.

    Same figure and rc context as ``render_document`` (style scale 1);
    writes atomically. ``transparent`` applies only to png/svg: it drops
    the figure and axes background patches; other formats stay opaque.
    """
    document.validate()
    if fmt not in ('pdf', 'svg', 'png', 'tiff', 'jpeg'):
        raise PlotDocumentError(f"unsupported export format {fmt!r}")
    import matplotlib
    with matplotlib.rc_context(_deterministic_rc(document)):
        fig = None
        try:
            fig, ax = _build_figure(document, 1.0, document.width_mm,
                                    document.height_mm)
            _fit_figure(document, fig, ax)

            def _write(fh):
                if fmt == 'svg':
                    fig.savefig(fh, format=fmt, metadata={'Date': None},
                                transparent=transparent)
                elif fmt == 'pdf':
                    fig.savefig(fh, format=fmt, metadata={'Date': None})
                elif fmt == 'png':
                    fig.savefig(fh, format=fmt, dpi=dpi,
                                transparent=transparent)
                else:
                    fig.savefig(fh, format=fmt, dpi=dpi)

            _atomic_write(path, _write)
        finally:
            if fig is not None:
                fig.clear()


FIT_PAD_MM = 0.5
MIN_AXES_FRACTION = 0.2


def _needs_fit(document) -> bool:
    """True when out-of-axes content requires ``_fit_axes`` margins.

    Plain line documents (the historical path) keep their fixed
    ``axes_rect`` so their rendered bytes stay identical.
    """
    return (document.kind != 'line'
            or document.legend_location == 'outside right'
            or bool(document.annotations)
            or bool(document.brackets))


_MATH_TOKEN = re.compile(r'\$[^$]*\$|\S+')


def _text_length_px(artist, renderer, text):
    """Unrotated length of *text* drawn with *artist*'s font (px)."""
    if not text:
        return 0.0
    prev = artist.get_text()
    try:
        artist.set_text(text)
        bb = artist.get_window_extent(renderer)
    finally:
        artist.set_text(prev)
    rot = artist.get_rotation() % 180.0
    return bb.height if abs(rot - 90.0) < 1.0 else bb.width


def _wrap_text(artist, renderer, limit_px):
    """Greedy word-wrap *artist* to *limit_px*; True when text changed.

    The unwrapped source is cached on ``artist._ilm_unwrapped`` so
    repeated passes re-wrap from the original.  Existing newlines are
    hard breaks; ``$...$`` math segments stay atomic and a single token
    longer than the limit keeps its own line (never split mid-word).
    """
    if limit_px <= 0:
        return False
    text = getattr(artist, '_ilm_unwrapped', None)
    if text is None:
        text = artist.get_text()
        artist._ilm_unwrapped = text
    if not text:
        return False
    lines = []
    for para in text.split('\n'):
        tokens = _MATH_TOKEN.findall(para)
        if not tokens:
            lines.append('')
            continue
        cur = ''
        for tok in tokens:
            cand = tok if not cur else cur + ' ' + tok
            if not cur \
                    or _text_length_px(artist, renderer, cand) \
                    <= limit_px:
                cur = cand
            else:
                lines.append(cur)
                cur = tok
        lines.append(cur)
    new = '\n'.join(lines)
    if new == artist.get_text():
        return False
    artist.set_text(new)
    return True


def _title_limits(fig, ax, renderer):
    """(horizontal limit, vertical limit) in px for title wrapping."""
    W = fig.get_figwidth() * fig.dpi
    H = fig.get_figheight() * fig.dpi
    pos = ax.get_window_extent(renderer)
    return (max(pos.width, 0.5 * W), max(pos.height, 0.5 * H))


def _wrap_axis_titles(fig, ax, renderer):
    """Wrap title(s) and axis labels to their axis extent; True if any
    text changed."""
    lim_x, lim_y = _title_limits(fig, ax, renderer)
    changed = False
    for artist in (ax.title, ax._left_title, ax._right_title,
                   ax.xaxis.label):
        changed = _wrap_text(artist, renderer, lim_x) or changed
    changed = _wrap_text(ax.yaxis.label, renderer, lim_y) or changed
    return changed


def _titles_overflow(fig, ax) -> bool:
    """True when any title/axis label's unwrapped length exceeds its
    wrap limit.  No text is modified."""
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    FigureCanvasAgg(fig)
    renderer = fig.canvas.get_renderer()
    lim_x, lim_y = _title_limits(fig, ax, renderer)
    for artist in (ax.title, ax._left_title, ax._right_title,
                   ax.xaxis.label, ax.yaxis.label):
        limit = lim_y if artist is ax.yaxis.label else lim_x
        text = getattr(artist, '_ilm_unwrapped', None)
        if text is None:
            text = artist.get_text()
        if _text_length_px(artist, renderer, text) > limit:
            return True
    return False


def _fit_figure(document, fig, ax) -> None:
    """Fit the axes rectangle when the document needs it."""
    if _needs_fit(document) or _titles_overflow(fig, ax):
        _fit_axes(fig, ax, FIT_PAD_MM / 25.4 * fig.dpi)


def _fit_axes(fig, ax, pad_px: float, fixed_y=None) -> None:
    """Reposition *ax* so nothing outside the axes box is clipped.

    Iterates a margin-feedback loop: each pass shrinks the axes rect by the
    measured overflow of tick labels, axis labels, title, offset text and
    legend plus *pad_px*, until every edge moves under 0.05 px (or 4
    passes).  Typography is never scaled down — when the text does not fit,
    the axes clamps to ``MIN_AXES_FRACTION`` of the figure instead.

    ``fixed_y=(y0_px, y1_px)`` (bottom-origin px) pins the axes' vertical
    extent — used to share an axes frame across a row of cells — and only
    the horizontal fit is solved.
    """
    from matplotlib.backends.backend_agg import FigureCanvasAgg
    FigureCanvasAgg(fig)
    renderer = fig.canvas.get_renderer()
    W = fig.get_figwidth() * fig.dpi
    H = fig.get_figheight() * fig.dpi
    for _ in range(6):
        wrapped = _wrap_axis_titles(fig, ax, renderer)
        pos = ax.get_window_extent(renderer)
        # Measure the out-of-axes extras first: only the artists that can
        # legitimately stick out (legend, brackets, annotations).  Other
        # clip_on=False artists (stack value labels, legend packer
        # internals) report stale/degenerate extents mid-iteration and
        # would feed a bogus, frozen overflow back into the loop.
        from matplotlib.transforms import Bbox
        extras = []
        leg = ax.get_legend()
        if leg is not None and leg.get_visible():
            try:
                extras.append(leg.get_window_extent(renderer))
            except Exception:
                pass
        for artist in ax.findobj():
            gid = artist.get_gid() or ''
            if not gid.startswith(('ilmplot-bracket-',
                                   'ilmplot-annotation-')):
                continue
            try:
                bb = artist.get_window_extent(renderer)
            except Exception:
                continue
            if math.isfinite(bb.x0) and math.isfinite(bb.y0) \
                    and math.isfinite(bb.x1) and math.isfinite(bb.y1) \
                    and (bb.width > 0 or bb.height > 0):
                extras.append(bb)
        # Wrapped titles/labels can exceed what get_tightbbox reports;
        # feed their measured extents so the margins account for them.
        for artist in (ax.title, ax._left_title, ax._right_title,
                       ax.xaxis.label, ax.yaxis.label):
            if getattr(artist, '_ilm_unwrapped', None) is None \
                    or artist.get_text() == artist._ilm_unwrapped:
                continue
            try:
                bb = artist.get_window_extent(renderer)
            except Exception:
                continue
            if math.isfinite(bb.x0) and math.isfinite(bb.y0) \
                    and math.isfinite(bb.x1) and math.isfinite(bb.y1):
                extras.append(bb)
        tight = ax.get_tightbbox(renderer)
        if extras:
            union = Bbox.union(extras)
            tight = union if tight is None \
                else Bbox.union([tight, union])
        left = max(pos.x0 - tight.x0, 0.0)
        right = max(tight.x1 - pos.x1, 0.0)
        bottom = max(pos.y0 - tight.y0, 0.0)
        top = max(tight.y1 - pos.y1, 0.0)
        x0, x1 = left + pad_px, W - right - pad_px
        if x1 - x0 < MIN_AXES_FRACTION * W:
            spare = (1.0 - MIN_AXES_FRACTION) * W
            denom = left + pad_px + right + pad_px
            x0 = spare * ((left + pad_px) / denom) if denom > 0 else spare * 0.5
            x1 = x0 + MIN_AXES_FRACTION * W
        if fixed_y is not None:
            y0, y1 = fixed_y
        else:
            y0, y1 = bottom + pad_px, H - top - pad_px
            if y1 - y0 < MIN_AXES_FRACTION * H:
                spare = (1.0 - MIN_AXES_FRACTION) * H
                denom = bottom + pad_px + top + pad_px
                y0 = spare * ((bottom + pad_px) / denom) if denom > 0 else spare * 0.5
                y1 = y0 + MIN_AXES_FRACTION * H
        if not wrapped and max(abs(x0 - pos.x0), abs(x1 - pos.x1),
                               abs(y0 - pos.y0), abs(y1 - pos.y1)) \
                < 0.05:
            break
        ax.set_position([x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H])


def _fixed_y_px(fig, v_span_mm):
    """(top_mm, bottom_mm) from the figure top -> bottom-origin px span."""
    H = fig.get_figheight() * fig.dpi
    return (H - v_span_mm[1] / 25.4 * fig.dpi,
            H - v_span_mm[0] / 25.4 * fig.dpi)


def _quantized_dims(width_mm, height_mm):
    w, h = float(width_mm), float(height_mm)
    for name, v in (('width_mm', w), ('height_mm', h)):
        if not math.isfinite(v) or v <= 0 or v > MAX_DIMENSION_MM:
            raise PlotDocumentError(
                f"{name}: expected 0 < value <= {MAX_DIMENSION_MM} mm, "
                f"got {v!r}")
    return round(w, 2), round(h, 2)


def _quantized_v_span(v_span_mm, h):
    if v_span_mm is None:
        return None
    top, bottom = float(v_span_mm[0]), float(v_span_mm[1])
    if not (math.isfinite(top) and math.isfinite(bottom)
            and 0.0 <= top < bottom <= h):
        raise PlotDocumentError(
            f"v_span_mm: expected 0 <= top < bottom <= {h} mm, "
            f"got {v_span_mm!r}")
    return round(top, 2), round(bottom, 2)


_measure_cache: OrderedDict = OrderedDict()
_MEASURE_CACHE_MAX = 64


def fit_plot_area(document: PlotDocument, width_mm: float,
                  height_mm: float, *,
                  pad_mm: float = FIT_PAD_MM) -> tuple:
    """Measure-only :func:`render_document_fitted` plot_area (no savefig)."""
    document.validate()
    w, h = _quantized_dims(width_mm, height_mm)
    key = ('measure', _canonical(document), w, h, float(pad_mm))
    hit = _measure_cache.get(key)
    if hit is not None:
        _measure_cache.move_to_end(key)
        return hit

    import matplotlib
    with matplotlib.rc_context(_deterministic_rc(document)):
        fig = None
        try:
            fig, ax = _build_figure(document, 1.0, w, h)
            _fit_axes(fig, ax, float(pad_mm) / 25.4 * fig.dpi)
            pos = ax.get_position()
        finally:
            if fig is not None:
                fig.clear()
    area = (pos.x0, 1.0 - pos.y1, pos.x1, 1.0 - pos.y0)
    _measure_cache[key] = area
    if len(_measure_cache) > _MEASURE_CACHE_MAX:
        _measure_cache.popitem(last=False)
    return area


def render_document_fitted(document: PlotDocument, width_mm: float,
                           height_mm: float, *,
                           pad_mm: float = FIT_PAD_MM,
                           v_span_mm=None) -> PlotRender:
    """Render *document* at exactly ``width_mm`` × ``height_mm``.

    Unlike :func:`render_document` the figure is sized to the target box
    (style scale 1.0, so point sizes are true) and the axes rectangle is
    solved by :func:`_fit_axes` so no text is clipped.  ``v_span_mm`` may
    pin the axes' vertical extent to ``(top_mm, bottom_mm)`` measured from
    the figure's top edge (row-aligned axes frames).  The embedded metadata
    carries the *original* document, not the fitted geometry.
    """
    document.validate()
    w, h = _quantized_dims(width_mm, height_mm)
    span = _quantized_v_span(v_span_mm, h)
    key = ('fitted', _canonical(document), w, h, float(pad_mm), span)
    hit = _render_cache.get(key)
    if hit is not None:
        _render_cache.move_to_end(key)
        return hit

    import matplotlib
    with matplotlib.rc_context(_deterministic_rc(document)):
        fig = None
        try:
            fig, ax = _build_figure(document, 1.0, w, h)
            _fit_axes(fig, ax, float(pad_mm) / 25.4 * fig.dpi,
                      _fixed_y_px(fig, span) if span is not None else None)
            pos = ax.get_position()
            buf = io.BytesIO()
            fig.savefig(buf, format='svg',
                        metadata={'Date': None,
                                  'Creator': 'ILM Plot Editor'})
        finally:
            if fig is not None:
                fig.clear()

    svg = embed_metadata(
        _prepare_svg(buf.getvalue(), document.font_family), document)
    if len(svg) > MAX_FILE_BYTES:
        raise PlotDocumentError(
            f"rendered SVG exceeds {MAX_FILE_BYTES // (1024 * 1024)} MiB — "
            f"reduce the number of data points")
    render = PlotRender(
        svg=svg, plot_area=(pos.x0, 1.0 - pos.y1, pos.x1, 1.0 - pos.y0))
    _render_cache[key] = render
    if len(_render_cache) > _RENDER_CACHE_MAX:
        _render_cache.popitem(last=False)
    return render


def save_document(document: PlotDocument, path: str) -> None:
    """Atomically write the self-contained ``*.ilmplot.svg`` for *document*.

    Stdlib-only (temp sibling + fsync + ``os.replace``) so the core package
    does not depend on the ILM figpack module. The destination is never
    touched when rendering fails.
    """
    data = render_document(document).svg
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent,
                               prefix='.' + os.path.basename(path),
                               suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as fh:
            fh.write(data)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# ── file-backed document recognition (bounded cache) ─────────────────────

_file_doc_cache: OrderedDict = OrderedDict()
_FILE_DOC_CACHE_MAX = 64


def load_rendered_document(path: str) -> PlotDocument:
    """Load a document from *path*, cached on (path, size, mtime_ns).

    Returns a clone — the cached instance is private so callers cannot
    mutate shared state.
    """
    from .document import load_document
    st = os.stat(path)
    key = (os.path.abspath(path), st.st_size, st.st_mtime_ns)
    hit = _file_doc_cache.get(key)
    if hit is not None:
        _file_doc_cache.move_to_end(key)
        return hit.clone()
    doc = load_document(path)
    _file_doc_cache[key] = doc
    if len(_file_doc_cache) > _FILE_DOC_CACHE_MAX:
        _file_doc_cache.popitem(last=False)
    return doc.clone()
