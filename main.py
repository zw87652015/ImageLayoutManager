import sys
import os

# --- DLL Path Fix for PyInstaller + PyQt6 on Windows ---
if getattr(sys, "frozen", False) and sys.platform == "win32":
    # In PyInstaller, sys._MEIPASS is the root of the bundled files
    base_dir = getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    
    # Try all common locations for Qt binaries in both --onefile and --onedir layouts
    dll_dirs = [
        base_dir,
        os.path.join(base_dir, "_internal"),
        os.path.join(base_dir, "PyQt6", "Qt6", "bin"),
        os.path.join(base_dir, "_internal", "PyQt6", "Qt6", "bin"),
    ]
    
    # Prepend to PATH for legacy DLL loading (fallback)
    existing_path = os.environ.get("PATH", "")
    new_paths = [d for d in dll_dirs if os.path.isdir(d)]
    if new_paths:
        os.environ["PATH"] = ";".join(new_paths) + ";" + existing_path
    
    # Use modern os.add_dll_directory
    if hasattr(os, "add_dll_directory"):
        for d in new_paths:
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
from src.app.theme import build_palette, get_stylesheet, LIGHT

def main():
    fmt = QSurfaceFormat()
    fmt.setSamples(8)
    QSurfaceFormat.setDefaultFormat(fmt)

    # AA_UseHighDpiPixmaps was removed in PyQt6 (enabled by default)
    app = QApplication(sys.argv)
    app.setApplicationName("Academic Figure Layout")

    # Apply initial theme (light)
    app.setPalette(build_palette(LIGHT))
    app.setStyleSheet(get_stylesheet(LIGHT))
    
    window = MainWindow()

    # Open a .figlayout file passed as a command-line argument.
    # Windows Explorer calls: ImageLayoutManager.exe "C:\path\to\file.figlayout"
    if len(sys.argv) > 1:
        cli_path = sys.argv[1]
        if os.path.isfile(cli_path):
            window.open_file_from_cli(cli_path)

    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
