"""Bridge a Matplotlib ``Figure`` into a :class:`PlotDocument`.

This is a *supported-data/style* import, not a pixel-identical
reconstruction: one rectilinear ``matplotlib.axes.Axes`` whose lines,
uniform scatter series, error bars, grouped/stacked bars, text notes,
ticks, spines, grid and legend map onto the document model is captured
exactly; harmless normalisations are reported in ``notes``; features the
document cannot express are collected in ``reasons`` and produce either
no document (:func:`convert`), a :class:`FallbackWarning` plain-SVG file
(:func:`savefig`), or :class:`UnsupportedFigureError` (strict mode and
the legacy :func:`document_from_figure`/:func:`export_figure` API).

Nothing about the caller's figure, ``rcParams`` or canvas is mutated.
"""

from __future__ import annotations

import math
import os
import tempfile
import warnings
from dataclasses import dataclass, field

from .document import (
    MARKERS, MAX_ANNOTATIONS, MAX_SERIES, MAX_TOTAL_POINTS, Annotation,
    AxisStyle, Band, FrameStyle, GridStyle, LegendStyle, LineSeries,
    MAX_SPANS, PlotDocument, PlotDocumentError, Span, StackCategory,
    StackOptions, TextStyle, TitleStyle, LINESTYLES,
)


class UnsupportedFigureError(PlotDocumentError):
    """Raised when a figure uses features the editor cannot represent."""

    def __init__(self, message, reasons=()):
        super().__init__(message)
        self.reasons = list(reasons)


class FallbackWarning(UserWarning):
    """Emitted when savefig writes a plain SVG instead of a native file."""


@dataclass
class ConversionResult:
    document: 'PlotDocument | None' = None
    reasons: list = field(default_factory=list)
    notes: list = field(default_factory=list)


@dataclass
class SaveResult:
    path: str = ''
    native: bool = False
    reasons: list = field(default_factory=list)
    notes: list = field(default_factory=list)


_LEGEND_LOC_CODES = {
    0: 'best', 1: 'upper right', 2: 'upper left', 3: 'lower left',
    4: 'lower right', 5: 'right', 6: 'center left', 7: 'center right',
    8: 'lower center', 9: 'upper center', 10: 'center',
}

_MARKER_MAP = {None: '', 'None': '', '': '',
               'o': 'o', 's': 's', '^': '^', 'v': 'v',
               'D': 'D', '+': '+', 'x': 'x', '.': '.'}

_REL_TOL = 1e-9


def _resolve_size_points(size) -> float:
    """Resolve a matplotlib font size (pt or named) to points."""
    if isinstance(size, (int, float)) and not isinstance(size, bool):
        return float(size)
    import matplotlib
    import matplotlib.font_manager
    scalings = matplotlib.font_manager.font_scalings
    try:
        return float(matplotlib.rcParams['font.size']) \
            * float(scalings[size])
    except Exception:
        return float(matplotlib.rcParams['font.size'])


def _axis_converter(axis):
    getter = getattr(axis, 'get_converter', None)
    if getter is not None:
        return getter()
    return getattr(axis, 'converter', None)


def _to_hex(value, ctx=None):
    """'#rrggbb', or '#rrggbbaa' when the colour has real alpha."""
    from matplotlib.colors import to_rgba
    try:
        r, g, b, a = to_rgba(value)
    except Exception:
        if ctx is not None:
            raise _BridgeError(f"{ctx}: unsupported colour {value!r}")
        raise
    ch = lambda v: int(v * 255 + 0.5)
    hexv = '#{:02x}{:02x}{:02x}'.format(ch(r), ch(g), ch(b))
    if a < 1.0:
        hexv += f'{ch(a):02x}'
    return hexv


class _BridgeError(Exception):
    pass


def _finite_1d(v, name):
    """Return a list of finite floats or raise _BridgeError."""
    import numpy as np
    if np.ma.isMaskedArray(v):
        raise _BridgeError("masked data is not supported")
    a = np.asarray(v)
    if a.ndim != 1:
        raise _BridgeError("only 1-D x/y data is supported")
    if a.dtype.kind not in 'iuf':
        try:
            a = a.astype(float)
        except (ValueError, TypeError):
            raise _BridgeError(
                f"only numeric x/y data is supported "
                f"(got dtype {a.dtype})")
        if a.dtype.kind not in 'iuf':
            raise _BridgeError(
                f"only numeric x/y data is supported "
                f"(got dtype {a.dtype})")
    a = np.asarray(a, dtype=float)
    if a.size == 0 or not np.isfinite(a).all():
        raise _BridgeError(f"{name} must contain only finite values")
    return a.tolist()


def _finite_pairs(x, y):
    """Return (xlist, ylist) or raise _BridgeError."""
    xa = _finite_1d(x, 'x')
    ya = _finite_1d(y, 'y')
    if len(xa) != len(ya):
        raise _BridgeError(
            "x and y must be non-empty arrays of equal length")
    return xa, ya


def _font_family_of(text_obj) -> str:
    """The resolved real family name for a text artist."""
    import matplotlib.font_manager
    prop = text_obj.get_fontproperties()
    try:
        path = matplotlib.font_manager.findfont(
            prop, fallback_to_default=False)
    except Exception:
        path = matplotlib.font_manager.findfont(prop)
    return matplotlib.font_manager.get_font(path).family_name


def _is_bold(fp) -> bool:
    w = fp.get_weight()
    if isinstance(w, str):
        return w in ('bold', 'semibold', 'demibold', 'heavy', 'black',
                     'extra bold', 'ultrabold')
    try:
        return float(w) >= 600
    except Exception:
        return False


def _is_italic(fp) -> bool:
    return fp.get_style() in ('italic', 'oblique')


def _text_style(text_obj, base_size, base_family, cls=TextStyle):
    """TextStyle with only the fields differing from the defaults."""
    fp = text_obj.get_fontproperties()
    st = cls()
    size = _resolve_size_points(text_obj.get_size())
    if not math.isclose(size, base_size, rel_tol=1e-6):
        st.size_pt = size
    try:
        color = _to_hex(text_obj.get_color())
        if color != '#000000':
            st.color = color
    except _BridgeError:
        pass
    if _is_bold(fp):
        st.bold = True
    if _is_italic(fp):
        st.italic = True
    fam = _font_family_of(text_obj)
    if fam != base_family:
        st.family = fam
    return st


