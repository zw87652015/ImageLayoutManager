from PyQt6.QtWidgets import QGraphicsView
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QPainter, QWheelEvent, QMouseEvent

class CanvasView(QGraphicsView):
    zoom_changed = pyqtSignal(float)

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

    def wheelEvent(self, event: QWheelEvent):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            # Zoom
            angle = event.angleDelta().y()
            factor = 1.1 if angle > 0 else 0.9
            
            self.scale(factor, factor)
            self._zoom_level *= factor
            self.zoom_changed.emit(self._zoom_level)
            event.accept()
        else:
            super().wheelEvent(event)

    def mousePressEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            # Pan
            self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
            # Create synthetic left button event
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

    def mouseReleaseEvent(self, event: QMouseEvent):
        if event.button() == Qt.MouseButton.MiddleButton:
            # Release Pan
            synthetic_event = QMouseEvent(
                event.type(),
                event.position(),
                event.globalPosition(),
                Qt.MouseButton.LeftButton,
                Qt.MouseButton.NoButton,
                event.modifiers()
            )
            super().mouseReleaseEvent(synthetic_event)
            self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        else:
            super().mouseReleaseEvent(event)
