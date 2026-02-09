from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsDropShadowEffect, QGraphicsView
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap
from PyQt6.QtCore import (QObject, QEvent, QTimer, QPointF, QRectF,
                          pyqtSignal, Qt, QVariantAnimation, QEasingCurve)


class DragManager(QObject):
    """Manages animated drag-and-drop of cells with spring physics.

    State machine: IDLE → DRAGGING → ANIMATING → IDLE
    - Ghost item follows mouse with spring-lag interpolation (~60 fps).
    - Drop target highlighted with translucent overlay.
    - On drop: ghost slides to target then swap is emitted.
    - On cancel (Escape / invalid target): ghost springs back to origin.
    - Supports multi-cell drag: N selected cells are moved together.
    """

    swap_requested = pyqtSignal(str, str)  # source_id, target_id (single)
    multi_swap_requested = pyqtSignal(list, list)  # source_ids, target_ids

    # Tuning constants
    SPRING_FACTOR = 0.18        # 0-1, ghost catch-up speed per tick
    GHOST_OPACITY = 0.82
    GHOST_SCALE = 1.05          # Slight lift enlargement
    GHOST_PX_WIDTH = 300        # Capture resolution
    HIGHLIGHT_FILL = QColor(0, 122, 204, 60)
    HIGHLIGHT_BORDER = QColor(0, 122, 204, 180)
    REJECT_FILL = QColor(204, 0, 0, 40)
    REJECT_BORDER = QColor(204, 0, 0, 140)
    TICK_MS = 16                # ~60 fps
    DROP_DURATION_MS = 180
    CANCEL_DURATION_MS = 250

    def __init__(self, scene):
        super().__init__(scene)
        self.scene = scene
        self._active = False
        self._animating = False  # True during drop/cancel animation

        # Source state (multi-cell aware)
        self._source_cell = None          # The cell under the mouse at drag start
        self._source_id = None
        self._source_scene_rect = QRectF()
        self._source_cells = []           # All dragged CellItems (sorted row-major)
        self._source_ids = []             # Their IDs

        # Ghost
        self._ghost = None          # QGraphicsPixmapItem
        self._ghost_scene_pos = QPointF()
        self._ghost_display_w = 0.0
        self._ghost_display_h = 0.0

        # Mouse
        self._mouse_scene_pos = QPointF()

        # Target highlight
        self._highlights = []       # list of QGraphicsRectItems
        self._target_ids = []

        # Spring timer
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._spring_tick)

        # Drop / cancel animation
        self._anim = None
        self._anim_start = QPointF()
        self._anim_end = QPointF()

        # View state saved during drag
        self._saved_drag_mode = None
        self._view = None  # reference to the view during drag

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_active(self):
        return self._active

    def start_drag(self, cell_item, scene_pos):
        """Begin a drag operation on *cell_item* (and all other selected cells)."""
        if self._active:
            return

        from src.canvas.cell_item import CellItem

        self._active = True
        self._animating = False
        self._source_cell = cell_item
        self._source_id = cell_item.cell_id
        self._mouse_scene_pos = scene_pos

        self._source_scene_rect = QRectF(
            cell_item.pos().x(), cell_item.pos().y(),
            cell_item.rect().width(), cell_item.rect().height(),
        )

        # Collect all selected non-label cells, sorted by position (row-major)
        selected = [
            i for i in self.scene.selectedItems()
            if isinstance(i, CellItem) and not i.is_label_cell
        ]
        if not selected or cell_item not in selected:
            selected = [cell_item]
        selected.sort(key=lambda i: (i.pos().y(), i.pos().x()))
        self._source_cells = selected
        self._source_ids = [i.cell_id for i in selected]

        # Create ghost BEFORE dimming sources (so capture is at full opacity)
        self._create_ghost(cell_item, scene_pos)

        # Dim all source cells
        for item in self._source_cells:
            item.setOpacity(0.3)

        # Release any implicit mouse grab the cell item may hold
        cell_item.ungrabMouse()

        # Install event filter on the viewport and disable rubber-band
        views = self.scene.views()
        if views:
            self._view = views[0]
            self._saved_drag_mode = self._view.dragMode()
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            vp = self._view.viewport()
            vp.setMouseTracking(True)
            vp.installEventFilter(self)
            self._view.setCursor(Qt.CursorShape.ClosedHandCursor)

        self._timer.start()

    # ------------------------------------------------------------------
    # Ghost creation
    # ------------------------------------------------------------------

    def _create_ghost(self, cell_item, scene_pos):
        cell_w = self._source_scene_rect.width()
        cell_h = self._source_scene_rect.height()
        if cell_w <= 0 or cell_h <= 0:
            return

        aspect = cell_h / cell_w
        cap_w = self.GHOST_PX_WIDTH
        cap_h = max(1, int(cap_w * aspect))

        pixmap = QPixmap(cap_w, cap_h)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.scene.render(
            painter,
            QRectF(0, 0, cap_w, cap_h),
            self._source_scene_rect,
        )
        painter.end()

        self._ghost = QGraphicsPixmapItem(pixmap)
        self._ghost.setZValue(1000)
        self._ghost.setOpacity(self.GHOST_OPACITY)

        # Scale so the ghost matches cell size * GHOST_SCALE
        base_scale = cell_w / cap_w
        self._ghost.setScale(base_scale * self.GHOST_SCALE)

        self._ghost_display_w = cell_w * self.GHOST_SCALE
        self._ghost_display_h = cell_h * self.GHOST_SCALE

        # Centre on mouse
        self._ghost_scene_pos = QPointF(
            scene_pos.x() - self._ghost_display_w / 2,
            scene_pos.y() - self._ghost_display_h / 2,
        )
        self._ghost.setPos(self._ghost_scene_pos)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(3, 3)
        self._ghost.setGraphicsEffect(shadow)

        self.scene.addItem(self._ghost)

    # ------------------------------------------------------------------
    # Spring physics (timer-driven)
    # ------------------------------------------------------------------

    def _spring_tick(self):
        if not self._ghost or not self._active or self._animating:
            return

        target = QPointF(
            self._mouse_scene_pos.x() - self._ghost_display_w / 2,
            self._mouse_scene_pos.y() - self._ghost_display_h / 2,
        )

        dx = (target.x() - self._ghost_scene_pos.x()) * self.SPRING_FACTOR
        dy = (target.y() - self._ghost_scene_pos.y()) * self.SPRING_FACTOR

        self._ghost_scene_pos = QPointF(
            self._ghost_scene_pos.x() + dx,
            self._ghost_scene_pos.y() + dy,
        )
        self._ghost.setPos(self._ghost_scene_pos)

    # ------------------------------------------------------------------
    # Target detection & highlighting
    # ------------------------------------------------------------------

    def _get_all_cells_sorted(self):
        """Return all non-label CellItems sorted in row-major order."""
        from src.canvas.cell_item import CellItem
        items = [i for i in self.scene.cell_items.values() if not i.is_label_cell]
        items.sort(key=lambda i: (i.pos().y(), i.pos().x()))
        return items

    def _find_target_cell(self, scene_pos):
        """Find the single cell under the cursor (not one of the sources)."""
        from src.canvas.cell_item import CellItem
        for item in self.scene.items(scene_pos):
            if (isinstance(item, CellItem)
                    and not item.is_label_cell
                    and item.cell_id not in self._source_ids):
                return item
        return None

    def _find_target_cells(self, scene_pos):
        """Find N consecutive target cells starting from the cell under cursor.
        Returns (target_items, valid) where valid=True if placement is possible."""
        n = len(self._source_ids)
        anchor = self._find_target_cell(scene_pos)
        if not anchor:
            return [], False

        if n == 1:
            return [anchor], True

        all_cells = self._get_all_cells_sorted()
        id_to_idx = {i.cell_id: idx for idx, i in enumerate(all_cells)}
        anchor_idx = id_to_idx.get(anchor.cell_id)
        if anchor_idx is None:
            return [], False

        # Try to place N cells starting at anchor_idx
        targets = []
        for offset in range(n):
            idx = anchor_idx + offset
            if idx >= len(all_cells):
                return [anchor], False  # Not enough room
            candidate = all_cells[idx]
            targets.append(candidate)

        # Check none of the targets overlap with sources
        target_ids = {t.cell_id for t in targets}
        source_ids = set(self._source_ids)
        if target_ids & source_ids:
            # Overlap is OK only if the sets are identical (drop on self = cancel)
            if target_ids != source_ids:
                return targets, False
            return [], False  # Dropped on self

        return targets, True

    def _update_highlights(self, targets, valid):
        """Show highlight rectangles on target cells. Blue=valid, Red=invalid."""
        new_ids = [t.cell_id for t in targets]
        if new_ids == self._target_ids:
            return
        self._target_ids = new_ids

        # Remove old highlights
        for h in self._highlights:
            self.scene.removeItem(h)
        self._highlights.clear()

        fill = self.HIGHLIGHT_FILL if valid else self.REJECT_FILL
        border = self.HIGHLIGHT_BORDER if valid else self.REJECT_BORDER

        for t in targets:
            h = QGraphicsRectItem(t.rect())
            h.setPos(t.pos())
            h.setZValue(999)
            h.setBrush(QBrush(fill))
            pen = QPen(border, 2)
            pen.setCosmetic(True)
            h.setPen(pen)
            self.scene.addItem(h)
            self._highlights.append(h)

    # ------------------------------------------------------------------
    # Mouse event handlers (called via eventFilter)
    # ------------------------------------------------------------------

    def _on_mouse_move(self, scene_pos):
        self._mouse_scene_pos = scene_pos
        targets, valid = self._find_target_cells(scene_pos)
        if targets:
            self._update_highlights(targets, valid)
        else:
            # Clear highlights when not over any cell
            self._update_highlights([], True)

    def _on_mouse_release(self, scene_pos):
        self._timer.stop()
        self._animating = True

        # Remove highlights immediately
        for h in self._highlights:
            self.scene.removeItem(h)
        self._highlights.clear()
        self._target_ids = []

        targets, valid = self._find_target_cells(scene_pos)
        if valid and targets:
            self._animate_drop(targets[0])
        else:
            self._animate_cancel()

    # ------------------------------------------------------------------
    # Drop / cancel animations (QVariantAnimation on QPointF)
    # ------------------------------------------------------------------

    def _animate_drop(self, first_target_cell):
        self._anim_start = QPointF(self._ghost_scene_pos)
        self._anim_end = QPointF(first_target_cell.pos().x(), first_target_cell.pos().y())

        # Compute target IDs for the drop
        n = len(self._source_ids)
        source_ids = list(self._source_ids)
        if n == 1:
            target_ids = [first_target_cell.cell_id]
        else:
            all_cells = self._get_all_cells_sorted()
            id_to_idx = {i.cell_id: idx for idx, i in enumerate(all_cells)}
            anchor_idx = id_to_idx.get(first_target_cell.cell_id, 0)
            target_ids = [all_cells[anchor_idx + i].cell_id for i in range(n)]

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self.DROP_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(lambda: self._on_drop_finished(source_ids, target_ids))
        self._anim.start()

    def _animate_cancel(self):
        self._anim_start = QPointF(self._ghost_scene_pos)
        self._anim_end = QPointF(self._source_scene_rect.x(), self._source_scene_rect.y())

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self.CANCEL_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._cleanup)
        self._anim.start()

    def _on_anim_value(self, t):
        if self._ghost:
            x = self._anim_start.x() + (self._anim_end.x() - self._anim_start.x()) * t
            y = self._anim_start.y() + (self._anim_end.y() - self._anim_start.y()) * t
            self._ghost.setPos(x, y)

    def _on_drop_finished(self, source_ids, target_ids):
        self._cleanup()
        if len(source_ids) == 1 and len(target_ids) == 1:
            self.swap_requested.emit(source_ids[0], target_ids[0])
        else:
            self.multi_swap_requested.emit(source_ids, target_ids)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self):
        self._timer.stop()

        if self._anim:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None

        if self._ghost:
            self.scene.removeItem(self._ghost)
            self._ghost = None

        for h in self._highlights:
            self.scene.removeItem(h)
        self._highlights.clear()

        # Restore opacity on all source cells
        for item in self._source_cells:
            try:
                item.setOpacity(1.0)
            except RuntimeError:
                pass  # item was deleted

        if self._view:
            vp = self._view.viewport()
            vp.removeEventFilter(self)
            self._view.unsetCursor()
            if self._saved_drag_mode is not None:
                self._view.setDragMode(self._saved_drag_mode)
                self._saved_drag_mode = None
            self._view = None

        self._active = False
        self._animating = False
        self._source_cell = None
        self._source_id = None
        self._source_cells = []
        self._source_ids = []
        self._target_ids = []
        self._ghost_scene_pos = QPointF()
        self._mouse_scene_pos = QPointF()

    # ------------------------------------------------------------------
    # Event filter (installed on the QGraphicsView during drag)
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if not self._active:
            return False

        etype = event.type()

        # During animation, consume mouse events to prevent interference
        if self._animating:
            if etype in (QEvent.Type.MouseMove,
                         QEvent.Type.MouseButtonPress,
                         QEvent.Type.MouseButtonRelease):
                return True
            return False

        if etype == QEvent.Type.MouseMove:
            if self._view:
                scene_pos = self._view.mapToScene(event.position().toPoint())
                self._on_mouse_move(scene_pos)
            return True

        if etype == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if self._view:
                    scene_pos = self._view.mapToScene(event.position().toPoint())
                    self._on_mouse_release(scene_pos)
                return True

        if etype == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._timer.stop()
                self._animating = True
                for h in self._highlights:
                    self.scene.removeItem(h)
                self._highlights.clear()
                self._target_ids = []
                self._animate_cancel()
                return True

        return False
