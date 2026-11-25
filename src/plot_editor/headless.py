"""Headless Plot Editor engine (no Qt): spec in, ``*.ilmplot.svg`` out.

Everything goes through the same Qt-free pieces the Plot Editor tab
uses — ``plot_file`` for the file format, ``plot_data`` builders for
the worksheet, ``overrides.effective_document`` for styling — so a
file written here is identical in kind to one saved from the UI.

A *spec* is the ``ilm-plot-worksheet`` payload shape plus ``title`` and
figure size::

    {"chart": "pure_line", "title": "", "width_mm": 90, "height_mm": 65,
     "columns": [{"designation": "X", "long_name": "", "units": "",
                  "comments": "", "values": [0, 1, 2]}, ...],
     "plot_columns": [0, 1],
     "overrides": {"xlabel": "x", "series": {"1": {"color": "#ff0000"}}},
     "info": {...}}   # read-only, emitted by inspect, ignored on input
"""

from __future__ import annotations

import copy
import os
from dataclasses import dataclass

from ilmplot.document import PlotDocumentError

from .export import (_ACCEPTED, CHART_KIND, EXPORT_FORMATS,
                     export_plot, with_suffix)
from .figure_size import FigureSize
from .formula import FormulaError
from .overrides import (OverridesError, PlotOverrides,
                        effective_document, hold_baked_colours,
                        overrides_from_document)
from .plot_data import (PlotSelectionError, build_categories,
                        build_groups, build_matrix, build_series)
from .plot_file import (_COLUMN_KEYS, WORKSHEET_FORMAT,
                        WORKSHEET_SCHEMA_VERSION, PlotFileError,
                        chart_from_document, items_from_document,
                        load_plot_file, save_plot_file,
                        worksheet_from_dict)
from .worksheet import DESIGNATIONS, Worksheet, parse_cell


class HeadlessError(ValueError):
    """Raised when a spec, patch or plot file cannot be processed."""


_SPEC_KEYS = {'chart', 'title', 'width_mm', 'height_mm', 'columns',
              'plot_columns', 'overrides', 'info'}
# ``plot export`` produces figure files, never another editable plot —
# 'ilmplot' is excluded so the worksheet node cannot be stripped by
# accident (use ``plot edit -o``/``create`` for *.ilmplot.svg).
_EXPORT_FORMATS = {k: v for k, v in EXPORT_FORMATS.items()
                   if k != 'ilmplot'}
_EXPORT_ACCEPTED = {k: v for k, v in _ACCEPTED.items() if k != 'ilmplot'}


def build_items(worksheet, columns, chart_key):
    """Series/Group/Category/Matrix items for ``chart_key`` from the
    sheet — the same dispatch the Plot Editor tab uses."""
    kind = CHART_KIND.get(chart_key, ('line', None))[0]
    if kind in ('violin', 'histogram'):
        return build_groups(worksheet, columns)
    if kind == 'stacked_column':
        return build_categories(worksheet, columns)
    if kind == 'heatmap':
        return [build_matrix(worksheet, columns)]
    return build_series(
        worksheet, columns,
        functions=chart_key in ('pure_line', 'pure_scatters',
                                'line_scatters', 'step_line'))


@dataclass
class State:
    """Everything needed to rebuild and save one plot, mirroring the
    fields ``PlotTab.load`` keeps on a tab."""
    worksheet: Worksheet
    chart: 'str | None'
    plot_columns: tuple
    overrides: PlotOverrides
    title: str
    figure_size: FigureSize
    # The document stored in the file (fallback item source); None for
    # spec-created states.
    document: 'object | None' = None
    # Render base for legacy files (no worksheet node): contributes the
    # look while the worksheet stays the data source. None otherwise.
    base_doc: 'object | None' = None
    has_worksheet: bool = True
    warnings: tuple = ()
    # True when the source must not be overwritten in place (its
    # worksheet node failed to parse and was rebuilt).
    read_only_source: bool = False


def _wrap(exc):
    return HeadlessError(str(exc))


