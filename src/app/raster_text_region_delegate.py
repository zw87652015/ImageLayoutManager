from PyQt6.QtCore import QEvent, QRect, QRectF, QSize, Qt
from PyQt6.QtGui import QColor, QFontMetrics, QPainter, QPainterPath, QPalette, QPen
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionButton


REGION_DETAILS_ROLE = Qt.ItemDataRole.UserRole + 1


class RasterTextRegionDelegate(QStyledItemDelegate):
    """Compact one-line row shared by the raster and SVG Match Text Size lists.

    ``index.data(REGION_DETAILS_ROLE)`` is a dict:
    ``text`` str · ``colour`` hex|None (filled dot; hollow Mid ring when None)
    · ``size`` str (right-aligned, subtle) · ``checkable``/``checked`` bool
    · ``muted`` bool (placeholder-colour text) · ``warning`` bool (triangle)
    · ``tooltip`` str (the window also puts it on the item's ToolTipRole).
    The checkbox itself is read from CheckStateRole so the list's existing
    itemChanged wiring keeps working.
    """

    DOT = 10

    def sizeHint(self, option, index):
        return QSize(220, max(26, QFontMetrics(option.font).height() + 10))

    def check_rect(self, option):
        style = option.widget.style() if option.widget else QApplication.style()
        width = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, option.widget)
        height = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight, None, option.widget)
        return QRect(option.rect.left() + 8,
                     option.rect.center().y() - height // 2, width, height)

    def paint(self, painter, option, index):
        details = index.data(REGION_DETAILS_ROLE)
        if not details:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 1, -2, -1)
        palette = option.palette
        accent = palette.color(QPalette.ColorRole.Highlight)
        text_colour = palette.color(QPalette.ColorRole.Text)
        subtle = QColor(text_colour)
        subtle.setAlpha(150)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        if selected:
            tint = QColor(accent)
            tint.setAlpha(40)
            painter.fillRect(rect, tint)
            painter.fillRect(QRect(rect.left(), rect.top() + 3, 3, rect.height() - 6), accent)
        elif hovered:
            tint = QColor(accent)
            tint.setAlpha(16)
            painter.fillRect(rect, tint)

        x = rect.left() + 8
        cy = rect.center().y()
        if details.get("checkable"):
            check = QStyleOptionButton()
            check.rect = self.check_rect(option)
            check.palette = palette
            check.state = QStyle.StateFlag.State_Enabled
            check.state |= (QStyle.StateFlag.State_On
                            if index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
                            else QStyle.StateFlag.State_Off)
            style = option.widget.style() if option.widget else QApplication.style()
            style.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox,
                                check, painter, option.widget)
            x = check.rect.right() + 8

        dot = QRectF(x, cy - self.DOT / 2, self.DOT, self.DOT)
        colour = details.get("colour")
        if colour:
            painter.setBrush(QColor(colour))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawEllipse(dot)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.setPen(QPen(palette.color(QPalette.ColorRole.Mid), 1.4))
            painter.drawEllipse(dot)
        x += self.DOT + 8

        metrics = QFontMetrics(option.font)
        painter.setFont(option.font)
        warn_w = 16 if details.get("warning") else 0
        size_text = details.get("size") or ""
        size_w = metrics.horizontalAdvance(size_text) + 8 if size_text else 0
        text_rect = QRect(x, rect.top(), max(0, rect.right() - 8 - warn_w - size_w - x),
                          rect.height())
        painter.setPen(palette.color(QPalette.ColorRole.PlaceholderText)
                       if details.get("muted") else text_colour)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(details.get("text") or "",
                                            Qt.TextElideMode.ElideRight, text_rect.width()))
        if size_text:
            size_rect = QRect(rect.right() - 8 - warn_w - size_w, rect.top(),
                              size_w, rect.height())
            painter.setPen(subtle)
            painter.drawText(size_rect,
                             Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                             size_text)
        if details.get("warning"):
            cx = rect.right() - 15
            path = QPainterPath()
            path.moveTo(cx + 7, cy - 6)
            path.lineTo(cx + 14, cy + 6)
            path.lineTo(cx, cy + 6)
            path.closeSubpath()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(palette.color(QPalette.ColorRole.BrightText))
            painter.drawPath(path)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        details = index.data(REGION_DETAILS_ROLE) or {}
        if (not details.get("checkable")
                or not index.flags() & Qt.ItemFlag.ItemIsUserCheckable
                or not index.flags() & Qt.ItemFlag.ItemIsEnabled):
            return False
        if event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.MouseButtonRelease,
                            QEvent.Type.MouseButtonDblClick):
            if event.button() != Qt.MouseButton.LeftButton or not self.check_rect(option).adjusted(-6, -6, 6, 6).contains(event.position().toPoint()):
                return False
            if event.type() != QEvent.Type.MouseButtonRelease:
                return True
        elif event.type() == QEvent.Type.KeyPress:
            if event.key() != Qt.Key.Key_Space or event.isAutoRepeat():
                return False
        else:
            return False
        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
        state = Qt.CheckState.Unchecked if checked else Qt.CheckState.Checked
        return model.setData(index, state, Qt.ItemDataRole.CheckStateRole)


# Shared name used by both Match Text Size windows.
TextMatchRowDelegate = RasterTextRegionDelegate
