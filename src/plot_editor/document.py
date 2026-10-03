"""Native plot document model + strict (de)serialization.

A ``PlotDocument`` describes one line plot. It serializes to a JSON payload
embedded in the SVG ``<metadata id="ilm-plot-document">`` element, making the
``*.ilmplot.svg`` file both a portable vector image and an editable document.

Parsing is strict by design: unknown fields, wrong types, non-finite numbers,
duplicate series ids and future schema versions raise
:class:`PlotDocumentError` with an actionable message rather than silently
losing data. Loading never executes code — no eval, pickle, or scripts.
"""

from __future__ import annotations

import copy
import io
import json
import math
import os
import re
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields

SCHEMA_VERSION = 1
METADATA_ID = 'ilm-plot-document'
FORMAT_NAME = 'ilm-plot'

# Optional-feature ids the reader understands beyond the schema-1
# baseline. Every new optional document field added after the baseline
# must get a capability id in CAPABILITIES, and writers must add it to
# ``requires`` whenever the field is emitted.
CAPABILITIES = frozenset()

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_SERIES = 100
MAX_TOTAL_POINTS = 100_000
MAX_DIMENSION_MM = 1000.0

LINESTYLES = ('-', '--', '-.', ':', '')
MARKERS = ('', 'o', 's', '^', 'v', 'D', '+', 'x', '.')
LEGEND_LOCATIONS = (
    'best', 'upper right', 'upper left', 'lower left', 'lower right',
    'right', 'center left', 'center right', 'lower center',
    'upper center', 'center', 'outside right',
)

# ``kind``: 'line' and 'ridgeline' plot ``series`` (LineSeries), 'violin'
# plots ``groups`` (ViolinGroup), 'stacked_column' plots ``categories``
# (StackCategory). Schema stays 1 — older builds reject the new kinds.
KINDS = ('line', 'violin', 'ridgeline', 'stacked_column')

ANNOTATION_ANCHORS = _ANCHORS = (
    'upper left', 'upper center', 'upper right',
    'lower left', 'lower center', 'lower right',
    'center left', 'center right')
_BANDWIDTHS = ('scott', 'silverman')
MAX_ANNOTATIONS = 20
MAX_BRACKETS = 20


class PlotDocumentError(ValueError):
    pass


class PlotVersionError(PlotDocumentError):
    """The file needs a newer Plot Editor (schema or capabilities)."""

    def __init__(self, message, schema_version=None, missing=()):
        super().__init__(message)
        self.schema_version = schema_version
        self.missing = sorted(missing)
    """Raised when a plot document is malformed or unsupported."""


def _err(msg: str) -> PlotDocumentError:
    return PlotDocumentError(msg)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def _req_number(data: dict, key: str, ctx: str,
                lo: float | None = None, hi: float | None = None,
                lo_exclusive: bool = False) -> float:
    v = data.get(key)
    if not _is_num(v) or not math.isfinite(v):
        raise _err(f"{ctx}.{key}: expected a finite number, got {v!r}")
    v = float(v)
    if lo is not None and (v <= lo if lo_exclusive else v < lo):
        op = '>' if lo_exclusive else '>='
        raise _err(f"{ctx}.{key}: expected {op} {lo}, got {v}")
    if hi is not None and v > hi:
        raise _err(f"{ctx}.{key}: expected <= {hi}, got {v}")
    return v


def _req_str(data: dict, key: str, ctx: str, allow_empty: bool = True) -> str:
    v = data.get(key)
    if not isinstance(v, str) or (not allow_empty and not v):
        raise _err(f"{ctx}.{key}: expected a string, got {v!r}")
    return v


def _req_bool(data: dict, key: str, ctx: str) -> bool:
    v = data.get(key)
    if not isinstance(v, bool):
        raise _err(f"{ctx}.{key}: expected true/false, got {v!r}")
    return v


def _check_color(value: str, ctx: str) -> str:
    """Validate and normalize a color to '#rrggbb' / '#rrggbbaa'."""
    if not isinstance(value, str):
        raise _err(f"{ctx}: expected a hex color string, got {value!r}")
    v = value.strip()
    try:
        from matplotlib.colors import to_rgba
        r, g, b, a = to_rgba(v)
    except Exception:
        raise _err(f"{ctx}: unsupported color {value!r}; use #rgb/#rrggbb/#rrggbbaa")
    if not v.startswith('#'):
        # Only accept literal hex in the file format — named colors and
        # expressions are normalized to hex so the document is stable.
        return '#{:02x}{:02x}{:02x}{:02x}'.format(
            round(r * 255), round(g * 255), round(b * 255), round(a * 255))
    if len(v) not in (4, 5, 7, 9):
        raise _err(f"{ctx}: invalid hex color {value!r}")
    try:
        int(v[1:], 16)
    except ValueError:
        raise _err(f"{ctx}: invalid hex color {value!r}")
    return v.lower()


def _check_limit(value, ctx: str):
    if value is None:
        return None
    if (not isinstance(value, (list, tuple)) or len(value) != 2
            or any(not _is_num(v) or not math.isfinite(v) for v in value)):
        raise _err(f"{ctx}: expected null or [min, max] of finite numbers")
    lo, hi = float(value[0]), float(value[1])
    if lo == hi:
        raise _err(f"{ctx}: axis limits must differ (got {lo} == {hi})")
    return [lo, hi]  # inverted axes are allowed


def _check_yerr(value, expected_len: int, ctx: str):
    """Optional y-error array: finite numbers >= 0 matching the series
    length, or None."""
    if value is None:
        return None
    if not isinstance(value, list) or len(value) != expected_len \
            or any(not _is_num(v) or not math.isfinite(v) or v < 0
                   for v in value):
        raise _err(f"{ctx}: expected null or an array of {expected_len} "
                   "finite numbers >= 0")
    return [float(v) for v in value]


def _check_yerr_pair(yerr, yerr_minus, yerr_plus, ctx: str):
    if (yerr_minus is None) != (yerr_plus is None):
        raise _err(f"{ctx}: yerr_minus and yerr_plus must be given "
                   "together")
    if yerr is not None and yerr_minus is not None:
        raise _err(f"{ctx}: use either yerr or yerr_minus/yerr_plus")


_REQUIRE_RE = re.compile(r'^[a-z0-9_.-]{1,40}$')


def _check_requires(value, ctx: str):
    """Optional capability-id list: unique [a-z0-9_.-]{1,40}, <= 50."""
    if value is None:
        return []
    if not isinstance(value, list) or len(value) > 50 \
            or any(not isinstance(v, str)
                   or not _REQUIRE_RE.match(v) for v in value) \
            or len(set(value)) != len(value):
        raise _err(f"{ctx}: expected an array of unique capability ids "
                   "([a-z0-9_.-]{1,40}, at most 50)")
    return list(value)


def required_capabilities(document) -> list:
    """Capability ids that must be stamped on *document*'s output."""
    return []


MAX_TICK_LABEL = 1000


def _check_tick_labels(value, ctx):
    """Validate an optional categorical x-axis tick list.

    Shape: ``[[position, label], ...]`` with unique finite positions and
    labels of at most ``MAX_TICK_LABEL`` characters. ``None`` (absent)
    passes through unchanged.
    """
    if value is None:
        return None
    if not isinstance(value, (list, tuple)) or not value:
        raise _err(f"{ctx}: expected a non-empty array of "
                   "[position, label] pairs")
    if len(value) > MAX_TOTAL_POINTS:
        raise _err(f"{ctx}: too many entries ({len(value)} > "
                   f"{MAX_TOTAL_POINTS})")
    seen = set()
    out = []
    for i, pair in enumerate(value):
        pc = f"{ctx}[{i}]"
        if not isinstance(pair, (list, tuple)) or len(pair) != 2:
            raise _err(f"{pc}: expected a [position, label] pair")
        pos, label = pair
        if not _is_num(pos) or not math.isfinite(pos):
            raise _err(f"{pc}: position must be a finite number, "
                       f"got {pos!r}")
        if pos in seen:
            raise _err(f"{pc}: duplicate position {pos!r}")
        seen.add(pos)
        if not isinstance(label, str) or len(label) > MAX_TICK_LABEL:
            raise _err(f"{pc}: label must be a string of at most "
                       f"{MAX_TICK_LABEL} characters")
        out.append([float(pos), label])
    return out