def load_state(path):
    """Load an ``*.ilmplot.svg`` into a :class:`State` (``PlotTab.load``
    semantics)."""
    try:
        pf = load_plot_file(path)
    except FileNotFoundError:
        raise
    except (PlotFileError, PlotDocumentError, OSError) as e:
        raise _wrap(e)
    chart = pf.chart_key or chart_from_document(pf.document)
    if pf.has_worksheet:
        columns = tuple(pf.plot_columns)
    else:
        columns = tuple(range(pf.worksheet.column_count))
    try:
        items = build_items(pf.worksheet, list(columns), chart)
    except PlotSelectionError:
        items = items_from_document(pf.document)
    overrides = pf.overrides if pf.overrides is not None \
        else overrides_from_document(pf.document, items, chart)
    hold_baked_colours(overrides, pf.document)
    try:
        figure_size = FigureSize.from_document(pf.document)
    except PlotDocumentError as e:
        raise _wrap(e)
    return State(pf.worksheet, chart, columns, overrides,
                 pf.document.title or '', figure_size,
                 document=pf.document,
                 base_doc=pf.document if not pf.has_worksheet else None,
                 has_worksheet=pf.has_worksheet,
                 warnings=pf.warnings,
                 read_only_source=pf.read_only_source)


def _spec_columns(columns):
    return [{'designation': c.designation,
             'long_name': c.long_name,
             'units': c.units,
             'comments': c.comments,
             'values': list(c.values)}
            for c in columns]


def state_from_spec(spec, base=None, document=None):
    """Build a :class:`State` from a spec dict (strict).

    ``base`` is an existing ``PlotDocument`` used as render base (the
    legacy-file path); ``document`` is the fallback item source. When a
    heatmap ``base`` meets non-empty ``columns`` the worksheet becomes
    the data source, so the base is dropped and its look is carried
    over through a seeded ``overrides.heatmap``.
    """
    if not isinstance(spec, dict):
        raise HeadlessError('spec: expected an object')
    unknown = sorted(set(spec) - _SPEC_KEYS)
    if unknown:
        raise HeadlessError('spec: unknown field(s) %s' % unknown)
    columns = spec.get('columns')
    has_columns = isinstance(columns, list) and bool(columns)
    if columns is not None and not isinstance(columns, list):
        raise HeadlessError('spec.columns: expected an array')
    if not has_columns and base is None and document is None:
        raise HeadlessError('spec.columns: at least one column is '
                            'required')
    overrides = None
    chart = spec.get('chart')
    worksheet = Worksheet()
    plot_columns = ()
    if has_columns:
        payload_columns = []
        for i, c in enumerate(columns):
            cc = 'spec.columns[%d]' % i
            if not isinstance(c, dict):
                raise HeadlessError('%s: expected an object' % cc)
            extra = sorted(set(c) - set(_COLUMN_KEYS))
            if extra:
                raise HeadlessError('%s: unknown field(s) %s'
                                    % (cc, extra))
            values = c.get('values') or []
            if not isinstance(values, list):
                raise HeadlessError('%s.values: expected an array' % cc)
            # Typed cells go through parse_cell: a numeric string is a
            # number, anything else stays text.
            payload_columns.append({
                'designation': c.get('designation'),
                'long_name': c.get('long_name', ''),
                'units': c.get('units', ''),
                'comments': c.get('comments', ''),
                'values': [parse_cell(v) if isinstance(v, str) else v
                           for v in values]})
        plot_columns = spec.get('plot_columns')
        if plot_columns is None:
            plot_columns = list(range(len(payload_columns)))
        payload = {'format': WORKSHEET_FORMAT,
                   'schema_version': WORKSHEET_SCHEMA_VERSION,
                   'chart': chart,
                   'plot_columns': plot_columns,
                   'columns': payload_columns}
        if spec.get('overrides') is not None:
            payload['overrides'] = spec['overrides']
        try:
            worksheet, chart, plot_columns, overrides = \
                worksheet_from_dict(payload)
        except (PlotFileError, ValueError) as e:
            raise _wrap(e)
    else:
        if spec.get('overrides') is not None:
            try:
                overrides = PlotOverrides.from_dict(spec['overrides'])
            except (OverridesError, ValueError) as e:
                raise _wrap(e)
        if chart is None and base is not None:
            chart = chart_from_document(base)
        if chart is not None and chart not in CHART_KIND:
            raise HeadlessError('spec.chart: unknown chart type %r'
                                % chart)
    title = spec.get('title', '')
    if not isinstance(title, str):
        raise HeadlessError('spec.title: expected a string')
    try:
        figure_size = FigureSize(
            spec.get('width_mm', FigureSize.width_mm),
            spec.get('height_mm', FigureSize.height_mm))
    except PlotDocumentError as e:
        raise _wrap(e)
    if base is not None and base.kind == 'heatmap' and has_columns:
        # ``effective_document`` always renders a heatmap base from the
        # base document itself; dropping it lets new worksheet data take
        # effect while a seeded override keeps the saved look.
        if overrides is None:
            overrides = PlotOverrides()
        if overrides.heatmap is None and base.heatmap is not None:
            from .overrides import HeatmapOverride
            keep = {k: v for k, v in base.heatmap.to_dict().items()
                    if k in HeatmapOverride._KEYS}
            overrides.heatmap = HeatmapOverride.from_dict(keep)
        if chart is None:
            chart = 'heatmap'
        base = None
    if document is None:
        document = base
    return State(worksheet, chart, tuple(plot_columns),
                 overrides if overrides is not None else PlotOverrides(),
                 title, figure_size, document=document, base_doc=base,
                 has_worksheet=True)


