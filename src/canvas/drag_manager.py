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
    """

    swap_requested = pyqtSignal(str, str)  # source_id, target_id

    # Tuning constants
    SPRING_FACTOR = 0.18        # 0-1, ghost catch-up speed per tick
    GHOST_OPACITY = 0.82
    GHOST_SCALE = 1.05          # Slight lift enlargement
    GHOST_PX_WIDTH = 300        # Capture resolution
    HIGHLIGHT_FILL = QColor(0, 122, 204, 60)
    HIGHLIGHT_BORDER = QColor(0, 122, 204, 180)
    TICK_MS = 16                # ~60 fps
    DROP_DURATION_MS = 180
    CANCEL_DURATION_MS = 250

    def __init__(self, scene):
        super().__init__(scene)
        self.scene = scene
        self._active = False
        self._animating = False  # True during drop/cancel animation

        # Source state
        self._source_cell = None
        self._source_id = None
        self._source_scene_rect = QRectF()

        # Ghost
        self._ghost = None          # QGraphicsPixmapItem
        self._ghost_scene_pos = QPointF()
        self._ghost_display_w = 0.0
        self._ghost_display_h = 0.0

        # Mouse
        self._mouse_scene_pos = QPointF()

        # Target highlight
        self._highlight = None      # QGraphicsRectItem
        self._target_id = None

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
        """Begin a drag operation on *cell_item*."""
        if self._active:
            return

        self._active = True
        self._animating = False
        self._source_cell = cell_item
        self._source_id = cell_item.cell_id
        self._mouse_scene_pos = scene_pos

        self._source_scene_rect = QRectF(
            cell_item.pos().x(), cell_item.pos().y(),
            cell_item.rect().width(), cell_item.rect().height(),
        )

        # Create ghost BEFORE dimming source (so capture is at full opacity)
        self._create_ghost(cell_item, scene_pos)

        # Dim the source cell
        cell_item.setOpacity(0.3)

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

    def _find_target_cell(self, scene_pos):
        from src.canvas.cell_item import CellItem

        for item in self.scene.items(scene_pos):
            if (isinstance(item, CellItem)
                    and not item.is_label_cell
                    and item.cell_id != self._source_id):
                return item
        return None

    def _update_highlight(self, target_cell):
        new_id = target_cell.cell_id if target_cell else None
        if new_id == self._target_id:
            return
        self._target_id = new_id

        if self._highlight:
            self.scene.removeItem(self._highlight)
            self._highlight = None

        if target_cell:
            self._highlight = QGraphicsRectItem(target_cell.rect())
            self._highlight.setPos(target_cell.pos())
            self._highlight.setZValue(999)
            self._highlight.setBrush(QBrush(self.HIGHLIGHT_FILL))
            pen = QPen(self.HIGHLIGHT_BORDER, 2)
            pen.setCosmetic(True)
            self._highlight.setPen(pen)
            self.scene.addItem(self._highlight)

    # ------------------------------------------------------------------
    # Mouse event handlers (called via eventFilter)
    # ------------------------------------------------------------------

    def _on_mouse_move(self, scene_pos):
        self._mouse_scene_pos = scene_pos
        target = self._find_target_cell(scene_pos)
        self._update_highlight(target)

    def _on_mouse_release(self, scene_pos):
        self._timer.stop()
        self._animating = True

        # Remove highlight immediately
        if self._highlight:
            self.scene.removeItem(self._highlight)
            self._highlight = None
            self._target_id = None

        target = self._find_target_cell(scene_pos)
        if target and target.cell_id != self._source_id:
            self._animate_drop(target)
        else:
            self._animate_cancel()

    # ------------------------------------------------------------------
    # Drop / cancel animations (QVariantAnimation on QPointF)
    # ------------------------------------------------------------------

    def _animate_drop(self, target_cell):
        self._anim_start = QPointF(self._ghost_scene_pos)
        self._anim_end = QPointF(target_cell.pos().x(), target_cell.pos().y())
        source_id = self._source_id
        target_id = target_cell.cell_id

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self.DROP_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(lambda: self._on_drop_finished(source_id, target_id))
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

    def _on_drop_finished(self, source_id, target_id):
        self._cleanup()
        self.swap_requested.emit(source_id, target_id)

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

        if self._highlight:
            self.scene.removeItem(self._highlight)
            self._highlight = None

        if self._source_cell:
            try:
                self._source_cell.setOpacity(1.0)
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
        self._target_id = None
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
                if self._highlight:
                    self.scene.removeItem(self._highlight)
                    self._highlight = None
                    self._target_id = None
                self._animate_cancel()
                return True

        return False