# ── optional per-element styling ──────────────────────────────────────────
#
# A ``PlotDocument.style`` object holds per-element overrides. Every field
# is emitted only when it differs from its default, so a document without
# styling serializes byte-identically to the pre-style schema. Older builds
# reject styled files (unknown key) — that is the accepted boundary.

_ALIGN = ('left', 'center', 'right')
_TICK_DIRECTIONS = ('out', 'in', 'inout')
_AXIS_SCALES = ('linear', 'log')
_GRID_AXES = ('both', 'x', 'y')
_GRID_WHICH = ('major', 'both')
_GRID_LINESTYLES = tuple(ls for ls in LINESTYLES if ls)

_MAX_STYLE_FAMILY = 100
_MAX_AFFIX = 50


def _style_bool(data: dict, key: str, ctx: str) -> bool:
    v = data.get(key)
    if v is not None and not isinstance(v, bool):
        raise _err(f"{ctx}.{key}: expected true/false, got {v!r}")
    return bool(v)


def _style_str(data: dict, key: str, ctx: str, max_len: int):
    v = data.get(key)
    if v is not None and (not isinstance(v, str) or len(v) > max_len):
        raise _err(f"{ctx}.{key}: expected a string of at most {max_len} "
                   f"characters, got {v!r}")
    return v


def _style_num(data: dict, key: str, ctx: str, lo=None, hi=None,
               lo_exclusive=False):
    v = data.get(key)
    if v is None:
        return None
    if not _is_num(v) or not math.isfinite(v):
        raise _err(f"{ctx}.{key}: expected a finite number, got {v!r}")
    v = float(v)
    if lo is not None and (v <= lo if lo_exclusive else v < lo):
        op = '>' if lo_exclusive else '>='
        raise _err(f"{ctx}.{key}: expected {op} {lo}, got {v}")
    if hi is not None and v > hi:
        raise _err(f"{ctx}.{key}: expected <= {hi}, got {v}")
    return v


def _style_choice(data: dict, key: str, ctx: str, choices):
    v = data.get(key)
    if v is not None and v not in choices:
        raise _err(f"{ctx}.{key}: unsupported {v!r}; one of {choices}")
    return v


def _unknown_style_keys(data: dict, allowed: set, ctx: str):
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _err(f"{ctx}: unknown field(s) {unknown}")


def _style_dict(data, ctx: str) -> dict:
    if not isinstance(data, dict):
        raise _err(f"{ctx}: expected an object, got {type(data).__name__}")
    return data


@dataclass
class TextStyle:
    """Per-text overrides; ``None`` fields inherit document defaults."""
    family: 'str | None' = None
    size_pt: 'float | None' = None
    bold: bool = False
    italic: bool = False
    underline: bool = False
    color: str = '#000000'

    _KEYS = ('family', 'size_pt', 'bold', 'italic', 'underline', 'color')

    def to_dict(self) -> dict:
        d = {}
        if self.family is not None:
            d['family'] = self.family
        if self.size_pt is not None:
            d['size_pt'] = self.size_pt
        if self.bold:
            d['bold'] = True
        if self.italic:
            d['italic'] = True
        if self.underline:
            d['underline'] = True
        if self.color != '#000000':
            d['color'] = self.color
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        s = cls()
        family = _style_str(data, 'family', ctx, _MAX_STYLE_FAMILY)
        if family is not None and not family:
            raise _err(f"{ctx}.family: expected a non-empty string")
        s.family = family
        s.size_pt = _style_num(data, 'size_pt', ctx, lo=0, hi=200,
                               lo_exclusive=True)
        s.bold = _style_bool(data, 'bold', ctx)
        s.italic = _style_bool(data, 'italic', ctx)
        s.underline = _style_bool(data, 'underline', ctx)
        if data.get('color') is not None:
            s.color = _check_color(data['color'], f"{ctx}.color")
        return s


@dataclass
class TitleStyle(TextStyle):
    align: str = 'center'

    _KEYS = TextStyle._KEYS + ('align',)

    def to_dict(self) -> dict:
        d = super().to_dict()
        if self.align != 'center':
            d['align'] = self.align
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        # super() resolves ``cls._KEYS``/``cls()`` as TitleStyle already.
        s = super().from_dict(data, ctx)
        align = _style_choice(data, 'align', ctx, _ALIGN)
        s.align = align or 'center'
        return s


@dataclass
class AxisStyle:
    """Tick/axis presentation for one axis."""
    ticks: 'TextStyle | None' = None
    rotation: float = 0.0
    prefix: str = ''
    suffix: str = ''
    decimals: 'int | None' = None
    step: 'float | None' = None
    minor: bool = False
    direction: str = 'out'
    length_pt: float = 3.5
    scale: str = 'linear'
    reversed: bool = False

    _KEYS = ('ticks', 'rotation', 'prefix', 'suffix', 'decimals', 'step',
             'minor', 'direction', 'length_pt', 'scale', 'reversed')

    def to_dict(self) -> dict:
        d = {}
        if self.ticks is not None:
            td = self.ticks.to_dict()
            if td:
                d['ticks'] = td
        if self.rotation != 0:
            d['rotation'] = self.rotation
        if self.prefix:
            d['prefix'] = self.prefix
        if self.suffix:
            d['suffix'] = self.suffix
        if self.decimals is not None:
            d['decimals'] = self.decimals
        if self.step is not None:
            d['step'] = self.step
        if self.minor:
            d['minor'] = True
        if self.direction != 'out':
            d['direction'] = self.direction
        if self.length_pt != 3.5:
            d['length_pt'] = self.length_pt
        if self.scale != 'linear':
            d['scale'] = self.scale
        if self.reversed:
            d['reversed'] = True
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        s = cls()
        if data.get('ticks') is not None:
            s.ticks = TextStyle.from_dict(data['ticks'], f"{ctx}.ticks")
        rot = _style_num(data, 'rotation', ctx, lo=-90, hi=90)
        s.rotation = rot if rot is not None else 0.0
        s.prefix = _style_str(data, 'prefix', ctx, _MAX_AFFIX) or ''
        s.suffix = _style_str(data, 'suffix', ctx, _MAX_AFFIX) or ''
        dec = data.get('decimals')
        if dec is not None:
            if not isinstance(dec, int) or isinstance(dec, bool) \
                    or not (0 <= dec <= 10):
                raise _err(f"{ctx}.decimals: expected an integer in "
                           f"0..10, got {dec!r}")
            s.decimals = dec
        s.step = _style_num(data, 'step', ctx, lo=0, lo_exclusive=True)
        s.minor = _style_bool(data, 'minor', ctx)
        s.direction = _style_choice(data, 'direction', ctx,
                                    _TICK_DIRECTIONS) or 'out'
        length = _style_num(data, 'length_pt', ctx, lo=0, hi=20)
        s.length_pt = length if length is not None else 3.5
        s.scale = _style_choice(data, 'scale', ctx, _AXIS_SCALES) \
            or 'linear'
        s.reversed = _style_bool(data, 'reversed', ctx)
        return s