def _resolve(state):
    """``(document, items)`` — the effective document plus the built
    items, exactly like ``PlotTab.effective_document``."""
    try:
        items = build_items(state.worksheet, list(state.plot_columns),
                            state.chart)
    except PlotSelectionError as e:
        doc0 = state.document
        kind = CHART_KIND.get(state.chart, ('line', None))[0]
        if doc0 is not None and doc0.kind == kind:
            items = items_from_document(doc0)
        elif state.base_doc is not None \
                and state.base_doc.kind == 'heatmap':
            items = []
        else:
            raise _wrap(e)
    try:
        doc = effective_document(state.base_doc, items, state.chart,
                                 state.title, state.overrides,
                                 figure_size=state.figure_size)
    except (PlotSelectionError, PlotDocumentError, PlotFileError,
            OverridesError, FormulaError) as e:
        raise _wrap(e)
    return doc, items


def effective(state):
    """The styled ``PlotDocument`` for *state*."""
    return _resolve(state)[0]


def _main_items(doc):
    if doc is None:
        return []
    if doc.kind in ('violin', 'histogram'):
        return list(doc.groups)
    if doc.kind == 'stacked_column':
        return list(doc.categories)
    if doc.kind == 'heatmap':
        return []
    return list(doc.series)


def spec_from_state(state):
    """Round-trippable spec for *state* plus a read-only ``info`` block.

    ``info.items`` lists the effective document's main collection in
    draw order; ``column`` is the source worksheet column index — the
    same index ``overrides.series`` keys use.
    """
    doc, items = _resolve(state)
    main = _main_items(doc)
    info_items = []
    for i, entry in enumerate(main):
        y_col = getattr(items[i], 'y_column', None) \
            if i < len(items) else None
        info_items.append({'n': i + 1,
                           'id': getattr(entry, 'id', ''),
                           'label': getattr(entry, 'label', ''),
                           'column': y_col})
    spec = {'chart': state.chart,
            'title': state.title,
            'width_mm': state.figure_size.width_mm,
            'height_mm': state.figure_size.height_mm,
            'columns': _spec_columns(state.worksheet.columns),
            'plot_columns': list(state.plot_columns),
            'info': {'kind': doc.kind,
                     'has_worksheet': state.has_worksheet,
                     'warnings': list(state.warnings),
                     'items': info_items}}
    od = state.overrides.to_dict()
    if od:
        spec['overrides'] = od
    return spec


def compact_spec(spec):
    """Copy of *spec* with each column's ``values`` replaced by its
    ``n_values`` length — the compact ``inspect`` overview."""
    out = copy.deepcopy(spec)
    for col in out.get('columns') or []:
        if isinstance(col, dict) and 'values' in col:
            col['n_values'] = len(col.pop('values'))
    return out


