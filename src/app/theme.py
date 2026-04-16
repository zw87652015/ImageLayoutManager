import os
from PyQt6.QtGui import QPalette, QColor
from PyQt6.QtCore import Qt

# Resolve check mark SVG: works both in dev and inside a PyInstaller .app bundle.
def _assets_dir() -> str:
    import sys
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        # Running inside a PyInstaller bundle; data files land at _MEIPASS root
        base = sys._MEIPASS
    else:
        base = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base, "assets").replace("\\", "/")

_CHECK_ON = f"{_assets_dir()}/check_on.svg"

DARK = "dark"
LIGHT = "light"

_DARK_PALETTE = {
    QPalette.ColorRole.Window:          "#1E1E1E",
    QPalette.ColorRole.WindowText:      "#E0E0E0",
    QPalette.ColorRole.Base:            "#121212",
    QPalette.ColorRole.AlternateBase:   "#1E1E1E",
    QPalette.ColorRole.ToolTipBase:     "#2D2D2D",
    QPalette.ColorRole.ToolTipText:     "#E0E0E0",
    QPalette.ColorRole.Text:            "#E0E0E0",
    QPalette.ColorRole.Button:          "#2D2D2D",
    QPalette.ColorRole.ButtonText:      "#E0E0E0",
    QPalette.ColorRole.BrightText:      "#FF4444",
    QPalette.ColorRole.Link:            "#4A90E2",
    QPalette.ColorRole.Highlight:       "#4A90E2",
    QPalette.ColorRole.HighlightedText: "#FFFFFF",
    QPalette.ColorRole.PlaceholderText: "#555555",
}

_LIGHT_PALETTE = {
    QPalette.ColorRole.Window:          "#F5F5F5",
    QPalette.ColorRole.WindowText:      "#1A1A1A",
    QPalette.ColorRole.Base:            "#FFFFFF",
    QPalette.ColorRole.AlternateBase:   "#F0F0F0",
    QPalette.ColorRole.ToolTipBase:     "#FFFFCC",
    QPalette.ColorRole.ToolTipText:     "#1A1A1A",
    QPalette.ColorRole.Text:            "#1A1A1A",
    QPalette.ColorRole.Button:          "#E8E8E8",
    QPalette.ColorRole.ButtonText:      "#1A1A1A",
    QPalette.ColorRole.BrightText:      "#CC0000",
    QPalette.ColorRole.Link:            "#1A6EC7",
    QPalette.ColorRole.Highlight:       "#1A6EC7",
    QPalette.ColorRole.HighlightedText: "#FFFFFF",
    QPalette.ColorRole.PlaceholderText: "#AAAAAA",
}

