"""Studio skin — an alternative visual layer for ImageLayoutManager.

``install()`` rewrites the design-token dicts of :mod:`src.app.theme` in
place, wraps ``get_stylesheet``/``apply_font_scale``/``build_palette`` with
Studio additions, isolates the process from classic single-instance routing
and (optionally) swaps ``src.app.main_window.MainWindow`` for a polished
subclass and restyles the canvas paint hooks. It must run *before* any app
module binds theme functions — ``main_studio.py`` is the entry point that
guarantees that ordering. The classic ``main.py`` path never imports this
module and is completely unaffected.
"""

import logging
import sys

from PyQt6.QtCore import QPointF, QRectF, QSize, Qt
from PyQt6.QtGui import (
    QBrush, QColor, QFont, QFontDatabase, QFontMetrics, QGuiApplication,
    QPainter, QPalette, QPen,
)
from PyQt6.QtWidgets import QApplication, QLabel, QStyle, QStyledItemDelegate

from src.app import theme
from src.app.theme import DARK, LIGHT

_log = logging.getLogger(__name__)

# ── Studio design tokens ─────────────────────────────────────────────────
# Same key set as theme._TOKENS_LIGHT/_TOKENS_DARK (asserted at install).
# Constraint: layers_panel detects dark themes via canvas_bg "#1" prefix —
# the dark value below must keep it, the light one must not.

STUDIO_LIGHT = {
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
    # Interactive states
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
    # Canvas helpers
    "placeholder":   "#B4B0A9",
    "grid_line":     "#D3D4D8",
    # Geometry
    "radius_panel":  "8px",
    "radius_button": "6px",
    "radius_input":  "6px",
}

