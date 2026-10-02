"""Editor-owned ``*.ilmplot.svg`` payload: the worksheet node (no Qt).

The ``ilm-plot-document`` metadata schema is unchanged and still parsed
strictly by ILM. This module adds a second metadata node,
``ilm-plot-worksheet``, which stores the raw worksheet (designations, meta
fields and cell values) plus the chart key and plotted columns so the
editor can reopen a file exactly as it was saved. Files written by ILM or
older editor versions simply lack the node and fall back to rebuilding a
worksheet from the document's series.
"""

import json
import math
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass

from . import render
from .actions import CHART_GROUPS
from .document import (MAX_FILE_BYTES, METADATA_ID, PlotDocument,
                       document_from_svg)
from .export import _atomic_write
from .overrides import PlotOverrides
from .plot_data import Series
from .worksheet import (Column, DESIGNATIONS, MAX_COLUMNS,
                        MAX_PASTE_CELLS, Worksheet)

WORKSHEET_METADATA_ID = 'ilm-plot-worksheet'
WORKSHEET_FORMAT = 'ilm-plot-worksheet'
WORKSHEET_SCHEMA_VERSION = 2

_CHART_KEYS = {c.key for g in CHART_GROUPS for c in g.charts}
_COLUMN_KEYS = ('designation', 'long_name', 'units', 'comments', 'values')


class PlotFileError(ValueError):
    """Raised when an ``*.ilmplot.svg`` worksheet payload is malformed."""


def _err(msg):
    return PlotFileError(msg)


@dataclass
class PlotFile:
    document: PlotDocument
    svg: bytes
    worksheet: Worksheet
    chart_key: 'str | None'
    plot_columns: tuple
    has_worksheet: bool
    overrides: 'PlotOverrides | None' = None


def worksheet_to_dict(ws, chart_key, plot_columns, overrides=None):
    columns = []
    for col in ws.columns:
        values = list(col.values)
        while values and values[-1] is None:
            values.pop()
        columns.append({'designation': col.designation,
                        'long_name': col.long_name,
                        'units': col.units,
                        'comments': col.comments,
                        'values': values})
    d = {'format': WORKSHEET_FORMAT,
         'schema_version': 1,
         'chart': chart_key,
         'plot_columns': list(plot_columns),
         'columns': columns}
    if overrides is not None:
        od = overrides.to_dict()
        if od:
            # Overrides need schema v2; unstyled files stay v1 so older
            # editor builds can still read them.
            d['overrides'] = od
            d['schema_version'] = WORKSHEET_SCHEMA_VERSION
    return d


def _reject_constant(value):
    raise _err('worksheet payload contains non-finite value %r' % value)


def worksheet_from_dict(data):
    """Strict parse of the worksheet payload → (Worksheet, chart, cols)."""
    ctx = 'worksheet'
    if not isinstance(data, dict):
        raise _err('%s: expected an object' % ctx)
    if data.get('format') != WORKSHEET_FORMAT:
        raise _err("%s.format: expected %r, got %r"
                   % (ctx, WORKSHEET_FORMAT, data.get('format')))
    sv = data.get('schema_version')
    if not isinstance(sv, int) or isinstance(sv, bool):
        raise _err('%s.schema_version: expected an integer, got %r'
                   % (ctx, sv))
    if not (1 <= sv <= WORKSHEET_SCHEMA_VERSION):
        raise _err('%s.schema_version: unsupported %r (this version '
                   'supports %d)' % (ctx, sv, WORKSHEET_SCHEMA_VERSION))
    allowed = {'format', 'schema_version', 'chart', 'plot_columns',
               'columns'} | ({'overrides'} if sv >= 2 else set())
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _err('%s: unknown field(s) %s — file may need a newer '
                   'version' % (ctx, unknown))
    chart = data.get('chart')
    if chart is not None and chart not in _CHART_KEYS:
        raise _err('%s.chart: unknown chart type %r' % (ctx, chart))
    cols = data.get('columns')
    if not isinstance(cols, list) or not (1 <= len(cols) <= MAX_COLUMNS):
        raise _err('%s.columns: expected 1..%d column objects'
                   % (ctx, MAX_COLUMNS))
    total = 0
    columns = []
    for i, c in enumerate(cols):
        cc = '%s.columns[%d]' % (ctx, i)
        if not isinstance(c, dict):
            raise _err('%s: expected an object' % cc)
        unknown = sorted(set(c) - set(_COLUMN_KEYS))
        if unknown:
            raise _err('%s: unknown field(s) %s' % (cc, unknown))
        designation = c.get('designation')
        if designation not in DESIGNATIONS:
            raise _err('%s.designation: unknown %r' % (cc, designation))
        meta = {}
        for name in ('long_name', 'units', 'comments'):
            v = c.get(name)
            if not isinstance(v, str):
                raise _err('%s.%s: expected a string' % (cc, name))
            meta[name] = v
        values = c.get('values')
        if not isinstance(values, list):
            raise _err('%s.values: expected an array' % cc)
        total += len(values)
        if total > MAX_PASTE_CELLS:
            raise _err('%s: too many cells (> %d)' % (cc, MAX_PASTE_CELLS))
        parsed = []
        for v in values:
            if v is None or isinstance(v, str):
                parsed.append(v)
            elif isinstance(v, (int, float)) \
                    and not isinstance(v, bool):
                if not math.isfinite(v):
                    raise _err('%s.values: non-finite number %r' % (cc, v))
                parsed.append(float(v))
            else:
                raise _err('%s.values: expected number/string/null, got %r'
                           % (cc, v))
        columns.append(Column(designation, meta['long_name'],
                              meta['units'], meta['comments'], parsed))
    overrides = None
    if data.get('overrides') is not None:
        try:
            overrides = PlotOverrides.from_dict(data['overrides'])
        except ValueError as e:
            raise _err('%s.overrides: %s' % (ctx, e))
    plot_columns = data.get('plot_columns')
    if not isinstance(plot_columns, list):
        raise _err('%s.plot_columns: expected an array' % ctx)
    for i in plot_columns:
        if not isinstance(i, int) or isinstance(i, bool) \
                or not (0 <= i < len(columns)):
            raise _err('%s.plot_columns: column index %r out of range'
                       % (ctx, i))
    return (Worksheet.from_columns(columns), chart, tuple(plot_columns),
            overrides)


