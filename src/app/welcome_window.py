"""Startup welcome window.

A small standalone launcher window shown INSTEAD of the main window at
launch: New Project / Open Project / Close, underlined recent-project
links, and an About button in the corner. Picking anything calls
``MainWindow._dismiss_welcome()``, which closes this window and reveals
the main window. Closing this window while the main window is still
hidden (title-bar X or the Close button) quits the app.
"""

import html
import os

from PyQt6.QtCore import Qt, QRectF
from PyQt6.QtGui import QColor, QPainter, QPalette, QPen
from PyQt6.QtWidgets import (
    QApplication, QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout,
    QWidget,
)

from src.app.i18n import tr
from src.app.motion import MotionTween, install_button_feedback

_MAX_RECENTS = 6


class WelcomeWindow(QWidget):
    def __init__(self, main_window):
        super().__init__(None)  # no parent: an independent top-level window
        self._mw = main_window
        self._drop_feedback = MotionTween(self)
        self._drop_feedback.updated.connect(lambda _value: self.update())
        self.setAcceptDrops(True)
        self.setObjectName("welcomePage")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowTitle(tr("about_app_name"))
        self.setWindowIcon(main_window.windowIcon())
        self.setWindowFlags(
            Qt.WindowType.Window
            | Qt.WindowType.WindowCloseButtonHint
            | Qt.WindowType.MSWindowsFixedSizeDialogHint
        )
        self.setFixedSize(480, 520)
        self._build_ui()
        install_button_feedback(self)
        # Centre on the primary screen
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(screen.center() - self.rect().center())

    # ------------------------------------------------------------------
    # UI
    # ------------------------------------------------------------------

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(24, 14, 24, 18)
        root.setSpacing(0)

        # Corner: About button, top-right
        corner = QHBoxLayout()
        corner.addStretch(1)
        self._btn_about = QPushButton(tr("welcome_about"))
        self._btn_about.setObjectName("welcomeCorner")
        self._btn_about.setFlat(True)
        self._btn_about.setCursor(Qt.CursorShape.PointingHandCursor)
        self._btn_about.clicked.connect(self._mw._on_show_about)
        corner.addWidget(self._btn_about)
        root.addLayout(corner)

        root.addStretch(3)

        self._title = QLabel(tr("about_app_name"))
        self._title.setObjectName("welcomeTitle")
        self._title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(self._title)
        self._drop_hint = QLabel(tr("welcome_drop_project"))
        self._drop_hint.setObjectName("welcomeDropHint")
        self._drop_hint.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._drop_hint.setWordWrap(True)
        root.addWidget(self._drop_hint)
        root.addSpacing(18)

        # Action buttons, centred fixed-width column
        btn_col = QVBoxLayout()
        btn_col.setSpacing(6)

        self._btn_new = QPushButton(tr("welcome_new"))
        self._btn_new.setObjectName("welcomePrimary")
        self._btn_new.clicked.connect(self._mw._dismiss_welcome)
        btn_col.addWidget(self._btn_new)

        self._btn_open = QPushButton(tr("welcome_open_project"))
        self._btn_open.clicked.connect(self._mw._on_open_project)
        btn_col.addWidget(self._btn_open)

        self._btn_learn = QPushButton(tr('tutorials_welcome'))
        self._btn_learn.setFlat(True)
        self._btn_learn.clicked.connect(self._mw._on_show_tutorials)
        btn_col.addWidget(self._btn_learn)

        self._btn_close = QPushButton(tr("welcome_close"))
        self._btn_close.setObjectName("welcomeGhost")
        self._btn_close.setFlat(True)
        self._btn_close.clicked.connect(self.close)
        btn_col.addWidget(self._btn_close)

        for button in (self._btn_new, self._btn_open, self._btn_close):
            button.setAttribute(Qt.WidgetAttribute.WA_LayoutUsesWidgetRect)

        btn_wrap = QHBoxLayout()
        btn_wrap.addStretch(1)
        btn_holder = QWidget()
        btn_holder.setFixedWidth(280)
        btn_holder.setLayout(btn_col)
        btn_wrap.addWidget(btn_holder)
        btn_wrap.addStretch(1)
        root.addLayout(btn_wrap)
        root.addSpacing(16)

        # Recent projects — underlined text links, one per row
        self._recent_box = QFrame()
        recent_col = QVBoxLayout(self._recent_box)
        recent_col.setContentsMargins(0, 0, 0, 0)
        recent_col.setSpacing(3)
        self._recent_header = QLabel(tr("welcome_recent"))
        self._recent_header.setObjectName("welcomeHeader")
        recent_col.addWidget(self._recent_header)
        self._recent_list = QVBoxLayout()
        self._recent_list.setSpacing(2)
        recent_col.addLayout(self._recent_list)

        self._recent_box.setFixedWidth(400)
        recent_wrap = QHBoxLayout()
        recent_wrap.addStretch(1)
        recent_wrap.addWidget(self._recent_box)
        recent_wrap.addStretch(1)
        root.addLayout(recent_wrap)

        root.addStretch(4)

        self._refresh_recent()

    # ------------------------------------------------------------------
    # Content
    # ------------------------------------------------------------------

    def _refresh_recent(self):
        while self._recent_list.count():
            item = self._recent_list.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        recents = self._mw._get_recent_projects()[:_MAX_RECENTS]
        from src.app.theme import get_tokens
        accent = get_tokens(self._mw._current_theme).get("accent", "#0891B2")
        for path in recents:
            name = html.escape(os.path.basename(path))
            folder = os.path.dirname(path)
            if len(folder) > 40:
                folder = "\u2026" + folder[-39:]  # ellipsis + tail
            folder = html.escape(folder)
            href = html.escape(path, quote=True)
            link = QLabel(
                f'<a href="{href}" style="color:{accent}; '
                f'text-decoration: underline;">{name}</a>'
                f'&nbsp;&nbsp;<span style="color:#8C959F;">{folder}</span>'
            )
            link.setObjectName("welcomeRecent")
            link.setTextFormat(Qt.TextFormat.RichText)
            link.setWordWrap(True)
            link.setCursor(Qt.CursorShape.PointingHandCursor)
            link.setToolTip(path)
            link.linkActivated.connect(self._mw._open_path_dispatch)
            self._recent_list.addWidget(link)
        self._recent_box.setVisible(bool(recents))

    def retranslate(self):
        self._btn_about.setText(tr("welcome_about"))
        self._title.setText(tr("about_app_name"))
        self.setWindowTitle(tr("about_app_name"))
        self._btn_new.setText(tr("welcome_new"))
        self._btn_open.setText(tr("welcome_open_project"))
        self._btn_learn.setText(tr('tutorials_welcome'))
        self._btn_close.setText(tr("welcome_close"))
        self._recent_header.setText(tr("welcome_recent"))
        self._drop_hint.setText(tr("welcome_drop_project"))

    # ------------------------------------------------------------------
    # Window behaviour
    # ------------------------------------------------------------------

    def _project_drop_paths(self, mime_data):
        if not mime_data.hasUrls():
            return []
        paths, seen = [], set()
        for url in mime_data.urls():
            if not url.isLocalFile():
                continue
            path = os.path.normpath(url.toLocalFile())
            key = os.path.normcase(os.path.abspath(path))
            if key not in seen and os.path.isfile(path) and self._mw._is_project_drop_path(path):
                seen.add(key)
                paths.append(path)
        return paths

    def _show_drop_feedback(self, active):
        self._drop_hint.setText(tr('welcome_release_project' if active else 'welcome_drop_project'))
        self._drop_feedback.set_target(1.0 if active else 0.0, 100)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._drop_feedback.value <= 0:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = self.palette().color(QPalette.ColorRole.Highlight)
        border = QColor(accent)
        border.setAlpha(round(210 * self._drop_feedback.value))
        fill = QColor(accent)
        fill.setAlpha(round(8 * self._drop_feedback.value))
        painter.setPen(QPen(border, 1.5))
        painter.setBrush(fill)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(8, 8, -8, -8), 8, 8)
        painter.end()

    def dragEnterEvent(self, event):
        valid = bool(self._project_drop_paths(event.mimeData()))
        self._show_drop_feedback(valid)
        if valid:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        self.dragEnterEvent(event)

    def dragLeaveEvent(self, event):
        self._show_drop_feedback(False)
        event.accept()

    def dropEvent(self, event):
        self._show_drop_feedback(False)
        paths = self._project_drop_paths(event.mimeData())
        if not paths:
            event.ignore()
            return
        event.acceptProposedAction()
        open_project = self._mw._open_path_dispatch
        for path in paths:
            open_project(path)

    def closeEvent(self, event):
        # If the main window never surfaced, closing the launcher means
        # quitting the app — run the main window's closeEvent too so its
        # cleanup (snapshot sweep, agent server stop) still executes.
        if not self._mw.isVisible():
            self._mw.close()
        super().closeEvent(event)
