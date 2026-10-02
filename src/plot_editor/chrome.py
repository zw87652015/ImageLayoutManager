"""Plot Editor chrome adapter: ILM theme/icons, read-only settings.

The standalone editor consumes ILM's shared style template
(``src.app.theme`` palette/QSS/font scale, ``src.app.icons``) so its
chrome matches the main app exactly.  Settings are read-only: the user's
saved theme, font scale and motion choices are honoured, never written.
"""

from __future__ import annotations

from PyQt6.QtCore import QSettings

from src.app.icons import make_icon
from src.app.theme import (DARK, LIGHT, _font_tokens, apply_font_scale,
                           build_palette, get_tokens)


def saved_theme() -> str:
    value = QSettings('AcademicFigureLayout', 'ImageLayoutManager').value(
        'theme', LIGHT)
    return DARK if value == DARK else LIGHT


def saved_font_scale() -> float:
    value = QSettings('AcademicFigureLayout', 'ImageLayoutManager').value(
        'ui/font_scale', 1.0)
    try:
        return float(value)
    except (TypeError, ValueError):
        return 1.0


def apply_app_style(app) -> str:
    theme = saved_theme()
    app.setPalette(build_palette(theme))
    apply_font_scale(app, saved_font_scale(), theme)
    return theme


def themed_icon(name: str, theme: str, role: str = 'text'):
    return make_icon(name, get_tokens(theme)[role])


def style_tokens(theme: str, scale: float) -> dict:
    return {**get_tokens(theme), **_font_tokens(scale)}


_WORKSHEET_QSS = """
QTableView#plotWorksheet, QTableView#plotWorksheetLabels {
    background: %(surface)s;
    color: %(text)s;
    gridline-color: %(divider)s;
    border: none;
    outline: none;
    font-size: %(font_md)s;
    selection-background-color: %(accent_tint)s;
    selection-color: %(text)s;
}
QTableView#plotWorksheetLabels {
    background: %(surface_subtle)s;
    color: %(text_sec)s;
    border-bottom: 1px solid %(border)s;
}
QTableView#plotWorksheet::item, QTableView#plotWorksheetLabels::item {
    background: transparent;
    border: none;
}
QTableView#plotWorksheet::item:hover,
QTableView#plotWorksheetLabels::item:hover {
    background: transparent;
}
QTableView#plotWorksheet::item:selected,
QTableView#plotWorksheetLabels::item:selected {
    background: %(accent_tint)s;
    color: %(text)s;
}
QTableView#plotWorksheet QHeaderView::section,
QTableView#plotWorksheetLabels QHeaderView::section {
    background: %(panel)s;
    color: %(text_sec)s;
    border: none;
    border-right: 1px solid %(divider)s;
    border-bottom: 1px solid %(divider)s;
    padding: 0 6px;
    font-size: %(font_sm)s;
    font-weight: 500;
}
QTableView#plotWorksheet QHeaderView::section:checked,
QTableView#plotWorksheetLabels QHeaderView::section:checked {
    background: %(accent_tint)s;
    color: %(accent)s;
}
QTableView#plotWorksheet QTableCornerButton::section {
    background: %(panel)s;
    border: none;
    border-right: 1px solid %(divider)s;
    border-bottom: 1px solid %(divider)s;
}
QLineEdit#plotWorksheetEditor {
    border: 1px solid %(border)s;
    border-radius: 0;
    padding: 0 4px;
    min-height: 0;
    background: %(surface)s;
    color: %(text)s;
    font-size: %(font_md)s;
}
"""


def worksheet_stylesheet(theme: str, scale: float) -> str:
    return _WORKSHEET_QSS % style_tokens(theme, scale)
