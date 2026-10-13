"""Find on-screen controls by spec, shared by the tutorials and the User Guide's "Show me".

Specs are tuples:
  ("action", "<MainWindow QAction attribute>")   -> the visible button, menu row or menu bar entry
  ("widget", "<alias>")                           -> one of WIDGET_ALIASES
  ("section", "<Inspector CollapsibleSection attribute>") -> expanded, scrolled into view
  ("menu", "<menu alias>")                        -> an entry of the menu bar
"""

from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, QRect, QTimer
from PyQt6.QtWidgets import QMenu, QToolButton, QToolTip

WIDGET_ALIASES = ("layers", "inspector", "canvas", "toolbar", "statusbar_zoom")
MENU_ALIASES = ("help",)
_PULSE_STEPS = (0.35, 1.0, 0.35, 1.0, 0.35, 1.0)
_PULSE_MS = 400
_FADE_MS = 240


def menu_holds(menu, action):
    for candidate in menu.actions():
        if candidate is action:
            return True
        sub = candidate.menu()
        if sub is not None and menu_holds(sub, action):
            return True
    return False


def action_target(window, action):
    """Find the visible control for *action*.

    Not every action has a toolbar button: some live only inside a popup (Export
    Preview sits in the Export button's menu) or a menu bar. Point at whatever the
    user must actually click, and follow the action into its popup once that popup
    is open, so the step never degrades into "use the keyboard shortcut".
    """
    if action is None:
        return None, None, False
    for menu in window.findChildren(QMenu):
        if menu.isVisible() and action in menu.actions():
            rect = menu.actionGeometry(action)
            if not rect.isEmpty():
                return menu, rect, True
    widget = window.toolbar.widgetForAction(action)
    if widget is not None and widget.isVisible():
        return widget, widget.rect(), True
    for button in window.toolbar.findChildren(QToolButton):
        menu = button.menu()
        if button.isVisible() and menu is not None and menu_holds(menu, action):
            return button, button.rect(), True
    return None, None, False


def _widget_for_alias(window, alias):
    if alias == "layers":
        return window.layers_panel
    if alias == "inspector":
        return window.inspector
    if alias == "canvas":
        return window.view.viewport() if window.view is not None else None
    if alias == "toolbar":
        return window.toolbar
    if alias == "statusbar_zoom":
        return window.zoom_label.parentWidget()
    return None


def _menu_for_alias(window, alias):
    if alias == "help":
        return window._help_menu
    return None


def _expand_section(window, section):
    """Show an Inspector section, clearing the canvas selection first for Project settings."""
    inspector = window.inspector
    if section is inspector.project_group and not section.isVisible():
        scene = getattr(window, "scene", None)
        if scene is not None:
            scene.clearSelection()
    if section._collapsed:
        section.set_collapsed(False, animate=False)
    QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
    if not section.isVisible():
        return None, None, False
    scroll = inspector._scroll
    for _ in range(4):
        QCoreApplication.sendPostedEvents(None, QEvent.Type.LayoutRequest)
        if section.height() > 0:
            break
    scroll.ensureWidgetVisible(section, 0, 24)
    return section, section.rect(), False


def resolve_target(window, spec):
    """(widget, rect, compact) for *spec*, or (None, None, False) when it cannot be found."""
    if not spec:
        return None, None, False
    kind, value = spec
    if kind == "action":
        return action_target(window, getattr(window, value, None))
    if kind == "widget":
        widget = _widget_for_alias(window, value)
        if widget is None or not widget.isVisible():
            return None, None, False
        return widget, widget.rect(), False
    if kind == "section":
        section = getattr(window.inspector, value, None)
        if section is None:
            return None, None, False
        widget, rect, compact = _expand_section(window, section)
        if widget is not None:
            return widget, rect, compact
        return resolve_target(window, ("widget", "inspector"))
    if kind == "menu":
        menu = _menu_for_alias(window, value)
        if menu is None:
            return None, None, False
        bar = window.menuBar()
        rect = bar.actionGeometry(menu.menuAction())
        if rect.isEmpty():
            return None, None, False
        return bar, rect, True
    return None, None, False


def flash_target(window, spec, caption):
    """Pulse the control named by *spec* and show *caption* beside it.

    Unresolvable targets show *caption* in the status bar for four seconds.
    """
    widget, rect, compact = resolve_target(window, spec)
    if widget is None:
        window.statusBar().showMessage(caption, 4000)
        return None
    from src.app.tutorials import TutorialHighlight

    highlight = TutorialHighlight(widget, compact)
    highlight.set_target_rect(QRect(rect))
    QToolTip.showText(widget.mapToGlobal(QPoint(rect.center().x(), rect.top())), caption, widget)

    def pulse(index):
        if index < len(_PULSE_STEPS):
            highlight.strength.set_target(_PULSE_STEPS[index], _PULSE_MS)
            QTimer.singleShot(_PULSE_MS, lambda: pulse(index + 1))
        else:
            highlight.strength.set_target(0.0, _FADE_MS)
            QTimer.singleShot(_FADE_MS + 20, highlight.deleteLater)

    pulse(0)
    return highlight
