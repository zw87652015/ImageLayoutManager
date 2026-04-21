from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QPoint, QRectF
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QPainterPath, QPen, QBrush, QColor


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
        
        # Interaction — NoDrag: custom rubber band avoids QMacCGContext/OpenGL conflict
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Custom rubber-band state (viewport coords)
        self._rb_origin: QPoint | None = None
        self._rb_current: QPoint | None = None
        
        # Scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        # Zoom state
        self._zoom_level = 1.0

        # Space-drag pan state
        self._space_held = False

        # Manual middle-button / space pan state (avoids synthetic LeftButton
        # reaching scene items and triggering their drag logic)
        self._pan_active = False
        self._pan_last_pos: QPoint | None = None

        # Mouse tracking for status bar coordinates
        self.setMouseTracking(True)
        from PyQt6.QtCore import QElapsedTimer
        self._last_mouse_emit = QElapsedTimer()
        self._last_mouse_emit.start()

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
            # Pan via middle-button or Space+drag — handled entirely in the
            # view so the event never reaches scene items (prevents accidental
            # cell-drag when the wheel button is pressed over a cell).
            self._pan_active = True
            self._pan_last_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            from PyQt6.QtWidgets import QGraphicsItem
            scene_pos = self.mapToScene(event.position().toPoint())
            # Deliver to the scene if there are selectable items OR interactive
            # non-selectable items (add buttons, dividers) that accept hover events.
            # Background-only items (page rect, margin rect) have no hover events
            # and are intentionally excluded so rubber-band can start over them.
            interactive = any(
                (i.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
                or i.acceptHoverEvents()
                for i in (self.scene().items(scene_pos) or [])
            )
            if not interactive:
                # Click on empty / background space: start custom rubber band
                self._rb_origin = event.position().toPoint()
                self._rb_current = self._rb_origin
                if not (event.modifiers() & Qt.KeyboardModifier.ControlModifier):
                    self.scene().clearSelection()
                event.accept()
            else:
                self._rb_origin = None
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # Emit scene coordinates for status bar (throttled to ~30fps)
        if self._last_mouse_emit.elapsed() > 33:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.mouse_scene_pos_changed.emit(scene_pos.x(), scene_pos.y())
            self._last_mouse_emit.restart()

        if self._pan_active and self._pan_last_pos is not None:
            current = event.position().toPoint()
            delta = current - self._pan_last_pos
            self._pan_last_pos = current
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
        elif self._rb_origin is not None:
            self._rb_current = event.position().toPoint()
            rb_start = self.mapToScene(self._rb_origin)
            rb_end = self.mapToScene(self._rb_current)
            rb_rect = QRectF(rb_start, rb_end).normalized()
            path = QPainterPath()
            path.addRect(rb_rect)
            op = (Qt.ItemSelectionOperation.AddToSelection
                  if event.modifiers() & Qt.KeyboardModifier.ControlModifier
                  else Qt.ItemSelectionOperation.ReplaceSelection)
            self.scene().setSelectionArea(
                path, op, Qt.ItemSelectionMode.IntersectsItemShape
            )
            self.viewport().update()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.LeftButton and self._rb_origin is not None:
            self._rb_origin = None
            self._rb_current = None
            self.viewport().update()
            event.accept()
            return
        if event.button() == Qt.MouseButton.MiddleButton or (self._space_held and event.button() == Qt.MouseButton.LeftButton):
            self._pan_active = False
            self._pan_last_pos = None
            self.setCursor(Qt.CursorShape.OpenHandCursor if self._space_held else Qt.CursorShape.ArrowCursor)
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def drawForeground(self, painter: QPainter, rect):
        super().drawForeground(painter, rect)
        if self._rb_origin is not None and self._rb_current is not None:
            rb_start = self.mapToScene(self._rb_origin)
            rb_end = self.mapToScene(self._rb_current)
            rb_rect = QRectF(rb_start, rb_end).normalized()
            painter.save()
            painter.setPen(QPen(QColor(74, 144, 226), 0))
            painter.setBrush(QBrush(QColor(74, 144, 226, 40)))
            painter.drawRect(rb_rect)
            painter.restore()

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
