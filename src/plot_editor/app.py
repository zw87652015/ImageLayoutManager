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

    from . import chrome as _chrome, i18n as _i18n
    _i18n.set_language(_chrome.saved_language())
    app.setApplicationName(_i18n.tr('app_name'))

    # PyQt6 aborts the process on an unhandled exception escaping a Qt
    # slot — convert it into a warning dialog instead (guarded against
    # recursion and a missing app).
    _handling = {'active': False}

    def _excepthook(exc_type, exc, tb):
        import traceback as _tb
        _tb.print_exception(exc_type, exc, tb)
        if _handling['active']:
            return
        _handling['active'] = True
        try:
            from PyQt6.QtWidgets import QApplication, QMessageBox
            if QApplication.instance() is not None:
                from .i18n import tr
                QMessageBox.warning(None, tr('app_name'),
                                    tr('msg_unexpected', error=exc))
        except Exception:
            pass
        finally:
            _handling['active'] = False

    sys.excepthook = _excepthook

    _chrome.apply_app_style(app)

    from .window import PlotEditorWindow
    win = PlotEditorWindow()
    if args.file:
        win.open_paths([args.file])
    if args.ilm_copy:
        from .ilm_bridge import is_ilm_copy_path
        if is_ilm_copy_path(args.ilm_copy):
            try:
                win.open_copy(args.ilm_copy, title=_i18n.tr(
                    'plot_from_ilm'))
            finally:
                try:
                    import os
                    os.unlink(args.ilm_copy)
                except OSError:
                    pass
    win.show()
    return app.exec()
