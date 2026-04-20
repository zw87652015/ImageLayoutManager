"""Light/Dark segmented control for the toolbar.

Mirrors the ``#themeSeg`` pill from the redesign mockups
(afl-macos-mockup.html / afl-windows-mockup.html). Exposes a single
``themeChanged(str)`` signal emitting ``"light"`` or ``"dark"``.

The widget only handles *interaction*; the owning window is responsible
for actually applying the theme (e.g. ``MainWindow._apply_theme``). This
keeps the widget reusable and free of imports from ``main_window``.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QToolButton, QButtonGroup

from src.app.theme import LIGHT, DARK
from src.app.icons import make_icon
from src.app.i18n import tr


class ThemeSegmented(QFrame):
    """Two-button pill: sun (light) | moon (dark)."""

    themeChanged = pyqtSignal(str)  # "light" or "dark"

    def __init__(self, initial: str = LIGHT, parent=None):
        super().__init__(parent)
        self.setObjectName("themeSegmented")
        self.setFrameShape(QFrame.Shape.NoFrame)

        lay = QHBoxLayout(self)
        lay.setContentsMargins(2, 2, 2, 2)
        lay.setSpacing(2)

        self._light_btn = self._make_seg_button(tr("theme_light"))
        self._dark_btn = self._make_seg_button(tr("theme_dark"))
        lay.addWidget(self._light_btn)
        lay.addWidget(self._dark_btn)

        # Manual exclusivity (QButtonGroup works but we need the toggle to
        # also fire themeChanged only when the user actually flips state).
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        self._group.addButton(self._light_btn)
        self._group.addButton(self._dark_btn)

        self._light_btn.clicked.connect(lambda: self._on_clicked(LIGHT))
        self._dark_btn.clicked.connect(lambda: self._on_clicked(DARK))

        self.set_theme(initial)
        # Initial icons (white-ish so they show on both themes — refreshed
        # later by refresh_icons() when the owner knows the text colour).
        self.refresh_icons("#6E6E73", "#8E8E93")

    # ── public API ────────────────────────────────────────────────────
    def set_theme(self, theme: str) -> None:
        """Update checked state without emitting ``themeChanged``."""
        self._light_btn.blockSignals(True)
        self._dark_btn.blockSignals(True)
        self._light_btn.setChecked(theme == LIGHT)
        self._dark_btn.setChecked(theme == DARK)
        self._light_btn.blockSignals(False)
        self._dark_btn.blockSignals(False)

    def refresh_icons(self, active_color: str, inactive_color: str) -> None:
        """Rebuild the two glyphs. Call on theme change for proper tint.

        ``active_color`` is used for the currently-selected button;
        ``inactive_color`` for the other. That way the checked pill's
        glyph picks up the accent tint from QSS while the idle one stays
        subdued.
        """
        light_col = active_color if self._light_btn.isChecked() else inactive_color
        dark_col = active_color if self._dark_btn.isChecked() else inactive_color
        self._light_btn.setIcon(make_icon("sun", light_col, size=16))
        self._dark_btn.setIcon(make_icon("moon", dark_col, size=16))

    def retranslate_ui(self) -> None:
        """Update button labels to the current language."""
        self._light_btn.setText(tr("theme_light"))
        self._dark_btn.setText(tr("theme_dark"))

    # ── internals ─────────────────────────────────────────────────────
    def _make_seg_button(self, text: str) -> QToolButton:
        btn = QToolButton(self)
        btn.setText(text)
        btn.setCheckable(True)
        btn.setAutoRaise(True)
        btn.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.setProperty("segmentedButton", True)
        return btn

    def _on_clicked(self, theme: str) -> None:
        # Ensure checked state is stable even if user double-clicks the
        # already-active pill (Qt would otherwise untoggle it).
        self.set_theme(theme)
        self.themeChanged.emit(theme)
