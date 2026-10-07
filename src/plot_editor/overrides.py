"""Editor-side per-element overrides (pure Python, no Qt).

In-place edits are *overrides*: a set field wins over whatever the
worksheet would derive, ``None`` means "not overridden". They serialize
into the ``ilm-plot-worksheet`` node (v2) — omitting defaults keeps
unstyled files at schema v1.
"""

import copy
import math

from ilmplot.document import (LEGEND_LOCATIONS, LINESTYLES, MARKERS,
                       MAX_ANNOTATIONS, MAX_BANDS, MAX_BRACKETS,
                       MAX_SERIES, MAX_SPANS,
                       Annotation, Band, Bracket, HistOptions,
                       PlotDocument, PlotStyle, RidgeOptions, Span,
                       StackOptions, ViolinOptions,
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
                 'markersize_pt', 'error_style', 'error_alpha')
    _KEYS = __slots__

    def __init__(self, label=None, color=None, linewidth_pt=None,
                 linestyle=None, marker=None, markersize_pt=None,
                 error_style=None, error_alpha=None):
        self.label = label
        self.color = color
        self.linewidth_pt = linewidth_pt
        self.linestyle = linestyle
        self.marker = marker
        self.markersize_pt = markersize_pt
        self.error_style = error_style
        self.error_alpha = error_alpha

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
        s.error_style = _opt_choice(data, 'error_style', ctx,
                                    ('bars', 'band'))
        s.error_alpha = _opt_num(data, 'error_alpha', ctx,
                                 lo=0, hi=1, lo_exclusive=True)
        return s


class PlotOverrides:
    """Document-level overrides plus per-series ones."""

    __slots__ = ('xlabel', 'ylabel', 'legend', 'legend_location', 'grid',
                 'xlim', 'ylim', 'style', 'series', 'palette',
                 'palette_reverse', 'violin', 'ridgeline', 'stacked',
                 'histogram', 'annotations', 'brackets', 'bands',
                 'bar_labels', 'spans', 'fills')
    _KEYS = ('xlabel', 'ylabel', 'legend', 'legend_location', 'grid',
             'xlim', 'ylim', 'style', 'series', 'palette',
             'palette_reverse', 'violin', 'ridgeline', 'stacked',
             'histogram', 'annotations', 'brackets', 'bands',
             'bar_labels', 'spans', 'fills')

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
        self.histogram = None
        self.annotations = None
        self.brackets = None
        self.bands = None
        self.bar_labels = None
        self.spans = None
        self.fills = None

    def is_empty(self):
        return (self.xlabel is None and self.ylabel is None
                and self.legend is None and self.legend_location is None
                and self.grid is None and self.xlim is None
                and self.ylim is None and not self.style.to_dict()
                and all(o.is_empty() for o in self.series.values())
                and self.palette is None and self.palette_reverse is None
                and self.violin is None and self.ridgeline is None
                and self.stacked is None and self.histogram is None
                and not self.annotations
                and not self.brackets and not self.bands
                and not self.bar_labels and not self.spans
                and not self.fills)

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
        for k in ('violin', 'ridgeline', 'stacked', 'histogram'):
            opt = getattr(self, k)
            if opt is not None:
                od = opt.to_dict()
                if od:
                    d[k] = od
        if self.annotations:
            d['annotations'] = [a.to_dict() for a in self.annotations]
        if self.brackets:
            d['brackets'] = [b.to_dict() for b in self.brackets]
        if self.bands:
            d['bands'] = [b.to_dict() for b in self.bands]
        if self.bar_labels:
            d['bar_labels'] = {str(k): v for k, v in
                               self.bar_labels.items()}
        if self.spans:
            d['spans'] = [s.to_dict() for s in self.spans]
        if self.fills:
            d['fills'] = [f.to_dict() for f in self.fills]
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
                          ('stacked', StackOptions),
                          ('histogram', HistOptions)):
            if data.get(name) is not None:
                try:
                    setattr(o, name, typ.from_dict(
                        data[name], f"{ctx}.{name}"))
                except ValueError as e:
                    raise _err(str(e))
        for name, typ, limit in (('annotations', Annotation,
                                  MAX_ANNOTATIONS),
                                 ('brackets', Bracket, MAX_BRACKETS),
                                 ('bands', Band, MAX_BANDS),
                                 ('spans', Span, MAX_SPANS)):
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
        fills = data.get('fills')
        if fills is not None:
            from .fills import CurveFill
            if not isinstance(fills, list) \
                    or len(fills) > MAX_BANDS + MAX_SPANS:
                raise _err(f"{ctx}.fills: expected at most "
                           f"{MAX_BANDS + MAX_SPANS} entries")
            try:
                o.fills = [CurveFill.from_dict(
                    f, f"{ctx}.fills[{i}]")
                    for i, f in enumerate(fills)]
            except ValueError as e:
                raise _err(str(e))
            ids = set()
            for f in o.fills:
                if f.id in ids:
                    raise _err(f"{ctx}.fills: duplicate id {f.id!r}")
                ids.add(f.id)
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
    elif key.startswith(('series:', 'violin:', 'stack:', 'hist:')):
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


