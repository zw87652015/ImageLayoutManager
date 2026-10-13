"""QComboBox drawn as a row of pictogram tiles with a caption line.

Still a real QComboBox (items, currentIndex, signals and blockSignals work as
before); only painting, mouse, and keyboard selection differ. There is no
popup and the wheel never changes the value, so scrolling the Inspector is safe.
"""

from PyQt6.QtCore import QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QFontMetrics, QPainter, QPalette, QPen
from PyQt6.QtWidgets import QComboBox, QSizePolicy

from src.app.pictogram_layout import row_width, tile_at, tile_rects
from src.app.pictograms import draw_pictogram


def _tint(color, alpha):
    c = QColor(color)
    c.setAlpha(alpha)
    return c


class PictogramCombo(QComboBox):
    TILE_H = 30
    GAP = 4
    CAPTION_H = 14
    MIN_W = 28
    MAX_W = 44

    def __init__(self, pictograms, parent=None, *, caption_suffix="", mirror=False):
        super().__init__(parent)
        self._pictograms = list(pictograms)
        self._caption_suffix = caption_suffix
        self._caption_tip = False
        self._mirror = mirror
        self._vertical = False
        self._hover = -1
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.TILE_H + self.GAP + self.CAPTION_H)
        model = self.model()
        for signal in (model.rowsInserted, model.rowsRemoved, model.modelReset,
                       model.dataChanged, model.layoutChanged):
            signal.connect(self._refresh_accessibility)
        self._refresh_accessibility()

    # ── configuration ────────────────────────────────────────────────────

    def set_orientation(self, orientation: str):
        self._vertical = orientation == "vertical"
        self.update()

    def setItemText(self, index, text):
        super().setItemText(index, text)
        self._refresh_accessibility()

    def _refresh_accessibility(self, *_args):
        names = [self.itemText(i) for i in range(self.count())]
        self.setAccessibleDescription(", ".join(names))

    def _tile_rects(self):
        return tile_rects(self.width(), self.count(), min_w=self.MIN_W,
                          max_w=self.MAX_W, gap=self.GAP, height=self.TILE_H)

    def _height(self):
        return self.TILE_H + self.GAP + self.CAPTION_H

    def sizeHint(self):
        return QSize(row_width(self.count(), 36, self.GAP), self._height())

    def minimumSizeHint(self):
        return QSize(row_width(self.count(), self.MIN_W, self.GAP), self._height())

    # ── popup and wheel are disabled ─────────────────────────────────────

    def showPopup(self):
        pass

    def wheelEvent(self, event):
        event.ignore()

    # ── painting ─────────────────────────────────────────────────────────

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        if not self.isEnabled():
            p.setOpacity(0.4)
        pal = self.palette()
        base = pal.color(QPalette.ColorRole.Base)
        mid = pal.color(QPalette.ColorRole.Mid)
        text = pal.color(QPalette.ColorRole.Text)
        accent = pal.color(QPalette.ColorRole.Highlight)
        current = self.currentIndex()
        rects = self._tile_rects()
        focus_index = current if current >= 0 else (0 if rects else -1)

        for i, (x, y, w, h) in enumerate(rects):
            rect = QRectF(x, y, w, h)
            selected = i == current
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QBrush(base))
            p.drawRoundedRect(rect, 6, 6)
            if selected:
                p.setBrush(QBrush(_tint(accent, 40)))
                p.drawRoundedRect(rect, 6, 6)
            if i == self._hover:
                p.setBrush(QBrush(_tint(accent, 18)))
                p.drawRoundedRect(rect, 6, 6)
            if selected:
                border, inset = QPen(accent, 1.5), 0.75
            else:
                border, inset = QPen(_tint(mid, 110), 1.0), 0.5
            p.setPen(border)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(rect.adjusted(inset, inset, -inset, -inset), 6, 6)

            ink = accent if selected else _tint(text, 190)
            key = self._pictograms[i] if i < len(self._pictograms) else ""
            picto_rect = rect.adjusted(5, 5, -5, -5)
            p.save()
            if self._vertical:
                centre = picto_rect.center()
                p.translate(centre)
                p.rotate(90)
                p.translate(-centre)
            draw_pictogram(key, p, picto_rect, ink, accent, mirror=self._mirror)
            p.restore()

            if i == focus_index and self.hasFocus():
                p.setPen(QPen(accent, 1.0, Qt.PenStyle.DotLine))
                p.setBrush(Qt.BrushStyle.NoBrush)
                # Inside the tile: the first tile sits at x = 0 / y = 0, so an
                # outset ring would be clipped by the widget edge.
                p.drawRoundedRect(rect.adjusted(2.5, 2.5, -2.5, -2.5), 4, 4)

        caption = (self.currentText() + self._caption_suffix) if current >= 0 else "—"
        font = QFont(self.font())
        font.setPixelSize(11)
        p.setFont(font)
        p.setPen(_tint(text, 153))
        shown = QFontMetrics(font).elidedText(caption, Qt.TextElideMode.ElideRight, int(self.width()))
        if shown != caption:
            self.setToolTip(caption)
            self._caption_tip = True
        elif self._caption_tip:
            self.setToolTip("")
            self._caption_tip = False
        p.drawText(QRectF(0, self.TILE_H + self.GAP, self.width(), self.CAPTION_H),
                   int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter),
                   shown)
        p.end()

    # ── mouse ────────────────────────────────────────────────────────────

    def mouseMoveEvent(self, event):
        pos = event.position()
        index = tile_at(pos.x(), pos.y(), self._tile_rects())
        if index != self._hover:
            self._hover = index
            self.update()
        if index >= 0:
            self.setToolTip(self.itemText(index) + self._caption_suffix)
        else:
            self.setToolTip("")

    def leaveEvent(self, event):
        self._hover = -1
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            index = tile_at(event.position().x(), event.position().y(), self._tile_rects())
            if index >= 0:
                self._select(index)
            event.accept()
            return
        event.accept()

    def _select(self, index):
        self.setCurrentIndex(index)
        self.activated.emit(index)
        self.textActivated.emit(self.itemText(index))

    # ── keyboard ─────────────────────────────────────────────────────────

    def keyPressEvent(self, event):
        key = event.key()
        if (key in (Qt.Key.Key_Space, Qt.Key.Key_F4)
                or (key == Qt.Key.Key_Down
                    and event.modifiers() & Qt.KeyboardModifier.AltModifier)):
            event.accept()
            return
        count = self.count()
        if count:
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
            if target is not None:
                self._select(target)
                event.accept()
                return
        super().keyPressEvent(event)

    def focusInEvent(self, event):
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self.update()
