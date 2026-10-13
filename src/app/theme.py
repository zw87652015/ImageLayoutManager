"""Design tokens + stylesheet for Image Layout Manager.

All visual values live in ``_TOKENS_LIGHT`` / ``_TOKENS_DARK``. The QSS
template below consumes those tokens via ``%(name)s`` substitution, so
there is exactly one place to change colours, radii or shadows.

Public API (stable — do not change signatures):
    build_palette(theme)            -> QPalette
    get_stylesheet(theme)           -> str  (full QSS)
    get_layers_tree_stylesheet(theme) -> str
    get_tokens(theme)               -> dict (for programmatic use:
                                             canvas grid, placeholder dashes,
                                             layer thumbnails, etc.)
"""
import os
from PyQt6.QtGui import QPalette, QColor, QFont, QFontDatabase

# Resolve assets directory: works both in dev and inside a PyInstaller bundle.
def _assets_dir() -> str:
    import sys
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base, "assets").replace("\\", "/")

_ARROW_DOWN_DARK = f"{_assets_dir()}/arrow_down_dark.svg"
_ARROW_DOWN_LIGHT = f"{_assets_dir()}/arrow_down_light.svg"

DARK = "dark"
LIGHT = "light"

# ── Design tokens ────────────────────────────────────────────────────────
# Source of truth for every colour/radius used by the app: a neutral,
# indigo-accented palette.

_TOKENS_LIGHT = {
    # Surfaces
    "chrome":        "#F6F5F3",
    "panel":         "#FBFAF9",
    "panel_alt":     "#FFFFFF",
    "canvas_bg":     "#E9EAED",
    "surface":       "#FFFFFF",
    "surface_subtle":"#F5F4F1",
    # Borders / dividers
    "border":        "#E3E1DD",
    "border_strong": "#CFCCC6",
    "divider":       "#ECEAE6",
    # Text
    "text":          "#1F1E1C",
    "text_sec":      "#6B6862",
    "text_tert":     "#9A968F",
    "label_caps":    "#8A867F",
    # Interactive states (rgba on the owning surface)
    "hover":         "rgba(31, 30, 28, 0.05)",
    "active":        "rgba(31, 30, 28, 0.09)",
    # Brand
    "accent":        "#4F5BD5",
    "accent_hover":  "#4350C4",
    "accent_press":  "#3640A6",
    "accent_tint":   "rgba(79, 91, 213, 0.10)",
    "accent_ring":   "rgba(79, 91, 213, 0.32)",
    "on_accent":     "#FFFFFF",
    # Semantic
    "danger":        "#D64545",
    "success":       "#2F8F5B",
    # Canvas helpers (not QSS — consumed by cell_item / canvas_view paint)
    "placeholder":   "#B4B0A9",
    "grid_line":     "#D3D4D8",
    # Geometry
    "radius_panel":  "8px",
    "radius_button": "6px",
    "radius_input":  "6px",
}

_TOKENS_DARK = {
    "chrome":        "#18191C",
    "panel":         "#1E1F23",
    "panel_alt":     "#222328",
    "canvas_bg":     "#131417",
    "surface":       "#26282D",
    "surface_subtle":"#222328",
    "border":        "#33353B",
    "border_strong": "#43464D",
    "divider":       "#2A2C31",
    "text":          "#ECEBE8",
    "text_sec":      "#A3A19C",
    "text_tert":     "#75736F",
    "label_caps":    "#8C8A85",
    "hover":         "rgba(255, 255, 255, 0.05)",
    "active":        "rgba(255, 255, 255, 0.09)",
    "accent":        "#8C96FF",
    "accent_hover":  "#A2AAFF",
    "accent_press":  "#6E79E8",
    "accent_tint":   "rgba(140, 150, 255, 0.14)",
    "accent_ring":   "rgba(140, 150, 255, 0.38)",
    "on_accent":     "#0E1030",
    "danger":        "#F07171",
    "success":       "#5CCB8C",
    "placeholder":   "#6F6D69",
    "grid_line":     "#2E3036",
    "radius_panel":  "8px",
    "radius_button": "6px",
    "radius_input":  "6px",
}


