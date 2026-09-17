import ctypes
import sys
import time
import weakref

from PyQt6.QtCore import (
    QAbstractAnimation, QCoreApplication, QEasingCurve, QObject, QSettings,
    QTimer, Qt, QVariantAnimation, pyqtSignal,
)


MODES = ('standard', 'reduced', 'off')


def system_reduced_motion():
    if sys.platform == 'win32':
        enabled = ctypes.c_int(1)
        try:
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
                return not bool(enabled.value)
        except (AttributeError, OSError):
            pass
    return False


class MotionPolicy(QObject):
    changed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        settings = QSettings('AcademicFigureLayout', 'ImageLayoutManager')
        mode = settings.value('ui/motion_mode', 'standard')
        self.mode = mode if mode in MODES else 'standard'
        self.system_reduced = system_reduced_motion()
        self._animations = weakref.WeakSet()

    @property
    def effective_mode(self):
        return 'reduced' if self.mode == 'standard' and self.system_reduced else self.mode

    def set_mode(self, mode):
        mode = mode if mode in MODES else 'standard'
        system_reduced = system_reduced_motion()
        if self.mode == mode and self.system_reduced == system_reduced:
            return
        self.mode = mode
        self.system_reduced = system_reduced
        for animation in list(self._animations):
            try:
                if animation.state() != QAbstractAnimation.State.Stopped and animation.totalDuration() >= 0:
                    animation.setCurrentTime(animation.totalDuration())
            except RuntimeError:
                self._animations.discard(animation)
        self.changed.emit()

    def duration(self, milliseconds, spatial=False):
        mode = self.effective_mode
        if mode == 'off' or mode == 'reduced' and spatial:
            return 0
        return min(int(milliseconds), 70) if mode == 'reduced' else max(0, int(milliseconds))


def motion_policy():
    app = QCoreApplication.instance()
    if app is None:
        return None
    policy = getattr(app, '_ilm_motion_policy', None)
    if policy is None:
        policy = MotionPolicy(app)
        app._ilm_motion_policy = policy
    return policy


def set_motion_mode(mode):
    policy = motion_policy()
    if policy is not None:
        policy.set_mode(mode)


def motion_duration(milliseconds, spatial=False):
    policy = motion_policy()
    return policy.duration(milliseconds, spatial) if policy is not None else 0


def screen_refresh_rate() -> float:
    """Refresh rate (Hz) of the screen showing the app's window."""
    from PyQt6.QtGui import QGuiApplication
    try:
        window = QGuiApplication.focusWindow()
    except RuntimeError:
        window = None
    if window is None:
        for candidate in QGuiApplication.topLevelWindows():
            try:
                if candidate.isVisible():
                    window = candidate
                    break
            except RuntimeError:
                continue
    screen = None
    if window is not None:
        try:
            screen = window.screen()
        except RuntimeError:
            screen = None
    if screen is None:
        screen = QGuiApplication.primaryScreen()
    rate = screen.refreshRate() if screen is not None else 60.0
    if rate <= 0:
        rate = 60.0
    return max(30.0, min(250.0, rate))


