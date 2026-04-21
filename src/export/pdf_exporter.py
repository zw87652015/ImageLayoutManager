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

        # Determine output page size & translation. If a user-defined export
        # region is set, the PDF page becomes the region's size and all content
        # is translated so the region origin maps to (0, 0) — content outside
        # the region is naturally clipped by the page bounds.
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
        
        # Collect PDF/EPS-source cells for vector post-processing (Pass 2)
        pdf_source_cells = []  # list of (cell, content_rect_mm)
        # Collect math text items rendered as vector PDF for Pass 2 stamping.
        # Each entry: (pdf_bytes, x_mm, y_mm, w_mm, h_mm, rotation_deg)
        math_stamps = []

        painter = QPainter(writer)
        
        try:
            # Coordinate Conversion Factor: mm -> dots
            # dpi dots / inch, 1 inch = 25.4 mm
            scale = project.dpi / 25.4

            # Shift everything so the export region's top-left maps to (0,0).
            # (No-op when export_region is None: region_dx/dy are 0.)
            if region_dx_mm != 0.0 or region_dy_mm != 0.0:
                painter.translate(-region_dx_mm * scale, -region_dy_mm * scale)
            
            label_row_above = getattr(project, 'label_placement', 'in_cell') == 'label_row_above'
            label_rects = getattr(layout_result, 'label_rects', {})

            # 1. Draw Images, Scale Bars, and Nested Layouts (sorted by z_index for freeform overlap support)
            sorted_cells = sorted(project.get_all_leaf_cells(), key=lambda c: getattr(c, 'z_index', 0))
            for cell in sorted_cells:
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
                    ext = os.path.splitext(cell.image_path)[1].lower()
                    if ext in ('.pdf', '.eps'):
                        # Skip in Pass 1 — will be stamped as vector in Pass 2
                        content_x_mm = (content_rect.x()) / scale
                        content_y_mm = (content_rect.y()) / scale
                        content_w_mm = content_rect.width() / scale
                        content_h_mm = content_rect.height() / scale
                        pdf_source_cells.append((cell, (content_x_mm, content_y_mm, content_w_mm, content_h_mm)))
                    else:
                        rotation = getattr(cell, 'rotation', 0)
                        crop = (getattr(cell, 'crop_left', 0.0), getattr(cell, 'crop_top', 0.0),
                                getattr(cell, 'crop_right', 1.0), getattr(cell, 'crop_bottom', 1.0))
                        svg_override = None
                        if cell.image_path.lower().endswith('.svg'):
                            from src.utils.svg_text_utils import build_svg_overrides_for_path, apply_svg_font_overrides
                            ov = build_svg_overrides_for_path(project, cell.image_path)
                            if ov:
                                svg_override = apply_svg_font_overrides(cell.image_path, ov)
                        PdfExporter._draw_image(painter, cell.image_path, content_rect, cell.fit_mode, rotation, crop, svg_override)

                        # Draw scale bar if enabled
                        if getattr(cell, 'scale_bar_enabled', False):
                            PdfExporter._draw_scale_bar(painter, cell, content_rect, scale)

                PdfExporter._draw_pip_items(painter, cell, content_rect)

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
                PdfExporter._draw_text(painter, project, text_item, layout_result, scale,
                                       math_stamps=math_stamps)
                
        finally:
            painter.end()

        # Pass 2: stamp PDF/EPS source cells as true vector XObjects.
        # Shift source cell mm coords so they match the (possibly-cropped) PDF page origin.
        if pdf_source_cells:
            if region_dx_mm != 0.0 or region_dy_mm != 0.0:
                shifted = [
                    (cell, (cx - region_dx_mm, cy - region_dy_mm, cw, ch))
                    for cell, (cx, cy, cw, ch) in pdf_source_cells
                ]
            else:
                shifted = pdf_source_cells
            PdfExporter._stamp_pdf_sources(output_path, shifted, page_w_mm, page_h_mm)

        # Pass 2b: stamp vector-PDF math expressions on top (true matplotlib vector).
        if math_stamps:
            if region_dx_mm != 0.0 or region_dy_mm != 0.0:
                shifted_math = [
                    (pdf_bytes, x - region_dx_mm, y - region_dy_mm, w, h, rot)
                    for (pdf_bytes, x, y, w, h, rot) in math_stamps
                ]
            else:
                shifted_math = math_stamps
            PdfExporter._stamp_math(output_path, shifted_math, page_w_mm, page_h_mm)

    @staticmethod
    def _stamp_math(output_path: str, math_stamps: list, page_w_mm: float, page_h_mm: float):
        """Stamp matplotlib-rendered math PDFs onto the output page as true
        vector XObjects using PyMuPDF show_pdf_page().

        math_stamps entries: (pdf_bytes, x_mm, y_mm, w_mm, h_mm, rotation_deg)
        """
        try:
            import fitz
        except ImportError:
            print("PyMuPDF not installed — math text will not be stamped as vector.")
            return

        try:
            out_doc = fitz.open(output_path)
            out_page = out_doc[0]
            actual_w_pt = out_page.rect.width
            actual_h_pt = out_page.rect.height
            mm_to_pt_x = actual_w_pt / page_w_mm
            mm_to_pt_y = actual_h_pt / page_h_mm

            for (pdf_bytes, x_mm, y_mm, w_mm, h_mm, rotation_deg) in math_stamps:
                try:
                    src_doc = fitz.open(stream=pdf_bytes, filetype='pdf')
                    x_pt = x_mm * mm_to_pt_x
                    y_pt = y_mm * mm_to_pt_y
                    w_pt = w_mm * mm_to_pt_x
                    h_pt = h_mm * mm_to_pt_y
                    dest = fitz.Rect(x_pt, y_pt, x_pt + w_pt, y_pt + h_pt)
                    # PyMuPDF's `rotate` only accepts multiples of 90; for
                    # arbitrary angles we still stamp upright (rotation == 0).
                    rotate = int(rotation_deg) if rotation_deg in (0, 90, 180, 270) else 0
                    out_page.show_pdf_page(
                        dest, src_doc, pno=0,
                        rotate=rotate,
                        keep_proportion=True,
                        overlay=True,
                    )
                    src_doc.close()
                except Exception as exc:
                    print(f"Failed to stamp math PDF: {exc}")

            import tempfile, shutil
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp_path = tmp.name
            out_doc.save(tmp_path, incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
            out_doc.close()
            shutil.move(tmp_path, output_path)
        except Exception as exc:
            print(f"Failed in math PDF stamping: {exc}")

    @staticmethod
    def _stamp_pdf_sources(output_path: str, pdf_source_cells: list, page_w_mm: float, page_h_mm: float):
        """Post-process the exported PDF to replace PDF/EPS source cells with
        true vector XObjects using PyMuPDF show_pdf_page().

        Coordinate system: QPdfWriter uses top-left origin (mm), PyMuPDF uses
        bottom-left origin (points, 1pt = 1/72 inch).
        """
        try:
            import fitz
        except ImportError:
            print("PyMuPDF not installed — PDF source cells will be blank in output.")
            return

        try:
            out_doc = fitz.open(output_path)
            out_page = out_doc[0]  # single-page export

            # Use the ACTUAL page dimensions from the PDF (QPdfWriter rounds to integer pts)
            # so that vector-stamped cells align exactly with QPainter-drawn elements.
            actual_w_pt = out_page.rect.width
            actual_h_pt = out_page.rect.height
            mm_to_pt_x = actual_w_pt / page_w_mm
            mm_to_pt_y = actual_h_pt / page_h_mm

            for cell, (cx_mm, cy_mm, cw_mm, ch_mm) in pdf_source_cells:
                src_path = cell.image_path
                if not src_path or not os.path.exists(src_path):
                    continue

                crop = (getattr(cell, 'crop_left', 0.0), getattr(cell, 'crop_top', 0.0),
                        getattr(cell, 'crop_right', 1.0), getattr(cell, 'crop_bottom', 1.0))
                fit_mode_str = getattr(cell, 'fit_mode', 'contain')
                rotation = getattr(cell, 'rotation', 0)
                cl, ct, cr, cb = crop

                try:
                    src_doc = fitz.open(src_path)
                    src_page = src_doc[0]
                    src_w_pt = src_page.rect.width
                    src_h_pt = src_page.rect.height

                    # Cropped source region in points
                    src_clip = fitz.Rect(
                        cl * src_w_pt, ct * src_h_pt,
                        cr * src_w_pt, cb * src_h_pt
                    )

                    # Target content rect in points.
                    # PyMuPDF uses top-left origin (same as Qt), no Y-flip needed.
                    cx_pt = cx_mm * mm_to_pt_x
                    cy_pt = cy_mm * mm_to_pt_y
                    cw_pt = cw_mm * mm_to_pt_x
                    ch_pt = ch_mm * mm_to_pt_y

                    # Destination rect = exact content cell (show_pdf_page fits src into it)
                    clip_rect = fitz.Rect(cx_pt, cy_pt, cx_pt + cw_pt, cy_pt + ch_pt)

                    # overlay=False: stamp underneath existing QPainter content
                    # (text, labels, PiPs drawn in Pass 1 must remain on top)
                    out_page.show_pdf_page(
                        clip_rect,      # destination = exact content cell rect (handles clipping)
                        src_doc,
                        pno=0,
                        clip=src_clip,  # source crop region
                        rotate=rotation,
                        keep_proportion=True,
                        overlay=False,
                    )

                    src_doc.close()
                except Exception as e:
                    print(f"Failed to stamp PDF source {src_path}: {e}")

            import tempfile, shutil
            with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as tmp:
                tmp_path = tmp.name
            out_doc.save(tmp_path, incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
            out_doc.close()
            shutil.move(tmp_path, output_path)

        except Exception as e:
            print(f"Failed in PDF vector post-processing: {e}")

    @staticmethod
    def _draw_pip_items(painter: QPainter, cell, content_rect: QRectF):
        """Draw all PiP insets for a cell onto the given content_rect."""
        from PyQt6.QtGui import QPen
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
            if pip.pip_type == "zoom" and cell.image_path and os.path.exists(cell.image_path):
                PdfExporter._draw_raster_cropped(
                    painter, cell.image_path, inset_rect, "contain", 0,
                    (pip.crop_left, pip.crop_top, pip.crop_right, pip.crop_bottom)
                )
            elif pip.pip_type == "external" and pip.image_path and os.path.exists(pip.image_path):
                PdfExporter._draw_image(painter, pip.image_path, inset_rect, "contain", 0)
            painter.restore()
            if pip.border_enabled:
                bpen = QPen(QColor(pip.border_color))
                bpen.setWidthF(pip.border_width_pt)
                bpen.setCosmetic(True)
                if getattr(pip, 'border_style', 'solid') == 'dashed':
                    bpen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(bpen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(inset_rect)
            if pip.pip_type == "zoom" and getattr(pip, 'show_origin_box', False):
                origin_rect = QRectF(
                    content_rect.x() + pip.crop_left * cw,
                    content_rect.y() + pip.crop_top * ch,
                    (pip.crop_right - pip.crop_left) * cw,
                    (pip.crop_bottom - pip.crop_top) * ch,
                )
                open_pen = QPen(QColor(pip.origin_box_color))
                open_pen.setWidthF(pip.origin_box_width_pt)
                open_pen.setCosmetic(True)
                if getattr(pip, 'origin_box_style', 'solid') == 'dashed':
                    open_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(open_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(origin_rect)

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
                crop = (getattr(cell, 'crop_left', 0.0), getattr(cell, 'crop_top', 0.0),
                        getattr(cell, 'crop_right', 1.0), getattr(cell, 'crop_bottom', 1.0))
                PdfExporter._draw_image(painter, cell.image_path, sub_content, cell.fit_mode, rotation, crop)
                if getattr(cell, 'scale_bar_enabled', False):
                    PdfExporter._draw_scale_bar(painter, cell, sub_content, sub_scale)

            PdfExporter._draw_pip_items(painter, cell, sub_content)

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
    def _draw_image(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                    crop: tuple = (0.0, 0.0, 1.0, 1.0), svg_override_bytes: bytes = None):
        ext = os.path.splitext(path)[1].lower()

        if ext == '.svg':
            PdfExporter._draw_svg(painter, path, rect, fit_mode_str, rotation, crop, svg_override_bytes)
        elif ext in ('.pdf', '.eps'):
            PdfExporter._draw_pdf(painter, path, rect, fit_mode_str, rotation, crop)
        else:
            PdfExporter._draw_raster(painter, path, rect, fit_mode_str, rotation, crop)

    @staticmethod
    def _draw_svg(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                  crop: tuple = (0.0, 0.0, 1.0, 1.0), svg_override_bytes: bytes = None):
        """Draw SVG vector image - renders as vector in PDF for best quality."""
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
            if default_size.isEmpty():
                img_w, img_h = rect.width(), rect.height()
            else:
                img_w, img_h = default_size.width(), default_size.height()

            cl, ct, cr, cb = crop
            crop_w_frac = max(0.001, cr - cl)
            crop_h_frac = max(0.001, cb - ct)

            is_sideways = rotation in [90, 270]
            eff_crop_w = (img_h * crop_h_frac) if is_sideways else (img_w * crop_w_frac)
            eff_crop_h = (img_w * crop_w_frac) if is_sideways else (img_h * crop_h_frac)

            if fit_mode == FitMode.CONTAIN:
                ratio = min(rect.width() / eff_crop_w, rect.height() / eff_crop_h)
            else:
                ratio = max(rect.width() / eff_crop_w, rect.height() / eff_crop_h)

            crop_canvas_w = eff_crop_w * ratio
            crop_canvas_h = eff_crop_h * ratio
            crop_x = rect.left() + (rect.width() - crop_canvas_w) / 2
            crop_y = rect.top() + (rect.height() - crop_canvas_h) / 2

            full_w = img_w * ratio
            full_h = img_h * ratio
            full_x = crop_x - cl * full_w
            full_y = crop_y - ct * full_h
            target_rect = QRectF(full_x, full_y, full_w, full_h)

            painter.save()
            painter.setClipRect(QRectF(crop_x, crop_y, crop_canvas_w, crop_canvas_h))

            if rotation != 0:
                center = QRectF(crop_x, crop_y, crop_canvas_w, crop_canvas_h).center()
                painter.translate(center)
                painter.rotate(rotation)
                draw_rect = QRectF(-img_w * ratio / 2, -img_h * ratio / 2, img_w * ratio, img_h * ratio)
                renderer.render(painter, draw_rect)
            else:
                renderer.render(painter, target_rect)

            painter.restore()

        except Exception as e:
            print(f"Failed to export SVG {path}: {e}")
    
    @staticmethod
    def _draw_raster_cropped(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str,
                             rotation: int = 0, crop: tuple = (0.0, 0.0, 1.0, 1.0)):
        """Draw raster image with a fractional crop region (cl, ct, cr, cb)."""
        try:
            with Image.open(path) as img:
                if img.mode != 'RGBA':
                    img = img.convert('RGBA')
                cl, ct, cr, cb = crop
                fw, fh = img.width, img.height
                cx0, cy0 = int(cl * fw), int(ct * fh)
                cx1, cy1 = max(cx0 + 1, int(cr * fw)), max(cy0 + 1, int(cb * fh))
                if cx0 != 0 or cy0 != 0 or cx1 != fw or cy1 != fh:
                    img = img.crop((cx0, cy0, cx1, cy1))
                data = img.tobytes("raw", "RGBA")
                qimage = QImage(data, img.width, img.height, QImage.Format.Format_RGBA8888)
                fit_mode = FitMode(fit_mode_str)
                iw, ih = qimage.width(), qimage.height()
                is_sideways = rotation in [90, 270]
                ew = ih if is_sideways else iw
                eh = iw if is_sideways else ih
                if fit_mode == FitMode.CONTAIN:
                    ratio = min(rect.width() / ew, rect.height() / eh)
                else:
                    ratio = max(rect.width() / ew, rect.height() / eh)
                nw, nh = ew * ratio, eh * ratio
                x = rect.left() + (rect.width() - nw) / 2
                y = rect.top() + (rect.height() - nh) / 2
                target = QRectF(x, y, nw, nh)
                painter.save()
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
                painter.drawImage(target, qimage)
                painter.restore()
        except Exception as e:
            print(f"Failed to export cropped image {path}: {e}")

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
        """Draw PDF/EPS first page as high-res raster via PyMuPDF.

        True vector passthrough into a QPdfWriter stream is not supported by
        Qt/PyMuPDF APIs. Instead we rasterise at a zoom that exactly matches
        the output rect's pixel size, so the embedded raster is at the full
        export DPI (e.g. 600 DPI) — indistinguishable from vector in print.
        """
        try:
            import fitz  # PyMuPDF

            doc = fitz.open(path)
            if doc.page_count == 0:
                doc.close()
                return

            page = doc[0]
            # PDF natural size is in points (72 dpi). Zoom to match rect in dots.
            page_rect = page.rect  # in points
            cl, ct, cr, cb = crop
            cropped_w_pts = max(1.0, (cr - cl) * page_rect.width)
            cropped_h_pts = max(1.0, (cb - ct) * page_rect.height)
            zoom_x = rect.width() / cropped_w_pts
            zoom_y = rect.height() / cropped_h_pts
            zoom = max(zoom_x, zoom_y) if FitMode(fit_mode_str) == FitMode.COVER \
                else min(zoom_x, zoom_y)
            zoom = max(zoom, 1.0)  # never render below 1× (72 dpi)
            matrix = fitz.Matrix(zoom, zoom)
            pix = page.get_pixmap(matrix=matrix, alpha=True)
            doc.close()

            qimage = QImage(pix.samples, pix.width, pix.height, pix.stride,
                            QImage.Format.Format_RGBA8888).copy()

            # Apply crop
            cl, ct, cr, cb = crop
            iw, ih = qimage.width(), qimage.height()
            cx0, cy0 = int(cl * iw), int(ct * ih)
            cx1, cy1 = max(cx0 + 1, int(cr * iw)), max(cy0 + 1, int(cb * ih))
            if cx0 != 0 or cy0 != 0 or cx1 != iw or cy1 != ih:
                qimage = qimage.copy(cx0, cy0, cx1 - cx0, cy1 - cy0)

            fit_mode = FitMode(fit_mode_str)
            img_w, img_h = qimage.width(), qimage.height()

            is_sideways = rotation in [90, 270]
            eff_w = img_h if is_sideways else img_w
            eff_h = img_w if is_sideways else img_h

            if fit_mode == FitMode.CONTAIN:
                ratio = min(rect.width() / eff_w, rect.height() / eff_h)
            else:
                ratio = max(rect.width() / eff_w, rect.height() / eff_h)

            nw, nh = eff_w * ratio, eff_h * ratio
            x = rect.left() + (rect.width() - nw) / 2
            y = rect.top() + (rect.height() - nh) / 2
            target_rect = QRectF(x, y, nw, nh)

            painter.save()
            if fit_mode == FitMode.COVER:
                painter.setClipRect(rect)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            if rotation != 0:
                painter.translate(target_rect.center())
                painter.rotate(rotation)
                draw_rect = QRectF(-img_w * ratio / 2, -img_h * ratio / 2,
                                   img_w * ratio, img_h * ratio)
                painter.drawImage(draw_rect, qimage)
            else:
                painter.drawImage(target_rect, qimage)
            painter.restore()

        except Exception as e:
            print(f"Failed to export PDF {path}: {e}")

    @staticmethod
    def _draw_text(painter: QPainter, project: Project, text_item, layout_result,
                   scale: float, math_stamps: list = None):
        from src.utils.math_text import (
            has_math, render_math_to_qimage, render_math_to_svg,
            render_math_to_pdf_bytes, strip_html, MATH_RENDER_DPI,
        )
        from src.export.image_exporter import ImageExporter

        plain = strip_html(text_item.text)
        if has_math(plain):
            # Prefer matplotlib-native vector PDF (same mechanism the
            # violin_plot_generator script uses). Stamped in Pass 2 via
            # PyMuPDF so the glyphs stay true vector in the output.
            if math_stamps is not None:
                pdf_result = render_math_to_pdf_bytes(
                    plain,
                    text_item.font_size_pt,
                    text_item.font_family,
                    text_item.font_weight,
                    text_item.color,
                )
                if pdf_result is not None:
                    pdf_bytes, tw_mm, th_mm = pdf_result
                    x_mm, y_mm = ImageExporter._text_position_mm(
                        text_item, layout_result, tw_mm, th_mm)
                    is_global = not (text_item.scope == "cell" and text_item.parent_id
                                     and text_item.parent_id in layout_result.cell_rects)
                    rotation_deg = float(getattr(text_item, 'rotation', 0.0)) if is_global else 0.0
                    math_stamps.append((pdf_bytes, x_mm, y_mm, tw_mm, th_mm, rotation_deg))
                    return

            svg_result = render_math_to_svg(
                plain,
                text_item.font_size_pt,
                text_item.font_family,
                text_item.font_weight,
                text_item.color,
            )
            if svg_result is not None:
                svg_bytes, tw_mm, th_mm = svg_result
                x_mm, y_mm = ImageExporter._text_position_mm(text_item, layout_result, tw_mm, th_mm)
                
                is_global = not (text_item.scope == "cell" and text_item.parent_id
                                 and text_item.parent_id in layout_result.cell_rects)
                rotation_deg = float(getattr(text_item, 'rotation', 0.0)) if is_global else 0.0

                from PyQt6.QtCore import QRectF, QByteArray
                from PyQt6.QtSvg import QSvgRenderer
                target = QRectF(0, 0, tw_mm * scale, th_mm * scale)
                renderer = QSvgRenderer(QByteArray(svg_bytes))
                
                painter.save()
                painter.translate(x_mm * scale, y_mm * scale)
                if rotation_deg:
                    painter.translate(tw_mm * scale / 2.0, th_mm * scale / 2.0)
                    painter.rotate(rotation_deg)
                    painter.translate(-tw_mm * scale / 2.0, -th_mm * scale / 2.0)
                renderer.render(painter, target)
                painter.restore()
                return

            # Fallback to raster if SVG fails
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
                x_mm, y_mm = ImageExporter._text_position_mm(text_item, layout_result, tw_mm, th_mm)
                
                is_global = not (text_item.scope == "cell" and text_item.parent_id
                                 and text_item.parent_id in layout_result.cell_rects)
                rotation_deg = float(getattr(text_item, 'rotation', 0.0)) if is_global else 0.0

                from PyQt6.QtCore import QRectF
                target = QRectF(0, 0, tw_mm * scale, th_mm * scale)
                
                painter.save()
                painter.translate(x_mm * scale, y_mm * scale)
                if rotation_deg:
                    painter.translate(tw_mm * scale / 2.0, th_mm * scale / 2.0)
                    painter.rotate(rotation_deg)
                    painter.translate(-tw_mm * scale / 2.0, -th_mm * scale / 2.0)
                painter.drawImage(target, img)
                painter.restore()
                return

        base_pt = 24
        text_scale = text_item.font_size_pt / base_pt

        temp_item = QGraphicsTextItem()
        temp_item.setHtml(text_item.text)

        font = QFont(text_item.font_family, base_pt)
        if text_item.font_weight == "bold":
            font.setBold(True)
        temp_item.setFont(font)
        temp_item.setDefaultTextColor(QColor(text_item.color))

        base_rect = temp_item.boundingRect()
        tw_mm = base_rect.width() * text_scale
        th_mm = base_rect.height() * text_scale

        x_mm, y_mm = ImageExporter._text_position_mm(text_item, layout_result, tw_mm, th_mm)

        # Canvas applies scale & rotation about the unscaled bounding-rect
        # centre for GLOBAL (floating) text. Mirror that here so the exported
        # visual top-left matches the on-canvas position:
        #   visual_topleft = (x, y) + (1 - s) * br/2
        is_global = not (text_item.scope == "cell" and text_item.parent_id
                         and text_item.parent_id in layout_result.cell_rects)
        if is_global:
            offset_x_mm = (base_rect.width() - tw_mm) / 2.0
            offset_y_mm = (base_rect.height() - th_mm) / 2.0
            x_mm += offset_x_mm
            y_mm += offset_y_mm

        x_dots = x_mm * scale
        y_dots = y_mm * scale

        render_scale = text_scale * scale

        painter.save()
        painter.translate(x_dots, y_dots)
        # Rotation around the scaled rect centre (same as canvas).
        rotation_deg = float(getattr(text_item, 'rotation', 0.0)) if is_global else 0.0
        if rotation_deg:
            painter.translate(tw_mm * scale / 2.0, th_mm * scale / 2.0)
            painter.rotate(rotation_deg)
            painter.translate(-tw_mm * scale / 2.0, -th_mm * scale / 2.0)
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

        # µm per pixel — value stored on the cell (set by the user via the inspector)
        um_per_px = getattr(cell, 'scale_bar_um_per_px', 0.1301)
        if um_per_px <= 0:
            um_per_px = 0.1301
        
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
            # Use custom text if provided, otherwise auto-generate from length
            custom_text = getattr(cell, 'scale_bar_custom_text', None)
            if custom_text:
                text = custom_text
            else:
                text = f"{cell.scale_bar_length_um:.0f} µm" if cell.scale_bar_length_um >= 1 else f"{cell.scale_bar_length_um:.2f} µm"

            # WYSIWYG: same QGraphicsTextItem + painter.scale() pattern used by
            # the canvas and the label exporter. No DPI-ratio compensation is
            # needed because the painter's own transform already maps
            # painter-units to device pixels correctly.
            text_size_mm = getattr(cell, 'scale_bar_text_size_mm', 2.0)
            base_pt = 24
            text_scale = text_size_mm / base_pt        # 1 local unit → text_scale mm
            render_scale = text_scale * scale          # 1 local unit → render_scale painter-dots

            temp_item = QGraphicsTextItem()
            temp_item.setPlainText(text)
            temp_item.setFont(QFont("Arial", base_pt))
            temp_item.setDefaultTextColor(QColor(cell.scale_bar_color))

            br = temp_item.boundingRect()
            tw_dots = br.width() * render_scale
            th_dots = br.height() * render_scale

            tx_dots = bar_x + (bar_length_dots - tw_dots) / 2
            ty_dots = bar_y - th_dots

            painter.save()
            painter.translate(tx_dots, ty_dots)
            painter.scale(render_scale, render_scale)
            option = QStyleOptionGraphicsItem()
            temp_item.paint(painter, option, None)
            painter.restore()