# ── QPalette mapping ─────────────────────────────────────────────────────
def _palette_tokens_to_roles(tokens: dict) -> dict:
    """Map design tokens to QPalette roles."""
    return {
        QPalette.ColorRole.Window:          tokens["panel"],
        QPalette.ColorRole.WindowText:      tokens["text"],
        QPalette.ColorRole.Base:            tokens["surface"],
        QPalette.ColorRole.AlternateBase:   tokens["surface_subtle"],
        QPalette.ColorRole.ToolTipBase:     tokens["surface"],
        QPalette.ColorRole.ToolTipText:     tokens["text"],
        QPalette.ColorRole.Text:            tokens["text"],
        QPalette.ColorRole.Button:          tokens["panel_alt"],
        QPalette.ColorRole.ButtonText:      tokens["text"],
        QPalette.ColorRole.BrightText:      tokens["danger"],
        QPalette.ColorRole.Link:            tokens["accent"],
        QPalette.ColorRole.Highlight:       tokens["accent"],
        QPalette.ColorRole.HighlightedText: tokens["on_accent"],
        QPalette.ColorRole.PlaceholderText: tokens["placeholder"],
        QPalette.ColorRole.Accent:          tokens["accent"],
    }


# ── QSS template ─────────────────────────────────────────────────────────
# One template, substituted per-theme via old-style ``%(name)s`` formatting.
# Qt 6 QSS supports ``rgba(r,g,b,a)`` natively so hover/active tints compose
# correctly over panel / chrome surfaces.

