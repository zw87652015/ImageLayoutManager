"""Stop panel scrolling from silently editing values.

Qt delivers a wheel event to whatever widget sits under the cursor, so
spin boxes and combo boxes change value while the user is only trying
to scroll the panel they live in. Worse, both default to
``Qt.WheelFocus``: the wheel event grabs focus *before* the widget sees
it, so a per-widget ``hasFocus()`` check can never catch the accident.

:class:`WheelGuard` therefore works application-wide per panel:

* Guarded widgets are switched to ``Qt.StrongFocus`` — only a click or
  Tab can focus them, never the wheel.
* A wheel over an unfocused value widget is forwarded to the enclosing
  scroll area's viewport, so the panel scrolls and the value stays put.
* A spin box that already has keyboard focus keeps its wheel stepping —
  the user clicked into it deliberately. Combo boxes never step: they
  retain focus after a pick, which would reintroduce the accident.
* A click anywhere outside the focused value widget (blank space, a
  section header, the canvas) drops that focus, so "click blank" means
  "nothing is focused" until another box is clicked.
"""

from PyQt6.QtCore import QCoreApplication, QEvent, QObject, Qt
from PyQt6.QtWidgets import (QApplication, QAbstractScrollArea,
                             QAbstractSpinBox, QComboBox, QWidget)

# Widget types whose value changes on wheel, and therefore need guarding.
GUARDED_TYPES = (QAbstractSpinBox, QComboBox)


class WheelGuard(QObject):
    """Application-wide filter guarding one panel's value widgets."""

    def __init__(self, scroll_area: QAbstractScrollArea, parent=None):
        super().__init__(parent)
        self._scroll_area = scroll_area

    # -- helpers ----------------------------------------------------------

    def _guarded_owner(self, widget):
        """Nearest guarded ancestor of *widget* inside this panel, or None."""
        while widget is not None and not isinstance(widget, GUARDED_TYPES):
            if widget.isWindow():
                return None  # popup (combo dropdown) or top-level: outside panel
            widget = widget.parentWidget()
        if widget is None or self._scroll_area is None:
            return None
        if widget is not self._scroll_area and not self._scroll_area.isAncestorOf(widget):
            return None
        return widget

    def _clear_stale_focus(self, press_target):
        """Drop focus from this panel's value widget when clicking outside it."""
        focus = QApplication.focusWidget()
        owner = self._guarded_owner(focus)
        if owner is None or owner is press_target or owner.isAncestorOf(press_target):
            return
        focus.clearFocus()

    # -- filter -------------------------------------------------------------

    def eventFilter(self, obj, event):
        try:
            return self._filter(obj, event)
        except RuntimeError:
            return False  # panel already destroyed, cleanup is pending

    def _filter(self, obj, event):
        if not isinstance(obj, QWidget):
            return False  # QWindow etc.: not part of any widget hierarchy
        etype = event.type()
        if etype == QEvent.Type.MouseButtonPress:
            self._clear_stale_focus(obj)
            return False
        if etype != QEvent.Type.Wheel:
            return False
        owner = self._guarded_owner(obj)
        if owner is None:
            return False
        # Focused spin box: the user aimed at this field, keep stepping.
        if isinstance(owner, QAbstractSpinBox) and owner.hasFocus():
            return False
        viewport = self._scroll_area.viewport()
        QCoreApplication.sendEvent(viewport, event)
        return True


def install_wheel_guard(root: QWidget,
                        scroll_area: QAbstractScrollArea) -> WheelGuard:
    """Guard every value widget under *root* against accidental wheel edits.

    Switches the panel's value widgets to ``Qt.StrongFocus`` (click/Tab
    only, never wheel) and registers one application-wide filter per
    *scroll_area*. Call again for widgets built later (dynamic rows) so
    they get the focus policy.
    """
    # One app-wide filter per scroll area. The guard is parented to the
    # application (never a dangling filter on a dead app) and dies with
    # the panel via destroyed->deleteLater (never a live filter for a
    # dead panel).
    guard = getattr(scroll_area, '_wheel_guard', None)
    if guard is None:
        app = QApplication.instance()
        guard = WheelGuard(scroll_area, parent=app)
        app.installEventFilter(guard)
        scroll_area.destroyed.connect(guard.deleteLater)
        scroll_area._wheel_guard = guard
    for widget_type in GUARDED_TYPES:
        for widget in root.findChildren(widget_type):
            widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    return guard
