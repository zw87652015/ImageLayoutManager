"""Plot Editor action and chart metadata.

Pure Python — no Qt imports. ``PlotEditorWindow`` builds menus and the
toolbar from these tables; handlers are wired in future tasks.
"""

from dataclasses import dataclass


NATIVE_PLOT_FILTER = 'ILM Plot (*.ilmplot.svg)'
NATIVE_PLOT_SUFFIX = '.ilmplot.svg'


@dataclass(frozen=True)
class ActionSpec:
    key: str
    text: str
    shortcut: str = ''
    icon: str = ''
    tooltip: str = ''


@dataclass(frozen=True)
class ChartType:
    key: str
    text: str


@dataclass(frozen=True)
class ChartGroup:
    key: str
    text: str
    charts: 'tuple[ChartType, ...]' = ()


CHART_GROUPS = (
    ChartGroup('line', 'Line', (
        ChartType('pure_line', 'Pure Line'),
        ChartType('pure_scatters', 'Pure Scatters'),
        ChartType('line_scatters', 'Line + Scatters'),
        ChartType('stacked_line', 'Stacked Line'),
        ChartType('ridgeline', 'Ridgeline'),
    )),
    ChartGroup('violin', 'Distribution', (
        ChartType('violin', 'Violin'),
        ChartType('box', 'Box'),
        ChartType('column_points', 'Column + Points'),
        ChartType('histogram', 'Histogram'),
    )),
    ChartGroup('column', 'Column & Bar', (
        ChartType('column', 'Column'),
        ChartType('stacked_column_pct', '100% Stacked Column'),
        ChartType('stacked_column', 'Stacked Column'),
        ChartType('bar', 'Bar'),
        ChartType('stacked_bar_pct', '100% Stacked Bar'),
        ChartType('stacked_bar', 'Stacked Bar'),
    )),
)

DEFAULT_CHART = ('line', 'pure_line')

ACTIONS = {
    'new': ActionSpec('new', 'New', 'Ctrl+N', 'new',
                      'New plot tab'),
    'open': ActionSpec('open', 'Open…', 'Ctrl+O', 'open',
                       'Open an ILM plot (*.ilmplot.svg)'),
    'save': ActionSpec('save', 'Save', 'Ctrl+S', 'save',
                       'Save the plot and its data (*.ilmplot.svg)'),
    'save_as': ActionSpec('save_as', 'Save As…', 'Ctrl+Shift+S', '',
                          'Save under a new name (*.ilmplot.svg)'),
    'import_data': ActionSpec('import_data', 'Import Data…', '', '',
                              'Not implemented yet'),
    'close': ActionSpec('close', 'Close', 'Ctrl+W', '',
                        'Close the current tab'),
    'quit': ActionSpec('quit', 'Quit', 'Ctrl+Q', '', 'Quit Plot Editor'),
    'undo': ActionSpec('undo', 'Undo', 'Ctrl+Z', 'undo',
                       'Nothing to undo'),
    'redo': ActionSpec('redo', 'Redo', 'Ctrl+Shift+Z', 'redo',
                       'Nothing to redo'),
    'cut': ActionSpec('cut', 'Cut', 'Ctrl+X', '',
                      'Cut the selected cells'),
    'copy': ActionSpec('copy', 'Copy', 'Ctrl+C', '',
                       'Copy the selected cells'),
    'paste': ActionSpec('paste', 'Paste', 'Ctrl+V', '',
                        'Paste cells from the clipboard'),
    'delete': ActionSpec('delete', 'Delete', 'Delete', '',
                         'Clear the selected cells'),
    'select_all': ActionSpec('select_all', 'Select All', 'Ctrl+A', '',
                             'Select all data cells'),
    'plot': ActionSpec('plot', 'Plot', 'Ctrl+Return', 'plot',
                       'Plot the selected columns as the chosen chart '
                       'type'),
    'style': ActionSpec('style', 'Plot Style…', '', '',
                        'Not implemented yet'),
    'figure_size': ActionSpec('figure_size', 'Figure Size…', '', '',
                              'Change the figure width, height and '
                              'aspect ratio'),
    'add_note': ActionSpec('add_note', 'Add Note', '', '',
                           'Add a corner note to the plot'),
    'add_bracket': ActionSpec('add_bracket', 'Add Significance Bracket',
                              '', '',
                              'Add a significance bracket between two '
                              'groups or bars'),
    'add_fill': ActionSpec('add_fill', 'Add Fill…', '', '',
                           'Add a shaded area: a span, or a fill under '
                           'or between curves'),
    'tutorials': ActionSpec('tutorials', 'Tutorials…', 'F1', '',
                            'Guided lessons for the Plot Editor'),
    'shortcuts': ActionSpec('shortcuts', 'Keyboard Shortcuts', '', '',
                            'Not implemented yet'),
    'about': ActionSpec('about', 'About Plot Editor', '', '',
                        'About the Plot Editor'),
    'export_ilmplot': ActionSpec('export_ilmplot',
                                 'ILM Plot (*.ilmplot.svg)…', '', '',
                                 'Export an editable ILM plot'),
    'export_pdf': ActionSpec('export_pdf', 'PDF…', '', '',
                             'Export the plot as PDF'),
    'export_svg': ActionSpec('export_svg', 'SVG…', '', '',
                             'Export the plot as SVG'),
    'export_png': ActionSpec('export_png', 'PNG…', '', '',
                             'Export the plot as PNG'),
    'export_tiff': ActionSpec('export_tiff', 'TIFF…', '', '',
                              'Export the plot as TIFF'),
    'export_jpg': ActionSpec('export_jpg', 'JPEG…', '', '',
                             'Export the plot as JPEG'),
}

HERO_ACTIONS = ('undo', 'redo', 'new', 'open', 'save', 'plot', 'export')

FILE_MENU = ('new', 'open', None, 'save', 'save_as', None, 'import_data',
             'export', None, 'close', 'quit')
EXPORT_MENU = ('export_ilmplot', 'export_pdf', 'export_svg', 'export_png',
               'export_tiff', 'export_jpg')
EDIT_MENU = ('undo', 'redo', None, 'cut', 'copy', 'paste', 'delete', None,
             'select_all')
HELP_MENU = ('tutorials', 'shortcuts', None, 'about')