class _Converter:
    def __init__(self, figure):
        self.fig = figure
        self.reasons = []
        self.notes = []
        self.doc = PlotDocument()
        self.doc.series = []
        self.doc.legend = False
        self.ax = None
        self._base_family = 'DejaVu Sans'
        self._base_size = 10.0
        self._line_yerr = {}          # Line2D -> (kind, yerr tuple)
        self._line_label = {}         # id(Line2D) -> container label
        self._owned_collections = set()  # errorbar LineCollections
        self._bar_yerr = {}              # id(BarContainer) -> (lo, hi)
        self._bar_containers = []
        self._errbar_containers = []

    def reason(self, msg):
        self.reasons.append(msg)

    def note(self, msg):
        self.notes.append(msg)

    def run(self) -> ConversionResult:
        fig = self.fig
        try:
            fig.draw_without_rendering()
        except Exception:
            pass
        self._check_figure_level()
        axes = list(fig.get_axes())
        if len(axes) != 1:
            self.reason(
                f"{len(axes)} axes (subplots/twin/inset/colorbar "
                "not supported)")
            return ConversionResult(None, self.reasons, self.notes)
        ax = axes[0]
        import matplotlib.axes
        if type(ax) is not matplotlib.axes.Axes:
            self.reason(
                f"only standard rectilinear axes are supported "
                f"(got {type(ax).__name__})")
            return ConversionResult(None, self.reasons, self.notes)
        self.ax = ax
        self._check_axes_level()
        self._collect_containers()
        self._map_geometry()
        self._map_fonts()
        self._map_scales_ticks()
        self._map_spines_grid()
        self._map_misc()
        self._map_lines()
        self._map_scatter()
        self._map_bars()
        self._map_patches()
        self._map_texts()
        self._map_legend()
        self._map_limits()
        if self.reasons:
            return ConversionResult(None, self.reasons, self.notes)
        try:
            self.doc.validate()
        except PlotDocumentError as e:
            self.reason(f"the mapped document is invalid: {e}")
            return ConversionResult(None, self.reasons, self.notes)
        return ConversionResult(self.doc, [], self.notes)

    # ── top-level rejection checks ───────────────────────────────────
    def _check_figure_level(self):
        fig = self.fig
        for name in ('texts', 'artists', 'images', 'lines', 'patches'):
            if list(getattr(fig, name, []) or []):
                self.reason(
                    f"figure-level {name} (figtext/suptitle/figimage) "
                    "are not supported")
        if getattr(fig, 'legends', None):
            self.reason("figure-level legends are not supported")

    def _check_axes_level(self):
        ax = self.ax
        if ax.images:
            self.reason("axes images (imshow/pcolormesh) are not "
                        "supported")
        if ax.artists:
            self.reason("free axes artists are not supported")
        if list(getattr(ax, 'child_axes', []) or []):
            self.reason("child/inset axes are not supported")
        if list(getattr(ax, 'tables', []) or []):
            self.reason("axes tables are not supported")
        titles = [(loc, ax.get_title(loc=loc))
                  for loc in ('left', 'center', 'right')]
        used = [(loc, t) for loc, t in titles if t]
        if len(used) > 1:
            self.reason("multiple axes titles are not supported")
        self._title_loc = used[0][0] if used else 'center'
        conv_x = _axis_converter(ax.xaxis)
        conv_y = _axis_converter(ax.yaxis)
        self._categorical = type(conv_x).__name__ == 'StrCategoryConverter'
        if conv_x is not None and not self._categorical:
            self.reason(
                f"x-axis unit/date converter "
                f"{type(conv_x).__name__} is not supported")
        if conv_y is not None:
            self.reason(
                f"y-axis unit/date converter "
                f"{type(conv_y).__name__} is not supported")

    def _collect_containers(self):
        from matplotlib.container import BarContainer, ErrorbarContainer
        for c in self.ax.containers:
            if isinstance(c, ErrorbarContainer):
                self._errbar_containers.append(c)
            elif isinstance(c, BarContainer):
                self._bar_containers.append(c)
            else:
                self.reason(
                    f"{type(c).__name__} containers are not supported")
        bar_owned = {id(getattr(b, 'errorbar', None))
                     for b in self._bar_containers}
        for c in self._errbar_containers:
            if id(c) in bar_owned:
                continue
            self._scan_errorbar(c, owner=None)
        for c in self._bar_containers:
            err = getattr(c, 'errorbar', None)
            if err is not None:
                self._scan_errorbar(err, owner=c)
        capline_ids = set()
        for c in self._errbar_containers + [getattr(b, 'errorbar', None)
                                            for b in self._bar_containers]:
            if c is None:
                continue
            try:
                _line, caplines, barcols = c.lines
            except Exception:
                continue
            capline_ids.update(id(cl) for cl in caplines)
            self._owned_collections.update(id(lc) for lc in barcols)
        self._caplines = capline_ids

    def _scan_errorbar(self, container, owner):
        """Validate an ErrorbarContainer and remember its y-errors."""
        ctx = 'errorbar'
        try:
            data_line, caplines, barcols = container.lines
        except Exception as e:
            self.reason(f"{ctx}: unreadable container ({e})")
            return
        if data_line is None and owner is None:
            self.reason("errorbar without a data line (fmt='none') is "
                        "not supported")
            return
        if caplines:
            self.note("error-bar caps dropped")
        if owner is None:
            base_lw = data_line.get_linewidth()
            base_color = None
            try:
                base_color = _to_hex(data_line.get_color())
            except _BridgeError:
                pass
        else:
            base_lw = None
            base_color = None
        minus = plus = None
        for lc in barcols:
            segs = lc.get_segments()
            vertical = horizontal = False
            for seg in segs:
                a, b = seg[0], seg[1]
                if math.isclose(float(a[0]), float(b[0]),
                                abs_tol=1e-12, rel_tol=0):
                    vertical = True
                elif math.isclose(float(a[1]), float(b[1]),
                                  abs_tol=1e-12, rel_tol=0):
                    horizontal = True
                else:
                    self.reason(f"{ctx}: non-axis-aligned error bars "
                                "are not supported")
                    return
            if horizontal:
                self.reason("xerr (horizontal error bars) is not "
                            "supported")
                return
            if vertical:
                lo = [float(min(a[1], b[1])) for a, b in
                      [(s[0], s[1]) for s in segs]]
                hi = [float(max(a[1], b[1])) for a, b in
                      [(s[0], s[1]) for s in segs]]
                minus, plus = lo, hi
        if minus is not None:
            if owner is None:
                self._line_yerr[id(data_line)] = (minus, plus)
            else:
                self._bar_yerr[id(owner)] = (minus, plus)
        if owner is None and data_line is not None:
            # The label lives on the container — the data Line2D
            # carries '_nolegend_'.
            self._line_label[id(data_line)] = \
                container.get_label() or ''
            lc0 = barcols[0] if barcols else None
            if lc0 is not None:
                try:
                    ecolor = _to_hex(lc0.get_color())
                    if base_color is not None and ecolor != base_color:
                        self.note("error-bar colour differs from the "
                                  "series colour")
                except _BridgeError:
                    pass
                try:
                    elw = float(lc0.get_linewidths()[0])
                    if not math.isclose(elw, float(base_lw),
                                        rel_tol=1e-6):
                        self.note("error-bar line width differs from "
                                  "the series")
                except Exception:
                    pass

    # ── geometry / fonts ─────────────────────────────────────────────
    def _map_geometry(self):
        fig, ax, doc = self.fig, self.ax, self.doc
        doc.width_mm = fig.get_figwidth() * 25.4
        doc.height_mm = fig.get_figheight() * 25.4
        l, b, w, h = ax.get_position().bounds
        rect = [float(l), float(b), float(w), float(h)]
        clamped = [min(max(rect[0], 0.0), 0.99), min(max(rect[1], 0.0),
                                                    0.99),
                   min(max(rect[2], 1e-6), 1.0),
                   min(max(rect[3], 1e-6), 1.0)]
        clamped[2] = min(clamped[2], 1.0 - clamped[0])
        clamped[3] = min(clamped[3], 1.0 - clamped[1])
        if clamped != rect:
            self.note("axes position re-fitted into the figure bounds")
        doc.axes_rect = clamped
        doc.title = next(
            (ax.get_title(loc=loc)
             for loc in ('left', 'center', 'right')
             if ax.get_title(loc=loc)), '')
        doc.xlabel = ax.get_xlabel() or ''
        doc.ylabel = ax.get_ylabel() or ''
        try:
            doc.xlim = [float(v) for v in ax.get_xlim()]
            doc.ylim = [float(v) for v in ax.get_ylim()]
            for lim in (doc.xlim, doc.ylim):
                if not all(map(math.isfinite, lim)) or lim[0] == lim[1]:
                    doc.xlim = doc.ylim = None
                    raise ValueError
        except Exception:
            doc.xlim = doc.ylim = None
            self.reason("axis limits are not finite")

    def _map_fonts(self):
        ax, doc = self.ax, self.doc
        xticks = ax.get_xticklabels()
        sample = xticks[0] if xticks else None
        if sample is not None:
            doc.font_family = _font_family_of(sample)
            doc.font_size_pt = _resolve_size_points(sample.get_size())
        else:
            import matplotlib
            doc.font_family = _font_family_of(ax.xaxis.label)
            doc.font_size_pt = _resolve_size_points(
                matplotlib.rcParams['xtick.labelsize'])
        self._base_family = doc.font_family
        self._base_size = doc.font_size_pt
        title_obj = {'left': ax._left_title, 'center': ax.title,
                     'right': ax._right_title}[self._title_loc]
        doc.title_size_pt = _resolve_size_points(title_obj.get_size())
        ts = _text_style(title_obj, doc.font_size_pt,
                         doc.font_family, cls=TitleStyle)
        # The title's own size maps to title_size_pt, not a style.
        ts.size_pt = None
        ts.align = self._title_loc
        if ts.to_dict():
            doc.style.title = ts
        for name, text_obj in (('xlabel', ax.xaxis.label),
                               ('ylabel', ax.yaxis.label)):
            st = _text_style(text_obj, doc.font_size_pt, doc.font_family)
            if st.to_dict():
                setattr(doc.style, name, st)
        if sample is not None:
            st = _text_style(sample, doc.font_size_pt, doc.font_family)
            st.size_pt = None  # x tick size *is* the document default
            if st.to_dict():
                doc.style.xaxis = doc.style.xaxis or AxisStyle()
                doc.style.xaxis.ticks = st
        yticks = ax.get_yticklabels()
        if yticks:
            st = _text_style(yticks[0], doc.font_size_pt,
                             doc.font_family)
            if st.to_dict():
                doc.style.yaxis = doc.style.yaxis or AxisStyle()
                doc.style.yaxis.ticks = st

    def _map_scales_ticks(self):
        ax, doc = self.ax, self.doc
        for name, axis, scale in (('xaxis', ax.xaxis, ax.get_xscale()),
                                  ('yaxis', ax.yaxis, ax.get_yscale())):
            st = getattr(doc.style, name) or AxisStyle()
            if scale == 'linear':
                pass
            elif scale == 'log':
                base = getattr(axis._scale, 'base', 10)
                if float(base) == 10.0:
                    st.scale = 'log'
                else:
                    self.reason(f"log axis with base {base} is not "
                                "supported (only base 10)")
            else:
                self.reason(f"{scale} axes are not supported "
                            f"({name[0]} axis)")
            params = axis.get_tick_params(which='major')
            direction = params.get('direction')
            if direction is None:
                import matplotlib
                direction = matplotlib.rcParams.get(
                    f"{name[0]}tick.direction", 'out')
            if direction in ('in', 'out', 'inout'):
                st.direction = direction
            length = params.get('length')
            if length is None:
                import matplotlib
                length = matplotlib.rcParams.get(
                    f"{name[0]}tick.major.size", 3.5)
            st.length_pt = float(length)
            minor_loc = axis.get_minor_locator()
            from matplotlib.ticker import NullLocator
            if minor_loc is not None \
                    and not isinstance(minor_loc, NullLocator):
                st.minor = True
            self._map_locator(axis, st, name)
            self._map_formatter(axis, st, name)
            if st.to_dict():
                setattr(doc.style, name, st)
        xticks = ax.get_xticklabels()
        if xticks:
            rot = xticks[0].get_rotation()
            if isinstance(rot, str):
                rot = {'horizontal': 0.0, 'vertical': 90.0}.get(rot, 0.0)
            rot = float(rot)
            if -90.0 <= rot <= 90.0:
                if rot:
                    st = doc.style.xaxis or AxisStyle()
                    st.rotation = rot
                    doc.style.xaxis = st
            else:
                self.reason(f"x tick label rotation {rot} is outside "
                            "-90..90")

    def _map_locator(self, axis, st, name):
        import matplotlib.ticker as mt
        loc = axis.get_major_locator()
        ok = (mt.AutoLocator, mt.MaxNLocator, mt.LinearLocator,
              mt.LogLocator, mt.IndexLocator, mt.NullLocator)
        if isinstance(loc, mt.MultipleLocator):
            if st.scale == 'linear':
                st.step = float(loc._edge.step)
            else:
                self.note("custom tick locator replaced by automatic "
                          f"on {name}")
        elif isinstance(loc, ok):
            pass
        elif type(loc).__name__ == 'StrCategoryLocator':
            pass
        else:
            self.note(f"custom tick locator "
                      f"{type(loc).__name__} replaced by automatic "
                      f"on {name}")

    def _map_formatter(self, axis, st, name):
        import matplotlib.ticker as mt
        fmt = axis.get_major_formatter()
        dec = None
        if isinstance(fmt, mt.FormatStrFormatter):
            import re
            m = re.fullmatch(r'%\.(\d+)f', fmt.fmt)
            if m:
                dec = int(m.group(1))
            else:
                self.note(f"custom tick format {fmt.fmt!r} replaced by "
                          f"automatic on {name}")
        elif isinstance(fmt, mt.StrMethodFormatter):
            import re
            m = re.fullmatch(r'\{x:\.(\d+)f\}', fmt.fmt)
            if m:
                dec = int(m.group(1))
            elif fmt.fmt != '{x}':
                self.note(f"custom tick format {fmt.fmt!r} replaced by "
                          f"automatic on {name}")
        elif isinstance(fmt, (mt.ScalarFormatter, mt.NullFormatter,
                              mt.LogFormatter, mt.LogFormatterSciNotation,
                              mt.LogFormatterExponent,
                              mt.LogFormatterMathtext, mt.FixedFormatter)) \
                or type(fmt).__name__ == 'StrCategoryFormatter':
            pass
        else:
            self.note(f"custom tick formatter "
                      f"{type(fmt).__name__} replaced by automatic "
                      f"on {name}")
        if dec is not None:
            st.decimals = dec

    def _map_misc(self):
        from matplotlib.colors import to_rgba
        for what, get in (('axes', self.ax.get_facecolor),
                          ('figure', self.fig.get_facecolor)):
            try:
                r, g, b, a = to_rgba(get())
            except Exception:
                continue
            if a > 0 and (r, g, b) != (1.0, 1.0, 1.0):
                self.note(f"{what} background colour normalised")
        if self.ax.xaxis.get_ticks_position() != 'bottom':
            self.note("ticks on top/right dropped")
        if self.ax.yaxis.get_ticks_position() != 'left':
            self.note("ticks on top/right dropped")

    def _map_spines_grid(self):
        ax, doc = self.ax, self.doc
        spines = ax.spines
        colors, widths = set(), set()
        for side in ('top', 'right', 'left', 'bottom'):
            visible = bool(spines[side].get_visible())
            if not visible:
                st = doc.style.frame or FrameStyle()
                setattr(st, f'hide_{side}', True)
                doc.style.frame = st
            else:
                try:
                    colors.add(_to_hex(spines[side].get_edgecolor()))
                except _BridgeError:
                    pass
                widths.add(round(float(spines[side].get_linewidth()), 6))
        if len(colors) == 1 and len(widths) == 1:
            st = doc.style.frame or FrameStyle()
            st.color = colors.pop()
            st.linewidth_pt = widths.pop()
            if st.to_dict():
                doc.style.frame = st
        elif colors or widths:
            self.note("spine colours/widths differ — the frame uses "
                      "the editor defaults")
        gx = [t.gridline for t in ax.xaxis.get_major_ticks()
              if t.gridline.get_visible()]
        gy = [t.gridline for t in ax.yaxis.get_major_ticks()
              if t.gridline.get_visible()]
        gminor = [t.gridline for t in
                  ax.xaxis.get_minor_ticks() + ax.yaxis.get_minor_ticks()
                  if t.gridline.get_visible()]
        visible = gx + gy
        if visible:
            doc.grid = True
            gs = GridStyle()
            gs.axis = 'both' if (gx and gy) else ('x' if gx else 'y')
            if gminor:
                gs.which = 'both'
            g = visible[0]
            try:
                gs.color = _to_hex(g.get_color())
            except _BridgeError:
                pass
            ls = g.get_linestyle()
            if ls in _GRID_LINESTYLES_OK:
                gs.linestyle = ls
            lw = float(g.get_linewidth())
            if 0 < lw <= 20:
                gs.linewidth_pt = lw
            alpha = g.get_alpha()
            if alpha is not None:
                gs.alpha = float(alpha)
            doc.style.grid = gs

    # ── series ───────────────────────────────────────────────────────
    def _map_lines(self):
        ax, doc = self.ax, self.doc
        lines = [l for l in ax.get_lines()
                 if id(l) not in self._caplines]
        for i, line in enumerate(lines):
            ctx = f"series[{i}]"
            try:
                self._map_line(line, ctx)
            except _BridgeError as e:
                self.reason(f"{ctx}: {e}")

    def _map_line(self, line, ctx):
        ax = self.ax
        if not line.get_visible():
            raise _BridgeError("hidden lines cannot be represented")
        if line.get_transform() is not ax.transData:
            raise _BridgeError(
                "non-data transforms (axhline/axvline/…) are not "
                "supported")
        if line.get_drawstyle() != 'default':
            raise _BridgeError(
                f"drawstyle {line.get_drawstyle()!r} is not supported")
        if line.get_markevery() not in (None, 1):
            raise _BridgeError("markevery is not supported")
        if getattr(line, 'get_path_effects', lambda: [])():
            raise _BridgeError("path effects are not supported")
        ls = line.get_linestyle()
        if ls in ('None', ''):
            ls = ''
        elif isinstance(ls, tuple) or ls not in LINESTYLES:
            raise _BridgeError(
                f"custom dash pattern {ls!r} is not supported")
        elif ls:
            from matplotlib.lines import Line2D
            default = Line2D([0], [0], linestyle=ls)._unscaled_dash_pattern
            if tuple(line._unscaled_dash_pattern) != tuple(default):
                raise _BridgeError("custom dash pattern is not supported")
        mk = _MARKER_MAP.get(line.get_marker())
        if mk is None:
            raise _BridgeError(
                f"marker {line.get_marker()!r} is not supported")
        if mk:
            self._check_marker_colors(line, ctx)
        try:
            x, y = _finite_pairs(
                line.get_xdata(orig=True), line.get_ydata(orig=True))
        except _BridgeError:
            if not self._categorical:
                raise
            y = _finite_1d(line.get_ydata(orig=True), 'y')
            x = self._category_positions(line.get_xdata(orig=True))
            if len(x) != len(y):
                raise _BridgeError(
                    "x and y must be non-empty arrays of equal length")
        label = line.get_label() or ''
        if not label or label.startswith('_'):
            # e.g. errorbar data lines: the container owns the label.
            label = self._line_label.get(id(line), '') or ''
        if label.startswith('_'):
            label = ''
        s = LineSeries(
            label=label, x=x, y=y,
            linewidth_pt=float(line.get_linewidth()),
            linestyle=ls, marker=mk,
            markersize_pt=float(line.get_markersize()),
        )
        s.color = _to_hex(line.get_color(), ctx)
        bounds = self._line_yerr.get(id(line))
        if bounds is not None:
            lo, hi = bounds
            if len(lo) != len(y):
                raise _BridgeError("error-bar count does not match the "
                                   "data points")
            s.yerr, s.yerr_minus, s.yerr_plus = _yerr_fields(y, lo, hi)
        self.doc.series.append(s)
        if self._categorical and self.doc.kind in ('line', 'ridgeline'):
            labels = self._category_labels()
            if labels is not None and self.doc.x_tick_labels is None:
                mapping = self._category_mapping()
                self.doc.x_tick_labels = [
                    [float(pos), str(lbl)] for lbl, pos in
                    sorted(mapping.items(), key=lambda kv: kv[1])]

    def _category_mapping(self):
        units = getattr(self.ax.xaxis, 'units', None)
        mapping = getattr(units, '_mapping', None)
        if not mapping:
            raise _BridgeError("categorical x positions are "
                               "unreadable")
        return mapping

    def _category_positions(self, values):
        mapping = self._category_mapping()
        out = []
        for v in list(values):
            key = str(v)
            hit = None
            for k, pos in mapping.items():
                if str(k) == key:
                    hit = pos
                    break
            if hit is None:
                raise _BridgeError(
                    f"unmapped category {key!r} on the x axis")
            out.append(float(hit))
        return out

    def _check_marker_colors(self, line, ctx):
        from matplotlib.colors import to_rgba
        if line.get_fillstyle() != 'full':
            raise _BridgeError(
                f"marker fillstyle {line.get_fillstyle()!r} is not "
                "supported (only fully filled markers)")
        line_rgba = to_rgba(line.get_color())
        for attr in ('get_markeredgecolor', 'get_markerfacecolor'):
            value = getattr(line, attr)()
            if value == 'auto':
                continue
            if value == 'none':
                if line_rgba[3] == 0:
                    continue
                raise _BridgeError(
                    f"hollow marker {attr[4:]}='none' is not supported")
            try:
                if to_rgba(value) == line_rgba:
                    continue
            except Exception:
                pass
            raise _BridgeError(
                f"custom {attr[4:]} {value!r} is not supported")

    def _map_scatter(self):
        from matplotlib.collections import PathCollection, PolyCollection
        owned = self._owned_collections
        for coll in self.ax.collections:
            if id(coll) in owned:
                continue
            if isinstance(coll, PathCollection):
                try:
                    self._map_one_scatter(coll)
                except _BridgeError as e:
                    self.reason(f"scatter: {e}")
                continue
            # fill_between/stackplot produce a FillBetweenPolyCollection
            # (mpl >= 3.10) or a plain PolyCollection (older mpl). Both
            # hold one closed polygon per contiguous band segment.
            if isinstance(coll, PolyCollection):
                try:
                    self._map_one_band(coll)
                except _BridgeError as e:
                    self.reason(f"fill_between: {e}")
                continue
            self.reason(
                f"axes collections ({type(coll).__name__} — "
                "fill_between/contour/…) are not supported")

    def _map_one_scatter(self, coll):
        import numpy as np
        from matplotlib.markers import MarkerStyle
        if not coll.get_visible():
            raise _BridgeError("hidden collections cannot be represented")
        try:
            probe = np.asarray([[0.1234, 0.5678]])
            off_t = coll.get_offset_transform().transform(probe)
            data_t = self.ax.transData.transform(probe)
            if not np.allclose(off_t, data_t):
                raise _BridgeError(
                    "non-data transforms are not supported")
        except _BridgeError:
            raise
        except Exception:
            pass
        if coll.get_array() is not None:
            raise _BridgeError("colormapped c= scatter values are not "
                               "supported (use a uniform colour)")
        offsets = np.asarray(coll.get_offsets(), dtype=float)
        if offsets.ndim != 2 or offsets.shape[1] != 2 \
                or offsets.shape[0] == 0:
            raise _BridgeError("only 1-D scatter offsets are supported")
        x, y = _finite_pairs(offsets[:, 0], offsets[:, 1])
        sizes = np.asarray(coll.get_sizes(), dtype=float)
        if sizes.size != 1 and not np.all(sizes == sizes[0]):
            raise _BridgeError("varying s= scatter sizes are not "
                               "supported")
        s_pt2 = float(sizes[0]) if sizes.size else 36.0
        faces = coll.get_facecolors()
        if len(faces) != 1:
            raise _BridgeError("multiple scatter colours are not "
                               "supported")
        edges = coll.get_edgecolors()
        try:
            if len(edges) and any(tuple(e) != (0., 0., 0., 0.)
                                  and _to_hex(e) != _to_hex(faces[0])
                                  for e in edges):
                self.note("scatter edge colours dropped")
        except _BridgeError:
            pass
        path = coll.get_paths()[0]
        marker = None
        for m in MARKERS:
            if not m:
                continue
            q = MarkerStyle(m).get_path().transformed(
                MarkerStyle(m).get_transform())
            if q.vertices.shape == path.vertices.shape \
                    and np.array_equal(path.vertices, q.vertices):
                marker = m
                break
        if marker is None:
            raise _BridgeError("scatter marker is not one of "
                               f"{tuple(m for m in MARKERS if m)}")
        label = coll.get_label() or ''
        if label.startswith('_'):
            label = ''
        s = LineSeries(
            label=label, x=x, y=y, linestyle='', marker=marker,
            markersize_pt=math.sqrt(s_pt2),
        )
        s.color = _to_hex(faces[0])
        self.doc.series.append(s)

    # ── bands (fill_between / stackplot) ─────────────────────────────
    def _map_one_band(self, coll):
        import numpy as np
        if not coll.get_visible():
            raise _BridgeError(
                "hidden collections cannot be represented")
        if getattr(coll, 't_direction', 'x') == 'y':
            raise _BridgeError("fill_betweenx is not supported")
        try:
            probe = np.asarray([[0.1234, 0.5678]])
            fill_t = coll.get_transform().transform(probe)
            data_t = self.ax.transData.transform(probe)
            if not np.allclose(fill_t, data_t):
                raise _BridgeError(
                    "non-data transforms are not supported")
        except _BridgeError:
            raise
        except Exception:
            pass
        if getattr(coll, 'get_hatch', lambda: None)() is not None:
            raise _BridgeError("hatched bands are not supported")
        faces = coll.get_facecolors()
        if len(faces) != 1:
            raise _BridgeError("multiple band colours are not "
                               "supported")
        color = _to_hex(faces[0])
        edges = coll.get_edgecolors()
        try:
            lws = [float(w) for w in coll.get_linewidths()]
            if len(edges) and any(w > 0 for w in lws) \
                    and any(_to_hex(e) != color for e in edges):
                self.note("band outlines dropped")
        except _BridgeError:
            pass
        line_z = [l.get_zorder() for l in self.ax.get_lines()]
        if line_z and coll.get_zorder() > max(line_z):
            self.note("bands drawn under lines")
        label = coll.get_label() or ''
        if label.startswith('_'):
            label = ''
        for path in coll.get_paths():
            x, y1, y2 = self._fill_path(path)
            band = Band(label=label, x=x, y1=y1, y2=y2, color=color)
            label = ''   # only the first split segment keeps the label
            self.doc.bands.append(band)

    def _fill_path(self, path):
        """Decode a fill_between polygon into (x, y1, y2) or raise.

        Layout (mpl 3.10): after dropping the trailing CLOSEPOLY
        vertex the 2n+2 vertices are ``(x0,y2_0)``, the n forward
        ``(x,y1)`` points, ``(xn,y2_n)``, then the n reversed ``(x,y2)``
        points.
        """
        from matplotlib.path import Path as _MplPath
        verts = [list(map(float, v)) for v in path.vertices]
        codes = list(path.codes) if path.codes is not None else []
        if codes and codes[-1] == _MplPath.CLOSEPOLY:
            verts = verts[:-1]
        m = len(verts)
        if m < 6 or (m - 2) % 2:
            raise _BridgeError("unrecognised fill polygon")
        n = (m - 2) // 2
        fwd = verts[1:n + 1]
        rev = verts[n + 2:2 * n + 2]
        flat = [v for pt in verts for v in pt]
        if not all(map(math.isfinite, flat)):
            raise _BridgeError("fill polygon has non-finite vertices")
        x = [v[0] for v in fwd]
        y1 = [v[1] for v in fwd]
        y2 = [v[1] for v in rev][::-1]
        x_rev = [v[0] for v in rev][::-1]
        same = lambda a, b: _close(a, b)
        if not (same(verts[0][0], x[0]) and same(verts[0][1], y2[0])
                and same(verts[n + 1][0], x[-1])
                and same(verts[n + 1][1], y2[-1])):
            raise _BridgeError("unrecognised fill polygon")
        if not all(same(a, b) for a, b in zip(x, x_rev)):
            raise _BridgeError("unrecognised fill polygon")
        return x, y1, y2

    # ── bars ─────────────────────────────────────────────────────────
    def _map_bars(self):
        containers = self._bar_containers
        if not containers:
            return
        doc = self.doc
        if doc.series or doc.bands:
            self.reason("bars cannot be mixed with line/scatter "
                        "series or bands")
            return
        doc.kind = 'stacked_column'
        rects = []
        for k, c in enumerate(containers):
            ctx = f"bars[{k}]"
            if getattr(c, 'orientation', 'vertical') != 'vertical':
                self.reason(f"{ctx}: horizontal bars (barh) are not "
                            "supported")
                continue
            rs = list(c.patches)
            xs = [float(p.get_x()) for p in rs]
            ws = [float(p.get_width()) for p in rs]
            bs = [float(p.get_y()) for p in rs]
            hs = [float(p.get_height()) for p in rs]
            if not rs:
                self.reason(f"{ctx}: empty bar container")
                continue
            if any(not all(map(math.isfinite, quad))
                   for quad in zip(xs, ws, bs, hs)):
                self.reason(f"{ctx}: non-finite bar geometry")
                continue
            if any(h < 0 for h in hs):
                self.reason(f"{ctx}: negative bar heights are not "
                            "supported")
                continue
            if len(set(round(w, 9) for w in ws)) != 1:
                self.reason(f"{ctx}: varying bar widths within one "
                            "bar() call are not supported")
                continue
            colors = set()
            for p in rs:
                try:
                    colors.add(_to_hex(p.get_facecolor()))
                except _BridgeError:
                    colors.add(str(p.get_facecolor()))
            if len(colors) != 1:
                self.reason(f"{ctx}: per-bar colours are not "
                            "supported")
                continue
            label = c.get_label() or ''
            if label.startswith('_'):
                label = ''
            rects.append(dict(c=c, ctx=ctx, xs=xs, ws=ws, bs=bs, hs=hs,
                              color=colors.pop(), label=label,
                              n=len(rs)))
        if self.reasons or not rects:
            return
        n = rects[0]['n']
        if any(r['n'] != n for r in rects):
            self.reason("bar groups with different bar counts are not "
                        "supported")
            return
        layout = self._bar_layout(rects, n)
        if layout is None:
            return
        grouped, spacing, span, centres = layout
        if n > 1 and not self._categorical \
                and span / spacing >= 0.999:
            self.reason("histogram-style bars (touching bars on a "
                        "numeric axis) are not supported")
            return
        if grouped:
            # Categories draw left→right in list order; flag sub-bars
            # that leave gaps or overlap inside a group.
            rects = sorted(rects, key=lambda r: r['xs'][0])
            edges = [(r['xs'][0], r['xs'][0] + r['ws'][0])
                     for r in rects]
            tiled = all(_close(edges[i][1], edges[i + 1][0])
                        for i in range(len(edges) - 1))
            if not tiled:
                self.note("grouped sub-bars have gaps or overlaps — "
                          "the bar layout is normalised")
        doc.stacked = StackOptions(
            grouped=grouped, percent=False,
            bar_width=span / spacing)
        edges, ewidths = set(), set()
        for r in rects:
            for p in r['c'].patches:
                try:
                    edges.add(_to_hex(p.get_edgecolor()))
                except _BridgeError:
                    edges.add(str(p.get_edgecolor()))
                ewidths.add(round(float(p.get_linewidth()), 6))
        if len(edges) == 1 and len(ewidths) == 1:
            doc.stacked.edge_color = edges.pop()
            doc.stacked.edge_width_pt = ewidths.pop()
        for k, r in enumerate(rects):
            cat = StackCategory(label=r['label'] or f'Category {k + 1}',
                                values=list(r['hs']), color=r['color'])
            yerr = self._bar_yerr.get(id(r['c']))
            if yerr is not None:
                lo, hi = yerr
                tops = [b + h for b, h in zip(r['bs'], r['hs'])]
                cat.yerr, cat.yerr_minus, cat.yerr_plus = \
                    _yerr_fields(tops, lo, hi)
                if not grouped:
                    self.note("error bars on stacked bars are ignored "
                              "by the renderer")
            doc.categories.append(cat)
        doc.x_tick_labels = self._bar_tick_labels(centres)

    def _bar_layout(self, rects, n):
        """Detect single/grouped/stacked bar layout.

        Returns (grouped, spacing, span, centres) or None (reason added).
        """
        k = len(rects)
        if k > 1:
            same_x = all(
                all(_close(a, b) for a, b in zip(r['xs'], rects[0]['xs']))
                for r in rects[1:])
            same_w = all(
                all(_close(a, b) for a, b in zip(r['ws'], rects[0]['ws']))
                for r in rects[1:])
            if same_x and same_w:
                acc = [0.0] * n
                ok = True
                for r in rects:
                    if not all(_close(bv, av) for bv, av
                               in zip(r['bs'], acc)):
                        ok = False
                        break
                    acc = [a + h for a, h in zip(acc, r['hs'])]
                if ok:
                    r0 = rects[0]
                    spacing = _spacing(r0['xs'], n)
                    if spacing is None:
                        self.reason("irregular bar positions are not "
                                    "supported")
                        return None
                    span = r0['ws'][0]
                    centres = [x + span / 2.0 for x in r0['xs']]
                    if not (0.0 < span / spacing <= 1.0):
                        self.reason("bar width exceeds the group "
                                    "spacing")
                        return None
                    return False, spacing, span, centres
                self.reason("bar containers neither stack nor group "
                            "(positions must match for stacking)")
                return None
        # grouped (also the single-container case)
        spacings = []
        for r in rects:
            s = _spacing(r['xs'], n)
            if s is None:
                self.reason(f"{r['ctx']}: irregular bar positions are "
                            "not supported")
                return None
            spacings.append(s)
        if not all(_close(s, spacings[0]) for s in spacings):
            self.reason("bar groups with different spacings are not "
                        "supported")
            return None
        spacing = spacings[0]
        left = min(r['xs'][0] for r in rects)
        right = max(r['xs'][0] + r['ws'][0] for r in rects)
        span = right - left
        if not (0.0 < span / spacing <= 1.0):
            self.reason("grouped bars overlap or leave no valid "
                        "bar_width")
            return None
        centres = [left + span / 2.0 + i * spacing for i in range(n)]
        return True, spacing, span, centres

    def _bar_tick_labels(self, centres):
        ax = self.ax
        if self._categorical:
            labels = self._category_labels()
            if labels is not None and len(labels) == len(centres):
                return [[float(i), labels[i]]
                        for i in range(len(centres))]
            ticks = [(t.get_position()[0], t.get_text())
                     for t in ax.get_xticklabels() if t.get_text()]
            if len(ticks) == len(centres):
                return [[float(i), lbl]
                        for i, (_p, lbl) in enumerate(ticks)]
        fmt = ax.xaxis.get_major_formatter()
        locs = [float(v) for v in ax.xaxis.get_majorticklocs()]
        tick_labels = [t.get_text() for t in ax.get_xticklabels()]
        out = []
        for i, c in enumerate(centres):
            label = None
            for pos, text in zip(locs, tick_labels):
                if _close(pos, c):
                    label = text or ''
                    break
            if label is None:
                try:
                    label = str(fmt(c, i))
                except Exception:
                    label = ''
            if label == '':
                label = f'{c:g}'
            out.append([float(i), label])
        return out

    # ── stray patches ────────────────────────────────────────────────
    def _map_patches(self):
        from matplotlib.artist import Artist
        owned = set()
        for c in self._bar_containers:
            owned.update(id(p) for p in c.patches)
        ax = self.ax
        seen = set()
        for p in ax.patches:
            if id(p) in owned:
                continue
            # axvspan/axhspan are Rectangles whose *artist* transform is
            # the blended x/y-axis transform (Patch.get_transform wraps
            # it in the patch transform, so ask Artist directly).
            artist_t = Artist.get_transform(p)
            axis = ('x' if artist_t == ax.get_xaxis_transform()
                    else 'y' if artist_t == ax.get_yaxis_transform()
                    else None)
            if axis is not None:
                try:
                    self._map_one_span(p, axis)
                    continue
                except _BridgeError as e:
                    self.reason(f"{type(p).__name__}: {e}")
                    continue
            name = type(p).__name__
            if name in seen:
                continue
            seen.add(name)
            self.reason(
                f"axes patches ({name} — axvspan/fill/shapes) are not "
                "supported")
        if self.doc.spans and self._bar_containers:
            self.reason("spans cannot be combined with bars")

    def _map_one_span(self, p, axis):
        """An axvspan/axhspan Rectangle → ``doc.spans`` or _BridgeError."""
        if not p.get_visible():
            raise _BridgeError(
                "hidden patches cannot be represented")
        if len(self.doc.spans) >= MAX_SPANS:
            raise _BridgeError(f"more than {MAX_SPANS} spans")
        verts = p.get_patch_transform().transform(p.get_path().vertices)
        xs = [float(v[0]) for v in verts]
        ys = [float(v[1]) for v in verts]
        lo = min(xs if axis == 'x' else ys)
        hi = max(xs if axis == 'x' else ys)
        cross = ys if axis == 'x' else xs
        # A document Span always covers the full cross axis; anything
        # partial (axvspan ymin/ymax, axhspan xmin/xmax) is a reason.
        if not (math.isfinite(lo) and math.isfinite(hi)) \
                or not lo < hi:
            raise _BridgeError("non-finite or empty span extent")
        if not (_close(min(cross), 0.0) and _close(max(cross), 1.0)):
            raise _BridgeError(
                "partial-height/width spans are not supported")
        color = _to_hex(p.get_facecolor())
        try:
            edge = p.get_edgecolor()
            if float(p.get_linewidth() or 0) > 0 \
                    and _to_hex(edge) != color:
                self.note("span outlines dropped")
        except _BridgeError:
            self.note("span outlines dropped")
        label = p.get_label() or ''
        if label.startswith('_'):
            label = ''
        self.doc.spans.append(
            Span(axis=axis, lo=lo, hi=hi, color=color, label=label))

    def _category_labels(self):
        units = getattr(self.ax.xaxis, 'units', None)
        mapping = getattr(units, '_mapping', None)
        if not mapping:
            return None
        try:
            ordered = sorted(mapping.items(), key=lambda kv: kv[1])
            return [str(k) for k, _v in ordered]
        except Exception:
            return None

    # ── annotations / legend / limits ────────────────────────────────
    def _map_texts(self):
        ax, doc = self.ax, self.doc
        texts = list(ax.texts)
        if len(texts) > MAX_ANNOTATIONS:
            self.reason(f"more than {MAX_ANNOTATIONS} text annotations")
            return
        for i, t in enumerate(texts):
            ctx = f"text[{i}]"
            if getattr(t, 'arrowprops', None):
                self.reason(f"{ctx}: annotate() arrows are not "
                            "supported")
                continue
            rot = t.get_rotation()
            if isinstance(rot, str):
                rot = {'horizontal': 0.0, 'vertical': 90.0}.get(rot, 0.0)
            if float(rot) != 0.0:
                self.reason(f"{ctx}: rotated text is not supported")
                continue
            try:
                bb = t.get_window_extent()
                centre = ax.transAxes.inverted().transform(
                    bb.corners().mean(axis=0))
                fx, fy = float(centre[0]), float(centre[1])
            except Exception as e:
                self.reason(f"{ctx}: cannot measure the text extent "
                            f"({e})")
                continue
            if not (-0.5 <= fx <= 1.5 and -0.5 <= fy <= 1.5):
                self.reason(f"{ctx}: text centre lies outside "
                            "-0.5..1.5 axes fraction")
                continue
            a = Annotation(text=t.get_text() or ' ', x=fx, y=fy,
                           box=t.get_bbox_patch() is not None)
            st = _text_style(t, self._base_size, self._base_family)
            if st.to_dict():
                a.style = st
            doc.annotations.append(a)

    def _map_legend(self):
        ax, doc = self.ax, self.doc
        leg = ax.get_legend()
        if leg is None:
            return
        doc.legend = True
        if leg._loc not in _LEGEND_LOC_CODES:
            self.reason(f"legend location {leg._loc!r} is not "
                        "supported (custom anchored/tuple locations "
                        "cannot be represented)")
        else:
            doc.legend_location = _LEGEND_LOC_CODES[leg._loc]
        if getattr(leg, '_bbox_to_anchor', None) is not None:
            self.reason("legend bbox_to_anchor is not supported")
        handles = list(getattr(leg, 'legend_handles', [])
                       or getattr(leg, 'legendHandles', []))
        expected = [s.label for s in doc.series if s.label] + \
            [c.label for c in doc.categories] + \
            [b.label for b in doc.bands if b.label] + \
            [sp.label for sp in doc.spans if sp.label]
        labelled = [h for h in handles
                    if not str(h.get_label()).startswith('_')]
        if not all(h.get_label() in expected for h in labelled):
            self.reason("custom legend handles are not supported")
        texts = [t.get_text() for t in leg.get_texts()]
        if sorted(texts) != sorted(expected):
            self.reason("legend labels do not match the plotted "
                        "series/categories")
        elif texts != expected:
            self.note("legend order normalised")
        ls = LegendStyle()
        ls.frame = bool(leg.get_frame_on())
        ls.ncols = int(getattr(leg, '_ncols',
                               getattr(leg, '_ncol', 1)) or 1)
        try:
            ls.frame_color = _to_hex(leg.get_frame().get_edgecolor())
        except _BridgeError:
            pass
        if ls.to_dict():
            doc.style.legend = ls

    def _map_limits(self):
        doc = self.doc
        n_series = len(doc.series) + len(doc.categories)
        if n_series > MAX_SERIES:
            self.reason(f"more than {MAX_SERIES} series/categories")
        total = sum(len(s.x) for s in doc.series) + \
            sum(len(c.values) for c in doc.categories) + \
            sum(len(b.x) for b in doc.bands)
        if total > MAX_TOTAL_POINTS:
            self.reason(f"more than {MAX_TOTAL_POINTS} data points")
        if doc.bands and not doc.series:
            self.reason("bands need at least one line or scatter "
                        "series (band-only figures such as a bare "
                        "stackplot are not supported)")
        if not doc.series and not doc.categories and not doc.bands:
            self.reason("the figure has no supported data to capture")