STUDIO_DARK = {
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

# Current theme as last applied by the Studio window; token lookups made from
# module-level painters (canvas items, history delegate) read it through
# _tokens() so they follow theme switches.
_state = {"theme": LIGHT}


def _tokens() -> dict:
    return theme.get_tokens(_state["theme"])


# ── Studio QSS overlay ───────────────────────────────────────────────────
# Appended after the classic template by the wrapped get_stylesheet, so the
# rules below only need to override what the Studio chrome changes plus the
# objectName-scoped widgets the Studio window creates.

_STUDIO_QSS = """
    /* ── Studio skin ── */
    QMainWindow { background: %(chrome)s; }
    QMenuBar { background: %(chrome)s; border-bottom: none; padding: 2px 6px; }
    QMenuBar::item { padding: 4px 10px; border-radius: %(radius_button)s; color: %(text_sec)s; }
    QMenuBar::item:selected { background: %(hover)s; color: %(text)s; }
    QMenuBar::item:pressed { background: %(active)s; color: %(text)s; }
    QMenu { background: %(surface)s; border: 1px solid %(border)s; border-radius: %(radius_panel)s; padding: 6px; }
    QMenu::item { padding: 6px 28px 6px 14px; border-radius: %(radius_button)s; margin: 1px 0; }
    QMenu::item:selected { background: %(accent)s; color: %(on_accent)s; }
    QMenu::item:disabled { color: %(text_tert)s; background: transparent; }
    QMenu::separator { height: 1px; background: %(divider)s; margin: 5px 10px; }

    QToolBar { background: %(chrome)s; border: none; border-bottom: 1px solid %(divider)s; padding: 6px 10px; spacing: 4px; }
    QToolBar::separator { background: %(divider)s; width: 1px; margin: 6px 8px; }
    QToolBar QToolButton { padding: 5px 9px; border-radius: 7px; color: %(text)s; border: 1px solid transparent; background: transparent; }
    QToolBar QToolButton:hover { background: %(hover)s; }
    QToolBar QToolButton:pressed { background: %(active)s; }
    QToolBar QToolButton:checked { background: %(surface)s; border: 1px solid %(border)s; color: %(accent)s; }
    QToolButton[primary="true"] { background: %(accent)s; border: 1px solid %(accent_press)s; color: %(on_accent)s; border-radius: %(radius_button)s; padding: 5px 14px; font-weight: 600; }
    QToolButton[primary="true"]:hover { background: %(accent_hover)s; }
    QToolButton[primary="true"]:pressed { background: %(accent_press)s; }

    QSplitter#studioSplitter { background: %(panel)s; }
    QSplitter#studioSplitter::handle { background: %(panel)s; }
    QSplitter#studioSplitter::handle:hover { background: %(hover)s; }

    QTabWidget#studioSideTabs::pane { border: none; border-top: 1px solid %(divider)s; border-radius: 0; background: %(panel)s; top: 0px; }
    QTabWidget#studioSideTabs QTabBar { background: %(panel)s; }
    QTabWidget#studioSideTabs QTabBar::tab { background: transparent; color: %(text_sec)s; border: 1px solid transparent; border-radius: %(radius_button)s; padding: 4px 12px; margin: 6px 2px 6px 0; font-weight: 500; }
    QTabWidget#studioSideTabs QTabBar::tab:first { margin-left: 8px; }
    QTabWidget#studioSideTabs QTabBar::tab:hover { color: %(text)s; background: %(hover)s; }
    QTabWidget#studioSideTabs QTabBar::tab:selected { background: %(surface)s; color: %(text)s; border: 1px solid %(border)s; }

    QTabWidget#studioDocTabs::pane { border: none; }
    QTabWidget#studioDocTabs QTabBar { background: %(panel)s; }
    QTabWidget#studioDocTabs QTabBar::tab { background: transparent; color: %(text_sec)s; border: none; border-bottom: 2px solid transparent; border-radius: 0; padding: 7px 14px 6px; margin: 0 2px; font-weight: 500; }
    QTabWidget#studioDocTabs QTabBar::tab:hover { color: %(text)s; background: transparent; }
    QTabWidget#studioDocTabs QTabBar::tab:selected { color: %(text)s; background: transparent; border-bottom: 2px solid %(accent)s; }

    QWidget#sectionHead { background: transparent; border: none; border-bottom: 1px solid %(divider)s; }
    QWidget#sectionHead:hover { background: %(hover)s; }
    QLabel#sectionTitle { font-size: %(font_md)s; font-weight: 600; color: %(text)s; letter-spacing: 0.2px; }

    QPushButton { border-radius: 7px; padding: 5px 14px; }
    QPushButton:hover { background: %(surface_subtle)s; border-color: %(border_strong)s; }
    QPushButton[accent="true"] { font-weight: 600; border-color: %(accent_press)s; }
    QPushButton#welcomePrimary { border-radius: 8px; padding: 7px 16px; font-weight: 600; }

    QCheckBox::indicator, QGroupBox::indicator { width: 13px; height: 13px; border: 1px solid %(border_strong)s; border-radius: 4px; background-color: %(surface)s; }
    QCheckBox::indicator:hover, QGroupBox::indicator:hover { border-color: %(accent)s; }
    QCheckBox::indicator:checked, QGroupBox::indicator:checked { border: 1px solid %(accent)s; background-color: %(accent)s; image: url(__STUDIO_CHECK__); }
    QCheckBox::indicator:checked:hover, QGroupBox::indicator:checked:hover { border-color: %(accent_hover)s; background-color: %(accent_hover)s; }
    QCheckBox::indicator:disabled, QGroupBox::indicator:disabled { border-color: %(border)s; background-color: %(surface_subtle)s; }
    QCheckBox::indicator:checked:disabled, QGroupBox::indicator:checked:disabled { border-color: %(border_strong)s; background-color: %(border_strong)s; }
    QRadioButton::indicator { width: 13px; height: 13px; border: 1px solid %(border_strong)s; border-radius: 7px; background-color: %(surface)s; }
    QRadioButton::indicator:hover { border-color: %(accent)s; }
    QRadioButton::indicator:checked { border: 1px solid %(accent)s; background-color: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 %(on_accent)s, stop:0.34 %(on_accent)s, stop:0.42 %(accent)s, stop:1 %(accent)s); }

    QScrollBar:vertical { width: 10px; background: transparent; }
    QScrollBar::handle:vertical { background: %(border_strong)s; border-radius: 3px; margin: 2px; min-height: 28px; }
    QScrollBar::handle:vertical:hover { background: %(text_tert)s; }
    QScrollBar:horizontal { height: 10px; background: transparent; }
    QScrollBar::handle:horizontal { background: %(border_strong)s; border-radius: 3px; margin: 2px; min-width: 28px; }
    QScrollBar::handle:horizontal:hover { background: %(text_tert)s; }

    QToolTip { background-color: %(text)s; color: %(panel)s; border: none; border-radius: %(radius_button)s; padding: 5px 9px; }

    QStatusBar { background: %(chrome)s; color: %(text_tert)s; border-top: 1px solid %(divider)s; min-height: 26px; max-height: 26px; }
    QStatusBar QLabel { color: %(text_sec)s; padding: 0 6px; }
    QLabel#studioBadge { color: %(accent)s; background: %(accent_tint)s; border-radius: 8px; padding: 1px 8px; margin: 3px 6px; font-size: %(font_xs)s; font-weight: 600; }

    QSpinBox::up-arrow:pressed, QDoubleSpinBox::up-arrow:pressed { image: url(__STUDIO_UP_ACCENT__); }
    QSpinBox::down-arrow:pressed, QDoubleSpinBox::down-arrow:pressed { image: url(__STUDIO_DOWN_ACCENT__); }
    QToolBar QToolButton[popupMode="1"] { padding-right: 20px; }
    QToolBar QToolButton::menu-button { border: none; border-left: 1px solid transparent; border-top-right-radius: 7px; border-bottom-right-radius: 7px; width: 16px; background: transparent; }
    QToolBar QToolButton::menu-button:hover { background: %(hover)s; border-left-color: %(divider)s; }
    QToolBar QToolButton::menu-button:pressed { background: %(accent_tint)s; border-left-color: %(divider)s; }
    QToolBar QToolButton::menu-arrow { image: url(__STUDIO_ARROW_DOWN__); width: 10px; height: 10px; }
    QToolBar QToolButton::menu-arrow:open, QToolBar QToolButton::menu-arrow:pressed { image: url(__STUDIO_DOWN_ACCENT__); }
"""


# ── Preferred UI font ────────────────────────────────────────────────────
_FONT_CANDIDATES = ["Segoe UI Variable Text", "Inter", "SF Pro Text", "Segoe UI"]
_font_family = None


def _preferred_family():
    """First available Studio UI font, resolved once a QGuiApplication exists.

    Without a GUI application instance there is no font database to query;
    the result is cached only after a successful resolve so a late-created
    app still picks the family up.
    """
    global _font_family
    if _font_family:
        return _font_family
    if QGuiApplication.instance() is None:
        return None
    try:
        families = set(QFontDatabase().families())
    except Exception:
        return None
    for name in _FONT_CANDIDATES:
        if name in families:
            _font_family = name
            break
    return _font_family


def studio_extra(theme_name: str, scale: float = 1.0) -> str:
    """The Studio QSS overlay appended after the classic stylesheet."""
    params = {**theme.get_tokens(theme_name), **theme._font_tokens(scale)}
    extra = _STUDIO_QSS % params
    variant = "dark" if theme_name == DARK else "light"
    assets = theme._assets_dir()
    extra = extra.replace(
        "__STUDIO_CHECK__", f"{assets}/studio/check_mark_{variant}.svg")
    extra = extra.replace(
        "__STUDIO_UP_ACCENT__", f"{assets}/studio/arrow_up_accent_{variant}.svg")
    extra = extra.replace(
        "__STUDIO_DOWN_ACCENT__", f"{assets}/studio/arrow_down_accent_{variant}.svg")
    extra = extra.replace(
        "__STUDIO_ARROW_DOWN__",
        theme._ARROW_DOWN_DARK if variant == "dark" else theme._ARROW_DOWN_LIGHT)
    family = _preferred_family()
    if family:
        extra = f'    QWidget {{ font-family: "{family}"; }}\n' + extra
    return extra


# ── Canvas paint hooks ───────────────────────────────────────────────────

def _cosmetic_pen(color, width=1.0, style=Qt.PenStyle.SolidLine) -> QPen:
    pen = QPen(color, width, style)
    pen.setCosmetic(True)
    return pen


_original_update_parent_hint = None


def _studio_update_parent_hint(self):
    _original_update_parent_hint(self)
    hint = self._parent_hint
    if hint is None:
        return
    accent = QColor(_tokens()["accent"])
    line = QColor(accent)
    line.setAlphaF(0.9)
    pen = QPen(line, 1.5, Qt.PenStyle.CustomDashLine)
    pen.setCosmetic(True)
    pen.setDashPattern([4, 3])
    fill = QColor(accent)
    fill.setAlphaF(0.05)
    hint.setPen(pen)
    hint.setBrush(QBrush(fill))


_studio_update_parent_hint.__studio__ = True


def _studio_add_button_paint(self, painter: QPainter, option, widget=None):
    r = self.rect()
    cx, cy = r.center().x(), r.center().y()
    t = _tokens()
    accent = QColor(t["accent"])
    hovered = self._hovered
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    min_mm = min(r.width(), r.height())
    px_per_mm = abs(painter.worldTransform().m11()) or 1.0
    min_px = min_mm * px_per_mm

    # Inset by half a device-independent pixel so the cosmetic outline stays
    # inside the rect; a fixed mm inset would eat more of the button the
    # further you zoom in.
    inset = 0.5 / px_per_mm
    track = r.adjusted(inset, inset, -inset, -inset)
    rad = min_mm / 2
    fill = QColor(accent)
    fill.setAlphaF(0.16 if hovered else 0.07)
    if hovered:
        pen = _cosmetic_pen(accent, 1.2)
    else:
        edge = QColor(accent)
        edge.setAlphaF(0.55)
        pen = _cosmetic_pen(edge, 1.0, Qt.PenStyle.CustomDashLine)
        pen.setDashPattern([4, 3])
    painter.setPen(pen)
    painter.setBrush(QBrush(fill))
    painter.drawRoundedRect(track, rad, rad)

    if min_px >= 10:
        d = min_mm * 0.82
        badge = QRectF(cx - d / 2, cy - d / 2, d, d)
        if hovered:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(accent))
            glyph = QColor(t["on_accent"])
        else:
            ring = QColor(accent)
            ring.setAlphaF(0.9)
            painter.setPen(_cosmetic_pen(ring, 1.2))
            painter.setBrush(QBrush(QColor(255, 255, 255)))
            glyph = QColor(accent)
        painter.drawEllipse(badge)
        arm = d * 0.24
    else:
        # Too small for a badge: a bare accent "+".
        glyph = QColor(accent)
        arm = min_mm * 0.3
    glyph_pen = _cosmetic_pen(glyph, 1.8)
    glyph_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
    painter.setPen(glyph_pen)
    painter.drawLine(QPointF(cx - arm, cy), QPointF(cx + arm, cy))
    painter.drawLine(QPointF(cx, cy - arm), QPointF(cx, cy + arm))