@dataclass
class GridStyle:
    axis: str = 'both'
    which: str = 'major'
    color: str = '#b0b0b0'
    linestyle: str = '-'
    linewidth_pt: float = 0.8
    alpha: float = 1.0

    _KEYS = ('axis', 'which', 'color', 'linestyle', 'linewidth_pt',
             'alpha')

    def to_dict(self) -> dict:
        d = {}
        if self.axis != 'both':
            d['axis'] = self.axis
        if self.which != 'major':
            d['which'] = self.which
        if self.color != '#b0b0b0':
            d['color'] = self.color
        if self.linestyle != '-':
            d['linestyle'] = self.linestyle
        if self.linewidth_pt != 0.8:
            d['linewidth_pt'] = self.linewidth_pt
        if self.alpha != 1.0:
            d['alpha'] = self.alpha
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        s = cls()
        s.axis = _style_choice(data, 'axis', ctx, _GRID_AXES) or 'both'
        s.which = _style_choice(data, 'which', ctx, _GRID_WHICH) or 'major'
        if data.get('color') is not None:
            s.color = _check_color(data['color'], f"{ctx}.color")
        ls = _style_choice(data, 'linestyle', ctx, _GRID_LINESTYLES)
        if ls is not None:
            s.linestyle = ls
        lw = _style_num(data, 'linewidth_pt', ctx, lo=0, hi=20,
                        lo_exclusive=True)
        if lw is not None:
            s.linewidth_pt = lw
        alpha = _style_num(data, 'alpha', ctx, lo=0, hi=1)
        if alpha is not None:
            s.alpha = alpha
        return s


@dataclass
class LegendStyle:
    frame: bool = True
    frame_color: str = '#cccccc'
    ncols: int = 1
    text: 'TextStyle | None' = None

    _KEYS = ('frame', 'frame_color', 'ncols', 'text')

    def to_dict(self) -> dict:
        d = {}
        if not self.frame:
            d['frame'] = False
        if self.frame_color != '#cccccc':
            d['frame_color'] = self.frame_color
        if self.ncols != 1:
            d['ncols'] = self.ncols
        if self.text is not None:
            td = self.text.to_dict()
            if td:
                d['text'] = td
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        s = cls()
        if data.get('frame') is not None and not isinstance(
                data['frame'], bool):
            raise _err(f"{ctx}.frame: expected true/false, "
                       f"got {data['frame']!r}")
        if data.get('frame') is not None:
            s.frame = data['frame']
        if data.get('frame_color') is not None:
            s.frame_color = _check_color(data['frame_color'],
                                         f"{ctx}.frame_color")
        n = data.get('ncols')
        if n is not None:
            if not isinstance(n, int) or isinstance(n, bool) \
                    or not (1 <= n <= 10):
                raise _err(f"{ctx}.ncols: expected an integer in 1..10, "
                           f"got {n!r}")
            s.ncols = n
        if data.get('text') is not None:
            s.text = TextStyle.from_dict(data['text'], f"{ctx}.text")
        return s


@dataclass
class FrameStyle:
    color: str = '#000000'
    linewidth_pt: float = 0.8
    hide_top: bool = False
    hide_right: bool = False
    hide_left: bool = False
    hide_bottom: bool = False

    _KEYS = ('color', 'linewidth_pt', 'hide_top', 'hide_right',
             'hide_left', 'hide_bottom')

    def to_dict(self) -> dict:
        d = {}
        if self.color != '#000000':
            d['color'] = self.color
        if self.linewidth_pt != 0.8:
            d['linewidth_pt'] = self.linewidth_pt
        if self.hide_top:
            d['hide_top'] = True
        if self.hide_right:
            d['hide_right'] = True
        if self.hide_left:
            d['hide_left'] = True
        if self.hide_bottom:
            d['hide_bottom'] = True
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        s = cls()
        if data.get('color') is not None:
            s.color = _check_color(data['color'], f"{ctx}.color")
        lw = _style_num(data, 'linewidth_pt', ctx, lo=0, hi=20)
        if lw is not None:
            s.linewidth_pt = lw
        s.hide_top = _style_bool(data, 'hide_top', ctx)
        s.hide_right = _style_bool(data, 'hide_right', ctx)
        s.hide_left = _style_bool(data, 'hide_left', ctx)
        s.hide_bottom = _style_bool(data, 'hide_bottom', ctx)
        return s


# ── kind options ─────────────────────────────────────────────────────
# One options object per kind; emitted only when non-default so files
# without them stay parseable by older builds (unknown fields rejected).

@dataclass
class ViolinOptions:
    show_box: bool = True
    show_points: bool = True
    points_beside: bool = False
    bandwidth: object = 'scott'      # 'scott' | 'silverman' | float > 0
    fill_alpha: float = 0.3
    edge_color: 'str | None' = None  # absent → the group's colour
    edge_width_pt: float = 1.0       # 0 → no border
    point_size_pt: float = 6.0      # marker diameter ≡ scatter s=12
    point_alpha: float = 1.0
    point_edge_color: 'str | None' = None  # absent → the point colour
    point_edge_width_pt: float = 1.0       # 0 → no outline
    enhance_contrast: bool = False

    _KEYS = ('show_box', 'show_points', 'points_beside', 'bandwidth',
             'fill_alpha', 'edge_color', 'edge_width_pt',
             'point_size_pt', 'point_alpha', 'point_edge_color',
             'point_edge_width_pt', 'enhance_contrast')

    def to_dict(self) -> dict:
        d = {}
        if not self.show_box:
            d['show_box'] = False
        if not self.show_points:
            d['show_points'] = False
        if self.points_beside:
            d['points_beside'] = True
        if self.bandwidth != 'scott':
            d['bandwidth'] = self.bandwidth
        if self.fill_alpha != 0.3:
            d['fill_alpha'] = self.fill_alpha
        if self.edge_color is not None:
            d['edge_color'] = self.edge_color
        if self.edge_width_pt != 1.0:
            d['edge_width_pt'] = self.edge_width_pt
        if self.point_size_pt != 6.0:
            d['point_size_pt'] = self.point_size_pt
        if self.point_alpha != 1.0:
            d['point_alpha'] = self.point_alpha
        if self.point_edge_color is not None:
            d['point_edge_color'] = self.point_edge_color
        if self.point_edge_width_pt != 1.0:
            d['point_edge_width_pt'] = self.point_edge_width_pt
        if self.enhance_contrast:
            d['enhance_contrast'] = True
        return d

    @classmethod
    def from_dict(cls, data, ctx='document.violin'):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        o = cls()
        for key in ('show_box', 'show_points', 'points_beside',
                    'enhance_contrast'):
            v = data.get(key)
            if v is not None:
                if not isinstance(v, bool):
                    raise _err(f"{ctx}.{key}: expected true/false, "
                               f"got {v!r}")
                setattr(o, key, v)
        bw = data.get('bandwidth')
        if bw is not None:
            if isinstance(bw, str):
                if bw not in _BANDWIDTHS:
                    raise _err(f"{ctx}.bandwidth: unsupported {bw!r}")
                o.bandwidth = bw
            elif _is_num(bw) and math.isfinite(bw) and bw > 0:
                o.bandwidth = float(bw)
            else:
                raise _err(f"{ctx}.bandwidth: expected scott/silverman "
                           f"or a positive finite number, got {bw!r}")
        v = _style_num(data, 'fill_alpha', ctx, lo=0, hi=1)
        if v is not None:
            o.fill_alpha = v
        if data.get('edge_color') is not None:
            o.edge_color = _check_color(data['edge_color'],
                                        f"{ctx}.edge_color")
        v = _style_num(data, 'edge_width_pt', ctx, lo=0, hi=10)
        if v is not None:
            o.edge_width_pt = v
        v = _style_num(data, 'point_size_pt', ctx, lo=0, hi=20)
        if v is not None:
            o.point_size_pt = v
        v = _style_num(data, 'point_alpha', ctx, lo=0, hi=1)
        if v is not None:
            o.point_alpha = v
        if data.get('point_edge_color') is not None:
            o.point_edge_color = _check_color(
                data['point_edge_color'], f"{ctx}.point_edge_color")
        v = _style_num(data, 'point_edge_width_pt', ctx, lo=0, hi=10)
        if v is not None:
            o.point_edge_width_pt = v
        return o


