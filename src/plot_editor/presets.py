"""Style presets for the Plot Editor (Qt-free).

A preset captures formatting only — fonts, alignment, tick look, grid,
legend and series appearance by order — never data-tied fields (titles,
limits, tick spacing, prefix/suffix, log scale, reversed). Presets are
one JSON file each under ``<root>/<plot_type>/<slug>.ilmstyle.json``
plus a ``defaults.json`` mapping plot type → preset name. Plot type is
the chart *group* key (``actions.CHART_GROUPS``); today only 'line'
exists, covering all four line charts.
"""

from __future__ import annotations

import copy
import json
import os
import re
import tempfile
from dataclasses import dataclass, field

from .actions import CHART_GROUPS
from ilmplot.document import (LEGEND_LOCATIONS, LINESTYLES, MARKERS,
                       AxisStyle, HistOptions, PlotStyle, RidgeOptions,
                       StackOptions, ViolinOptions, _check_color)
from .overrides import PlotOverrides, SeriesOverride

FORMAT = 'ilm-plot-style'
SCHEMA_VERSION = 1
STANDARD_NAME = 'Standard'
MAX_NAME = 60
MAX_COLORS = 20
_SUFFIX = '.ilmstyle.json'
# AxisStyle fields tied to the data, never captured or applied.
_DATA_AXIS_FIELDS = ('step', 'prefix', 'suffix', 'scale', 'reversed')


class PresetError(ValueError):
    pass


def plot_type_for_chart(chart_key):
    """Chart key → its group's key; unknown → the group key itself."""
    for group in CHART_GROUPS:
        if any(c.key == chart_key for c in group.charts):
            return group.key
    return chart_key


def _slug(name):
    """Filesystem-safe slug: keeps CJK, replaces separators/spaces."""
    s = re.sub(r'[\\/:*?"<>|\s]+', '_', name).strip('._')
    return s or 'preset'


def _check_name(name):
    if not isinstance(name, str) or not name.strip():
        raise PresetError('Preset name must not be empty')
    if len(name) > MAX_NAME:
        raise PresetError('Preset name is too long (max %d)' % MAX_NAME)
    if re.search(r'[\\/:*?"<>|]', name):
        raise PresetError('Preset name must not contain path separators')


@dataclass
class SeriesLook:
    """Per-series appearance applied by order of the series list."""
    colors: 'list | None' = None       # hex list; None = chart cycle
    linewidth_pt: 'float | None' = None
    linestyle: 'str | None' = None
    marker: 'str | None' = None
    markersize_pt: 'float | None' = None

    def is_empty(self):
        return (self.colors is None and self.linewidth_pt is None
                and self.linestyle is None and self.marker is None
                and self.markersize_pt is None)

    def to_dict(self):
        d = {}
        if self.colors is not None:
            d['colors'] = list(self.colors)
        if self.linewidth_pt is not None:
            d['linewidth_pt'] = self.linewidth_pt
        if self.linestyle is not None:
            d['linestyle'] = self.linestyle
        if self.marker is not None:
            d['marker'] = self.marker
        if self.markersize_pt is not None:
            d['markersize_pt'] = self.markersize_pt
        return d

    @classmethod
    def from_dict(cls, data):
        ctx = 'series'
        if not isinstance(data, dict):
            raise PresetError(f'{ctx}: expected an object')
        allowed = {'colors', 'linewidth_pt', 'linestyle', 'marker',
                   'markersize_pt'}
        for k in data:
            if k not in allowed:
                raise PresetError(f'{ctx}: unknown key {k!r}')
        look = cls()
        colors = data.get('colors')
        if colors is not None:
            if (not isinstance(colors, list)
                    or not 1 <= len(colors) <= MAX_COLORS):
                raise PresetError(
                    f'{ctx}.colors: expected 1..{MAX_COLORS} hex '
                    'strings')
            try:
                look.colors = [_check_color(c, f'{ctx}.colors')
                               for c in colors]
            except ValueError as e:
                raise PresetError(str(e)) from e
        lw = data.get('linewidth_pt')
        if lw is not None:
            if not isinstance(lw, (int, float)) or isinstance(lw, bool) \
                    or not (0 < lw <= 200):
                raise PresetError(
                    f'{ctx}.linewidth_pt: expected a number in (0, 200]')
            look.linewidth_pt = float(lw)
        ls = data.get('linestyle')
        if ls is not None:
            if ls not in LINESTYLES:
                raise PresetError(f'{ctx}.linestyle: unknown {ls!r}')
            look.linestyle = ls
        mk = data.get('marker')
        if mk is not None:
            if mk not in MARKERS:
                raise PresetError(f'{ctx}.marker: unknown {mk!r}')
            look.marker = mk
        ms = data.get('markersize_pt')
        if ms is not None:
            if not isinstance(ms, (int, float)) or isinstance(ms, bool) \
                    or not (0 <= ms <= 200):
                raise PresetError(
                    f'{ctx}.markersize_pt: expected a number in '
                    '[0, 200]')
            look.markersize_pt = float(ms)
        return look