_AXIS_TITLE = re.compile(r'(.*\S)\s*\(([^()]*)\)')


def split_axis_title(text):
    """``'Time (s)'`` → ``('Time', 's')``; no suffix → ``(text, '')``."""
    match = _AXIS_TITLE.fullmatch(text.strip())
    if match:
        return match.group(1), match.group(2)
    return text, ''


def _tick_lookup(doc):
    """``{position: label}`` when the document carries categorical ticks."""
    if not doc.x_tick_labels:
        return {}
    return {p: l for p, l in doc.x_tick_labels}


def worksheet_from_document(doc):
    """Rebuild a worksheet from a document: shared-x dedupe → X,Y[,X,Y…].

    When ``doc.x_tick_labels`` covers every x of a series, its X column
    becomes a ``Label`` column holding the tick strings for its x values.
    """
    columns = []
    last_x = None
    tick_map = _tick_lookup(doc)
    x_name, x_units = split_axis_title(doc.xlabel)
    y_name, y_units = split_axis_title(doc.ylabel)
    for s in doc.series:
        categorical = bool(tick_map) and all(v in tick_map for v in s.x)
        x_values = ([tick_map[v] for v in s.x]
                    if categorical else list(s.x))
        if last_x is None or x_values != last_x.values:
            last_x = Column('Label' if categorical else 'X',
                            long_name=x_name, units=x_units,
                            values=x_values)
            columns.append(last_x)
        columns.append(Column('Y', long_name=y_name, units=y_units,
                              comments=s.label, values=list(s.y)))
    return Worksheet.from_columns(columns)


def series_from_document(doc):
    tick_map = _tick_lookup(doc)
    out = []
    for s in doc.series:
        labels = None
        if tick_map and all(v in tick_map for v in s.x):
            labels = tuple(tick_map[v] for v in s.x)
        out.append(Series(tuple(s.x), tuple(s.y), s.label,
                          doc.xlabel, doc.ylabel, labels))
    return out


def chart_from_document(doc):
    s = doc.series[0]
    if not s.linestyle:
        return 'pure_scatters'
    if s.marker:
        return 'line_scatters'
    return 'pure_line'


def _metadata_nodes(root):
    ns = ''
    if root.tag.startswith('{'):
        ns = root.tag[:root.tag.index('}') + 1]
    return ns, [c for c in root if c.tag == f'{ns}metadata']


def save_plot_file(path, document, worksheet, chart_key, plot_columns,
                   overrides=None):
    """Atomically write the SVG with both metadata nodes."""
    svg = render.render_document(document).svg
    payload = json.dumps(
        worksheet_to_dict(worksheet, chart_key, plot_columns, overrides),
        ensure_ascii=False, allow_nan=False, separators=(',', ':'))
    render._register_namespaces(svg)
    root = ET.fromstring(svg)
    ns, metas = _metadata_nodes(root)
    for meta in metas:
        if meta.get('id') == WORKSHEET_METADATA_ID:
            root.remove(meta)
    node = ET.Element(f'{ns}metadata', {'id': WORKSHEET_METADATA_ID})
    node.text = payload
    index = 0
    for i, meta in enumerate(list(root)):
        if meta.tag == f'{ns}metadata' and meta.get('id') == METADATA_ID:
            index = i + 1
    root.insert(index, node)
    data = ET.tostring(root, encoding='unicode').encode('utf-8')
    if len(data) > MAX_FILE_BYTES:
        raise _err('plot file too large (> %d MiB)'
                   % (MAX_FILE_BYTES // (1024 * 1024)))
    _atomic_write(path, lambda fh: fh.write(data))


def load_plot_file(path):
    """Read an ``*.ilmplot.svg``; worksheet node optional (strict if present)."""
    with open(path, 'rb') as fh:
        data = fh.read(MAX_FILE_BYTES + 1)
    if len(data) > MAX_FILE_BYTES:
        raise PlotFileError(
            'file too large (> %d MiB)' % (MAX_FILE_BYTES // (1024 * 1024)))
    document = document_from_svg(data)
    try:
        root = ET.fromstring(data)
    except ET.ParseError as e:
        raise _err('not a valid SVG file: %s' % e)
    _ns, metas = _metadata_nodes(root)
    text = None
    for meta in metas:
        if meta.get('id') == WORKSHEET_METADATA_ID:
            text = meta.text
    if text is None:
        worksheet = worksheet_from_document(document)
        return PlotFile(document, data, worksheet,
                        chart_from_document(document),
                        tuple(range(worksheet.column_count)),
                        False)
    try:
        payload = json.loads(text, parse_constant=_reject_constant)
    except json.JSONDecodeError as e:
        raise _err('worksheet payload is not valid JSON: %s' % e)
    worksheet, chart, plot_columns, overrides = \
        worksheet_from_dict(payload)
    return PlotFile(document, data, worksheet, chart, plot_columns, True,
                    overrides)
