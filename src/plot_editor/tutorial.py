"""Guided tutorials for the standalone Plot Editor.

A non-modal ``TutorialCard`` floats at the bottom-right of the editor
window; a ``TutorialHighlight`` ring marks the widget the current step
talks about. Steps, bodies, and readiness predicates are Qt-free and live
in ``tutorial_lessons.py`` — this module only resolves targets and runs
the guided actions.
"""

from PyQt6.QtCore import QEvent, QPoint, QRect, Qt, QTimer
from PyQt6.QtGui import QColor, QPainter, QPen
from PyQt6.QtWidgets import (QDialog, QDialogButtonBox, QHBoxLayout,
                             QLabel, QPushButton, QScrollArea,
                             QVBoxLayout, QWidget)

from src.app.theme import get_tokens

from . import chrome
from .i18n import tr
from .tutorial_lessons import (LESSONS, STYLING_Y_COUNT,
                               fill_sample_data, fill_styling_sample)


class TutorialHighlight(QWidget):
    """Accent ring drawn over the widget a step refers to.

    Hosted by the editor window so the ring can sit just outside a small
    control's own bounds; never intercepts mouse input.
    """

    GAP = 3

    def __init__(self, target, window):
        super().__init__(window)
        self.target = target
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setStyleSheet('background: transparent;')
        self._rect = QRect()
        self._tokens = get_tokens(chrome.saved_theme())
        target.installEventFilter(self)
        target.destroyed.connect(self.deleteLater)

    def set_target(self, target):
        if target is self.target:
            self._reposition()
            return
        if self.target is not None:
            self.target.removeEventFilter(self)
        self.target = target
        target.installEventFilter(self)
        target.destroyed.connect(self.deleteLater)
        self._reposition()
        self.raise_()

    def _reposition(self):
        if self.target is None:
            self.hide()
            return
        rect = self.target.rect()
        top_left = self.target.mapTo(self.parentWidget(),
                                     rect.topLeft())
        self._rect = QRect(top_left, rect.size()).adjusted(
            -self.GAP, -self.GAP, self.GAP, self.GAP)
        self.setGeometry(self._rect)
        self.show()
        self.raise_()

    def eventFilter(self, obj, event):
        if obj is self.target and event.type() in (
                QEvent.Type.Move, QEvent.Type.Resize):
            self._reposition()
        elif obj is self.target and event.type() == QEvent.Type.Hide:
            self.hide()
        return False

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        color = QColor(self._tokens['accent'])
        color.setAlpha(230)
        painter.setPen(QPen(color, 3))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QRect(self.rect()).adjusted(2, 2, -2, -2), 6, 6)


class TutorialCard(QDialog):
    """Non-modal lesson card: title, step text, status, navigation."""

    def __init__(self, controller):
        super().__init__(controller.window, Qt.WindowType.Tool)
        self.controller = controller
        self.setWindowTitle(tr('tut_title'))
        self.setMinimumWidth(360)
        self.resize(420, 300)

        tokens = chrome.style_tokens(controller.window._theme,
                                     controller.window._scale)
        self.setStyleSheet(
            "QDialog { background: %(surface)s; }"
            "QLabel#tutLesson { color: %(text_sec)s; font-size: %(font_sm)s; }"
            "QLabel#tutStep { color: %(text)s; font-size: %(font_md)s; "
            "  font-weight: 600; }"
            "QLabel#tutBody { color: %(text)s; font-size: %(font_md)s; }"
            "QLabel#tutStatus { color: %(text_sec)s; font-size: %(font_sm)s; }"
            % tokens)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        self.lesson_label = QLabel()
        self.lesson_label.setObjectName('tutLesson')
        layout.addWidget(self.lesson_label)
        self.heading = QLabel()
        self.heading.setObjectName('tutStep')
        self.heading.setWordWrap(True)
        layout.addWidget(self.heading)
        self.body = QLabel()
        self.body.setObjectName('tutBody')
        self.body.setWordWrap(True)
        self.body.setTextFormat(Qt.TextFormat.PlainText)
        self.body.setAlignment(Qt.AlignmentFlag.AlignTop
                               | Qt.AlignmentFlag.AlignLeft)
        self.body.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self.scroll.setMinimumHeight(120)
        self.scroll.setWidget(self.body)
        layout.addWidget(self.scroll, 1)
        self.status = QLabel()
        self.status.setObjectName('tutStatus')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.action = QPushButton()
        self.action.clicked.connect(controller.perform_action)
        self.action.setObjectName('tutAction')
        layout.addWidget(self.action)
        row = QHBoxLayout()
        self.back = QPushButton()
        self.skip = QPushButton()
        self.next = QPushButton()
        self.exit = QPushButton()
        for button in (self.back, self.skip, self.next, self.exit):
            button.setAutoDefault(False)
            row.addWidget(button)
        self.back.clicked.connect(controller.back)
        self.skip.clicked.connect(controller.skip)
        self.next.clicked.connect(controller.next)
        self.exit.clicked.connect(controller.stop)
        layout.addLayout(row)

    def closeEvent(self, event):
        self.controller.stop()
        event.accept()

    def reject(self):
        self.controller.stop()


