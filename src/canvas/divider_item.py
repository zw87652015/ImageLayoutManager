from PyQt6.QtWidgets import QGraphicsRectItem, QGraphicsItem
from PyQt6.QtGui import QColor, QPen, QBrush, QPainter
from PyQt6.QtCore import Qt, QRectF, QPointF


# Hit-test thickness (mm) – invisible grab zone centred on the gap
HIT_THICKNESS = 4.0
# Visual highlight thickness when hovered/dragging
VIS_THICKNESS = 1.5


class DividerItem(QGraphicsRectItem):
    """An invisible drag handle placed in the gap between rows or columns.

    Orientation:
      'row'  – horizontal divider between two rows; dragging changes height_ratio.
      'col'  – vertical divider between two columns in a row; dragging changes column_ratios.

    The item sits at Z=600 so it is always on top of cells.
    When the user starts dragging it notifies the scene via
      scene.divider_drag_finished(kind, row_a, row_b, col_a, col_b, new_ratio_a, new_ratio_b)
    """

    def __init__(self, kind: str,
                 row_a: int = -1, row_b: int = -1,
                 col_a: int = -1, col_b: int = -1,
                 ratio_a: float = 1.0, ratio_b: float = 1.0,
                 row_index: int = -1,
                 parent=None):
        super().__init__(parent)
        self.kind = kind          # 'row' | 'col'
        self.row_a = row_a        # index of the row above  (row divider)
        self.row_b = row_b        # index of the row below  (row divider)
        self.col_a = col_a        # col_index of left cell  (col divider)
        self.col_b = col_b        # col_index of right cell (col divider)
        self.row_index = row_index  # which row this col divider belongs to
        self.ratio_a = ratio_a
        self.ratio_b = ratio_b

        self._hovered = False
        self._dragging = False
        self._drag_start_scene = QPointF()
        self._drag_start_ratio_a = ratio_a
        self._drag_start_ratio_b = ratio_b
        # Original ratios before the drag started (for undo)
        self.original_ratio_a = ratio_a
        self.original_ratio_b = ratio_b

        self.setZValue(600)
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)

        cursor = (Qt.CursorShape.SizeVerCursor if kind == 'row'
                  else Qt.CursorShape.SizeHorCursor)
        self.setCursor(cursor)
        self.setPen(QPen(Qt.PenStyle.NoPen))
        self.setBrush(QBrush(Qt.BrushStyle.NoBrush))

    # ------------------------------------------------------------------
    # Paint – only visible when hovered or dragging
    # ------------------------------------------------------------------

    def paint(self, painter: QPainter, option, widget=None):
        if not (self._hovered or self._dragging):
            return
        r = self.rect()
        color = QColor(0, 122, 204, 180)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setBrush(QBrush(color))
        painter.setPen(QPen(Qt.PenStyle.NoPen))
        if self.kind == 'row':
            cx = r.center().x()
            cy = r.center().y()
            vis_r = QRectF(r.left(), cy - VIS_THICKNESS / 2,
                           r.width(), VIS_THICKNESS)
        else:
            cx = r.center().x()
            cy = r.center().y()
            vis_r = QRectF(cx - VIS_THICKNESS / 2, r.top(),
                           VIS_THICKNESS, r.height())
        painter.drawRect(vis_r)

    # ------------------------------------------------------------------
    # Hover
    # ------------------------------------------------------------------

    def hoverEnterEvent(self, event):
        self._hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    # ------------------------------------------------------------------
    # Drag
    # ------------------------------------------------------------------

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_scene = event.scenePos()
            self._drag_start_ratio_a = self.ratio_a
            self._drag_start_ratio_b = self.ratio_b
            self.original_ratio_a = self.ratio_a
            self.original_ratio_b = self.ratio_b
            self.update()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if not self._dragging:
            super().mouseMoveEvent(event)
            return

        scene = self.scene()
        if scene is None:
            return

        delta_scene = event.scenePos() - self._drag_start_scene
        total_ratio = self._drag_start_ratio_a + self._drag_start_ratio_b
        if total_ratio <= 0:
            return

        if self.kind == 'row':
            # Map scene delta (mm) to ratio change
            # Total pixel span of the two rows = total_ratio / sum_all_ratios * available_height
            total_mm = self._get_total_span_mm(scene)
            if total_mm <= 0:
                return
            delta_ratio = (delta_scene.y() / total_mm) * total_ratio
            new_a = max(0.05, self._drag_start_ratio_a + delta_ratio)
            new_b = max(0.05, total_ratio - new_a)
            new_a = total_ratio - new_b  # clamp both
        else:
            total_mm = self._get_total_span_mm(scene)
            if total_mm <= 0:
                return
            delta_ratio = (delta_scene.x() / total_mm) * total_ratio
            new_a = max(0.05, self._drag_start_ratio_a + delta_ratio)
            new_b = max(0.05, total_ratio - new_a)
            new_a = total_ratio - new_b

        self.ratio_a = new_a
        self.ratio_b = new_b

        # Live-update the model and refresh canvas for interactive feel
        if hasattr(scene, '_divider_live_update'):
            scene._divider_live_update(self)

        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self._dragging:
            self._dragging = False
            self.update()
            scene = self.scene()
            if scene and hasattr(scene, '_divider_drag_finished'):
                scene._divider_drag_finished(self)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _get_total_span_mm(self, scene) -> float:
        """Return the combined mm span of the two adjacent rows/cols."""
        project = getattr(scene, 'project', None)
        if project is None:
            return 0.0

        if self.kind == 'row':
            last_result = getattr(scene, '_last_layout_result', None)
            if last_result is None:
                return 0.0
            ha = last_result.row_heights.get(self.row_a, 0.0)
            hb = last_result.row_heights.get(self.row_b, 0.0)
            return ha + hb
        else:
            # Sum of the two adjacent column widths in this row
            row_temp = next((r for r in project.rows if r.index == self.row_index), None)
            if row_temp is None:
                return 0.0
            from src.model.layout_engine import LayoutEngine
            content_width = (project.page_width_mm
                             - project.margin_left_mm
                             - project.margin_right_mm)
            col_widths = LayoutEngine._compute_col_widths(row_temp, content_width, project.gap_mm)
            wa = col_widths[self.col_a] if self.col_a < len(col_widths) else 0.0
            wb = col_widths[self.col_b] if self.col_b < len(col_widths) else 0.0
            return wa + wb