def save_state(state, path):
    """Write *state* as ``*.ilmplot.svg``; returns the document."""
    doc, _items = _resolve(state)
    try:
        save_plot_file(with_suffix(str(path), 'ilmplot'), doc,
                       state.worksheet, state.chart, state.plot_columns,
                       state.overrides)
    except (PlotFileError, PlotDocumentError, OSError) as e:
        raise _wrap(e)
    return doc


def _merge_patch(target, patch):
    """RFC 7386 JSON merge patch (``null`` deletes, objects merge,
    arrays/scalars replace)."""
    if isinstance(patch, dict):
        if not isinstance(target, dict):
            target = {}
        out = dict(target)
        for key, value in patch.items():
            if value is None:
                out.pop(key, None)
            else:
                out[key] = _merge_patch(out.get(key), value)
        return out
    return copy.deepcopy(patch)


def apply_patch(spec, patch):
    """Apply an RFC 7386 merge patch to a spec; returns a new spec.

    Extension: ``patch['columns']`` may be an object keyed by column
    index — an existing index merge-patches that column, the index equal
    to the current column count appends a new column (``designation``
    required), anything else is an error. ``info`` in a patch is
    ignored.
    """
    if not isinstance(spec, dict):
        raise HeadlessError('spec: expected an object')
    if not isinstance(patch, dict):
        raise HeadlessError('patch: expected an object')
    patch = {k: v for k, v in patch.items() if k != 'info'}
    columns_patch = patch.get('columns')
    if isinstance(columns_patch, dict):
        patch = dict(patch)
        del patch['columns']
        base_columns = spec.get('columns')
        if not isinstance(base_columns, list):
            raise HeadlessError('patch.columns: spec has no columns')
        columns = copy.deepcopy(base_columns)
        for key, sub in columns_patch.items():
            try:
                idx = int(key)
            except (TypeError, ValueError):
                raise HeadlessError(
                    'patch.columns: column index %r is not an integer'
                    % key)
            if idx < 0 or idx > len(columns):
                raise HeadlessError(
                    'patch.columns: column index %d out of range '
                    '(0..%d)' % (idx, len(columns)))
            if not isinstance(sub, dict):
                raise HeadlessError(
                    'patch.columns[%d]: expected an object' % idx)
            if idx == len(columns):
                if 'designation' not in sub:
                    raise HeadlessError(
                        'patch.columns[%d].designation: required when '
                        'appending a column' % idx)
                columns.append(sub)
            else:
                if not isinstance(columns[idx], dict):
                    raise HeadlessError(
                        'patch.columns[%d]: spec column is not an '
                        'object' % idx)
                columns[idx] = _merge_patch(columns[idx], sub)
        patch['columns'] = columns
    return _merge_patch(spec, patch)


def _result(state, doc, path):
    return {'path': os.path.abspath(str(path)),
            'kind': doc.kind,
            'items': len(_main_items(doc)),
            'warnings': list(state.warnings)}


def create(spec, out_path):
    """Create a new ``*.ilmplot.svg`` from *spec*."""
    state = state_from_spec(spec)
    doc = save_state(state, out_path)
    return _result(state, doc, with_suffix(str(out_path), 'ilmplot'))


def inspect(path):
    """Return the spec (with ``info``) for an existing plot file."""
    return spec_from_state(load_state(path))


def edit(path, patch, out_path=None):
    """Merge-patch the spec of an existing file and save the result.

    ``out_path=None`` edits in place; in-place edits of a read-only
    source (worksheet node failed to parse) are refused.
    """
    state = load_state(path)
    spec = spec_from_state(state)
    patched = apply_patch(spec, patch)
    new_state = state_from_spec(patched, base=state.base_doc,
                                document=state.document)
    if out_path is None:
        if state.read_only_source:
            raise HeadlessError(
                '%s: source file is read-only (its worksheet node '
                'could not be parsed); pass an output path instead'
                % path)
        out_path = path
    doc = save_state(new_state, out_path)
    return _result(new_state, doc, with_suffix(str(out_path), 'ilmplot'))


