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

def main():
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

    # Open a file passed as a command-line argument (double-click in Explorer).
    # Windows Explorer calls: ImageLayoutManager.exe "C:\path\to\file.figpack"
    if len(sys.argv) > 1:
        cli_path = sys.argv[1]
        if os.path.isfile(cli_path):
            window.open_file_from_cli(cli_path)

    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
