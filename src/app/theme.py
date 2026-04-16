"""
Uber-Inspired Design System — PyQt6 QSS Theme (Desktop Adaptation)
===================================================================
Palette
  Near-Black  #1a1a1a   primary actions, focus borders, headings
  Pure White  #ffffff   input/card surfaces
  Off-White   #f7f7f7   panel / window background
  Chip Gray   #ebebeb   toolbar chip buttons
  Border Gray #c8c8c8   default input borders
  Divider     #e0e0e0   separators, group box borders
  Body Gray   #4b4b4b   secondary text, status bar text
  Muted Gray  #999999   placeholder, disabled text

Key desktop adaptations vs. the web guide:
  - Status bar: light (#f5f5f5) not black — footers are a web concept
  - Input borders: subtle (#c8c8c8) at rest, near-black on focus
  - SpinBox arrows: NOT custom-styled so Qt renders them natively
  - Font 12px (compact inspector) instead of 13-18px web sizes
  - Pill radius kept for toolbar chips and main action buttons
  - Inspector inputs: natural height, no forced min-height
"""

STYLESHEET = """

/* ─────────────────────────── GLOBAL BASE ─────────────────────────── */
QWidget {
    font-family: "Segoe UI", system-ui, "Helvetica Neue", Arial, sans-serif;
    font-size: 12px;
    color: #1a1a1a;
    background-color: #f7f7f7;
    selection-background-color: #1a1a1a;
    selection-color: #ffffff;
}

/* ──────────────────────────── MAIN WINDOW ────────────────────────── */
QMainWindow {
    background-color: #f0f0f0;
}

/* ─── Surfaces that should be pure white ─── */
QScrollArea,
QScrollArea > QWidget > QWidget,
Inspector,
QGroupBox {
    background-color: #ffffff;
}

/* ────────────────────────────── MENU BAR ─────────────────────────── */
QMenuBar {
    background-color: #ffffff;
    color: #1a1a1a;
    font-size: 12px;
    font-weight: 500;
    border-bottom: 1px solid #e0e0e0;
    padding: 1px 4px;
}

QMenuBar::item {
    background: transparent;
    padding: 5px 10px;
    border-radius: 999px;
}

QMenuBar::item:selected { background-color: #ebebeb; }
QMenuBar::item:pressed  { background-color: #e0e0e0; }

/* ──────────────────────────── DROP-DOWN MENUS ────────────────────── */
QMenu {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #c8c8c8;
    border-radius: 6px;
    padding: 3px;
}

QMenu::item {
    padding: 6px 18px;
    border-radius: 3px;
    font-size: 12px;
}

QMenu::item:selected { background-color: #1a1a1a; color: #ffffff; }

QMenu::separator {
    height: 1px;
    background: #e8e8e8;
    margin: 3px 8px;
}

/* ─────────────────────────────── TOOLBAR ─────────────────────────── */
QToolBar {
    background-color: #ffffff;
    border-bottom: 1px solid #e0e0e0;
    spacing: 3px;
    padding: 5px 8px;
}

QToolBar::separator {
    width: 1px;
    background-color: #e0e0e0;
    margin: 4px 3px;
}

/* Toolbar action buttons → Chip pill (Uber nav style) */
QToolBar QToolButton {
    background-color: #ebebeb;
    color: #1a1a1a;
    border: none;
    border-radius: 999px;
    padding: 5px 14px;
    font-size: 12px;
    font-weight: 500;
}

QToolBar QToolButton:hover {
    background-color: #e0e0e0;
}

QToolBar QToolButton:pressed,
QToolBar QToolButton:checked {
    background-color: #1a1a1a;
    color: #ffffff;
}

QToolBar QToolButton:disabled {
    background-color: #f5f5f5;
    color: #b8b8b8;
}

QToolBar QToolButton::menu-indicator {
    image: none;
    width: 0;
}

/* ─────────────────────────────── BUTTONS ─────────────────────────── */
QPushButton {
    background-color: #1a1a1a;
    color: #ffffff;
    border: none;
    border-radius: 999px;
    padding: 5px 16px;
    font-size: 12px;
    font-weight: 500;
    min-height: 26px;
}

QPushButton:hover   { background-color: #333333; }
QPushButton:pressed { background-color: #555555; }

QPushButton:disabled {
    background-color: #ebebeb;
    color: #b8b8b8;
}

/* ─────────────────────────────── GROUP BOX ───────────────────────── */
QGroupBox {
    font-size: 12px;
    font-weight: 700;
    color: #1a1a1a;
    border: 1px solid #dcdcdc;
    border-radius: 6px;
    margin-top: 16px;
    padding-top: 6px;
    background-color: #ffffff;
}

QGroupBox::title {
    subcontrol-origin: margin;
    subcontrol-position: top left;
    left: 10px;
    top: -8px;
    padding: 0px 6px;
    background-color: #ffffff;
    color: #1a1a1a;
    font-weight: 700;
    font-size: 12px;
}

/* ────────────────────────────── LINE EDIT ────────────────────────── */
QLineEdit {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    padding: 3px 7px;
    font-size: 12px;
}

QLineEdit:focus    { border: 1px solid #1a1a1a; }
QLineEdit:disabled { background-color: #f5f5f5; color: #999999; border-color: #e0e0e0; }

/* ──────────────────────────── SPIN BOXES ─────────────────────────── */
/* NOTE: ::up-button / ::down-button are intentionally NOT styled so Qt
   renders its native arrows, which are always visible and correct. */
QSpinBox,
QDoubleSpinBox {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    padding: 2px 4px;
    font-size: 12px;
}

QSpinBox:focus,
QDoubleSpinBox:focus {
    border: 1px solid #1a1a1a;
}

QSpinBox:disabled,
QDoubleSpinBox:disabled {
    background-color: #f5f5f5;
    color: #999999;
    border-color: #e0e0e0;
}

/* ─────────────────────────────── COMBO BOX ───────────────────────── */
QComboBox {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    padding: 3px 7px;
    font-size: 12px;
}

QComboBox:focus    { border: 1px solid #1a1a1a; }
QComboBox:disabled { background-color: #f5f5f5; color: #999999; border-color: #e0e0e0; }

QComboBox::drop-down {
    border: none;
    width: 22px;
    background: transparent;
}

QComboBox QAbstractItemView {
    background-color: #ffffff;
    color: #1a1a1a;
    border: 1px solid #c8c8c8;
    border-radius: 4px;
    selection-background-color: #1a1a1a;
    selection-color: #ffffff;
    outline: none;
}

/* ─────────────────────────────── CHECK BOX ───────────────────────── */
QCheckBox {
    color: #1a1a1a;
    font-size: 12px;
    spacing: 6px;
    background: transparent;
}

QCheckBox::indicator {
    width: 14px;
    height: 14px;
    border: 1px solid #888888;
    border-radius: 3px;
    background: #ffffff;
}

QCheckBox::indicator:checked {
    background-color: #1a1a1a;
    border-color: #1a1a1a;
}

QCheckBox::indicator:hover         { border-color: #555555; }
QCheckBox::indicator:checked:hover { background-color: #333333; }

/* ─────────────────────────────── SCROLL AREA ─────────────────────── */
QScrollArea {
    border: none;
    background-color: #ffffff;
}

/* ─────────────────────────────── SCROLL BARS ─────────────────────── */
QScrollBar:vertical {
    background: transparent;
    width: 7px;
    border: none;
    margin: 0;
}

QScrollBar::handle:vertical {
    background: #d0d0d0;
    border-radius: 3px;
    min-height: 20px;
}

QScrollBar::handle:vertical:hover { background: #aaaaaa; }

QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical,
QScrollBar::add-page:vertical,
QScrollBar::sub-page:vertical { background: none; height: 0; }

QScrollBar:horizontal {
    background: transparent;
    height: 7px;
    border: none;
    margin: 0;
}

QScrollBar::handle:horizontal {
    background: #d0d0d0;
    border-radius: 3px;
    min-width: 20px;
}

QScrollBar::handle:horizontal:hover { background: #aaaaaa; }

QScrollBar::add-line:horizontal,
QScrollBar::sub-line:horizontal,
QScrollBar::add-page:horizontal,
QScrollBar::sub-page:horizontal { background: none; width: 0; }

QAbstractScrollArea::corner {
    background-color: #ffffff;
    border: none;
}

/* ─────────────────────────────── SPLITTER ────────────────────────── */
QSplitter::handle           { background-color: #e0e0e0; }
QSplitter::handle:horizontal { width: 1px; }
QSplitter::handle:vertical   { height: 1px; }
QSplitter::handle:hover      { background-color: #aaaaaa; }

/* ───────────────────────────── STATUS BAR ────────────────────────── */
QStatusBar {
    background-color: #f5f5f5;
    color: #4b4b4b;
    font-size: 11px;
    border-top: 1px solid #e0e0e0;
    min-height: 22px;
}

QStatusBar QLabel {
    color: #4b4b4b;
    background: transparent;
    padding: 0 6px;
    font-size: 11px;
}

QStatusBar::item { border: none; }

/* ──────────────────────────────── LABELS ─────────────────────────── */
QLabel {
    color: #1a1a1a;
    background: transparent;
    font-size: 12px;
}

/* ──────────────────────────── GRAPHICS VIEW ──────────────────────── */
QGraphicsView {
    border: none;
    background-color: transparent;
}

/* ────────────────────────────── TOOL TIPS ────────────────────────── */
QToolTip {
    background-color: #1a1a1a;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    padding: 5px 10px;
    font-size: 11px;
}

/* ─────────────────────────── MESSAGE BOXES ───────────────────────── */
QMessageBox { background-color: #ffffff; }
QMessageBox QPushButton { min-width: 72px; }

"""
