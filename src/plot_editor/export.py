"""Plot export: native ILM Plot documents and matplotlib formats (no Qt)."""

import os
import tempfile

from .document import (LineSeries, PlotDocument, StackCategory,
                       StackOptions, ViolinGroup)
from .i18n import tr
from .plot_data import tick_label_map
from .plotting import stack_offsets
from . import palettes, render

EXPORT_FORMATS = {
    'ilmplot': ('ILM Plot (*.ilmplot.svg)', '.ilmplot.svg'),
    'pdf': ('PDF (*.pdf)', '.pdf'),
    'svg': ('SVG (*.svg)', '.svg'),
    'png': ('PNG (*.png)', '.png'),
    'tiff': ('TIFF (*.tif *.tiff)', '.tif'),
    'jpg': ('JPEG (*.jpg *.jpeg)', '.jpg'),
}
RASTER_DPI = 300

_ACCEPTED = {
    'ilmplot': ('.ilmplot.svg',),
    'pdf': ('.pdf',),
    'svg': ('.svg',),
    'png': ('.png',),
    'tiff': ('.tif', '.tiff'),
    'jpg': ('.jpg', '.jpeg'),
}

_STYLE = {
    'pure_line': ('-', ''),
    'pure_scatters': ('', 'o'),
    'line_scatters': ('-', 'o'),
    'stacked_line': ('-', ''),
}

# Chart key → (document kind, percent flag for stacked column charts).
CHART_KIND = {
    'pure_line': ('line', None),
    'pure_scatters': ('line', None),
    'line_scatters': ('line', None),
    'stacked_line': ('line', None),
    'ridgeline': ('ridgeline', None),
    'violin': ('violin', None),
    'column': ('stacked_column', None),
    'stacked_column_pct': ('stacked_column', True),
    'stacked_column': ('stacked_column', False),
}


def with_suffix(path, key):
    """Return *path* with the format's suffix appended when missing."""
    accepted = _ACCEPTED[key]
    lower = path.lower()
    if not lower.endswith(accepted):
        if key == 'ilmplot' and lower.endswith('.svg'):
            path = path[:-4]
        path += EXPORT_FORMATS[key][1]
    return path


def document_from_plot(items, chart_key, title='', *,
                       palette=None, palette_reverse=False):
    """Build a validated ``PlotDocument`` from the chart's items.

    ``items`` are ``Series`` (line kinds/ridgeline), ``Group`` (violin)
    or ``Category`` (stacked column) objects from ``plot_data``.
    ``palette``/``palette_reverse`` pick the colour theme; per-item
    colours are not applied here (the overrides layer does that).
    """
    kind, percent = CHART_KIND.get(chart_key, (None, None))
    if kind is None:
        raise ValueError(tr('err_unknown_chart', value=repr(chart_key)))
    colors = palettes.theme_colors(palette, len(items),
                                   chart_key, reverse=palette_reverse)
    doc = PlotDocument()
    doc.title = title
    if kind == 'violin':
        doc.kind = 'violin'
        doc.series = []
        doc.xlabel = items[0].x_label
        doc.ylabel = items[0].y_label
        doc.legend = False
        doc.groups = [ViolinGroup(id='g%d' % i, label=g.label,
                                  values=list(g.values),
                                  color=colors[i])
                      for i, g in enumerate(items)]
        return doc.validate()
    if kind == 'stacked_column':
        doc.kind = 'stacked_column'
        doc.series = []
        doc.xlabel = items[0].x_label
        doc.ylabel = 'Percentage (%)' if percent else items[0].y_label
        doc.legend = True
        doc.stacked = StackOptions(percent=bool(percent),
                                   grouped=chart_key == 'column')
        doc.categories = [StackCategory(
            id='c%d' % i, label=c.label,
            values=list(c.values), color=colors[i],
            yerr=list(c.yerr) if c.yerr is not None else None,
            yerr_minus=list(c.yerr_minus)
            if c.yerr_minus is not None else None,
            yerr_plus=list(c.yerr_plus)
            if c.yerr_plus is not None else None)
            for i, c in enumerate(items)]
        bar_labels = items[0].bar_labels
        if bar_labels:
            doc.x_tick_labels = [[float(i), t]
                                 for i, t in enumerate(bar_labels)]
        return doc.validate()
    linestyle, marker = _STYLE.get(chart_key, ('-', ''))
    offsets = stack_offsets(items)
    doc.xlabel = items[0].x_label
    doc.ylabel = items[0].y_label
    ticks = tick_label_map(items)
    doc.x_tick_labels = [[p, ticks[p]] for p in sorted(ticks)] or None
    if kind == 'ridgeline':
        doc.kind = 'ridgeline'
        doc.legend = False
    else:
        doc.legend = len(items) > 1
    doc.series = []
    for i, s in enumerate(items):
        y = s.y
        if chart_key == 'stacked_line' and i > 0:
            y = tuple(v + offsets[i] for v in y)
        doc.series.append(LineSeries(
            id='s%d' % i, label=s.label,
            x=list(s.x), y=list(y),
            color=colors[i],
            linewidth_pt=1.5, linestyle=linestyle, marker=marker,
            markersize_pt=6.0,
            yerr=(list(s.yerr)
                  if kind != 'ridgeline' and s.yerr is not None
                  else None),
            yerr_minus=(list(s.yerr_minus)
                        if kind != 'ridgeline'
                        and s.yerr_minus is not None else None),
            yerr_plus=(list(s.yerr_plus)
                       if kind != 'ridgeline'
                       and s.yerr_plus is not None else None)))
    return doc.validate()


def _atomic_write(path, write):
    """Write to a temp sibling, fsync, then ``os.replace`` into place."""
    parent = os.path.dirname(os.path.abspath(path))
    os.makedirs(parent, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=parent,
                               prefix='.' + os.path.basename(path),
                               suffix='.tmp')
    try:
        with os.fdopen(fd, 'wb') as fh:
            write(fh)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def export_plot(document, path, key):
    """Atomically write *document* in format *key* to *path*.

    Everything goes through the native renderer: ``ilmplot`` embeds the
    document metadata; other formats use ``render.export_document`` so
    exports match the preview exactly.
    """
    if key == 'ilmplot':
        render.save_document(document, path)
        return
    if key not in EXPORT_FORMATS:
        raise ValueError(tr('err_unknown_export', value=repr(key)))
    fmt = 'jpeg' if key == 'jpg' else key
    render.export_document(document, path, fmt, dpi=RASTER_DPI)