_studio_add_button_paint.__studio__ = True


# ── Undo history timeline ────────────────────────────────────────────────

class StudioTimelineDelegate(QStyledItemDelegate):
    """Vertical timeline rows for the QUndoView history list."""

    ROW_H = 28
    RAIL_X = 16
    TEXT_X = 30

    def sizeHint(self, option, index):
        return QSize(option.rect.width(), self.ROW_H)

    def paint(self, painter: QPainter, option, index):
        t = _tokens()

        def c(key):
            return theme.token_color(t[key])

        view = self.parent()
        stack = view.stack()
        current = stack.index() if stack else 0
        clean = stack.cleanIndex() if stack else -1
        row = index.row()
        count = index.model().rowCount()
        r = QRectF(option.rect)
        rail_x = r.left() + self.RAIL_X
        cy = r.top() + r.height() / 2

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        pill = r.adjusted(4, 2, -4, -2)
        if row == current:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c("accent_tint")))
            painter.drawRoundedRect(pill, 6, 6)
        elif option.state & QStyle.StateFlag.State_MouseOver:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c("hover")))
            painter.drawRoundedRect(pill, 6, 6)

        applied_color = c("accent")
        applied_color.setAlphaF(0.45)
        applied = QPen(applied_color, 1.5)
        applied.setCapStyle(Qt.PenCapStyle.FlatCap)
        future = QPen(c("border_strong"), 1.2, Qt.PenStyle.CustomDashLine)
        future.setDashPattern([2, 2.5])

        if row > 0:
            painter.setPen(applied if row <= current else future)
            painter.drawLine(QPointF(rail_x, r.top()), QPointF(rail_x, cy))
        if row < count - 1:
            painter.setPen(applied if row < current else future)
            painter.drawLine(QPointF(rail_x, cy), QPointF(rail_x, r.bottom() + 1))

        accent = c("accent")
        center = QPointF(rail_x, cy)
        if row == current:
            halo = QColor(accent)
            halo.setAlphaF(0.18)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(halo))
            painter.drawEllipse(center, 6, 6)
            painter.setBrush(QBrush(accent))
            painter.drawEllipse(center, 3.5, 3.5)
        elif row == 0:
            painter.setPen(QPen(c("text_sec"), 1.4))
            painter.setBrush(QBrush(c("panel")))
            painter.drawEllipse(center, 3.5, 3.5)
        elif row < current:
            dot = QColor(accent)
            dot.setAlphaF(0.55)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(dot))
            painter.drawEllipse(center, 3, 3)
        else:
            painter.setPen(QPen(c("border_strong"), 1.2))
            painter.setBrush(QBrush(c("panel")))
            painter.drawEllipse(center, 3, 3)

        font = QFont(option.font)
        if row == current:
            font.setWeight(QFont.Weight.DemiBold)
        painter.setFont(font)
        painter.setPen(c("text") if row <= current else c("text_tert"))
        text_left = r.left() + self.TEXT_X
        right = r.right() - 6 - (14 if row == clean else 0)
        text_rect = QRectF(text_left, r.top(), max(0.0, right - text_left), r.height())
        text = str(index.data(Qt.ItemDataRole.DisplayRole) or "")
        elided = QFontMetrics(font).elidedText(
            text, Qt.TextElideMode.ElideRight, int(text_rect.width()))
        painter.drawText(
            text_rect,
            int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
            elided)

        if row == clean:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QBrush(c("success")))
            painter.drawEllipse(QPointF(r.right() - 10, cy), 2.5, 2.5)
        painter.restore()


