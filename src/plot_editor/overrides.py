"""Editor-side per-element overrides (pure Python, no Qt).

In-place edits are *overrides*: a set field wins over whatever the
worksheet would derive, ``None`` means "not overridden". They serialize
into the ``ilm-plot-worksheet`` node (v2) — omitting defaults keeps
unstyled files at schema v1.
"""

import copy
import math

from .document import (LEGEND_LOCATIONS, LINESTYLES, MARKERS,
                       MAX_ANNOTATIONS, MAX_BRACKETS, MAX_SERIES,
                       Annotation, Bracket, PlotDocument, PlotStyle,
                       RidgeOptions, StackOptions, ViolinOptions,
                       _check_color, _check_limit, _is_num)


class OverridesError(ValueError):
    """Raised when an overrides payload is malformed."""


def _err(msg):
    return OverridesError(msg)


def _opt_num(data, key, ctx, lo=None, hi=None, lo_exclusive=False):
    v = data.get(key)
    if v is None:
        return None
    if not _is_num(v) or not math.isfinite(v):
        raise _err(f"{ctx}.{key}: expected a finite number, got {v!r}")
    v = float(v)
    if lo is not None and (v <= lo if lo_exclusive else v < lo):
        raise _err(f"{ctx}.{key}: expected > {lo}, got {v}")
    if hi is not None and v > hi:
        raise _err(f"{ctx}.{key}: expected <= {hi}, got {v}")
    return v


def _opt_bool(data, key, ctx):
    v = data.get(key)
    if v is not None and not isinstance(v, bool):
        raise _err(f"{ctx}.{key}: expected true/false, got {v!r}")
    return v


def _opt_str(data, key, ctx):
    v = data.get(key)
    if v is not None and not isinstance(v, str):
        raise _err(f"{ctx}.{key}: expected a string, got {v!r}")
    return v


def _opt_choice(data, key, ctx, choices):
    v = data.get(key)
    if v is not None and v not in choices:
        raise _err(f"{ctx}.{key}: unsupported {v!r}; one of {choices}")
    return v


def _unknown(data, allowed, ctx):
    extra = sorted(set(data) - allowed)
    if extra:
        raise _err(f"{ctx}: unknown field(s) {extra}")


class SeriesOverride:
    """Per-series overrides keyed by Y column index; all None = unset."""

    __slots__ = ('label', 'color', 'linewidth_pt', 'linestyle', 'marker',
                 'markersize_pt')
    _KEYS = __slots__

    def __init__(self, label=None, color=None, linewidth_pt=None,
                 linestyle=None, marker=None, markersize_pt=None):
        self.label = label
        self.color = color
        self.linewidth_pt = linewidth_pt
        self.linestyle = linestyle
        self.marker = marker
        self.markersize_pt = markersize_pt

    def is_empty(self):
        return all(getattr(self, k) is None for k in self._KEYS)

    def to_dict(self):
        d = {}
        for k in self._KEYS:
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        if not isinstance(data, dict):
            raise _err(f"{ctx}: expected an object")
        _unknown(data, set(cls._KEYS), ctx)
        s = cls()
        s.label = _opt_str(data, 'label', ctx)
        if data.get('color') is not None:
            try:
                s.color = _check_color(data['color'], f"{ctx}.color")
            except ValueError as e:
                raise _err(str(e))
        s.linewidth_pt = _opt_num(data, 'linewidth_pt', ctx,
                                  lo=0, hi=200, lo_exclusive=True)
        s.linestyle = _opt_choice(data, 'linestyle', ctx, LINESTYLES)
        s.marker = _opt_choice(data, 'marker', ctx, MARKERS)
        s.markersize_pt = _opt_num(data, 'markersize_pt', ctx,
                                   lo=0, hi=200)
        return s


