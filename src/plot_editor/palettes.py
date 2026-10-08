"""Colour themes for the Plot Editor (Qt-free).

The lists are copied verbatim from NCPlotGenerator
(``mountain_stacked_plot_generator.py`` / ``stacked_column_generator.py``);
``default`` is matplotlib's tab10 cycle — the historical line colours.
"""

import re

from matplotlib.colors import LinearSegmentedColormap, to_hex

_TAB10 = ['#1f77b4', '#ff7f0e', '#2ca02c', '#d62728', '#9467bd',
          '#8c564b', '#e377c2', '#7f7f7f', '#bcbd22', '#17becf']

THEMES = {
    'default': _TAB10,
    'wong': ['#000000', '#E69F00', '#56B4E9', '#009E73',
             '#F0E442', '#0072B2', '#D55E00', '#CC79A7'],
    'blue-pink': ['#104e8b', '#376b9e', '#5f89b1', '#afc3d8',
                  '#c5e9e3', '#d7e1eb', '#f2dada', '#e5b5b5',
                  '#d89090', '#b22222'],
    'blue-red': ['#1b3b70', '#276faf', '#4d9ac7', '#99c8e0',
                 '#d4e6ef', '#f8f4f2', '#fbd8c3', '#f2a481',
                 '#d6604d', '#b5202e', '#700c22'],
    'blue-red-preserve-ends': ['#1b3b70', '#276faf', '#4a6a9a',
                               '#7a78a6', '#a07c93', '#b56e6e',
                               '#d6604d', '#b5202e', '#700c22'],
    'purple-brown': ['#4e659b', '#8a8cbf', '#b8a8cf', '#e7bcc6',
                     '#fdcf9e', '#efa484', '#b6766c'],
    'ocean': ['#081D58', '#253494', '#225EA8', '#1D91C0',
              '#41B6C4', '#7FCDBB', '#C7E9B4', '#EDF8B1'],
    'rainbow': ['#C0504D', '#D07030', '#C8A020', '#5A9E5A',
                '#3A87A8', '#4A6EB5', '#7B5EA7', '#A85482'],
    'colorful': ['#0072B2', '#E69F00', '#009E73', '#CC79A7',
                 '#56B4E9', '#D55E00', '#F0E442', '#000000'],
    'high-moderate-low': ['#2ECC71', '#F39C12', '#E67E22'],
}

# NCPlot's stacked fallback: Wong order minus black.
STACKED_WONG = ['#0072B2', '#E69F00', '#009E73', '#CC79A7',
                '#56B4E9', '#D55E00', '#F0E442']

# User themes, referenced as ``'custom:<name>'``. Populated by the
# editor window from ``theme_store.ThemeStore``. A plot file also stores
# the resolved list (``PlotOverrides.palette_colors``) so a machine
# without that theme still draws the saved colours. With no snapshot
# and no installed theme, resolution falls back to the chart default.
_CUSTOM = {}

_BAD_NAME_CHARS = re.compile(r'[\\/:*?"<>|]')


def set_custom_themes(mapping):
    """Install the user's custom themes: ``{name: [hex, ...]}``."""
    _CUSTOM.clear()
    for name, colors in (mapping or {}).items():
        _CUSTOM[name] = list(colors)


def custom_theme_names():
    return sorted(_CUSTOM)


def theme_colors_list(name):
    """Colour list for a built-in, ``_stacked_wong`` or custom ref."""
    if name in THEMES:
        return THEMES[name]
    if name == '_stacked_wong':
        return STACKED_WONG
    if isinstance(name, str) and name.startswith('custom:'):
        return _CUSTOM.get(name[7:])
    return None


def valid_theme_ref(name):
    """A usable ``palette`` value: a built-in key or 'custom:<name>'."""
    if not isinstance(name, str):
        return False
    if name in THEMES:
        return True
    if name.startswith('custom:'):
        sub = name[7:]
        return bool(sub.strip()) and len(sub) <= 60 \
            and not _BAD_NAME_CHARS.search(sub)
    return False


def _pick(colors, n, mode, reverse):
    colors = list(colors)
    if reverse:
        colors = colors[::-1]
    if n <= 0:
        return []
    if mode == 'spread' or n > len(colors):
        cmap = LinearSegmentedColormap.from_list('ilm', colors)
        return [to_hex(cmap(i / max(1, n - 1))) for i in range(n)]
    return colors[:n]


def palette_colors(name, n, mode='first', reverse=False):
    """``n`` hex colours from theme *name*.

    ``mode='first'`` takes the first n, interpolating through the list
    when n exceeds it (NCPlot violin behaviour); ``'spread'`` always
    interpolates i/(n-1) across the whole list (NCPlot ridgeline). The
    'default' theme is a cycle — it reproduces the C0…C9 colours for
    every n. ``reverse`` flips the list first.
    """
    if name == 'default':
        if n <= 0:
            return []
        base = _TAB10[::-1] if reverse else _TAB10
        return [base[i % len(base)] for i in range(n)]
    colors = theme_colors_list(name) or _TAB10
    return _pick(colors, n, mode, reverse)


def default_theme(chart_key, n_items):
    """Theme for a chart the user hasn't themed: matplotlib's default colour cycle (tab10) for every chart kind."""
    return 'default'


def custom_theme_missing(name):
    """True when *name* is a ``custom:`` ref with nothing installed."""
    return (isinstance(name, str) and name.startswith('custom:')
            and theme_colors_list(name) is None)


def stamp_palette_colors(overrides):
    """Copy an installed custom theme's colours onto *overrides*.

    Called when a plot file is written. A missing theme keeps a snapshot
    already loaded from the file; any other palette clears it.
    """
    name = getattr(overrides, 'palette', None)
    if not (isinstance(name, str) and name.startswith('custom:')):
        overrides.palette_colors = None
        return
    found = theme_colors_list(name)
    if found:
        overrides.palette_colors = list(found)


def theme_colors(name, n, chart_key='', mode=None, reverse=False,
                 fallback_colors=None):
    """Resolve *name* (a THEMES key, ``'custom:<name>'``, ``None``/``''``
    for the chart default, or the internal ``'_stacked_wong'``) to n hex
    colours.

    ``fallback_colors`` is a custom theme's own list, used only when that
    theme is not installed. Built-in names ignore it. A custom name with
    neither an installation nor a fallback uses the chart default.
    """
    if mode is None:
        from .export import CHART_KIND
        kind = CHART_KIND.get(chart_key, ('line', None))[0]
        mode = 'spread' if kind == 'ridgeline' else 'first'
    if isinstance(name, str) and name.startswith('custom:'):
        colors = _CUSTOM.get(name[7:])
        if colors is None and fallback_colors:
            colors = list(fallback_colors)
        if colors is not None:
            return _pick(colors, n, mode, reverse)
        name = None
    resolved = name if (name in THEMES or name == '_stacked_wong') \
        else default_theme(chart_key, n)
    if resolved == '_stacked_wong':
        base = STACKED_WONG[::-1] if reverse else STACKED_WONG
        return [base[i % len(base)] for i in range(n)]
    return palette_colors(resolved, n, mode, reverse)


def theme_display_key(name):
    """i18n key for a theme's display name (unknown → ``pal_default``)."""
    return 'pal_' + name.replace('-', '_')


def theme_display_name(name):
    """Display text: translated for built-ins, the bare name for
    ``custom:<name>`` refs."""
    if isinstance(name, str) and name.startswith('custom:'):
        return name[7:]
    from .i18n import tr
    return tr(theme_display_key(name))
