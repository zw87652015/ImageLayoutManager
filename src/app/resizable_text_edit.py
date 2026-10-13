from PyQt6.QtCore import QSettings, QSize, Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QPalette, QPen
from PyQt6.QtWidgets import QLineEdit, QPlainTextEdit, QSizePolicy, QWidget

_DEFAULT_LINES = 4
_MIN_LINES = 2
_MAX_LINES = 30
_GRIP_SIZE = 12


class _Grip(QWidget):
    """Bottom-right corner handle that drags the owner's height."""

    def __init__(self, owner: "ResizableTextEdit"):
        super().__init__(owner)
        self._owner = owner
        self._press_y: float | None = None
        self._start_height = 0
        self.setFixedSize(_GRIP_SIZE, _GRIP_SIZE)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(QPen(self.palette().color(QPalette.ColorRole.PlaceholderText)))
        size = self.width()
        for offset in (3, 6, 9):
            painter.drawLine(size - offset, size - 1, size - 1, size - offset)
        painter.end()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_y = event.globalPosition().y()
            self._start_height = self._owner.height()
            event.accept()

    def mouseMoveEvent(self, event):
        if self._press_y is not None:
            delta = event.globalPosition().y() - self._press_y
            self._owner.set_height_px(self._start_height + round(delta))
            event.accept()

    def mouseReleaseEvent(self, event):
        if self._press_y is not None and event.button() == Qt.MouseButton.LeftButton:
            self._press_y = None
            self._owner.persist_height()
            event.accept()


class ResizableTextEdit(QPlainTextEdit):
    """Multi-line text field with a corner grip to change its height.

    Enter inserts a newline; Ctrl+Enter commits and leaves the field; Esc
    reverts to the committed text; focus-out commits.
    """

    committed = pyqtSignal(str)

    def __init__(self, settings_key: str | None = None, parent=None):
        super().__init__(parent)
        self._settings_key = settings_key
        self._baseline = ""
        self._probe: QLineEdit | None = None
        self.setTabChangesFocus(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self._grip = _Grip(self)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self._initial_height())

    def _line_edit_probe(self) -> QLineEdit:
        if self._probe is None:
            self._probe = QLineEdit()
            self._probe.hide()
        self._probe.setFont(self.font())
        return self._probe

    def sizeHint(self) -> QSize:
        return QSize(self._line_edit_probe().sizeHint().width(), self.height())

    def minimumSizeHint(self) -> QSize:
        return QSize(self._line_edit_probe().minimumSizeHint().width(), self.height())

    def _lines_px(self, lines: int) -> int:
        return self.fontMetrics().lineSpacing() * lines + 2 * self.frameWidth() + 6

    def _clamp_px(self, px: int) -> int:
        return min(max(px, self._lines_px(_MIN_LINES)), self._lines_px(_MAX_LINES))

    def _initial_height(self) -> int:
        default = self._lines_px(_DEFAULT_LINES)
        if not self._settings_key:
            return default
        settings = QSettings("AcademicFigureLayout", "ImageLayoutManager")
        return self._clamp_px(settings.value(self._settings_key, default, type=int))

    def set_height_px(self, px: int):
        self.setFixedHeight(self._clamp_px(px))

    def persist_height(self):
        if self._settings_key:
            settings = QSettings("AcademicFigureLayout", "ImageLayoutManager")
            settings.setValue(self._settings_key, self.height())

    def set_committed_text(self, text: str):
        self.setPlainText(text)
        self._baseline = text

    def _commit(self):
        text = self.toPlainText()
        if text != self._baseline:
            self._baseline = text
            self.committed.emit(text)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        inset = self.frameWidth()
        self._grip.move(self.width() - inset - _GRIP_SIZE,
                        self.height() - inset - _GRIP_SIZE)
        self._grip.raise_()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) \
                and event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self._commit()
            self.clearFocus()
            return
        if event.key() == Qt.Key.Key_Escape:
            self.setPlainText(self._baseline)
            self.clearFocus()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        self._commit()
        super().focusOutEvent(event)