class TutorialChooserDialog(QDialog):
    """Help → Tutorials… — pick a lesson."""

    def __init__(self, controller, parent=None):
        super().__init__(parent or controller.window)
        self.controller = controller
        self.setWindowTitle(tr('tut_title'))
        self.setMinimumWidth(360)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(8)
        intro = QLabel(tr('tut_chooser_intro'))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.lesson_buttons = {}
        for key, lesson in LESSONS.items():
            button = QPushButton(tr(lesson.title_key))
            button.setToolTip(tr(lesson.summary_key))
            button.setAutoDefault(False)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            summary = QLabel(tr(lesson.summary_key))
            summary.setWordWrap(True)
            summary.setIndent(12)
            layout.addWidget(button)
            layout.addWidget(summary)
            button.clicked.connect(
                lambda checked=False, k=key: self._pick(k))
            self.lesson_buttons[key] = button
        box = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        box.rejected.connect(self.reject)
        layout.addWidget(box)

    def _pick(self, key):
        self.accept()
        self.controller.start(key)


class TutorialController:
    """Drives one practice-tab lesson at a time inside *window*."""

    def __init__(self, window):
        self.window = window
        self.tab = None
        self.lesson = None
        self.index = 0
        self.ctx = {}
        self.highlight = None
        self.card = TutorialCard(self)
        self.timer = QTimer(window)
        self.timer.setInterval(250)
        self.timer.timeout.connect(self.refresh)
        window.tabs.currentChanged.connect(lambda _i: self.refresh())

    @property
    def steps(self):
        return LESSONS[self.lesson].steps

    @property
    def step(self):
        return self.steps[self.index]

    # ── lifecycle ───────────────────────────────────────────────────

    def show_chooser(self):
        TutorialChooserDialog(self, self.window).exec()

    def start(self, lesson_key):
        if lesson_key not in LESSONS:
            raise ValueError(lesson_key)
        self.stop()
        self.lesson = lesson_key
        lesson = LESSONS[lesson_key]
        tab = self.window._add_tab()
        tab.title = tr('tut_practice', name=tr(lesson.title_key))
        self.tab = tab
        self.index = 0
        self.ctx = {}
        if lesson.setup == 'plotted':
            fill_styling_sample(tab.worksheet)
            self._select_columns(1, STYLING_Y_COUNT)
            tab.plot_current('line_scatters')
        tab.changed.emit()
        self.window._sync_tab()
        self.card.show()
        self._reposition_card()
        self.timer.start()
        self.refresh()

    def _reposition_card(self):
        area = self.window.frameGeometry()
        self.card.move(area.right() - self.card.width() - 24,
                       area.bottom() - self.card.height() - 24)
        self.card.raise_()

    def stop(self):
        self.timer.stop()
        self._clear_highlight()
        self.card.hide()
        # The practice tab stays open under normal dirty/close rules.
        self.tab = None
        self.lesson = None

    # ── navigation ──────────────────────────────────────────────────

    def back(self):
        if self.tab and self.index:
            self.index -= 1
            self.refresh()

    def skip(self):
        if self.tab and self.index < len(self.steps) - 1:
            self.index += 1
            self.refresh()

    def next(self):
        if not self.tab or not self.ready():
            return
        if self.index == len(self.steps) - 1:
            self.stop()
        else:
            self.index += 1
            self.refresh()

    # ── readiness ───────────────────────────────────────────────────

    def _practice_active(self):
        return (self.tab is not None
                and self.window.tabs.indexOf(self.tab) >= 0
                and self.window.current_tab() is self.tab)

    def ready(self):
        if not self._practice_active():
            return False
        predicate = self.step.ready
        return predicate(self.tab, self.ctx) if predicate else True

    def on_saved(self, tab):
        """Event hook from ``window._save_to`` after a *successful* save:
        the first_plot 'save' step completes itself. Failed or cancelled
        saves never reach this; next() still re-checks readiness."""
        if tab is not self.tab or not self._practice_active():
            return
        if self.lesson == 'first_plot' and self.step.key == 'save':
            self.next()

    # ── guided actions ───────────────────────────────────────────────

    def _select_columns(self, first, last):
        view = self.tab.worksheet_view
        model = view.model()
        from PyQt6.QtCore import QItemSelection
        from PyQt6.QtCore import QItemSelectionModel
        sel = QItemSelection(model.index(0, first),
                             model.index(model.rowCount() - 1, last))
        view.selectionModel().select(
            sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def perform_action(self):
        if not self._practice_active():
            return
        action = self.step.action
        if action == 'fill_sample':
            fill_sample_data(self.tab.worksheet)
        elif action == 'plot_sample':
            self._select_columns(1, 2)
            try:
                self.tab.plot_current('line_scatters')
            except Exception:
                pass
        self.refresh()

    # ── target resolution ────────────────────────────────────────────

    def _target_widget(self, target):
        tab, window = self.tab, self.window
        if target == 'worksheet':
            return tab.worksheet_view, tab.worksheet_view.rect()
        if target == 'worksheet_header':
            header = tab.worksheet_view.horizontalHeader()
            return header, header.rect()
        if target == 'plot_button':
            return window._plot_button, window._plot_button.rect()
        if target == 'canvas':
            return tab.plot_canvas, tab.plot_canvas.rect()
        if target == 'title_field':
            return tab.title_field, tab.title_field.rect()
        if target == 'style_presets':
            return tab.style_presets, tab.style_presets.rect()
        if target == 'reset_all':
            return tab.reset_all, tab.reset_all.rect()
        if target.startswith('action_'):
            action = window.editor_actions.get(target[len('action_'):])
            if action is None:
                return None, None
            # Toolbar button wins when one exists, else the menubar entry.
            return self._action_target(action)
        return None, None

    def _action_target(self, action):
        from PyQt6.QtWidgets import QMenu, QToolBar
        for tb in self.window.findChildren(QToolBar):
            widget = tb.widgetForAction(action)
            if widget is not None and widget.isVisible():
                return widget, widget.rect()
        bar = self.window.menuBar()
        for entry in bar.actions():
            menu = entry.menu()
            if menu is not None and self._menu_holds(menu, action):
                rect = bar.actionGeometry(entry)
                if not rect.isEmpty():
                    return bar, rect
        return None, None

    @staticmethod
    def _menu_holds(menu, action):
        from PyQt6.QtWidgets import QMenu
        for candidate in menu.actions():
            if candidate is action:
                return True
            sub = candidate.menu()
            if sub is not None and TutorialController._menu_holds(sub, action):
                return True
        return False

    # ── refresh ─────────────────────────────────────────────────────

    def _clear_highlight(self):
        if self.highlight is not None:
            self.highlight.hide()
            self.highlight.deleteLater()
            self.highlight = None

    def refresh(self):
        if self.tab is None or self.lesson is None:
            return
        if self.window.tabs.indexOf(self.tab) < 0:
            # Practice tab was closed — end the lesson, leave others be.
            self.stop()
            return
        active = self._practice_active()
        lesson = LESSONS[self.lesson]
        card = self.card
        card.setWindowTitle(tr('tut_title'))
        card.lesson_label.setText(
            tr(lesson.title_key) + ' — '
            + tr('tut_step_fmt', n=self.index + 1, m=len(self.steps)))
        card.heading.setText(tr(self.step.title_key))
        body = tr(self.step.body_key)
        if card.body.text() != body:
            card.body.setText(body)
            card.scroll.verticalScrollBar().setValue(0)
        ready = active and self.ready()
        card.status.setText(
            tr('tut_status_paused') if not active else
            tr('tut_status_ready') if ready and self.step.ready else
            tr('tut_status_info') if ready else tr('tut_status_wait'))
        card.back.setText(tr('tut_back'))
        card.skip.setText(tr('tut_skip'))
        card.next.setText(tr('tut_finish')
                          if self.index == len(self.steps) - 1
                          else tr('tut_next'))
        card.exit.setText(tr('tut_exit'))
        card.back.setEnabled(active and self.index > 0)
        card.skip.setEnabled(active
                             and self.index < len(self.steps) - 1)
        card.next.setEnabled(ready)
        card.action.setVisible(bool(self.step.action) and active)
        if self.step.action:
            card.action.setText(tr('tut_act_' + self.step.action))

        if active and self.step.target:
            widget, rect = self._target_widget(self.step.target)
            if widget is not None and widget.isVisible():
                if self.highlight is None:
                    self.highlight = TutorialHighlight(
                        widget, self.window)
                else:
                    self.highlight.set_target(widget)
                return
        self._clear_highlight()
