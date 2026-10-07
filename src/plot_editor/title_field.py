"""Slim always-visible plot-title field for the Plot Editor."""

from __future__ import annotations

from PyQt6.QtCore import QEvent, Qt, pyqtSignal
from PyQt6.QtGui import QPalette, QPixmap
from PyQt6.QtWidgets import (QLabel, QLineEdit, QStackedLayout, QWidget)

from .i18n import tr
from ilmplot.mathtext import has_math


class PlotTitleField(QWidget):
    """Dashed placeholder label; double-click switches to a QLineEdit."""

    title_changed = pyqtSignal(str)

    def __init__(self, theme, scale=1.0, parent=None):
        super().__init__(parent)
        self.setObjectName('plotTitleField')
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        from . import chrome
        self.setStyleSheet(chrome.title_stylesheet(theme, scale))
        self._title = ''
        self._display = QLabel(tr('title_placeholder'))
        self._display.setObjectName('plotTitleDisplay')
        self._display.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._display.setAttribute(
            Qt.WidgetAttribute.WA_Hover, True)
        self._display.setProperty('empty', True)
        self._display.installEventFilter(self)
        self._editor = QLineEdit()
        self._editor.setObjectName('plotTitleEditor')
        self._editor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._editor.installEventFilter(self)
        self._editor.returnPressed.connect(self._commit)
        self._editor.editingFinished.connect(self._commit)
        self._stack = QStackedLayout(self)
        self._stack.setContentsMargins(8, 4, 8, 4)
        self._stack.addWidget(self._display)
        self._stack.addWidget(self._editor)
        self.ensurePolished()
        self._display.ensurePolished()
        self.setFixedHeight(self._display.sizeHint().height() + 8)

    def eventFilter(self, obj, event):
        if obj is self._display:
            if event.type() == QEvent.Type.MouseButtonDblClick:
                self._edit()
                return True
        elif obj is self._editor:
            if (event.type() == QEvent.Type.KeyPress
                    and event.key() == Qt.Key.Key_Escape):
                self._cancel()
                return True
        return super().eventFilter(obj, event)

    def title(self):
        return self._title

    def set_title(self, text):
        """Set the title without emitting ``title_changed``."""
        self._title = text
        self._update_display()

    def _update_display(self):
        empty = not self._title
        self._display.setProperty('empty', empty)
        if not empty and has_math(self._title):
            from .math_render import math_pixmap
            pm = math_pixmap(
                self._title, self._display.font(),
                self._display.palette().color(QPalette.ColorRole.WindowText),
                self._display.devicePixelRatioF())
            if pm is not None:
                # Keep the fixed height: shrink the pixmap to fit.
                avail = self._display.sizeHint().height()
                dpr = pm.devicePixelRatio() or 1.0
                if pm.height() / dpr > avail > 0:
                    pm = pm.scaled(
                        pm.size() * (avail * dpr / pm.height()),
                        Qt.AspectRatioMode.KeepAspectRatio,
                        Qt.TransformationMode.SmoothTransformation)
                    pm.setDevicePixelRatio(dpr)
                self._display.setPixmap(pm)
                self._display.setText('')
            else:
                self._display.setPixmap(QPixmap())
                self._display.setText(self._title)
        else:
            self._display.setPixmap(QPixmap())
            self._display.setText(
                tr('title_placeholder') if empty else self._title)
        self._display.style().unpolish(self._display)
        self._display.style().polish(self._display)

    def _edit(self):
        self._editor.blockSignals(True)
        self._editor.setText(self._title)
        self._editor.blockSignals(False)
        self._editor.selectAll()
        self._stack.setCurrentWidget(self._editor)
        self._editor.setFocus()

    def _commit(self):
        if self._stack.currentWidget() is not self._editor:
            return
        self._stack.setCurrentWidget(self._display)
        text = self._editor.text().strip()
        if text != self._title:
            self._title = text
            self._update_display()
            self.title_changed.emit(text)

    def _cancel(self):
        self._stack.setCurrentWidget(self._display)
