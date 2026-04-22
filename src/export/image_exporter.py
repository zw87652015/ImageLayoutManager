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

        # If a user-defined export region is set, the raster canvas shrinks to
        # the region size and content is translated so the region origin maps
        # to (0, 0). Content outside the region is simply clipped by image bounds.
        export_region = getattr(project, 'export_region', None)
        if export_region is not None:
            page_w_mm = export_region.w_mm
            page_h_mm = export_region.h_mm
            region_dx_mm = export_region.x_mm
            region_dy_mm = export_region.y_mm
        else:
            page_w_mm = project.page_width_mm
            page_h_mm = project.page_height_mm
            region_dx_mm = 0.0
            region_dy_mm = 0.0
        
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

        # Shift so the region's top-left maps to pixel (0, 0). No-op when unset.
        if region_dx_mm != 0.0 or region_dy_mm != 0.0:
            painter.translate(-region_dx_mm * scale, -region_dy_mm * scale)
        
        try:
            label_row_above = getattr(project, 'label_placement', 'in_cell') == 'label_row_above'
            label_rects = getattr(layout_result, 'label_rects', {})

            # 1. Draw Images, Scale Bars, and Nested Layouts (sorted by z_index for freeform overlap support)
            sorted_cells = sorted(project.get_all_leaf_cells(), key=lambda c: getattr(c, 'z_index', 0))
            for cell in sorted_cells:
                if cell.id not in layout_result.cell_rects:
                    continue
                x_mm, y_mm, w_mm, h_mm = layout_result.cell_rects[cell.id]

                target_rect = QRectF(
                    x_mm * scale, y_mm * scale, w_mm * scale, h_mm * scale
                )

                p_top = cell.padding_top * scale
                p_right = cell.padding_right * scale
                p_bottom = cell.padding_bottom * scale
                p_left = cell.padding_left * scale
                content_rect = target_rect.adjusted(p_left, p_top, -p_right, -p_bottom)

                if content_rect.width() <= 0 or content_rect.height() <= 0:
                    continue

                nested_path = getattr(cell, 'nested_layout_path', None)
                if nested_path and os.path.exists(nested_path):
                    ImageExporter._draw_nested_layout(painter, nested_path, content_rect, project.dpi)
                elif cell.image_path and os.path.exists(cell.image_path):
                    rotation = getattr(cell, 'rotation', 0)
                    crop = (getattr(cell, 'crop_left', 0.0), getattr(cell, 'crop_top', 0.0),
                            getattr(cell, 'crop_right', 1.0), getattr(cell, 'crop_bottom', 1.0))
                    svg_override = None
                    if cell.image_path.lower().endswith('.svg'):
                        from src.utils.svg_text_utils import build_svg_overrides_for_path, apply_svg_font_overrides
                        ov = build_svg_overrides_for_path(project, cell.image_path)
                        if ov:
                            svg_override = apply_svg_font_overrides(cell.image_path, ov)
                    ImageExporter._draw_image(painter, cell.image_path, content_rect, cell.fit_mode, rotation, crop, svg_override)

                    if getattr(cell, 'scale_bar_enabled', False):
                        ImageExporter._draw_scale_bar(painter, cell, content_rect, scale)

                ImageExporter._draw_pip_items(painter, project, cell, content_rect, scale)

            # 1b. Draw Label Cells (label rows above picture rows)
            if label_row_above:
                ImageExporter._draw_label_cells(painter, project, layout_result, scale)
                        
            # 2. Draw Text Items
            for text_item in project.text_items:
                # Skip numbering labels rendered by label cells
                if (
                    label_row_above
                    and text_item.scope == 'cell'
                    and getattr(text_item, 'subtype', None) != 'corner'
                    and text_item.parent_id in label_rects
                ):
                    continue
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
    def render_to_qimage(project: Project) -> QImage:
        """Render project to a QImage (in-memory, no file save).
        
        Used for generating nested layout thumbnails on the canvas.
        """
        layout_result = LayoutEngine.calculate_layout(project)
        scale = project.dpi / 25.4
        width_px = int(project.page_width_mm * scale)
        height_px = int(project.page_height_mm * scale)

        image = QImage(width_px, height_px, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)

        dpm = int(project.dpi * 39.3701)
        image.setDotsPerMeterX(dpm)
        image.setDotsPerMeterY(dpm)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        try:
            label_row_above = getattr(project, 'label_placement', 'in_cell') == 'label_row_above'
            label_rects = getattr(layout_result, 'label_rects', {})

            for cell in project.get_all_leaf_cells():
                if cell.id not in layout_result.cell_rects:
                    continue
                x_mm, y_mm, w_mm, h_mm = layout_result.cell_rects[cell.id]
                target_rect = QRectF(x_mm * scale, y_mm * scale, w_mm * scale, h_mm * scale)
                p_top = cell.padding_top * scale
                p_right = cell.padding_right * scale
                p_bottom = cell.padding_bottom * scale
                p_left = cell.padding_left * scale
                content_rect = target_rect.adjusted(p_left, p_top, -p_right, -p_bottom)
                if content_rect.width() <= 0 or content_rect.height() <= 0:
                    continue

                nested_path = getattr(cell, 'nested_layout_path', None)
                if nested_path and os.path.exists(nested_path):
                    ImageExporter._draw_nested_layout(painter, nested_path, content_rect, project.dpi)
                elif cell.image_path and os.path.exists(cell.image_path):
                    rotation = getattr(cell, 'rotation', 0)
                    crop = (getattr(cell, 'crop_left', 0.0), getattr(cell, 'crop_top', 0.0),
                            getattr(cell, 'crop_right', 1.0), getattr(cell, 'crop_bottom', 1.0))
                    svg_override = None
                    if cell.image_path.lower().endswith('.svg'):
                        from src.utils.svg_text_utils import build_svg_overrides_for_path, apply_svg_font_overrides
                        ov = build_svg_overrides_for_path(project, cell.image_path)
                        if ov:
                            svg_override = apply_svg_font_overrides(cell.image_path, ov)
                    ImageExporter._draw_image(painter, cell.image_path, content_rect, cell.fit_mode, rotation, crop, svg_override)
                    if getattr(cell, 'scale_bar_enabled', False):
                        ImageExporter._draw_scale_bar(painter, cell, content_rect, scale)

                ImageExporter._draw_pip_items(painter, project, cell, content_rect, scale)

            if label_row_above:
                ImageExporter._draw_label_cells(painter, project, layout_result, scale)

            for text_item in project.text_items:
                if (
                    label_row_above
                    and text_item.scope == 'cell'
                    and getattr(text_item, 'subtype', None) != 'corner'
                    and text_item.parent_id in label_rects
                ):
                    continue
                ImageExporter._draw_text(painter, project, text_item, layout_result, scale)
        finally:
            painter.end()

        return image

    @staticmethod
    def _draw_pip_items(painter: QPainter, project, cell, content_rect: QRectF, scale: float):
        """Draw all PiP insets for a cell onto the given content_rect."""
        pip_items = getattr(cell, 'pip_items', [])
        if not pip_items:
            return
        cw = content_rect.width()
        ch = content_rect.height()
        for pip in pip_items:
            inset_rect = QRectF(
                content_rect.x() + pip.x * cw,
                content_rect.y() + pip.y * ch,
                pip.w * cw,
                pip.h * ch,
            )
            painter.save()
            painter.setClipRect(inset_rect)
            # Draw pip image
            if pip.pip_type == "zoom" and cell.image_path and os.path.exists(cell.image_path):
                src_crop = (pip.crop_left, pip.crop_top, pip.crop_right, pip.crop_bottom)
                ImageExporter._draw_raster(painter, cell.image_path, inset_rect, "contain", 0, src_crop)
            elif pip.pip_type == "external" and pip.image_path and os.path.exists(pip.image_path):
                ImageExporter._draw_image(painter, pip.image_path, inset_rect, "contain", 0)
            painter.restore()

            # Draw PiP scale bar if enabled
            if getattr(pip, "scale_bar_enabled", False):
                # Determine correct mapping inheritance
                current_um_per_px = getattr(pip, "scale_bar_um_per_px", 0.0)
                if pip.pip_type == "zoom" and current_um_per_px <= 0:
                    current_um_per_px = getattr(cell, "scale_bar_um_per_px", 0.1301)
                if current_um_per_px <= 0:
                    current_um_per_px = 0.1301
                
                # Temporarily set for _draw_scale_bar logic
                old_um = getattr(pip, "scale_bar_um_per_px", 0.0)
                pip.scale_bar_um_per_px = current_um_per_px
                
                # PiP zoom type is STRETCH, external is CONTAIN
                pip_fit = "stretch" if pip.pip_type == "zoom" else "contain"
                ImageExporter._draw_scale_bar(painter, pip, inset_rect, scale, fit_mode_override=pip_fit)
                
                # Restore
                pip.scale_bar_um_per_px = old_um
            # Draw border
            if pip.border_enabled:
                from PyQt6.QtGui import QPen
                bpen = QPen(QColor(pip.border_color))
                # Convert points to pixels (1pt = 1/72 inch)
                bpen.setWidthF(pip.border_width_pt * (project.dpi / 72.0))
                bpen.setCosmetic(False)
                if getattr(pip, 'border_style', 'solid') == 'dashed':
                    bpen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(bpen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(inset_rect)
            # Draw zoom origin box
            if pip.pip_type == "zoom" and getattr(pip, 'show_origin_box', False):
                origin_rect = QRectF(
                    content_rect.x() + pip.crop_left * cw,
                    content_rect.y() + pip.crop_top * ch,
                    (pip.crop_right - pip.crop_left) * cw,
                    (pip.crop_bottom - pip.crop_top) * ch,
                )
                from PyQt6.QtGui import QPen
                open_pen = QPen(QColor(pip.origin_box_color))
                # Convert points to pixels
                open_pen.setWidthF(pip.origin_box_width_pt * (project.dpi / 72.0))
                open_pen.setCosmetic(False)
                if getattr(pip, 'origin_box_style', 'solid') == 'dashed':
                    open_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(open_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(origin_rect)

    @staticmethod
    def _draw_nested_layout(painter: QPainter, figlayout_path: str, content_rect: QRectF, parent_dpi: int):
        """Render a nested .figlayout into the given content_rect as raster graphics.
        
        Loads the sub-project, renders it to a QImage at the parent DPI,
        then draws the image into content_rect with aspect ratio preserved.
        """
        try:
            from src.model.data_model import Project as SubProject
            sub_project = SubProject.load_from_file(figlayout_path)
        except Exception as e:
            print(f"Failed to load nested layout {figlayout_path}: {e}")
            return

        sub_project.dpi = parent_dpi
        sub_image = ImageExporter.render_to_qimage(sub_project)
        if sub_image is None or sub_image.isNull():
            return

        # Draw the rendered sub-image into content_rect (contain mode)
        pix_w = sub_image.width()
        pix_h = sub_image.height()
        if pix_w <= 0 or pix_h <= 0:
            return

        ratio = min(content_rect.width() / pix_w, content_rect.height() / pix_h)
        new_w = pix_w * ratio
        new_h = pix_h * ratio
        x = content_rect.left() + (content_rect.width() - new_w) / 2
        y = content_rect.top() + (content_rect.height() - new_h) / 2
        target = QRectF(x, y, new_w, new_h)

        painter.drawImage(target, sub_image)

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
    def _draw_image(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                    crop: tuple = (0.0, 0.0, 1.0, 1.0), svg_override_bytes: bytes = None):
        """Draw an image into the given rect, applying crop and rotation."""
        ext = os.path.splitext(path)[1].lower()
        if ext == '.svg':
            ImageExporter._draw_svg(painter, path, rect, fit_mode_str, rotation, crop, svg_override_bytes)
        elif ext in ('.pdf', '.eps'):
            ImageExporter._draw_pdf(painter, path, rect, fit_mode_str, rotation, crop)
        else:
            ImageExporter._draw_raster(painter, path, rect, fit_mode_str, rotation, crop)

    @staticmethod
    def _draw_svg(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                  crop: tuple = (0.0, 0.0, 1.0, 1.0), svg_override_bytes: bytes = None):
        """Draw SVG vector image, honouring crop."""
        try:
            if svg_override_bytes:
                from PyQt6.QtCore import QByteArray
                renderer = QSvgRenderer(QByteArray(svg_override_bytes))
            else:
                renderer = QSvgRenderer(path)
            if not renderer.isValid():
                print(f"Invalid SVG file: {path}")
                return

            fit_mode = FitMode(fit_mode_str)
            default_size = renderer.defaultSize()
            img_w = default_size.width() if not default_size.isEmpty() else rect.width()
            img_h = default_size.height() if not default_size.isEmpty() else rect.height()

            cl, ct, cr, cb = crop
            crop_w_frac = max(0.001, cr - cl)
            crop_h_frac = max(0.001, cb - ct)
            eff_img_w_full = img_w
            eff_img_h_full = img_h

            # Effective dimensions are the cropped portion
            is_sideways = rotation in [90, 270]
            eff_crop_w = (img_h * crop_h_frac) if is_sideways else (img_w * crop_w_frac)
            eff_crop_h = (img_w * crop_w_frac) if is_sideways else (img_h * crop_h_frac)

            if fit_mode == FitMode.CONTAIN:
                ratio = min(rect.width() / eff_crop_w, rect.height() / eff_crop_h)
            else:
                ratio = max(rect.width() / eff_crop_w, rect.height() / eff_crop_h)

            # Where the crop portion lands (centred in rect)
            crop_canvas_w = eff_crop_w * ratio
            crop_canvas_h = eff_crop_h * ratio
            crop_x = rect.left() + (rect.width() - crop_canvas_w) / 2
            crop_y = rect.top() + (rect.height() - crop_canvas_h) / 2

            # Full SVG canvas rect (may extend beyond rect edges)
            full_w = eff_img_w_full * ratio
            full_h = eff_img_h_full * ratio
            full_x = crop_x - cl * full_w
            full_y = crop_y - ct * full_h
            target_rect = QRectF(full_x, full_y, full_w, full_h)

            painter.save()
            # Always clip to the visible crop area
            painter.setClipRect(QRectF(crop_x, crop_y, crop_canvas_w, crop_canvas_h))

            if rotation != 0:
                center = QRectF(crop_x, crop_y, crop_canvas_w, crop_canvas_h).center()
                painter.translate(center)
                painter.rotate(rotation)
                draw_rect = QRectF(-eff_img_w_full * ratio / 2, -eff_img_h_full * ratio / 2,
                                   eff_img_w_full * ratio, eff_img_h_full * ratio)
                renderer.render(painter, draw_rect)
            else:
                renderer.render(painter, target_rect)

            painter.restore()

        except Exception as e:
            print(f"Failed to export SVG {path}: {e}")
    
    @staticmethod
    def _draw_raster(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                     crop: tuple = (0.0, 0.0, 1.0, 1.0)):
        """Draw raster image using PIL, honouring crop."""
        try:
            with Image.open(path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')

                cl, ct, cr, cb = crop
                full_w, full_h = img.width, img.height
                # Crop to the visible region in source pixels
                cx0 = int(cl * full_w)
                cy0 = int(ct * full_h)
                cx1 = max(cx0 + 1, int(cr * full_w))
                cy1 = max(cy0 + 1, int(cb * full_h))
                if cx0 != 0 or cy0 != 0 or cx1 != full_w or cy1 != full_h:
                    img = img.crop((cx0, cy0, cx1, cy1))

                data = img.tobytes("raw", "RGBA")
                qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)

                fit_mode = FitMode(fit_mode_str)
                img_w = qimage.width()
                img_h = qimage.height()

                is_sideways = rotation in [90, 270]
                eff_img_w = img_h if is_sideways else img_w
                eff_img_h = img_w if is_sideways else img_h

                if fit_mode == FitMode.CONTAIN:
                    ratio = min(rect.width() / eff_img_w, rect.height() / eff_img_h)
                else:
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
    def _draw_pdf(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                  crop: tuple = (0.0, 0.0, 1.0, 1.0)):
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

            # Apply crop by sub-imaging the QImage
            cl, ct, cr, cb = crop
            img_w_full = qimage.width()
            img_h_full = qimage.height()
            cx0 = int(cl * img_w_full)
            cy0 = int(ct * img_h_full)
            cx1 = max(cx0 + 1, int(cr * img_w_full))
            cy1 = max(cy0 + 1, int(cb * img_h_full))
            if cx0 != 0 or cy0 != 0 or cx1 != img_w_full or cy1 != img_h_full:
                qimage = qimage.copy(cx0, cy0, cx1 - cx0, cy1 - cy0)

            fit_mode = FitMode(fit_mode_str)
            img_w = qimage.width()
            img_h = qimage.height()

            is_sideways = rotation in [90, 270]
            eff_img_w = img_h if is_sideways else img_w
            eff_img_h = img_w if is_sideways else img_h

            if fit_mode == FitMode.CONTAIN:
                ratio = min(rect.width() / eff_img_w, rect.height() / eff_img_h)
            else:
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
        from src.utils.math_text import has_math, render_math_to_qimage, strip_html, MATH_RENDER_DPI

        plain = strip_html(text_item.text)
        if has_math(plain):
            # Render with matplotlib mathtext engine at a fixed reference DPI,
            # then draw scaled to the target pixel rect.
            result = render_math_to_qimage(
                plain,
                text_item.font_size_pt,
                text_item.font_family,
                text_item.font_weight,
                text_item.color,
                dpi=MATH_RENDER_DPI,
            )
            if result is not None:
                img, tw_mm, th_mm = result
                x_mm, y_mm = ImageExporter._text_position_mm(
                    text_item, layout_result, tw_mm, th_mm)
                target = QRectF(x_mm * scale, y_mm * scale, tw_mm * scale, th_mm * scale)
                painter.drawImage(target, img)
                return
            # Fall through to Qt rendering if matplotlib failed

        base_pt = 24
        text_scale = text_item.font_size_pt / base_pt

        # Create temporary QGraphicsTextItem - same as canvas does
        temp_item = QGraphicsTextItem()
        temp_item.setHtml(text_item.text)

        font = QFont(text_item.font_family, base_pt)
        if text_item.font_weight == "bold":
            font.setBold(True)
        temp_item.setDefaultTextColor(QColor(text_item.color))

        base_rect = temp_item.boundingRect()
        tw_mm = base_rect.width() * text_scale
        th_mm = base_rect.height() * text_scale

        x_mm, y_mm = ImageExporter._text_position_mm(text_item, layout_result, tw_mm, th_mm)
        x_px = x_mm * scale
        y_px = y_mm * scale

        render_scale = text_scale * scale
        painter.save()
        painter.translate(x_px, y_px)
        painter.scale(render_scale, render_scale)
        option = QStyleOptionGraphicsItem()
        temp_item.paint(painter, option, None)
        painter.restore()

    @staticmethod
    def _text_position_mm(text_item, layout_result, tw_mm: float, th_mm: float):
        """Compute (x_mm, y_mm) top-left origin for a text item given its size."""
        if text_item.scope == "cell" and text_item.parent_id and text_item.parent_id in layout_result.cell_rects:
            cx, cy, cw, ch = layout_result.cell_rects[text_item.parent_id]
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
        return x_mm, y_mm

    @staticmethod
    def _draw_label_cells(painter: QPainter, project, layout_result, scale: float):
        """Draw label cells (label rows above picture rows) with centered text.
        
        Uses the same QGraphicsTextItem rendering approach as _draw_text to
        ensure font size matches the canvas exactly.
        """
        label_rects = getattr(layout_result, 'label_rects', {})
        if not label_rects:
            return

        # Build numbering text map from TextItems
        numbering_texts = {}
        for t in project.text_items:
            if t.scope == 'cell' and getattr(t, 'subtype', None) != 'corner' and t.parent_id:
                numbering_texts[t.parent_id] = t.text

        # Use same base_pt / text_scale approach as _draw_text and TextGraphicsItem
        base_pt = 24
        font_size_pt = project.label_font_size
        text_scale = font_size_pt / base_pt

        font = QFont(project.label_font_family, base_pt)
        if project.label_font_weight == "bold":
            font.setBold(True)

        align = getattr(project, 'label_align', 'center')
        ox_mm = getattr(project, 'label_offset_x', 0.0)
        oy_mm = getattr(project, 'label_offset_y', 0.0)

        for cell_id, (lx, ly, lw, lh) in label_rects.items():
            text = numbering_texts.get(cell_id, "")
            if not text:
                continue

            # Create a temporary QGraphicsTextItem to measure and render
            temp_item = QGraphicsTextItem()
            temp_item.setPlainText(text)
            temp_item.setFont(font)
            temp_item.setDefaultTextColor(QColor(project.label_color))

            base_rect = temp_item.boundingRect()
            tw_mm = base_rect.width() * text_scale
            th_mm = base_rect.height() * text_scale

            # Position within label cell (mm), applying alignment and offsets
            cell_x_mm = lx + ox_mm
            cell_y_mm = ly + oy_mm
            cell_w_mm = lw
            cell_h_mm = lh

            # Vertical: center in label cell
            y_mm = cell_y_mm + (cell_h_mm - th_mm) / 2.0

            # Horizontal: align within label cell
            if align == 'left':
                x_mm = cell_x_mm
            elif align == 'right':
                x_mm = cell_x_mm + cell_w_mm - tw_mm
            else:
                x_mm = cell_x_mm + (cell_w_mm - tw_mm) / 2.0

            # Render using painter.scale — same approach as _draw_text
            render_scale = text_scale * scale
            painter.save()
            painter.translate(x_mm * scale, y_mm * scale)
            painter.scale(render_scale, render_scale)

            option = QStyleOptionGraphicsItem()
            temp_item.paint(painter, option, None)
            painter.restore()

    @staticmethod
    def _draw_scale_bar(painter: QPainter, obj, content_rect: QRectF, scale: float, fit_mode_override=None):
        """Draw scale bar on the exported image (works for Cell or PiPItem)."""
        # Ensure we have all necessary attributes (PiPItem/Cell compatibility)
        um_per_px = getattr(obj, "scale_bar_um_per_px", 0.1301)
        if um_per_px <= 0:
            um_per_px = 0.1301
        
        length_um = getattr(obj, "scale_bar_length_um", 10.0)
        unit = getattr(obj, "scale_bar_unit", "µm")
        thickness_mm = getattr(obj, "scale_bar_thickness_mm", 0.5)
        color = getattr(obj, "scale_bar_color", "#FFFFFF")
        show_text = getattr(obj, "scale_bar_show_text", True)
        custom_text = getattr(obj, "scale_bar_custom_text", None)
        text_size_mm = getattr(obj, "scale_bar_text_size_mm", 2.0)
        position = getattr(obj, "scale_bar_position", "bottom_right")
        offset_x = getattr(obj, "scale_bar_offset_x", 2.0)
        offset_y = getattr(obj, "scale_bar_offset_y", 2.0)

        # Get image dimensions for scale calculation
        from PIL import Image
        img_path = getattr(obj, "image_path", None)
        try:
            if img_path and os.path.exists(img_path):
                with Image.open(img_path) as img:
                    orig_w, orig_h = img.size
            else:
                orig_w, orig_h = 1000, 1000
        except Exception:
            orig_w, orig_h = 1000, 1000
        
        # Crop
        cl = getattr(obj, "crop_left", 0.0)
        ct = getattr(obj, "crop_top", 0.0)
        cr = getattr(obj, "crop_right", 1.0)
        cb = getattr(obj, "crop_bottom", 1.0)
        eff_orig_w = orig_w * max(0.001, cr - cl)
        eff_orig_h = orig_h * max(0.001, cb - ct)

        # Rotation
        rotation = getattr(obj, 'rotation', 0)
        is_sideways = rotation in [90, 270]
        eff_pix_w = eff_orig_h if is_sideways else eff_orig_w
        eff_pix_h = eff_orig_w if is_sideways else eff_orig_h

        # Calculate bar length in source pixels
        bar_length_px = length_um / um_per_px
        
        # Calculate actual image rectangle and scale factor
        if fit_mode_override == "stretch":
            scale_ratio = content_rect.width() / eff_pix_w
            img_rect = content_rect
        else:
            fit_mode_str = getattr(obj, "fit_mode", "contain")
            from src.model.enums import FitMode
            fit_mode = FitMode(fit_mode_str)
            if fit_mode == FitMode.CONTAIN:
                scale_ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            else:  # COVER
                scale_ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
            
            new_w = eff_pix_w * scale_ratio
            new_h = eff_pix_h * scale_ratio
            img_rect = QRectF(
                content_rect.left() + (content_rect.width() - new_w) / 2,
                content_rect.top() + (content_rect.height() - new_h) / 2,
                new_w, new_h
            )
        
        # Bar length in output pixels
        bar_length_out = bar_length_px * scale_ratio
        bar_thickness_out = thickness_mm * scale
        
        ox = offset_x * scale
        oy = offset_y * scale
        bar_y = img_rect.bottom() - oy - bar_thickness_out
        
        if position == "bottom_left":
            bar_x = img_rect.left() + ox
        elif position == "bottom_center":
            bar_x = img_rect.left() + (img_rect.width() - bar_length_out) / 2
        else:  # bottom_right
            bar_x = img_rect.right() - ox - bar_length_out
        
        painter.fillRect(QRectF(bar_x, bar_y, bar_length_out, bar_thickness_out), QColor(color))
        
        if show_text:
            if custom_text:
                text = custom_text
            else:
                factor = {"m": 1e6, "cm": 1e4, "dm": 1e5, "mm": 1e3, "µm": 1.0, "nm": 1e-3, "pm": 1e-6, "fm": 1e-9}.get(unit, 1.0)
                display_val = length_um / factor
                text = f"{display_val:.0f} {unit}" if display_val >= 1 or display_val == 0 else f"{display_val:.2f} {unit}"

            base_pt = 24
            text_scale = text_size_mm / base_pt
            render_scale = text_scale * scale

            temp_item = QGraphicsTextItem()
            temp_item.setPlainText(text)
            temp_item.setFont(QFont("Arial", base_pt))
            temp_item.setDefaultTextColor(QColor(color))

            br = temp_item.boundingRect()
            tw_out = br.width() * render_scale
            th_out = br.height() * render_scale

            tx_out = bar_x + (bar_length_out - tw_out) / 2
            ty_out = bar_y - th_out

            painter.save()
            painter.translate(tx_out, ty_out)
            painter.scale(render_scale, render_scale)
            option = QStyleOptionGraphicsItem()
            temp_item.paint(painter, option, None)
            painter.restore()
