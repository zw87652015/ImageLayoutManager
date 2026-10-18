"""Save Copy for Older ILM — choose a target schema, preview what will
be left out, then pick a destination. Writing the copy is handled by
the caller; this dialog only reports the selection and the dry-run
issues for the currently selected target."""

from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QLabel, QVBoxLayout, QWidget,
)

from src.app.i18n import tr
from src.model.downgrade import DOWNGRADE_TARGETS, downgrade_project_data


def issue_text(code: str, count: int) -> str:
    """Localized one-line description of a downgrade issue."""
    key = f"save_older_issue_{code}"
    text = tr(key)
    if text == key:
        text = f"{code}: {{n}}"
    return text.format(n=count)


def issue_lines(issues: List[Tuple[str, int]]) -> List[str]:
    return [issue_text(code, count) for code, count in issues if count > 0]


class SaveOlderDialog(QDialog):
    """Target picker + live left-out preview for a downgraded copy."""

    def __init__(self, project, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._project = project
        self._issues: List[Tuple[str, int]] = []
        self.setWindowTitle(tr("save_older_title"))
        self.setModal(True)

        layout = QVBoxLayout(self)

        row = QWidget(self)
        row_layout = QVBoxLayout(row)
        row_layout.setContentsMargins(0, 0, 0, 0)
        row_layout.addWidget(QLabel(tr("save_older_target"), row))
        self._combo = QComboBox(row)
        for schema, label in DOWNGRADE_TARGETS:
            self._combo.addItem(f"ILM {label}", schema)
        self._combo.currentIndexChanged.connect(self._refresh_issues)
        row_layout.addWidget(self._combo)
        layout.addWidget(row)

        layout.addWidget(QLabel(tr("save_older_what"), self))
        self._issues_label = QLabel(self)
        self._issues_label.setWordWrap(True)
        self._issues_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        layout.addWidget(self._issues_label)

        note = QLabel(tr("save_older_note"), self)
        note.setWordWrap(True)
        layout.addWidget(note)

        buttons = QDialogButtonBox(self)
        self._save_btn = buttons.addButton(
            tr("save_older_save"), QDialogButtonBox.ButtonRole.AcceptRole
        )
        buttons.addButton(
            tr("btn_cancel"), QDialogButtonBox.ButtonRole.RejectRole
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self._refresh_issues()

    def _refresh_issues(self) -> None:
        try:
            _data, self._issues = downgrade_project_data(
                self._project.to_dict(), self.selected_schema()
            )
        except Exception as e:  # defensive: keep the dialog usable
            self._issues = [("__error__", 1)]
            self._issues_label.setText(str(e))
            return
        lines = issue_lines(self._issues)
        self._issues_label.setText(
            "\n".join(lines) if lines else tr("save_older_none")
        )

    def selected_schema(self) -> int:
        return self._combo.currentData()

    def selected_label(self) -> str:
        idx = self._combo.currentIndex()
        return DOWNGRADE_TARGETS[idx][1]

    def issues(self) -> List[Tuple[str, int]]:
        return list(self._issues)
