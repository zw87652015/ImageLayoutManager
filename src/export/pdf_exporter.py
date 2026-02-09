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
            
            label_row_above = getattr(project, 'label_placement', 'in_cell') == 'label_row_above'
            label_rects = getattr(layout_result, 'label_rects', {})

            # 1. Draw Images, Scale Bars, and Nested Layouts
            for cell in project.get_all_leaf_cells():
                if cell.id not in layout_result.cell_rects:
                    continue
                x_mm, y_mm, w_mm, h_mm = layout_result.cell_rects[cell.id]

                # Convert rect to dots
                target_rect = QRectF(
                    x_mm * scale, y_mm * scale, w_mm * scale, h_mm * scale
                )

                # Apply Padding
                p_top = cell.padding_top * scale
                p_right = cell.padding_right * scale
                p_bottom = cell.padding_bottom * scale
                p_left = cell.padding_left * scale
                content_rect = target_rect.adjusted(p_left, p_top, -p_right, -p_bottom)

                if content_rect.width() <= 0 or content_rect.height() <= 0:
                    continue

                # Nested layout: vector render the sub-project into this cell
                nested_path = getattr(cell, 'nested_layout_path', None)
                if nested_path and os.path.exists(nested_path):
                    PdfExporter._draw_nested_layout(painter, nested_path, content_rect, project.dpi)
                elif cell.image_path and os.path.exists(cell.image_path):
                    rotation = getattr(cell, 'rotation', 0)
                    PdfExporter._draw_image(painter, cell.image_path, content_rect, cell.fit_mode, rotation)

                    # Draw scale bar if enabled
                    if getattr(cell, 'scale_bar_enabled', False):
                        PdfExporter._draw_scale_bar(painter, cell, content_rect, scale)

            # 1b. Draw Label Cells (label rows above picture rows)
            if label_row_above:
                PdfExporter._draw_label_cells(painter, project, layout_result, scale)
                        
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
                PdfExporter._draw_text(painter, project, text_item, layout_result, scale)
                
        finally:
            painter.end()

    @staticmethod
    def _draw_nested_layout(painter: QPainter, figlayout_path: str, content_rect: QRectF, parent_dpi: int):
        """Render a nested .figlayout as vector graphics into the given content_rect.
        
        The sub-project is loaded, laid out, and all its elements (images, text,
        labels) are drawn using the same vector pipeline, translated and scaled
        to fit inside content_rect while preserving aspect ratio.
        """
        try:
            from src.model.data_model import Project as SubProject
            sub_project = SubProject.load_from_file(figlayout_path)
        except Exception as e:
            print(f"Failed to load nested layout {figlayout_path}: {e}")
            return

        sub_layout = LayoutEngine.calculate_layout(sub_project)

        # Sub-project page dimensions in mm
        sub_w_mm = sub_project.page_width_mm
        sub_h_mm = sub_project.page_height_mm
        if sub_w_mm <= 0 or sub_h_mm <= 0:
            return

        # content_rect is in dots (parent_dpi). Convert to mm for ratio calc.
        parent_scale = parent_dpi / 25.4
        cr_w_mm = content_rect.width() / parent_scale
        cr_h_mm = content_rect.height() / parent_scale

        # Fit sub-project page into content_rect (contain mode)
        fit_ratio = min(cr_w_mm / sub_w_mm, cr_h_mm / sub_h_mm)

        # Centered offset in mm
        fitted_w_mm = sub_w_mm * fit_ratio
        fitted_h_mm = sub_h_mm * fit_ratio
        offset_x_mm = (cr_w_mm - fitted_w_mm) / 2.0
        offset_y_mm = (cr_h_mm - fitted_h_mm) / 2.0

        # The sub-project's internal scale: mm -> dots for the sub-project
        # We need to map sub-project mm coordinates into parent dots.
        # sub_mm * fit_ratio * parent_scale = parent_dots
        sub_scale = fit_ratio * parent_scale

        painter.save()
        painter.translate(
            content_rect.left() + offset_x_mm * parent_scale,
            content_rect.top() + offset_y_mm * parent_scale,
        )

        # Draw sub-project images
        for cell in sub_project.get_all_leaf_cells():
            if cell.id not in sub_layout.cell_rects:
                continue
            sx, sy, sw, sh = sub_layout.cell_rects[cell.id]
            sub_target = QRectF(sx * sub_scale, sy * sub_scale, sw * sub_scale, sh * sub_scale)

            sp_top = cell.padding_top * sub_scale
            sp_right = cell.padding_right * sub_scale
            sp_bottom = cell.padding_bottom * sub_scale
            sp_left = cell.padding_left * sub_scale
            sub_content = sub_target.adjusted(sp_left, sp_top, -sp_right, -sp_bottom)

            if sub_content.width() <= 0 or sub_content.height() <= 0:
                continue

            # Recurse for nested-in-nested
            nested = getattr(cell, 'nested_layout_path', None)
            if nested and os.path.exists(nested):
                PdfExporter._draw_nested_layout(painter, nested, sub_content, parent_dpi)
            elif cell.image_path and os.path.exists(cell.image_path):
                rotation = getattr(cell, 'rotation', 0)
                PdfExporter._draw_image(painter, cell.image_path, sub_content, cell.fit_mode, rotation)
                if getattr(cell, 'scale_bar_enabled', False):
                    PdfExporter._draw_scale_bar(painter, cell, sub_content, sub_scale)

        # Draw sub-project label cells
        sub_label_above = getattr(sub_project, 'label_placement', 'in_cell') == 'label_row_above'
        sub_label_rects = getattr(sub_layout, 'label_rects', {})
        if sub_label_above:
            PdfExporter._draw_label_cells(painter, sub_project, sub_layout, sub_scale)

        # Draw sub-project text items
        for text_item in sub_project.text_items:
            if (
                sub_label_above
                and text_item.scope == 'cell'
                and getattr(text_item, 'subtype', None) != 'corner'
                and text_item.parent_id in sub_label_rects
            ):
                continue
            PdfExporter._draw_text(painter, sub_project, text_item, sub_layout, sub_scale)

        painter.restore()

    @staticmethod
    def _draw_image(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0):
        ext = os.path.splitext(path)[1].lower()
        
        if ext == '.svg':
            PdfExporter._draw_svg(painter, path, rect, fit_mode_str, rotation)
        elif ext in ('.pdf', '.eps'):
            PdfExporter._draw_pdf(painter, path, rect, fit_mode_str, rotation)
        else:
            PdfExporter._draw_raster(painter, path, rect, fit_mode_str, rotation)
    
    @staticmethod
    def _draw_svg(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0):
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
        """Draw PDF first page as vector by converting to SVG via PyMuPDF."""
        try:
            import fitz  # PyMuPDF
            
            doc = fitz.open(path)
            if doc.page_count == 0:
                doc.close()
                return
            
            page = doc[0]
            svg_bytes = page.get_svg_image()
            doc.close()
            
            # Load SVG into Qt renderer
            svg_data = svg_bytes.encode('utf-8') if isinstance(svg_bytes, str) else svg_bytes
            renderer = QSvgRenderer(svg_data)
            if not renderer.isValid():
                print(f"Failed to create SVG renderer for PDF: {path}")
                return
            
            fit_mode = FitMode(fit_mode_str)
            
            # Use the SVG renderer's default size for aspect ratio calculation
            # This is in the same coordinate space as the renderer output
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
                draw_rect = QRectF(-img_w * ratio / 2, -img_h * ratio / 2, img_w * ratio, img_h * ratio)
                renderer.render(painter, draw_rect)
            else:
                renderer.render(painter, target_rect)
            
            painter.restore()
                
        except Exception as e:
            print(f"Failed to export PDF {path}: {e}")

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
                cell = project.find_cell_by_id(text_item.parent_id)
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
    def _draw_scale_bar(painter: QPainter, cell, content_rect: QRectF, scale: float):
        """Draw scale bar on the exported image."""
        from PIL import Image
        
        # Get image dimensions for scale calculation
        try:
            with Image.open(cell.image_path) as img:
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
        
        # Calculate scale factor from image to content rect (in dots)
        fit_mode = FitMode(cell.fit_mode)
        if fit_mode == FitMode.CONTAIN:
            scale_ratio = min(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        else:  # COVER
            scale_ratio = max(content_rect.width() / eff_pix_w, content_rect.height() / eff_pix_h)
        
        # Bar length in dots
        bar_length_dots = bar_length_px * scale_ratio
        
        # Bar thickness in dots
        bar_thickness_dots = cell.scale_bar_thickness_mm * scale
        
        # Calculate position based on scale_bar_position and offsets
        ox = cell.scale_bar_offset_x * scale
        oy = cell.scale_bar_offset_y * scale
        
        # Y position (always at bottom)
        bar_y = content_rect.bottom() - oy - bar_thickness_dots
        
        # X position based on horizontal alignment
        if cell.scale_bar_position == "bottom_left":
            bar_x = content_rect.left() + ox
        elif cell.scale_bar_position == "bottom_center":
            bar_x = content_rect.left() + (content_rect.width() - bar_length_dots) / 2
        else:  # bottom_right
            bar_x = content_rect.right() - ox - bar_length_dots
        
        # Draw the bar
        bar_rect = QRectF(bar_x, bar_y, bar_length_dots, bar_thickness_dots)
        painter.fillRect(bar_rect, QColor(cell.scale_bar_color))
        
        # Draw text if enabled
        if cell.scale_bar_show_text:
            text = f"{cell.scale_bar_length_um:.0f} µm" if cell.scale_bar_length_um >= 1 else f"{cell.scale_bar_length_um:.2f} µm"
            
            font_size_dots = 2.0 * scale
            # Compensate for QPdfWriter physical/logical DPI mismatch
            device = painter.device()
            dpi_ratio = device.physicalDpiY() / device.logicalDpiY() if device.logicalDpiY() > 0 else 1.0
            font_size_device = max(8, int(font_size_dots * dpi_ratio))
            font = QFont("Arial")
            font.setPixelSize(font_size_device)
            painter.setFont(font)
            painter.setPen(QColor(cell.scale_bar_color))
            
            # Use a wide text rect centered on the bar to avoid clipping
            text_rect_w = max(bar_length_dots, content_rect.width())
            text_rect_x = bar_x + bar_length_dots / 2 - text_rect_w / 2
            text_height = font_size_device * 3
            text_rect = QRectF(text_rect_x, bar_y - text_height, text_rect_w, text_height)
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignBottom, text)
