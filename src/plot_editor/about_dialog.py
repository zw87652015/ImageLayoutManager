"""About dialog for the standalone Plot Editor.

All metadata comes from ``src.version`` (the same source as ILM's own
About page) and all copy lives in the editor i18n table - nothing here
hardcodes a version, publisher, or license.
"""

from PyQt6.QtCore import Qt, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton,
                             QScrollArea, QVBoxLayout, QWidget)

from src.app import i18n as app_i18n
from src.app.license_dialog import LicenseDialog
from src.version import (APP_COPYRIGHT, APP_LICENSE, APP_NAME,
                         APP_PUBLISHER, APP_PUBLISHER_URL, APP_VERSION)

from . import chrome
from .i18n import current_language, tr


class PlotEditorAboutDialog(QDialog):
    """Restrained About page: scrollable copy, fixed action row."""

    def __init__(self, theme, scale=1.0, parent=None):
        super().__init__(parent)
        self._theme = theme
        self._scale = scale
        self.setWindowTitle(tr('about_title'))
        self.setMinimumWidth(400)
        self.resize(560, 590)

        tokens = chrome.style_tokens(theme, scale)
        self.setStyleSheet(
            "QDialog { background: %(surface)s; }"
            "QLabel { color: %(text)s; }"
            "QLabel#aboutTitle { font-size: %(font_base)s; "
            "  font-weight: 700; }"
            "QLabel#aboutSection { color: %(accent)s; "
            "  font-weight: 600; }"
            "QLabel#aboutMeta { color: %(text_sec)s; "
            "  font-size: %(font_sm)s; }"
            "QPushButton { padding: 5px 14px; }"
            % tokens)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 18, 20, 14)
        layout.setSpacing(10)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        content = QWidget()
        body = QVBoxLayout(content)
        body.setContentsMargins(0, 0, 8, 0)
        body.setSpacing(8)

        header = QHBoxLayout()
        header.setSpacing(10)
        icon = QLabel()
        icon.setPixmap(chrome.themed_icon('plot', theme, 'text')
                       .pixmap(28, 28))
        header.addWidget(icon, 0, Qt.AlignmentFlag.AlignTop)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = self._label(tr('app_name'), 'aboutTitle')
        title_col.addWidget(title)
        title_col.addWidget(self._label(
            tr('about_version', version=APP_VERSION), 'aboutMeta'))
        title_col.addWidget(self._label(
            tr('about_suite', name=APP_NAME), 'aboutMeta'))
        header.addLayout(title_col, 1)
        body.addLayout(header)

        body.addSpacing(4)
        body.addWidget(self._label(tr('about_description')))

        for title_key, body_key in (
                ('about_tools_title', 'about_tools_body'),
                ('about_native_title', 'about_native_body'),
                ('about_reflow_title', 'about_reflow_body')):
            body.addSpacing(6)
            body.addWidget(self._label(tr(title_key), 'aboutSection'))
            body.addWidget(self._label(tr(body_key)))

        body.addSpacing(8)
        body.addWidget(self._label(
            tr('about_developer', publisher=APP_PUBLISHER), 'aboutMeta'))
        body.addWidget(self._label(
            tr('about_license', license=APP_LICENSE), 'aboutMeta'))
        body.addWidget(self._label(APP_COPYRIGHT, 'aboutMeta'))
        body.addStretch(1)
        self.scroll.setWidget(content)
        layout.addWidget(self.scroll, 1)

        row = QHBoxLayout()
        row.setSpacing(8)
        repo = QPushButton(tr('about_repository'))
        repo.setAutoDefault(False)
        repo.setCursor(Qt.CursorShape.PointingHandCursor)
        repo.clicked.connect(self._open_repository)
        row.addWidget(repo)
        licenses = QPushButton(tr('about_licenses'))
        licenses.setAutoDefault(False)
        licenses.setCursor(Qt.CursorShape.PointingHandCursor)
        licenses.clicked.connect(self._show_licenses)
        row.addWidget(licenses)
        row.addStretch(1)
        close = QPushButton(tr('btn_close'))
        close.setDefault(True)
        close.clicked.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)

    def _label(self, text, object_name=''):
        label = QLabel(text)
        if object_name:
            label.setObjectName(object_name)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    def _open_repository(self):
        # User-initiated only - the dialog never touches the network on
        # its own.
        QDesktopServices.openUrl(QUrl(APP_PUBLISHER_URL))

    def _show_licenses(self):
        # LicenseDialog reads the shared app i18n table; borrow the
        # editor's language for the dialog's lifetime, then restore.
        previous = app_i18n.current_language()
        app_i18n.set_language(current_language())
        try:
            LicenseDialog(self).exec()
        finally:
            app_i18n.set_language(previous)
