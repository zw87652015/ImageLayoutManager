import sys
import os

# --- DLL Path Fix for PyInstaller + PyQt6 on Windows ---
# PyInstaller's dependency scanner can bundle DLLs (like icuuc.dll) that
# shadow the system copies with an ABI-incompatible version, causing
# ERROR_PROC_NOT_FOUND (WinError 127).  The build script removes these
# rogue DLLs; this block ensures the remaining Qt6 DLLs are findable.
if getattr(sys, "frozen", False) and sys.platform == "win32":
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    exe_dir = os.path.dirname(sys.executable)

    dll_dirs = [
        os.path.join(base_dir, "PyQt6", "Qt6", "bin"),
        base_dir,
        exe_dir,
    ]
    existing = [d for d in dll_dirs if os.path.isdir(d)]

    # Prepend to PATH
    path = os.environ.get("PATH", "")
    os.environ["PATH"] = ";".join(existing) + ";" + path

    # os.add_dll_directory (Python ≥ 3.8)
    if hasattr(os, "add_dll_directory"):
        for d in existing:
            try:
                os.add_dll_directory(d)
            except Exception:
                pass
# -------------------------------------------------------

# Add src to python path to allow imports if running from root
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QSurfaceFormat
from src.app.main_window import MainWindow
from src.app.theme import build_palette, apply_font_scale, LIGHT
from src.utils import crash_recovery

def main():
    # File logging + crash guard must exist before any Qt code runs so
    # even import-time/startup failures leave a trace. The excepthook is
    # re-armed with a rescue callback once the window exists.
    logger = crash_recovery.setup_logging()
    crash_recovery.install_excepthook()
    from src.version import APP_VERSION
    logger.info("ImageLayoutManager %s starting (pid %d)", APP_VERSION, os.getpid())
    # ``--agent-server`` enables the JSON-RPC server at launch. We strip it
    # from ``argv`` *before* handing off to ``QApplication`` so Qt's own
    # argument parser doesn't choke on it, and before the positional-file
    # check below treats it as a path to open.
    enable_agent_server = "--agent-server" in sys.argv
    if enable_agent_server:
        sys.argv = [a for a in sys.argv if a != "--agent-server"]

    fmt = QSurfaceFormat()
    fmt.setSamples(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    # AA_UseHighDpiPixmaps was removed in PyQt6 (enabled by default)
    app = QApplication(sys.argv)
    app.setApplicationName("Academic Figure Layout")

    # Restore persisted font scale before building any widgets so the
    # initial layout uses the user's preferred size.
    from PyQt6.QtCore import QSettings
    _settings = QSettings("AcademicFigureLayout", "ImageLayoutManager")
    try:
        _scale = float(_settings.value("ui/font_scale", 1.0))
    except (TypeError, ValueError):
        _scale = 1.0
    # Apply initial theme (light) + persisted font scale together.
    app.setPalette(build_palette(LIGHT))
    apply_font_scale(app, _scale, LIGHT)

    window = MainWindow()

    # Re-arm the crash hook with a rescue callback: on an unhandled
    # exception, every dirty tab is snapshotted to the recovery dir
    # before the crash dialog is shown.
    crash_recovery.install_excepthook(window.rescue_save_all)

    # Open a file passed as a command-line argument (double-click in Explorer).
    # Windows Explorer calls: ImageLayoutManager.exe "C:\path\to\file.figpack"
    if len(sys.argv) > 1:
        cli_path = sys.argv[1]
        if os.path.isfile(cli_path):
            window.open_file_from_cli(cli_path)

    # Honour the persisted "Auto-start MCP Server" preference unless the
    # caller already forced it on via --agent-server.
    if not enable_agent_server:
        autostart = _settings.value("mcp_autostart", False)
        if isinstance(autostart, str):
            autostart = autostart.lower() not in ("false", "0", "no", "")
        if autostart:
            enable_agent_server = True

    if enable_agent_server:
        window.toggle_agent_server(True)

    window.show()

    # Offer to restore autosave snapshots left behind by a crashed
    # session. Deferred one event-loop turn so the window paints first.
    from PyQt6.QtCore import QTimer
    QTimer.singleShot(0, window.offer_recovery)

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