class FrameClock(QObject):
    """Steps Paused animations at the display's refresh rate.

    Qt's unified timer ticks Running animations at a fixed 16 ms. A Paused
    animation is detached from it, yet setCurrentTime() still updates values
    and finishes normally — so a precise QTimer can drive playback at the
    real refresh rate. The timer idles at zero when nothing is driven.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)
        self._entries = []            # [animation, start perf_counter]
        self._interval_ms = 16
        self._refresh_rate = 60.0
        self._last_tick = 0.0
        self._slow_ticks = 0

    @property
    def interval_ms(self) -> int:
        return self._interval_ms

    @property
    def refresh_rate(self) -> float:
        return self._refresh_rate

    def is_active(self) -> bool:
        return self._timer.isActive()

    def _start_clock(self) -> None:
        self._refresh_rate = screen_refresh_rate()
        self._interval_ms = max(4, min(33, int(1000 // self._refresh_rate)))
        self._slow_ticks = 0
        self._last_tick = 0.0
        self._timer.setInterval(self._interval_ms)
        self._timer.start()

    def _drop_animation(self, animation) -> None:
        for entry in list(self._entries):
            if entry[0] is animation:
                self._drop(entry)

    def _drop(self, entry) -> None:
        if entry in self._entries:
            self._entries.remove(entry)
            try:
                entry[0].stateChanged.disconnect(entry[2])
            except (TypeError, RuntimeError):
                pass
        if not self._entries:
            self._timer.stop()

    def drive(self, animation) -> None:
        for entry in self._entries:
            if entry[0] is animation:
                entry[1] = time.perf_counter()
                return
        connection = animation.stateChanged.connect(
            lambda new, _old, a=animation: (
                self._drop_animation(a)
                if new == QAbstractAnimation.State.Stopped else None))
        self._entries.append([animation, time.perf_counter(), connection])
        if not self._timer.isActive():
            self._start_clock()

    def release(self, animation) -> None:
        for entry in list(self._entries):
            if entry[0] is animation:
                self._drop(entry)

    def _tick(self) -> None:
        tick_start = time.perf_counter()
        if self._last_tick and tick_start - self._last_tick < self._interval_ms / 2000.0:
            return
        self._last_tick = tick_start
        for entry in list(self._entries):
            animation, start, _connection = entry
            try:
                state = animation.state()
            except RuntimeError:
                self._drop(entry)
                continue
            if state != QAbstractAnimation.State.Paused:
                self._drop(entry)
                continue
            total = animation.totalDuration()
            animation.setCurrentTime(min(int((tick_start - start) * 1000), total))
        if not self._entries:
            self._timer.stop()
        cost = time.perf_counter() - tick_start
        if cost > self._interval_ms / 1000.0:
            self._slow_ticks += 1
            if self._slow_ticks >= 3:
                self._interval_ms = min(16, self._interval_ms * 2)
                self._timer.setInterval(self._interval_ms)
                self._slow_ticks = 0
        else:
            self._slow_ticks = 0


def frame_clock() -> FrameClock:
    app = QCoreApplication.instance()
    if app is None:
        return None
    clock = getattr(app, '_ilm_frame_clock', None)
    if clock is None:
        clock = FrameClock(app)
        app._ilm_frame_clock = clock
    return clock


def hold_animation(animation) -> None:
    """Stop driving *animation* but keep it Paused so setCurrentTime() can
    step it deterministically."""
    clock = frame_clock()
    if clock is not None:
        clock.release(animation)


def start_animation(animation, milliseconds, spatial=False):
    policy = motion_policy()
    animation.setDuration(motion_duration(milliseconds, spatial))
    if policy is not None:
        policy._animations.add(animation)
    animation.start()
    if animation.state() == QAbstractAnimation.State.Running:
        animation.pause()
        clock = frame_clock()
        if clock is not None:
            clock.drive(animation)
    return animation


class MotionTween(QObject):
    updated = pyqtSignal(float)
    finished = pyqtSignal()

    def __init__(self, parent=None, value=0.0):
        super().__init__(parent)
        self.value = float(value)
        self._target = self.value
        self._animation = QVariantAnimation(self)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_value)
        self._animation.finished.connect(self.finished)

    def _set_value(self, value):
        self.value = float(value)
        self.updated.emit(self.value)

    def set_target(self, target, ms=100, spatial=False):
        target = float(target)
        if target == self._target and ms > 0 and self._animation.state() != QAbstractAnimation.State.Stopped:
            return
        self._target = target
        self._animation.stop()
        if self.value == target or motion_duration(ms, spatial) == 0:
            self._set_value(target)
            self.finished.emit()
            return
        self._animation.setStartValue(self.value)
        self._animation.setEndValue(target)
        start_animation(self._animation, ms, spatial)

    def stop(self):
        self._animation.stop()


def install_button_feedback(root):
    from PyQt6.QtCore import QEvent, QRectF, Qt
    from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
    from PyQt6.QtWidgets import QPushButton, QToolButton, QWidget

    class ButtonFeedback(QWidget):
        def __init__(self, button):
            super().__init__(button)
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setStyleSheet('background: transparent; border: none;')
            self._button = button
            self._hovered = False
            self._strength = MotionTween(self)
            self._strength.updated.connect(lambda _value: self.update())
            self.setGeometry(button.rect())
            button.installEventFilter(self)
            self.show()

        def eventFilter(self, obj, event):
            kind = event.type()
            if kind == QEvent.Type.Resize:
                self.setGeometry(obj.rect())
            elif kind == QEvent.Type.Enter:
                self._hovered = True
                self._strength.set_target(1.0 if obj.isEnabled() else 0.0, 110)
            elif kind == QEvent.Type.Leave:
                self._hovered = False
                self._strength.set_target(0.0, 90)
            elif kind == QEvent.Type.MouseButtonPress:
                self._strength.set_target(0.45, 0)
            elif kind == QEvent.Type.MouseButtonRelease:
                self._strength.set_target(1.0 if self._hovered else 0.0, 90)
            elif kind == QEvent.Type.EnabledChange and not obj.isEnabled():
                self._strength.set_target(0.0, 0)
            return False

        def paintEvent(self, event):
            if self._strength.value <= 0 or not self._button.isEnabled():
                return
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            accent = self.palette().color(QPalette.ColorRole.Highlight)
            border = QColor(accent)
            border.setAlpha(round(100 * self._strength.value))
            fill = QColor(accent)
            fill.setAlpha(round(10 * self._strength.value))
            painter.setPen(QPen(border, 1))
            painter.setBrush(fill)
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 4, 4)
            painter.end()

    for kind in (QPushButton, QToolButton):
        for button in root.findChildren(kind):
            if not hasattr(button, '_motion_feedback'):
                button._motion_feedback = ButtonFeedback(button)


def show_layout_transition(view, before, after):
    from PyQt6.QtCore import QEvent, QRectF, Qt
    from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
    from PyQt6.QtWidgets import QWidget

    previous = getattr(view, '_layout_motion_overlay', None)
    if previous is not None:
        previous.cancel()
    changed = [key for key in before.keys() | after.keys() if before.get(key) != after.get(key)]
    if not changed or motion_duration(180, spatial=True) == 0:
        return

    class LayoutFeedback(QWidget):
        def __init__(self):
            super().__init__(view.viewport())
            self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
            self.setStyleSheet('background: transparent; border: none;')
            self._view = view
            self._frames = [(before.get(key, after.get(key)), after.get(key, before.get(key)))
                            for key in changed[:80]]
            self._progress = MotionTween(self)
            self._progress.updated.connect(lambda _value: self.update())
            self._progress.finished.connect(self.cancel)
            self.setGeometry(view.viewport().rect())
            view.viewport().installEventFilter(self)
            view.installEventFilter(self)
            self.show()
            self.raise_()

        def cancel(self):
            self._progress.stop()
            self.hide()
            if getattr(self._view, '_layout_motion_overlay', None) is self:
                self._view._layout_motion_overlay = None
            self.deleteLater()

        def eventFilter(self, obj, event):
            if event.type() == QEvent.Type.Resize:
                self.setGeometry(self._view.viewport().rect())
            elif event.type() in (QEvent.Type.MouseButtonPress, QEvent.Type.Wheel, QEvent.Type.KeyPress):
                self.cancel()
            return False

        def paintEvent(self, event):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            t = self._progress.value
            color = QColor(self.palette().color(QPalette.ColorRole.Highlight))
            color.setAlpha(round(130 * (1 - t)))
            painter.setPen(QPen(color, 1.25))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            transform = self._view.viewportTransform()
            for start, end in self._frames:
                rect = QRectF(*(a + (b - a) * t for a, b in zip(start, end)))
                painter.drawRoundedRect(transform.mapRect(rect), 3, 3)
            painter.end()

    overlay = LayoutFeedback()
    view._layout_motion_overlay = overlay
    overlay._progress.set_target(1.0, 180, spatial=True)