_DARK_QSS = """
    QMainWindow, QWidget {
        background-color: #1E1E1E;
        color: #E0E0E0;
        font-family: -apple-system, "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 13px;
    }
    QSplitter::handle {
        background: #2D2D2D;
        width: 2px;
    }
    QSplitter::handle:hover { background: #4A90E2; }
    QMainWindow::separator { background: transparent; }

    QToolBar {
        border: none;
        background: #191919;
        padding: 8px 12px;
        border-bottom: 1px solid #2D2D2D;
    }
    QToolBar QToolButton {
        border-radius: 4px; padding: 6px 12px;
        color: #CCCCCC; background: transparent; margin-right: 4px;
    }
    QToolBar QToolButton:hover  { background: #333333; color: #FFFFFF; }
    QToolBar QToolButton:pressed { background: #4A90E2; color: #FFFFFF; }

    QMenuBar { background-color: #191919; color: #E0E0E0; }
    QMenuBar::item { background-color: transparent; padding: 4px 10px; }
    QMenuBar::item:selected { background-color: #333333; border-radius: 4px; }
    QMenu { background-color: #2D2D2D; border: 1px solid #3D3D3D; border-radius: 4px; padding: 4px 0; }
    QMenu::item { padding: 6px 24px; }
    QMenu::item:selected { background-color: #4A90E2; color: white; }

    QGroupBox {
        font-weight: 600; font-size: 12px; color: #888888;
        border: 1px solid #333333; border-radius: 8px;
        margin-top: 14px; padding-top: 12px; background: #252525;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 10px; padding: 0 5px; color: #888888;
    }

    QScrollArea { border: none; background: transparent; }
    QScrollArea QWidget { background: transparent; }
    QGroupBox QWidget { background: transparent; }
    QGroupBox QLabel { background: transparent; }

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background: #121212; border: 1px solid #333333;
        border-radius: 4px; padding: 5px 8px; color: #E0E0E0; min-height: 22px;
    }
    QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover { border: 1px solid #4A90E2; }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #4A90E2; background: #1A1A1A; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background-color: #121212; border: 1px solid #333333;
        selection-background-color: #4A90E2;
    }

    QPushButton {
        background: #333333; border: 1px solid #444444;
        border-radius: 4px; padding: 6px 12px; color: #E0E0E0; font-weight: 500;
    }
    QPushButton:hover  { background: #444444; border-color: #555555; }
    QPushButton:pressed { background: #222222; }

    QScrollBar:vertical   { background: transparent; width: 12px; }
    QScrollBar::handle:vertical {
        background: #444444; border-radius: 6px; min-height: 20px; margin: 2px;
    }
    QScrollBar::handle:vertical:hover { background: #666666; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    QScrollBar:horizontal { background: transparent; height: 12px; }
    QScrollBar::handle:horizontal {
        background: #444444; border-radius: 6px; min-width: 20px; margin: 2px;
    }
    QScrollBar::handle:horizontal:hover { background: #666666; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

    QLabel { color: #CCCCCC; }

    QCheckBox { spacing: 6px; }
    QCheckBox::indicator {
        width: 14px; height: 14px;
        border: 2px solid #555555; border-radius: 3px;
        background-color: #2D2D2D;
    }
    QCheckBox::indicator:hover { border-color: #4A90E2; }
    QCheckBox::indicator:checked {
        border: none;
        image: url(__CHECK_ON__);
    }
    QGroupBox::indicator {
        width: 14px; height: 14px;
        border: 2px solid #555555; border-radius: 3px;
        background-color: #2D2D2D;
    }
    QGroupBox::indicator:checked {
        border: none;
        image: url(__CHECK_ON__);
    }

    QStatusBar { background: #191919; color: #888888; border-top: 1px solid #2D2D2D; }
    QStatusBar::item { border: none; }
"""

