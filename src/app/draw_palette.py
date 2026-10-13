"""Floating shape-tool palette shown over the canvas while Draw mode is on."""

from PyQt6.QtCore import QEvent, QSize, Qt
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QToolButton

from src.app.i18n import tr
from src.app.icons import make_icon

_ICON = 18
_BUTTON = 28


class DrawPalette(QFrame):

    def __init__(self, tool_actions, keep_action, on_done, parent=None):
        super().__init__(parent)
        self.setObjectName("drawPalette")
        self._keep = keep_action
        self._on_done = on_done
        self._view = None
        self._color = "#222222"
        layout = QHBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 4)
        layout.setSpacing(2)
        for action in tool_actions:
            layout.addWidget(self._tool_button(action))
        separator = QFrame(self)
        separator.setObjectName("drawPaletteSep")
        separator.setFrameShape(QFrame.Shape.VLine)
        layout.addWidget(separator)
        layout.addWidget(self._tool_button(keep_action))
        self._done = QToolButton(self)
        self._done.setObjectName("drawPaletteDone")
        self._done.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self._done.clicked.connect(lambda checked=False: self._on_done())
        layout.addWidget(self._done)
        keep_action.toggled.connect(lambda _checked: self._refresh_lock())
        self.retranslate()
        self._refresh_lock()
        self.hide()

    def _tool_button(self, action):
        button = QToolButton(self)
        button.setDefaultAction(action)
        button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)
        button.setIconSize(QSize(_ICON, _ICON))
        button.setFixedSize(_BUTTON, _BUTTON)
        button.setAutoRaise(True)
        return button

    def _refresh_lock(self):
        name = "lock_closed" if self._keep.isChecked() else "lock_open"
        self._keep.setIcon(make_icon(name, self._color, _ICON))

    def retranslate(self):
        self._done.setText(tr("draw_palette_done"))

    def apply_theme(self, tokens):
        self._color = tokens["text"]
        self._refresh_lock()

    def place(self, view):
        if self._view is not view:
            if self._view is not None:
                self._view.removeEventFilter(self)
            self._view = view
            view.installEventFilter(self)
        self.setParent(view)
        self.adjustSize()
        self._reposition()
        self.show()
        self.raise_()

    def _reposition(self):
        if self._view is None:
            return
        viewport = self._view.viewport().geometry()
        x = viewport.x() + (viewport.width() - self.width()) // 2
        self.move(max(8, x), viewport.y() + 8)

    def eventFilter(self, obj, event):
        if obj is self._view and event.type() == QEvent.Type.Resize and self.isVisible():
            self._reposition()
        return super().eventFilter(obj, event)