@dataclass
class StylePreset:
    name: str
    plot_type: str
    style: PlotStyle = field(default_factory=PlotStyle)
    legend: 'bool | None' = None
    legend_location: 'str | None' = None
    grid: 'bool | None' = None
    series: SeriesLook = field(default_factory=SeriesLook)
    palette: 'str | None' = None
    palette_reverse: 'bool | None' = None
    violin: 'ViolinOptions | None' = None
    ridgeline: 'RidgeOptions | None' = None
    stacked: 'StackOptions | None' = None
    histogram: 'HistOptions | None' = None
    builtin: bool = False
    filename: 'str | None' = None     # basename when loaded from disk

    def to_dict(self):
        _check_name(self.name)
        d = {'format': FORMAT, 'schema_version': SCHEMA_VERSION,
             'type': self.plot_type, 'name': self.name,
             'style': self.style.to_dict()}
        if self.legend is not None:
            d['legend'] = self.legend
        if self.legend_location is not None:
            d['legend_location'] = self.legend_location
        if self.grid is not None:
            d['grid'] = self.grid
        if not self.series.is_empty():
            d['series'] = self.series.to_dict()
        if self.palette is not None:
            d['palette'] = self.palette
        if self.palette_reverse is not None:
            d['palette_reverse'] = self.palette_reverse
        for k in ('violin', 'ridgeline', 'stacked', 'histogram'):
            opt = getattr(self, k)
            if opt is not None:
                od = opt.to_dict()
                if od:
                    d[k] = od
        return d

    @classmethod
    def from_dict(cls, data, filename=None):
        if not isinstance(data, dict):
            raise PresetError('expected a JSON object')
        allowed = {'format', 'schema_version', 'type', 'name', 'style',
                   'legend', 'legend_location', 'grid', 'series',
                   'palette', 'palette_reverse', 'violin', 'ridgeline',
                   'stacked', 'histogram'}
        for k in data:
            if k not in allowed:
                raise PresetError(f'unknown key {k!r}')
        if data.get('format') != FORMAT:
            raise PresetError(f'format: expected {FORMAT!r}')
        if data.get('schema_version') != SCHEMA_VERSION:
            raise PresetError(
                'schema_version: expected %d' % SCHEMA_VERSION)
        ptype = data.get('type')
        if not isinstance(ptype, str) or not ptype:
            raise PresetError('type: expected a string')
        name = data.get('name')
        _check_name(name)
        style = data.get('style')
        if not isinstance(style, dict):
            raise PresetError('style: expected an object')
        try:
            preset_style = PlotStyle.from_dict(style, 'style')
        except ValueError as e:
            raise PresetError(str(e)) from e
        preset = cls(name=name, plot_type=ptype, style=preset_style,
                     filename=filename)
        for key in ('legend', 'grid'):
            v = data.get(key)
            if v is not None:
                if not isinstance(v, bool):
                    raise PresetError(f'{key}: expected a bool')
                setattr(preset, key, v)
        loc = data.get('legend_location')
        if loc is not None:
            if loc not in LEGEND_LOCATIONS:
                raise PresetError(f'legend_location: unknown {loc!r}')
            preset.legend_location = loc
        if 'series' in data:
            preset.series = SeriesLook.from_dict(data['series'])
        pal = data.get('palette')
        if pal is not None:
            from .palettes import valid_theme_ref
            if not valid_theme_ref(pal):
                raise PresetError(f'palette: unknown theme {pal!r}')
            preset.palette = pal
        pr = data.get('palette_reverse')
        if pr is not None:
            if not isinstance(pr, bool):
                raise PresetError('palette_reverse: expected a bool')
            preset.palette_reverse = pr
        for name, typ in (('violin', ViolinOptions),
                          ('ridgeline', RidgeOptions),
                          ('stacked', StackOptions),
                          ('histogram', HistOptions)):
            if data.get(name) is not None:
                try:
                    setattr(preset, name, typ.from_dict(
                        data[name], f'preset.{name}'))
                except ValueError as e:
                    raise PresetError(str(e)) from e
        return preset


def _write_atomic(path, text):
    parent = os.path.dirname(path)
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent, prefix='.', suffix='.tmp')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def builtin_preset(plot_type):
    """The read-only "Standard" preset: chart defaults, no formatting."""
    return StylePreset(name=STANDARD_NAME, plot_type=plot_type,
                       builtin=True)


