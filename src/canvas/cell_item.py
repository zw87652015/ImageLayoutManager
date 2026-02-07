from PyQt6.QtWidgets import QGraphicsRectItem, QStyleOptionGraphicsItem, QGraphicsItem
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap, QDrag, QFont
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
        self.rotation = 0
        self.is_placeholder = False
        
        # Scale bar properties
        self.scale_bar_enabled = False
        self.scale_bar_mode = "rgb"
        self.scale_bar_length_um = 10.0
        self.scale_bar_color = "#FFFFFF"
        self.scale_bar_show_text = True
        self.scale_bar_thickness_mm = 0.5
        self.scale_bar_position = "bottom_right"
        self.scale_bar_offset_x = 2.0
        self.scale_bar_offset_y = 2.0
        
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

    def update_data(self, image_path, fit_mode, padding, is_placeholder, rotation=0, align_h="center", align_v="center",
                     scale_bar_enabled=False, scale_bar_mode="rgb", scale_bar_length_um=10.0,
                     scale_bar_color="#FFFFFF", scale_bar_show_text=True, scale_bar_thickness_mm=0.5,
                     scale_bar_position="bottom_right", scale_bar_offset_x=2.0, scale_bar_offset_y=2.0):
        self.image_path = image_path
        self.fit_mode = FitMode(fit_mode)
        self.rotation = rotation
        self.align_h = align_h
        self.align_v = align_v
        self.padding = (padding['top'], padding['right'], padding['bottom'], padding['left'])
        self.is_placeholder = is_placeholder
        
        # Scale bar
        self.scale_bar_enabled = scale_bar_enabled
        self.scale_bar_mode = scale_bar_mode
        self.scale_bar_length_um = scale_bar_length_um
        self.scale_bar_color = scale_bar_color
        self.scale_bar_show_text = scale_bar_show_text
        self.scale_bar_thickness_mm = scale_bar_thickness_mm
        self.scale_bar_position = scale_bar_position
        self.scale_bar_offset_x = scale_bar_offset_x
        self.scale_bar_offset_y = scale_bar_offset_y
        
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

        # Draw Scale Bar (if enabled and has image)
        if self.scale_bar_enabled and self._pixmap and not self._pixmap.isNull():
            self._draw_scale_bar(painter, rect)

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

        # Adjust dimensions if rotated 90 or 270 degrees
        is_sideways = self.rotation in [90, 270]
        eff_pix_w = pix_h if is_sideways else pix_w
        eff_pix_h = pix_w if is_sideways else pix_h
        
        target_rect = QRectF()
        
        if self.fit_mode == FitMode.CONTAIN:
            # Aspect ratio scaling
            ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            new_w = eff_pix_w * ratio
            new_h = eff_pix_h * ratio
            
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
            ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            new_w = eff_pix_w * ratio
            new_h = eff_pix_h * ratio
            
            # Center and clip
            x = content_rect.left() + (content_rect.width() - new_w) / 2
            y = content_rect.top() + (content_rect.height() - new_h) / 2
            
            target_rect = QRectF(x, y, new_w, new_h)
            painter.setClipRect(content_rect)
            
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        # Apply rotation
        if self.rotation != 0:
            painter.save()
            painter.translate(target_rect.center())
            painter.rotate(self.rotation)
            # When rotated, target_rect needs to be relative to the new origin (center)
            # The pixmap itself always has pix_w x pix_h
            rotated_draw_rect = QRectF(-pix_w * ratio / 2, -pix_h * ratio / 2, pix_w * ratio, pix_h * ratio)
            painter.drawPixmap(rotated_draw_rect.toRect(), self._pixmap)
            painter.restore()
        else:
            painter.drawPixmap(target_rect.toRect(), self._pixmap)
            
        painter.setClipping(False)

    def _draw_placeholder_icon(self, painter: QPainter, rect: QRectF):
        # Scale elements based on cell size for proper display at all dimensions
        min_dimension = min(rect.width(), rect.height())
        
        # Scale the + mark size (20% of smaller dimension, clamped between 10 and 40)
        s = max(10, min(40, min_dimension * 0.2))
        
        # Scale line width (proportional to mark size, clamped between 1 and 4)
        line_width = max(1, min(4, s / 10))
        
        painter.setPen(QPen(QColor("#AAAAAA"), line_width))
        c = rect.center()
        painter.drawLine(int(c.x() - s), int(c.y()), int(c.x() + s), int(c.y()))
        painter.drawLine(int(c.x()), int(c.y() - s), int(c.x()), int(c.y() + s))
        
        # Draw text "Drop Image Here" with dynamic font size
        painter.setPen(QPen(QColor("#888888")))
        font = painter.font()
        
        # Calculate font size based on cell dimensions (8% of smaller dimension, clamped between 8 and 16)
        font_size = max(8, min(16, int(min_dimension * 0.08)))
        font.setPointSize(font_size)
        painter.setFont(font)
        
        # Position text with padding from bottom
        text_rect = rect.adjusted(5, 0, -5, -s * 1.5)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter | Qt.AlignmentFlag.AlignBottom, "Drop Image Here")

    def _draw_scale_bar(self, painter: QPainter, rect: QRectF):
        """Draw scale bar on the image."""
        # Calculate content rect (inside padding)
        content_rect = rect.adjusted(
            self.padding[3], self.padding[0], 
            -self.padding[1], -self.padding[2]
        )
        
        if content_rect.width() <= 0 or content_rect.height() <= 0:
            return
        
        # µm per pixel based on mode
        um_per_px = 0.1301 if self.scale_bar_mode == "rgb" else 0.2569
        
        # Calculate bar length in pixels (source image pixels)
        bar_length_px = self.scale_bar_length_um / um_per_px
        
        # Get ORIGINAL image dimensions (not thumbnail) for accurate scale calculation
        from PIL import Image
        try:
            with Image.open(self.image_path) as img:
                orig_w, orig_h = img.size
        except Exception:
            # Fallback to pixmap if PIL fails
            orig_w = self._pixmap.width()
            orig_h = self._pixmap.height()
        
        # Adjust dimensions if rotated 90 or 270 degrees
        is_sideways = self.rotation in [90, 270]
        eff_pix_w = orig_h if is_sideways else orig_w
        eff_pix_h = orig_w if is_sideways else orig_h

        if self.fit_mode == FitMode.CONTAIN:
            scale_ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        else:  # COVER
            scale_ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        
        # Bar length in mm (canvas units)
        bar_length_mm = bar_length_px * scale_ratio
        
        # Bar thickness in mm
        bar_thickness = self.scale_bar_thickness_mm
        
        # Calculate position based on scale_bar_position and offsets
        ox = self.scale_bar_offset_x
        oy = self.scale_bar_offset_y
        
        # Y position (always at bottom)
        bar_y = content_rect.bottom() - oy - bar_thickness
        
        # X position based on horizontal alignment
        if self.scale_bar_position == "bottom_left":
            bar_x = content_rect.left() + ox
        elif self.scale_bar_position == "bottom_center":
            bar_x = content_rect.left() + (content_rect.width() - bar_length_mm) / 2
        else:  # bottom_right
            bar_x = content_rect.right() - ox - bar_length_mm
        
        # Draw the bar
        bar_rect = QRectF(bar_x, bar_y, bar_length_mm, bar_thickness)
        painter.fillRect(bar_rect, QColor(self.scale_bar_color))
        
        # Draw text if enabled
        if self.scale_bar_show_text:
            text = f"{self.scale_bar_length_um:.0f} µm" if self.scale_bar_length_um >= 1 else f"{self.scale_bar_length_um:.2f} µm"
            
            font = QFont("Arial", 8)
            painter.setFont(font)
            painter.setPen(QPen(QColor(self.scale_bar_color)))
            
            # Text above the bar, centered
            text_rect = QRectF(bar_x, bar_y - 4, bar_length_mm, 4)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, text)

    def hoverEnterEvent(self, event):
        self.is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)