class PlotOverrides:
    """Document-level overrides plus per-series ones."""

    __slots__ = ('xlabel', 'ylabel', 'legend', 'legend_location', 'grid',
                 'xlim', 'ylim', 'style', 'series', 'palette',
                 'palette_reverse', 'violin', 'ridgeline', 'stacked',
                 'annotations', 'brackets', 'bar_labels')
    _KEYS = ('xlabel', 'ylabel', 'legend', 'legend_location', 'grid',
             'xlim', 'ylim', 'style', 'series', 'palette',
             'palette_reverse', 'violin', 'ridgeline', 'stacked',
             'annotations', 'brackets', 'bar_labels')

    def __init__(self):
        self.xlabel = None
        self.ylabel = None
        self.legend = None
        self.legend_location = None
        self.grid = None
        self.xlim = None
        self.ylim = None
        self.style = PlotStyle()
        self.series = {}
        self.palette = None
        self.palette_reverse = None
        self.violin = None
        self.ridgeline = None
        self.stacked = None
        self.annotations = None
        self.brackets = None
        self.bar_labels = None

    def is_empty(self):
        return (self.xlabel is None and self.ylabel is None
                and self.legend is None and self.legend_location is None
                and self.grid is None and self.xlim is None
                and self.ylim is None and not self.style.to_dict()
                and all(o.is_empty() for o in self.series.values())
                and self.palette is None and self.palette_reverse is None
                and self.violin is None and self.ridgeline is None
                and self.stacked is None and not self.annotations
                and not self.brackets and not self.bar_labels)

    def to_dict(self):
        d = {}
        for k in ('xlabel', 'ylabel', 'legend', 'legend_location',
                  'grid', 'xlim', 'ylim', 'palette', 'palette_reverse'):
            v = getattr(self, k)
            if v is not None:
                d[k] = v
        style = self.style.to_dict() if self.style is not None else {}
        if style:
            d['style'] = style
        series = {str(k): o.to_dict() for k, o in self.series.items()
                  if not o.is_empty()}
        if series:
            d['series'] = series
        for k in ('violin', 'ridgeline', 'stacked'):
            opt = getattr(self, k)
            if opt is not None:
                od = opt.to_dict()
                if od:
                    d[k] = od
        if self.annotations:
            d['annotations'] = [a.to_dict() for a in self.annotations]
        if self.brackets:
            d['brackets'] = [b.to_dict() for b in self.brackets]
        if self.bar_labels:
            d['bar_labels'] = {str(k): v for k, v in
                               self.bar_labels.items()}
        return d

    @classmethod
    def from_dict(cls, data, ctx='overrides'):
        if not isinstance(data, dict):
            raise _err(f"{ctx}: expected an object")
        _unknown(data, set(cls._KEYS), ctx)
        o = cls()
        o.xlabel = _opt_str(data, 'xlabel', ctx)
        o.ylabel = _opt_str(data, 'ylabel', ctx)
        o.legend = _opt_bool(data, 'legend', ctx)
        o.legend_location = _opt_choice(data, 'legend_location', ctx,
                                        LEGEND_LOCATIONS)
        o.grid = _opt_bool(data, 'grid', ctx)
        for name in ('xlim', 'ylim'):
            if data.get(name) is not None:
                try:
                    setattr(o, name,
                            _check_limit(data[name], f"{ctx}.{name}"))
                except ValueError as e:
                    raise _err(str(e))
        if data.get('style') is not None:
            try:
                o.style = PlotStyle.from_dict(data['style'],
                                              f"{ctx}.style")
            except ValueError as e:
                raise _err(str(e))
        series = data.get('series')
        if series is not None:
            if not isinstance(series, dict):
                raise _err(f"{ctx}.series: expected an object")
            if len(series) > MAX_SERIES:
                raise _err(f"{ctx}.series: at most {MAX_SERIES} entries")
            for key, sub in series.items():
                try:
                    col = int(key)
                except (TypeError, ValueError):
                    raise _err(f"{ctx}.series: non-integer key {key!r}")
                if col < 0:
                    raise _err(f"{ctx}.series: negative key {key!r}")
                o.series[col] = SeriesOverride.from_dict(
                    sub, f"{ctx}.series[{key}]")
        pal = data.get('palette')
        if pal is not None:
            from .palettes import valid_theme_ref
            if not valid_theme_ref(pal):
                raise _err(f"{ctx}.palette: unknown theme {pal!r}")
            o.palette = pal
        o.palette_reverse = _opt_bool(data, 'palette_reverse', ctx)
        for name, typ in (('violin', ViolinOptions),
                          ('ridgeline', RidgeOptions),
                          ('stacked', StackOptions)):
            if data.get(name) is not None:
                try:
                    setattr(o, name, typ.from_dict(
                        data[name], f"{ctx}.{name}"))
                except ValueError as e:
                    raise _err(str(e))
        for name, typ, limit in (('annotations', Annotation,
                                  MAX_ANNOTATIONS),
                                 ('brackets', Bracket, MAX_BRACKETS)):
            items = data.get(name)
            if items is None:
                continue
            if not isinstance(items, list) or len(items) > limit:
                raise _err(f"{ctx}.{name}: expected at most {limit} "
                           "entries")
            try:
                setattr(o, name, [typ.from_dict(
                    v, f"{ctx}.{name}[{i}]")
                    for i, v in enumerate(items)])
            except ValueError as e:
                raise _err(str(e))
        bl = data.get('bar_labels')
        if bl is not None:
            if not isinstance(bl, dict):
                raise _err(f"{ctx}.bar_labels: expected an object")
            o.bar_labels = {}
            for key, text in bl.items():
                try:
                    idx = int(key)
                except (TypeError, ValueError):
                    raise _err(f"{ctx}.bar_labels: non-integer key "
                               f"{key!r}")
                if idx < 0 or str(idx) != str(key):
                    raise _err(f"{ctx}.bar_labels: bad index {key!r}")
                if not isinstance(text, str) or len(text) > 200:
                    raise _err(f"{ctx}.bar_labels[{key}]: expected a "
                               "string of at most 200 characters")
                o.bar_labels[idx] = text
        return o


