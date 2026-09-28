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
import uuid
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, fields

SCHEMA_VERSION = 1
METADATA_ID = 'ilm-plot-document'
FORMAT_NAME = 'ilm-plot'

MAX_FILE_BYTES = 16 * 1024 * 1024
MAX_SERIES = 100
MAX_TOTAL_POINTS = 100_000
MAX_DIMENSION_MM = 1000.0

LINESTYLES = ('-', '--', '-.', ':', '')
MARKERS = ('', 'o', 's', '^', 'v', 'D', '+', 'x', '.')
LEGEND_LOCATIONS = (
    'best', 'upper right', 'upper left', 'lower left', 'lower right',
    'right', 'center left', 'center right', 'lower center',
    'upper center', 'center',
)


class PlotDocumentError(ValueError):
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


@dataclass
class LineSeries:
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    label: str = 'Series 1'
    x: list = field(default_factory=lambda: [0., 1., 2., 3.])
    y: list = field(default_factory=lambda: [0., 1., .5, 1.5])
    color: str = '#0891b2'
    linewidth_pt: float = 1.25
    linestyle: str = '-'
    marker: str = ''
    markersize_pt: float = 4.

    def to_dict(self) -> dict:
        return {
            'id': self.id, 'label': self.label,
            'x': list(self.x), 'y': list(self.y),
            'color': self.color, 'linewidth_pt': self.linewidth_pt,
            'linestyle': self.linestyle, 'marker': self.marker,
            'markersize_pt': self.markersize_pt,
        }

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
    font_size_pt: float = 8.
    title_size_pt: float = 10.
    xlim: list | None = None
    ylim: list | None = None
    legend: bool = True
    legend_location: str = 'best'
    grid: bool = False
    series: list = field(default_factory=lambda: [LineSeries()])

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
        if self.kind != 'line':
            raise _err(f"{ctx}.kind: unsupported {self.kind!r} (only 'line')")
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
        if not isinstance(self.legend, bool) or not isinstance(self.grid, bool):
            raise _err(f"{ctx}.legend/grid: expected true/false")
        if self.legend_location not in LEGEND_LOCATIONS:
            raise _err(f"{ctx}.legend_location: unsupported "
                       f"{self.legend_location!r}")
        if not isinstance(self.series, list) or not self.series:
            raise _err(f"{ctx}.series: at least one series is required")
        if len(self.series) > MAX_SERIES:
            raise _err(f"{ctx}.series: at most {MAX_SERIES} series")
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
        if total > MAX_TOTAL_POINTS:
            raise _err(f"{ctx}: too many data points ({total} > {MAX_TOTAL_POINTS})")
        return self

    # ── serialization ───────────────────────────────────────────────
    def to_dict(self) -> dict:
        return {
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

    @classmethod
    def from_dict(cls, data) -> 'PlotDocument':
        if not isinstance(data, dict):
            raise _err(f"plot document: expected a JSON object, got "
                       f"{type(data).__name__}")
        if data.get('format') != FORMAT_NAME:
            raise _err(f"plot document: missing or wrong 'format' "
                       f"(expected {FORMAT_NAME!r}, got {data.get('format')!r})")
        allowed = {f.name for f in fields(cls)} | {'format'}
        unknown = sorted(set(data) - allowed)
        if unknown:
            raise _err(f"plot document: unknown field(s) {unknown} — "
                       f"file may need a newer version of the editor")
        d = cls()
        sv = data.get('schema_version')
        if not isinstance(sv, int) or isinstance(sv, bool):
            raise _err(f"document.schema_version: expected an integer, got {sv!r}")
        d.schema_version = sv
        if data.get('kind') != 'line':
            raise _err(f"document.kind: unsupported {data.get('kind')!r}")
        d.kind = 'line'
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
        d.legend = _req_bool(data, 'legend', 'document')
        loc = data.get('legend_location')
        if loc not in LEGEND_LOCATIONS:
            raise _err(f"document.legend_location: unsupported {loc!r}")
        d.legend_location = loc
        d.grid = _req_bool(data, 'grid', 'document')
        series = data.get('series')
        if not isinstance(series, list) or not series:
            raise _err("document.series: expected a non-empty array")
        d.series = [LineSeries.from_dict(s, ctx=f"series[{i}]")
                    for i, s in enumerate(series)]
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


def document_from_svg(svg: bytes) -> PlotDocument:
    """Parse the embedded document; raises PlotDocumentError if absent/bad."""
    if len(svg) > MAX_FILE_BYTES:
        raise _err(f"SVG too large (> {MAX_FILE_BYTES // (1024 * 1024)} MiB)")
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
                result = _METADATA_MARKER in fh.read()
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
