"""Standalone entry point for the ILM Plot Editor.

``main(argv)`` builds its own ``QApplication`` (the editor always runs in its
own process — either via ``plot_editor_main.py`` or the frozen
``ImageLayoutManager.exe --plot-editor`` dispatch in ``main.py``), restores
the persisted language/theme/font-scale preferences shared with ILM, shows
the editor and runs the event loop.
"""

from __future__ import annotations

import argparse
import os
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='ilm-plot-editor',
        description='ILM Plot Editor — create and edit editable line plots '
                    '(*.ilmplot.svg) for ImageLayoutManager.')
    parser.add_argument('file', nargs='?', default=None,
                        help='optional *.ilmplot.svg / *.svg file to open')
    args = parser.parse_args(argv)

    from PyQt6.QtWidgets import QApplication
    from PyQt6.QtCore import QSettings
    from src.app.i18n import set_language
    from src.app.theme import build_palette, apply_font_scale, LIGHT, DARK

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName('ILM Plot Editor')

    settings = QSettings('AcademicFigureLayout', 'ImageLayoutManager')
    lang = settings.value('language', 'zh')
    set_language(lang if lang in ('en', 'zh') else 'en')
    theme = settings.value('theme', LIGHT)
    if theme not in (LIGHT, DARK):
        theme = LIGHT
    try:
        scale = float(settings.value('ui/font_scale', 1.0))
    except (TypeError, ValueError):
        scale = 1.0
    app.setPalette(build_palette(theme))
    apply_font_scale(app, scale, theme)

    from .window import PlotEditorWindow
    win = PlotEditorWindow()
    win.theme_combo.setCurrentIndex(0 if theme == LIGHT else 1)
    if args.file:
        if not os.path.isfile(args.file):
            parser.exit(2, f'error: no such file: {args.file}\n')
        win.open_path(args.file)
    win.show()
    return app.exec()