_QSS_TEMPLATE = """
    QDialog#plotAlignmentDialog QPushButton,
    QDialog#plotAlignmentDialog QPushButton[accent="true"] {
        padding: 5px 8px;
        font-weight: 400;
    }
    QDialog#plotAlignmentDialog QToolButton {
        border: 1px solid %(border)s;
        border-radius: %(radius_button)s;
        padding: 4px 8px;
        background: %(surface)s;
    }
    QDialog#plotAlignmentDialog QToolButton:hover,
    QDialog#plotAlignmentDialog QToolButton:focus {
        border-color: %(accent)s;
    }
    QDialog#plotAlignmentDialog QTableWidget {
        border: 1px solid %(border)s;
    }
    QDialog#plotAlignmentDialog QTableWidget[plotGuideTarget="true"],
    QDialog#plotAlignmentDialog QComboBox[plotGuideTarget="true"] {
        border-color: %(accent)s;
    }
    QDialog#plotAlignmentDialog QHeaderView::section,
    QDialog#plotAlignmentDialog QLabel#plotGuidance {
        font-weight: 500;
        background: transparent;
    }
    QPushButton#plotViewSegment {
        background: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: 0;
        padding: 4px 12px;
        color: %(text_sec)s;
        margin-left: -1px;
    }
    QPushButton#plotViewSegment[segment="first"] {
        border-top-left-radius: %(radius_button)s;
        border-bottom-left-radius: %(radius_button)s;
        margin-left: 0;
    }
    QPushButton#plotViewSegment[segment="last"] {
        border-top-right-radius: %(radius_button)s;
        border-bottom-right-radius: %(radius_button)s;
    }
    QPushButton#plotViewSegment:checked {
        background: %(accent_tint)s;
        color: %(accent)s;
        border-color: %(accent)s;
    }
    QMainWindow {
        background-color: %(panel)s;
        background: %(chrome)s;
        color: %(text)s;
        font-size: %(font_base)s;
    }
    QWidget {
        background-color: %(panel)s;
        color: %(text)s;
        font-size: %(font_base)s;
    }

    /* Splitters between panels */
    QSplitter::handle { background: %(divider)s; width: 1px; }
    QSplitter::handle:hover { background: %(accent)s; }
    QMainWindow::separator { background: transparent; }

    QSplitter#mainSplitter { background: %(panel)s; }
    QSplitter#mainSplitter::handle { background: %(panel)s; }
    QSplitter#mainSplitter::handle:hover { background: %(hover)s; }

    /* ── Toolbar ───────────────────────────────────────────────────── */
    QToolBar {
        border: none;
        background: %(chrome)s;
        padding: 6px 10px;
        border-bottom: 1px solid %(divider)s;
        spacing: 4px;
    }
    QToolBar::separator {
        background: %(divider)s;
        width: 1px; height: 22px;
        margin: 6px 8px;
    }
    QToolBar QToolButton {
        border-radius: 7px;
        padding: 5px 9px;
        color: %(text)s;
        border: 1px solid transparent;
        background: transparent;
        margin: 0 1px;
    }
    QToolBar QToolButton:hover  { background: %(hover)s; }
    QToolBar QToolButton:pressed { background: %(accent_tint)s; color: %(accent)s; background: %(active)s; }
    QToolBar QToolButton:checked { background: %(accent_tint)s; color: %(accent)s; background: %(surface)s; border: 1px solid %(border)s; }
    QToolBar QToolButton[popupMode="1"] { padding-right: 20px; }
    QToolBar QToolButton::menu-button { border: none; border-left: 1px solid transparent; border-top-right-radius: 7px; border-bottom-right-radius: 7px; width: 16px; background: transparent; }
    QToolBar QToolButton::menu-button:hover { background: %(hover)s; border-left-color: %(divider)s; }
    QToolBar QToolButton::menu-button:pressed { background: %(accent_tint)s; border-left-color: %(divider)s; }
    QToolBar QToolButton::menu-arrow { image: url(__ARROW_DOWN__); width: 10px; height: 10px; }
    QToolBar QToolButton::menu-arrow:open, QToolBar QToolButton::menu-arrow:pressed { image: url(__ARROW_DOWN_PRESSED__); }

    /* Menu bar + menus */
    QMenuBar { background-color: %(chrome)s; color: %(text)s; border-bottom: none; background: %(chrome)s; padding: 2px 6px; }
    QMenuBar::item { background-color: transparent; padding: 4px 10px; border-radius: %(radius_button)s; color: %(text_sec)s; }
    QFrame#drawPalette { background: %(surface)s; border: 1px solid %(border_strong)s; border-radius: 10px; }
    QFrame#drawPalette QToolButton { background: transparent; border: 1px solid transparent; border-radius: 6px; padding: 0; color: %(text)s; }
    QFrame#drawPalette QToolButton:hover { background: %(hover)s; }
    QFrame#drawPalette QToolButton:checked { background: %(accent_tint)s; border-color: %(accent)s; }
    QFrame#drawPalette QToolButton#drawPaletteDone { padding: 0 10px; font-weight: 600; color: %(accent)s; }
    QFrame#drawPaletteSep { color: %(divider)s; }
    QMenuBar::item:selected { background-color: %(hover)s; background: %(hover)s; color: %(text)s; }
    QMenuBar::item:pressed { background: %(active)s; color: %(text)s; }
    QMenu {
        background-color: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_panel)s;
        padding: 6px;
        color: %(text)s;
        background: %(surface)s;
    }
    QMenu::item { padding: 6px 28px 6px 14px; border-radius: %(radius_button)s; margin: 1px 0; }
    QMenu::item:selected { background-color: %(accent_tint)s; color: %(on_accent)s; background: %(accent)s; }
    QMenu::item:disabled { color: %(text_tert)s; background: transparent; }
    QMenu::separator { height: 1px; background: %(divider)s; margin: 5px 10px; }

    /* ── Inspector collapsible sections ──────────────────────────── */
    QWidget#collapsibleSection {
        background: transparent;
    }
    QFrame#sectionHead {
        background: %(surface_subtle)s;
        border: none;
        border-top: 1px solid %(border_strong)s;
        border-bottom: 1px solid %(border)s;
    }
    QFrame#sectionHead:hover {
        background: %(accent_tint)s;
    }
    QLabel#sectionTitle {
        font-size: %(font_md)s;
        font-weight: 700;
        color: %(text)s;
        letter-spacing: 0.4px;
        background: transparent;
    }
    QLabel#sectionChevron {
        color: %(text_sec)s;
        font-size: %(font_xs)s;
        background: transparent;
    }
    QWidget#sectionBody {
        background: transparent;
    }
    QFrame#sectionDivider {
        background: transparent;
        border: none;
        max-height: 1px;
    }

    /* ── Group boxes (legacy / dialogs) ──────────────────────────── */
    QGroupBox {
        font-weight: 500; font-size: %(font_sm)s;
        color: %(label_caps)s;
        border: 1px solid %(divider)s;
        border-radius: %(radius_panel)s;
        margin-top: 12px;
        padding: 10px 10px 8px;
        background: %(panel_alt)s;
    }
    QGroupBox::title {
        subcontrol-origin: margin;
        subcontrol-position: top left;
        left: 10px; padding: 0 6px;
        color: %(label_caps)s;
        background: %(panel_alt)s;
    }

    QScrollArea { border: none; background: transparent; }
    QScrollArea QWidget { background: transparent; }
    QGroupBox QWidget { background: transparent; }
    QGroupBox QLabel { background: transparent; }

    /* ── Inputs ───────────────────────────────────────────────────── */
    QLineEdit, QPlainTextEdit#inspectorTextContent, QComboBox {
        background: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_input)s;
        padding: 2px 8px;
        color: %(text)s;
        min-height: 24px;
        font-size: %(font_md)s;
        selection-background-color: %(accent)s;
        selection-color: %(on_accent)s;
    }
    QLineEdit:hover, QPlainTextEdit#inspectorTextContent:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
        border-color: %(border_strong)s;
    }
    QLineEdit:focus, QPlainTextEdit#inspectorTextContent:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border-color: %(accent)s;
    }
    QLineEdit:disabled, QPlainTextEdit#inspectorTextContent:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
        color: %(text_tert)s; background: %(surface_subtle)s;
    }

    /* Spin buttons: side by side on the right, with hover/pressed feedback. */
    QSpinBox, QDoubleSpinBox {
        background: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_input)s;
        padding: 2px 8px;
        color: %(text)s;
        min-height: 24px;
        font-size: %(font_md)s;
        selection-background-color: %(accent)s;
        selection-color: %(on_accent)s;
        padding-right: 46px;
    }
    QSpinBox::up-button, QDoubleSpinBox::up-button {
        subcontrol-origin: border;
        subcontrol-position: center right;
        width: 20px; height: 18px;
        border: none;
        border-radius: %(radius_button)s;
        background: transparent;
        right: 24px;
    }
    QSpinBox::down-button, QDoubleSpinBox::down-button {
        subcontrol-origin: border;
        subcontrol-position: center right;
        width: 20px; height: 18px;
        border: none;
        border-radius: %(radius_button)s;
        background: transparent;
        right: 3px;
    }
    QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover,
    QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {
        background: %(active)s;
    }
    QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed,
    QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {
        background: %(accent_tint)s;
    }
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {
        image: url(__ARROW_UP__); width: 10px; height: 10px;
    }
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {
        image: url(__ARROW_DOWN__); width: 10px; height: 10px;
    }
    QSpinBox::up-arrow:pressed, QDoubleSpinBox::up-arrow:pressed {
        image: url(__ARROW_UP_PRESSED__);
    }
    QSpinBox::down-arrow:pressed, QDoubleSpinBox::down-arrow:pressed {
        image: url(__ARROW_DOWN_PRESSED__);
    }
    QSpinBox::up-arrow:off, QDoubleSpinBox::up-arrow:off,
    QSpinBox::up-arrow:disabled, QDoubleSpinBox::up-arrow:disabled {
        image: url(__ARROW_UP_OFF__);
    }
    QSpinBox::down-arrow:off, QDoubleSpinBox::down-arrow:off,
    QSpinBox::down-arrow:disabled, QDoubleSpinBox::down-arrow:disabled {
        image: url(__ARROW_DOWN_OFF__);
    }
    QSpinBox::up-button:off, QDoubleSpinBox::up-button:off,
    QSpinBox::down-button:off, QDoubleSpinBox::down-button:off,
    QSpinBox::up-button:disabled, QDoubleSpinBox::up-button:disabled,
    QSpinBox::down-button:disabled, QDoubleSpinBox::down-button:disabled {
        background: transparent;
    }

    QComboBox::drop-down {
        border: none; width: 22px;
        subcontrol-origin: padding; subcontrol-position: top right;
    }
    QComboBox::down-arrow { image: url(__ARROW_DOWN__); width: 10px; height: 10px; }
    QComboBox QAbstractItemView {
        background-color: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_panel)s;
        padding: 4px;
        selection-background-color: %(accent_tint)s;
        selection-color: %(accent)s;
        outline: none;
    }

    /* ── Buttons ──────────────────────────────────────────────────── */
    QPushButton {
        background: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: 7px;
        padding: 5px 14px;
        color: %(text)s;
        font-weight: 400;
    }
    QPushButton:hover  { background: %(surface_subtle)s; border-color: %(border_strong)s; }
    QPushButton:pressed { background: %(active)s; }
    QPushButton:disabled { color: %(text_tert)s; background: %(surface_subtle)s; }

    QPushButton[accent="true"] {
        background: %(accent)s;
        border-color: %(accent_press)s;
        color: %(on_accent)s;
        font-weight: 600;
        padding: 5px 14px;
    }
    QPushButton[accent="true"]:hover  { background: %(accent_hover)s; border-color: %(accent_hover)s; }
    QPushButton[accent="true"]:pressed { background: %(accent_press)s; border-color: %(accent_press)s; }

    /* Primary QToolButton variant (e.g. toolbar Export): solid accent
       button with white glyph/text. */
    QToolButton[primary="true"] {
        background: %(accent)s;
        color: %(on_accent)s;
        border: 1px solid %(accent_press)s;
        border-radius: %(radius_button)s;
        padding: 5px 14px;
        font-weight: 600;
    }
    QToolButton[primary="true"]:hover  { background: %(accent_hover)s; border-color: %(accent_hover)s; }
    QToolButton[primary="true"]:pressed,
    QToolButton[primary="true"]:checked { background: %(accent_press)s; border-color: %(accent_press)s; }
    QToolButton[primary="true"]:disabled {
        background: %(surface_subtle)s;
        color: %(text_tert)s;
        border-color: %(border)s;
    }
    QToolButton[primary="true"]::menu-indicator { image: none; width: 0; }

    /* Startup welcome page — compact "high-DPI" density; element sizes
       follow importance: modest title, small actions, tiny hints. */
    QWidget#welcomePage { background: %(panel)s; }
    QLabel#welcomeTitle { font-size: 13pt; font-weight: 500; color: %(text)s; }
    QLabel#welcomeDropHint { font-size: 10px; color: %(text_tert)s; }
    QLabel#welcomeHeader {
        font-size: 10px; font-weight: 500; color: %(text_tert)s;
    }
    QLabel#welcomeRecent { font-size: 11px; color: %(text)s; }
    QPushButton#welcomePrimary {
        background: %(accent)s;
        color: %(on_accent)s;
        border: 1px solid %(accent)s;
        border-radius: 8px;
        padding: 7px 16px;
        font-size: %(font_base)s;
        font-weight: 600;
        min-width: 180px;
    }
    QPushButton#welcomePrimary:hover { background: %(accent_hover)s; }
    QPushButton#welcomeGhost {
        color: %(text_sec)s;
        border: none;
        padding: 5px 14px;
        font-size: 12px;
    }
    QPushButton#welcomeGhost:hover { color: %(text)s; }
    QPushButton#welcomeCorner {
        color: %(text_sec)s;
        border: none;
        padding: 2px 6px;
        font-size: 11px;
    }
    QPushButton#welcomeCorner:hover { color: %(accent)s; }

    /* MCP status indicator in the status bar */
    QToolButton#mcpStatus {
        border: none;
        padding: 0 8px;
        color: %(text_sec)s;
    }

    /* ── Tabs ─────────────────────────────────────────────────────── */
    /* On macOS the strip behind QTabBar falls back to the system palette
       (dark in system dark mode) unless we paint it explicitly. */
    QTabWidget {
        background: %(panel)s;
    }
    QTabWidget::pane {
        border: 1px solid %(divider)s;
        border-radius: %(radius_panel)s;
        top: -1px;
        background: %(panel)s;
    }
    QTabBar {
        background: %(panel)s;
        border: none;
    }
    QTabBar::tab {
        background: transparent;
        color: %(text_sec)s;
        padding: 6px 14px;
        border: 1px solid transparent;
        border-top-left-radius: %(radius_panel)s;
        border-top-right-radius: %(radius_panel)s;
        margin-right: 2px;
    }
    QTabBar::tab:hover { color: %(text)s; background: %(hover)s; }
    QTabBar::tab:selected {
        background: %(accent_tint)s;
        color: %(accent)s;
        border-color: %(divider)s;
        border-bottom-color: %(accent_tint)s;
        font-weight: 500;
    }

    QTabWidget#sideTabs::pane { border: none; border-top: 1px solid %(divider)s; border-radius: 0; background: %(panel)s; top: 0px; }
    QTabWidget#sideTabs QTabBar { background: %(panel)s; }
    QTabWidget#sideTabs QTabBar::tab { background: transparent; color: %(text_sec)s; border: 1px solid transparent; border-radius: %(radius_button)s; padding: 4px 12px; margin: 6px 2px 6px 0; font-weight: 500; }
    QTabWidget#sideTabs QTabBar::tab:first { margin-left: 8px; }
    QTabWidget#sideTabs QTabBar::tab:hover { color: %(text)s; background: %(hover)s; }
    QTabWidget#sideTabs QTabBar::tab:selected { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; }

    QTabWidget#docTabs::pane { border: none; }
    QTabWidget#docTabs QTabBar { background: %(panel)s; }
    QTabWidget#docTabs QTabBar::tab { background: transparent; color: %(text_sec)s; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 7px 14px 6px; margin: 0 2px; font-weight: 500; }
    QTabWidget#docTabs QTabBar::tab:hover { color: %(text)s; background: transparent; }
    QTabWidget#docTabs QTabBar::tab:selected { color: %(text)s; background: transparent; border-bottom: 2px solid %(accent)s; }

    /* ── Scrollbars ───────────────────────────────────────────────── */
    QScrollBar:vertical   { background: transparent; width: 10px; margin: 0; }
    QScrollBar::handle:vertical {
        background: %(border_strong)s;
        border-radius: 3px;
        min-height: 28px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover { background: %(text_tert)s; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    QScrollBar:horizontal { background: transparent; height: 10px; margin: 0; }
    QScrollBar::handle:horizontal {
        background: %(border_strong)s;
        border-radius: 3px;
        min-width: 28px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover { background: %(text_tert)s; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

    /* Generic labels */
    QLabel { color: %(text)s; background: transparent; }

    /* ── Checkboxes ───────────────────────────────────────────────── */
    QCheckBox { spacing: 6px; color: %(text)s; }
    QCheckBox::indicator, QGroupBox::indicator {
        width: 13px; height: 13px;
        border: 1px solid %(border_strong)s;
        border-radius: 4px;
        background-color: %(surface)s;
    }
    QCheckBox::indicator:hover, QGroupBox::indicator:hover { border-color: %(accent)s; }
    QCheckBox::indicator:checked, QGroupBox::indicator:checked {
        border: 1px solid %(accent)s;
        background-color: %(accent)s;
        image: url(__CHECK_ON__);
    }
    QCheckBox::indicator:checked:hover, QGroupBox::indicator:checked:hover { border-color: %(accent_hover)s; background-color: %(accent_hover)s; }
    QCheckBox::indicator:disabled, QGroupBox::indicator:disabled { border-color: %(border)s; background-color: %(surface_subtle)s; }
    QCheckBox::indicator:checked:disabled, QGroupBox::indicator:checked:disabled { border-color: %(border_strong)s; background-color: %(border_strong)s; }

    /* ── Radio buttons ────────────────────────────────────────────── */
    QRadioButton { spacing: 6px; color: %(text)s; }
    QRadioButton::indicator {
        width: 13px; height: 13px;
        border: 1px solid %(border_strong)s;
        border-radius: 7px;
        background-color: %(surface)s;
    }
    QRadioButton::indicator:hover { border-color: %(accent)s; }
    QRadioButton::indicator:checked {
        border: 1px solid %(accent)s;
        background-color: qradialgradient(
            cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5,
            stop:0 %(on_accent)s, stop:0.34 %(on_accent)s,
            stop:0.42 %(accent)s, stop:1 %(accent)s);
    }
    QRadioButton::indicator:disabled {
        border-color: %(border)s;
        background-color: %(surface_subtle)s;
    }

    /* ── Status bar ───────────────────────────────────────────────── */
    QStatusBar {
        background: %(chrome)s;
        color: %(text_tert)s;
        border-top: 1px solid %(divider)s;
        font-size: %(font_sm)s;
        min-height: 26px;
        max-height: 26px;
    }
    QStatusBar::item { border: none; }
    QStatusBar QLabel { color: %(text_sec)s; padding: 0 6px; }
    QFrame#statusDivider {
        background: %(border)s;
        border: none;
        max-width: 1px;
    }
    QWidget#zoomControl QToolButton {
        border: none;
        border-radius: %(radius_button)s;
        padding: 0 6px;
        min-height: 20px;
        color: %(text_sec)s;
        background: transparent;
    }
    QWidget#zoomControl QToolButton:hover { background: %(hover)s; color: %(text)s; }
    QWidget#zoomControl QToolButton:pressed { background: %(accent_tint)s; color: %(accent)s; }
    QWidget#zoomControl QToolButton::menu-indicator { image: none; width: 0; }

    /* ── Tooltips ─────────────────────────────────────────────────── */
    QToolTip {
        background-color: %(text)s;
        color: %(panel)s;
        border: none;
        border-radius: %(radius_button)s;
        padding: 5px 9px;
    }

    QDialog#tutorialCenter { background: %(panel)s; }
    QDialog#tutorialCenter QLabel { background: transparent; }
    QLabel#tutorialCenterHeading, QLabel#tutorialLessonTitle {
        font-size: %(font_base)s;
        font-weight: 500;
    }
    QLabel#tutorialGroupHeading {
        font-size: %(font_md)s;
        font-weight: 500;
        color: %(text_sec)s;
    }
    QLabel#tutorialCenterSubtitle, QLabel#tutorialLessonSummary {
        font-size: %(font_base)s;
        color: %(text_sec)s;
    }
    QLabel#tutorialCenterProgress, QLabel#tutorialLessonNumber,
    QLabel#tutorialLessonMetadata, QLabel#tutorialLessonStatus {
        font-size: %(font_sm)s;
        color: %(text_sec)s;
    }
    QWidget#tutorialLessonList { background: transparent; }
    QPushButton#tutorialLesson {
        background: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_panel)s;
        padding: 0;
        font-weight: 300;
        text-align: left;
    }
    QPushButton#tutorialLesson:hover {
        background: %(surface_subtle)s;
        border-color: %(accent)s;
    }
    QPushButton#tutorialLesson:focus {
        border: 2px solid %(accent)s;
    }
    QPushButton#tutorialLesson:pressed {
        background: %(accent_tint)s;
    }
    QPushButton#tutorialLesson QLabel { background: transparent; }
    QPushButton#tutorialLesson[lessonState="completed"] QLabel#tutorialLessonStatus {
        color: %(accent)s;
    }
"""