def _close(a, b, tol=1e-9):
    return math.isclose(a, b, rel_tol=0,
                        abs_tol=tol * max(1.0, abs(a), abs(b)))


def _spacing(xs, n):
    """Uniform spacing between consecutive bar positions, or None."""
    if n < 2:
        return 1.0
    diffs = [xs[i + 1] - xs[i] for i in range(n - 1)]
    if any(d <= 0 for d in diffs):
        return None
    if not all(_close(d, diffs[0]) for d in diffs):
        return None
    return diffs[0]


def _yerr_fields(y, lo, hi):
    """Split measured lower/upper bounds into yerr fields."""
    minus = [max(0.0, yv - lv) for yv, lv in zip(y, lo)]
    plus = [max(0.0, hv - yv) for hv, yv in zip(hi, y)]
    symmetric = all(
        math.isclose(m, p, rel_tol=_REL_TOL,
                     abs_tol=_REL_TOL * max(1.0, abs(p)))
        for m, p in zip(minus, plus))
    if symmetric:
        return list(plus), None, None
    return None, minus, plus


def convert(figure) -> ConversionResult:
    """Map *figure* onto a :class:`PlotDocument`.

    Never raises for unsupported features: they are collected in
    ``result.reasons`` (``result.document`` is then ``None``), while
    harmless normalisations land in ``result.notes``.
    """
    return _Converter(figure).run()


