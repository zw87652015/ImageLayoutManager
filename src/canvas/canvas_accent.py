"""Single source of the canvas accent colour.

CanvasScene.apply_theme sets it from the active theme. Until then it resolves
from the classic light accent each time it is read (never cached), so a skin
that patches the theme tokens before any canvas use is picked up.
"""

from PyQt6.QtGui import QColor

_current = None


def set_accent(color: str) -> None:
    global _current
    _current = str(color)


def accent(alpha: int = 255) -> QColor:
    if _current is not None:
        name = _current
    else:
        from src.app.theme import get_tokens, LIGHT
        name = get_tokens(LIGHT)["accent"]
    color = QColor(name)
    color.setAlpha(alpha)
    return color
