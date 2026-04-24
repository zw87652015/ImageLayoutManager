"""Dialog for choosing a CMYK ICC profile and rendering intent before a TIFF export."""
from __future__ import annotations

import os
from typing import Optional, List, Tuple

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QComboBox, QLabel, QPushButton, QFileDialog, QDialogButtonBox,
    QCheckBox, QLineEdit, QMessageBox,
)
from PyQt6.QtCore import Qt


# Human-friendly rendering-intent labels mapped to Pillow's ImageCms enum ints.
# We keep the enum values numeric so we don't import Pillow at UI-construction time.
_INTENTS: List[Tuple[str, int]] = [
    ("Relative Colorimetric (default)", 1),
    ("Perceptual (photos, smooth gradation)", 0),
    ("Saturation (charts, solid colours)", 2),
    ("Absolute Colorimetric (proofing)", 3),
]


def _profile_color_space(path: str) -> str:
    """Return the ICC profile's colour space (e.g. 'RGB', 'CMYK'), or '' on error."""
    try:
        from PIL import ImageCms
        prof = ImageCms.getOpenProfile(path)
        cs = prof.profile.xcolor_space
        return (cs or "").strip().upper()
    except Exception:
        return ""


def _discover_system_profiles(cmyk_only: bool = True) -> List[str]:
    """Return absolute paths to ICC profiles installed on the system.

    When ``cmyk_only`` is True, only profiles whose colour space reports CMYK
    are returned — invalid destinations (monitors, scanners, printers linked to
    RGB) are filtered out so users can't accidentally pick them.
    """
    candidate_dirs: List[str] = []
    win_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                           "System32", "spool", "drivers", "color")
    if os.path.isdir(win_dir):
        candidate_dirs.append(win_dir)
    for d in ("/System/Library/ColorSync/Profiles",
              "/Library/ColorSync/Profiles",
              os.path.expanduser("~/Library/ColorSync/Profiles")):
        if os.path.isdir(d):
            candidate_dirs.append(d)

    paths: List[str] = []
    for d in candidate_dirs:
        for name in sorted(os.listdir(d)):
            if not name.lower().endswith((".icc", ".icm")):
                continue
            full = os.path.join(d, name)
            if cmyk_only and _profile_color_space(full) != "CMYK":
                continue
            paths.append(full)
    return paths


def _describe_profile(path: str) -> str:
    """Return human description of an ICC profile, or the filename if unavailable."""
    try:
        from PIL import ImageCms
        p = ImageCms.getOpenProfile(path)
        desc = ImageCms.getProfileDescription(p).strip()
        if desc:
            cs = _profile_color_space(path)
            return f"{desc}  [{cs}]" if cs else desc
    except Exception:
        pass
    return os.path.basename(path)