def savefig(figure, path, *, strict=False, **savefig_kwargs) -> SaveResult:
    """Write *figure* to *path* as ``*.ilmplot.svg`` when representable.

    When the figure uses unsupported features: ``strict=True`` raises
    :class:`UnsupportedFigureError` without touching *path*; otherwise a
    plain SVG (text kept as text) is written atomically to the same path
    and a :class:`FallbackWarning` listing the reasons is emitted.
    ``savefig_kwargs`` (``bbox_inches``, ``transparent``, …) apply only to
    the fallback path.
    """
    result = convert(figure)
    if not result.reasons:
        from .render import save_document
        save_document(result.document, path)
        return SaveResult(path=str(path), native=True, reasons=[],
                          notes=result.notes)
    if strict:
        raise UnsupportedFigureError(
            '; '.join(result.reasons), reasons=result.reasons)
    warnings.warn(
        FallbackWarning(
            'figure uses features ilmplot cannot represent ('
            + '; '.join(result.reasons)
            + '); wrote a plain SVG instead'),
        stacklevel=2)
    import matplotlib
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent,
                               prefix='.' + os.path.basename(path),
                               suffix='.tmp')
    os.close(fd)
    try:
        with matplotlib.rc_context({'svg.fonttype': 'none'}):
            figure.savefig(tmp, format='svg', **savefig_kwargs)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    return SaveResult(path=str(path), native=False,
                      reasons=list(result.reasons),
                      notes=list(result.notes))


def document_from_figure(figure) -> PlotDocument:
    """Convert *figure* into a :class:`PlotDocument` or raise.

    Legacy strict API: the exception message is the collected reasons.
    """
    result = convert(figure)
    if result.reasons:
        raise UnsupportedFigureError(
            '; '.join(result.reasons), reasons=result.reasons)
    return result.document


def export_figure(figure, path: str) -> PlotDocument:
    """Strictly convert *figure* and write the ``*.ilmplot.svg``.

    Raises :class:`UnsupportedFigureError` before anything is written —
    the existing file at *path* is never touched on failure.
    """
    from .render import save_document
    doc = document_from_figure(figure)
    save_document(doc, path)
    return doc


_GRID_LINESTYLES_OK = set(LINESTYLES) - {''}
