"""Animated how-to demo for a User Guide topic card (QWidget).

Plays only while visible and in the 'standard' motion mode. Pause/resume is a
stop plus a restart from the remembered time, so every animation is started
through start_animation(). In reduced or off motion the final frame is painted
once with a caption.
"""

from PyQt6.QtCore import (QAbstractAnimation, QEasingCurve, QPointF, QRectF, Qt, QTimer,
                          QVariantAnimation, pyqtSignal)
from PyQt6.QtGui import QBrush, QColor, QFont, QGuiApplication, QImage, QPainter, QPalette, QPolygonF
from PyQt6.QtWidgets import QWidget

from src.app.help_content import TOPICS
from src.app.help_demo_paint import paint_frame
from src.app.help_demos import duration, frame_at
from src.app.i18n import current_language, tr
from src.app.motion import motion_policy, start_animation
from src.app.theme import DARK, LIGHT, get_tokens

_HOLD_MS = 1500
_FADE_MS = 250
_GLYPH_PX = 22.0
_MARGIN = 8.0


def _palette_colors(widget=None):
    window = QGuiApplication.palette().color(QPalette.ColorRole.Window)
    tokens = get_tokens(DARK if window.lightness() < 128 else LIGHT)
    colors = {"ink": tokens["text"], "muted": tokens["text_tert"], "accent": tokens["accent"],
              "on_accent": tokens["on_accent"], "base": tokens["surface"],
              "surface": tokens["surface_subtle"], "mid": tokens["border_strong"],
              "chrome": tokens["chrome"], "canvas": tokens["canvas_bg"]}
    return {name: QColor(value) for name, value in colors.items()}


def _topic_title(key):
    for topic in TOPICS:
        if topic.key == key:
            return topic.title[1] if current_language() == "zh" else topic.title[0]
    return key


