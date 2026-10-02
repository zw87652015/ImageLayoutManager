"""Zoomable SVG plot canvas for the Plot Editor (QGraphicsView)."""

from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtGui import QPainter
from PyQt6.QtSvg import QSvgRenderer
from PyQt6.QtSvgWidgets import QGraphicsSvgItem
from PyQt6.QtWidgets import QFrame, QGraphicsScene, QGraphicsView

from src.app.theme import get_tokens, token_color

_MARGIN = 24.0
_MIN_SCALE = 0.1
_MAX_SCALE = 20.0


class PlotCanvas(QGraphicsView):
    """Displays the rendered plot SVG; Ctrl+wheel zooms, middle-drag pans."""

    def __init__(self, theme, parent=None):
        super().__init__(parent)
        self.setObjectName('plotCanvas')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self._auto_fit = True
        self._scale = 1.0
        self._item = None
        self._panning = False
        self._pan_pos = None
        scene = QGraphicsScene(self)
        scene.setBackgroundBrush(token_color(get_tokens(theme)
                                             ['canvas_bg']))
        self.setScene(scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setTransformationAnchor(
            QGraphicsView.ViewportAnchor.AnchorUnderMouse)

    def show_svg(self, data):
        """Replace the scene with ``data`` (SVG bytes) and fit to view."""
        scene = self.scene()
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
        self.resetTransform()
        self._scale = 1.0
        self._auto_fit = True
        self._fit()

    def _fit(self):
        if self._item is not None:
            self.fitInView(self._item.boundingRect(),
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
            self._auto_fit = False
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
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton and self._panning:
            self._panning = False
            self.viewport().unsetCursor()
            event.accept()
            return
        super().mouseReleaseEvent(event)