class CmykIccDialog(QDialog):
    """Lets the user pick a CMYK ICC profile + rendering intent for TIFF export."""

    def __init__(self, parent=None, current_path: Optional[str] = None,
                 current_intent: int = 1):
        super().__init__(parent)
        self.setWindowTitle("CMYK Colour Management")
        self.setMinimumWidth(520)

        self._selected_path: Optional[str] = None
        self._selected_intent: int = current_intent

        layout = QVBoxLayout(self)

        intro = QLabel(
            "Choose the CMYK ICC profile and rendering intent for this "
            "TIFF export.\n"
            "The profile will be embedded in the output file."
        )
        intro.setWordWrap(True)
        layout.addWidget(intro)

        form = QFormLayout()

        # Profile dropdown — system scan restricted to CMYK-colour-space profiles.
        self.profile_combo = QComboBox()
        profiles = _discover_system_profiles(cmyk_only=True)
        self._profile_paths: List[Optional[str]] = []
        if not profiles:
            # Visible notice instead of a silent empty list.
            self.profile_combo.addItem("(no CMYK profile found on this system)")
            self._profile_paths.append("__none__")
        for path in profiles:
            self.profile_combo.addItem(_describe_profile(path))
            self._profile_paths.append(path)
        self.profile_combo.addItem("Custom file…")
        self._profile_paths.append(None)  # marker for custom
        self.profile_combo.addItem("No profile (naive conversion, not recommended)")
        self._profile_paths.append("__none__")
        self.profile_combo.currentIndexChanged.connect(self._on_profile_changed)
        form.addRow("ICC Profile:", self.profile_combo)

        # Custom path (shown only when Custom file… selected)
        path_row = QHBoxLayout()
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path to .icc / .icm file")
        self.browse_btn = QPushButton("Browse…")
        self.browse_btn.clicked.connect(self._browse)
        path_row.addWidget(self.path_edit, 1)
        path_row.addWidget(self.browse_btn)
        self.path_row_label = QLabel("Custom Path:")
        form.addRow(self.path_row_label, path_row)

        # Rendering intent
        self.intent_combo = QComboBox()
        for text, _val in _INTENTS:
            self.intent_combo.addItem(text)
        form.addRow("Rendering Intent:", self.intent_combo)

        # Remember-checkbox
        self.remember = QCheckBox("Remember this profile for future exports")
        self.remember.setChecked(True)
        layout.addLayout(form)
        layout.addWidget(self.remember)

        # Description label
        self.desc_label = QLabel("")
        self.desc_label.setStyleSheet("color: gray; font-style: italic;")
        self.desc_label.setWordWrap(True)
        layout.addWidget(self.desc_label)

        # Buttons
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Initialise selection: match current_path if provided.
        initial_idx = 0
        if current_path and current_path in profiles:
            initial_idx = profiles.index(current_path)
        elif current_path and os.path.isfile(current_path):
            # Custom: put path into the edit and select Custom row
            self.path_edit.setText(current_path)
            initial_idx = len(profiles)  # points at "Custom file…"
        self.profile_combo.setCurrentIndex(initial_idx)
        # Intent index
        for i, (_t, v) in enumerate(_INTENTS):
            if v == current_intent:
                self.intent_combo.setCurrentIndex(i)
                break
        self._on_profile_changed(self.profile_combo.currentIndex())

    # ------------------------------------------------------------------
    def _on_profile_changed(self, idx: int):
        marker = self._profile_paths[idx]
        is_custom = marker is None
        self.path_edit.setVisible(is_custom)
        self.browse_btn.setVisible(is_custom)
        self.path_row_label.setVisible(is_custom)
        # Description
        if marker is None:
            self.desc_label.setText("Provide a path to any CMYK ICC profile.")
        elif marker == "__none__":
            self.desc_label.setText(
                "Output will be converted with Pillow's built-in CMYK conversion. "
                "Colours will not be colour-accurate for print."
            )
        else:
            self.desc_label.setText(f"Using {os.path.basename(marker)}")

    def _browse(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose ICC Profile", os.path.dirname(self.path_edit.text() or ""),
            "ICC Profiles (*.icc *.icm);;All Files (*)",
        )
        if path:
            self.path_edit.setText(path)

    def _accept(self):
        idx = self.profile_combo.currentIndex()
        marker = self._profile_paths[idx]
        if marker is None:
            candidate = self.path_edit.text().strip()
            if not candidate or not os.path.isfile(candidate):
                QMessageBox.warning(
                    self, "Invalid Profile",
                    "Please pick a valid .icc / .icm file, or choose another option.",
                )
                return
            cs = _profile_color_space(candidate)
            if cs and cs != "CMYK":
                QMessageBox.warning(
                    self, "Not a CMYK Profile",
                    f"The selected profile is a {cs} profile, not CMYK.\n\n"
                    "CMYK ICC profiles have names like 'Coated FOGRA39', "
                    "'US Web Coated SWOP', or 'Japan Color 2001 Coated'. "
                    "You can download free ones from https://www.color.org/ or "
                    "https://www.eci.org/.",
                )
                return
            self._selected_path = candidate
        elif marker == "__none__":
            self._selected_path = None
        else:
            self._selected_path = marker
        self._selected_intent = _INTENTS[self.intent_combo.currentIndex()][1]
        self.accept()

    # ------------------------------------------------------------------
    def selected_profile_path(self) -> Optional[str]:
        """None means the user chose naive (non-managed) conversion."""
        return self._selected_path

    def selected_intent(self) -> int:
        return self._selected_intent

    def remember_choice(self) -> bool:
        return self.remember.isChecked()
