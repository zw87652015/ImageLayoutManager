"""Import a Matplotlib ``Figure`` into a :class:`PlotDocument`.

This is a *supported-data/style* import, not a pixel-identical
reconstruction: one standard rectilinear axes with linear scales and
``Line2D`` series are captured exactly (data, colors incl. alpha, styles,
labels, limits), while margins, tick formatting and legend chrome are
normalized to the editor's own layout. Anything else — scatter/errorbar
artists, images, annotations, extra axes, categorical/date/unit data,
custom transforms/dashes, custom legend arrangement, masked or
non-1-D data — raises :class:`UnsupportedFigureError` *before* anything is
written. For those figures, export a plain SVG for display instead.
"""

from __future__ import annotations

from .document import (
    PlotDocument, LineSeries, PlotDocumentError,
    LINESTYLES, MARKERS, LEGEND_LOCATIONS,
)


class UnsupportedFigureError(PlotDocumentError):
    """Raised when a figure uses features the editor cannot represent."""


_LEGEND_LOC_CODES = {
    0: 'best', 1: 'upper right', 2: 'upper left', 3: 'lower left',
    4: 'lower right', 5: 'right', 6: 'center left', 7: 'center right',
    8: 'lower center', 9: 'upper center', 10: 'center',
}

_MARKER_MAP = {None: '', 'None': '', '': '',
               'o': 'o', 's': 's', '^': '^', 'v': 'v',
               'D': 'D', '+': '+', 'x': 'x', '.': '.'}


def _reject(reason: str):
    raise UnsupportedFigureError(reason)


def _resolve_size_points(size) -> float:
    """Resolve a matplotlib font size (pt or named) to points."""
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        return float(size)
    import matplotlib
    import matplotlib.font_manager
    scalings = matplotlib.font_manager.font_scalings
    try:
        return float(matplotlib.rcParams['font.size']) * float(scalings[size])
    except Exception:
        return float(matplotlib.rcParams['font.size'])


def _check_finite_pairs(x, y, ctx: str):
    import numpy as np
    # Masked arrays must be rejected *before* np.asarray() — conversion
    # silently drops the mask and would import hidden values as real data.
    if np.ma.isMaskedArray(x) or np.ma.isMaskedArray(y):
        _reject(f"{ctx}: masked data is not supported")
    xa = np.asarray(x)
    ya = np.asarray(y)
    if xa.ndim != 1 or ya.ndim != 1:
        _reject(f"{ctx}: only 1-D x/y data is supported")
    if xa.dtype.kind not in 'iuf' or ya.dtype.kind not in 'iuf':
        _reject(f"{ctx}: only numeric x/y data is supported "
                f"(got dtypes {xa.dtype}, {ya.dtype})")
    xa = np.asarray(xa, dtype=float)
    ya = np.asarray(ya, dtype=float)
    if xa.shape != ya.shape or xa.size == 0:
        _reject(f"{ctx}: x and y must be non-empty arrays of equal length")
    if not (np.isfinite(xa).all() and np.isfinite(ya).all()):
        _reject(f"{ctx}: x and y must contain only finite values")
    return xa.tolist(), ya.tolist()


def _series_color(line) -> str:
    """#rrggbb, or #rrggbbaa when the line has real alpha."""
    from matplotlib.colors import to_rgba
    try:
        r, g, b, a = to_rgba(line.get_color(), alpha=line.get_alpha())
    except Exception:
        _reject(f"unsupported color {line.get_color()!r}")
    hexv = '#{:02x}{:02x}{:02x}'.format(
        round(r * 255), round(g * 255), round(b * 255))
    if a < 1.0:
        hexv += f'{round(a * 255):02x}'
    return hexv