def preview_png(path, out_path):
    """Write a PNG render of an existing plot file's effective
    document; returns the written path."""
    state = load_state(path)
    doc = effective(state)
    out = with_suffix(str(out_path), 'png')
    try:
        export_plot(doc, out, 'png')
    except (PlotDocumentError, OSError, ValueError) as e:
        raise _wrap(e)
    return out


def _format_for_path(path):
    lower = str(path).lower()
    for suffix, key in sorted(
            ((s, k) for k, sufs in _EXPORT_ACCEPTED.items()
             for s in sufs), key=lambda t: -len(t[0])):
        if lower.endswith(suffix):
            return key
    return None


def export(path, out_path, fmt=None, transparent=False):
    """Render an existing plot file to a figure format.

    The effective document is rebuilt like the editor would; a file
    whose state cannot be rebuilt falls back to its stored document.
    """
    state = load_state(path)
    try:
        doc = effective(state)
    except HeadlessError:
        if state.document is None:
            raise
        doc = state.document
    key = fmt if fmt is not None else _format_for_path(out_path)
    if key is None or key not in _EXPORT_FORMATS:
        raise HeadlessError(
            'export format: unknown %r (expected one of %s or a '
            'recognised extension)'
            % (key, ', '.join(sorted(_EXPORT_FORMATS))))
    out = with_suffix(str(out_path), key)
    try:
        export_plot(doc, out, key, transparent=transparent)
    except (PlotDocumentError, OSError, ValueError) as e:
        raise _wrap(e)
    return {'path': os.path.abspath(out), 'format': key}


def _spec_json(obj, level=0):
    """Compact readable JSON for the spec reference: objects indent,
    scalar arrays stay on one line."""
    import json
    pad = '  ' * level
    if isinstance(obj, dict):
        if not obj:
            return '{}'
        inner = pad + '  '
        return '{\n' + ',\n'.join(
            '%s%s: %s' % (inner, json.dumps(k, ensure_ascii=False),
                          _spec_json(v, level + 1))
            for k, v in obj.items()) + '\n' + pad + '}'
    if isinstance(obj, list):
        if all(not isinstance(v, (dict, list)) for v in obj):
            return '[' + ', '.join(
                json.dumps(v, ensure_ascii=False) for v in obj) + ']'
        inner = pad + '  '
        return '[\n' + ',\n'.join(
            inner + _spec_json(v, level + 1) for v in obj) + '\n' + pad + ']'
    return json.dumps(obj, ensure_ascii=False)


def _spec_reference_json(name):
    return _spec_json(SPEC_EXAMPLES[name])


# ── agent-facing spec reference ────────────────────────────────────────

SPEC_EXAMPLES = {
    'line_with_function': {
        'chart': 'pure_line',
        'columns': [
            {'designation': 'X', 'values': [0, 1, 2, 3, 4]},
            {'designation': 'Y', 'comments': 'data',
             'values': [1, 3, 2, 5, 4]},
            {'designation': 'Function', 'values': ['2*x']},
        ],
        'overrides': {'legend_text': '\\l(1) %(1)\n\\l(2) %(2)'},
    },
    'grouped_column': {
        'chart': 'column',
        'columns': [
            {'designation': 'Label', 'values': ['a', 'b', 'c']},
            {'designation': 'Y', 'comments': 'ctrl',
             'values': [3, 5, 2]},
            {'designation': 'Y', 'comments': 'treated',
             'values': [4, 2, 6]},
        ],
    },
}

