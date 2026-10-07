"""Zoomable SVG plot canvas for the Plot Editor (QGraphicsView)."""

from __future__ import annotations

from PyQt6.QtCore import (QEvent, QPoint, QPointF, QRectF, Qt,
                          pyqtSignal)
from PyQt6.QtGui import QBrush, QColor, QPainter, QPen
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import (QFrame, QGraphicsRectItem, QGraphicsScene,
                             QGraphicsView)

from src.app.theme import get_tokens, token_color
from . import hit_test

_MARGIN = 24.0
_MIN_SCALE = 0.1
_MAX_SCALE = 20.0
_HIT_PX = 5.0      # series pick tolerance, view pixels
_HOVER_PAD = 2.0   # hover border padding, view pixels


class PlotCanvas(QGraphicsView):
    """Displays the rendered plot SVG; Ctrl+wheel zooms, middle-drag pans.

    When element regions are set (``set_regions``) hovering an editable
    element shows a dashed outline and a left double-click emits
    ``element_activated``.
    """

    element_activated = pyqtSignal(str, QPoint)
    # key-or-None, global pos, figure fraction (or None)
    context_requested = pyqtSignal(object, QPoint, object)
    # 'annotation:<id>' dropped at a new axes-fraction centre
    element_moved = pyqtSignal(str, float, float)
    # Delete/Backspace on a selected 'annotation:'/'bracket:' element
    element_delete_requested = pyqtSignal(str)

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setObjectName('plotCanvas')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._auto_fit = True
        self._scale = 1.0
        self._item = None
        self._panning = False
        self._pan_pos = None
        self._regions = None
        self._hover = None
        self._hover_key = None
        self._drag = None
        self._selected_key = None
        self._selection = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)
        self.setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context)
        scene = QGraphicsScene(self)
        scene.setBackgroundBrush(token_color(get_tokens(theme)
                                             ['canvas_bg']))
        self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self._hover_pen = QPen(token_color(get_tokens(theme)['text_sec']))
        self._hover_pen.setStyle(Qt.PenStyle.DashLine)
        self._hover_pen.setCosmetic(True)
        self._hover_pen.setWidth(1)
        self._select_pen = QPen(token_color(get_tokens(theme)['accent']))
        self._select_pen.setCosmetic(True)
        self._select_pen.setWidthF(1.5)

    def show_svg(self, data, keep_view=False):
        """Replace the scene with ``data`` (SVG bytes) and fit to view.

        With ``keep_view`` and an unchanged scene size the transform and
        scroll positions are kept, so re-renders don't jump; a size change
        or a fresh plot still fits to view.
        """
        scene = self.scene()
        old_bounds = (self._item.boundingRect()
                      if keep_view and self._item is not None else None)
        old_transform = self.transform()
        old_auto = self._auto_fit
        hs = self.horizontalScrollBar().value()
        vs = self.verticalScrollBar().value()
        scene.clear()
        item = QGraphicsSvgItem()
        renderer = QSvgRenderer(data, item)
        item.setSharedRenderer(renderer)
        item.setCacheMode(QGraphicsSvgItem.CacheMode.NoCache)
        bounds = item.boundingRect()
        scene.addItem(item)
        scene.setSceneRect(bounds.adjusted(-_MARGIN, -_MARGIN,
                                         _MARGIN, _MARGIN))
        self._item = item
        hover = QGraphicsRectItem()
        hover.setPen(self._hover_pen)
        hover.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        hover.setZValue(1)
        hover.hide()
        scene.addItem(hover)
        self._hover = hover
        self._hover_key = None
        selection = QGraphicsRectItem()
        selection.setPen(self._select_pen)
        selection.setBrush(QBrush(Qt.BrushStyle.NoBrush))
        selection.setZValue(2)
        selection.hide()
        scene.addItem(selection)
        self._selection = selection
        if old_bounds is not None and bounds == old_bounds:
            if old_auto:
                self._fit()
            else:
                self.setTransform(old_transform)
                self._scale = old_transform.m11()
                self.horizontalScrollBar().setValue(hs)
                self.verticalScrollBar().setValue(vs)
            return
        self.resetTransform()
        self._scale = 1.0
        self._set_auto_fit(True)
        self._fit()

    # ── element hit-testing ──────────────────────────────────────────

    def set_regions(self, regions):
        """Update element hit regions (figure fractions, top-left origin)."""
        self._regions = regions
        self._hover_key = None
        if self._hover is not None:
            self._hover.hide()
        # Keep the selection across re-renders while its element exists.
        self._select(self._selected_key)

    # ── selection (notes / brackets; Delete removes) ─────────────────

    def _select(self, key):
        """Select a deletable element, or clear with ``None``."""
        bbox = None
        if key is not None and self._regions is not None \
                and self._item is not None:
            bbox = self._hover_bbox(key)
        self._selected_key = key if bbox is not None else None
        if self._selection is None:
            return
        if bbox is None:
            self._selection.hide()
            return
        rect = self._frac_bbox_to_scene(bbox)
        pad = _HOVER_PAD / max(self._scale, 1e-6)
        self._selection.setRect(rect.adjusted(-pad, -pad, pad, pad))
        self._selection.show()

    def event(self, event):
        # The window-level Delete QAction would otherwise steal the
        # key; claim it while the canvas has focus so keyPressEvent
        # sees it (nothing selected → it just does nothing).
        if event.type() == QEvent.Type.ShortcutOverride \
                and event.key() in (Qt.Key.Key_Delete,
                                    Qt.Key.Key_Backspace) \
                and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            event.accept()
            return True
        return super().event(event)

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) \
                and self._selected_key is not None:
            self.delete_selected()
            event.accept()
            return
        if event.key() == Qt.Key.Key_Escape \
                and self._selected_key is not None:
            self._select(None)
            event.accept()
            return
        super().keyPressEvent(event)

    def delete_selected(self):
        """The same path as the Delete key: drop the element selected
        on the canvas (none selected → nothing happens)."""
        key = self._selected_key
        if key is None:
            return
        self._select(None)
        self.element_delete_requested.emit(key)

    def _frac_point(self, view_pos):
        """View pos → figure fraction, or None when outside the SVG."""
        if self._item is None:
            return None
        bounds = self._item.boundingRect()
        if bounds.width() <= 0 or bounds.height() <= 0:
            return None
        scene_pt = self.mapToScene(view_pos)
        fx = (scene_pt.x() - bounds.x()) / bounds.width()
        fy = (scene_pt.y() - bounds.y()) / bounds.height()
        return fx, fy

    def _frac_bbox_to_scene(self, bbox):
        bounds = self._item.boundingRect()
        x0 = bounds.x() + bbox[0] * bounds.width()
        y0 = bounds.y() + bbox[1] * bounds.height()
        x1 = bounds.x() + bbox[2] * bounds.width()
        y1 = bounds.y() + bbox[3] * bounds.height()
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _series_view(self, entry):
        """Series entry (fractions) → view-coord bbox + points."""
        bounds = self._item.boundingRect()
        fr = self._frac_bbox_to_scene(entry['bbox']) \
            if entry.get('bbox') is not None else None
        bbox = None
        if fr is not None:
            tl = self.mapFromScene(fr.topLeft())
            br = self.mapFromScene(fr.bottomRight())
            bbox = (min(tl.x(), br.x()), min(tl.y(), br.y()),
                    max(tl.x(), br.x()), max(tl.y(), br.y()))
        points = []
        for fx, fy in entry.get('points') or ():
            p = self.mapFromScene(QPointF(
                bounds.x() + fx * bounds.width(),
                bounds.y() + fy * bounds.height()))
            points.append((p.x(), p.y()))
        return {'bbox': bbox, 'points': points}

    def _hit_key(self, view_pos):
        if self._regions is None or self._item is None:
            return None
        frac = self._frac_point(view_pos)
        if frac is None:
            return None
        key = hit_test.pick(self._regions, *frac)
        if key is not None:
            return key
        series = self._regions.get('series') or {}
        view_series = {sid: self._series_view(e)
                       for sid, e in series.items()}
        sid = hit_test.pick_series(view_series, view_pos.x(),
                                   view_pos.y(), _HIT_PX)
        if sid is not None:
            return 'series:%s' % sid
        # Filled areas: after series so a line inside a band still picks
        # the line, before the frame fallback.
        area = hit_test.pick_area(self._regions, *frac)
        if area is not None:
            return area
        return hit_test.pick_frame(self._regions, *frac)

    def _hover_bbox(self, key):
        """Fraction bbox for element ``key``."""
        if key.startswith('series:'):
            entry = (self._regions.get('series') or {}).get(key[7:])
            return entry.get('bbox') if entry else None
        for prefix, coll in (('violin:', 'violins'), ('stack:', 'stacks'),
                             ('hist:', 'hists'),
                             ('annotation:', 'annotations'),
                             ('bracket:', 'brackets'),
                             ('band:', 'bands'), ('span:', 'spans')):
            if key.startswith(prefix):
                entry = (self._regions.get(coll) or {}).get(
                    key[len(prefix):])
                return entry.get('bbox') \
                    if isinstance(entry, dict) else entry
        return self._regions.get(key)

    def _update_hover(self, view_pos):
        if self._hover is None:
            return
        key = self._hit_key(view_pos) if self._regions else None
        self._hover_key = key
        if key is None:
            self._hover.hide()
            return
        bbox = self._hover_bbox(key)
        if bbox is None:
            self._hover.hide()
            return
        rect = self._frac_bbox_to_scene(bbox)
        pad = _HOVER_PAD / max(self._scale, 1e-6)
        self._hover.setRect(rect.adjusted(-pad, -pad, pad, pad))
        self._hover.show()

    def _set_auto_fit(self, on):
        self._auto_fit = on
        policy = (Qt.ScrollBarPolicy.ScrollBarAlwaysOff if on
                  else Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(policy)
        self.setVerticalScrollBarPolicy(policy)

    def _fit(self):
        if self._item is not None:
            self.fitInView(self.sceneRect(),
                           Qt.AspectRatioMode.KeepAspectRatio)
            self._scale = self.transform().m11()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self._auto_fit:
            self._fit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = event.angleDelta().y() / 120.0
            factor = 1.1 ** steps
            new = self._scale * factor
            if new < _MIN_SCALE or new > _MAX_SCALE:
                return
            self._scale = new
            if self._auto_fit:
                self._set_auto_fit(False)
            self.scale(factor, factor)
            return
        super().wheelEvent(event)

    def _on_context(self, pos):
        """Emit ``context_requested`` with the hit key and figure
        fraction under the cursor (both possibly None)."""
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        key = self._hit_key(pos)
        frac = self._frac_point(pos)
        self.context_requested.emit(
            key, self.viewport().mapToGlobal(pos), frac)

    def mousePressEvent(self, event):
        # ClickFocus alone doesn't fire for every path — take focus
        # explicitly so Delete reaches keyPressEvent, not the window
        # shortcut.
        self.setFocus(Qt.FocusReason.MouseFocusReason)
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_pos = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton \
                and self._regions is not None:
            pos = event.position().toPoint()
            key = self._hit_key(pos)
            self._select(key if key is not None and key.startswith(
                ('annotation:', 'bracket:', 'span:', 'band:'))
                else None)
            if key is not None and key.startswith('annotation:'):
                bbox = self._hover_bbox(key)
                if bbox is not None:
                    self._drag = {'key': key, 'pos': pos,
                                  'rect': self._frac_bbox_to_scene(bbox),
                                  'moved': False}
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag is not None:
            pos = event.position().toPoint()
            delta = pos - self._drag['pos']
            if not self._drag['moved'] and max(abs(delta.x()),
                                               abs(delta.y())) < 4:
                return
            self._drag['moved'] = True
            if self._selection is not None:
                self._selection.hide()
            s_delta = self.mapToScene(pos) - self.mapToScene(
                self._drag['pos'])
            if self._hover is not None:
                pad = _HOVER_PAD / max(self._scale, 1e-6)
                self._hover.setRect(
                    self._drag['rect'].translated(s_delta).adjusted(
                        -pad, -pad, pad, pad))
                self._hover.show()
            event.accept()
            return
        if self._panning:
            delta = event.position() - self._pan_pos
            self._pan_pos = event.position()
            self.horizontalScrollBar().setValue(
                self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(
                self.verticalScrollBar().value() - round(delta.y()))
            if self._hover is not None:
                self._hover.hide()
            event.accept()
            return
        self._update_hover(event.position().toPoint())
        super().mouseMoveEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            key = self._hit_key(event.position().toPoint())
            if key is not None:
                event.accept()
                self.element_activated.emit(
                    key, event.globalPosition().toPoint())
                return
        super().mouseDoubleClickEvent(event)

    def leaveEvent(self, event):
        if self._hover is not None:
            self._hover.hide()
            self._hover_key = None
        super().leaveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton \
                and self._drag is not None:
            drag = self._drag
            self._drag = None
            if drag['moved'] and self._item is not None:
                rect = drag['rect'].translated(
                    self.mapToScene(event.position().toPoint())
                    - self.mapToScene(drag['pos']))
                bounds = self._item.boundingRect()
                fx = (rect.center().x() - bounds.x()) / bounds.width()
                fy = (rect.center().y() - bounds.y()) / bounds.height()
                axes = hit_test.figure_to_axes(self._regions, fx, fy)
                if axes is not None:
                    self.element_moved.emit(drag['key'], axes[0],
                                            axes[1])
            event.accept()
            return
        super().mouseReleaseEvent(event)
