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

import ilmplot.render as render
from .actions import CHART_GROUPS
from ilmplot.document import (MAX_FILE_BYTES, METADATA_ID, PlotDocument,
                       document_from_svg)
from .export import _atomic_write, HORIZONTAL_CHARTS
from .overrides import PlotOverrides
from .plot_data import Series
from .worksheet import (Column, DESIGNATIONS, MAX_COLUMNS,
                        MAX_PASTE_CELLS, Worksheet)

WORKSHEET_METADATA_ID = 'ilm-plot-worksheet'
WORKSHEET_FORMAT = 'ilm-plot-worksheet'
WORKSHEET_SCHEMA_VERSION = 2

# Optional-feature ids the worksheet reader understands beyond the
# baseline; writers stamp theirs into the payload's ``requires``.
WORKSHEET_CAPABILITIES = frozenset(
    {'bands', 'error_band', 'spans', 'fills', 'box_plot',
     'column_points', 'histogram', 'horizontal_bars'})

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
    # Translated load warnings (e.g. a worksheet node that could not be
    # read and was rebuilt from the document).
    warnings: tuple = ()
    # True when the source file must not be written back (rebuilt sheet).
    read_only_source: bool = False


def worksheet_to_dict(ws, chart_key, plot_columns, overrides=None,
                      for_save=False):
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
    if for_save:
        from src.version import APP_VERSION
        d['generator'] = 'ILM %s' % APP_VERSION
    if overrides is not None:
        od = overrides.to_dict()
        if od:
            # Overrides need schema v2; unstyled files stay v1 so older
            # editor builds can still read them.
            d['overrides'] = od
            d['schema_version'] = WORKSHEET_SCHEMA_VERSION
    # ``requires`` is a v1-allowed key: chart kinds needing reader
    # features stamp it even without overrides.
    req = []
    if overrides is not None and overrides.to_dict():
        if getattr(overrides, 'bands', None) \
                or getattr(overrides, 'fills', None):
            req.append('bands')
        if getattr(overrides, 'spans', None):
            req.append('spans')
        if getattr(overrides, 'fills', None):
            req.append('fills')
        for so in getattr(overrides, 'series', {}).values():
            if getattr(so, 'error_style', None) == 'band':
                req.append('error_band')
                break
    if chart_key == 'histogram' \
            or getattr(overrides, 'histogram', None) is not None:
        req.append('histogram')
    vd = {}
    if overrides is not None and overrides.violin is not None:
        vd = overrides.violin.to_dict()
    if chart_key == 'box' or vd.get('body') == 'none' \
            or 'box_width' in vd or 'show_outliers' in vd:
        req.append('box_plot')
    if chart_key == 'column_points' or vd.get('body') == 'bar' \
            or 'bar_width' in vd or 'bar_error' in vd:
        req.append('column_points')
    if chart_key in HORIZONTAL_CHARTS:
        req.append('horizontal_bars')
    if req:
        d['requires'] = sorted(set(req))
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
               'columns', 'requires', 'generator'} \
        | ({'overrides'} if sv >= 2 else set())
    unknown = sorted(set(data) - allowed)
    if unknown:
        raise _err('%s: unknown field(s) %s — file may need a newer '
                   'version' % (ctx, unknown))
    from ilmplot.document import _check_requires
    req = _check_requires(data.get('requires'), '%s.requires' % ctx)
    missing = sorted(set(req) - WORKSHEET_CAPABILITIES)
    if missing:
        raise _err('%s.requires: unsupported capabilities %s '
                   '(file needs a newer version)' % (ctx, missing))
    gen = data.get('generator')
    if gen is not None and (not isinstance(gen, str)
                            or len(gen) > 100):
        raise _err('%s.generator: expected a string of at most 100 '
                   'characters' % ctx)
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
    """Rebuild a worksheet from a document (wide format, per kind).

    Line/ridgeline: shared-x dedupe → X,Y[,X,Y…]; a ``doc.x_tick_labels``
    covering every x of a series turns its X column into a ``Label``
    column. Violin: one Y column per group. Stacked: a Label column of
    bar names plus one Y per category.
    """
    if doc.kind in ('violin', 'histogram'):
        # Histograms carry the value title on x (y is the count axis).
        v_name, v_units = split_axis_title(
            doc.xlabel if doc.kind == 'histogram' else doc.ylabel)
        return Worksheet.from_columns([
            Column('Y', long_name=v_name if i == 0 else '',
                   units=v_units if i == 0 else '',
                   comments=g.label, values=list(g.values))
            for i, g in enumerate(doc.groups)])
    if doc.kind == 'stacked_column':
        tick_map = _tick_lookup(doc)
        n = len(doc.categories[0].values)
        names = [tick_map.get(i, str(i)) for i in range(n)]
        x_name, x_units = split_axis_title(doc.xlabel)
        columns = [Column('Label', long_name=x_name, units=x_units,
                          values=names)]
        for c in doc.categories:
            columns.append(Column('Y', comments=c.label,
                                  values=list(c.values)))
            if c.yerr is not None:
                columns.append(Column('yErr', values=list(c.yerr)))
            if c.yerr_minus is not None:
                columns.append(Column('yErrMinus',
                                      values=list(c.yerr_minus)))
            if c.yerr_plus is not None:
                columns.append(Column('yErrPlus',
                                      values=list(c.yerr_plus)))
        return Worksheet.from_columns(columns)
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
        if s.yerr is not None:
            columns.append(Column('yErr', values=list(s.yerr)))
        if s.yerr_minus is not None:
            columns.append(Column('yErrMinus',
                                  values=list(s.yerr_minus)))
        if s.yerr_plus is not None:
            columns.append(Column('yErrPlus',
                                  values=list(s.yerr_plus)))
    return Worksheet.from_columns(columns)