@dataclass
class RidgeOptions:
    offset: 'float | None' = None    # absent → max series range × 1.05
    fill_alpha: float = 0.22
    reverse: bool = False
    baseline_color: str = '#444444'
    baseline_width_pt: float = 0.6
    labels: bool = True

    _KEYS = ('offset', 'fill_alpha', 'reverse', 'baseline_color',
             'baseline_width_pt', 'labels')

    def to_dict(self) -> dict:
        d = {}
        if self.offset is not None:
            d['offset'] = self.offset
        if self.fill_alpha != 0.22:
            d['fill_alpha'] = self.fill_alpha
        if self.reverse:
            d['reverse'] = True
        if self.baseline_color != '#444444':
            d['baseline_color'] = self.baseline_color
        if self.baseline_width_pt != 0.6:
            d['baseline_width_pt'] = self.baseline_width_pt
        if not self.labels:
            d['labels'] = False
        return d

    @classmethod
    def from_dict(cls, data, ctx='document.ridgeline'):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        o = cls()
        o.offset = _style_num(data, 'offset', ctx, lo=0,
                              lo_exclusive=True)
        v = _style_num(data, 'fill_alpha', ctx, lo=0, hi=1)
        if v is not None:
            o.fill_alpha = v
        o.reverse = _style_bool(data, 'reverse', ctx)
        if data.get('baseline_color') is not None:
            o.baseline_color = _check_color(data['baseline_color'],
                                            f"{ctx}.baseline_color")
        v = _style_num(data, 'baseline_width_pt', ctx, lo=0, hi=10)
        if v is not None:
            o.baseline_width_pt = v
        if data.get('labels') is not None:
            if not isinstance(data['labels'], bool):
                raise _err(f"{ctx}.labels: expected true/false, "
                           f"got {data['labels']!r}")
            o.labels = data['labels']
        return o


@dataclass
class StackOptions:
    percent: bool = True
    grouped: bool = False        # side-by-side columns, not stacked
    bar_width: float = 0.8
    show_values: bool = False
    value_threshold: float = 5.0
    value_decimals: int = 1
    value_color: str = '#ffffff'
    value_bold: bool = True
    value_size_pt: 'float | None' = None  # absent → font_size_pt × 6/7
    edge_color: str = '#ffffff'
    edge_width_pt: float = 0.0

    _KEYS = ('percent', 'grouped', 'bar_width', 'show_values',
             'value_threshold', 'value_decimals', 'value_color',
             'value_bold', 'value_size_pt', 'edge_color',
             'edge_width_pt')

    def to_dict(self) -> dict:
        d = {}
        if not self.percent:
            d['percent'] = False
        if self.grouped:
            d['grouped'] = True
        if self.bar_width != 0.8:
            d['bar_width'] = self.bar_width
        if self.show_values:
            d['show_values'] = True
        if self.value_threshold != 5.0:
            d['value_threshold'] = self.value_threshold
        if self.value_decimals != 1:
            d['value_decimals'] = self.value_decimals
        if self.value_color != '#ffffff':
            d['value_color'] = self.value_color
        if not self.value_bold:
            d['value_bold'] = False
        if self.value_size_pt is not None:
            d['value_size_pt'] = self.value_size_pt
        if self.edge_color != '#ffffff':
            d['edge_color'] = self.edge_color
        if self.edge_width_pt != 0.0:
            d['edge_width_pt'] = self.edge_width_pt
        return d

    @classmethod
    def from_dict(cls, data, ctx='document.stacked'):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        o = cls()
        for key in ('percent', 'grouped', 'show_values', 'value_bold'):
            v = data.get(key)
            if v is not None:
                if not isinstance(v, bool):
                    raise _err(f"{ctx}.{key}: expected true/false, "
                               f"got {v!r}")
                setattr(o, key, v)
        if o.grouped and o.percent:
            raise _err(f"{ctx}: grouped columns cannot be "
                       "percent-stacked")
        v = _style_num(data, 'bar_width', ctx, lo=0, hi=1,
                       lo_exclusive=True)
        if v is not None:
            o.bar_width = v
        v = _style_num(data, 'value_threshold', ctx, lo=0, hi=100)
        if v is not None:
            o.value_threshold = v
        dec = data.get('value_decimals')
        if dec is not None:
            if not isinstance(dec, int) or isinstance(dec, bool) \
                    or not (0 <= dec <= 4):
                raise _err(f"{ctx}.value_decimals: expected an integer "
                           f"in 0..4, got {dec!r}")
            o.value_decimals = dec
        for key in ('value_color', 'edge_color'):
            if data.get(key) is not None:
                setattr(o, key, _check_color(data[key],
                                             f"{ctx}.{key}"))
        v = _style_num(data, 'value_size_pt', ctx, lo=0, hi=200,
                       lo_exclusive=True)
        if v is not None:
            o.value_size_pt = v
        v = _style_num(data, 'edge_width_pt', ctx, lo=0, hi=10)
        if v is not None:
            o.edge_width_pt = v
        return o


# ── annotations / brackets ──────────────────────────────────────────