def document_from_figure(figure) -> PlotDocument:
    """Convert *figure* into a :class:`PlotDocument` or raise."""
    axes = list(figure.get_axes())
    if len(axes) != 1:
        _reject(f"expected exactly one axes, found {len(axes)} "
                f"(subplots and inset axes are not supported)")
    ax = axes[0]
    import matplotlib.axes
    if type(ax) is not matplotlib.axes.Axes:
        _reject(f"only standard rectilinear axes are supported "
                f"(got {type(ax).__name__!r})")
    if ax.get_xscale() != 'linear' or ax.get_yscale() != 'linear':
        _reject(f"only linear axes are supported "
                f"(got x={ax.get_xscale()!r}, y={ax.get_yscale()!r})")
    if ax.images:
        _reject("axes contains images (imshow/pcolormesh) — not supported")
    if ax.collections:
        _reject("axes contains collections (scatter/errorbar/fill) — "
                "not supported")
    if ax.patches:
        _reject("axes contains patches (bars/shapes) — not supported")
    if ax.containers:
        _reject("axes contains containers (bar/errorbar) — not supported")
    if ax.artists:
        _reject("axes contains free artists — not supported")
    if list(getattr(ax, 'child_axes', []) or []):
        _reject("axes contains child/inset axes — not supported")
    if ax.texts:
        _reject("axes contains text annotations — not supported")
    if list(getattr(ax, 'tables', [])):
        _reject("axes contains tables — not supported")
    if ax.get_title(loc='left') or ax.get_title(loc='right'):
        _reject("left/right axes titles are not supported "
                "(use the centered title)")
    for name in ('texts', 'artists', 'images', 'lines', 'patches'):
        if list(getattr(figure, name, []) or []):
            _reject(f"figure-level {name} (figtext/suptitle/figimage) are "
                    f"not supported")
    if getattr(figure, 'legends', None):
        _reject("figure-level legends are not supported")
    if getattr(ax, 'xaxis', None) is not None and (
            ax.xaxis.get_converter() is not None
            or ax.yaxis.get_converter() is not None):
        _reject("categorical/date/unit-aware axes are not supported")

    lines = list(ax.get_lines())
    if not lines:
        _reject("axes has no line series to capture")
    eligible = [l for l in lines
                if l.get_label() and not l.get_label().startswith('_')]

    doc = PlotDocument()
    doc.series = []
    doc.width_mm = figure.get_figwidth() * 25.4
    doc.height_mm = figure.get_figheight() * 25.4
    l, b, w, h = ax.get_position().bounds
    doc.axes_rect = [float(l), float(b), float(w), float(h)]
    doc.title = ax.get_title() or ''
    doc.xlabel = ax.get_xlabel() or ''
    doc.ylabel = ax.get_ylabel() or ''
    doc.xlim = [float(v) for v in ax.get_xlim()]
    doc.ylim = [float(v) for v in ax.get_ylim()]
    doc.font_size_pt = _resolve_size_points(
        ax.xaxis.get_label().get_size())
    doc.title_size_pt = _resolve_size_points(ax.title.get_size())
    import matplotlib
    family = matplotlib.rcParams.get('font.sans-serif') or ['DejaVu Sans']
    doc.font_family = str(family[0])

    leg = ax.get_legend()
    doc.legend = leg is not None
    if leg is not None:
        _check_legend(leg, ax, eligible)
        doc.legend_location = _LEGEND_LOC_CODES[leg._loc]
    doc.grid = any(gl.get_visible() for gl in
                   list(ax.get_xgridlines()) + list(ax.get_ygridlines()))

    for i, line in enumerate(lines):
        ctx = f"series[{i}]"
        if not line.get_visible():
            _reject(f"{ctx}: hidden lines cannot be represented")
        if line.get_transform() is not ax.transData:
            _reject(f"{ctx}: custom data transforms are not supported")
        if line.get_drawstyle() != 'default':
            _reject(f"{ctx}: drawstyle {line.get_drawstyle()!r} is not "
                    f"supported")
        mevery = line.get_markevery()
        if mevery not in (None, 1):
            _reject(f"{ctx}: markevery is not supported")
        if getattr(line, 'get_path_effects', lambda: [])():
            _reject(f"{ctx}: path effects are not supported")
        ls = line.get_linestyle()
        if ls in ('None', ''):
            ls = ''
        elif isinstance(ls, tuple) or ls not in LINESTYLES:
            _reject(f"{ctx}: custom dash pattern {ls!r} is not supported")
        elif ls:
            # ``set_dashes`` keeps reporting the named style while swapping
            # in a custom pattern — compare against the canonical pattern.
            from matplotlib.lines import Line2D
            default = Line2D([0], [0], linestyle=ls)._unscaled_dash_pattern
            if tuple(line._unscaled_dash_pattern) != tuple(default):
                _reject(f"{ctx}: custom dash pattern is not supported")
        mk = _MARKER_MAP.get(line.get_marker())
        if mk is None:
            _reject(f"{ctx}: marker {line.get_marker()!r} is not supported")
        if mk:
            _check_marker_colors(line, ctx)
        x, y = _check_finite_pairs(
            line.get_xdata(orig=True), line.get_ydata(orig=True), ctx)
        label = line.get_label() or ''
        if label.startswith('_'):
            label = ''
        s = LineSeries(
            label=label, x=x, y=y,
            linewidth_pt=float(line.get_linewidth()),
            linestyle=ls, marker=mk,
            markersize_pt=float(line.get_markersize()),
        )
        s.color = _series_color(line)
        doc.series.append(s)

    return doc.validate()


def _check_marker_colors(line, ctx: str):
    """Auto/line-matching marker colors normalize; hollow/custom reject."""
    from matplotlib.colors import to_rgba
    if line.get_fillstyle() != 'full':
        _reject(f"{ctx}: marker fillstyle {line.get_fillstyle()!r} is "
                f"not supported (only fully filled markers)")
    line_rgba = to_rgba(line.get_color())
    for attr in ('get_markeredgecolor', 'get_markerfacecolor'):
        value = getattr(line, attr)()
        if value == 'auto':
            continue
        if value == 'none':
            # 'none' draws a hollow marker — only harmless when the line
            # itself is fully transparent (nothing would render anyway).
            if line_rgba[3] == 0:
                continue
            _reject(f"{ctx}: hollow marker {attr[4:]}='none' is not "
                    f"supported")
        try:
            if to_rgba(value) == line_rgba:
                continue
        except Exception:
            pass
        _reject(f"{ctx}: custom {attr[4:]} {value!r} is not supported")


def _check_legend(leg, ax, eligible):
    """Only standard legends over the labeled lines are representable."""
    if leg._loc not in _LEGEND_LOC_CODES:
        _reject(f"legend location {leg._loc!r} is not supported "
                f"(custom anchored/tuple locations cannot be represented)")
    if getattr(leg, '_bbox_to_anchor', None) is not None:
        _reject("legend bbox_to_anchor is not supported")
    texts = [t.get_text() for t in leg.get_texts()]
    expected = [l.get_label() for l in eligible]
    if texts != expected:
        _reject("legend labels do not match the labeled lines "
                "(custom handles/order are not supported)")
    handles = list(getattr(leg, 'legend_handles', [])
                   or getattr(leg, 'legendHandles', []))
    if not all(h.get_label() in expected for h in handles):
        _reject("custom legend handles are not supported")


def export_figure(figure, path: str) -> PlotDocument:
    """Convert *figure* and write it as a self-contained ``*.ilmplot.svg``.

    Raises :class:`UnsupportedFigureError` before anything is written when
    the figure uses unsupported features — the existing file at *path* is
    never touched on failure.
    """
    from .render import save_document
    doc = document_from_figure(figure)
    save_document(doc, path)
    return doc
