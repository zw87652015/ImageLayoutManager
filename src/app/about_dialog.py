from __future__ import annotations

import json
import threading
import urllib.request
import urllib.error

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QColor, QDesktopServices
from PyQt6.QtCore import QUrl
from src.app.i18n import tr

GITHUB_OWNER = "zw87652015"
GITHUB_REPO  = "ImageLayoutManager"
GITHUB_URL   = f"https://github.com/{GITHUB_OWNER}/{GITHUB_REPO}"
WEBSITE_URL  = "https://luojiajiang.uk/image-layout-manager"
# Self-hosted version manifest. Schema:
#   { "version": "3.2", "url": "<download_page_url>", "notes": "optional" }
# Served as a static file from the author's website so update checks don't
# depend on api.github.com being reachable (often blocked in mainland China).
RELEASES_API = "https://luojiajiang.uk/image-layout-manager/latest.json"


def _parse_version(v: str):
    """Return a tuple of ints for simple semver comparison, ignoring leading 'v'."""
    v = v.lstrip("vV")
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


class StartupUpdateChecker(QObject):
    """Silent background update check used at app startup.

    Runs on a daemon ``threading.Thread`` (not ``QThread``) so the Python
    interpreter can exit even while the blocking urllib call is in flight —
    avoids ``QThread: Destroyed while thread '' is still running`` when the
    user quits the app before the network response arrives. Emits
    ``update_available(latest_tag, url)`` only when a strictly newer release
    exists on GitHub; silent on failures, parse errors, same version, or
    pre-releases.
    """
    update_available = pyqtSignal(str, str)  # latest_tag, url

    def start(self):
        threading.Thread(target=self._run, daemon=True,
                         name="StartupUpdateChecker").start()

    def _run(self):
        try:
            req = urllib.request.Request(
                RELEASES_API,
                headers={"User-Agent": "AcademicFigureLayout-UpdateChecker"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            latest_tag = data.get("version") or data.get("tag_name") or ""
            latest_url = data.get("url") or data.get("html_url") or WEBSITE_URL
            if not latest_tag:
                return
            from src.version import APP_VERSION
            if _parse_version(latest_tag) > _parse_version(APP_VERSION):
                # Signal emission is auto-queued to the UI thread.
                self.update_available.emit(latest_tag, latest_url)
        except Exception:
            # Silent on all failures: user can still check manually via About.
            pass


class _UpdateChecker(QObject):
    """Manual update check from the About dialog — daemon-thread based.

    See ``StartupUpdateChecker`` for the rationale. The caller must keep a
    reference to this instance until ``result_ready`` fires (or the dialog
    closes, at which point the signal should be disconnected).
    """
    result_ready = pyqtSignal(str)   # emits status message

    def start(self):
        threading.Thread(target=self._run, daemon=True,
                         name="UpdateChecker").start()

    def _run(self):
        try:
            req = urllib.request.Request(
                RELEASES_API,
                headers={"User-Agent": "AcademicFigureLayout-UpdateChecker"}
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read().decode())
            latest_tag = data.get("version") or data.get("tag_name") or ""
            latest_url = data.get("url") or data.get("html_url") or WEBSITE_URL
            if not latest_tag:
                self.result_ready.emit("⚠ No release information found.")
                return

            from src.version import APP_VERSION
            current = _parse_version(APP_VERSION)
            latest  = _parse_version(latest_tag)

            if latest > current:
                self.result_ready.emit(
                    f'🔔 New version <b>{latest_tag}</b> is available!  '
                    f'<a href="{WEBSITE_URL}">{tr("about_download")}</a>'
                    f' &middot; '
                    f'<a href="{latest_url}">GitHub</a>'
                )
            elif latest == current:
                self.result_ready.emit(tr("about_latest"))
            else:
                self.result_ready.emit(tr("about_pre"))
        except urllib.error.URLError:
            self.result_ready.emit(tr("about_no_conn"))
        except Exception as e:
            self.result_ready.emit(f"⚠ Update check failed: {e}")


class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        from src.version import APP_VERSION, APP_COPYRIGHT
        self._app_version = APP_VERSION
        self._app_copyright = APP_COPYRIGHT
        self._checker: _UpdateChecker | None = None

        self.setWindowTitle(tr("about_title"))
        self.setFixedWidth(500)
        self.setModal(True)
        self._build_ui()

    def _theme_tokens(self):
        from src.app.theme import LIGHT, _font_tokens, get_tokens
        parent = self.parent()
        theme = getattr(parent, '_current_theme', LIGHT)
        try:
            scale = float(parent._current_font_scale())
        except (AttributeError, TypeError, ValueError):
            scale = 1.0
        return {**get_tokens(theme), **_font_tokens(scale)}, scale

    def _build_ui(self):
        from PyQt6.QtGui import QPalette
        from PyQt6.QtWidgets import QGridLayout

        tokens, scale = self._theme_tokens()
        tokens = {**tokens, "font_title": f"{round(20 * scale)}px"}
        palette = self.palette()
        palette.setColor(QPalette.ColorRole.Link, QColor(tokens["accent"]))
        palette.setColor(QPalette.ColorRole.LinkVisited, QColor(tokens["accent"]))
        self.setPalette(palette)
        self.setStyleSheet(
            "QDialog { background: %(surface)s; }"
            "QLabel { color: %(text)s; font-size: %(font_md)s; }"
            "QLabel#aboutTitle { font-size: %(font_title)s; font-weight: 600; }"
            "QLabel#aboutMeta { color: %(text_sec)s; }"
            "QLabel#aboutKey { color: %(text_sec)s; }"
            "QLabel#aboutFine { color: %(text_tert)s; font-size: %(font_sm)s; }"
            "QFrame#aboutDivider { background: %(divider)s; border: none; }"
            "QFrame#aboutCard { background: %(surface_subtle)s;"
            "  border: 1px solid %(border)s; border-radius: %(radius_panel)s; }"
            "QFrame#aboutCard QLabel { background: transparent; border: none; }"
            "QPushButton#aboutLink { color: %(accent)s; background: transparent;"
            "  border: none; padding: 2px 0; font-size: %(font_md)s; text-align: left; }"
            "QPushButton#aboutLink:hover { color: %(accent_hover)s; text-decoration: underline; }"
            "QScrollArea#aboutChangelog { background: %(surface_subtle)s;"
            "  border: 1px solid %(border)s; border-radius: %(radius_panel)s; }"
            "QWidget#aboutChangelogBody { background: transparent; }"
            "QToolButton#aboutVersion { color: %(text)s; background: transparent;"
            "  border: none; border-radius: %(radius_button)s; padding: 5px 6px;"
            "  font-size: %(font_md)s; font-weight: 600; text-align: left; }"
            "QToolButton#aboutVersion:hover { background: %(hover)s; }"
            "QToolButton#aboutVersion:focus { background: %(accent_tint)s; }"
            "QLabel#aboutNotes { color: %(text)s; padding: 0 6px 6px 22px; }"
            % tokens)

        root = QVBoxLayout(self)
        root.setContentsMargins(28, 24, 28, 20)
        root.setSpacing(0)

        # ── Header: icon + name + version ─────────────
        header = QHBoxLayout()
        header.setSpacing(14)
        icon = self.parent().windowIcon() if self.parent() is not None else None
        if icon is not None and not icon.isNull():
            icon_lbl = QLabel()
            icon_lbl.setPixmap(icon.pixmap(52, 52))
            icon_lbl.setFixedSize(52, 52)
            header.addWidget(icon_lbl, 0, Qt.AlignmentFlag.AlignTop)
        title_col = QVBoxLayout()
        title_col.setSpacing(2)
        title = QLabel(tr("about_app_name"))
        title.setObjectName("aboutTitle")
        title_col.addWidget(title)
        version_lbl = QLabel(tr("about_version").format(version=self._app_version))
        version_lbl.setObjectName("aboutMeta")
        version_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        title_col.addWidget(version_lbl)
        title_col.addStretch(1)
        header.addLayout(title_col, 1)
        root.addLayout(header)
        root.addSpacing(14)

        desc = QLabel(tr("about_desc"))
        desc.setObjectName("aboutMeta")
        desc.setWordWrap(True)
        root.addWidget(desc)
        root.addSpacing(16)

        root.addWidget(self._divider())
        root.addSpacing(14)

        # ── Info grid ─────────────────────────────────
        grid = QGridLayout()
        grid.setHorizontalSpacing(18)
        grid.setVerticalSpacing(8)
        grid.setColumnStretch(1, 1)
        rows = (
            (tr("about_developer"), self._link(f"https://github.com/{GITHUB_OWNER}", f"@{GITHUB_OWNER}")),
            (tr("about_website"), self._link(WEBSITE_URL, "luojiajiang.uk")),
            (tr("about_repository"), self._link(GITHUB_URL, f"{GITHUB_OWNER}/{GITHUB_REPO}")),
            (tr("about_license"), tr("about_license_summary")),
        )
        for r, (key, value) in enumerate(rows):
            key_lbl = QLabel(key)
            key_lbl.setObjectName("aboutKey")
            val_lbl = QLabel(value)
            val_lbl.setWordWrap(True)
            val_lbl.setOpenExternalLinks(True)
            val_lbl.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
            grid.addWidget(key_lbl, r, 0, Qt.AlignmentFlag.AlignTop)
            grid.addWidget(val_lbl, r, 1)
        root.addLayout(grid)
        root.addSpacing(10)

        links = QHBoxLayout()
        links.setSpacing(18)
        licenses_btn = self._link_button(tr("about_licenses"), self._show_licenses)
        links.addWidget(licenses_btn)
        self._changelog_btn = self._link_button("▸ " + tr("about_changelog"), self._toggle_changelog)
        links.addWidget(self._changelog_btn)
        links.addStretch(1)
        root.addLayout(links)

        # ── Changelog (hidden until requested) ────────
        # One collapsible section per version; only the newest starts open.
        self._changelog_view = self._build_changelog()
        self._changelog_view.setVisible(False)
        root.addSpacing(6)
        root.addWidget(self._changelog_view)
        root.addSpacing(12)

        # ── Update card ───────────────────────────────
        card = QFrame()
        card.setObjectName("aboutCard")
        card_row = QHBoxLayout(card)
        card_row.setContentsMargins(14, 10, 10, 10)
        card_row.setSpacing(12)
        self._update_label = QLabel(tr("about_click_check"))
        self._update_label.setObjectName("aboutMeta")
        self._update_label.setWordWrap(True)
        self._update_label.setOpenExternalLinks(True)
        self._update_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextBrowserInteraction)
        card_row.addWidget(self._update_label, 1)
        self._check_btn = QPushButton(tr("about_check_btn"))
        self._check_btn.setAutoDefault(False)
        self._check_btn.clicked.connect(self._on_check_updates)
        card_row.addWidget(self._check_btn, 0, Qt.AlignmentFlag.AlignVCenter)
        root.addWidget(card)
        root.addSpacing(16)

        # ── Footer: copyright + actions ───────────────
        # Matches the LegalCopyright string embedded in the .exe and the
        # AppCopyright field in the Inno Setup installer so users see the
        # same attribution everywhere.
        footer = QHBoxLayout()
        footer.setSpacing(8)
        copyright_lbl = QLabel(self._app_copyright)
        copyright_lbl.setObjectName("aboutFine")
        copyright_lbl.setWordWrap(True)
        footer.addWidget(copyright_lbl, 1, Qt.AlignmentFlag.AlignVCenter)
        dl_btn = QPushButton(tr("about_download"))
        dl_btn.setAutoDefault(False)
        dl_btn.setToolTip(WEBSITE_URL)
        dl_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(WEBSITE_URL)))
        footer.addWidget(dl_btn)
        self._dl_btn = dl_btn
        close_btn = QPushButton(tr("about_close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        footer.addWidget(close_btn)
        root.addLayout(footer)

    def _build_changelog(self):
        import html
        from PyQt6.QtWidgets import QScrollArea, QToolButton, QWidget
        from src.app.changelog import CHANGELOG
        from src.app.i18n import current_language

        lang = current_language()
        area = QScrollArea()
        area.setObjectName("aboutChangelog")
        area.setWidgetResizable(True)
        area.setFixedHeight(260)
        area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        body = QWidget()
        body.setObjectName("aboutChangelogBody")
        col = QVBoxLayout(body)
        col.setContentsMargins(6, 6, 6, 6)
        col.setSpacing(2)

        for index, (version, date, bullets) in enumerate(CHANGELOG):
            header = QToolButton()
            header.setObjectName("aboutVersion")
            header.setCheckable(True)
            header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
            header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            header.setCursor(Qt.CursorShape.PointingHandCursor)
            header.setText(f"{version}    {date}    ·  "
                           + tr("about_changes_count").format(n=len(bullets)))
            notes = QLabel("<ul style='margin:0; -qt-list-indent:1;'>" + "".join(
                f"<li style='margin-bottom:3px;'>{html.escape(b.get(lang, b['en']))}</li>"
                for b in bullets) + "</ul>")
            notes.setObjectName("aboutNotes")
            notes.setTextFormat(Qt.TextFormat.RichText)
            notes.setWordWrap(True)
            notes.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

            def toggle(open_, header=header, notes=notes, version=version):
                header.setArrowType(Qt.ArrowType.DownArrow if open_ else Qt.ArrowType.RightArrow)
                notes.setVisible(open_)

            header.setAccessibleName(tr("about_version").format(version=version))
            header.toggled.connect(toggle)
            # Parent the widgets before toggling: setVisible(True) on a
            # parentless QLabel would briefly show it as its own window.
            col.addWidget(header)
            col.addWidget(notes)
            header.setChecked(index == 0)
            toggle(index == 0)
        col.addStretch(1)
        area.setWidget(body)
        return area

    @staticmethod
    def _link(url, text):
        return f'<a href="{url}" style="text-decoration:none;">{text}</a>'

    @staticmethod
    def _divider():
        line = QFrame()
        line.setObjectName("aboutDivider")
        line.setFixedHeight(1)
        return line

    def _link_button(self, text, slot):
        btn = QPushButton(text)
        btn.setObjectName("aboutLink")
        btn.setFlat(True)
        btn.setAutoDefault(False)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(slot)
        return btn

    def _show_licenses(self):
        from src.app.license_dialog import LicenseDialog
        dlg = LicenseDialog(self)
        dlg.exec()

    def _toggle_changelog(self):
        show = not self._changelog_view.isVisible()
        self._changelog_view.setVisible(show)
        arrow = "▾" if show else "▸"
        self._changelog_btn.setText(f"{arrow} " + tr("about_changelog"))
        # adjustSize() asks for a height below the fixed-width layout's
        # word-wrapped minimum and Windows rejects it ("Unable to set
        # geometry"); compute the real minimum ourselves instead.
        layout = self.layout()
        layout.activate()
        if layout.hasHeightForWidth():
            h = layout.totalHeightForWidth(self.width())
        else:
            h = layout.totalSizeHint().height()
        h = max(h, layout.totalMinimumSize().height())
        self.resize(self.width(), h)

    def _on_check_updates(self):
        from PyQt6.QtWidgets import QApplication
        self._check_btn.setEnabled(False)
        self._update_label.setText(tr("about_checking"))
        # Parent to QApplication so the QObject outlives this dialog; the
        # daemon thread may still be running when the user closes About.
        self._checker = _UpdateChecker(QApplication.instance())
        self._checker.result_ready.connect(self._on_update_result)
        self._checker.start()

    def _on_update_result(self, message: str):
        self._update_label.setText(message)
        self._check_btn.setEnabled(True)

    def closeEvent(self, event):
        # Drop the signal connection so a late thread reply can't call into
        # a deleted widget. The QObject itself is parented to QApplication
        # and will be collected when the daemon thread exits.
        if self._checker is not None:
            try:
                self._checker.result_ready.disconnect(self._on_update_result)
            except (TypeError, RuntimeError):
                pass
            self._checker = None
        super().closeEvent(event)

    def done(self, result):
        # Same cleanup when the dialog is closed via accept()/reject().
        if self._checker is not None:
            try:
                self._checker.result_ready.disconnect(self._on_update_result)
            except (TypeError, RuntimeError):
                pass
            self._checker = None
        super().done(result)
