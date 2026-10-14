"""Numbering scheme picker: a QComboBox drawn as a wrapping grid of label chips.

A real QComboBox, so addItems/currentText/setCurrentText/currentIndex and the
currentIndexChanged/currentTextChanged signals keep working. Each chip shows the
first three labels of its scheme ("a b c"); the none item shows "—". There is no
popup and the wheel does not change the value.
"""

import math

from PyQt6.QtCore import QRectF, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QBrush, QColor, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QComboBox, QSizePolicy

from src.utils.label_numbering import format_index

_CHIP_W = 64
_CHIP_H = 30
_GAP = 6
_SELECTORS = "aAiI1"


class SchemePicker(QComboBox):
    activated = pyqtSignal(int)
    textActivated = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMinimumWidth(_CHIP_W * 2)
        policy = QSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        policy.setHeightForWidth(True)
        self.setSizePolicy(policy)
        self._hover = None

    # ── sizing ───────────────────────────────────────────────────────────

    def _columns(self, width):
        return max(1, int((width + _GAP) // (_CHIP_W + _GAP)))

    def hasHeightForWidth(self):
        return True

    def heightForWidth(self, width):
        rows = math.ceil(max(1, self.count()) / self._columns(width))
        return rows * (_CHIP_H + _GAP) + _GAP

    def sizeHint(self):
        width = (_CHIP_W + _GAP) * 4 + _GAP
        return QSize(width, self.heightForWidth(width))

    # ── scheme helpers ───────────────────────────────────────────────────

    def _scheme_at(self, index):
        data = self.itemData(index)
        return data if isinstance(data, str) else self.itemText(index)

    def _chip_label(self, index):
        scheme = self._scheme_at(index)
        if not scheme or not any(ch in _SELECTORS for ch in scheme):
            return "—"
        return " ".join(format_index(i, scheme) for i in range(3))

    def _chip_rects(self):
        columns = self._columns(self.width())
        rects = []
        for index in range(self.count()):
            row, col = divmod(index, columns)
            rects.append(QRectF(_GAP + col * (_CHIP_W + _GAP), _GAP + row * (_CHIP_H + _GAP), _CHIP_W, _CHIP_H))
        return rects

    def _index_at(self, pos):
        for index, rect in enumerate(self._chip_rects()):
            if rect.contains(pos):
                return index
        return -1

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        accent = pal.color(QPalette.ColorRole.Highlight)
        text = pal.color(QPalette.ColorRole.Text)
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        current = self.currentIndex()
        font = QFont(self.font())
        font.setPixelSize(12)
        painter.setFont(font)
        enabled = self.isEnabled()
        for index, rect in enumerate(self._chip_rects()):
            selected = index == current
            hovered = index == self._hover
            if selected:
                tint = QColor(accent)
                tint.setAlpha(40)
                painter.setPen(QPen(accent, 1.5))
                painter.setBrush(QBrush(tint))
            else:
                painter.setPen(QPen(mid, 1))
                painter.setBrush(QBrush(base))
            painter.save()
            if not enabled:
                painter.setOpacity(0.4)
            painter.drawRoundedRect(rect, 6, 6)
            if hovered and not selected:
                wash = QColor(accent)
                wash.setAlpha(18)
                painter.setPen(Qt.PenStyle.NoPen)
                painter.setBrush(QBrush(wash))
                painter.drawRoundedRect(rect, 6, 6)
            painter.setPen(accent if selected else text)
            painter.drawText(rect, int(Qt.AlignmentFlag.AlignCenter), self._chip_label(index))
            painter.restore()
        painter.end()

    # ── mouse ────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        index = self._index_at(event.position())
        if index != self._hover:
            self._hover = index
            self.update()
        self.setToolTip(self._scheme_at(index) if index >= 0 else "")
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self._hover = None
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            return
        index = self._index_at(event.position())
        if index >= 0 and index != self.currentIndex():
            self.setCurrentIndex(index)
            self.activated.emit(index)
            self.textActivated.emit(self.itemText(index))
        self.setFocus()

    # ── overrides: no popup, no wheel change ─────────────────────────────

    def showPopup(self):
        return

    def wheelEvent(self, event):
        event.ignore()

    def keyPressEvent(self, event):
        key = event.key()
        count = self.count()
        current = self.currentIndex()
        target = None
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Up):
            target = max(0, current - 1)
        elif key in (Qt.Key.Key_Right, Qt.Key.Key_Down):
            target = min(count - 1, current + 1)
        elif key == Qt.Key.Key_Home:
            target = 0
        elif key == Qt.Key.Key_End:
            target = count - 1
        elif key in (Qt.Key.Key_Space, Qt.Key.Key_F4) or (
                key == Qt.Key.Key_Down and event.modifiers() & Qt.KeyboardModifier.AltModifier):
            event.accept()
            return
        if target is None or count == 0:
            super().keyPressEvent(event)
            return
        if target != current:
            self.setCurrentIndex(target)
            self.activated.emit(target)
            self.textActivated.emit(self.itemText(target))
        event.accept()