_LIGHT_QSS = """
    QMainWindow, QWidget {
        background-color: #F5F5F5;
        color: #1A1A1A;
        font-family: -apple-system, "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 13px;
    }
    QSplitter::handle { background: #DDDDDD; width: 2px; }
    QSplitter::handle:hover { background: #1A6EC7; }
    QMainWindow::separator { background: transparent; }

    QToolBar {
        border: none;
        background: #EFEFEF;
        padding: 8px 12px;
        border-bottom: 1px solid #DDDDDD;
    }
    QToolBar QToolButton {
        border-radius: 4px; padding: 6px 12px;
        color: #444444; background: transparent; margin-right: 4px;
    }
    QToolBar QToolButton:hover  { background: #DDDDDD; color: #1A1A1A; }
    QToolBar QToolButton:pressed { background: #1A6EC7; color: #FFFFFF; }

    QMenuBar { background-color: #EFEFEF; color: #1A1A1A; }
    QMenuBar::item { background-color: transparent; padding: 4px 10px; }
    QMenuBar::item:selected { background-color: #DDDDDD; border-radius: 4px; }
    QMenu { background-color: #FFFFFF; border: 1px solid #CCCCCC; border-radius: 4px; padding: 4px 0; }
    QMenu::item { padding: 6px 24px; }
    QMenu::item:selected { background-color: #1A6EC7; color: white; }

    QGroupBox {
        font-weight: 600; font-size: 12px; color: #666666;
        border: 1px solid #DDDDDD; border-radius: 8px;
        margin-top: 14px; padding-top: 12px; background: #FFFFFF;
    }
    QGroupBox::title {
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 10px; padding: 0 5px; color: #666666;
    }

    QScrollArea { border: none; background: transparent; }
    QScrollArea QWidget { background: transparent; }
    QGroupBox QWidget { background: transparent; }
    QGroupBox QLabel { background: transparent; }

    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background: #FFFFFF; border: 1px solid #CCCCCC;
        border-radius: 4px; padding: 5px 8px; color: #1A1A1A; min-height: 22px;
    }
    QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover { border: 1px solid #1A6EC7; }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border: 1px solid #1A6EC7; background: #F8F8FF; }
    QComboBox::drop-down { border: none; width: 20px; }
    QComboBox QAbstractItemView {
        background-color: #FFFFFF; border: 1px solid #CCCCCC;
        selection-background-color: #1A6EC7; selection-color: #FFFFFF;
    }

    QPushButton {
        background: #E8E8E8; border: 1px solid #CCCCCC;
        border-radius: 4px; padding: 6px 12px; color: #1A1A1A; font-weight: 500;
    }
    QPushButton:hover  { background: #D8D8D8; border-color: #BBBBBB; }
    QPushButton:pressed { background: #C8C8C8; }

    QScrollBar:vertical   { background: transparent; width: 12px; }
    QScrollBar::handle:vertical {
        background: #BBBBBB; border-radius: 6px; min-height: 20px; margin: 2px;
    }
    QScrollBar::handle:vertical:hover { background: #999999; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    QScrollBar:horizontal { background: transparent; height: 12px; }
    QScrollBar::handle:horizontal {
        background: #BBBBBB; border-radius: 6px; min-width: 20px; margin: 2px;
    }
    QScrollBar::handle:horizontal:hover { background: #999999; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

    QLabel { color: #333333; }

    QCheckBox { spacing: 6px; }
    QCheckBox::indicator {
        width: 14px; height: 14px;
        border: 2px solid #BBBBBB; border-radius: 3px;
        background-color: #FFFFFF;
    }
    QCheckBox::indicator:hover { border-color: #1A6EC7; }
    QCheckBox::indicator:checked {
        border: none;
        image: url(__CHECK_ON__);
    }
    QGroupBox::indicator {
        width: 14px; height: 14px;
        border: 2px solid #BBBBBB; border-radius: 3px;
        background-color: #FFFFFF;
    }
    QGroupBox::indicator:checked {
        border: none;
        image: url(__CHECK_ON__);
    }

    QStatusBar { background: #EFEFEF; color: #666666; border-top: 1px solid #DDDDDD; }
    QStatusBar::item { border: none; }
"""

_LAYERS_TREE_DARK = """
    QTreeWidget { background-color: transparent; border: none; outline: none; }
    QTreeWidget::item { padding: 3px 2px; }
    QTreeWidget::item:selected { background-color: #2A3F5F; color: #4A90E2; border-radius: 4px; }
    QTreeWidget::item:hover:!selected { background-color: #2D2D2D; }
    QTreeWidget::branch { background: transparent; }
"""

_LAYERS_TREE_LIGHT = """
    QTreeWidget { background-color: transparent; border: none; outline: none; }
    QTreeWidget::item { padding: 3px 2px; }
    QTreeWidget::item:selected { background-color: #D0E4F8; color: #1A6EC7; border-radius: 4px; }
    QTreeWidget::item:hover:!selected { background-color: #EBEBEB; }
    QTreeWidget::branch { background: transparent; }
"""


def build_palette(theme: str) -> QPalette:
    colors = _DARK_PALETTE if theme == DARK else _LIGHT_PALETTE
    palette = QPalette()
    for role, hex_color in colors.items():
        palette.setColor(role, QColor(hex_color))
    return palette


def get_stylesheet(theme: str) -> str:
    raw = _DARK_QSS if theme == DARK else _LIGHT_QSS
    return raw.replace("__CHECK_ON__", _CHECK_ON)


def get_layers_tree_stylesheet(theme: str) -> str:
    return _LAYERS_TREE_DARK if theme == DARK else _LAYERS_TREE_LIGHT