def static_bands(doc, overrides):
    """``doc.bands`` minus the bands computed from ``overrides.fills``
    (they share the fill's id): the list to lift into
    ``overrides.bands`` for editing/deleting, so the next
    ``effective_document`` doesn't append a duplicate fill band."""
    fill_ids = {f.id for f in (overrides.fills or ())}
    return [b for b in getattr(doc, 'bands', None) or ()
            if b.id not in fill_ids]


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
    # Curve fills reference Y columns: remap them the same way and drop
    # fills whose column was removed.
    if overrides.fills:
        def _remap(col):
            if event[0] == 'columns_inserted':
                return col + count if col >= at else col
            if at <= col < at + count:
                return None
            return col - count if col >= at + count else col
        kept = []
        for f in overrides.fills:
            a = _remap(f.a)
            b = _remap(f.b) if f.b is not None else None
            if a is None or (f.b is not None and b is None):
                continue
            f.a, f.b = a, b
            kept.append(f)
        overrides.fills = kept or None
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


def record_overrides_edit(worksheet, overrides, fn, commit,
                          label='Edit Plot'):
    """Apply ``fn(overrides)`` and record it in *worksheet*'s undo
    history (chronological with cell edits).

    Keeps ``apply_update``'s rollback; a no-op edit (identical
    ``to_dict``) or a failed one records nothing. Apply/revert restore
    every ``PlotOverrides._KEYS`` field **in place** — open panels and
    the tab hold that exact object — then run ``commit()`` (re-render).
    ``_record`` calls ``apply`` immediately, so the restore is
    idempotent. Returns True when an entry was recorded.
    """
    before = copy.deepcopy(overrides)
    if not apply_update(overrides, fn, commit):
        return False
    after = copy.deepcopy(overrides)
    if before.to_dict() == after.to_dict():
        return False

    def restore(snapshot):
        fresh = copy.deepcopy(snapshot)
        for name in PlotOverrides._KEYS:
            setattr(overrides, name, getattr(fresh, name))
        commit()

    worksheet.record_external_edit(
        label, apply=lambda: restore(after),
        revert=lambda: restore(before))
    return True


_SERIES_SEED_FIELDS = ('color', 'linewidth_pt', 'linestyle', 'marker',
                       'markersize_pt', 'error_style', 'error_alpha')


def overrides_from_document(doc, items=None, chart_key=None):
    """Seed overrides from a document with no override metadata (legacy or
    ILM file): style is cloned; document-level fields are set only where
    they differ from a fresh ``PlotDocument``.

    With *items* + *chart_key* and a line-kind document whose series
    count matches, per-series overrides are seeded with every look
    field (colour, width, style, marker, size, error display) that
    differs from a plain ``document_from_plot`` regeneration — so the
    series look survives the first save (which switches the file onto
    the regenerated-document path)."""
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
    if doc.histogram is not None:
        o.histogram = copy.deepcopy(doc.histogram)
    if doc.annotations:
        o.annotations = copy.deepcopy(doc.annotations)
    if doc.brackets:
        o.brackets = copy.deepcopy(doc.brackets)
    if doc.bands:
        o.bands = copy.deepcopy(doc.bands)
    if getattr(doc, 'spans', None):
        o.spans = copy.deepcopy(doc.spans)
    if items is not None and chart_key is not None \
            and doc.kind in ('line', 'ridgeline') \
            and len(items) == len(doc.series):
        from .export import document_from_plot
        try:
            regen = document_from_plot(items, chart_key)
        except Exception:
            regen = None
        if regen is not None:
            for i, (s, rs) in enumerate(zip(doc.series, regen.series)):
                y_col = getattr(items[i], 'y_column', None)
                if y_col is None:
                    continue
                diff = {}
                for f in _SERIES_SEED_FIELDS:
                    if getattr(s, f, None) != getattr(rs, f, None):
                        diff[f] = getattr(s, f)
                if diff:
                    o.series[y_col] = SeriesOverride(**diff)
    return o