def reset_element(overrides, key, y_column=None):
    """Clear every override belonging to element ``key``."""
    if key == 'title':
        overrides.style.title = None
    elif key == 'xlabel':
        overrides.xlabel = None
        overrides.style.xlabel = None
    elif key == 'ylabel':
        overrides.ylabel = None
        overrides.style.ylabel = None
    elif key == 'xticks':
        overrides.xlim = None
        overrides.style.xaxis = None
        overrides.bar_labels = None
    elif key == 'yticks':
        overrides.ylim = None
        overrides.style.yaxis = None
    elif key == 'legend':
        overrides.legend = None
        overrides.legend_location = None
        overrides.style.legend = None
    elif key == 'frame':
        overrides.grid = None
        overrides.style.frame = None
        overrides.style.grid = None
        overrides.palette = None
        overrides.palette_reverse = None
    elif key.startswith(('series:', 'violin:', 'stack:')):
        if y_column is not None:
            overrides.series.pop(y_column, None)
    elif key.startswith('annotation:'):
        if overrides.annotations:
            overrides.annotations = [
                a for a in overrides.annotations
                if a.id != key[len('annotation:'):]] or None
    elif key.startswith('bracket:'):
        if overrides.brackets:
            overrides.brackets = [
                b for b in overrides.brackets
                if b.id != key[len('bracket:'):]] or None


def parse_axis_limits(lo_text, hi_text):
    """``(limits, error)``: both empty → ``(None, False)`` (auto); both
    finite and different → ``([lo, hi], False)``; otherwise ``(None, True)``
    so the caller can flag the inputs without applying."""
    lo_text = (lo_text or '').strip()
    hi_text = (hi_text or '').strip()
    if not lo_text and not hi_text:
        return None, False
    try:
        lo, hi = float(lo_text), float(hi_text)
    except ValueError:
        return None, True
    if not (math.isfinite(lo) and math.isfinite(hi)) or lo == hi:
        return None, True
    return [lo, hi], False


def remap_series_keys(overrides, event):
    """Shift ``overrides.series`` keys for column insert/remove events."""
    if not event or event[0] not in ('columns_inserted',
                                     'columns_removed'):
        return
    _name, at, count = event[0], event[1], event[2]
    if event[0] == 'columns_inserted':
        overrides.series = {
            (k + count if k >= at else k): o
            for k, o in overrides.series.items()}
    else:
        overrides.series = {
            (k - count if k >= at + count else k): o
            for k, o in overrides.series.items()
            if not (at <= k < at + count)}
    # bar_labels keys are bar (row) indices, not columns — no remap.


def apply_update(overrides, fn, commit):
    """``fn(overrides)`` then ``commit()`` (re-render), with rollback.

    On any exception the pre-edit overrides are restored in place and
    ``commit()`` runs again to repaint the previous state; tracebacks go
    to stderr. Returns True on success — callers must never let the
    exception reach a Qt slot (PyQt6 aborts on those).
    """
    import traceback
    snapshot = copy.deepcopy(overrides)
    try:
        fn(overrides)
        commit()
        return True
    except Exception:
        traceback.print_exc()
        for name in PlotOverrides._KEYS:
            setattr(overrides, name, getattr(snapshot, name))
        try:
            commit()
        except Exception:
            traceback.print_exc()
        return False


def overrides_from_document(doc):
    """Seed overrides from a document with no override metadata (legacy or
    ILM file): style is cloned; document-level fields are set only where
    they differ from a fresh ``PlotDocument``."""
    o = PlotOverrides()
    base = PlotDocument()
    o.style = copy.deepcopy(doc.style) if doc.style is not None \
        else PlotStyle()
    if doc.legend != base.legend:
        o.legend = doc.legend
    if doc.legend_location != base.legend_location:
        o.legend_location = doc.legend_location
    if doc.grid != base.grid:
        o.grid = doc.grid
    if doc.xlim != base.xlim:
        o.xlim = list(doc.xlim)
    if doc.ylim != base.ylim:
        o.ylim = list(doc.ylim)
    # New-kind options and content survive regeneration: seed them as
    # overrides so a loaded file keeps its options, notes and brackets.
    if doc.violin is not None:
        o.violin = copy.deepcopy(doc.violin)
    if doc.ridgeline is not None:
        o.ridgeline = copy.deepcopy(doc.ridgeline)
    if doc.stacked is not None:
        o.stacked = copy.deepcopy(doc.stacked)
    if doc.annotations:
        o.annotations = copy.deepcopy(doc.annotations)
    if doc.brackets:
        o.brackets = copy.deepcopy(doc.brackets)
    return o


