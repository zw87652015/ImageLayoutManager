"""Self-update download dialog for the Inno-Setup installer channel.

Shown from the status-bar update notice (and About's manual check) when a
newer release carries a ``windows_installer`` block. Downloads to a .part
file on a daemon thread, verifies size + SHA-256, then hands the verified
path to the main window via ``install_requested``.
"""

import os
import subprocess
import threading

from PyQt6.QtCore import Qt, pyqtSignal, QSettings
from PyQt6.QtWidgets import (
    QDialog, QHBoxLayout, QLabel, QProgressBar, QPushButton, QVBoxLayout,
)

from src.app.i18n import tr
from src.utils.update_release import (
    DownloadCancelled, DownloadError, cached_installer_path,
    download_installer, verify_file,
)


class UpdateDialog(QDialog):
    install_requested = pyqtSignal(str, object)   # verified installer path, Release

    _progress = pyqtSignal(int, int)
    _finished = pyqtSignal(object)        # str path | DownloadError | DownloadCancelled

    def __init__(self, release, cache_dir, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self._release = release
        self._path = cached_installer_path(cache_dir, release.version)
        self._cancel = threading.Event()
        self._busy = False
        self.setWindowTitle(tr("update_title"))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 14)
        lay.setSpacing(10)
        self._label = QLabel()
        self._label.setWordWrap(True)
        lay.addWidget(self._label)
        self._progress_bar = QProgressBar()
        self._progress_bar.setRange(0, 100)
        self._progress_bar.hide()
        lay.addWidget(self._progress_bar)
        row = QHBoxLayout()
        row.addStretch(1)
        self._buttons = {}
        for key, slot in (
                ("download", self._start_download),
                ("skip", self._on_skip),
                ("cancel", self._cancel_download),
                ("install", self._on_install),
                ("show", self._on_show_in_folder),
                ("redownload", self._on_redownload),
                ("retry", self._start_download),
                ("later", self.close)):
            btn = QPushButton(tr(f"update_btn_{key}"))
            btn.clicked.connect(slot)
            row.addWidget(btn)
            self._buttons[key] = btn
        lay.addLayout(row)

        self._progress.connect(self._on_progress)
        self._finished.connect(self._on_finished)
        if verify_file(self._path, release.installer.sha256,
                       release.installer.size):
            self._set_state("ready")
        else:
            self._set_state("idle")

    # ── states ─────────────────────────────────────────────────────────

    def _show_only(self, keys):
        for key, btn in self._buttons.items():
            btn.setVisible(key in keys)

    def _set_state(self, state, code=None):
        self._state = state
        inst = self._release.installer
        if state == "idle":
            self._label.setText(tr("update_idle").format(
                v=self._release.version, cur=self._current_version(),
                mb=f"{inst.size / 1048576:.1f}"))
            self._progress_bar.hide()
            self._show_only(("download", "skip", "later"))
        elif state == "downloading":
            self._progress_bar.show()
            self._progress_bar.setValue(0)
            self._on_progress(0, inst.size)
            self._show_only(("cancel",))
        elif state == "ready":
            self._label.setText(tr("update_ready"))
            self._progress_bar.hide()
            self._show_only(("install", "show", "redownload", "later"))
        elif state == "error":
            self._label.setText(tr(f"update_err_{code}"))
            self._progress_bar.hide()
            keys = ["retry", "later"]
            if os.path.isfile(self._path):
                keys.insert(1, "show")
            self._show_only(tuple(keys))

    @staticmethod
    def _current_version():
        from src.version import APP_VERSION
        return APP_VERSION

    # ── download ───────────────────────────────────────────────────────

    def _start_download(self):
        if self._busy:
            return
        self._busy = True
        self._cancel.clear()
        self._set_state("downloading")
        installer, dest, cancel = self._release.installer, self._path, self._cancel

        def run():
            try:
                result = download_installer(
                    installer, dest,
                    progress=lambda d, t: self._progress.emit(d, t),
                    cancel=cancel)
            except (DownloadError, DownloadCancelled) as exc:
                result = exc
            except Exception as exc:
                result = DownloadError("network")
            self._finished.emit(result)

        threading.Thread(target=run, daemon=True, name="UpdateDownload").start()

    def _cancel_download(self):
        self._cancel.set()

    def _on_redownload(self):
        try:
            os.remove(self._path)
        except OSError:
            pass
        self._start_download()

    def _on_progress(self, done, total):
        self._progress_bar.setValue(round(100 * done / total) if total else 0)
        self._label.setText(tr("update_downloading").format(
            done=f"{done / 1048576:.1f}", total=f"{total / 1048576:.1f}"))

    def _on_finished(self, result):
        self._busy = False
        if isinstance(result, DownloadCancelled):
            self._set_state("idle")
        elif isinstance(result, DownloadError):
            self._set_state("error", code=result.code)
        else:
            self._set_state("ready")

    # ── actions ────────────────────────────────────────────────────────

    def _on_skip(self):
        QSettings("AcademicFigureLayout", "ImageLayoutManager").setValue(
            "updates/skipped_version", self._release.version)
        self.close()

    def _on_install(self):
        self.install_requested.emit(self._path, self._release)

    def _on_show_in_folder(self):
        path = os.path.normpath(os.path.abspath(self._path))
        if os.path.isfile(path):
            subprocess.Popen(["explorer.exe", "/select,", path])

    def closeEvent(self, event):
        self._cancel.set()
        super().closeEvent(event)