_SPEC_REFERENCE = '''# Plot spec reference (`imagelayout-cli plot schema`)

A spec describes one editable plot as plain JSON — the same data the
Plot Editor stores in a `*.ilmplot.svg` file. `plot create` writes the
file, `plot inspect` prints it back, `plot edit` applies an RFC 7386
merge patch, `plot export` renders figure formats (pdf/svg/png/tiff/jpg).
Unknown top-level keys are rejected.

## Top level

- `chart` (string, **required** for create): one of %s
- `title` (string, default `""`); `width_mm`/`height_mm` (default 90×65)
- `columns` (array, **required**, ≥ 1): worksheet columns, below
- `plot_columns` (array of int): plotted columns, default = all
- `overrides` (object): styling, below. Omit for defaults
- `info` (object): read-only, emitted by `inspect`, ignored on input

## Columns

Each column: `{"designation", "long_name"?, "units"?, "comments"?,
"values"?}`. `values` is a row-major array of numbers, strings or null;
numeric strings are read like typed cells (`"3"` → 3). `comments` is the
series label, `long_name`+`units` the axis title.

Designations: %s. Pairing: each Y (or Function) column takes the nearest
X/Label column to its **left**; `yErr` attaches to the nearest Y on its
left; a `Label` column makes a categorical axis. A `Function` column
plots a formula typed in its **first** cell (other cells ignored):
`y=f(x)` by default, `x=g(y)` with an `x=` prefix, `=` alone also means
`y=…`. Grammar: digits, `x`/`y`, `+ - * / ^ ( ) { }`, implicit
multiplication (`2x`, `(x+1)(x-1)`), `**` = `^`, LaTeX-style functions
(`\\sin \\cos \\tan \\arcsin \\asin \\arccos \\acos \\arctan \\atan
\\sinh \\cosh \\tanh \\exp \\ln \\log \\lg \\sqrt \\abs`), constants
(`\\pi \\e`), bases (`\\log_2(…)`, `\\log_{10}(…)`). `y=3` draws a
horizontal line, `x=3` a vertical one. Function curves become ordinary
sampled lines on `pure_line`, `pure_scatters`, `line_scatters`,
`step_line` only. `plot_columns` and `overrides.series` keys are
**column indices** (see `info.items[].column`).

## Overrides (the useful subset)

```json
{"xlabel": "time (s)", "xlim": [0, 100], "legend": true,
 "legend_location": "upper right", "grid": true, "palette": "wong",
 "legend_text": "\\l(1) %%(1)\\nplain note $\\alpha$",
 "series": {"1": {"label": "fit", "color": "#d62728",
                  "linewidth_pt": 2, "linestyle": "--", "marker": "o",
                  "legend": false}}}
```

- `xlabel`/`ylabel`/`grid`/`legend` (bool)/`legend_location`: `best`,
  `upper right`, `upper left`, `lower left`, `lower right`, `right`,
  `center left`, `center right`, `lower center`, `upper center`,
  `center`, `outside right`.
- `xlim`/`ylim`: `[lo, hi]`; function curves re-sample to span them.
- `legend_text`: one row per line; a **leading** run of `\\l(n)` draws
  the n-th item's symbol (`B`/`S` = fill band/span), `%%(n)` its label,
  `$…$` math; no `\\l` = plain text; deleting a line hides the entry.
- `palette`: `default`, `wong`, `blue-pink`, `blue-red`,
  `blue-red-preserve-ends`, `purple-brown`, `ocean`, `rainbow`,
  `colorful`, `high-moderate-low`, `_stacked_wong`, `custom:<name>`.
- `series`: keyed by **column index**; `label`, `color` (`#rrggbb`),
  `linewidth_pt`, `linestyle` (`- -- -. : ''`), `marker`
  (`'' o s ^ v D + x .`), `markersize_pt`, `legend` (`false` hides).
- `style` and the kind options (`violin`, `histogram`, `ridgeline`,
  `stacked`, `bands`, `spans`, `fills`, `annotations`, `brackets`,
  `bar_labels`, `heatmap`): see the `overrides` block `inspect` prints
  from an existing styled file.

## `plot edit` merge patch

RFC 7386: objects merge recursively, `null` deletes a key, arrays and
scalars replace. `info` is ignored. `columns` may also be an object
keyed by column index: an existing index merge-patches that column, the
index equal to the column count appends a column (`designation`
required), anything else errors.

## Examples

```json
%s
```

```json
%s
```
''' % (', '.join(sorted(CHART_KIND)),
       ', '.join(DESIGNATIONS),
       _spec_reference_json('line_with_function'),
       _spec_reference_json('grouped_column'))


SPEC_REFERENCE_MD = _SPEC_REFERENCE
