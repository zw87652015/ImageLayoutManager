from PyQt6.QtWidgets import QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItem
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QDrag
from PyQt6.QtCore import Qt, QRectF, QMimeData, QPointF

from src.model.enums import FitMode
from src.utils.image_proxy import get_image_proxy

class CellItem(QGraphicsRectItem):
    def __init__(self, cell_id: str, parent=None):
        super().__init__(parent)
        self.cell_id = cell_id
        # ... existing init code ...
        self.image_path = None
        self.fit_mode = FitMode.CONTAIN
        self.align_h = "center"  # left, center, right
        self.align_v = "center"  # top, center, bottom
        self.padding = (2, 2, 2, 2) # top, right, bottom, left
        self.is_placeholder = False
        
        # Visual settings
        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setAcceptDrops(True)
        
        self.proxy = get_image_proxy()
        self.proxy.thumbnail_ready.connect(self.on_thumbnail_ready)
        
        self._pixmap = None
        
        # Style
        self.border_pen = QPen(QColor("#CCCCCC"))
        self.border_pen.setWidth(1)
        self.border_pen.setCosmetic(True) # Width stays constant on zoom
        
        self.selected_pen = QPen(QColor("#007ACC"))
        self.selected_pen.setWidth(2)
        self.selected_pen.setCosmetic(True)
        
        self.hover_brush = QBrush(QColor(0, 122, 204, 30))
        self.normal_brush = QBrush(Qt.GlobalColor.white)
        self.placeholder_brush = QBrush(QColor("#F0F0F0"))
        
        self.is_hovered = False
        self._drag_start_pos = None

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.screenPos()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._drag_start_pos:
            dist = (event.screenPos() - self._drag_start_pos).manhattanLength()
            if dist > 10: # Drag threshold
                self._start_drag()
                self._drag_start_pos = None
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        super().mouseReleaseEvent(event)

    def _start_drag(self):
        drag = QDrag(self.scene().views()[0])
        mime_data = QMimeData()
        mime_data.setText(self.cell_id) # Transfer cell ID
        mime_data.setData("application/x-cell-id", self.cell_id.encode('utf-8'))
        drag.setMimeData(mime_data)
        
        # Create a small pixmap for drag
        pixmap = self._pixmap.scaled(100, 100, Qt.AspectRatioMode.KeepAspectRatio) if (self._pixmap and not self._pixmap.isNull()) else QPixmap(50, 50)
        if pixmap.isNull():
            pixmap.fill(QColor("#CCCCCC"))
        
        drag.setPixmap(pixmap)
        drag.setHotSpot(pixmap.rect().center())
        
        drag.exec(Qt.DropAction.MoveAction)

    def update_data(self, image_path, fit_mode, padding, is_placeholder, align_h="center", align_v="center"):
        self.image_path = image_path
        self.fit_mode = FitMode(fit_mode)
        self.align_h = align_h
        self.align_v = align_v
        self.padding = (padding['top'], padding['right'], padding['bottom'], padding['left'])
        self.is_placeholder = is_placeholder
        
        if self.image_path:
            import os
            if os.path.exists(self.image_path):
                self._pixmap = self.proxy.get_pixmap(self.image_path)
            else:
                self._pixmap = None
        else:
            self._pixmap = None
            
        self.update()

    def on_thumbnail_ready(self, path):
        if path == self.image_path:
            import os
            if os.path.exists(path):
                self._pixmap = self.proxy.get_pixmap(path)
                self.update()

    def paint(self, painter: QPainter, option: QStyleOptionGraphicsItem, widget):
        # Draw background
        rect = self.rect()
        
        if self.is_placeholder:
            painter.fillRect(rect, self.placeholder_brush)
        else:
            painter.fillRect(rect, self.normal_brush)
            
        if self.is_hovered:
            painter.fillRect(rect, self.hover_brush)
            
        # Draw Image
        import os
        if self.image_path and not os.path.exists(self.image_path) and not self.is_placeholder:
             self._draw_missing_file_icon(painter, rect)
        elif self._pixmap and not self._pixmap.isNull():
            self._draw_image(painter, rect)
        elif self.is_placeholder:
            self._draw_placeholder_icon(painter, rect)

        # Draw Border
        if self.isSelected():
            painter.setPen(self.selected_pen)
            painter.drawRect(rect)
        else:
            painter.setPen(self.border_pen)
            painter.drawRect(rect)
            
    def _draw_missing_file_icon(self, painter: QPainter, rect: QRectF):
        # Draw red cross or "Missing" text
        painter.setPen(QPen(QColor("#FF4444"), 2))
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, "Image Not Found")
        
        # Red border
        pen = QPen(QColor("#FF4444"))
        pen.setWidth(2)
        pen.setStyle(Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.drawRect(rect)

    def _draw_image(self, painter: QPainter, rect: QRectF):
        # Calculate content rect with padding
        content_rect = rect.adjusted(
            self.padding[3], self.padding[0], 
            -self.padding[1], -self.padding[2]
        )
        
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return

        pix_w = self._pixmap.width()
        pix_h = self._pixmap.height()
        
        target_rect = QRectF()
        
        if self.fit_mode == FitMode.CONTAIN:
            # Aspect ratio scaling
            ratio = min(content_rect.width() / pix_w, content_rect.height() / pix_h)
            new_w = pix_w * ratio
            new_h = pix_h * ratio
            
            # Alignment
            if self.align_h == "left":
                x = content_rect.left()
            elif self.align_h == "right":
                x = content_rect.right() - new_w
            else:  # center
                x = content_rect.left() + (content_rect.width() - new_w) / 2
            
            if self.align_v == "top":
                y = content_rect.top()
            elif self.align_v == "bottom":
                y = content_rect.bottom() - new_h
            else:  # center
                y = content_rect.top() + (content_rect.height() - new_h) / 2
            
            target_rect = QRectF(x, y, new_w, new_h)
            
        elif self.fit_mode == FitMode.COVER:
            # Aspect ratio scaling to fill
            ratio = max(content_rect.width() / pix_w, content_rect.height() / pix_h)
            new_w = pix_w * ratio
            new_h = pix_h * ratio
            
            # Center and clip
            x = content_rect.left() + (content_rect.width() - new_w) / 2
            y = content_rect.top() + (content_rect.height() - new_h) / 2
            
            target_rect = QRectF(x, y, new_w, new_h)
            # Clip is handled by painter clip if we wanted strict clipping, 
            # but usually we just draw the pixmap into the target rect.
            # However, for cover, we might draw outside content_rect if we don't clip.
            painter.setClipRect(content_rect)
            
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawPixmap(target_rect.toRect(), self._pixmap)
        painter.setClipping(False)

    def _draw_placeholder_icon(self, painter: QPainter, rect: QRectF):
        painter.setPen(QPen(QColor("#AAAAAA"), 2))
        c = rect.center()
        s = 20
        painter.drawLine(int(c.x() - s), int(c.y()), int(c.x() + s), int(c.y()))
        painter.drawLine(int(c.x()), int(c.y() - s), int(c.x()), int(c.y() + s))
        
        # Optional: Draw text "Drag Image Here"
        painter.setPen(QPen(QColor("#888888")))
        font = painter.font()
        font.setPointSize(10)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, "Drop Image Here")

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)
