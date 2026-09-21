from PyQt6.QtGui import QPainter, QFont, QImage, QColor
from PyQt6.QtCore import QRectF, Qt
from PyQt6.QtWidgets import QGraphicsTextItem, QStyleOptionGraphicsItem
from PyQt6.QtSvg import QSvgRenderer
from PIL import Image
from dataclasses import dataclass, field
import ntpath
import os
import stat
import unicodedata
from src.model.data_model import Project, Cell
from src.model.enums import FitMode
from src.model.layout_engine import LayoutEngine
from src.utils.figpack.encoding import sanitize_basename
from src.utils.plot_alignment import resolve_image_placements, content_rect as cell_content_rect


@dataclass(frozen=True)
class SourceImage:
    path: str | None
    filename: str
    reference: str


@dataclass
class SourceImageExportResult:
    copied: list[str] = field(default_factory=list)
    failures: list[tuple[str, str]] = field(default_factory=list)
    cancelled: bool = False


class ImageExporter:
    """Export project to raster image formats (TIFF, JPG, PNG)."""
    
    @staticmethod
    def collect_source_images(project: Project, project_dir: str | None = None,
                              bundle_dir: str | None = None) -> list[SourceImage]:
        sources: list[SourceImage] = []
        seen: set[tuple[str, str]] = set()

        def add_source(current: str | None, sticky: str | None = None):
            if not current and not (current is None and sticky):
                return
            reference = sticky or current
            if current:
                if os.path.isabs(current):
                    candidates = [current]
                else:
                    candidates = [os.path.join(directory, current)
                                  for directory in (bundle_dir, project_dir)
                                  if directory is not None]
                    if not candidates:
                        candidates = [os.path.join(os.getcwd(), current)]
                path = next((candidate for candidate in candidates if os.path.isfile(candidate)),
                            candidates[0])
                path = os.path.normcase(os.path.realpath(path))
                key = ('path', path)
            else:
                path = None
                key = ('missing', reference)
            if key in seen:
                return
            seen.add(key)
            sources.append(SourceImage(
                path=path, filename=sanitize_basename(ntpath.basename(reference)),
                reference=reference,
            ))

        for cell in project.get_all_leaf_cells():
            add_source(cell.image_path, cell.original_source_path)
            for pip in cell.pip_items:
                if pip.pip_type == 'external' and pip.image_path:
                    add_source(pip.image_path)
        return sources

    @staticmethod
    def export_source_images(sources: list[SourceImage], output_dir: str, *,
                             progress=None, cancel=None) -> SourceImageExportResult:
        if not os.path.isdir(output_dir):
            raise NotADirectoryError(f'Output directory does not exist or is not a directory: {output_dir}')
        output_dir = os.path.abspath(output_dir)
        result = SourceImageExportResult()

        def name_key(name: str) -> str:
            return unicodedata.normalize('NFC', name).casefold()

        def source_opener(path: str, flags: int) -> int:
            return os.open(path, flags | getattr(os, 'O_NONBLOCK', 0))

        with os.scandir(output_dir) as entries:
            used_names = {name_key(entry.name) for entry in entries}
        total = len(sources)
        for completed, source in enumerate(sources):
            if cancel is not None and cancel():
                result.cancelled = True
                break
            if progress is not None:
                progress(completed, total, source.reference)
            destination = None
            destination_stat = None
            copied = False
            failure = None
            try:
                if source.path is None:
                    raise FileNotFoundError('Source image is unavailable; its current image path is missing.')
                if not stat.S_ISREG(os.stat(source.path).st_mode):
                    raise OSError(f'Source image is not a regular file: {source.path}')
                with open(source.path, 'rb', opener=source_opener) as source_file:
                    if not stat.S_ISREG(os.fstat(source_file.fileno()).st_mode):
                        raise OSError(f'Source image is not a regular file: {source.path}')
                    filename = sanitize_basename(ntpath.basename(source.filename))
                    stem, extension = os.path.splitext(filename)
                    suffix = 0
                    while True:
                        if cancel is not None and cancel():
                            result.cancelled = True
                            break
                        candidate = filename if suffix == 0 else f'{stem}_{suffix}{extension}'
                        suffix += 1
                        key = name_key(candidate)
                        if key in used_names:
                            continue
                        used_names.add(key)
                        candidate_path = os.path.join(output_dir, candidate)
                        try:
                            output_file = open(candidate_path, 'xb')
                        except FileExistsError:
                            continue
                        destination = candidate_path
                        with output_file:
                            destination_stat = os.fstat(output_file.fileno())
                            while True:
                                if cancel is not None and cancel():
                                    result.cancelled = True
                                    break
                                chunk = source_file.read(1024 * 1024)
                                if not chunk:
                                    break
                                output_file.write(chunk)
                        break
                if not result.cancelled:
                    copied = True
                    result.copied.append(destination)
            except (OSError, ValueError) as error:
                failure = str(error) or type(error).__name__
            finally:
                if destination is not None and not copied:
                    try:
                        current_stat = os.stat(destination, follow_symlinks=False)
                        if destination_stat is None or os.path.samestat(destination_stat, current_stat):
                            os.unlink(destination)
                    except FileNotFoundError:
                        pass
                    except OSError as error:
                        failure = f'{failure + "; " if failure else ""}Could not remove partial file: {error}'
            if failure is not None:
                result.failures.append((source.reference, failure))
            if progress is not None:
                progress(completed if result.cancelled else completed + 1, total, source.reference)
            if result.cancelled:
                break
        return result

    @staticmethod
    def export(project: Project, output_path: str, format: str = "TIFF",
               color_mode: str = "rgb", icc_profile_path: str = None,
               rendering_intent: int = 1):
        """
        Export project to a raster image.

        Args:
            project: The project to export
            output_path: Output file path
            format: Image format - "TIFF", "JPG", "JPEG", or "PNG"
        """
        # Calculate Layout (mm)
        layout_result = LayoutEngine.calculate_layout(project)
        layout_result._image_placements = resolve_image_placements(project, layout_result, strict=True)
        layout_result._image_placements_strict = True

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
            label_rects = getattr(layout_result, 'label_rects', {})

            # 1. Draw Images and Scale Bars (sorted by z_index for freeform overlap support)
            sorted_cells = sorted(project.get_all_leaf_cells(), key=lambda c: getattr(c, 'z_index', 0))
            for cell in sorted_cells:
                if cell.id not in layout_result.cell_rects:
                    continue
                x_mm, y_mm, w_mm, h_mm = layout_result.cell_rects[cell.id]

                target_rect = QRectF(
                    x_mm * scale, y_mm * scale, w_mm * scale, h_mm * scale
                )

                content_rect = QRectF(*(v * scale for v in cell_content_rect(
                    cell, (x_mm, y_mm, w_mm, h_mm), project.layout_mode)))
                placement = layout_result._image_placements.placements.get(cell.id)

                if content_rect.width() <= 0 or content_rect.height() <= 0:
                    continue

                if placement is not None:
                    from src.utils.text_overrides import overrides_for_cell
                    svg_override, raster_override = overrides_for_cell(
                        project, cell, layout_result,
                        (content_rect.width() / scale, content_rect.height() / scale))
                    ImageExporter._draw_placed_image(painter, cell, placement, scale,
                                                     svg_override, raster_override)

                    if getattr(cell, 'scale_bar_enabled', False):
                        ImageExporter._draw_scale_bar(painter, cell,
                            QRectF(*(v * scale for v in placement.rect)), scale, fit_mode_override='contain',
                            typography_mode=getattr(project, 'typography_mode', 'points'))

                ImageExporter._draw_pip_items(painter, project, cell, content_rect, scale, placement)

            # 1b. Draw Label Cells (labels living in their own reserved strip)
            ImageExporter._draw_label_cells(painter, project, layout_result, scale)

            # 1c. Draw Group Label bands (spans, column headers, row titles)
            ImageExporter._draw_group_labels(painter, project, layout_result, scale)

            # 2. Draw Text Items
            for text_item in project.text_items:
                # Skip numbering labels rendered by label cells
                if (
                    text_item.scope == 'cell'
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
            ImageExporter._save_as_tiff(
                image, output_path, project.dpi,
                color_mode=color_mode, icc_profile_path=icc_profile_path,
                rendering_intent=rendering_intent,
            )
        elif format_upper in ("JPG", "JPEG"):
            image.save(output_path, "JPEG", quality=100)
        elif format_upper == "PNG":
            image.save(output_path, "PNG")
        else:
            # Default to PNG
            image.save(output_path, "PNG")
    
    @staticmethod
    def _paint_scene(painter: QPainter, project: Project, layout_result, scale: float, *, cell_painter=None):
        """Shared painting logic: draws all cells, labels, and text items.

        Extracted so raster export, in-memory render, and SVG export can share it.
        """
        placements = getattr(layout_result, '_image_placements', None)
        if placements is None or not getattr(layout_result, '_image_placements_strict', False):
            placements = resolve_image_placements(project, layout_result, strict=True)
            layout_result._image_placements = placements
            layout_result._image_placements_strict = True
        label_rects = getattr(layout_result, 'label_rects', {})

        sorted_cells = sorted(project.get_all_leaf_cells(), key=lambda c: getattr(c, 'z_index', 0))
        for cell in sorted_cells:
            if cell.id not in layout_result.cell_rects:
                continue
            if cell_painter is not None:
                cell_painter(cell)
                continue
            x_mm, y_mm, w_mm, h_mm = layout_result.cell_rects[cell.id]
            target_rect = QRectF(x_mm * scale, y_mm * scale, w_mm * scale, h_mm * scale)
            content_rect = QRectF(*(v * scale for v in cell_content_rect(
                cell, (x_mm, y_mm, w_mm, h_mm), project.layout_mode)))
            placement = placements.placements.get(cell.id)
            if content_rect.width() <= 0 or content_rect.height() <= 0:
                continue
            if placement is not None:
                from src.utils.text_overrides import overrides_for_cell
                svg_override, raster_override = overrides_for_cell(
                    project, cell, layout_result,
                    (content_rect.width() / scale, content_rect.height() / scale))
                ImageExporter._draw_placed_image(painter, cell, placement, scale,
                                                 svg_override, raster_override)
                if getattr(cell, 'scale_bar_enabled', False):
                    ImageExporter._draw_scale_bar(painter, cell,
                        QRectF(*(v * scale for v in placement.rect)), scale, fit_mode_override='contain',
                        typography_mode=getattr(project, 'typography_mode', 'points'))
            ImageExporter._draw_pip_items(painter, project, cell, content_rect, scale, placement)

        ImageExporter._draw_label_cells(painter, project, layout_result, scale)
        ImageExporter._draw_group_labels(painter, project, layout_result, scale)

        for text_item in project.text_items:
            if (
                text_item.scope == 'cell'
                and getattr(text_item, 'subtype', None) != 'corner'
                and text_item.parent_id in label_rects
            ):
                continue
            ImageExporter._draw_text(painter, project, text_item, layout_result, scale)

    @staticmethod
    def render_to_qimage(project: Project) -> QImage:
        """Render project to a QImage (in-memory, no file save).

        Respects ``project.export_region`` (clips canvas to region bounds,
        same as ``export()``).  Delegates all painting to ``_paint_scene``
        so z-index ordering and label-placement logic stay in sync.
        """
        layout_result = LayoutEngine.calculate_layout(project)
        layout_result._image_placements = resolve_image_placements(project, layout_result, strict=True)
        layout_result._image_placements_strict = True

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

        scale = project.dpi / 25.4
        width_px = int(page_w_mm * scale)
        height_px = int(page_h_mm * scale)

        image = QImage(width_px, height_px, QImage.Format.Format_ARGB32)
        image.fill(Qt.GlobalColor.white)

        dpm = int(project.dpi * 39.3701)
        image.setDotsPerMeterX(dpm)
        image.setDotsPerMeterY(dpm)

        painter = QPainter(image)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        if region_dx_mm != 0.0 or region_dy_mm != 0.0:
            painter.translate(-region_dx_mm * scale, -region_dy_mm * scale)

        try:
            ImageExporter._paint_scene(painter, project, layout_result, scale)
        finally:
            painter.end()

        return image

    @staticmethod
    def _placed_source_rect(placement, crop, scale=1.0):
        from src.utils.plot_alignment import rotate_box
        cl, ct, cr, cb = rotate_box(placement.crop, placement.rotation)
        left, top, right, bottom = rotate_box(crop, placement.rotation)
        x, y, width, height = placement.rect
        full_w, full_h = width / (cr - cl), height / (cb - ct)
        return QRectF((x + (left - cl) * full_w) * scale,
                      (y + (top - ct) * full_h) * scale,
                      (right - left) * full_w * scale, (bottom - top) * full_h * scale)

    @staticmethod
    def _draw_pip_items(painter: QPainter, project, cell, content_rect: QRectF, scale: float, image_placement=None):
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
            pad_px = getattr(pip, 'content_padding_pt', 0.0) * (scale * 25.4 / 72.0)
            img_rect = inset_rect.adjusted(pad_px, pad_px, -pad_px, -pad_px)
            painter.save()
            painter.setClipRect(img_rect)
            # Draw pip image
            if pip.pip_type == "zoom" and cell.image_path and os.path.exists(cell.image_path):
                src_crop = (pip.crop_left, pip.crop_top, pip.crop_right, pip.crop_bottom)
                ImageExporter._draw_raster(painter, cell.image_path, img_rect, "contain", 0, src_crop)
            elif pip.pip_type == "external" and pip.image_path and os.path.exists(pip.image_path):
                ImageExporter._draw_image(painter, pip.image_path, img_rect, "contain", 0)
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
                ImageExporter._draw_scale_bar(painter, pip, img_rect, scale, fit_mode_override=pip_fit,
                    source_path_override=cell.image_path if pip.pip_type == 'zoom' else None,
                    typography_mode=getattr(project, 'typography_mode', 'points'))
                
                # Restore
                pip.scale_bar_um_per_px = old_um
            # Draw border
            if pip.border_enabled:
                from PyQt6.QtGui import QPen
                bpen = QPen(QColor(pip.border_color))
                # pt -> output units: pt * mm/pt * units/mm = pt * 25.4/72 * scale
                bpen.setWidthF(pip.border_width_pt * (scale * 25.4 / 72.0))
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
                if image_placement is not None:
                    origin_rect = ImageExporter._placed_source_rect(image_placement,
                        (pip.crop_left, pip.crop_top, pip.crop_right, pip.crop_bottom), scale)
                from PyQt6.QtGui import QPen
                open_pen = QPen(QColor(pip.origin_box_color))
                # pt -> output units (see _draw_pip_items border comment above)
                open_pen.setWidthF(pip.origin_box_width_pt * (scale * 25.4 / 72.0))
                open_pen.setCosmetic(False)
                if getattr(pip, 'origin_box_style', 'solid') == 'dashed':
                    open_pen.setStyle(Qt.PenStyle.DashLine)
                painter.setPen(open_pen)
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawRect(origin_rect)

    @staticmethod
    def _save_as_tiff(qimage: QImage, output_path: str, dpi: int,
                      color_mode: str = "rgb", icc_profile_path: str = None,
                      rendering_intent: int = 1):
        """Save QImage as TIFF with proper DPI metadata using PIL.

        color_mode: "rgb" (default) or "cmyk" for print-ready output.
        icc_profile_path: absolute path to a CMYK ICC profile (*.icc/*.icm).
            When given and ``color_mode`` is ``cmyk``, performs an ICC-managed
            sRGB -> CMYK conversion via Pillow's ImageCms and embeds the
            profile in the saved TIFF.  When missing or the profile fails to
            load, falls back to Pillow's naive ``convert('CMYK')`` and logs a
            warning.
        """
        width = qimage.width()
        height = qimage.height()
        ptr = qimage.bits()
        ptr.setsize(qimage.sizeInBytes())

        if qimage.format() == QImage.Format.Format_ARGB32:
            pil_image = Image.frombytes("RGBA", (width, height), bytes(ptr), "raw", "BGRA")
        else:
            pil_image = Image.frombytes("RGBA", (width, height), bytes(ptr), "raw", "BGRA")
            pil_image = pil_image.convert("RGB")

        save_kwargs = {"dpi": (dpi, dpi), "compression": "tiff_lzw"}

        if str(color_mode).lower() == "cmyk":
            if pil_image.mode != "RGB":
                pil_image = pil_image.convert("RGB")
            pil_image, profile_bytes = ImageExporter._convert_rgb_to_cmyk(
                pil_image, icc_profile_path, rendering_intent=rendering_intent,
            )
            if profile_bytes:
                save_kwargs["icc_profile"] = profile_bytes

        pil_image.save(output_path, "TIFF", **save_kwargs)

    @staticmethod
    def _convert_rgb_to_cmyk(pil_rgb, icc_profile_path: str = None,
                             rendering_intent: int = 1):
        """Return (cmyk_image, profile_bytes_or_None).

        Uses PIL.ImageCms for colour-managed conversion when a CMYK profile is
        supplied or discoverable on the system.  Falls back to ``convert('CMYK')``
        with a printed warning when no usable profile is found.
        """
        import os
        from PIL import ImageCms

        # 1. Resolve a CMYK output profile.
        candidate_paths = []
        if icc_profile_path:
            candidate_paths.append(icc_profile_path)
        # Windows system colour profiles (common install locations).
        win_dir = os.path.join(os.environ.get("WINDIR", r"C:\Windows"),
                               "System32", "spool", "drivers", "color")
        if os.path.isdir(win_dir):
            for name in (
                "USWebCoatedSWOP.icc", "USWebCoatedSWOP.icm",
                "CoatedFOGRA39.icc", "CoatedFOGRA39.icm",
                "JapanColor2001Coated.icc",
            ):
                candidate_paths.append(os.path.join(win_dir, name))
        # macOS default
        candidate_paths.append("/System/Library/ColorSync/Profiles/Generic CMYK Profile.icc")

        out_profile_path = next(
            (p for p in candidate_paths if p and os.path.isfile(p)),
            None,
        )

        if out_profile_path is None:
            print("[tiff-export] No CMYK ICC profile found; using naive RGB->CMYK. "
                  "Set a profile via File > Export TIFF for colour-accurate print.")
            return pil_rgb.convert("CMYK"), None

        # Resolve an sRGB input profile. LittleCMS often refuses transforms
        # from the synthetic createProfile("sRGB") profile, so prefer a real
        # on-disk profile when available.
        srgb_candidates = []
        if os.path.isdir(win_dir):
            # Scan the whole colour directory for any sRGB-named profile.
            for name in sorted(os.listdir(win_dir)):
                low = name.lower()
                if low.endswith((".icc", ".icm")) and "srgb" in low:
                    srgb_candidates.append(os.path.join(win_dir, name))
        srgb_candidates.extend([
            "/System/Library/ColorSync/Profiles/sRGB Profile.icc",
            "/usr/share/color/icc/sRGB.icc",
            "/usr/share/color/icc/colord/sRGB.icc",
        ])
        srgb_path = next((p for p in srgb_candidates if os.path.isfile(p)), None)

        # Profile descriptions for diagnostics.
        def _desc(p):
            try:
                return ImageCms.getProfileDescription(ImageCms.getOpenProfile(p)).strip()
            except Exception:
                return os.path.basename(p) if isinstance(p, str) else str(p)

        print(f"[tiff-export] CMYK profile: {_desc(out_profile_path)}")
        if srgb_path:
            print(f"[tiff-export] sRGB profile: {_desc(srgb_path)}")
        else:
            print("[tiff-export] sRGB profile: synthetic (no on-disk sRGB found)")

        with open(out_profile_path, "rb") as fh:
            profile_bytes = fh.read()

        # Try progressively more forgiving strategies.
        attempts = []
        if srgb_path:
            attempts.append(("profileToProfile(srgb_file)",
                             lambda: ImageCms.profileToProfile(
                                 pil_rgb, srgb_path, out_profile_path,
                                 renderingIntent=int(rendering_intent),
                                 outputMode="CMYK")))
        attempts.append(("profileToProfile(synthetic_sRGB)",
                         lambda: ImageCms.profileToProfile(
                             pil_rgb, ImageCms.createProfile("sRGB"), out_profile_path,
                             renderingIntent=int(rendering_intent),
                             outputMode="CMYK")))
        attempts.append(("perceptual intent",
                         lambda: ImageCms.profileToProfile(
                             pil_rgb,
                             srgb_path if srgb_path else ImageCms.createProfile("sRGB"),
                             out_profile_path,
                             renderingIntent=0,
                             outputMode="CMYK")))

        for label, fn in attempts:
            try:
                cmyk = fn()
                if cmyk is not None:
                    print(f"[tiff-export] ICC transform OK via {label}.")
                    return cmyk, profile_bytes
            except Exception as exc:
                print(f"[tiff-export]   strategy '{label}' failed: {exc!r}")

        # All transforms failed. Still tag the output with the CMYK profile so
        # downstream tools know the intended colour space — pixels are the
        # naive conversion, which is the best we can do without a working CMS.
        print("[tiff-export] All ICC strategies failed; embedding profile tag on naive CMYK.")
        return pil_rgb.convert("CMYK"), profile_bytes

    @staticmethod
    def _draw_placed_image(painter: QPainter, cell, placement, scale: float,
                           svg_override_bytes=None, raster_override=None):
        path = cell.image_path
        target = QRectF(*(value * scale for value in placement.rect))
        clip = QRectF(*(value * scale for value in placement.clip_rect))
        cl, ct, cr, cb = placement.crop
        if target.isEmpty() or clip.isEmpty() or cr <= cl or cb <= ct:
            return
        width, height = target.width(), target.height()
        if placement.rotation % 180:
            width, height = height, width
        local = QRectF(-width / 2, -height / 2, width, height)
        painter.save()
        try:
            painter.setClipRect(clip, Qt.ClipOperation.IntersectClip)
            painter.setClipRect(target, Qt.ClipOperation.IntersectClip)
            painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
            painter.translate(target.center())
            painter.rotate(placement.rotation)
            extension = os.path.splitext(path)[1].lower()
            if extension == '.svg':
                from PyQt6.QtCore import QByteArray
                from src.utils.svg_utils import sanitize_svg_bytes
                if svg_override_bytes is None:
                    with open(path, 'rb') as source:
                        svg_override_bytes = source.read()
                renderer = QSvgRenderer(QByteArray(sanitize_svg_bytes(svg_override_bytes)))
                if renderer.isValid():
                    full_w, full_h = width / (cr - cl), height / (cb - ct)
                    renderer.render(painter, QRectF(-width / 2 - cl * full_w,
                                                    -height / 2 - ct * full_h, full_w, full_h))
            else:
                if extension in ('.pdf', '.eps'):
                    import fitz
                    with fitz.open(path) as document:
                        if not document.page_count:
                            return
                        pix = document[0].get_pixmap(matrix=fitz.Matrix(4, 4), alpha=True)
                    image = QImage(pix.samples, pix.width, pix.height, pix.stride,
                                   QImage.Format.Format_RGBA8888).copy()
                else:
                    from src.utils.raster_text_utils import load_raster_with_overrides
                    raster = load_raster_with_overrides(path, raster_override)
                    data = raster.tobytes('raw', 'RGBA')
                    image = QImage(data, raster.width, raster.height, QImage.Format.Format_RGBA8888)
                source = QRectF(cl * image.width(), ct * image.height(),
                                (cr - cl) * image.width(), (cb - ct) * image.height())
                if getattr(painter, '_svg_full_source', False):
                    full_w, full_h = width / (cr - cl), height / (cb - ct)
                    painter.drawImage(QRectF(-width / 2 - cl * full_w,
                                            -height / 2 - ct * full_h, full_w, full_h), image)
                else:
                    painter.drawImage(local, image, source)
        except Exception as exc:
            print(f'Failed to export image {path}: {exc}')
        finally:
            painter.restore()

    @staticmethod
    def _draw_image(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                    crop: tuple = (0.0, 0.0, 1.0, 1.0), svg_override_bytes: bytes = None,
                    raster_override: dict = None):
        """Draw an image into the given rect, applying crop and rotation."""
        ext = os.path.splitext(path)[1].lower()
        if ext == '.svg':
            ImageExporter._draw_svg(painter, path, rect, fit_mode_str, rotation, crop, svg_override_bytes)
        elif ext in ('.pdf', '.eps'):
            ImageExporter._draw_pdf(painter, path, rect, fit_mode_str, rotation, crop)
        else:
            ImageExporter._draw_raster(painter, path, rect, fit_mode_str, rotation, crop, raster_override)

    @staticmethod
    def _draw_svg(painter: QPainter, path: str, rect: QRectF, fit_mode_str: str, rotation: int = 0,
                  crop: tuple = (0.0, 0.0, 1.0, 1.0), svg_override_bytes: bytes = None):
        """Draw SVG vector image, honouring crop."""
        try:
            from PyQt6.QtCore import QByteArray
            from src.utils.svg_utils import sanitize_svg_bytes
            if svg_override_bytes:
                svg_bytes = sanitize_svg_bytes(svg_override_bytes)
            else:
                with open(path, "rb") as _f:
                    svg_bytes = sanitize_svg_bytes(_f.read())
            renderer = QSvgRenderer(QByteArray(svg_bytes))
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
                     crop: tuple = (0.0, 0.0, 1.0, 1.0), raster_override: dict = None):
        """Draw raster image using PIL, honouring crop."""
        try:
            from src.utils.raster_text_utils import load_raster_with_overrides
            img = load_raster_with_overrides(path, raster_override)
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

        is_global = not (text_item.scope == "cell" and text_item.parent_id
                         and text_item.parent_id in layout_result.cell_rects)
        if getattr(project, 'typography_mode', 'legacy') == 'points':
            from src.utils.typography import point_text_item
            temp_item = point_text_item(text_item.text, text_item.font_family,
                                        text_item.font_size_pt,
                                        text_item.font_weight, text_item.color)
            text_scale = temp_item.scale()
            base_rect = temp_item.boundingRect()
            tw_mm = base_rect.width() * text_scale
            th_mm = base_rect.height() * text_scale
            x_mm, y_mm = ImageExporter._text_position_mm(
                text_item, layout_result, tw_mm, th_mm)
        else:
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

            base_rect = temp_item.boundingRect()
            tw_mm = base_rect.width() * text_scale
            th_mm = base_rect.height() * text_scale

            x_mm, y_mm = ImageExporter._text_position_mm(text_item, layout_result, tw_mm, th_mm)

            # The canvas positions global text via setPos(x, y) + setScale(text_scale).
            # Qt scales around the item origin, so the visual top-left is shifted inward
            # by (1 - scale) * br/2. Correct for that here to match on-canvas placement.
            if is_global:
                x_mm += (base_rect.width() - tw_mm) / 2.0
                y_mm += (base_rect.height() - th_mm) / 2.0

        x_px = x_mm * scale
        y_px = y_mm * scale

        render_scale = text_scale * scale
        painter.save()
        painter.translate(x_px, y_px)
        # Rotation around the scaled rect centre, same as canvas.
        rotation_deg = float(getattr(text_item, 'rotation', 0.0)) if is_global else 0.0
        if rotation_deg:
            painter.translate(tw_mm * scale / 2.0, th_mm * scale / 2.0)
            painter.rotate(rotation_deg)
            painter.translate(-tw_mm * scale / 2.0, -th_mm * scale / 2.0)
        if getattr(text_item, 'bg_enabled', False):
            from PyQt6.QtGui import QBrush as _QB
            pad = float(getattr(text_item, 'bg_padding_mm', 0.6)) * scale
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(_QB(QColor(getattr(text_item, 'bg_color', '#FFFFFF'))))
            painter.drawRect(QRectF(-pad, -pad, tw_mm * scale + 2 * pad, th_mm * scale + 2 * pad))
            painter.restore()
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
        """Draw cell labels that live in their own reserved strip.

        Each label is styled from its own TextItem fields rather than the
        project defaults, so panel letters and panel titles can share a
        figure. Sizing mirrors CellItem._draw_label_cell so the exported
        label matches the canvas exactly.
        """
        label_rects = getattr(layout_result, 'label_rects', {})
        if not label_rects:
            return

        for t in project.text_items:
            if t.scope != 'cell' or getattr(t, 'subtype', None) == 'corner':
                continue
            if not t.parent_id or t.parent_id not in label_rects:
                continue
            if not t.text:
                continue
            lx, ly, lw, lh = label_rects[t.parent_id]
            align = project.effective_label_align(t)
            ox_mm, oy_mm = project.effective_label_offsets(t)

            rect_px = QRectF((lx + ox_mm) * scale, (ly + oy_mm) * scale,
                             lw * scale, lh * scale)
            from src.utils.typography import uses_points
            if uses_points(project):
                from src.utils.label_strip_render import draw_point_strip_label
                draw_point_strip_label(
                    painter, rect_px, t.text, t.font_family, t.font_size_pt,
                    t.font_weight, QColor(t.color),
                    project.label_strip_is_vertical(t), align,
                    project.effective_label_valign(t),
                    getattr(t, 'rotation', 0.0) or 0.0, device_scale=scale)
                continue

            # The canvas draws strip labels with an explicit pixel size, i.e.
            # one point of label font spans one millimetre on the page (the
            # same convention the layout engine sizes the strip with). Mirror
            # that here instead of measuring a point-sized QGraphicsTextItem,
            # whose metrics carry the screen's 96-dpi pt→px factor and would
            # render the label a third larger than the app shows.
            font = QFont(t.font_family)
            font.setPixelSize(max(1, int(round(t.font_size_pt * scale))))
            if t.font_weight == "bold":
                font.setBold(True)

            from src.utils.label_strip_render import draw_strip_label
            draw_strip_label(painter, rect_px, t.text, font, QColor(t.color),
                             project.label_strip_is_vertical(t), align,
                             project.effective_label_valign(t),
                             getattr(t, 'rotation', 0.0) or 0.0)

    @staticmethod
    def _draw_group_labels(painter: QPainter, project, layout_result, scale: float):
        """Draw group-label bands (spans, column headers, rotated row titles).

        Delegates to the shared renderer so canvas and export agree.
        """
        bands = getattr(layout_result, 'group_label_rects', {}) or {}
        if not bands:
            return
        from src.utils import group_label_render
        for group_label in getattr(project, 'group_labels', []) or []:
            band = bands.get(group_label.id)
            if not band:
                continue
            x, y, w, h = band
            group_label_render.draw(painter, group_label, QRectF(x, y, w, h), scale,
                                    typography_mode=getattr(project, 'typography_mode', 'points'))

    @staticmethod
    def _draw_scale_bar(painter: QPainter, obj, content_rect: QRectF, scale: float, fit_mode_override=None,
                        source_path_override=None, typography_mode='points'):
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
        img_path = source_path_override or getattr(obj, "image_path", None)
        try:
            if img_path and os.path.exists(img_path):
                with Image.open(img_path) as img:
                    orig_w, orig_h = img.size
            else:
                orig_w, orig_h = 1000, 1000
        except Exception:
            orig_w, orig_h = 1000, 1000
        
        from src.utils.plot_alignment import get_source_size
        orig_w, orig_h = get_source_size(img_path) or (orig_w, orig_h)

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
            fit_mode_str = fit_mode_override or getattr(obj, "fit_mode", "contain")
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

            if typography_mode == 'points':
                from src.utils.typography import point_text_item
                temp_item = point_text_item(
                    text, 'Arial', getattr(obj, 'scale_bar_text_size_pt', 8.0),
                    'normal', color, rich=False)
                text_scale = temp_item.scale()
            else:
                base_pt = 24
                text_scale = text_size_mm / base_pt

                temp_item = QGraphicsTextItem()
                temp_item.setPlainText(text)
                temp_item.setFont(QFont("Arial", base_pt))
                temp_item.setDefaultTextColor(QColor(color))

            render_scale = text_scale * scale

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
