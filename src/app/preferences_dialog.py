"""
Preferences dialog — tabbed, persistent via QSettings.

Tabs
----
General         Language, theme, undo history limit.
Files & Editing Default save format, export directory policy, hot-reload.
Bundles         figpack cache location, quota, compression, watch-originals.
                Also exposes "Open Cache Folder" and "Clear Cache Now" actions.
"""

from __future__ import annotations

import os
from typing import Optional

from PyQt6.QtCore import Qt, QSettings
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QGraphicsOpacityEffect,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from src.app.i18n import tr
from src.app.motion import MotionTween, install_button_feedback, set_motion_mode
from src.app.theme import LIGHT, DARK


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

def _read_settings() -> QSettings:
    return QSettings("AcademicFigureLayout", "ImageLayoutManager")


def get_pref(key: str, default):
    s = _read_settings()
    v = s.value(key, default)
    # QSettings returns strings; coerce booleans and ints when the default
    # type gives us a hint.
    if isinstance(default, bool):
        if isinstance(v, str):
            return v.lower() not in ("false", "0", "no", "")
        return bool(v)
    if isinstance(default, int):
        try:
            return int(v)
        except (TypeError, ValueError):
            return default
    return v


# ──────────────────────────────────────────────────────────────────────────────
# Dialog
# ──────────────────────────────────────────────────────────────────────────────

