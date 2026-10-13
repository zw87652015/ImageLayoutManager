from __future__ import annotations

from PyQt6.QtWidgets import QGraphicsView, QGraphicsRectItem
import math

from PyQt6.QtCore import Qt, QEvent, pyqtSignal, QPointF, QPoint, QRect, QRectF, QVariantAnimation, QEasingCurve, QTimer
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent, QKeyEvent, QPainterPath, QPen, QBrush, QColor, QCursor, QTransform

from src.app.motion import start_animation
from src.canvas.canvas_ruler import CanvasRuler, RulerCorner
from src.canvas.reveal_math import axis_reveal_delta, reveal_margin


class CanvasView(QGraphicsView):
    MIN_ZOOM = 0.05
    MAX_ZOOM = 64.0
    ZOOM_DURATION_MS = 140

    zoom_changed = pyqtSignal(float)
    mouse_scene_pos_changed = pyqtSignal(float, float)  # x_mm, y_mm
    navigate_cell = pyqtSignal(str)       # direction: "up"/"down"/"left"/"right"/"next"/"prev"
    swap_cell = pyqtSignal(str)           # direction: "up"/"down"/"left"/"right"
    ruler_unit_requested = pyqtSignal(str)  # unit picked on a ruler/corner menu

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self.viewport().setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        
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
        self._pinch_total = 1.0
        self.grabGesture(Qt.GestureType.PinchGesture)
        for bar in (self.horizontalScrollBar(), self.verticalScrollBar()):
            bar.sliderPressed.connect(self._cancel_zoom)
            bar.actionTriggered.connect(self._cancel_zoom)
        if scene is not None:
            scene.sceneRectChanged.connect(self._scene_rect_changed)

        # Manual middle-button / space pan state (avoids synthetic LeftButton
        # reaching scene items and triggering their drag logic)
        self._pan_active = False
        self._pan_last_pos: QPoint | None = None

        # Mouse tracking for status bar coordinates
        self.setMouseTracking(True)
        from PyQt6.QtCore import QElapsedTimer
        self._last_mouse_emit = QElapsedTimer()
        self._last_mouse_emit.start()

        # Canvas rulers — hidden by default (plot-alignment previews and
        # other secondary CanvasViews keep their un-margined viewport).
        self._rulers_visible = False
        self._ruler_unit = "mm"
        self._ruler_tokens = {}
        self._ruler_dirty = False
        self._cursor_vp_pos = None
        self._h_ruler = CanvasRuler(Qt.Orientation.Horizontal, self)
        self._v_ruler = CanvasRuler(Qt.Orientation.Vertical, self)
        self._ruler_corner = RulerCorner(self)
        for w in (self._h_ruler, self._v_ruler, self._ruler_corner):
            w.hide()
        # Never connect to scene.changed: any connection switches
        # QGraphicsScene to its legacy update path, which leaves stale
        # pixels on the canvas. Geometry changes refresh the rulers via
        # mouse moves and MainWindow._refresh_and_update instead.
        if scene is not None:
            scene.selectionChanged.connect(self._schedule_ruler_update)

    # ------------------------------------------------------------------
    # Rulers
    # ------------------------------------------------------------------

    def set_rulers_visible(self, visible: bool):
        visible = bool(visible)
        if visible == self._rulers_visible:
            return
        self._rulers_visible = visible
        t = self._h_ruler.thickness() if visible else 0
        self.setViewportMargins(t, t, 0, 0)
        for w in (self._h_ruler, self._v_ruler, self._ruler_corner):
            w.setVisible(visible)
        self._layout_rulers()
        self._update_rulers()

    def set_ruler_unit(self, unit: str):
        self._ruler_unit = unit
        self._h_ruler.set_unit(unit)
        self._v_ruler.set_unit(unit)
        self._ruler_corner.set_unit(unit)

    def set_ruler_tokens(self, tokens: dict):
        self._ruler_tokens = tokens or {}
        for w in (self._h_ruler, self._v_ruler, self._ruler_corner):
            w.set_tokens(self._ruler_tokens)

    def _layout_rulers(self):
        if not getattr(self, '_rulers_visible', False):
            return
        t = self._h_ruler.thickness()
        vp = self.viewport().geometry()
        self._h_ruler.setGeometry(QRect(vp.x(), vp.y() - t, vp.width(), t))
        self._v_ruler.setGeometry(QRect(vp.x() - t, vp.y(), t, vp.height()))
        self._ruler_corner.setGeometry(QRect(vp.x() - t, vp.y() - t, t, t))

    def _schedule_ruler_update(self):
        """Coalesce bursts of scene/selection changes into one repaint."""
        if not getattr(self, '_rulers_visible', False) or self._ruler_dirty:
            return
        self._ruler_dirty = True
        QTimer.singleShot(0, self._update_rulers)

    def _update_rulers(self):
        self._ruler_dirty = False
        if not getattr(self, '_rulers_visible', False):
            return
        sel = self.selection_scene_rect()
        m = self.viewportTransform()
        cur = self._cursor_vp_pos
        for ruler, horizontal in ((self._h_ruler, True),
                                  (self._v_ruler, False)):
            if sel is not None:
                if horizontal:
                    a = m.m11() * sel.left() + m.dx()
                    b = m.m11() * sel.right() + m.dx()
                else:
                    a = m.m22() * sel.top() + m.dy()
                    b = m.m22() * sel.bottom() + m.dy()
                ruler.set_selection_range((min(a, b), max(a, b)))
            else:
                ruler.set_selection_range(None)
            ruler.set_cursor(
                None if cur is None else (cur.x() if horizontal else cur.y()))
            ruler.update()

    def selection_scene_rect(self):
        """Union of the current selection's exact scene geometry."""
        scene = self.scene()
        if scene is None:
            return None
        rect = None
        for item in scene.selectedItems():
            r = None
            pip_id = getattr(item, '_selected_pip_id', None)
            if pip_id:
                pip = next((p for p in getattr(item, '_pip_items', ())
                            if p.id == pip_id), None)
                if pip is not None:
                    r = item.mapRectToScene(
                        item._pip_inset_rect(pip, item._pip_content_rect()))
            if r is None:
                if isinstance(item, QGraphicsRectItem):
                    r = item.mapRectToScene(item.rect())
                else:
                    r = item.sceneBoundingRect()
            rect = r if rect is None else rect.united(r)
        return rect

    def reveal_scene_rect(self, rect, margin_px=24.0, animated=True) -> bool:
        """Pan only as far as needed to show *rect*; no pan when it is already visible."""
        if rect is None or not rect.isValid():
            return False
        viewport = QRectF(self.viewport().rect())
        target = self.viewportTransform().mapRect(QRectF(rect))
        mx = reveal_margin(viewport.width(), margin_px)
        my = reveal_margin(viewport.height(), margin_px)
        dx = axis_reveal_delta(target.left(), target.right(),
                               viewport.left() + mx, viewport.right() - mx)
        dy = axis_reveal_delta(target.top(), target.bottom(),
                               viewport.top() + my, viewport.bottom() - my)
        if abs(dx) < 0.5 and abs(dy) < 0.5:
            return False
        anchor = QPointF(viewport.center())
        scene_target = self._scene_at(anchor) + QPointF(dx, dy) / self.transform().m11()
        self._start_zoom(self._zoom_target, anchor, scene_target, animated=animated)
        return True

    def reveal_selection(self, animated=True) -> bool:
        return self.reveal_scene_rect(self.selection_scene_rect(), animated=animated)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange and getattr(self, '_rulers_visible', False):
            t = self._h_ruler.thickness()
            self.setViewportMargins(t, t, 0, 0)
            self._layout_rulers()
            self._update_rulers()

    def scrollContentsBy(self, dx, dy):
        super().scrollContentsBy(dx, dy)
        self._update_rulers()

    def leaveEvent(self, event):
        self._cursor_vp_pos = None
        self._update_rulers()
        super().leaveEvent(event)

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

    def zoom_to(self, level):
        """Animate to an absolute zoom level about the viewport centre."""
        self._start_zoom(level, QPointF(self.viewport().rect().center()))

    def zoom_in(self):
        self._apply_zoom(1.25, QPointF(self.viewport().rect().center()))

    def zoom_out(self):
        self._apply_zoom(1 / 1.25, QPointF(self.viewport().rect().center()))

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
        scene_obj = self.scene()
        if scene_obj is not None and hasattr(scene_obj, 'set_view_scale'):
            scene_obj.set_view_scale(self.transform().m11())
        self.horizontalScrollBar().setValue(scroll_x)
        self.verticalScrollBar().setValue(scroll_y)
        self._zoom_level = self.transform().m11()
        self.zoom_changed.emit(self._zoom_level)
        self._update_rulers()

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
        if event.button() == Qt.MouseButton.MiddleButton:
            # Pan via middle-button — handled entirely in the
            # view so the event never reaches scene items (prevents accidental
            # cell-drag when the wheel button is pressed over a cell).
            self._pan_active = True
            self._pan_last_pos = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
        elif event.button() == Qt.MouseButton.LeftButton:
            if getattr(self.scene(), 'draw_tool', None):
                # A draw tool owns left clicks: let Qt deliver to the scene
                # (the custom rubber-band would swallow empty-space presses).
                super().mousePressEvent(event)
                return
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
        # Feed the rulers' cursor marker first — before the emit throttle and
        # before the label-drag early return below.
        self._cursor_vp_pos = event.position()
        self._update_rulers()
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
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = False
            self._pan_last_pos = None
            self.setCursor(Qt.CursorShape.ArrowCursor)
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

        # Draw tool keys (Esc/Enter/Backspace) and navigation suppression
        scene = self.scene()
        if scene is not None and getattr(scene, 'draw_key_press', None):
            if scene.draw_key_press(event):
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

    def event(self, event):
        if event.type() == QEvent.Type.Gesture:
            pinch = event.gesture(Qt.GestureType.PinchGesture)
            if pinch is not None:
                self._pinch(pinch)
                event.accept(pinch)
                return True
        return super().event(event)

    def _pinch(self, gesture):
        if gesture.state() == Qt.GestureState.GestureStarted:
            self._cancel_zoom()
            self._pinch_total = 1.0
        total = gesture.totalScaleFactor()
        factor = total / self._pinch_total if self._pinch_total > 0 else 1.0
        self._pinch_total = total
        centre = self.viewport().mapFrom(self, gesture.centerPoint().toPoint())
        self._apply_zoom(factor, QPointF(centre), animated=False)

    def resizeEvent(self, event):
        if hasattr(self, '_zoom_anim'):
            self._cancel_zoom()
        super().resizeEvent(event)
        self._layout_rulers()
        self._update_rulers()

    def hideEvent(self, event):
        self._cancel_zoom()
        super().hideEvent(event)

    def focusOutEvent(self, event):
        if self._pan_active:
            self._pan_active = False
            self._pan_last_pos = None
            self.unsetCursor()
        super().focusOutEvent(event)