class PresetStore:
    """Folder-backed preset collection: ``<root>/<type>/*.ilmstyle.json``."""

    def __init__(self, root):
        self.root = root
        self.errors = []          # (filename, message) of skipped files

    def _dir(self, plot_type):
        return os.path.join(self.root, plot_type)

    def _defaults_path(self):
        return os.path.join(self.root, 'defaults.json')

    def _load_defaults(self):
        try:
            with open(self._defaults_path(), encoding='utf-8') as fh:
                data = json.load(fh)
        except (OSError, ValueError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_defaults(self, data):
        _write_atomic(self._defaults_path(), json.dumps(
            data, ensure_ascii=False, indent=2))

    def _custom(self, plot_type):
        """Custom presets from disk; invalid files go to self.errors."""
        self.errors = []
        out = []
        folder = self._dir(plot_type)
        try:
            names = sorted(os.listdir(folder))
        except OSError:
            return out
        for fn in names:
            if not fn.lower().endswith(_SUFFIX):
                continue
            path = os.path.join(folder, fn)
            try:
                with open(path, encoding='utf-8') as fh:
                    preset = StylePreset.from_dict(json.load(fh),
                                                   filename=fn)
            except (OSError, ValueError, PresetError) as e:
                self.errors.append((fn, str(e)))
                continue
            if preset.plot_type != plot_type:
                self.errors.append((fn, 'type mismatch'))
                continue
            out.append(preset)
        out.sort(key=lambda p: p.name.lower())
        return out

    def list(self, plot_type):
        return [builtin_preset(plot_type)] + self._custom(plot_type)

    def get(self, plot_type, name):
        for p in self.list(plot_type):
            if p.name == name:
                return p
        return None

    def _find(self, plot_type, name):
        for p in self._custom(plot_type):
            if p.name.lower() == name.lower():
                return p
        return None

    def save(self, preset, overwrite=False):
        _check_name(preset.name)
        if preset.name == STANDARD_NAME:
            raise PresetError(f'{STANDARD_NAME!r} is a built-in name')
        existing = self._find(preset.plot_type, preset.name)
        if existing is not None and not overwrite \
                and existing.filename != preset.filename:
            raise PresetError(
                'A preset named %r already exists' % preset.name)
        path = os.path.join(self._dir(preset.plot_type),
                            _slug(preset.name) + _SUFFIX)
        preset.filename = os.path.basename(path)
        _write_atomic(path, json.dumps(preset.to_dict(),
                                       ensure_ascii=False, indent=2))
        return preset

    def rename(self, plot_type, old, new):
        p = self._find(plot_type, old)
        if p is None:
            raise PresetError('No preset named %r' % old)
        _check_name(new)
        if new == STANDARD_NAME or self._find(plot_type, new):
            raise PresetError('A preset named %r already exists' % new)
        old_path = os.path.join(self._dir(plot_type), p.filename)
        try:
            os.unlink(old_path)
        except OSError:
            pass
        p.name = new
        self.save(p, overwrite=True)
        if self.default_name(plot_type) == old:
            self.set_default(plot_type, new)
        return p

    def duplicate(self, plot_type, name):
        p = self._find(plot_type, name)
        if p is None:
            src = builtin_preset(plot_type)
            if name != STANDARD_NAME:
                raise PresetError('No preset named %r' % name)
            p = src
        base = re.sub(r'\s*\(\d+\)$', '', name)
        for n in range(2, 1000):
            cand = '%s (%d)' % (base, n)
            if self._find(plot_type, cand) is None \
                    and cand != STANDARD_NAME:
                break
        clone = StylePreset.from_dict(p.to_dict())
        clone.name = cand
        clone.filename = None
        return self.save(clone)

    def delete(self, plot_type, name):
        if name == STANDARD_NAME:
            raise PresetError(f'{STANDARD_NAME!r} is built-in')
        p = self._find(plot_type, name)
        if p is None:
            raise PresetError('No preset named %r' % name)
        try:
            os.unlink(os.path.join(self._dir(plot_type), p.filename))
        except OSError as e:
            raise PresetError(str(e)) from e
        if self.default_name(plot_type) == name:
            self.set_default(plot_type, None)

    def default_name(self, plot_type):
        return self._load_defaults().get(plot_type) or STANDARD_NAME

    def set_default(self, plot_type, name):
        if name is not None and name != STANDARD_NAME:
            p = self._find(plot_type, name)
            if p is None:
                raise PresetError('No preset named %r' % name)
        data = self._load_defaults()
        if name in (None, STANDARD_NAME):
            data.pop(plot_type, None)
        else:
            data[plot_type] = name
        self._write_defaults(data)

    def default_preset(self, plot_type):
        return self.get(plot_type, self.default_name(plot_type)) \
            or builtin_preset(plot_type)


def _strip_axis_data_fields(axis):
    if axis is not None:
        for f in _DATA_AXIS_FIELDS:
            setattr(axis, f, getattr(AxisStyle(), f))


def capture(overrides, plot_type):
    """Formatting-only ``StylePreset`` payload from *overrides*."""
    style = copy.deepcopy(overrides.style)
    _strip_axis_data_fields(style.xaxis)
    _strip_axis_data_fields(style.yaxis)
    series = SeriesLook()
    ordered = sorted(overrides.series.items())   # y_column order
    colors = [s.color for _k, s in ordered if s.color is not None]
    if colors:
        series.colors = colors[:MAX_COLORS]
    for _k, s in ordered:
        if series.linewidth_pt is None and s.linewidth_pt is not None:
            series.linewidth_pt = s.linewidth_pt
        if series.linestyle is None and s.linestyle is not None:
            series.linestyle = s.linestyle
        if series.marker is None and s.marker is not None:
            series.marker = s.marker
        if series.markersize_pt is None and s.markersize_pt is not None:
            series.markersize_pt = s.markersize_pt
    return StylePreset(name='', plot_type=plot_type, style=style,
                       legend=overrides.legend,
                       legend_location=overrides.legend_location,
                       grid=overrides.grid, series=series,
                       palette=overrides.palette,
                       palette_reverse=overrides.palette_reverse,
                       violin=copy.deepcopy(overrides.violin),
                       ridgeline=copy.deepcopy(overrides.ridgeline),
                       stacked=copy.deepcopy(overrides.stacked),
                       histogram=copy.deepcopy(overrides.histogram))


def _merge_axis_data(old, new):
    """Copy data-tied axis fields from *old* into *new* (in place)."""
    if old is None:
        return new
    if new is None:
        new = AxisStyle()
    for f in _DATA_AXIS_FIELDS:
        setattr(new, f, getattr(old, f))
    return new


def apply(preset, overrides, series_list, chart_key):
    """Apply *preset* to *overrides*; keeps text and data-tied fields."""
    from .export import _STYLE
    draws_line, draws_marker = _STYLE.get(chart_key, ('', ''))
    if preset.builtin:
        keep = overrides.style
        overrides.style = PlotStyle()
        overrides.style.xaxis = _merge_axis_data(keep.xaxis, None)
        overrides.style.yaxis = _merge_axis_data(keep.yaxis, None)
        overrides.legend = None
        overrides.legend_location = None
        overrides.grid = None
        for key, so in list(overrides.series.items()):
            so.color = so.linewidth_pt = so.linestyle = None
            so.marker = so.markersize_pt = None
            if so.is_empty():
                del overrides.series[key]
        overrides.palette = None
        overrides.palette_reverse = None
        overrides.violin = None
        overrides.ridgeline = None
        overrides.stacked = None
        overrides.histogram = None
        return
    keep = overrides.style
    overrides.style = copy.deepcopy(preset.style)
    overrides.style.xaxis = _merge_axis_data(
        keep.xaxis, overrides.style.xaxis)
    overrides.style.yaxis = _merge_axis_data(
        keep.yaxis, overrides.style.yaxis)
    overrides.legend = preset.legend
    overrides.legend_location = preset.legend_location
    overrides.grid = preset.grid
    look = preset.series
    for i, s in enumerate(series_list):
        y_col = getattr(s, 'y_column', None)
        if y_col is None:
            continue
        so = overrides.series.get(y_col)
        if so is None:
            so = SeriesOverride()
            overrides.series[y_col] = so
        if look.colors:
            so.color = look.colors[i % len(look.colors)]
        if look.linewidth_pt is not None:
            so.linewidth_pt = look.linewidth_pt
        if draws_line and look.linestyle is not None:
            so.linestyle = look.linestyle
        if draws_marker and look.marker is not None:
            so.marker = look.marker
        if look.markersize_pt is not None:
            so.markersize_pt = look.markersize_pt
    overrides.palette = preset.palette
    overrides.palette_reverse = preset.palette_reverse
    overrides.violin = copy.deepcopy(preset.violin)
    overrides.ridgeline = copy.deepcopy(preset.ridgeline)
    overrides.stacked = copy.deepcopy(preset.stacked)
    overrides.histogram = copy.deepcopy(preset.histogram)


def should_auto_apply(overrides, preset):
    """Auto-apply the type default only on a fresh, unoverridden plot."""
    return (preset is not None and not preset.builtin
            and overrides is not None and overrides.is_empty())
