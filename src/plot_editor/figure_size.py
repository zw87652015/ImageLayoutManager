"""Physical figure size for the Plot Editor (Qt-free).

``width_mm``/``height_mm`` are already part of the native document;
this value object just carries them as the tab's geometry state and
does the aspect-ratio arithmetic for the Figure Size dialog.
"""

from dataclasses import dataclass
import math

from ilmplot.document import MAX_DIMENSION_MM, PlotDocumentError
from .i18n import tr


@dataclass(frozen=True)
class FigureSize:
    width_mm: float = 90.0
    height_mm: float = 65.0

    def __post_init__(self):
        for value in (self.width_mm, self.height_mm):
            if (isinstance(value, bool)
                    or not isinstance(value, (int, float))
                    or not math.isfinite(value)
                    or not 0 < value <= MAX_DIMENSION_MM):
                raise PlotDocumentError(
                    tr('err_figure_size', maximum=MAX_DIMENSION_MM))

    @classmethod
    def from_document(cls, document):
        return cls(document.width_mm, document.height_mm)

    def resized(self, dimension, value, locked=False):
        if dimension not in ('width', 'height'):
            raise ValueError('unknown figure dimension')
        # Validate the requested value before arithmetic
        # (booleans/nonfinite too).
        FigureSize(value, value)
        if dimension == 'width':
            return FigureSize(value, self.height_mm * value
                              / self.width_mm if locked
                              else self.height_mm)
        return FigureSize(self.width_mm * value / self.height_mm
                          if locked else self.width_mm, value)

    def with_ratio(self, ratio):
        if (isinstance(ratio, bool)
                or not isinstance(ratio, (int, float))
                or not math.isfinite(ratio) or ratio <= 0):
            raise ValueError('aspect ratio must be finite and positive')
        width = self.width_mm
        height = width / ratio
        if height > MAX_DIMENSION_MM:
            height = float(MAX_DIMENSION_MM)
            width = height * ratio
        return FigureSize(width, height)

    def swapped(self):
        return FigureSize(self.height_mm, self.width_mm)
