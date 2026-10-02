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
    l, b, w, h = (float(v) for v in document.axes_rect)
    render = PlotRender(svg=svg, plot_area=(l, 1.0 - (b + h), l + w, 1.0 - b))
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


def _build_figure(document: PlotDocument, s: float,
                  width_mm: float, height_mm: float):
    """Build (Figure, Axes) for *document* at typography scale *s*."""
    from matplotlib.figure import Figure
    from matplotlib.ticker import (AutoMinorLocator, LogLocator,
                                   MultipleLocator, NullFormatter)
    style = document.style
    x_axis = getattr(style, 'xaxis', None) if style is not None else None
    y_axis = getattr(style, 'yaxis', None) if style is not None else None
    categorical_x = bool(document.x_tick_labels)
    fig = Figure(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax = fig.add_axes(list(document.axes_rect))
    lines = []
    for s_ in document.series:
        line, = ax.plot(
            s_.x, s_.y,
            color=s_.color,
            linewidth=max(s_.linewidth_pt * s, 1e-3),
            linestyle=s_.linestyle if s_.linestyle else 'None',
            marker=s_.marker or None,
            markersize=max(s_.markersize_pt * s, 0.0),
            markeredgewidth=1.0 * s,
            label=safe_text(s_.label) or '_nolegend_',
        )
        line.set_gid(f'ilmplot-series-{s_.id}')
        lines.append((line, s_))
    if categorical_x:
        ax.set_xticks([p for p, _l in document.x_tick_labels],
                      [safe_text(l) for _p, l in document.x_tick_labels])
    # Axis scales first so locators/formatters see the right transform.
    if x_axis is not None and x_axis.scale != 'linear' and not categorical_x:
        ax.set_xscale(x_axis.scale)
    if y_axis is not None and y_axis.scale != 'linear':
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
        categorical = categorical_x and axis_obj == 'x'
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
    underlines = []
    t_style = getattr(style, 'title', None) if style is not None else None
    if document.title:
        kw = _text_kwargs(t_style, document.font_family,
                          document.title_size_pt, s)
        loc = t_style.align if t_style is not None else 'center'
        t = ax.set_title(safe_text(document.title), pad=4.0 * s,
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
    if document.ylabel:
        yl = ax.set_ylabel(
            safe_text(document.ylabel),
            **_text_kwargs(yl_style, document.font_family,
                           document.font_size_pt, s))
        yl.set_gid('ilmplot-ylabel')
        if yl_style is not None and yl_style.underline:
            underlines.append(lambda t=yl: [t])
    ax.tick_params(labelsize=document.font_size_pt * s,
                   length=3.0 * s, width=0.8 * s,
                   pad=3.0 * s)
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
    for name, spine in ax.spines.items():
        if frame is not None:
            if name == 'top' and frame.hide_top \
                    or name == 'right' and frame.hide_right:
                spine.set_visible(False)
                continue
            spine.set_color(frame.color)
            spine.set_linewidth(frame.linewidth_pt * s)
        else:
            spine.set_linewidth(0.8 * s)
    ax.xaxis.labelpad = 3.0 * s
    ax.yaxis.labelpad = 3.0 * s
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
            ax.grid(True, linewidth=0.5 * s, alpha=0.4)
        else:
            if grid.which == 'both':
                for axis_name, ast in (('x', x_axis), ('y', y_axis)):
                    if grid.axis in ('both', axis_name) and (
                            ast is None or not ast.minor):
                        axis = ax.xaxis if axis_name == 'x' else ax.yaxis
                        categorical = categorical_x and axis_name == 'x'
                        if categorical:
                            continue
                        if ast is not None and ast.scale == 'log':
                            axis.set_minor_locator(
                                LogLocator(base=10.0, subs='auto'))
                        else:
                            axis.set_minor_locator(AutoMinorLocator())
                        axis.set_minor_formatter(NullFormatter())
            ax.grid(True, which=grid.which, axis=grid.axis,
                    color=grid.color, linestyle=grid.linestyle,
                    linewidth=grid.linewidth_pt * s, alpha=grid.alpha)
    if document.legend:
        handles = [l for l in ax.get_lines()
                   if l.get_label()
                   and not l.get_label().startswith('_')]
        if handles:
            leg_style = getattr(style, 'legend', None) \
                if style is not None else None
            leg_kw = {'loc': document.legend_location,
                      'fontsize': document.font_size_pt * s}
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
            leg = ax.legend(**leg_kw)
            if leg is not None:
                leg.get_frame().set_linewidth(0.6 * s)
                if leg_style is not None and leg_style.text is not None \
                        and leg_style.text.underline:
                    underlines.append(
                        lambda leg=leg: [t for t in leg.get_texts()
                                         if t.get_visible()])
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
                    dpi: int = 300):
    """Export *document* via the native figure to pdf/svg/png/tiff/jpeg.

    Same figure and rc context as ``render_document`` (style scale 1);
    writes atomically.
    """
    document.validate()
    if fmt not in ('pdf', 'svg', 'png', 'tiff', 'jpeg'):
        raise PlotDocumentError(f"unsupported export format {fmt!r}")
    import matplotlib
    with matplotlib.rc_context(_deterministic_rc(document)):
        fig = None
        try:
            fig, _ax = _build_figure(document, 1.0, document.width_mm,
                                     document.height_mm)

            def _write(fh):
                if fmt in ('pdf', 'svg'):
                    fig.savefig(fh, format=fmt, metadata={'Date': None})
                else:
                    fig.savefig(fh, format=fmt, dpi=dpi)

            _atomic_write(path, _write)
        finally:
            if fig is not None:
                fig.clear()


FIT_PAD_MM = 0.5
MIN_AXES_FRACTION = 0.2


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
    for _ in range(4):
        pos = ax.get_window_extent(renderer)
        tight = ax.get_tightbbox(renderer)
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
        if max(abs(x0 - pos.x0), abs(x1 - pos.x1),
               abs(y0 - pos.y0), abs(y1 - pos.y1)) < 0.05:
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
