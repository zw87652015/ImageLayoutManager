"""Zoomable SVG plot canvas for the Plot Editor (QGraphicsView)."""

from __future__ import annotations

from PyQt6.QtCore import QPoint, QPointF, QRectF, Qt, pyqtSignal
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
        self.setMouseTracking(True)
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
        return hit_test.pick_frame(self._regions, *frac)

    def _hover_bbox(self, key):
        """Fraction bbox for element ``key``."""
        if key.startswith('series:'):
            entry = (self._regions.get('series') or {}).get(key[7:])
            return entry.get('bbox') if entry else None
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

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_pos = event.position()
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
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
        super().mouseReleaseEvent(event)
