from PyQt6.QtCore import QEvent, QRect, QRectF, QSize, Qt, QTimer, pyqtSlot
from PyQt6.QtGui import QColor, QFont, QFontMetrics, QPalette, QPen
from PyQt6.QtWidgets import QApplication, QStyle, QStyledItemDelegate, QStyleOptionButton

from src.app.i18n import tr
from src.app.motion import MotionTween


REGION_DETAILS_ROLE = Qt.ItemDataRole.UserRole + 1


class RasterTextRegionDelegate(QStyledItemDelegate):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._feedback = {}
        self._groups = {}
        self._states = {}
        if parent is not None:
            parent.model().rowsRemoved.connect(self._schedule_prune)
            parent.model().modelReset.connect(self._schedule_prune)

    def _schedule_prune(self, *args):
        QTimer.singleShot(0, self._prune)

    def _prune(self):
        view = self.parent()
        if view is not None:
            model = view.model()
            self.set_regions({model.index(row, 0).data(Qt.ItemDataRole.UserRole):
                              (model.index(row, 0).data(REGION_DETAILS_ROLE) or {}).get('group')
                              for row in range(model.rowCount())})

    @pyqtSlot(float)
    def _feedback_updated(self, _value):
        if self.parent() is not None:
            self.parent().viewport().update()

    def set_regions(self, groups):
        for rid in self._feedback.keys() - groups.keys():
            self._states.pop(rid, None)
            for tween in self._feedback.pop(rid):
                tween.updated.disconnect(self._feedback_updated)
                tween.set_target(tween.value, ms=0)
                tween.deleteLater()
        for rid, group in groups.items():
            if rid not in self._feedback:
                self._states[rid] = (False, False)
                self._feedback[rid] = tuple(MotionTween(self, value=value)
                                            for value in (0, 0, bool(group), 0))
                for tween in self._feedback[rid]:
                    tween.updated.connect(self._feedback_updated)
            elif group != self._groups.get(rid):
                self._feedback[rid][2].set_target(float(bool(group)), ms=100)
                pulse = self._feedback[rid][3]
                pulse.set_target(1.0, ms=0)
                pulse.set_target(0.0, ms=100)
        self._groups = dict(groups)
        self._feedback_updated(0)

    def sizeHint(self, option, index):
        height = QFontMetrics(option.font).height()
        details = index.data(REGION_DETAILS_ROLE) or {}
        extra = bool(details.get('warning') or details.get('note'))
        return QSize(280, max(82, height * (3 + extra) + 30 + 4 * extra))

    def check_rect(self, option):
        style = option.widget.style() if option.widget else QApplication.style()
        width = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorWidth, None, option.widget)
        height = style.pixelMetric(QStyle.PixelMetric.PM_IndicatorHeight, None, option.widget)
        return QRect(option.rect.left() + (52 - width) // 2,
                     option.rect.center().y() - height, width, height)

    def paint(self, painter, option, index):
        details = index.data(REGION_DETAILS_ROLE)
        if not details:
            super().paint(painter, option, index)
            return
        painter.save()
        painter.setClipRect(option.rect)
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        rect = option.rect.adjusted(2, 2, -2, -2)
        palette = option.palette
        accent = palette.color(QPalette.ColorRole.Highlight)
        text = palette.color(QPalette.ColorRole.Text)
        subtle = QColor(text)
        subtle.setAlpha(180)
        selected = bool(option.state & QStyle.StateFlag.State_Selected)
        hovered = bool(option.state & QStyle.StateFlag.State_MouseOver)
        rid = index.data(Qt.ItemDataRole.UserRole)
        if rid not in self._feedback or details['group'] != self._groups.get(rid):
            self.set_regions({**self._groups, rid: details['group']})
        selection, hover, group, pulse = self._feedback[rid]
        previous = self._states[rid]
        self._states[rid] = (selected, hovered)
        for tween, old, new in zip((selection, hover), previous, self._states[rid]):
            if old != new:
                tween.set_target(float(new), ms=100)
        painter.fillRect(rect, palette.color(QPalette.ColorRole.Base))
        tint = QColor(accent)
        tint.setAlpha(round(28 * selection.value + 12 * hover.value * (1 - selection.value)))
        painter.fillRect(rect, tint)
        stripe = QColor(accent)
        stripe.setAlpha(round(255 * selection.value))
        painter.fillRect(QRect(rect.left(), rect.top() + 5, 3, rect.height() - 10), stripe)
        line = QColor(text)
        line.setAlpha(25)
        painter.setPen(line)
        painter.drawLine(rect.left() + 52, rect.top() + 8, rect.left() + 52, rect.bottom() - 8)
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())

        checked = index.data(Qt.ItemDataRole.CheckStateRole) == Qt.CheckState.Checked.value
        check = QStyleOptionButton()
        check.rect = self.check_rect(option)
        check.palette = palette
        check.state = QStyle.StateFlag.State_Enabled
        check.state |= QStyle.StateFlag.State_On if checked else QStyle.StateFlag.State_Off
        style = option.widget.style() if option.widget else QApplication.style()
        style.drawPrimitive(QStyle.PrimitiveElement.PE_IndicatorCheckBox, check, painter, option.widget)
        painter.setFont(option.font)
        metrics = QFontMetrics(option.font)
        painter.setPen(subtle)
        label_rect = QRect(rect.left() + 5, check.rect.bottom() + 4, 43, metrics.height())
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter,
                         tr('rastertxt_enabled_short' if checked else 'rastertxt_disabled_short'))

        left, right = rect.left() + 64, rect.right() - 10
        width = max(1, right - left)
        line_h = metrics.height()
        title_rect = QRect(left, rect.top() + 6, width, line_h + 2)
        bold = QFont(option.font)
        bold.setWeight(QFont.Weight.DemiBold)
        painter.setFont(bold)
        painter.setPen(text)
        title = QFontMetrics(bold).elidedText(details['text'], Qt.TextElideMode.ElideRight, width)
        painter.drawText(title_rect, Qt.AlignmentFlag.AlignVCenter, title)

        painter.setFont(option.font)
        badge_y = title_rect.bottom() + 5
        badge_text = tr('rastertxt_group_badge').format(name=details['group']) if details['group'] else tr('rastertxt_ungrouped')
        badge_w = min(metrics.horizontalAdvance(badge_text) + 16, max(40, int(width * 0.58)))
        badge = QRectF(left, badge_y, badge_w, line_h + 4)
        badge_color = QColor(*(round(a + (b - a) * group.value)
                               for a, b in zip(text.getRgb()[:3], accent.getRgb()[:3])))
        badge_color.setAlpha(round(12 + 10 * group.value + 12 * pulse.value
                                   + 6 * selection.value + 4 * hover.value))
        painter.setBrush(badge_color)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.drawRoundedRect(badge, 4, 4)
        painter.setPen(accent if details['group'] else subtle)
        painter.drawText(badge.adjusted(8, 0, -8, 0), Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(badge_text, Qt.TextElideMode.ElideRight, badge_w - 16))
        size_rect = QRect(left + badge_w + 10, badge_y, max(1, width - badge_w - 10), line_h + 4)
        painter.setPen(subtle)
        painter.drawText(size_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(details['size'], Qt.TextElideMode.ElideRight, size_rect.width()))

        status_rect = QRect(left, badge_y + line_h + 10, width, line_h)
        warning = details['severity'] == 'warning'
        if warning:
            warning_color = palette.color(QPalette.ColorRole.BrightText)
            tint = QColor(warning_color)
            tint.setAlpha(15)
            painter.fillRect(status_rect.adjusted(-3, -2, 3, 2), tint)
            icon_kind = QStyle.StandardPixmap.SP_MessageBoxWarning
        elif details['severity'] == 'applied':
            icon_kind = QStyle.StandardPixmap.SP_DialogApplyButton
        else:
            icon_kind = QStyle.StandardPixmap.SP_MessageBoxInformation
        side = min(16, line_h)
        style.standardIcon(icon_kind).paint(painter, QRect(left, status_rect.top(), side, side))
        painter.setPen(text if warning else subtle)
        status_rect.adjust(side + 6, 0, 0, 0)
        painter.drawText(status_rect, Qt.AlignmentFlag.AlignVCenter,
                         metrics.elidedText(details['status'], Qt.TextElideMode.ElideRight, status_rect.width()))
        if details['warning'] or details['note']:
            note = tr('rastertxt_review_status').format(reason=details['warning']) if details['warning'] else details['note']
            if details['warning'] and details['note']:
                note += ' — ' + details['note']
            note_rect = QRect(left, status_rect.bottom() + 5, width, line_h)
            tint = QColor(palette.color(QPalette.ColorRole.BrightText) if details['warning'] else accent)
            tint.setAlpha(15)
            painter.fillRect(note_rect.adjusted(-3, -2, 3, 2), tint)
            kind = QStyle.StandardPixmap.SP_MessageBoxWarning if details['warning'] else QStyle.StandardPixmap.SP_MessageBoxInformation
            style.standardIcon(kind).paint(painter, QRect(left, note_rect.top(), side, side))
            painter.setPen(text)
            note_rect.adjust(side + 6, 0, 0, 0)
            painter.drawText(note_rect, Qt.AlignmentFlag.AlignVCenter,
                             metrics.elidedText(note, Qt.TextElideMode.ElideRight, note_rect.width()))
        if option.state & QStyle.StateFlag.State_HasFocus:
            focus = QPen(accent, 1, Qt.PenStyle.DotLine)
            painter.setPen(focus)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(QRectF(rect).adjusted(1, 1, -1, -1), 4, 4)
        painter.restore()

    def editorEvent(self, event, model, option, index):
        if not index.flags() & Qt.ItemFlag.ItemIsUserCheckable or not index.flags() & Qt.ItemFlag.ItemIsEnabled:
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