class PreferencesDialog(QDialog):
    """
    Modal preferences dialog with explicit Apply semantics: edits to any
    control only take effect (saved to QSettings + propagated to the live
    ``main_window``) when Apply or OK is pressed. Cancel — or simply closing
    the dialog without pressing either — discards them; nothing is written
    or applied until then. OK is "Apply, then close".
    """

    def __init__(self, main_window, parent=None):
        super().__init__(parent)
        self._mw = main_window
        self._settings = _read_settings()
        self.setWindowTitle(tr("prefs_title"))
        self.setMinimumWidth(520)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)

        root = QVBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 8)
        root.setSpacing(8)

        self._tabs = QTabWidget()
        self._tabs.addTab(self._build_general(), tr("prefs_tab_general"))
        self._tabs.addTab(self._build_files(), tr("prefs_tab_files"))
        self._tabs.addTab(self._build_bundles(), tr("prefs_tab_bundles"))
        self._tabs.addTab(self._build_ocr(), tr("prefs_tab_ocr"))
        root.addWidget(self._tabs)

        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok
            | QDialogButtonBox.StandardButton.Cancel
            | QDialogButtonBox.StandardButton.Apply
        )
        btns.accepted.connect(self._on_ok)
        btns.rejected.connect(self.reject)
        self._apply_btn = btns.button(QDialogButtonBox.StandardButton.Apply)
        self._apply_btn.clicked.connect(self._on_apply)
        self._apply_btn.setEnabled(False)
        footer = QHBoxLayout()
        self._applied_status = QLabel()
        self._applied_status.setObjectName("preferencesAppliedStatus")
        self._applied_status.setForegroundRole(QPalette.ColorRole.Text)
        self._applied_effect = QGraphicsOpacityEffect(self._applied_status)
        self._applied_status.setGraphicsEffect(self._applied_effect)
        self._applied_feedback = MotionTween(self)
        self._applied_feedback.updated.connect(self._applied_effect.setOpacity)
        footer.addWidget(self._applied_status, 1)
        footer.addWidget(btns)
        root.addLayout(footer)

        # Any edit to a settings control arms Apply; OK/Apply disarm it again.
        # Wired last so the initial setChecked()/setValue() calls above don't
        # themselves count as user edits.
        self._wire_dirty_tracking()
        install_button_feedback(self)

    def _wire_dirty_tracking(self):
        """Arm the Apply button when any settings control changes value."""
        for w in self.findChildren(QComboBox):
            w.currentIndexChanged.connect(self._mark_dirty)
        for w in self.findChildren(QCheckBox):
            w.toggled.connect(self._mark_dirty)
        for w in self.findChildren(QRadioButton):
            w.toggled.connect(self._mark_dirty)
        for w in self.findChildren(QSpinBox):
            w.valueChanged.connect(self._mark_dirty)
        for w in self.findChildren(QLineEdit):
            w.textChanged.connect(self._mark_dirty)

    def _mark_dirty(self, *_args):
        self._applied_status.setText("")
        self._apply_btn.setEnabled(True)

    # ── Tab builders ──────────────────────────────────────────────────────────

    def _build_general(self) -> QWidget:
        w = QWidget()
        form = QFormLayout(w)
        form.setContentsMargins(16, 16, 16, 16)
        form.setSpacing(10)

        # Language
        self._lang_combo = QComboBox()
        self._lang_combo.addItem("English", "en")
        self._lang_combo.addItem("中文", "zh")
        current_lang = self._settings.value("language", "zh")
        idx = self._lang_combo.findData(current_lang)
        if idx >= 0:
            self._lang_combo.setCurrentIndex(idx)
        form.addRow(tr("prefs_language"), self._lang_combo)

        # Theme
        self._theme_combo = QComboBox()
        self._theme_combo.addItem(tr("prefs_theme_light"), LIGHT)
        self._theme_combo.addItem(tr("prefs_theme_dark"), DARK)
        current_theme = self._settings.value("theme", LIGHT)
        tidx = self._theme_combo.findData(current_theme)
        if tidx >= 0:
            self._theme_combo.setCurrentIndex(tidx)
        form.addRow(tr("prefs_theme"), self._theme_combo)

        self._motion_combo = QComboBox()
        for mode in ("standard", "reduced", "off"):
            self._motion_combo.addItem(tr("prefs_motion_" + mode), mode)
        motion_index = self._motion_combo.findData(
            self._settings.value("ui/motion_mode", "standard")
        )
        self._motion_combo.setCurrentIndex(max(0, motion_index))
        self._motion_combo.setToolTip(tr("prefs_motion_hint"))
        form.addRow(tr("prefs_motion"), self._motion_combo)
        motion_hint = QLabel(tr("prefs_motion_hint"))
        motion_hint.setWordWrap(True)
        motion_hint.setForegroundRole(QPalette.ColorRole.PlaceholderText)
        form.addRow("", motion_hint)

        # Undo limit
        self._undo_spin = QSpinBox()
        self._undo_spin.setRange(50, 2000)
        self._undo_spin.setSingleStep(50)
        self._undo_spin.setSuffix(" steps")
        self._undo_spin.setValue(int(self._settings.value("max_history", 200)))
        form.addRow(tr("prefs_undo_limit"), self._undo_spin)

        # Autosave interval (recovery snapshots); 0 disables
        self._autosave_spin = QSpinBox()
        self._autosave_spin.setRange(0, 3600)
        self._autosave_spin.setSingleStep(30)
        self._autosave_spin.setSuffix(" s")
        self._autosave_spin.setSpecialValueText("0 s (" + tr("prefs_autosave_off") + ")")
        self._autosave_spin.setToolTip(tr("prefs_autosave_interval_tip"))
        self._autosave_spin.setValue(get_pref("autosave_interval_s", 180))
        form.addRow(tr("prefs_autosave_interval"), self._autosave_spin)

        # MCP auto-start
        self._mcp_autostart_chk = QCheckBox(tr("prefs_mcp_autostart"))
        self._mcp_autostart_chk.setToolTip(tr("prefs_mcp_autostart_tip"))
        self._mcp_autostart_chk.setChecked(get_pref("mcp_autostart", False))
        form.addRow("", self._mcp_autostart_chk)

        return w

    def _build_files(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Default save format
        fmt_group = QGroupBox(tr("prefs_default_save_format"))
        fmt_layout = QVBoxLayout(fmt_group)
        self._fmt_figlayout = QRadioButton(tr("prefs_fmt_figlayout"))
        self._fmt_figpack   = QRadioButton(tr("prefs_fmt_figpack"))
        fmt_layout.addWidget(self._fmt_figlayout)
        fmt_layout.addWidget(self._fmt_figpack)
        current_fmt = self._settings.value("default_save_format", "figlayout")
        if current_fmt == "figpack":
            self._fmt_figpack.setChecked(True)
        else:
            self._fmt_figlayout.setChecked(True)
        layout.addWidget(fmt_group)

        # Export directory policy
        export_group = QGroupBox(tr("prefs_export_dir_policy"))
        export_vbox = QVBoxLayout(export_group)
        self._exp_project = QRadioButton(tr("prefs_export_dir_project"))
        self._exp_last    = QRadioButton(tr("prefs_export_dir_last"))
        self._exp_custom  = QRadioButton(tr("prefs_export_dir_custom"))
        for rb in (self._exp_project, self._exp_last, self._exp_custom):
            export_vbox.addWidget(rb)
        policy = self._settings.value("export_dir_policy", "project")
        {"project": self._exp_project,
         "last":    self._exp_last,
         "custom":  self._exp_custom}.get(policy, self._exp_project).setChecked(True)

        custom_row = QHBoxLayout()
        self._exp_custom_path = QLineEdit()
        self._exp_custom_path.setPlaceholderText(tr("prefs_export_dir_browse"))
        self._exp_custom_path.setText(self._settings.value("export_dir_custom", ""))
        self._exp_custom_path.setEnabled(self._exp_custom.isChecked())
        browse_btn = QPushButton(tr("prefs_export_dir_browse"))
        browse_btn.setFixedWidth(90)
        browse_btn.clicked.connect(self._browse_export_dir)
        browse_btn.setEnabled(self._exp_custom.isChecked())
        custom_row.addWidget(self._exp_custom_path)
        custom_row.addWidget(browse_btn)
        export_vbox.addLayout(custom_row)

        self._exp_custom.toggled.connect(self._exp_custom_path.setEnabled)
        self._exp_custom.toggled.connect(browse_btn.setEnabled)
        layout.addWidget(export_group)

        # Hot-reload
        self._hot_reload_chk = QCheckBox(tr("prefs_hot_reload"))
        self._hot_reload_chk.setToolTip(tr("prefs_hot_reload_tip"))
        self._hot_reload_chk.setChecked(get_pref("hot_reload_enabled", True))
        layout.addWidget(self._hot_reload_chk)

        layout.addStretch()
        return w

    def _build_bundles(self) -> QWidget:
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        # Cache location
        cache_group = QGroupBox(tr("prefs_cache_location"))
        cache_vbox = QVBoxLayout(cache_group)
        cache_row = QHBoxLayout()
        self._cache_path_edit = QLineEdit()
        self._cache_path_edit.setPlaceholderText(tr("prefs_cache_default"))
        self._cache_path_edit.setText(self._settings.value("figpack_cache_root", ""))
        cache_browse = QPushButton(tr("prefs_cache_browse"))
        cache_browse.setFixedWidth(90)
        cache_browse.clicked.connect(self._browse_cache_dir)
        cache_reset = QPushButton(tr("prefs_cache_reset"))
        cache_reset.clicked.connect(lambda: self._cache_path_edit.clear())
        cache_row.addWidget(self._cache_path_edit)
        cache_row.addWidget(cache_browse)
        cache_row.addWidget(cache_reset)
        cache_vbox.addLayout(cache_row)

        # Quota
        quota_row = QHBoxLayout()
        quota_label = QLabel(tr("prefs_cache_quota"))
        self._quota_spin = QSpinBox()
        self._quota_spin.setRange(1, 200)
        self._quota_spin.setSuffix(" GB")
        self._quota_spin.setValue(get_pref("figpack_quota_gb", 10))
        quota_row.addWidget(quota_label)
        quota_row.addWidget(self._quota_spin)
        quota_row.addStretch()
        cache_vbox.addLayout(quota_row)
        layout.addWidget(cache_group)

        # Watch originals
        self._watch_chk = QCheckBox(tr("prefs_watch_original"))
        self._watch_chk.setToolTip(tr("prefs_watch_original_tip"))
        self._watch_chk.setChecked(get_pref("figpack_watch_original", True))
        layout.addWidget(self._watch_chk)

        # Compress assets
        self._compress_chk = QCheckBox(tr("prefs_compress_assets"))
        self._compress_chk.setToolTip(tr("prefs_compress_assets_tip"))
        self._compress_chk.setChecked(get_pref("figpack_compress_assets", False))
        layout.addWidget(self._compress_chk)

        # Action buttons
        btn_row = QHBoxLayout()
        open_cache_btn = QPushButton(tr("prefs_open_cache_folder"))
        open_cache_btn.clicked.connect(self._on_open_cache_folder)
        clear_cache_btn = QPushButton(tr("prefs_clear_cache"))
        clear_cache_btn.clicked.connect(self._on_clear_cache)
        btn_row.addWidget(open_cache_btn)
        btn_row.addWidget(clear_cache_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        layout.addStretch()
        return w

    def _build_ocr(self) -> QWidget:
        from src.utils.raster_text_ocr import BACKENDS, DEFAULT_BACKEND
        w = QWidget()
        layout = QVBoxLayout(w)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        hint = QLabel(tr("prefs_ocr_hint"))
        hint.setWordWrap(True)
        layout.addWidget(hint)

        form = QFormLayout()
        self._ocr_combo = QComboBox()
        for name in BACKENDS:
            self._ocr_combo.addItem(tr("prefs_ocr_backend_" + name), name)
        idx = self._ocr_combo.findData(self._settings.value("ocr_backend", DEFAULT_BACKEND))
        self._ocr_combo.setCurrentIndex(max(0, idx))
        form.addRow(tr("prefs_ocr_backend"), self._ocr_combo)

        self._ocr_command = QLineEdit(self._settings.value("ocr_command", ""))
        self._ocr_command.setPlaceholderText("my_ocr.exe --json {image}")
        self._ocr_command.setToolTip(tr("prefs_ocr_command_tip"))
        form.addRow(tr("prefs_ocr_command"), self._ocr_command)
        layout.addLayout(form)

        cmd_tip = QLabel(tr("prefs_ocr_command_tip"))
        cmd_tip.setWordWrap(True)
        cmd_tip.setStyleSheet("color: #666;")
        layout.addWidget(cmd_tip)

        test_row = QHBoxLayout()
        test_btn = QPushButton(tr("prefs_ocr_test"))
        test_btn.clicked.connect(self._on_ocr_test)
        self._ocr_status = QLabel()
        self._ocr_status.setWordWrap(True)
        test_row.addWidget(test_btn)
        test_row.addWidget(self._ocr_status, 1)
        layout.addLayout(test_row)

        def _sync_command_enabled(_=None):
            self._ocr_command.setEnabled(self._ocr_combo.currentData() == "command")
        self._ocr_combo.currentIndexChanged.connect(_sync_command_enabled)
        _sync_command_enabled()

        layout.addStretch()
        return w

    # ── Actions ───────────────────────────────────────────────────────────────

    def _on_ocr_test(self):
        from src.utils.raster_text_ocr import backend_status
        reason = backend_status(self._ocr_combo.currentData(), self._ocr_command.text())
        if reason is None:
            self._ocr_status.setStyleSheet("color: #2e9e44;")
            self._ocr_status.setText(tr("prefs_ocr_status_ok"))
        else:
            self._ocr_status.setStyleSheet("color: #b00020;")
            self._ocr_status.setText(reason)

    def _browse_export_dir(self):
        start = self._exp_custom_path.text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, tr("prefs_export_dir_browse"), start)
        if path:
            self._exp_custom_path.setText(path)

    def _browse_cache_dir(self):
        start = self._cache_path_edit.text() or os.path.expanduser("~")
        path = QFileDialog.getExistingDirectory(self, tr("prefs_cache_location"), start)
        if path:
            self._cache_path_edit.setText(path)

    def _on_open_cache_folder(self):
        from src.utils.figpack.cache_manager import default_cache_root
        cache_root = self._cache_path_edit.text().strip() or default_cache_root()
        os.makedirs(cache_root, exist_ok=True)
        from PyQt6.QtGui import QDesktopServices
        from PyQt6.QtCore import QUrl
        QDesktopServices.openUrl(QUrl.fromLocalFile(cache_root))

    def _on_clear_cache(self):
        reply = QMessageBox.question(
            self,
            tr("prefs_clear_cache"),
            tr("prefs_clear_cache_confirm"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        from src.utils.figpack.cache_manager import cleanup_orphans, default_cache_root
        cache_root = self._cache_path_edit.text().strip() or default_cache_root()
        deleted = cleanup_orphans(cache_root)
        n = len(deleted)
        y = "y" if n == 1 else "ies"
        msg = tr("prefs_cache_cleared").format(n=n, y=y)
        QMessageBox.information(self, tr("prefs_clear_cache"), msg)

    # ── OK / apply ────────────────────────────────────────────────────────────

    def _on_ok(self):
        self._on_apply()
        self.accept()

    def _on_apply(self):
        """Persist settings and propagate them to the running app. Nothing
        in this dialog takes effect until Apply (or OK, which applies then
        closes) is pressed — Cancel leaves the running app untouched."""
        self._save()
        self.apply()
        self._apply_btn.setEnabled(False)
        self._applied_status.setText(tr("prefs_applied"))
        self._applied_feedback.set_target(0.0, 0)
        self._applied_feedback.set_target(1.0, 110)

    def _save(self):
        s = self._settings

        # General
        s.setValue("language", self._lang_combo.currentData())
        s.setValue("theme", self._theme_combo.currentData())
        s.setValue("ui/motion_mode", self._motion_combo.currentData())
        s.setValue("max_history", self._undo_spin.value())
        s.setValue("autosave_interval_s", self._autosave_spin.value())
        s.setValue("mcp_autostart", self._mcp_autostart_chk.isChecked())

        # Files
        fmt = "figpack" if self._fmt_figpack.isChecked() else "figlayout"
        s.setValue("default_save_format", fmt)
        if self._exp_project.isChecked():
            policy = "project"
        elif self._exp_last.isChecked():
            policy = "last"
        else:
            policy = "custom"
        s.setValue("export_dir_policy", policy)
        s.setValue("export_dir_custom", self._exp_custom_path.text().strip())
        s.setValue("hot_reload_enabled", self._hot_reload_chk.isChecked())

        # Bundles
        s.setValue("figpack_cache_root", self._cache_path_edit.text().strip())
        s.setValue("figpack_quota_gb", self._quota_spin.value())
        s.setValue("figpack_watch_original", self._watch_chk.isChecked())
        s.setValue("figpack_compress_assets", self._compress_chk.isChecked())

        # Text detection
        s.setValue("ocr_backend", self._ocr_combo.currentData())
        s.setValue("ocr_command", self._ocr_command.text().strip())

    def apply(self):
        """Propagate saved settings to the running main window."""
        set_motion_mode(self._settings.value("ui/motion_mode", "standard"))
        mw = self._mw
        if mw is None:
            return

        # Language
        new_lang = self._settings.value("language", "zh")
        from src.app.i18n import set_language, current_language
        if new_lang != current_language():
            set_language(new_lang)
            mw.retranslate_ui()

        # Theme — go through MainWindow._apply_theme so palette, stylesheet,
        # canvas scenes, layers panel, inspector and icons ALL update. The
        # previous hand-rolled subset left the canvas on the old theme.
        new_theme = self._settings.value("theme", LIGHT)
        if hasattr(mw, '_apply_theme'):
            mw._apply_theme(new_theme)

        # Undo limit
        limit = int(self._settings.value("max_history", 200))
        for tab in mw._tabs:
            tab.undo_stack.setUndoLimit(limit)

        # Autosave interval (0 disables the timer)
        autosave_s = get_pref("autosave_interval_s", 180)
        if hasattr(mw, "_autosave_timer"):
            if autosave_s > 0:
                mw._autosave_timer.setInterval(max(autosave_s, 30) * 1000)
                if not mw._autosave_timer.isActive():
                    mw._autosave_timer.start()
            else:
                mw._autosave_timer.stop()

        # Hot-reload enabled/disabled — instant, both directions: turning it
        # back on must re-arm the watcher immediately, not just on next load.
        hot_reload = get_pref("hot_reload_enabled", True)
        if hasattr(mw, '_image_watcher'):
            if hot_reload:
                if hasattr(mw, '_sync_image_watcher'):
                    mw._sync_image_watcher()
            else:
                # Clearing files from the watcher effectively disables it
                files = mw._image_watcher.files()
                if files:
                    mw._image_watcher.removePaths(files)