_LAYERS_TREE_TEMPLATE = """
    QTreeWidget {
        background-color: transparent;
        border: none;
        outline: none;
        show-decoration-selected: 0;
        font-size: %(font_md)s;
    }
    QTreeWidget::item {
        padding: 1px 4px;
        border: none;
    }
    QTreeWidget::item:selected {
        background-color: transparent;
        color: %(accent)s;
    }
    QTreeWidget::item:hover:!selected { background-color: transparent; }
    QTreeWidget::branch {
        background: transparent;
        border-image: none;
        image: none;
    }
    QTreeWidget::branch:has-siblings,
    QTreeWidget::branch:!has-siblings,
    QTreeWidget::branch:has-children,
    QTreeWidget::branch:has-siblings:adjoins-item,
    QTreeWidget::branch:!has-siblings:adjoins-item {
        border-image: none;
        image: none;
    }
"""


# ── Public API (stable) ──────────────────────────────────────────────────

def get_tokens(theme: str) -> dict:
    """Return the full token dict for the given theme.

    Intended for programmatic consumers (canvas grid rendering, cell
    placeholder dash colour, layer-panel thumbnails, custom delegates).
    """
    return dict(_TOKENS_DARK if theme == DARK else _TOKENS_LIGHT)


def token_color(value, fallback: str = "#000000") -> QColor:
    """Parse a design-token colour into a QColor.

    Handles "#hex" via QColor directly, plus CSS-style "rgba(r, g, b, a)"
    with a float alpha in 0–1 — QColor's string parser rejects that form,
    and painting with the invalid result renders as opaque black.
    """
    s = str(value).strip()
    if s.startswith("rgba") and s.endswith(")"):
        try:
            parts = [p.strip() for p in s[s.index("(") + 1:-1].split(",")]
            r, g, b = (int(float(p)) for p in parts[:3])
            a = float(parts[3]) if len(parts) > 3 else 1.0
            alpha = int(round(a * 255)) if a <= 1.0 else int(a)
            return QColor(r, g, b, alpha)
        except (ValueError, IndexError):
            pass
    color = QColor(s)
    return color if color.isValid() else QColor(fallback)


