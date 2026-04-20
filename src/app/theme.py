"""Design tokens + stylesheet for Academic Figure Layout.

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
from PyQt6.QtGui import QPalette, QColor

# Resolve assets directory: works both in dev and inside a PyInstaller bundle.
def _assets_dir() -> str:
    import sys
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base = sys._MEIPASS
    else:
        base = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".."))
    return os.path.join(base, "assets").replace("\\", "/")

_CHECK_ON = f"{_assets_dir()}/check_on.svg"
_ARROW_DOWN_DARK = f"{_assets_dir()}/arrow_down_dark.svg"
_ARROW_DOWN_LIGHT = f"{_assets_dir()}/arrow_down_light.svg"

DARK = "dark"
LIGHT = "light"

# ── Design tokens ────────────────────────────────────────────────────────
# Source of truth for every colour/radius used by the app. Names match the
# CSS variables in afl-macos-mockup.html / afl-windows-mockup.html 1:1 so
# future designers can port styles directly.

_TOKENS_LIGHT = {
    # Surfaces
    "chrome":        "#ECECEC",
    "panel":         "#F5F5F5",
    "panel_alt":     "#FAFAFA",
    "canvas_bg":     "#E8E8E8",
    "surface":       "#FFFFFF",
    "surface_subtle":"#F9F9F9",
    # Borders / dividers
    "border":        "#D8D8D8",
    "border_strong": "#C4C4C4",
    "divider":       "#E4E4E4",
    # Text
    "text":          "#1D1D1F",
    "text_sec":      "#6E6E73",
    "text_tert":     "#8E8E93",
    "label_caps":    "#86868B",
    # Interactive states (rgba on the owning surface)
    "hover":         "rgba(0, 0, 0, 0.05)",
    "active":        "rgba(0, 0, 0, 0.09)",
    # Brand
    "accent":        "#0891B2",
    "accent_hover":  "#0E7490",
    "accent_press":  "#164E63",
    "accent_tint":   "rgba(8, 145, 178, 0.12)",
    "accent_ring":   "rgba(8, 145, 178, 0.35)",
    "on_accent":     "#FFFFFF",
    # Semantic
    "danger":        "#DC2626",
    # Canvas helpers (not QSS — consumed by cell_item / canvas_view paint)
    "placeholder":   "#AEAEB2",
    "grid_line":     "#C7C7CC",
    # Geometry
    "radius_panel":  "6px",
    "radius_button": "4px",
    "radius_input":  "4px",
}

_TOKENS_DARK = {
    "chrome":        "#2C2C2E",
    "panel":         "#242426",
    "panel_alt":     "#1F1F21",
    "canvas_bg":     "#1A1A1C",
    "surface":       "#2F2F31",
    "surface_subtle":"#2A2A2C",
    "border":        "#3A3A3C",
    "border_strong": "#48484A",
    "divider":       "#323234",
    "text":          "#F5F5F7",
    "text_sec":      "#A1A1A6",
    "text_tert":     "#6E6E73",
    "label_caps":    "#8E8E93",
    "hover":         "rgba(255, 255, 255, 0.06)",
    "active":        "rgba(255, 255, 255, 0.10)",
    "accent":        "#22D3EE",
    "accent_hover":  "#06B6D4",
    "accent_press":  "#0E7490",
    "accent_tint":   "rgba(34, 211, 238, 0.14)",
    "accent_ring":   "rgba(34, 211, 238, 0.40)",
    "on_accent":     "#001018",
    "danger":        "#F87171",
    "placeholder":   "#636366",
    "grid_line":     "#48484A",
    "radius_panel":  "6px",
    "radius_button": "4px",
    "radius_input":  "4px",
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
        QPalette.ColorRole.PlaceholderText: tokens["text_tert"],
    }


# ── QSS template ─────────────────────────────────────────────────────────
# One template, substituted per-theme via old-style ``%(name)s`` formatting.
# Qt 6 QSS supports ``rgba(r,g,b,a)`` natively so hover/active tints compose
# correctly over panel / chrome surfaces.

_QSS_TEMPLATE = """
    QMainWindow, QWidget {
        background-color: %(panel)s;
        color: %(text)s;
        font-family: system-ui, "SF Pro Text", "Segoe UI", "Helvetica Neue", Arial, sans-serif;
        font-size: 13px;
    }

    /* Splitters between panels */
    QSplitter::handle { background: %(divider)s; width: 1px; }
    QSplitter::handle:hover { background: %(accent)s; }
    QMainWindow::separator { background: transparent; }

    /* ── Toolbar ───────────────────────────────────────────────────── */
    QToolBar {
        border: none;
        background: %(chrome)s;
        padding: 8px 12px;
        border-bottom: 1px solid %(divider)s;
        spacing: 2px;
    }
    QToolBar::separator {
        background: %(border)s;
        width: 1px; height: 22px;
        margin: 0 6px;
    }
    QToolBar QToolButton {
        border-radius: %(radius_button)s;
        padding: 6px 10px;
        color: %(text)s;
        background: transparent;
        margin: 0 1px;
    }
    QToolBar QToolButton:hover  { background: %(hover)s; }
    QToolBar QToolButton:pressed,
    QToolBar QToolButton:checked { background: %(accent_tint)s; color: %(accent)s; }

    /* Menu bar + menus */
    QMenuBar { background-color: %(chrome)s; color: %(text)s; border-bottom: 1px solid %(divider)s; }
    QMenuBar::item { background-color: transparent; padding: 4px 10px; border-radius: %(radius_button)s; }
    QMenuBar::item:selected { background-color: %(hover)s; }
    QMenu {
        background-color: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_panel)s;
        padding: 4px;
        color: %(text)s;
    }
    QMenu::item { padding: 6px 22px; border-radius: %(radius_button)s; }
    QMenu::item:selected { background-color: %(accent_tint)s; color: %(accent)s; }
    QMenu::separator { height: 1px; background: %(divider)s; margin: 4px 8px; }

    /* ── Inspector collapsible sections ──────────────────────────── */
    QWidget#collapsibleSection {
        background: transparent;
    }
    QWidget#sectionHead {
        background: transparent;
    }
    QWidget#sectionHead:hover {
        background: %(hover)s;
    }
    QLabel#sectionTitle {
        font-size: 11px;
        font-weight: 600;
        color: %(label_caps)s;
        letter-spacing: 1px;
        background: transparent;
    }
    QLabel#sectionChevron {
        color: %(text_tert)s;
        font-size: 10px;
        background: transparent;
    }
    QWidget#sectionBody {
        background: transparent;
    }
    QFrame#sectionDivider {
        background: %(divider)s;
        border: none;
        max-height: 1px;
    }

    /* ── Group boxes (legacy / dialogs) ──────────────────────────── */
    QGroupBox {
        font-weight: 600; font-size: 11px;
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
    QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
        background: %(surface)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_input)s;
        padding: 2px 8px;
        color: %(text)s;
        min-height: 24px;
        font-size: 12px;
        selection-background-color: %(accent)s;
        selection-color: %(on_accent)s;
    }
    QLineEdit:hover, QSpinBox:hover, QDoubleSpinBox:hover, QComboBox:hover {
        border-color: %(border_strong)s;
    }
    QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
        border-color: %(accent)s;
    }
    QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {
        color: %(text_tert)s; background: %(surface_subtle)s;
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
        border-radius: %(radius_button)s;
        padding: 5px 12px;
        color: %(text)s;
        font-weight: 500;
    }
    QPushButton:hover  { background: %(hover)s; border-color: %(border_strong)s; }
    QPushButton:pressed { background: %(active)s; }
    QPushButton:disabled { color: %(text_tert)s; background: %(surface_subtle)s; }

    QPushButton[accent="true"] {
        background: %(accent)s;
        border-color: %(accent)s;
        color: %(on_accent)s;
        font-weight: 600;
        padding: 5px 14px;
    }
    QPushButton[accent="true"]:hover  { background: %(accent_hover)s; border-color: %(accent_hover)s; }
    QPushButton[accent="true"]:pressed { background: %(accent_press)s; border-color: %(accent_press)s; }

    /* Primary QToolButton variant (e.g. toolbar Export). Matches the
       mockup's .tb-btn.primary: solid accent pill with white glyph/text. */
    QToolButton[primary="true"] {
        background: %(accent)s;
        color: %(on_accent)s;
        border: 1px solid %(accent)s;
        border-radius: %(radius_button)s;
        padding: 5px 14px;
        font-weight: 600;
    }
    QToolButton[primary="true"]:hover  { background: %(accent_hover)s; border-color: %(accent_hover)s; }
    QToolButton[primary="true"]:pressed,
    QToolButton[primary="true"]:checked { background: %(accent_press)s; border-color: %(accent_press)s; }
    QToolButton[primary="true"]::menu-indicator { image: none; width: 0; }

    /* Theme segmented control (sun/moon pill on the right of the toolbar).
       Matches .segmented / .seg-btn in the redesign mockups. */
    QFrame#themeSegmented {
        background: %(panel_alt)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_button)s;
    }
    QFrame#themeSegmented QToolButton[segmentedButton="true"] {
        background: transparent;
        color: %(text_sec)s;
        border: none;
        border-radius: 3px;
        padding: 2px 10px;
        font-size: 12px;
    }
    QFrame#themeSegmented QToolButton[segmentedButton="true"]:hover {
        color: %(text)s;
        background: %(hover)s;
    }
    QFrame#themeSegmented QToolButton[segmentedButton="true"]:checked {
        background: %(surface)s;
        color: %(accent)s;
        font-weight: 600;
    }

    /* ── Tabs ─────────────────────────────────────────────────────── */
    QTabWidget::pane {
        border: 1px solid %(divider)s;
        border-radius: %(radius_panel)s;
        top: -1px;
        background: %(panel)s;
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
        font-weight: 600;
    }

    /* ── Scrollbars ───────────────────────────────────────────────── */
    QScrollBar:vertical   { background: transparent; width: 12px; margin: 0; }
    QScrollBar::handle:vertical {
        background: %(border_strong)s;
        border-radius: 5px;
        min-height: 24px;
        margin: 2px;
    }
    QScrollBar::handle:vertical:hover { background: %(text_tert)s; }
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }

    QScrollBar:horizontal { background: transparent; height: 12px; margin: 0; }
    QScrollBar::handle:horizontal {
        background: %(border_strong)s;
        border-radius: 5px;
        min-width: 24px;
        margin: 2px;
    }
    QScrollBar::handle:horizontal:hover { background: %(text_tert)s; }
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal { background: transparent; }

    /* Generic labels */
    QLabel { color: %(text)s; background: transparent; }

    /* ── Checkboxes ───────────────────────────────────────────────── */
    QCheckBox { spacing: 6px; color: %(text)s; }
    QCheckBox::indicator {
        width: 14px; height: 14px;
        border: 1.5px solid %(border_strong)s;
        border-radius: 3px;
        background-color: %(surface)s;
    }
    QCheckBox::indicator:hover { border-color: %(accent)s; }
    QCheckBox::indicator:checked {
        border: none;
        image: url(__CHECK_ON__);
    }
    QGroupBox::indicator {
        width: 14px; height: 14px;
        border: 1.5px solid %(border_strong)s;
        border-radius: 3px;
        background-color: %(surface)s;
    }
    QGroupBox::indicator:checked {
        border: none;
        image: url(__CHECK_ON__);
    }

    /* ── Status bar ───────────────────────────────────────────────── */
    QStatusBar {
        background: %(panel)s;
        color: %(text_sec)s;
        border-top: 1px solid %(divider)s;
        font-size: 11px;
        min-height: 24px;
        max-height: 24px;
    }
    QStatusBar::item { border: none; }
    QFrame#statusDivider {
        background: %(border)s;
        border: none;
        max-width: 1px;
    }

    /* ── Tooltips ─────────────────────────────────────────────────── */
    QToolTip {
        background-color: %(surface)s;
        color: %(text)s;
        border: 1px solid %(border)s;
        border-radius: %(radius_button)s;
        padding: 4px 8px;
    }
"""

_LAYERS_TREE_TEMPLATE = """
    QTreeWidget {
        background-color: transparent;
        border: none;
        outline: none;
        show-decoration-selected: 0;
        font-size: 12px;
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


def build_palette(theme: str) -> QPalette:
    tokens = get_tokens(theme)
    palette = QPalette()
    for role, color_str in _palette_tokens_to_roles(tokens).items():
        # Tokens may contain rgba(...) — palette roles want solid colours, so
        # any rgba here would be a bug. All roles currently pull solid hex.
        palette.setColor(role, QColor(color_str))
    return palette


def get_stylesheet(theme: str) -> str:
    tokens = get_tokens(theme)
    arrow = _ARROW_DOWN_DARK if theme == DARK else _ARROW_DOWN_LIGHT
    return (_QSS_TEMPLATE % tokens) \
        .replace("__CHECK_ON__", _CHECK_ON) \
        .replace("__ARROW_DOWN__", arrow)


def get_layers_tree_stylesheet(theme: str) -> str:
    return _LAYERS_TREE_TEMPLATE % get_tokens(theme)
