"""Single source of the canvas accent and on-accent colours.

CanvasScene.apply_theme sets them from the active theme. Until then they
resolve from the light theme each time they are read (never cached), so
callers always see the current token values.
"""

from PyQt6.QtGui import QColor

_current = None
_on_current = None


def set_accent(color: str) -> None:
    global _current
    _current = str(color)


def set_on_accent(color: str) -> None:
    global _on_current
    _on_current = str(color)


def accent(alpha: int = 255) -> QColor:
    if _current is not None:
        name = _current
    else:
        from src.app.theme import get_tokens, LIGHT
        name = get_tokens(LIGHT)["accent"]
    color = QColor(name)
    color.setAlpha(alpha)
    return color


def on_accent(alpha: int = 255) -> QColor:
    if _on_current is not None:
        name = _on_current
    else:
        from src.app.theme import get_tokens, LIGHT
        name = get_tokens(LIGHT)["on_accent"]
    color = QColor(name)
    color.setAlpha(alpha)
    return color