def build_palette(theme: str) -> QPalette:
    tokens = get_tokens(theme)
    palette = QPalette()
    for role, color_str in _palette_tokens_to_roles(tokens).items():
        # Tokens may contain rgba(...) — palette roles want solid colours, so
        # any rgba here would be a bug. All roles currently pull solid hex.
        palette.setColor(role, QColor(color_str))
    return palette


def _font_tokens(scale: float) -> dict:
    """Return font-size tokens as px strings for the given scale factor."""
    scale = max(FONT_SCALE_MIN, min(FONT_SCALE_MAX, float(scale)))
    return {
        "font_base": f"{round(13 * scale)}px",
        "font_md":   f"{round(12 * scale)}px",
        "font_sm":   f"{round(11 * scale)}px",
        "font_xs":   f"{round(10 * scale)}px",
    }


def get_stylesheet(theme: str, scale: float = 1.0) -> str:
    tokens = {**get_tokens(theme), **_font_tokens(scale)}
    arrow = _ARROW_DOWN_DARK if theme == DARK else _ARROW_DOWN_LIGHT
    variant = "dark" if theme == DARK else "light"
    assets = _assets_dir()
    # Longer placeholders first so "__ARROW_DOWN__" never clips "__ARROW_DOWN_OFF__".
    qss = (_QSS_TEMPLATE % tokens) \
        .replace("__CHECK_ON__", f"{assets}/check_mark_{variant}.svg") \
        .replace("__ARROW_UP_PRESSED__", f"{assets}/arrow_up_accent_{variant}.svg") \
        .replace("__ARROW_DOWN_PRESSED__", f"{assets}/arrow_down_accent_{variant}.svg") \
        .replace("__ARROW_UP_OFF__", f"{assets}/arrow_up_{variant}_off.svg") \
        .replace("__ARROW_DOWN_OFF__", f"{assets}/arrow_down_{variant}_off.svg") \
        .replace("__ARROW_UP__", f"{assets}/arrow_up_{variant}.svg") \
        .replace("__ARROW_DOWN__", arrow)
    return qss


