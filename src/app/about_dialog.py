import json
import threading
import urllib.request
import urllib.error

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QFrame, QSizePolicy
)
from PyQt6.QtCore import Qt, QObject, pyqtSignal
from PyQt6.QtGui import QFont, QDesktopServices
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
                    f'<a href="{WEBSITE_URL}" style="color:#4A90E2;">{tr("about_download")}</a>'
                    f' &middot; '
                    f'<a href="{latest_url}" style="color:#4A90E2;">GitHub</a>'
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
        from src.version import APP_VERSION
        self._app_version = APP_VERSION
        self._checker: _UpdateChecker | None = None

        self.setWindowTitle(tr("about_title"))
        self.setFixedWidth(520)
        self.setModal(True)
        self._build_ui()

    def _build_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(28, 28, 28, 20)
        root.setSpacing(0)

        # ── App name ──────────────────────────────────
        title = QLabel(tr("about_app_name"))
        title_font = QFont()
        title_font.setPointSize(18)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(title)
        root.addSpacing(4)

        version_lbl = QLabel(f"Version {self._app_version}")
        version_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_lbl.setStyleSheet("color: #888888; font-size: 12px;")
        root.addWidget(version_lbl)
        root.addSpacing(20)

        # ── Separator ─────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet("color: #444444;")
        root.addWidget(sep)
        root.addSpacing(16)

        # ── Description ───────────────────────────────
        desc = QLabel(tr("about_desc"))
        desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        desc.setWordWrap(True)
        desc.setStyleSheet("color: #AAAAAA; font-size: 12px;")
        root.addWidget(desc)
        root.addSpacing(20)

        # ── Info rows ─────────────────────────────────
        info_layout = QVBoxLayout()
        info_layout.setSpacing(8)

        def info_row(label_text, value_text, link=None):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setStyleSheet("color: #888888; font-size: 12px;")
            lbl.setFixedWidth(90)
            val = QLabel(
                f'<a href="{link}" style="color:#4A90E2;">{value_text}</a>'
                if link else value_text
            )
            val.setStyleSheet("font-size: 12px;")
            val.setOpenExternalLinks(True)
            row.addWidget(lbl)
            row.addWidget(val)
            row.addStretch()
            info_layout.addLayout(row)

        info_row(tr("about_developer"), f'<a href="https://github.com/{GITHUB_OWNER}" '
                              f'style="color:#4A90E2;">@{GITHUB_OWNER}</a>')
        info_row(tr("about_website"),    "luojiajiang.uk", link=WEBSITE_URL)
        info_row(tr("about_repository"), "GitHub", link=GITHUB_URL)
        info_row(tr("about_license"),    "Apache-2.0")

        root.addLayout(info_layout)
        root.addSpacing(20)

        # ── Update status area ────────────────────────
        self._update_label = QLabel(tr("about_click_check"))
        self._update_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._update_label.setWordWrap(True)
        self._update_label.setOpenExternalLinks(True)
        self._update_label.setStyleSheet("color: #888888; font-size: 12px; min-height: 20px;")
        root.addWidget(self._update_label)
        root.addSpacing(16)

        # ── Buttons ───────────────────────────────────
        btn_row = QHBoxLayout()
        btn_row.setSpacing(8)

        self._check_btn = QPushButton(tr("about_check_btn"))
        self._check_btn.clicked.connect(self._on_check_updates)
        btn_row.addWidget(self._check_btn)

        dl_btn = QPushButton(tr("about_download"))
        dl_btn.setToolTip(WEBSITE_URL)
        dl_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(WEBSITE_URL)))
        btn_row.addWidget(dl_btn)
        self._dl_btn = dl_btn

        gh_btn = QPushButton(tr("about_open_github"))
        gh_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl(GITHUB_URL)))
        btn_row.addWidget(gh_btn)

        btn_row.addStretch()

        close_btn = QPushButton(tr("about_close"))
        close_btn.setDefault(True)
        close_btn.clicked.connect(self.accept)
        btn_row.addWidget(close_btn)

        root.addLayout(btn_row)

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
