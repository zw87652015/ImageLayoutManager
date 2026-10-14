"""Chooser shown before the first save of a project: .figlayout or .figpack."""
from __future__ import annotations

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QRadioButton, QButtonGroup,
    QFrame, QDialogButtonBox,
)
from PyQt6.QtCore import QEvent

from src.app.i18n import tr


class SaveFormatDialog(QDialog):
    """Two selectable cards explaining the project formats; .figlayout is the default."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("saveFormatDialog")
        self.setWindowTitle(tr("save_fmt_title"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)

        intro = QLabel(tr("save_fmt_intro"))
        intro.setObjectName("saveFmtIntro")
        intro.setWordWrap(True)
        layout.addWidget(intro)

        cards_row = QHBoxLayout()
        self._group = QButtonGroup(self)
        self._cards = []
        self._add_card(cards_row, ".figlayout", "save_fmt_layout_title", "save_fmt_layout_points")
        self._add_card(cards_row, ".figpack", "save_fmt_pack_title", "save_fmt_pack_points")
        layout.addLayout(cards_row)

        self._cards[0][1].setChecked(True)
        self._refresh_selection()

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        ok = buttons.button(QDialogButtonBox.StandardButton.Ok)
        ok.setText(tr("save_fmt_continue"))
        ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_card(self, row: QHBoxLayout, ext: str, title_key: str, points_key: str) -> None:
        frame = QFrame()
        frame.setObjectName("saveFmtCard")
        card = QVBoxLayout(frame)
        card.setContentsMargins(14, 12, 14, 12)
        card.setSpacing(8)

        radio = QRadioButton(tr(title_key))
        radio.setObjectName("saveFmtCardTitle")
        self._group.addButton(radio)
        radio.toggled.connect(self._refresh_selection)
        card.addWidget(radio)

        children = [radio]
        for line in tr(points_key).split("\n"):
            point = QLabel("• " + line)
            point.setObjectName("saveFmtPoint")
            point.setWordWrap(True)
            card.addWidget(point)
            children.append(point)

        for widget in [frame] + children:
            widget.installEventFilter(self)
        row.addWidget(frame, 1)
        self._cards.append((frame, radio, ext))

    def eventFilter(self, obj, event):
        for frame, radio, _ext in self._cards:
            if obj is frame or frame.isAncestorOf(obj):
                if event.type() == QEvent.Type.MouseButtonPress:
                    radio.setChecked(True)
                elif event.type() == QEvent.Type.MouseButtonDblClick:
                    radio.setChecked(True)
                    self.accept()
                break
        return super().eventFilter(obj, event)

    def _refresh_selection(self) -> None:
        for frame, radio, _ext in self._cards:
            frame.setProperty("selected", "true" if radio.isChecked() else "false")
            frame.style().unpolish(frame)
            frame.style().polish(frame)

    def selected_extension(self) -> str:
        for _frame, radio, ext in self._cards:
            if radio.isChecked():
                return ext
        return ".figlayout"