def series_from_document(doc):
    tick_map = _tick_lookup(doc)
    out = []
    for s in doc.series:
        labels = None
        if tick_map and all(v in tick_map for v in s.x):
            labels = tuple(tick_map[v] for v in s.x)
        out.append(Series(tuple(s.x), tuple(s.y), s.label,
                          doc.xlabel, doc.ylabel, labels,
                          yerr=tuple(s.yerr) if s.yerr is not None
                          else None,
                          yerr_minus=tuple(s.yerr_minus)
                          if s.yerr_minus is not None else None,
                          yerr_plus=tuple(s.yerr_plus)
                          if s.yerr_plus is not None else None))
    return out


def items_from_document(doc):
    """Fallback items for a document whose worksheet can't rebuild."""
    from .plot_data import Category, Group
    if doc.kind == 'histogram':
        return [Group(tuple(g.values), g.label, '', doc.xlabel)
                for g in doc.groups]
    if doc.kind == 'violin':
        return [Group(tuple(g.values), g.label,
                      doc.xlabel, doc.ylabel)
                for g in doc.groups]
    if doc.kind == 'stacked_column':
        tick_map = _tick_lookup(doc)
        n = len(doc.categories[0].values)
        bar_labels = tuple(tick_map.get(i, str(i)) for i in range(n))
        return [Category(tuple(c.values), c.label,
                         doc.xlabel, doc.ylabel, bar_labels,
                         yerr=tuple(c.yerr) if c.yerr is not None
                         else None,
                         yerr_minus=tuple(c.yerr_minus)
                         if c.yerr_minus is not None else None,
                         yerr_plus=tuple(c.yerr_plus)
                         if c.yerr_plus is not None else None)
                for c in doc.categories]
    return series_from_document(doc)


def chart_from_document(doc):
    if doc.kind == 'violin':
        body = doc.violin.body if doc.violin is not None else 'violin'
        return {'none': 'box', 'bar': 'column_points'}.get(
            body, 'violin')
    if doc.kind == 'histogram':
        return 'histogram'
    if doc.kind == 'ridgeline':
        return 'ridgeline'
    if doc.kind == 'stacked_column':
        horizontal = doc.stacked is not None and doc.stacked.horizontal
        if doc.stacked is not None and doc.stacked.grouped:
            return 'bar' if horizontal else 'column'
        pct = doc.stacked.percent if doc.stacked is not None else True
        if horizontal:
            return 'stacked_bar_pct' if pct else 'stacked_bar'
        return 'stacked_column_pct' if pct else 'stacked_column'
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
        worksheet_to_dict(worksheet, chart_key, plot_columns, overrides,
                          for_save=True),
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
    # Verify the exact bytes before touching the file: both metadata
    # nodes must re-parse with this reader.
    try:
        document_from_svg(data)
        worksheet_from_dict(json.loads(payload))
    except Exception as e:
        from .i18n import tr
        raise _err(tr('err_save_verify', error=e))
    _atomic_write(path, lambda fh: fh.write(data))


def load_plot_file(path):
    """Read an ``*.ilmplot.svg``; worksheet node optional.

    A worksheet node that fails to parse (bad JSON, future schema,
    unknown designations or capabilities) never blocks the file: the
    sheet is rebuilt from the plot document, a warning is attached, and
    the source is flagged read-only so it cannot be overwritten.
    """
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
    warnings = ()
    if text is not None:
        try:
            payload = json.loads(text, parse_constant=_reject_constant)
            worksheet, chart, plot_columns, overrides = \
                worksheet_from_dict(payload)
        except Exception as e:
            from .i18n import tr
            warnings = (tr('warn_worksheet_rebuilt', error=e),)
        else:
            return PlotFile(document, data, worksheet, chart,
                            plot_columns, True, overrides)
    worksheet = worksheet_from_document(document)
    return PlotFile(document, data, worksheet,
                    chart_from_document(document),
                    tuple(range(worksheet.column_count)),
                    False, warnings=warnings,
                    read_only_source=bool(warnings))
