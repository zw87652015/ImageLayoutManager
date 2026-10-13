"""Spotlight tour of the main window: a dimmed layer with a hole around each target and a caption card.

The overlay covers the window and takes all pointer input, so the tour is read-only.
Keys: Right/Enter next, Left back, Escape exit. Targets come from ui_targets.resolve_target;
a step whose target cannot be found is skipped.
"""

from PyQt6.QtCore import QEvent, QObject, QRect, QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QFont, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QToolButton, QVBoxLayout, QWidget

from src.app.i18n import current_language, tr
from src.app.motion import MotionTween
from src.app.ui_targets import resolve_target
from src.app.help_content import TOUR_STEPS, place_bubble

_PAD = 8
_RADIUS = 8
_CARD_W = 300
_MOVE_MS = 180


def _text(pair):
    return pair[1] if current_language() == "zh" else pair[0]


class TourOverlay(QWidget):
    finished = pyqtSignal()

    def __init__(self, window, steps=TOUR_STEPS):
        super().__init__(window)
        self.window_ref = window
        self.steps = tuple(steps)
        self.index = -1
        self._hole_from = QRectF()
        self._hole_to = QRectF()
        self._hole = QRectF()
        self._move = MotionTween(self, 1.0)
        self._move.updated.connect(lambda _value: self._interpolate_hole())

        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setGeometry(window.rect())

        self._card = QFrame(self)
        self._card.setFixedWidth(_CARD_W)
        self._card.setFrameShape(QFrame.Shape.StyledPanel)
        self._card.setAutoFillBackground(True)
        layout = QVBoxLayout(self._card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        head = QHBoxLayout()
        self._title = QLabel()
        font = QFont(self._title.font())
        font.setBold(True)
        self._title.setFont(font)
        head.addWidget(self._title, 1)
        self._exit = QToolButton()
        self._exit.setText("\u00d7")
        self._exit.setToolTip(tr("help_tour_exit"))
        self._exit.setAccessibleName(tr("help_tour_exit"))
        self._exit.clicked.connect(self.close_tour)
        head.addWidget(self._exit)
        layout.addLayout(head)

        self._caption = QLabel()
        self._caption.setWordWrap(True)
        layout.addWidget(self._caption)

        footer = QHBoxLayout()
        self._count = QLabel()
        footer.addWidget(self._count, 1)
        self._back = QPushButton(tr("help_tour_back"))
        self._back.clicked.connect(self.previous_step)
        footer.addWidget(self._back)
        self._next = QPushButton(tr("help_tour_next"))
        self._next.setDefault(True)
        self._next.clicked.connect(self.next_step)
        footer.addWidget(self._next)
        layout.addLayout(footer)

        window.installEventFilter(self)
        self.show()
        self.raise_()
        self.setFocus()
        self._advance(0, forward=True)

    # ── navigation ───────────────────────────────────────────────────────

    def _resolved(self, index):
        widget, rect, _compact = resolve_target(self.window_ref, self.steps[index].target)
        if widget is None or rect is None or rect.isEmpty():
            return None
        top_left = widget.mapTo(self.window_ref, rect.topLeft())
        return QRect(top_left, rect.size()).adjusted(-_PAD, -_PAD, _PAD, _PAD)

    def _advance(self, start, forward):
        """Show the first resolvable step from *start* in the given direction, else close."""
        index = start
        while 0 <= index < len(self.steps):
            target = self._resolved(index)
            if target is not None:
                self._show(index, target)
                return
            index += 1 if forward else -1
        if forward:
            self.close_tour()

    def _show(self, index, target):
        self.index = index
        step = self.steps[index]
        self._title.setText(_text(step.title))
        self._caption.setText(_text(step.caption))
        self._count.setText(f"{index + 1} / {len(self.steps)}")
        self._back.setEnabled(index > 0)
        self._next.setText(tr("help_tour_done") if index == len(self.steps) - 1 else tr("help_tour_next"))
        self._hole_from = QRectF(self._hole) if not self._hole.isEmpty() else QRectF(target)
        self._hole_to = QRectF(target)
        self._move.set_target(0.0, 0)
        self._move.set_target(1.0, _MOVE_MS, spatial=True)
        self._place_card()
        self._interpolate_hole()

    def _interpolate_hole(self):
        t = self._move.value
        a, b = self._hole_from, self._hole_to
        self._hole = QRectF(
            a.left() + (b.left() - a.left()) * t,
            a.top() + (b.top() - a.top()) * t,
            a.width() + (b.width() - a.width()) * t,
            a.height() + (b.height() - a.height()) * t,
        )
        self._place_card()
        self.update()

    def next_step(self):
        if self.index >= len(self.steps) - 1:
            self.close_tour()
            return
        self._advance(self.index + 1, forward=True)

    def previous_step(self):
        if self.index > 0:
            self._advance(self.index - 1, forward=False)

    def close_tour(self):
        if self.window_ref is not None:
            self.window_ref.removeEventFilter(self)
        self.finished.emit()
        self.close()
        self.deleteLater()

    # ── layout and painting ──────────────────────────────────────────────

    def _place_card(self):
        if self._hole.isEmpty():
            return
        self._card.adjustSize()
        bounds = (0, 0, self.width(), self.height())
        hole = (self._hole.left(), self._hole.top(), self._hole.width(), self._hole.height())
        x, y = place_bubble(hole, (self._card.width(), self._card.height()), bounds)
        self._card.move(int(x), int(y))

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        palette = self.palette()
        dark = palette.color(QPalette.ColorRole.Window).lightness() < 128
        dim = QColor(0, 0, 0, 170 if dark else 140)
        outer = QPainterPath()
        outer.addRect(QRectF(self.rect()))
        if not self._hole.isEmpty():
            hole = QPainterPath()
            hole.addRoundedRect(self._hole, _RADIUS, _RADIUS)
            outer = outer.subtracted(hole)
            painter.fillPath(outer, dim)
            painter.setPen(QPen(palette.color(QPalette.ColorRole.Highlight), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(self._hole, _RADIUS, _RADIUS)
        else:
            painter.fillPath(outer, dim)
        painter.end()

    def eventFilter(self, obj, event):
        if obj is self.window_ref and event.type() in (QEvent.Type.Resize, QEvent.Type.Move):
            self.setGeometry(self.window_ref.rect())
            if self.index >= 0:
                target = self._resolved(self.index)
                if target is not None:
                    self._hole_from = QRectF(self._hole)
                    self._hole_to = QRectF(target)
                    self._move.set_target(0.0, 0)
                    self._move.set_target(1.0, 0, spatial=True)
                    self._interpolate_hole()
        return super().eventFilter(obj, event)

    # ── input: the tour is read-only ─────────────────────────────────────

    def mousePressEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def wheelEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Right, Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.next_step()
        elif key == Qt.Key.Key_Left:
            self.previous_step()
        elif key == Qt.Key.Key_Escape:
            self.close_tour()
        else:
            event.ignore()
            return
        event.accept()