# ── Studio main window ───────────────────────────────────────────────────

def _make_studio_window(base):
    """Build the MainWindow subclass; ``base`` is the classic MainWindow."""

    class StudioMainWindow(base):
        def __init__(self, *a, **kw):
            super().__init__(*a, **kw)
            self._studio_polish()
            self._studio_ready = True

        def _studio_polish(self):
            try:
                splitter = getattr(self, "splitter", None)
                if splitter is not None:
                    splitter.setObjectName("studioSplitter")
                left_tabs = getattr(self, "left_tabs", None)
                if left_tabs is not None:
                    left_tabs.setObjectName("studioSideTabs")
                    left_tabs.tabBar().setDrawBase(False)
                tab_widget = getattr(self, "tab_widget", None)
                if tab_widget is not None:
                    tab_widget.setObjectName("studioDocTabs")
                toolbar = getattr(self, "toolbar", None)
                if toolbar is not None:
                    toolbar.setIconSize(QSize(18, 18))
                statusbar = getattr(self, "statusbar", None)
                if statusbar is not None:
                    badge = QLabel("Studio")
                    badge.setObjectName("studioBadge")
                    badge.setToolTip(
                        "Studio skin preview (main_studio.py) — visual only; "
                        "projects and settings are shared with the classic app")
                    statusbar.addPermanentWidget(badge)
            except Exception:
                _log.exception("studio polish (chrome) failed")
            try:
                # Layers tree: the delegate draws its own accent bar, so the
                # palette-wide Accent (used by the style for a row pill) is hidden.
                layers_tree = getattr(getattr(self, "layers_panel", None), "tree", None)
                if layers_tree is not None:
                    pal = QPalette(layers_tree.palette())
                    for group in (QPalette.ColorGroup.Active,
                                  QPalette.ColorGroup.Inactive,
                                  QPalette.ColorGroup.Disabled):
                        pal.setColor(group, QPalette.ColorRole.Accent, QColor(0, 0, 0, 0))
                    layers_tree.setPalette(pal)
            except Exception:
                _log.exception("studio polish (layers palette) failed")
            try:
                history = getattr(self, "history_view", None)
                if history is not None:
                    self._studio_timeline_delegate = StudioTimelineDelegate(history)
                    history.setItemDelegate(self._studio_timeline_delegate)
            except Exception:
                _log.exception("studio polish (history delegate) failed")
            try:
                app = QApplication.instance()
                if app is not None:
                    app.setStyleSheet(theme.get_stylesheet(
                        getattr(self, "_current_theme", LIGHT),
                        self._current_font_scale()))
            except Exception:
                _log.exception("studio polish (stylesheet) failed")
            try:
                self._studio_apply_tokens()
            except Exception:
                _log.exception("studio polish (tokens) failed")
            try:
                self._update_window_title()
            except Exception:
                _log.exception("studio polish (title) failed")

        def _studio_apply_tokens(self):
            t = _tokens()
            splitter = getattr(self, "splitter", None)
            if splitter is not None:
                for i in range(1, splitter.count()):
                    try:
                        btn = getattr(splitter.handle(i), "_btn", None)
                        if btn is not None:
                            btn.setStyleSheet(
                                "QToolButton { border: none; background: transparent; "
                                f"color: {t['text_tert']}; border-radius: 5px; font-size: 8px; }} "
                                f"QToolButton:hover {{ background: {t['hover']}; color: {t['accent']}; }}")
                    except Exception:
                        _log.exception("studio splitter handle polish failed")
            draw_label = getattr(self, "draw_mode_label", None)
            if draw_label is not None:
                draw_label.setStyleSheet(
                    f"background-color: {t['accent']}; color: {t['on_accent']}; "
                    "font-weight: 600; border-radius: 9px; padding: 1px 10px; margin: 3px 4px;")
            update_label = getattr(self, "update_available_label", None)
            if update_label is not None:
                update_label.setStyleSheet(
                    f"color: {t['accent']}; font-size: 12px; padding: 0 8px;")
            header = getattr(getattr(self, "layers_panel", None), "header_label", None)
            if header is not None:
                header.setStyleSheet(
                    "font-weight: 600; font-size: 11px; letter-spacing: 0.6px; "
                    f"padding: 0 2px; color: {t['label_caps']};")

        def _apply_theme(self, theme_name, animate=True):
            _state["theme"] = theme_name
            super()._apply_theme(theme_name, animate)
            if getattr(self, "_studio_ready", False):
                self._studio_apply_tokens()
                for tab in getattr(self, "_tabs", []):
                    scene = getattr(tab, "scene", None)
                    if scene:
                        scene._update_parent_hint()
                        scene.update()

        def _update_window_title(self):
            super()._update_window_title()
            title = self.windowTitle()
            if not title.endswith(" · Studio"):
                self.setWindowTitle(title + " · Studio")

    return StudioMainWindow


