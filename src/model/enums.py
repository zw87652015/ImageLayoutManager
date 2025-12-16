from enum import Enum

class FitMode(Enum):
    CONTAIN = "contain"
    COVER = "cover"

class LabelPosition(Enum):
    TOP_LEFT = "top_left"
    TOP_RIGHT = "top_right"
    BOTTOM_LEFT = "bottom_left"
    BOTTOM_RIGHT = "bottom_right"
    # Outside margins could be handled by different coordinates or distinct enums if needed
    OUTSIDE_TOP_LEFT = "outside_top_left"

class PageSizePreset(Enum):
    A4 = ("A4", 210, 297)
    LETTER = ("Letter", 215.9, 279.4)
    JOURNAL_1_COL = ("Journal 1-Col (85mm)", 85, 297) # Height arbitrary? Usually max height
    JOURNAL_1_5_COL = ("Journal 1.5-Col (114mm)", 114, 297)
    JOURNAL_2_COL = ("Journal 2-Col (178mm)", 178, 297)

    def __init__(self, label, width_mm, height_mm):
        self.label = label
        self.width_mm = width_mm
        self.height_mm = height_mm