@dataclass
class Annotation:
    """A text note placed in axes coordinates (NCPlot's ``ur_note``).

    When ``x``/``y`` are both set (axes fractions, -0.5..1.5), the note
    is a floating centred text at that point and ``anchor`` is ignored;
    otherwise the corner-anchored behaviour applies.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    text: str = ''
    anchor: str = 'upper right'
    style: 'TextStyle | None' = None
    box: bool = False
    x: 'float | None' = None
    y: 'float | None' = None

    _KEYS = ('id', 'text', 'anchor', 'style', 'box', 'x', 'y')

    def to_dict(self) -> dict:
        d = {'id': self.id, 'text': self.text, 'anchor': self.anchor}
        if self.style is not None:
            sd = self.style.to_dict()
            if sd:
                d['style'] = sd
        if self.box:
            d['box'] = True
        if self.x is not None:
            d['x'] = self.x
            d['y'] = self.y
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        a = cls()
        sid = data.get('id')
        if not isinstance(sid, str) or not sid:
            raise _err(f"{ctx}.id: expected a non-empty string")
        a.id = sid
        text = data.get('text')
        if not isinstance(text, str) or not (1 <= len(text) <= 500):
            raise _err(f"{ctx}.text: expected 1..500 characters")
        a.text = text
        anchor = data.get('anchor')
        if anchor not in _ANCHORS:
            raise _err(f"{ctx}.anchor: unsupported {anchor!r}")
        a.anchor = anchor
        if data.get('style') is not None:
            a.style = TextStyle.from_dict(data['style'], f"{ctx}.style")
        a.box = _style_bool(data, 'box', ctx)
        x, y = data.get('x'), data.get('y')
        if (x is None) != (y is None):
            raise _err(f"{ctx}: x and y must appear together")
        if x is not None:
            for key, v in (('x', x), ('y', y)):
                if not _is_num(v) or not math.isfinite(v) \
                        or not (-0.5 <= v <= 1.5):
                    raise _err(f"{ctx}.{key}: expected a finite number "
                               f"in [-0.5, 1.5], got {v!r}")
            a.x, a.y = float(x), float(y)
        return a


@dataclass
class Bracket:
    """A significance bracket between two positions (NCPlot style).

    ``a``/``b`` are group/bar indices (int ≥ 0) for violin and
    stacked_column, or x positions (finite floats) for line/ridgeline.
    """
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    a: float = 0.0
    b: float = 0.0
    text: str = '*'
    offset: float = 0.05
    style: 'TextStyle | None' = None

    _KEYS = ('id', 'a', 'b', 'text', 'offset', 'style')

    def to_dict(self) -> dict:
        d = {'id': self.id, 'a': self.a, 'b': self.b,
             'text': self.text}
        if self.offset != 0.05:
            d['offset'] = self.offset
        if self.style is not None:
            sd = self.style.to_dict()
            if sd:
                d['style'] = sd
        return d

    @classmethod
    def from_dict(cls, data, ctx):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        br = cls()
        sid = data.get('id')
        if not isinstance(sid, str) or not sid:
            raise _err(f"{ctx}.id: expected a non-empty string")
        br.id = sid
        for key in ('a', 'b'):
            v = data.get(key)
            if not _is_num(v) or not math.isfinite(v) or v < 0:
                raise _err(f"{ctx}.{key}: expected a finite number "
                           f">= 0, got {v!r}")
            setattr(br, key, float(v))
        if br.a == br.b:
            raise _err(f"{ctx}: a and b must differ")
        text = data.get('text', '*')
        if not isinstance(text, str) or len(text) > 50:
            raise _err(f"{ctx}.text: expected a string of at most 50 "
                       f"characters")
        br.text = text
        v = _style_num(data, 'offset', ctx, lo=0, hi=1)
        if v is not None:
            br.offset = v
        if data.get('style') is not None:
            br.style = TextStyle.from_dict(data['style'],
                                           f"{ctx}.style")
        return br


# ── kind data ─────────────────────────────────────────────────────────

@dataclass
class ViolinGroup:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    label: str = 'Group 1'
    values: list = field(default_factory=lambda: [0., 1., 2.])
    color: str = '#0891b2'

    def to_dict(self) -> dict:
        return {'id': self.id, 'label': self.label,
                'values': [float(v) for v in self.values],
                'color': self.color}

    @classmethod
    def from_dict(cls, data, ctx: str) -> 'ViolinGroup':
        if not isinstance(data, dict):
            raise _err(f"{ctx}: expected an object, got "
                       f"{type(data).__name__}")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise _err(f"{ctx}: unknown field(s) {unknown} — file may "
                       "need a newer version")
        g = cls()
        sid = data.get('id')
        if not isinstance(sid, str) or not sid:
            raise _err(f"{ctx}.id: expected a non-empty string")
        g.id = sid
        g.label = _req_str(data, 'label', ctx)
        values = data.get('values')
        if not isinstance(values, list) or not values:
            raise _err(f"{ctx}.values: expected a non-empty array of "
                       "numbers")
        if any(not _is_num(v) or not math.isfinite(v) for v in values):
            raise _err(f"{ctx}.values: all values must be finite "
                       "numbers")
        g.values = [float(v) for v in values]
        g.color = _check_color(data.get('color'), f"{ctx}.color")
        return g


@dataclass
class StackCategory:
    """One stack segment series: ``values[i]`` is its height in bar i."""
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    label: str = 'Category 1'
    values: list = field(default_factory=lambda: [1.])
    color: str = '#0891b2'
    yerr: list | None = None
    yerr_minus: list | None = None
    yerr_plus: list | None = None

    def to_dict(self) -> dict:
        d = {'id': self.id, 'label': self.label,
             'values': [float(v) for v in self.values],
             'color': self.color}
        if self.yerr is not None:
            d['yerr'] = [float(v) for v in self.yerr]
        if self.yerr_minus is not None:
            d['yerr_minus'] = [float(v) for v in self.yerr_minus]
        if self.yerr_plus is not None:
            d['yerr_plus'] = [float(v) for v in self.yerr_plus]
        return d

    @classmethod
    def from_dict(cls, data, ctx: str) -> 'StackCategory':
        if not isinstance(data, dict):
            raise _err(f"{ctx}: expected an object, got "
                       f"{type(data).__name__}")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise _err(f"{ctx}: unknown field(s) {unknown} — file may "
                       "need a newer version")
        c = cls()
        sid = data.get('id')
        if not isinstance(sid, str) or not sid:
            raise _err(f"{ctx}.id: expected a non-empty string")
        c.id = sid
        c.label = _req_str(data, 'label', ctx)
        values = data.get('values')
        if not isinstance(values, list) or not values:
            raise _err(f"{ctx}.values: expected a non-empty array of "
                       "numbers")
        if any(not _is_num(v) or not math.isfinite(v) or v < 0
               for v in values):
            raise _err(f"{ctx}.values: all values must be finite "
                       "numbers >= 0")
        c.values = [float(v) for v in values]
        c.color = _check_color(data.get('color'), f"{ctx}.color")
        c.yerr = _check_yerr(data.get('yerr'), len(c.values),
                             f"{ctx}.yerr")
        c.yerr_minus = _check_yerr(data.get('yerr_minus'),
                                   len(c.values), f"{ctx}.yerr_minus")
        c.yerr_plus = _check_yerr(data.get('yerr_plus'),
                                  len(c.values), f"{ctx}.yerr_plus")
        _check_yerr_pair(c.yerr, c.yerr_minus, c.yerr_plus, ctx)
        return c


@dataclass
class PlotStyle:
    """Optional per-element styling; empty means "everything default"."""
    title: 'TitleStyle | None' = None
    xlabel: 'TextStyle | None' = None
    ylabel: 'TextStyle | None' = None
    xaxis: 'AxisStyle | None' = None
    yaxis: 'AxisStyle | None' = None
    grid: 'GridStyle | None' = None
    legend: 'LegendStyle | None' = None
    frame: 'FrameStyle | None' = None

    _KEYS = ('title', 'xlabel', 'ylabel', 'xaxis', 'yaxis', 'grid',
             'legend', 'frame')
    _TYPES = {'title': TitleStyle, 'xlabel': TextStyle,
              'ylabel': TextStyle, 'xaxis': AxisStyle, 'yaxis': AxisStyle,
              'grid': GridStyle, 'legend': LegendStyle,
              'frame': FrameStyle}

    def to_dict(self) -> dict:
        d = {}
        for name in self._KEYS:
            sub = getattr(self, name)
            if sub is not None:
                sd = sub.to_dict()
                if sd:
                    d[name] = sd
        return d

    @classmethod
    def from_dict(cls, data, ctx='document.style'):
        data = _style_dict(data, ctx)
        _unknown_style_keys(data, set(cls._KEYS), ctx)
        s = cls()
        for name, typ in cls._TYPES.items():
            v = data.get(name)
            if v is not None:
                setattr(s, name, typ.from_dict(v, f"{ctx}.{name}"))
        return s


@dataclass
class LineSeries:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    label: str = 'Series 1'
    x: list = field(default_factory=lambda: [0., 1., 2., 3.])
    y: list = field(default_factory=lambda: [0., 1., .5, 1.5])
    color: str = '#0891b2'
    linewidth_pt: float = 1.5
    linestyle: str = '-'
    marker: str = ''
    markersize_pt: float = 6.
    yerr: list | None = None
    yerr_minus: list | None = None
    yerr_plus: list | None = None

    def to_dict(self) -> dict:
        d = {
            'id': self.id, 'label': self.label,
            'x': list(self.x), 'y': list(self.y),
            'color': self.color, 'linewidth_pt': self.linewidth_pt,
            'linestyle': self.linestyle, 'marker': self.marker,
            'markersize_pt': self.markersize_pt,
        }
        if self.yerr is not None:
            d['yerr'] = [float(v) for v in self.yerr]
        if self.yerr_minus is not None:
            d['yerr_minus'] = [float(v) for v in self.yerr_minus]
        if self.yerr_plus is not None:
            d['yerr_plus'] = [float(v) for v in self.yerr_plus]
        return d

    @classmethod
    def from_dict(cls, data, ctx: str = 'series') -> 'LineSeries':
        if not isinstance(data, dict):
            raise _err(f"{ctx}: expected an object, got {type(data).__name__}")
        allowed = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise _err(f"{ctx}: unknown field(s) {unknown} — file may need a newer version")
        s = cls()
        sid = data.get('id')
        if not isinstance(sid, str) or not sid:
            raise _err(f"{ctx}.id: expected a non-empty string")
        s.id = sid
        s.label = _req_str(data, 'label', ctx)
        x, y = data.get('x'), data.get('y')
        for name, arr in (('x', x), ('y', y)):
            if not isinstance(arr, list) or not arr:
                raise _err(f"{ctx}.{name}: expected a non-empty array of numbers")
            if any(not _is_num(v) or not math.isfinite(v) for v in arr):
                raise _err(f"{ctx}.{name}: all values must be finite numbers")
        if len(x) != len(y):
            raise _err(f"{ctx}: x and y must have the same length "
                       f"({len(x)} != {len(y)})")
        s.x = [float(v) for v in x]
        s.y = [float(v) for v in y]
        s.color = _check_color(data.get('color'), f"{ctx}.color")
        s.linewidth_pt = _req_number(data, 'linewidth_pt', ctx,
                                     lo=0, hi=200, lo_exclusive=True)
        ls = data.get('linestyle')
        if ls not in LINESTYLES:
            raise _err(f"{ctx}.linestyle: unsupported {ls!r}; one of {LINESTYLES}")
        s.linestyle = ls
        mk = data.get('marker')
        if mk not in MARKERS:
            raise _err(f"{ctx}.marker: unsupported {mk!r}; one of {MARKERS}")
        s.marker = mk
        s.markersize_pt = _req_number(data, 'markersize_pt', ctx,
                                      lo=0, hi=200)
        s.yerr = _check_yerr(data.get('yerr'), len(s.y),
                             f"{ctx}.yerr")
        s.yerr_minus = _check_yerr(data.get('yerr_minus'), len(s.y),
                                   f"{ctx}.yerr_minus")
        s.yerr_plus = _check_yerr(data.get('yerr_plus'), len(s.y),
                                  f"{ctx}.yerr_plus")
        _check_yerr_pair(s.yerr, s.yerr_minus, s.yerr_plus, ctx)
        return s


@dataclass
class PlotDocument:
    schema_version: int = SCHEMA_VERSION
    kind: str = 'line'
    width_mm: float = 90.
    height_mm: float = 65.
    # normalized left, bottom, width, height (matplotlib add_axes rect)
    axes_rect: list = field(default_factory=lambda: [.18, .18, .76, .72])
    title: str = ''
    xlabel: str = 'X'
    ylabel: str = 'Y'
    font_family: str = 'DejaVu Sans'
    font_size_pt: float = 10.
    title_size_pt: float = 12.
    xlim: list | None = None
    ylim: list | None = None
    # Optional categorical x axis: [[position, label], ...]; None = numeric.
    x_tick_labels: list | None = None
    legend: bool = True
    legend_location: str = 'best'
    grid: bool = False
    series: list = field(default_factory=lambda: [LineSeries()])
    # 'violin' data; 'stacked_column' data; per-kind option objects.
    groups: list = field(default_factory=list)
    categories: list = field(default_factory=list)
    violin: 'ViolinOptions | None' = None
    ridgeline: 'RidgeOptions | None' = None
    stacked: 'StackOptions | None' = None
    annotations: list = field(default_factory=list)
    brackets: list = field(default_factory=list)
    style: 'PlotStyle' = field(default_factory=lambda: PlotStyle())
    # Optional-feature ids this document needs a reader to understand
    # (see CAPABILITIES); emitted only when non-empty.
    requires: list = field(default_factory=list)

    # ── validation ──────────────────────────────────────────────────
    def validate(self) -> 'PlotDocument':
        ctx = 'document'
        if not isinstance(self.schema_version, int) \
                or isinstance(self.schema_version, bool):
            raise _err(f"{ctx}.schema_version: expected an integer, got "
                       f"{self.schema_version!r}")
        if self.schema_version != SCHEMA_VERSION:
            raise _err(f"{ctx}.schema_version: unsupported {self.schema_version!r} "
                       f"(this version supports {SCHEMA_VERSION})")
        if self.kind not in KINDS:
            raise _err(f"{ctx}.kind: unsupported {self.kind!r} "
                       f"(one of {KINDS})")
        for name in ('width_mm', 'height_mm'):
            v = getattr(self, name)
            if not _is_num(v) or not math.isfinite(v) \
                    or v <= 0 or v > MAX_DIMENSION_MM:
                raise _err(f"{ctx}.{name}: expected 0 < value <= "
                           f"{MAX_DIMENSION_MM} mm, got {v!r}")
        rect = self.axes_rect
        if (not isinstance(rect, (list, tuple)) or len(rect) != 4
                or any(not _is_num(v) or not math.isfinite(v) for v in rect)):
            raise _err(f"{ctx}.axes_rect: expected [left, bottom, width, height] "
                       f"of finite numbers in 0..1")
        l, b, w, h = (float(v) for v in rect)
        if not (0.0 <= l < 1.0 and 0.0 <= b < 1.0 and 0.0 < w <= 1.0
                and 0.0 < h <= 1.0 and l + w <= 1.0 and b + h <= 1.0):
            raise _err(f"{ctx}.axes_rect: {list(rect)} is outside the figure bounds")
        for name in ('title', 'xlabel', 'ylabel', 'font_family'):
            if not isinstance(getattr(self, name), str):
                raise _err(f"{ctx}.{name}: expected a string")
        if not self.font_family:
            raise _err(f"{ctx}.font_family: expected a non-empty string")
        for name in ('font_size_pt', 'title_size_pt'):
            v = getattr(self, name)
            if not _is_num(v) or not math.isfinite(v) or v <= 0 or v > 200:
                raise _err(f"{ctx}.{name}: expected 0 < value <= 200, got {v!r}")
        self.xlim = _check_limit(self.xlim, f"{ctx}.xlim")
        self.ylim = _check_limit(self.ylim, f"{ctx}.ylim")
        self.x_tick_labels = _check_tick_labels(
            self.x_tick_labels, f"{ctx}.x_tick_labels")
        if not isinstance(self.legend, bool) or not isinstance(self.grid, bool):
            raise _err(f"{ctx}.legend/grid: expected true/false")
        if self.legend_location not in LEGEND_LOCATIONS:
            raise _err(f"{ctx}.legend_location: unsupported "
                       f"{self.legend_location!r}")
        if self.kind in ('line', 'ridgeline'):
            if not isinstance(self.series, list) or not self.series:
                raise _err(f"{ctx}.series: at least one series is "
                           "required")
            for coll, coll_name in ((self.groups, 'groups'),
                                    (self.categories, 'categories')):
                if coll:
                    raise _err(f"{ctx}.{coll_name}: must be empty for "
                               f"kind {self.kind!r}")
            blocked = ('violin', 'stacked') if self.kind == 'ridgeline' \
                else ('violin', 'stacked', 'ridgeline')
            owners = {'violin': 'violin', 'stacked': 'stacked_column',
                      'ridgeline': 'ridgeline'}
            for name in blocked:
                if getattr(self, name) is not None:
                    raise _err(f"{ctx}.{name}: options only apply to "
                               f"kind {owners[name]!r}")
        else:
            if self.series:
                raise _err(f"{ctx}.series: must be empty for kind "
                           f"{self.kind!r}")
            if self.ridgeline is not None:
                raise _err(f"{ctx}.ridgeline: options only apply to "
                           "kind 'ridgeline'")
        if self.kind == 'violin':
            if not self.groups:
                raise _err(f"{ctx}.groups: at least one group is "
                           "required")
            if self.stacked is not None:
                raise _err(f"{ctx}.stacked: options only apply to "
                           "kind 'stacked_column'")
        if self.kind == 'stacked_column':
            if not self.categories:
                raise _err(f"{ctx}.categories: at least one category "
                           "is required")
            if self.stacked is not None and self.stacked.grouped \
                    and self.stacked.percent:
                raise _err(f"{ctx}.stacked: grouped columns cannot be "
                           "percent-stacked")
            if self.violin is not None:
                raise _err(f"{ctx}.violin: options only apply to "
                           "kind 'violin'")
        if len(self.series) > MAX_SERIES:
            raise _err(f"{ctx}.series: at most {MAX_SERIES} series")
        if len(self.groups) > MAX_SERIES:
            raise _err(f"{ctx}.groups: at most {MAX_SERIES} groups")
        if len(self.categories) > MAX_SERIES:
            raise _err(f"{ctx}.categories: at most {MAX_SERIES} "
                       "categories")
        ids = set()
        total = 0
        for i, s in enumerate(self.series):
            if not isinstance(s, LineSeries):
                raise _err(f"{ctx}.series[{i}]: not a LineSeries")
            LineSeries.from_dict(s.to_dict(), ctx=f"series[{i}]")
            if s.id in ids:
                raise _err(f"{ctx}.series[{i}]: duplicate id {s.id!r}")
            ids.add(s.id)
            total += len(s.x)
        for i, g in enumerate(self.groups):
            if not isinstance(g, ViolinGroup):
                raise _err(f"{ctx}.groups[{i}]: not a ViolinGroup")
            ViolinGroup.from_dict(g.to_dict(), ctx=f"groups[{i}]")
            if g.id in ids:
                raise _err(f"{ctx}.groups[{i}]: duplicate id {g.id!r}")
            ids.add(g.id)
            total += len(g.values)
        n_bars = None
        for i, c in enumerate(self.categories):
            if not isinstance(c, StackCategory):
                raise _err(f"{ctx}.categories[{i}]: not a "
                           "StackCategory")
            StackCategory.from_dict(c.to_dict(),
                                    ctx=f"categories[{i}]")
            if c.id in ids:
                raise _err(f"{ctx}.categories[{i}]: duplicate id "
                           f"{c.id!r}")
            ids.add(c.id)
            total += len(c.values)
            if n_bars is None:
                n_bars = len(c.values)
            elif len(c.values) != n_bars:
                raise _err(f"{ctx}.categories[{i}].values: expected "
                           f"{n_bars} values (all categories must "
                           "have the same length)")
        if self.kind == 'stacked_column' and n_bars is not None \
                and self.x_tick_labels is not None:
            positions = sorted(p for p, _l in self.x_tick_labels)
            if positions != [float(i) for i in range(n_bars)]:
                raise _err(f"{ctx}.x_tick_labels: expected exactly "
                           f"{n_bars} entries at positions 0.."
                           f"{n_bars - 1}")
        if total > MAX_TOTAL_POINTS:
            raise _err(f"{ctx}: too many data points ({total} > {MAX_TOTAL_POINTS})")
        for name in ('violin', 'ridgeline', 'stacked'):
            opt = getattr(self, name)
            if opt is not None:
                typ = {'violin': ViolinOptions,
                       'ridgeline': RidgeOptions,
                       'stacked': StackOptions}[name]
                if not isinstance(opt, typ):
                    raise _err(f"{ctx}.{name}: expected {typ.__name__}"
                               f" or None")
                typ.from_dict(opt.to_dict(), f"{ctx}.{name}")
        for coll, coll_name, typ, limit in (
                (self.annotations, 'annotations', Annotation,
                 MAX_ANNOTATIONS),
                (self.brackets, 'brackets', Bracket, MAX_BRACKETS)):
            if not isinstance(coll, list) or len(coll) > limit:
                raise _err(f"{ctx}.{coll_name}: expected a list of at "
                           f"most {limit} entries")
            aids = set()
            for i, a in enumerate(coll):
                if not isinstance(a, typ):
                    raise _err(f"{ctx}.{coll_name}[{i}]: not a "
                               f"{typ.__name__}")
                typ.from_dict(a.to_dict(), ctx=f"{coll_name}[{i}]")
                if a.id in aids:
                    raise _err(f"{ctx}.{coll_name}[{i}]: duplicate id "
                               f"{a.id!r}")
                aids.add(a.id)
        for i, br in enumerate(self.brackets):
            index_kind = self.kind in ('violin', 'stacked_column')
            for key in ('a', 'b'):
                v = getattr(br, key)
                if index_kind and not float(v).is_integer():
                    raise _err(f"{ctx}.brackets[{i}].{key}: expected "
                               f"a group/bar index, got {v}")
                if index_kind:
                    count = len(self.groups) if self.kind == 'violin' \
                        else n_bars
                    if count is not None and v >= count:
                        raise _err(f"{ctx}.brackets[{i}].{key}: index "
                                   f"{int(v)} >= {count} items")
        if not isinstance(self.style, PlotStyle):
            raise _err(f"{ctx}.style: not a PlotStyle")
        # Round-trip validates every emitted key/value strictly.
        PlotStyle.from_dict(self.style.to_dict())
        return self

    # ── serialization ───────────────────────────────────────────────
    def to_dict(self) -> dict:
        d = {
            'format': FORMAT_NAME,
            'schema_version': self.schema_version,
            'kind': self.kind,
            'width_mm': self.width_mm,
            'height_mm': self.height_mm,
            'axes_rect': list(self.axes_rect),
            'title': self.title,
            'xlabel': self.xlabel,
            'ylabel': self.ylabel,
            'font_family': self.font_family,
            'font_size_pt': self.font_size_pt,
            'title_size_pt': self.title_size_pt,
            'xlim': list(self.xlim) if self.xlim is not None else None,
            'ylim': list(self.ylim) if self.ylim is not None else None,
            'legend': self.legend,
            'legend_location': self.legend_location,
            'grid': self.grid,
            'series': [s.to_dict() for s in self.series],
        }
        # Optional field: emit only when set so files without it stay
        # byte-identical and parseable by older builds (unknown fields
        # are rejected by from_dict).
        if self.x_tick_labels is not None:
            d['x_tick_labels'] = [[p, l] for p, l in self.x_tick_labels]
        if self.groups:
            d['groups'] = [g.to_dict() for g in self.groups]
        if self.categories:
            d['categories'] = [c.to_dict() for c in self.categories]
        for name in ('violin', 'ridgeline', 'stacked'):
            opt = getattr(self, name)
            if opt is not None:
                od = opt.to_dict()
                if od:
                    d[name] = od
                else:
                    # An all-default options object still pins the kind's
                    # rendering defaults when present.
                    d[name] = {}
        if self.annotations:
            d['annotations'] = [a.to_dict() for a in self.annotations]
        if self.brackets:
            d['brackets'] = [b.to_dict() for b in self.brackets]
        style = self.style.to_dict() if self.style is not None else {}
        if style:
            d['style'] = style
        req = required_capabilities(self)
        if req:
            d['requires'] = req
        return d

    @classmethod
    def from_dict(cls, data) -> 'PlotDocument':
        if not isinstance(data, dict):
            raise _err(f"plot document: expected a JSON object, got "
                       f"{type(data).__name__}")
        if data.get('format') != FORMAT_NAME:
            raise _err(f"plot document: missing or wrong 'format' "
                       f"(expected {FORMAT_NAME!r}, got {data.get('format')!r})")
        d = cls()
        sv = data.get('schema_version')
        if not isinstance(sv, int) or isinstance(sv, bool):
            raise _err(f"document.schema_version: expected an integer, got {sv!r}")
        d.schema_version = sv
        if sv > SCHEMA_VERSION:
            from .i18n import tr
            raise PlotVersionError(
                tr('err_plot_newer_schema', found=sv,
                   supported=SCHEMA_VERSION),
                schema_version=sv)
        d.requires = _check_requires(data.get('requires'),
                                     'document.requires')
        missing = sorted(set(d.requires) - CAPABILITIES)
        if missing:
            from .i18n import tr
            raise PlotVersionError(
                tr('err_plot_newer_features',
                   features=', '.join(missing)),
                schema_version=sv, missing=missing)
        allowed = {f.name for f in fields(cls)} | {'format'}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise _err(f"plot document: unknown field(s) {unknown} — "
                       f"file may need a newer version of the editor")
        kind = data.get('kind')
        if kind not in KINDS:
            raise _err(f"document.kind: unsupported {kind!r}")
        d.kind = kind
        d.width_mm = _req_number(data, 'width_mm', 'document',
                                 lo=0, hi=MAX_DIMENSION_MM, lo_exclusive=True)
        d.height_mm = _req_number(data, 'height_mm', 'document',
                                  lo=0, hi=MAX_DIMENSION_MM, lo_exclusive=True)
        rect = data.get('axes_rect')
        if not isinstance(rect, list) or len(rect) != 4 \
                or any(not _is_num(v) or not math.isfinite(v) for v in rect):
            raise _err("document.axes_rect: expected [left, bottom, width, height]")
        d.axes_rect = [float(v) for v in rect]
        d.title = _req_str(data, 'title', 'document')
        d.xlabel = _req_str(data, 'xlabel', 'document')
        d.ylabel = _req_str(data, 'ylabel', 'document')
        d.font_family = _req_str(data, 'font_family', 'document', allow_empty=False)
        d.font_size_pt = _req_number(data, 'font_size_pt', 'document',
                                     lo=0, hi=200, lo_exclusive=True)
        d.title_size_pt = _req_number(data, 'title_size_pt', 'document',
                                      lo=0, hi=200, lo_exclusive=True)
        d.xlim = _check_limit(data.get('xlim'), 'document.xlim')
        d.ylim = _check_limit(data.get('ylim'), 'document.ylim')
        d.x_tick_labels = _check_tick_labels(
            data.get('x_tick_labels'), 'document.x_tick_labels')
        d.legend = _req_bool(data, 'legend', 'document')
        loc = data.get('legend_location')
        if loc not in LEGEND_LOCATIONS:
            raise _err(f"document.legend_location: unsupported {loc!r}")
        d.legend_location = loc
        d.grid = _req_bool(data, 'grid', 'document')
        series = data.get('series')
        if not isinstance(series, list) or (not series
                                           and d.kind in ('line',
                                                          'ridgeline')):
            raise _err("document.series: expected a non-empty array")
        d.series = [LineSeries.from_dict(s, ctx=f"series[{i}]")
                    for i, s in enumerate(series)]
        for name, typ in (('groups', ViolinGroup),
                          ('categories', StackCategory)):
            coll = data.get(name)
            if coll is not None:
                if not isinstance(coll, list):
                    raise _err(f"document.{name}: expected an array")
                setattr(d, name, [typ.from_dict(
                    v, ctx=f"{name}[{i}]") for i, v in enumerate(coll)])
        for name, typ in (('violin', ViolinOptions),
                          ('ridgeline', RidgeOptions),
                          ('stacked', StackOptions)):
            opt = data.get(name)
            if opt is not None:
                setattr(d, name,
                        typ.from_dict(opt, f'document.{name}'))
        for name, typ in (('annotations', Annotation),
                          ('brackets', Bracket)):
            coll = data.get(name)
            if coll is not None:
                if not isinstance(coll, list):
                    raise _err(f"document.{name}: expected an array")
                setattr(d, name, [typ.from_dict(
                    v, ctx=f"{name}[{i}]") for i, v in enumerate(coll)])
        style = data.get('style')
        if style is not None:
            d.style = PlotStyle.from_dict(style)
        return d.validate()

    def clone(self) -> 'PlotDocument':
        return copy.deepcopy(self)


# ── SVG embedding / extraction ────────────────────────────────────────────

def embed_metadata(svg_bytes: bytes, document: PlotDocument) -> bytes:
    """Insert or replace the plot-document metadata node in *svg_bytes*."""
    payload = json.dumps(document.to_dict(), ensure_ascii=False,
                         allow_nan=False, separators=(',', ':'))
    try:
        root = ET.fromstring(svg_bytes)
    except ET.ParseError as e:
        raise _err(f"cannot embed metadata in invalid SVG: {e}")
    ns = ''
    if root.tag.startswith('{'):
        ns = root.tag[:root.tag.index('}') + 1]
    # remove existing node(s)
    for meta in list(root.findall(f'{ns}metadata')) + list(root.findall('metadata')):
        if meta.get('id') == METADATA_ID:
            root.remove(meta)
    meta = ET.Element(f'{ns}metadata', {'id': METADATA_ID})
    meta.text = payload
    root.insert(0, meta)
    return ET.tostring(root, encoding='unicode').encode('utf-8')


_ENTITY_RE = re.compile(rb'<!ENTITY', re.IGNORECASE)


def _reject_entities(svg: bytes):
    """Refuse SVG input that declares entities (XXE hardening)."""
    if _ENTITY_RE.search(svg):
        from .i18n import tr
        raise _err(tr('err_svg_entities'))


def document_from_svg(svg: bytes) -> PlotDocument:
    """Parse the embedded document; raises PlotDocumentError if absent/bad."""
    if len(svg) > MAX_FILE_BYTES:
        raise _err(f"SVG too large (> {MAX_FILE_BYTES // (1024 * 1024)} MiB)")
    _reject_entities(svg)
    try:
        root = ET.fromstring(svg)
    except ET.ParseError as e:
        raise _err(f"not a valid SVG file: {e}")
    text = _find_metadata_text(root)
    if text is None:
        raise _err("no embedded plot document — this is a plain SVG "
                   "(editable plots are saved as *.ilmplot.svg)")
    try:
        data = json.loads(text, parse_constant=_reject_json_constant)
    except json.JSONDecodeError as e:
        raise _err(f"embedded plot document is not valid JSON: {e}")
    return PlotDocument.from_dict(data)


def _reject_json_constant(value: str):
    raise _err(f"embedded plot document contains non-finite value {value!r}")


def _find_metadata_text(root) -> str | None:
    for elem in root.iter():
        local = elem.tag.rsplit('}', 1)[-1]
        if local == 'metadata' and elem.get('id') == METADATA_ID:
            return elem.text
    return None


def load_document(path: str) -> PlotDocument:
    with open(path, 'rb') as fh:
        head = fh.read(MAX_FILE_BYTES + 1)
    if len(head) > MAX_FILE_BYTES:
        raise _err(f"file too large (> {MAX_FILE_BYTES // (1024 * 1024)} MiB)")
    return document_from_svg(head)


# ── cheap presence detection (cached) ─────────────────────────────────────

_METADATA_MARKER = METADATA_ID.encode('utf-8')
_detect_cache: dict = {}
_DETECT_CACHE_MAX = 256


def has_plot_metadata(path: str) -> bool:
    """True when *path* is an SVG that carries an ilm-plot metadata node.

    Returns True even when the embedded payload is malformed or from a
    future schema version, so the editor can open and explain the problem.
    """
    try:
        st = os.stat(path)
    except OSError:
        return False
    key = os.path.abspath(path)
    sig = (st.st_size, st.st_mtime_ns)
    hit = _detect_cache.get(key)
    if hit is not None and hit[0] == sig:
        return hit[1]
    result = False
    if st.st_size <= MAX_FILE_BYTES:
        try:
            with open(path, 'rb') as fh:
                # bounded scan: matplotlib emits metadata near the end;
                # scan the whole (bounded) file to be safe.
                blob = fh.read()
            result = _METADATA_MARKER in blob \
                and not _ENTITY_RE.search(blob)
        except OSError:
            result = False
    if len(_detect_cache) >= _DETECT_CACHE_MAX:
        _detect_cache.clear()
    _detect_cache[key] = (sig, result)
    return result


def document_from_metadata_text(text: str) -> PlotDocument:
    """Parse raw JSON payload text (test/diagnostic helper)."""
    return PlotDocument.from_dict(
        json.loads(text, parse_constant=_reject_json_constant))
