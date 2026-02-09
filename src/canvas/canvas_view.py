from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, pyqtSignal, QPointF
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent


class CanvasView(QGraphicsView):
    zoom_changed = pyqtSignal(float)
    mouse_scene_pos_changed = pyqtSignal(float, float)  # x_mm, y_mm
    navigate_cell = pyqtSignal(str)       # direction: "up"/"down"/"left"/"right"/"next"/"prev"
    swap_cell = pyqtSignal(str)           # direction: "up"/"down"/"left"/"right"

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        
        # Rendering hints for quality
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        
        # Interaction
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        
        # Scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        # Zoom state
        self._zoom_level = 1.0

        # Space-drag pan state
        self._space_held = False
        self._pre_space_drag_mode = None

        # Mouse tracking for status bar coordinates
        self.setMouseTracking(True)

    # ------------------------------------------------------------------
    # Zoom helpers
    # ------------------------------------------------------------------

    def zoom_to_fit(self):
        """Fit entire page in view."""
        scene = self.scene()
        if not scene:
            return
        page_rect = getattr(scene, 'page_rect', scene.sceneRect())
        self.fitInView(page_rect, Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom_level = self.transform().m11()
        self.zoom_changed.emit(self._zoom_level)

    def zoom_to_100(self):
        """Reset zoom to 100%."""
        self.resetTransform()
        self._zoom_level = 1.0
        self.zoom_changed.emit(self._zoom_level)

    def _apply_zoom(self, factor):
        self.scale(factor, factor)
        self._zoom_level *= factor
        self.zoom_changed.emit(self._zoom_level)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            angle = event.angleDelta().y()
            factor = 1.1 if angle > 0 else 0.9
            self._apply_zoom(factor)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or self._space_held:
            # Pan via middle-button or Space+drag
            self._pre_space_drag_mode = self.dragMode()
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            synthetic_event = QMouseEvent(
                event.type(),
                event.position(),
                event.globalPosition(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.LeftButton,
                event.modifiers()
            )
            super().mousePressEvent(synthetic_event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Emit scene coordinates for status bar
        scene_pos = self.mapToScene(event.position().toPoint())
        self.mouse_scene_pos_changed.emit(scene_pos.x(), scene_pos.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton or (self._space_held and event.button() == Qt.MouseButton.LeftButton):
            synthetic_event = QMouseEvent(
                event.type(),
                event.position(),
                event.globalPosition(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                event.modifiers()
            )
            super().mouseReleaseEvent(synthetic_event)
            mode = self._pre_space_drag_mode if self._pre_space_drag_mode is not None else QGraphicsView.DragMode.RubberBandDrag
            self.setDragMode(mode)
            self._pre_space_drag_mode = None
        else:
            super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent):
        key = event.key()
        mod = event.modifiers()

        # Space+drag pan
        if key == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return

        # Zoom shortcuts
        if mod & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_0:
                self.zoom_to_fit()
                event.accept()
                return
            if key == Qt.Key.Key_1:
                self.zoom_to_100()
                event.accept()
                return
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self._apply_zoom(1.2)
                event.accept()
                return
            if key == Qt.Key.Key_Minus:
                self._apply_zoom(1 / 1.2)
                event.accept()
                return

        # Cell navigation (arrow keys)
        if key == Qt.Key.Key_Up:
            if mod & Qt.KeyboardModifier.ControlModifier:
                self.swap_cell.emit("up")
            else:
                self.navigate_cell.emit("up")
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            if mod & Qt.KeyboardModifier.ControlModifier:
                self.swap_cell.emit("down")
            else:
                self.navigate_cell.emit("down")
            event.accept()
            return
        if key == Qt.Key.Key_Left:
            if mod & Qt.KeyboardModifier.ControlModifier:
                self.swap_cell.emit("left")
            else:
                self.navigate_cell.emit("left")
            event.accept()
            return
        if key == Qt.Key.Key_Right:
            if mod & Qt.KeyboardModifier.ControlModifier:
                self.swap_cell.emit("right")
            else:
                self.navigate_cell.emit("right")
            event.accept()
            return

        # Tab / Shift+Tab cycle
        if key == Qt.Key.Key_Tab:
            self.navigate_cell.emit("next")
            event.accept()
            return
        if key == Qt.Key.Key_Backtab:
            self.navigate_cell.emit("prev")
            event.accept()
            return

        # Escape clears selection
        if key == Qt.Key.Key_Escape:
            scene = self.scene()
            if scene:
                scene.clearSelection()
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            self.unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)
