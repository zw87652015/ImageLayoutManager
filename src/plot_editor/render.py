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
            if style and _FONT_FAMILY_STYLE_RE.search(style):
                node.set('style', _FONT_FAMILY_STYLE_RE.sub('', style)
                         .strip('; '))
            if font_family:
                node.set('font-family', font_family)
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


def _build_figure(document: PlotDocument, s: float,
                  width_mm: float, height_mm: float):
    """Build (Figure, Axes) for *document* at typography scale *s*."""
    from matplotlib.figure import Figure
    fig = Figure(figsize=(width_mm / 25.4, height_mm / 25.4))
    ax = fig.add_axes(list(document.axes_rect))
    for s_ in document.series:
        line, = ax.plot(
            s_.x, s_.y,
            color=s_.color,
            linewidth=max(s_.linewidth_pt * s, 1e-3),
            linestyle=s_.linestyle if s_.linestyle else 'None',
            marker=s_.marker or None,
            markersize=max(s_.markersize_pt * s, 0.0),
            markeredgewidth=1.0 * s,
            label=s_.label or '_nolegend_',
        )
        line.set_gid(f'ilmplot-series-{s_.id}')
    if document.xlim is not None:
        ax.set_xlim(document.xlim)
    if document.ylim is not None:
        ax.set_ylim(document.ylim)
    if document.title:
        t = ax.set_title(document.title,
                         fontsize=document.title_size_pt * s,
                         pad=4.0 * s)
        t.set_gid('ilmplot-title')
    if document.xlabel:
        xl = ax.set_xlabel(document.xlabel,
                           fontsize=document.font_size_pt * s)
        xl.set_gid('ilmplot-xlabel')
    if document.ylabel:
        yl = ax.set_ylabel(document.ylabel,
                           fontsize=document.font_size_pt * s)
        yl.set_gid('ilmplot-ylabel')
    ax.tick_params(labelsize=document.font_size_pt * s,
                   length=3.0 * s, width=0.8 * s,
                   pad=3.0 * s)
    for spine in ax.spines.values():
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
        ax.grid(True, linewidth=0.5 * s, alpha=0.4)
    if document.legend:
        handles = [l for l in ax.get_lines()
                   if l.get_label()
                   and not l.get_label().startswith('_')]
        if handles:
            leg = ax.legend(loc=document.legend_location,
                            fontsize=document.font_size_pt * s)
            if leg is not None:
                leg.get_frame().set_linewidth(0.6 * s)
    return fig, ax


FIT_PAD_MM = 0.5
MIN_AXES_FRACTION = 0.2


def _fit_axes(fig, ax, pad_px: float) -> None:
    """Reposition *ax* so nothing outside the axes box is clipped.

    Iterates a margin-feedback loop: each pass shrinks the axes rect by the
    measured overflow of tick labels, axis labels, title, offset text and
    legend plus *pad_px*, until every edge moves under 0.05 px (or 4
    passes).  Typography is never scaled down — when the text does not fit,
    the axes clamps to ``MIN_AXES_FRACTION`` of the figure instead.
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
        y0, y1 = bottom + pad_px, H - top - pad_px
        if x1 - x0 < MIN_AXES_FRACTION * W:
            spare = (1.0 - MIN_AXES_FRACTION) * W
            denom = left + pad_px + right + pad_px
            x0 = spare * ((left + pad_px) / denom) if denom > 0 else spare * 0.5
            x1 = x0 + MIN_AXES_FRACTION * W
        if y1 - y0 < MIN_AXES_FRACTION * H:
            spare = (1.0 - MIN_AXES_FRACTION) * H
            denom = bottom + pad_px + top + pad_px
            y0 = spare * ((bottom + pad_px) / denom) if denom > 0 else spare * 0.5
            y1 = y0 + MIN_AXES_FRACTION * H
        if max(abs(x0 - pos.x0), abs(x1 - pos.x1),
               abs(y0 - pos.y0), abs(y1 - pos.y1)) < 0.05:
            break
        ax.set_position([x0 / W, y0 / H, (x1 - x0) / W, (y1 - y0) / H])


def render_document_fitted(document: PlotDocument, width_mm: float,
                           height_mm: float, *,
                           pad_mm: float = FIT_PAD_MM) -> PlotRender:
    """Render *document* at exactly ``width_mm`` × ``height_mm``.

    Unlike :func:`render_document` the figure is sized to the target box
    (style scale 1.0, so point sizes are true) and the axes rectangle is
    solved by :func:`_fit_axes` so no text is clipped.  The embedded
    metadata carries the *original* document, not the fitted geometry.
    """
    document.validate()
    w, h = float(width_mm), float(height_mm)
    for name, v in (('width_mm', w), ('height_mm', h)):
        if not math.isfinite(v) or v <= 0 or v > MAX_DIMENSION_MM:
            raise PlotDocumentError(
                f"{name}: expected 0 < value <= {MAX_DIMENSION_MM} mm, "
                f"got {v!r}")
    w, h = round(w, 2), round(h, 2)
    key = ('fitted', _canonical(document), w, h, float(pad_mm))
    hit = _render_cache.get(key)
    if hit is not None:
        _render_cache.move_to_end(key)
        return hit

    import matplotlib
    with matplotlib.rc_context(_deterministic_rc(document)):
        fig = None
        try:
            fig, ax = _build_figure(document, 1.0, w, h)
            _fit_axes(fig, ax, float(pad_mm) / 25.4 * fig.dpi)
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