def effective_document(base_doc, items, chart_key, title, overrides, *,
                       figure_size=None):
    """Build the validated ``PlotDocument`` shown/saved by the editor.

    ``items`` are Series/Group/Category objects. ``base_doc`` (an
    already-loaded document) wins over regeneration for line kinds when
    its series count matches; new kinds always regenerate from the
    worksheet items. Overrides are applied on top.
    """
    from .export import (CHART_KIND, GROUPED_CHARTS,
                         HORIZONTAL_CHARTS, VIOLIN_BODY,
                         default_axis_titles, document_from_plot)
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
    h_eff = overrides.histogram if overrides.histogram is not None \
        else doc.histogram
    x_def, y_def = default_axis_titles(
        items, chart_key,
        density=bool(h_eff.density) if h_eff is not None else False)
    doc.xlabel = overrides.xlabel if overrides.xlabel is not None \
        else x_def
    doc.ylabel = overrides.ylabel if overrides.ylabel is not None \
        else y_def
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
    if kind == 'violin' and (doc.violin is not None
                             or chart_key != 'violin'):
        # The chart key owns the body; a plain violin without
        # overrides keeps ``violin=None`` (byte-identical output).
        doc.violin = doc.violin or ViolinOptions()
        doc.violin.body = VIOLIN_BODY[chart_key]
    if overrides.histogram is not None and kind == 'histogram':
        doc.histogram = copy.deepcopy(overrides.histogram)
    if overrides.ridgeline is not None and kind == 'ridgeline':
        doc.ridgeline = copy.deepcopy(overrides.ridgeline)
    if overrides.stacked is not None and kind == 'stacked_column':
        doc.stacked = copy.deepcopy(overrides.stacked)
        doc.stacked.percent = bool(percent)
        doc.stacked.grouped = chart_key in GROUPED_CHARTS
        doc.stacked.horizontal = chart_key in HORIZONTAL_CHARTS
    if overrides.bar_labels and doc.x_tick_labels:
        for entry in doc.x_tick_labels:
            idx = int(entry[0])
            if idx in overrides.bar_labels:
                entry[1] = overrides.bar_labels[idx]
    if overrides.annotations:
        doc.annotations = copy.deepcopy(overrides.annotations)
    if overrides.brackets:
        doc.brackets = copy.deepcopy(overrides.brackets)
    if overrides.bands is not None and doc.kind == 'line':
        doc.bands = copy.deepcopy(overrides.bands)
    if doc.kind == 'line':
        if overrides.spans is not None:
            doc.spans = copy.deepcopy(overrides.spans)
        if overrides.fills:
            # Curve fills compile to bands after the static ones, bound
            # to the *drawn* series (stacked-line offsets already in
            # ``doc.series``).
            from .fills import compute_band
            drawn = {}
            for it, s in zip(items, doc.series):
                y_col = getattr(it, 'y_column', None)
                if y_col is not None:
                    drawn[y_col] = (s.x, s.y)
            for fl in overrides.fills:
                band = compute_band(fl, drawn)
                if band is not None:
                    doc.bands.append(band)
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
                if so.error_style is not None:
                    entry.error_style = so.error_style
                if so.error_alpha is not None:
                    entry.error_alpha = so.error_alpha
    if figure_size is not None:
        doc.width_mm = figure_size.width_mm
        doc.height_mm = figure_size.height_mm
    return doc.validate()
