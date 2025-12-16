from PyQt6.QtGui import QPdfWriter, QPainter, QPageSize, QPageLayout, QFont, QImage, QColor
from PyQt6.QtCore import QSizeF, QRectF, QMarginsF, Qt
from PyQt6.QtWidgets import QGraphicsTextItem, QStyleOptionGraphicsItem
from PyQt6.QtSvg import QSvgRenderer
from PIL import Image
import os
from src.model.data_model import Project, Cell
from src.model.enums import FitMode
from src.model.layout_engine import LayoutEngine

class PdfExporter:
    @staticmethod
    def export(project: Project, output_path: str):
        writer = QPdfWriter(output_path)
        
        # Set Resolution FIRST to avoid resetting layout later
        writer.setResolution(project.dpi)
        writer.setCreator("Academic Figure Layout")

        # Calculate Layout (mm)
        layout_result = LayoutEngine.calculate_layout(project)

        # Use the project's page size directly (WYSIWYG with canvas)
        page_w_mm = project.page_width_mm
        page_h_mm = project.page_height_mm
        
        print(f"DEBUG: Exporting PDF: {page_w_mm}mm x {page_h_mm}mm at {project.dpi} DPI")
        print(f"DEBUG: Scale factor (dpi/25.4): {project.dpi / 25.4:.2f}")

        # Create custom page size using Millimeter units directly
        # Always specify dimensions as (width, height) and use Portrait orientation
        # This ensures the PDF matches the canvas exactly without dimension swapping
        page_size = QPageSize(QSizeF(page_w_mm, page_h_mm), QPageSize.Unit.Millimeter)
        
        page_layout = QPageLayout(
            page_size,
            QPageLayout.Orientation.Portrait,  # Always Portrait - dimensions already correct
            QMarginsF(0, 0, 0, 0),
            QPageLayout.Unit.Millimeter
        )
        
        if not writer.setPageLayout(page_layout):
            print("DEBUG: WARNING - setPageLayout returned False!")
        
        # Debug: verify the actual page rect
        actual_layout = writer.pageLayout()
        actual_size_mm = actual_layout.pageSize().size(QPageSize.Unit.Millimeter)
        actual_rect = actual_layout.paintRectPixels(project.dpi)
        print(f"DEBUG: Actual page size: {actual_size_mm.width():.1f}mm x {actual_size_mm.height():.1f}mm")
        print(f"DEBUG: Paint rect: {actual_rect.width()}x{actual_rect.height()} pixels")
        print(f"DEBUG: Expected: {page_w_mm * project.dpi / 25.4:.0f}x{page_h_mm * project.dpi / 25.4:.0f} pixels")
        
        painter = QPainter(writer)
        
        try:
            # Coordinate Conversion Factor: mm -> dots
            # dpi dots / inch, 1 inch = 25.4 mm
            scale = project.dpi / 25.4
            
            # 1. Draw Images
            for cell in project.cells:
                if cell.id in layout_result.cell_rects and cell.image_path and os.path.exists(cell.image_path):
                    x_mm, y_mm, w_mm, h_mm = layout_result.cell_rects[cell.id]
                    
                    # Convert rect to dots
                    target_rect = QRectF(
                        x_mm * scale, 
                        y_mm * scale, 
                        w_mm * scale, 
                        h_mm * scale
                    )
                    
                    # Apply Padding
                    p_top = cell.padding_top * scale
                    p_right = cell.padding_right * scale
                    p_bottom = cell.padding_bottom * scale
                    p_left = cell.padding_left * scale
                    
                    content_rect = target_rect.adjusted(p_left, p_top, -p_right, -p_bottom)
                    
                    if content_rect.width() > 0 and content_rect.height() > 0:
                        PdfExporter._draw_image(painter, cell.image_path, content_rect, cell.fit_mode)
                        
            # 2. Draw Text Items
            for text_item in project.text_items:
                PdfExporter._draw_text(painter, project, text_item, layout_result, scale)
                
        finally:
            painter.end()

    @staticmethod
    def _draw_image(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str):
        ext = os.path.splitext(path)[1].lower()
        
        if ext == '.svg':
            PdfExporter._draw_svg(painter, path, rect, fit_mode_str)
        else:
            PdfExporter._draw_raster(painter, path, rect, fit_mode_str)
    
    @staticmethod
    def _draw_svg(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str):
        """Draw SVG vector image - renders as vector in PDF for best quality."""
        try:
            renderer = QSvgRenderer(path)
            if not renderer.isValid():
                print(f"Invalid SVG file: {path}")
                return
            
            fit_mode = FitMode(fit_mode_str)
            default_size = renderer.defaultSize()
            
            if default_size.isEmpty():
                # Fallback: use rect size
                img_w, img_h = rect.width(), rect.height()
            else:
                img_w, img_h = default_size.width(), default_size.height()
            
            if fit_mode == FitMode.CONTAIN:
                ratio = min(rect.width() / img_w, rect.height() / img_h)
                new_w = img_w * ratio
                new_h = img_h * ratio
                
                x = rect.left() + (rect.width() - new_w) / 2
                y = rect.top() + (rect.height() - new_h) / 2
                
                target_rect = QRectF(x, y, new_w, new_h)
                renderer.render(painter, target_rect)
                
            elif fit_mode == FitMode.COVER:
                ratio = max(rect.width() / img_w, rect.height() / img_h)
                new_w = img_w * ratio
                new_h = img_h * ratio
                
                x = rect.left() + (rect.width() - new_w) / 2
                y = rect.top() + (rect.height() - new_h) / 2
                
                full_target_rect = QRectF(x, y, new_w, new_h)
                
                painter.save()
                painter.setClipRect(rect)
                renderer.render(painter, full_target_rect)
                painter.restore()
                
        except Exception as e:
            print(f"Failed to export SVG {path}: {e}")
    
    @staticmethod
    def _draw_raster(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str):
        """Draw raster image using PIL."""
        try:
            with Image.open(path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                
                data = img.tobytes("raw", "RGBA")
                qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
                
                fit_mode = FitMode(fit_mode_str)
                
                img_w = qimage.width()
                img_h = qimage.height()
                
                if fit_mode == FitMode.CONTAIN:
                    ratio = min(rect.width() / img_w, rect.height() / img_h)
                    new_w = img_w * ratio
                    new_h = img_h * ratio
                    
                    x = rect.left() + (rect.width() - new_w) / 2
                    y = rect.top() + (rect.height() - new_h) / 2
                    
                    target_draw_rect = QRectF(x, y, new_w, new_h)
                    
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    painter.drawImage(target_draw_rect, qimage)
                    
                elif fit_mode == FitMode.COVER:
                    ratio = max(rect.width() / img_w, rect.height() / img_h)
                    new_w = img_w * ratio
                    new_h = img_h * ratio
                    
                    x = rect.left() + (rect.width() - new_w) / 2
                    y = rect.top() + (rect.height() - new_h) / 2
                    
                    full_target_rect = QRectF(x, y, new_w, new_h)
                    
                    painter.save()
                    painter.setClipRect(rect)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                    painter.drawImage(full_target_rect, qimage)
                    painter.restore()
                    
        except Exception as e:
            print(f"Failed to export image {path}: {e}")

    @staticmethod
    def _draw_text(painter: QPainter, project: Project, text_item, layout_result, scale: float):
        # WYSIWYG text rendering - use exact same method as canvas (QGraphicsTextItem)
        #
        # Canvas behavior (TextGraphicsItem.update_style + canvas_scene.refresh_layout):
        #   - Uses 24pt base font with setScale(font_size_pt / 24)
        #   - boundingRect() * scale gives final size in scene "mm"
        #   - setDefaultTextColor() sets the color
        #
        # PDF strategy: Create a temporary QGraphicsTextItem, measure it exactly as
        # canvas does, then render to PDF with the same proportions.
        
        base_pt = 24
        text_scale = text_item.font_size_pt / base_pt
        
        # Create temporary QGraphicsTextItem - same as canvas does
        temp_item = QGraphicsTextItem()
        temp_item.setHtml(text_item.text)
        
        font = QFont(text_item.font_family, base_pt)
        if text_item.font_weight == "bold":
            font.setBold(True)
        temp_item.setFont(font)
        temp_item.setDefaultTextColor(QColor(text_item.color))
        
        # Get bounding rect at base font (same as canvas)
        base_rect = temp_item.boundingRect()
        
        # Canvas "mm" = boundingRect * text_scale (this is what user sees)
        tw_mm = base_rect.width() * text_scale
        th_mm = base_rect.height() * text_scale
        
        # Calculate position in mm (same logic as canvas_scene.refresh_layout)
        # For cell-scoped labels, use anchor-based positioning (default to top_left_inside if anchor is None)
        if text_item.scope == "cell" and text_item.parent_id and text_item.parent_id in layout_result.cell_rects:
            cx, cy, cw, ch = layout_result.cell_rects[text_item.parent_id]

            attach_to = getattr(project, 'label_attach_to', 'figure')
            if attach_to == "figure":
                cell = next((c for c in project.cells if c.id == text_item.parent_id), None)
                if cell:
                    cx += cell.padding_left
                    cy += cell.padding_top
                    cw -= cell.padding_left + cell.padding_right
                    ch -= cell.padding_top + cell.padding_bottom

            # Default to top_left_inside if anchor is None (for numbering labels)
            anchor = text_item.anchor or "top_left_inside"
            ox, oy = text_item.offset_x, text_item.offset_y

            if "top" in anchor:
                y_mm = cy + oy
            elif "bottom" in anchor:
                y_mm = cy + ch - oy - th_mm
            else:
                y_mm = cy + (ch - th_mm) / 2

            if "left" in anchor:
                x_mm = cx + ox
            elif "right" in anchor:
                x_mm = cx + cw - ox - tw_mm
            else:
                x_mm = cx + (cw - tw_mm) / 2
        else:
            x_mm = text_item.x
            y_mm = text_item.y

        # Convert position to PDF dots
        x_dots = x_mm * scale
        y_dots = y_mm * scale
        
        # Render: scale painter so text fills the correct mm in PDF
        # PDF needs: tw_mm * scale dots wide
        # QGraphicsTextItem at base_pt renders at base_rect.width() pixels
        # So render_scale = (tw_mm * scale) / base_rect.width() = text_scale * scale
        render_scale = text_scale * scale
        
        painter.save()
        painter.translate(x_dots, y_dots)
        painter.scale(render_scale, render_scale)
        
        # Paint the QGraphicsTextItem directly to the PDF painter
        option = QStyleOptionGraphicsItem()
        temp_item.paint(painter, option, None)
        
        painter.restore()