class DemoView(QWidget):
    """Emits the current step while playing, and 0 when at rest (end hold or static)."""

    step_changed = pyqtSignal(int)

    def __init__(self, demo, parent=None):
        super().__init__(parent)
        self._demo = demo
        self._duration = duration(demo)
        self._t = 0
        self._anim = None
        self._user_paused = False
        self._hover = False
        self._last_step = None
        self._fade_anim = None
        self._fade_image = None
        self._fade_k = 0.0
        self._hold_timer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._restart_after_hold)
        self.setMouseTracking(True)
        self.setToolTip(tr("help_demo_tooltip"))
        self.setAccessibleName(tr("help_demo_name").format(title=_topic_title(demo.key)))
        policy = motion_policy()
        if policy is not None:
            policy.changed.connect(self._sync)

    # --- playback -----------------------------------------------------

    def _standard(self):
        policy = motion_policy()
        return policy is not None and policy.effective_mode == "standard"

    def _may_play(self):
        return self.isVisible() and self._standard() and not self._user_paused

    def _sync(self):
        if self._may_play():
            if self._t >= self._duration:
                self._t = 0
            if self._anim is None:
                self._play(self._t)
        else:
            self._stop()
            if not self._standard():
                self._t = self._duration
                self._emit_step(0)
        self.update()

    def _play(self, from_t):
        self._stop()
        if from_t >= self._duration:
            self._finish()
            return
        anim = QVariantAnimation(self)
        anim.setStartValue(int(from_t))
        anim.setEndValue(int(self._duration))
        anim.setEasingCurve(QEasingCurve.Type.Linear)
        anim.valueChanged.connect(lambda value, a=anim: self._on_value(a, value))
        anim.finished.connect(lambda a=anim: self._on_finished(a))
        self._anim = anim
        start_animation(anim, self._duration - from_t)

    def _stop(self):
        self._hold_timer.stop()
        anim, self._anim = self._anim, None
        if anim is not None and anim.state() != QAbstractAnimation.State.Stopped:
            anim.stop()
        fade, self._fade_anim = self._fade_anim, None
        if fade is not None and fade.state() != QAbstractAnimation.State.Stopped:
            fade.stop()
        self._fade_image = None
        self._fade_k = 0.0

    def _on_value(self, anim, value):
        if anim is not self._anim:
            return
        self._t = int(value)
        self._emit_step(frame_at(self._demo, self._t).step)
        self.update()

    def _on_finished(self, anim):
        if anim is not self._anim:
            return
        self._anim = None
        self._finish()

    def _finish(self):
        self._t = self._duration
        self._emit_step(0)
        self.update()
        self._hold_timer.start(_HOLD_MS)

    def _restart_after_hold(self):
        if not self._may_play():
            return
        self._t = 0
        self._fade_image = self._snapshot_final()
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.Linear)
        anim.valueChanged.connect(lambda value, a=anim: self._on_fade(a, value))
        anim.finished.connect(lambda a=anim: self._on_fade_finished(a))
        self._fade_anim = anim
        start_animation(anim, _FADE_MS)

    def _on_fade(self, anim, value):
        if anim is not self._fade_anim:
            return
        self._fade_k = float(value)
        self.update()

    def _on_fade_finished(self, anim):
        if anim is not self._fade_anim:
            return
        self._fade_anim = None
        self._fade_image = None
        self._fade_k = 0.0
        self._play(0)

    def _emit_step(self, step):
        if step != self._last_step:
            self._last_step = step
            self.step_changed.emit(int(step))

    # --- events -------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self._t = 0
        self._user_paused = False
        self._sync()

    def hideEvent(self, event):
        self._stop()
        super().hideEvent(event)

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton or not self._standard():
            super().mousePressEvent(event)
            return
        if self._user_paused:
            self._user_paused = False
            self._play(0 if self._t >= self._duration else self._t)
        else:
            self._user_paused = True
            self._stop()
        self.update()
        event.accept()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    # --- painting -----------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        colors = _palette_colors(self)
        static = not self._standard()
        self._paint_card(painter, colors, self._duration if static else self._t, static)
        if self._fade_image is not None:
            painter.setOpacity(1.0 - self._fade_k)
            painter.drawImage(QRectF(self.rect()), self._fade_image)
            painter.setOpacity(1.0)

        if static:
            self._paint_caption(painter, colors)
        elif self._hover:
            self._paint_glyph(painter, colors)
        painter.end()

    def _paint_card(self, painter, colors, t, static):
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(colors["surface"]))
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(0, 0, -1, -1), 10, 10)
        stage = QRectF(self.rect()).adjusted(_MARGIN, _MARGIN, -_MARGIN, -_MARGIN)
        if static:
            stage.setBottom(stage.bottom() - 18)
        paint_frame(painter, stage, frame_at(self._demo, t), colors, current_language())

    def _snapshot_final(self):
        ratio = self.devicePixelRatioF()
        image = QImage(int(self.width() * ratio), int(self.height() * ratio),
                       QImage.Format.Format_ARGB32_Premultiplied)
        image.setDevicePixelRatio(ratio)
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._paint_card(painter, _palette_colors(self), self._duration, False)
        painter.end()
        return image

    def _paint_caption(self, painter, colors):
        font = QFont(painter.font())
        font.setPixelSize(11)
        painter.setFont(font)
        painter.setPen(colors["muted"])
        rect = QRectF(_MARGIN, self.height() - _MARGIN - 14, self.width() - 2 * _MARGIN, 14)
        painter.drawText(rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                         tr("help_demo_motion_off"))

    def _paint_glyph(self, painter, colors):
        cx = self.width() - _MARGIN - _GLYPH_PX / 2
        cy = self.height() - _MARGIN - _GLYPH_PX / 2
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(colors["base"]))
        painter.drawEllipse(QRectF(cx - _GLYPH_PX / 2, cy - _GLYPH_PX / 2, _GLYPH_PX, _GLYPH_PX))
        painter.setBrush(QBrush(colors["ink"]))
        if self._may_play():
            painter.drawRect(QRectF(cx - 4, cy - 5, 2.5, 10))
            painter.drawRect(QRectF(cx + 1.5, cy - 5, 2.5, 10))
        else:
            painter.drawPolygon(QPolygonF([QPointF(cx - 3, cy - 5), QPointF(cx - 3, cy + 5),
                                           QPointF(cx + 5, cy)]))