# ── Install ──────────────────────────────────────────────────────────────
_INSTALLED = False


def install(patch_window: bool = True) -> None:
    """Install the Studio skin over src.app.theme.

    Idempotent. Raises RuntimeError when an app module that binds theme
    functions at import time was already imported — the skin must be
    installed before them (main_studio.py does exactly that).
    """
    global _INSTALLED, _original_update_parent_hint
    if _INSTALLED:
        return
    for mod_name in ("src.app.main_window", "src.app.layers_panel",
                     "src.plot_editor.chrome"):
        if mod_name in sys.modules:
            raise RuntimeError(
                f"studio_skin.install() must run before {mod_name} is imported")
    assert set(STUDIO_LIGHT) == set(theme._TOKENS_LIGHT), \
        "STUDIO_LIGHT keys drifted from theme._TOKENS_LIGHT"
    assert set(STUDIO_DARK) == set(theme._TOKENS_LIGHT), \
        "STUDIO_DARK keys drifted from theme._TOKENS_LIGHT"

    original_stylesheet = theme.get_stylesheet
    original_font_scale = theme.apply_font_scale
    original_build_palette = theme.build_palette

    def _studio_stylesheet(theme_name, scale=1.0):
        return original_stylesheet(theme_name, scale) + studio_extra(theme_name, scale)

    def _studio_apply_font_scale(app, scale, theme_name=LIGHT):
        clamped = original_font_scale(app, scale, theme_name)
        f = app.font()
        family = _preferred_family()
        if family:
            f.setFamily(family)
        f.setWeight(QFont.Weight.Normal)
        app.setFont(f)
        app.setStyleSheet(theme.get_stylesheet(theme_name, clamped))
        return clamped

    def _studio_build_palette(theme_name):
        pal = original_build_palette(theme_name)
        pal.setColor(QPalette.ColorRole.Accent,
                     QColor(theme.get_tokens(theme_name)["accent"]))
        return pal

    theme._TOKENS_LIGHT.clear()
    theme._TOKENS_LIGHT.update(STUDIO_LIGHT)
    theme._TOKENS_DARK.clear()
    theme._TOKENS_DARK.update(STUDIO_DARK)
    theme.get_stylesheet = _studio_stylesheet
    theme.apply_font_scale = _studio_apply_font_scale
    theme.build_palette = _studio_build_palette

    # A Studio process never forwards file launches to a classic window and
    # never registers itself as a forward target — the two skins stay apart.
    from src.app import instance_router
    instance_router.forward_to_running_instance = lambda *a, **kw: False
    instance_router.InstanceServer.start = lambda self, *a, **kw: False

    if patch_window:
        from src.canvas import canvas_scene, add_button_item
        _original_update_parent_hint = canvas_scene.CanvasScene._update_parent_hint
        canvas_scene.CanvasScene._update_parent_hint = _studio_update_parent_hint
        add_button_item.AddButtonItem.paint = _studio_add_button_paint

        from src.app import main_window
        main_window.MainWindow = _make_studio_window(main_window.MainWindow)

    _INSTALLED = True
