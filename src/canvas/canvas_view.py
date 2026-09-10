from __future__ import annotations

from PyQt6.QtWidgets import QGraphicsView
import math

from PyQt6.QtCore import Qt, pyqtSignal, QPointF, QPoint, QRectF, QVariantAnimation, QEasingCurve
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QPainterPath, QPen, QBrush, QColor, QCursor, QTransform

from src.app.motion import start_animation


class CanvasView(QGraphicsView):
    MIN_ZOOM = 0.05
    MAX_ZOOM = 64.0
    ZOOM_DURATION_MS = 140

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
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)

        # Custom rubber-band state (viewport coords)
        self._rb_origin: QPoint | None = None
        self._rb_current: QPoint | None = None
        
        # Scrollbars
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        
        # Zoom state
        self._zoom_level = 1.0
        self._zoom_target = 1.0
        self._zoom_anim = None
        for bar in (self.horizontalScrollBar(), self.verticalScrollBar()):
            bar.sliderPressed.connect(self._cancel_zoom)
            bar.actionTriggered.connect(self._cancel_zoom)
        if scene is not None:
            scene.sceneRectChanged.connect(self._scene_rect_changed)

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
        if page_rect.isEmpty():
            return
        viewport = self.viewport().rect()
        zoom = min(max(1, viewport.width() - 4) / page_rect.width(),
                   max(1, viewport.height() - 4) / page_rect.height())
        self._start_zoom(zoom, QPointF(viewport.center()), page_rect.center())

    def zoom_to_100(self):
        """Reset zoom to 100%."""
        self._start_zoom(1.0)

    def _zoom_anchor(self):
        point = self.viewport().mapFromGlobal(QCursor.pos())
        if not self.viewport().rect().contains(point):
            point = self.viewport().rect().center()
        return QPointF(point)

    def _scene_at(self, viewport_pos):
        inverse, valid = self.viewportTransform().inverted()
        return inverse.map(QPointF(viewport_pos)) if valid else QPointF()

    def _cancel_zoom(self):
        anim = self._zoom_anim
        self._zoom_anim = None
        if anim is not None:
            anim.stop()
            anim.deleteLater()
        self._zoom_level = self.transform().m11()
        self._zoom_target = self._zoom_level

    def _scene_rect_changed(self, _rect):
        anchor = QPointF(self.viewport().rect().center())
        scene_anchor = self._scene_at(anchor)
        self._cancel_zoom()
        self._set_zoom_frame(self._zoom_level, scene_anchor, anchor)

    def _set_zoom_frame(self, zoom, scene_anchor, viewport_anchor):
        viewport = self.viewport().rect()
        center = scene_anchor + (QPointF(viewport.center()) - viewport_anchor) / zoom
        width, height = viewport.width() / zoom, viewport.height() / zoom
        visible_margin = QRectF(center.x() - width, center.y() - height,
                                2 * width, 2 * height)
        scene = self.scene()
        self.setSceneRect(visible_margin.united(scene.sceneRect()) if scene else visible_margin)
        offset = viewport_anchor - scene_anchor * zoom
        scroll_x, scroll_y = round(-offset.x()), round(-offset.y())
        transform = QTransform(zoom, 0, 0, zoom,
                               offset.x() + scroll_x, offset.y() + scroll_y)
        self.setTransform(transform)
        self.horizontalScrollBar().setValue(scroll_x)
        self.verticalScrollBar().setValue(scroll_y)
        self._zoom_level = self.transform().m11()
        self.zoom_changed.emit(self._zoom_level)

    def _start_zoom(self, zoom, anchor=None, scene_target=None, animated=True):
        if not math.isfinite(zoom) or zoom <= 0:
            return
        zoom = min(self.MAX_ZOOM, max(self.MIN_ZOOM, zoom))
        anchor = self._zoom_anchor() if anchor is None else QPointF(anchor)
        scene_start = self._scene_at(anchor)
        scene_end = scene_start if scene_target is None else QPointF(scene_target)
        self._cancel_zoom()
        self._zoom_target = zoom
        start = self._zoom_level
        if not animated or (zoom == start and scene_start == scene_end):
            self._set_zoom_frame(zoom, scene_end, anchor)
            return
        anim = QVariantAnimation(self)
        self._zoom_anim = anim
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def update(value):
            if self._zoom_anim is anim:
                t = float(value)
                frame_zoom = zoom if t >= 1.0 else start + (zoom - start) * t
                frame_anchor = scene_end if t >= 1.0 else scene_start + (scene_end - scene_start) * t
                self._set_zoom_frame(frame_zoom, frame_anchor, anchor)

        def finish():
            if self._zoom_anim is not anim:
                return
            self._zoom_anim = None
            self._zoom_target = zoom
            anim.deleteLater()

        anim.valueChanged.connect(update)
        anim.finished.connect(finish)
        start_animation(anim, self.ZOOM_DURATION_MS, spatial=True)

    def _apply_zoom(self, factor, anchor=None, animated=True):
        if not math.isfinite(factor) or factor <= 0:
            return
        base = self._zoom_target if animated and self._zoom_anim is not None else self.transform().m11()
        self._start_zoom(base * factor, anchor, animated=animated)

    # ------------------------------------------------------------------
    # Events
    # ------------------------------------------------------------------

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            pixels = event.pixelDelta()
            direct = not pixels.isNull() or event.phase() != Qt.ScrollPhase.NoScrollPhase
            delta = pixels.y() if not pixels.isNull() else event.angleDelta().y()
            if delta:
                steps = max(-20.0, min(20.0, delta / (40.0 if not pixels.isNull() else 120.0)))
                self._apply_zoom(1.1 ** steps, event.position(), animated=not direct)
            elif direct:
                self._cancel_zoom()
            event.accept()
        else:
            self._cancel_zoom()
            pixels = event.pixelDelta()
            if not pixels.isNull():
                self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - pixels.x())
                self.verticalScrollBar().setValue(self.verticalScrollBar().value() - pixels.y())
                event.accept()
            else:
                super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        self._cancel_zoom()
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
                # Also deselect any focused PiP (handles clicks outside the scene rect)
                for item in self.scene().cell_items.values():
                    if item._selected_pip_id is not None:
                        item.deselect_pip()
                event.accept()
            else:
                self._rb_origin = None
                super().mousePressEvent(event)
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent):
        # A strip-label drag outlives its source item (the hover preview can
        # remove the strip), so the view forwards continuation events itself.
        scene = self.scene()
        if scene is not None and getattr(scene, '_label_drag', None) is not None:
            scene.label_drag_move(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
        # Emit scene coordinates for status bar (throttled to ~30fps)
        if self._last_mouse_emit.elapsed() > 33:
            scene_pos = self.mapToScene(event.position().toPoint())
            self.mouse_scene_pos_changed.emit(scene_pos.x(), scene_pos.y())
            self._last_mouse_emit.restart()

        if self._pan_active and self._pan_last_pos is not None:
            self._cancel_zoom()
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
        scene = self.scene()
        if (event.button() == Qt.MouseButton.LeftButton and scene is not None
                and getattr(scene, '_label_drag', None) is not None):
            scene.label_drag_finish(self.mapToScene(event.position().toPoint()))
            event.accept()
            return
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
        if (mod & Qt.KeyboardModifier.ControlModifier
                and not mod & Qt.KeyboardModifier.AltModifier):
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

    def resizeEvent(self, event):
        if hasattr(self, '_zoom_anim'):
            self._cancel_zoom()
        super().resizeEvent(event)

    def hideEvent(self, event):
        self._cancel_zoom()
        super().hideEvent(event)

    def keyReleaseEvent(self, event: QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_held = False
            self.unsetCursor()
            event.accept()
            return
        super().keyReleaseEvent(event)