def effective_document(base_doc, items, chart_key, title, overrides):
    """Build the validated ``PlotDocument`` shown/saved by the editor.

    ``items`` are Series/Group/Category objects. ``base_doc`` (an
    already-loaded document) wins over regeneration for line kinds when
    its series count matches; new kinds always regenerate from the
    worksheet items. Overrides are applied on top.
    """
    from .export import CHART_KIND, document_from_plot
    from .plot_data import tick_label_map
    kind, percent = CHART_KIND.get(chart_key, ('line', None))
    if kind in ('line', 'ridgeline') and base_doc is not None \
            and len(base_doc.series) == len(items) \
            and base_doc.kind == kind:
        doc = base_doc.clone()
        # The worksheet is the data source of truth; the base only
        # contributes its look (colours, sizes, typography).
        for ds, s in zip(doc.series, items):
            ds.x = list(s.x)
            ds.y = list(s.y)
            ds.yerr = list(s.yerr) if s.yerr is not None else None
            ds.yerr_minus = (list(s.yerr_minus)
                             if s.yerr_minus is not None else None)
            ds.yerr_plus = (list(s.yerr_plus)
                            if s.yerr_plus is not None else None)
        ticks = tick_label_map(items)
        doc.x_tick_labels = [[p, ticks[p]] for p in sorted(ticks)] or None
    else:
        doc = document_from_plot(items, chart_key,
                                 palette=overrides.palette,
                                 palette_reverse=bool(
                                     overrides.palette_reverse))
    doc.title = title
    doc.xlabel = overrides.xlabel if overrides.xlabel is not None \
        else items[0].x_label
    doc.ylabel = overrides.ylabel if overrides.ylabel is not None \
        else doc.ylabel if kind == 'stacked_column' and percent \
        else items[0].y_label
    if overrides.legend is not None:
        doc.legend = overrides.legend
    if overrides.legend_location is not None:
        doc.legend_location = overrides.legend_location
    if overrides.grid is not None:
        doc.grid = overrides.grid
    if overrides.xlim is not None:
        doc.xlim = list(overrides.xlim)
    if overrides.ylim is not None:
        doc.ylim = list(overrides.ylim)
    # Kind options stay in the overrides across chart switches but only
    # reach a document of their own kind.
    if overrides.violin is not None and kind == 'violin':
        doc.violin = copy.deepcopy(overrides.violin)
    if overrides.ridgeline is not None and kind == 'ridgeline':
        doc.ridgeline = copy.deepcopy(overrides.ridgeline)
    if overrides.stacked is not None and kind == 'stacked_column':
        doc.stacked = copy.deepcopy(overrides.stacked)
        doc.stacked.percent = bool(percent)
        doc.stacked.grouped = chart_key == 'column'
    if overrides.bar_labels and doc.x_tick_labels:
        for entry in doc.x_tick_labels:
            idx = int(entry[0])
            if idx in overrides.bar_labels:
                entry[1] = overrides.bar_labels[idx]
    if overrides.annotations:
        doc.annotations = copy.deepcopy(overrides.annotations)
    if overrides.brackets:
        doc.brackets = copy.deepcopy(overrides.brackets)
    doc.style = copy.deepcopy(overrides.style) \
        if overrides.style is not None else PlotStyle()
    # Per-item label/colour overrides, keyed by Y column (the other
    # SeriesOverride fields only apply to line-kind series).
    for coll in (doc.series, doc.groups, doc.categories):
        pal_colors = None
        if overrides.palette or overrides.palette_reverse:
            from .palettes import theme_colors
            pal_colors = theme_colors(
                overrides.palette, len(coll), chart_key,
                reverse=bool(overrides.palette_reverse))
        for i, entry in enumerate(coll):
            if i >= len(items):
                break
            y_col = getattr(items[i], 'y_column', None)
            so = overrides.series.get(y_col) if y_col is not None \
                else None
            entry.label = so.label if so is not None \
                and so.label is not None else items[i].label
            if so is not None and so.color is not None:
                entry.color = so.color
            elif pal_colors is not None:
                entry.color = pal_colors[i]
            if kind in ('line', 'ridgeline') and so is not None:
                if so.linewidth_pt is not None:
                    entry.linewidth_pt = so.linewidth_pt
                if so.linestyle is not None:
                    entry.linestyle = so.linestyle
                if so.marker is not None:
                    entry.marker = so.marker
                if so.markersize_pt is not None:
                    entry.markersize_pt = so.markersize_pt
    return doc.validate()
