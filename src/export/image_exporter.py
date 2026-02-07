from PyQt6.QtGui import QPainter, QFont, QImage, QColor
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QGraphicsTextItem, QStyleOptionGraphicsItem
from PyQt6.QtSvg import QSvgRenderer
from PIL import Image
import os
from src.model.data_model import Project, Cell
from src.model.enums import FitMode
from src.model.layout_engine import LayoutEngine


class ImageExporter:
    """Export project to raster image formats (TIFF, JPG, PNG)."""
    
    @staticmethod
    def export(project: Project, output_path: str, format: str = "TIFF"):
        """
        Export project to a raster image.
        
        Args:
            project: The project to export
            output_path: Output file path
            format: Image format - "TIFF", "JPG", "JPEG", or "PNG"
        """
        # Calculate Layout (mm)
        layout_result = LayoutEngine.calculate_layout(project)

        # Use the project's page size directly (WYSIWYG with canvas)
        page_w_mm = project.page_width_mm
        page_h_mm = project.page_height_mm
        
        # Convert mm to pixels using DPI
        # DPI = dots per inch, 1 inch = 25.4 mm
        scale = project.dpi / 25.4
        width_px = int(page_w_mm * scale)
        height_px = int(page_h_mm * scale)
        
        print(f"DEBUG: Exporting {format}: {page_w_mm}mm x {page_h_mm}mm at {project.dpi} DPI")
        print(f"DEBUG: Image size: {width_px} x {height_px} pixels")

        # Create QImage with white background
        # Use ARGB32 for transparency support, RGB32 for JPG
        if format.upper() in ("JPG", "JPEG"):
            image = QImage(width_px, height_px, QImage.Format.Format_RGB32)
            image.fill(Qt.GlobalColor.white)
        else:
            image = QImage(width_px, height_px, QImage.Format.Format_ARGB32)
            image.fill(Qt.GlobalColor.white)
        
        # Set DPI metadata
        # QImage uses dots per meter: dpi * 39.3701 (inches per meter)
        dpm = int(project.dpi * 39.3701)
        image.setDotsPerMeterX(dpm)
        image.setDotsPerMeterY(dpm)
        
        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        
        try:
            # 1. Draw Images and Scale Bars
            for cell in project.cells:
                if cell.id in layout_result.cell_rects and cell.image_path and os.path.exists(cell.image_path):
                    rects = getattr(layout_result, 'figure_rects', layout_result.cell_rects)
                    x_mm, y_mm, w_mm, h_mm = rects.get(cell.id, layout_result.cell_rects[cell.id])
                    
                    # Convert rect to pixels
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
                        rotation = getattr(cell, 'rotation', 0)
                        ImageExporter._draw_image(painter, cell.image_path, content_rect, cell.fit_mode, rotation)
                        
                        # Draw scale bar if enabled
                        if getattr(cell, 'scale_bar_enabled', False):
                            ImageExporter._draw_scale_bar(painter, cell, content_rect, scale)
                        
            # 2. Draw Text Items
            for text_item in project.text_items:
                ImageExporter._draw_text(painter, project, text_item, layout_result, scale)
                
        finally:
            painter.end()
        
        # Save using appropriate format
        format_upper = format.upper()
        if format_upper == "TIFF":
            # Use PIL for TIFF to ensure proper compression and metadata
            ImageExporter._save_as_tiff(image, output_path, project.dpi)
        elif format_upper in ("JPG", "JPEG"):
            image.save(output_path, "JPEG", quality=95)
        elif format_upper == "PNG":
            image.save(output_path, "PNG")
        else:
            # Default to PNG
            image.save(output_path, "PNG")
    
    @staticmethod
    def _save_as_tiff(qimage: QImage, output_path: str, dpi: int):
        """Save QImage as TIFF with proper DPI metadata using PIL."""
        # Convert QImage to PIL Image
        width = qimage.width()
        height = qimage.height()
        
        # Get raw data from QImage
        ptr = qimage.bits()
        ptr.setsize(qimage.sizeInBytes())
        
        # QImage Format_ARGB32 is actually BGRA in memory on little-endian systems
        if qimage.format() == QImage.Format.Format_ARGB32:
            pil_image = Image.frombytes("RGBA", (width, height), bytes(ptr), "raw", "BGRA")
        else:  # Format_RGB32
            pil_image = Image.frombytes("RGBA", (width, height), bytes(ptr), "raw", "BGRA")
            pil_image = pil_image.convert("RGB")
        
        # Save as TIFF with DPI metadata
        pil_image.save(output_path, "TIFF", dpi=(dpi, dpi), compression="tiff_lzw")

    @staticmethod
    def _draw_image(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0):
        """Draw an image into the given rect."""
        ext = os.path.splitext(path)[1].lower()
        
        if ext == '.svg':
            ImageExporter._draw_svg(painter, path, rect, fit_mode_str, rotation)
        elif ext == '.pdf':
            ImageExporter._draw_pdf(painter, path, rect, fit_mode_str, rotation)
        else:
            ImageExporter._draw_raster(painter, path, rect, fit_mode_str, rotation)
    
    @staticmethod
    def _draw_svg(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0):
        """Draw SVG vector image."""
        try:
            renderer = QSvgRenderer(path)
            if not renderer.isValid():
                print(f"Invalid SVG file: {path}")
                return
            
            fit_mode = FitMode(fit_mode_str)
            default_size = renderer.defaultSize()
            
            if default_size.isEmpty():
                img_w, img_h = rect.width(), rect.height()
            else:
                img_w, img_h = default_size.width(), default_size.height()
            
            # Adjust dimensions if rotated 90 or 270 degrees
            is_sideways = rotation in [90, 270]
            eff_img_w = img_h if is_sideways else img_w
            eff_img_h = img_w if is_sideways else img_h

            if fit_mode == FitMode.CONTAIN:
                ratio = min(rect.width() / eff_img_w, rect.height() / eff_img_h)
                new_w = eff_img_w * ratio
                new_h = eff_img_h * ratio
                
                x = rect.left() + (rect.width() - new_w) / 2
                y = rect.top() + (rect.height() - new_h) / 2
                
                target_rect = QRectF(x, y, new_w, new_h)
                
            elif fit_mode == FitMode.COVER:
                ratio = max(rect.width() / eff_img_w, rect.height() / eff_img_h)
                new_w = eff_img_w * ratio
                new_h = eff_img_h * ratio
                
                x = rect.left() + (rect.width() - new_w) / 2
                y = rect.top() + (rect.height() - new_h) / 2
                
                target_rect = QRectF(x, y, new_w, new_h)

            painter.save()
            if fit_mode == FitMode.COVER:
                painter.setClipRect(rect)
            
            if rotation != 0:
                painter.translate(target_rect.center())
                painter.rotate(rotation)
                # Drawing rect is relative to center
                draw_rect = QRectF(-img_w * ratio / 2, -img_h * ratio / 2, img_w * ratio, img_h * ratio)
                renderer.render(painter, draw_rect)
            else:
                renderer.render(painter, target_rect)
            
            painter.restore()
                
        except Exception as e:
            print(f"Failed to export SVG {path}: {e}")
    
    @staticmethod
    def _draw_raster(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0):
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
                
                # Adjust dimensions if rotated 90 or 270 degrees
                is_sideways = rotation in [90, 270]
                eff_img_w = img_h if is_sideways else img_w
                eff_img_h = img_w if is_sideways else img_h

                if fit_mode == FitMode.CONTAIN:
                    ratio = min(rect.width() / eff_img_w, rect.height() / eff_img_h)
                    new_w = eff_img_w * ratio
                    new_h = eff_img_h * ratio
                    
                    x = rect.left() + (rect.width() - new_w) / 2
                    y = rect.top() + (rect.height() - new_h) / 2
                    
                    target_rect = QRectF(x, y, new_w, new_h)
                    
                elif fit_mode == FitMode.COVER:
                    ratio = max(rect.width() / eff_img_w, rect.height() / eff_img_h)
                    new_w = eff_img_w * ratio
                    new_h = eff_img_h * ratio
                    
                    x = rect.left() + (rect.width() - new_w) / 2
                    y = rect.top() + (rect.height() - new_h) / 2
                    
                    target_rect = QRectF(x, y, new_w, new_h)
                
                painter.save()
                if fit_mode == FitMode.COVER:
                    painter.setClipRect(rect)
                
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                
                if rotation != 0:
                    painter.translate(target_rect.center())
                    painter.rotate(rotation)
                    draw_rect = QRectF(-img_w * ratio / 2, -img_h * ratio / 2, img_w * ratio, img_h * ratio)
                    painter.drawImage(draw_rect, qimage)
                else:
                    painter.drawImage(target_rect, qimage)
                
                painter.restore()
                    
        except Exception as e:
            print(f"Failed to export image {path}: {e}")

    @staticmethod
    def _draw_pdf(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0):
        """Draw PDF first page as raster image using PyMuPDF."""
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(path)
            if doc.page_count == 0:
                doc.close()
                return
            
            page = doc[0]
            
            # Render at high resolution for quality
            zoom = 4.0  # 4x zoom for high quality
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=True)
            doc.close()
            
            # Convert to QImage
            qimage = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format.Format_RGBA8888).copy()
            
            fit_mode = FitMode(fit_mode_str)
            
            img_w = qimage.width()
            img_h = qimage.height()
            
            # Adjust dimensions if rotated 90 or 270 degrees
            is_sideways = rotation in [90, 270]
            eff_img_w = img_h if is_sideways else img_w
            eff_img_h = img_w if is_sideways else img_h

            if fit_mode == FitMode.CONTAIN:
                ratio = min(rect.width() / eff_img_w, rect.height() / eff_img_h)
                new_w = eff_img_w * ratio
                new_h = eff_img_h * ratio
                
                x = rect.left() + (rect.width() - new_w) / 2
                y = rect.top() + (rect.height() - new_h) / 2
                
                target_rect = QRectF(x, y, new_w, new_h)
                
            elif fit_mode == FitMode.COVER:
                ratio = max(rect.width() / eff_img_w, rect.height() / eff_img_h)
                new_w = eff_img_w * ratio
                new_h = eff_img_h * ratio
                
                x = rect.left() + (rect.width() - new_w) / 2
                y = rect.top() + (rect.height() - new_h) / 2
                
                target_rect = QRectF(x, y, new_w, new_h)
            
            painter.save()
            if fit_mode == FitMode.COVER:
                painter.setClipRect(rect)
            
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            
            if rotation != 0:
                painter.translate(target_rect.center())
                painter.rotate(rotation)
                draw_rect = QRectF(-img_w * ratio / 2, -img_h * ratio / 2, img_w * ratio, img_h * ratio)
                painter.drawImage(draw_rect, qimage)
            else:
                painter.drawImage(target_rect, qimage)
            
            painter.restore()
                
        except Exception as e:
            print(f"Failed to export PDF {path}: {e}")

    @staticmethod
    def _draw_text(painter: QPainter, project: Project, text_item, layout_result, scale: float):
        """Draw text item (same logic as PdfExporter for WYSIWYG)."""
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
        if text_item.scope == "cell" and text_item.parent_id and text_item.parent_id in layout_result.cell_rects:
            cx, cy, cw, ch = layout_result.cell_rects[text_item.parent_id]

            if (
                getattr(project, 'label_placement', 'in_cell') == 'label_row_above'
                and getattr(text_item, 'subtype', None) != 'corner'
                and text_item.parent_id in getattr(layout_result, 'label_rects', {})
            ):
                cx, cy, cw, ch = layout_result.label_rects[text_item.parent_id]
            else:
                attach_to = getattr(project, 'label_attach_to', 'figure')
                if attach_to == "figure":
                    cell = next((c for c in project.cells if c.id == text_item.parent_id), None)
                    if cell:
                        cx += cell.padding_left
                        cy += cell.padding_top
                        cw -= cell.padding_left + cell.padding_right
                        ch -= cell.padding_top + cell.padding_bottom

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

        # Convert position to pixels
        x_px = x_mm * scale
        y_px = y_mm * scale
        
        # Render: scale painter so text fills the correct mm
        render_scale = text_scale * scale
        
        painter.save()
        painter.translate(x_px, y_px)
        painter.scale(render_scale, render_scale)
        
        # Paint the QGraphicsTextItem directly
        option = QStyleOptionGraphicsItem()
        temp_item.paint(painter, option, None)
        
        painter.restore()

    @staticmethod
    def _draw_scale_bar(painter: QPainter, cell, content_rect: QRectF, scale: float):
        """Draw scale bar on the exported image."""
        from PIL import Image as PILImage
        
        # Get image dimensions for scale calculation
        try:
            with PILImage.open(cell.image_path) as img:
                orig_w, orig_h = img.size
        except Exception:
            return
        
        # Adjust dimensions if rotated 90 or 270 degrees
        rotation = getattr(cell, 'rotation', 0)
        is_sideways = rotation in [90, 270]
        eff_pix_w = orig_h if is_sideways else orig_w
        eff_pix_h = orig_w if is_sideways else orig_h

        # µm per pixel based on mode
        um_per_px = 0.1301 if cell.scale_bar_mode == "rgb" else 0.2569
        
        # Calculate bar length in source image pixels
        bar_length_px = cell.scale_bar_length_um / um_per_px
        
        # Calculate scale factor from image to content rect (in pixels)
        from src.model.enums import FitMode
        fit_mode = FitMode(cell.fit_mode)
        if fit_mode == FitMode.CONTAIN:
            scale_ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        else:  # COVER
            scale_ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        
        # Bar length in output pixels
        bar_length_out = bar_length_px * scale_ratio
        
        # Bar thickness in output pixels
        bar_thickness_out = cell.scale_bar_thickness_mm * scale
        
        # Calculate position based on scale_bar_position and offsets
        ox = cell.scale_bar_offset_x * scale
        oy = cell.scale_bar_offset_y * scale
        
        # Y position (always at bottom)
        bar_y = content_rect.bottom() - oy - bar_thickness_out
        
        # X position based on horizontal alignment
        if cell.scale_bar_position == "bottom_left":
            bar_x = content_rect.left() + ox
        elif cell.scale_bar_position == "bottom_center":
            bar_x = content_rect.left() + (content_rect.width() - bar_length_out) / 2
        else:  # bottom_right
            bar_x = content_rect.right() - ox - bar_length_out
        
        # Draw the bar
        bar_rect = QRectF(bar_x, bar_y, bar_length_out, bar_thickness_out)
        painter.fillRect(bar_rect, QColor(cell.scale_bar_color))
        
        # Draw text if enabled
        if cell.scale_bar_show_text:
            text = f"{cell.scale_bar_length_um:.0f} µm" if cell.scale_bar_length_um >= 1 else f"{cell.scale_bar_length_um:.2f} µm"
            
            font = QFont("Arial", int(8 * scale / 3))  # Scale font for output
            painter.setFont(font)
            painter.setPen(QColor(cell.scale_bar_color))
            
            # Text above the bar, centered
            text_height = 4 * scale
            text_rect = QRectF(bar_x, bar_y - text_height, bar_length_out, text_height)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, text)
