"""Mini figure under Label Hierarchy: three panels, the second split into two labelled sub-panels."""

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QBrush, QFont, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QWidget

from src.app.i18n import tr
from src.utils.numbering_preview import preview

_HEIGHT = 110
_GAP = 10


class NumberingPreview(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._rows = preview("(a)", "", False, "")
        self.setFixedHeight(_HEIGHT)
        self.setAccessibleName(tr("numbering_preview_label"))
        self.setToolTip(tr("numbering_preview_label"))

    def set_scheme(self, main_scheme, sub_scheme, prefix_parent, separator):
        self._rows = preview(main_scheme or "a", sub_scheme or "", bool(prefix_parent), separator or "")
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        pal = self.palette()
        text = pal.color(QPalette.ColorRole.Text)
        mid = pal.color(QPalette.ColorRole.Mid)
        base = pal.color(QPalette.ColorRole.Base)
        accent = pal.color(QPalette.ColorRole.Highlight)
        font = QFont(self.font())
        font.setPixelSize(12)
        small = QFont(self.font())
        small.setPixelSize(10)
        count = len(self._rows)
        slot_w = (self.width() - _GAP * (count + 1)) / count
        top = 22.0
        bottom = self.height() - 8.0
        for index, (label, subs) in enumerate(self._rows):
            x = _GAP + index * (slot_w + _GAP)
            painter.setFont(font)
            painter.setPen(text)
            painter.drawText(QRectF(x, 0, slot_w, top - 2), int(Qt.AlignmentFlag.AlignCenter), label)
            panel = QRectF(x, top, slot_w, bottom - top)
            painter.setPen(QPen(mid, 1))
            painter.setBrush(QBrush(base))
            painter.drawRoundedRect(panel, 4, 4)
            if not subs:
                continue
            half = (panel.height() - 6) / 2
            for sub_index, sub_label in enumerate(subs[:2]):
                sub = QRectF(panel.left() + 4, panel.top() + 3 + sub_index * (half + 0), panel.width() - 8, half - 3)
                painter.setPen(QPen(accent, 1.2))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRoundedRect(sub, 3, 3)
                painter.setFont(small)
                painter.setPen(accent)
                painter.drawText(sub.adjusted(4, 1, -2, 0), int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop),
                                 sub_label)
                painter.setFont(font)
        painter.end()
