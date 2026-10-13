"""Section heading helper shared by the SVG and raster Match Text Size windows."""

from PyQt6.QtWidgets import QLabel
from PyQt6.QtGui import QFont


def section_label(text: str) -> QLabel:
    lbl = QLabel(text)
    f = lbl.font()
    f.setWeight(QFont.Weight.Medium)
    lbl.setFont(f)
    return lbl