def get_layers_tree_stylesheet(theme: str, scale: float = 1.0) -> str:
    tokens = {**get_tokens(theme), **_font_tokens(scale)}
    return _LAYERS_TREE_TEMPLATE % tokens


# ── App-wide font scaling ────────────────────────────────────────────────
# Captured once on startup so successive zoom-in/zoom-out steps remain
# relative to the platform default rather than compounding.
_BASE_APP_FONT_PT = None
FONT_SCALE_MIN = 0.75
FONT_SCALE_MAX = 2.0
FONT_SCALE_STEP = 0.1


def _app_font(scale: float) -> QFont:
    """The platform system UI font at normal weight, scaled from its base size."""
    global _BASE_APP_FONT_PT
    f = QFontDatabase.systemFont(QFontDatabase.SystemFont.GeneralFont)
    f.setWeight(QFont.Weight.Normal)
    if _BASE_APP_FONT_PT is None:
        base = f.pointSizeF()
        if base <= 0:
            base = max(f.pixelSize(), 9) * 0.75
        _BASE_APP_FONT_PT = base
    f.setPointSizeF(_BASE_APP_FONT_PT * scale)
    return f


def apply_font_scale(app, scale: float, theme: str = LIGHT) -> float:
    """Scale the QApplication font by *scale* (clamped) and re-apply the stylesheet.

    Re-applying the stylesheet is required because font-size values are
    hardcoded as px in the QSS — app.setFont() alone is overridden by them.
    Returns the clamped scale that was actually applied.
    """
    scale = max(FONT_SCALE_MIN, min(FONT_SCALE_MAX, float(scale)))
    app.setFont(_app_font(scale))
    app.setStyleSheet(get_stylesheet(theme, scale))
    return scale
