"""Standalone entry point for the ILM Plot Editor.

``main(argv)`` builds its own ``QApplication`` (the editor always runs in its
own process — either via ``plot_editor_main.py`` or the frozen
``ImageLayoutManager.exe --plot-editor`` dispatch in ``main.py``), shows the
standalone Plot Editor shell (menu bar and hero toolbar styled by ILM's
shared theme; all actions emit placeholder signals) and runs the event
loop.
"""

from __future__ import annotations

import argparse
import sys


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        prog='ilm-plot-editor',
        description='ILM Plot Editor — standalone editor shell.')
    parser.add_argument('file', nargs='?', default=None,
                        help='ILM plot (*.ilmplot.svg) to open')
    parser.add_argument('--ilm-copy', metavar='PATH', default=None,
                        help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([sys.argv[0]])
    app.setApplicationName('Plot Editor')

    from . import chrome
    chrome.apply_app_style(app)

    from .window import PlotEditorWindow
    win = PlotEditorWindow()
    if args.file:
        win.open_paths([args.file])
    if args.ilm_copy:
        from .ilm_bridge import is_ilm_copy_path
        if is_ilm_copy_path(args.ilm_copy):
            try:
                win.open_copy(args.ilm_copy, title='Plot from ILM')
            finally:
                try:
                    import os
                    os.unlink(args.ilm_copy)
                except OSError:
                    pass
    win.show()
    return app.exec()
