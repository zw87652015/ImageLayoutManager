import sys
import os

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
    window.show()
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
