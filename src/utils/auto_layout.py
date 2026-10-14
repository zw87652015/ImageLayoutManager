import os
from typing import List, Tuple, Dict
from PIL import Image
from PyQt6.QtSvg import QSvgRenderer
from src.model.data_model import Project, Cell

# Active Reflow plots can fit any panel; use a common landscape starting
# shape instead of treating their saved SVG dimensions as a constraint.
_REFLOW_LAYOUT_ASPECT = 4.0 / 3.0

class AutoLayout:
    @staticmethod
    def _get_image_aspect_ratios(project: Project) -> Dict[str, float]:
        """Return layout aspects, keeping active Reflow independent of source size.

        Grid Reflow cells share a 4:3 starting shape. In freeform mode their
        existing panel aspect is retained. Fixed artwork keeps its cropped,
        rotated source aspect.
        """
        aspect_ratios = {}
        for cell in project.get_all_leaf_cells():
            if cell.image_path and os.path.exists(cell.image_path) and not cell.is_placeholder:
                try:
                    if getattr(cell, 'plot_reflow', False) is True:
                        from src.utils.editable_plot import plot_reflows
                        if plot_reflows(project, cell):
                            ratio = _REFLOW_LAYOUT_ASPECT
                            if project.layout_mode == 'freeform':
                                w = cell.freeform_w_mm
                                h = cell.freeform_h_mm
                                if w > 0 and h > 0:
                                    ratio = w / h
                            aspect_ratios[cell.id] = ratio
                            continue
                    ext = os.path.splitext(cell.image_path)[1].lower()
                    if ext == '.svg':
                        # Handle SVG vector format
                        renderer = QSvgRenderer(cell.image_path)
                        if renderer.isValid():
                            size = renderer.defaultSize()
                            if size.height() > 0:
                                ratio = (size.width() * max(0.001, cell.crop_right - cell.crop_left)
                                         / (size.height() * max(0.001, cell.crop_bottom - cell.crop_top)))
                                if getattr(cell, 'rotation', 0) in [90, 270]:
                                    ratio = 1.0 / ratio if ratio != 0 else 0
                                aspect_ratios[cell.id] = ratio
                    elif ext == '.pdf':
                        # Handle PDF format with PyMuPDF
                        try:
                            import fitz
                            doc = fitz.open(cell.image_path)
                            if doc.page_count > 0:
                                page = doc[0]
                                rect = page.rect
                                if rect.height > 0:
                                    ratio = (rect.width * max(0.001, cell.crop_right - cell.crop_left)
                                             / (rect.height * max(0.001, cell.crop_bottom - cell.crop_top)))
                                    if getattr(cell, 'rotation', 0) in [90, 270]:
                                        ratio = 1.0 / ratio if ratio != 0 else 0
                                    aspect_ratios[cell.id] = ratio
                            doc.close()
                        except ImportError:
                            pass
                    else:
                        # Handle raster formats with PIL
                        with Image.open(cell.image_path) as img:
                            w, h = img.size
                            if h > 0:
                                crop_w = max(0.001, getattr(cell, 'crop_right', 1.0) - getattr(cell, 'crop_left', 0.0))
                                crop_h = max(0.001, getattr(cell, 'crop_bottom', 1.0) - getattr(cell, 'crop_top', 0.0))
                                ratio = (w * crop_w) / (h * crop_h)
                                if getattr(cell, 'rotation', 0) in [90, 270]:
                                    ratio = 1.0 / ratio if ratio != 0 else 0
                                aspect_ratios[cell.id] = ratio
                except Exception:
                    pass
        return aspect_ratios

    @staticmethod
    def optimize_layout(project: Project) -> Dict[str, any]:
        """
        Calculates optimized row heights, column ratios and page height.

        Every cell is modelled as slot_width = a * slot_height + s, where s
        carries the cell's side label strip (and any width that does not
        scale with height). Models follow LayoutEngine's geometry: outer-edge
        label bands are hoisted into the row band, and fixed-size children
        contribute their fixed extent. A row solves its height from the sum of
        its column models; split_ratios are then assigned top-down from the
        sizes the engine will produce.
        """
        from src.model.layout_engine import LayoutEngine

        # Resolve fixed source shapes and flexible Reflow preferences once.
        aspect_ratios = AutoLayout._get_image_aspect_ratios(project)

        # 1a-group. Size-group aware aspect bucketing.
        # Cells that belong to the same size group must end up with the same W/H.
        # Using the MIN aspect of the group ensures the shared size fits every member.
        groups = getattr(project, 'size_groups', []) or []
        if groups:
            for g in groups:
                member_ids = [c.id for c in project.get_all_leaf_cells() if c.size_group_id == g.id]
                aspects = [aspect_ratios[mid] for mid in member_ids if mid in aspect_ratios]
                if aspects:
                    shared_aspect = min(aspects)
                    for mid in member_ids:
                        aspect_ratios[mid] = shared_aspect

        gap = project.gap_mm
        placements, strip_sizes = LayoutEngine.resolve_label_placements(project)
        strips_above, strips_below = LayoutEngine._row_label_strips(
            project, placements, strip_sizes)
        bands_top, bands_bottom, bands_left, bands_right = \
            LayoutEngine._collect_group_bands(project)
        typography = getattr(project, 'typography_mode', 'points')
        content_width = max(0.0, project.page_width_mm
                            - project.margin_left_mm - project.margin_right_mm
                            - LayoutEngine._gutter_mm(bands_left, typography)
                            - LayoutEngine._gutter_mm(bands_right, typography))

        def strip_of(cell: Cell, placement: str) -> float:
            return strip_sizes.get(cell.id, 0.0) if placements.get(cell.id) == placement else 0.0

        def side_of(cell: Cell) -> float:
            if placements.get(cell.id) in ("label_col_left", "label_col_right"):
                return strip_sizes.get(cell.id, 0.0) + gap
            return 0.0

        info: Dict[str, dict] = {}

        def build(cell: Cell, hoist_above: bool, hoist_below: bool):
            """Return the (a, s) model of *cell*, or None when it has no image.

            hoist_above / hoist_below say a label band is passed in from the
            parent, mirroring LayoutEngine's hoist_above / hoist_below.
            """
            entry = {"side": side_of(cell), "model": None,
                     "hoist_above": hoist_above, "hoist_below": hoist_below}
            info[cell.id] = entry
            if cell.is_leaf:
                a = aspect_ratios.get(cell.id)
                if a and a > 0:
                    entry["model"] = (a, entry["side"])
                return entry["model"]

            children = cell.children
            n = len(children)
            if n == 0 or cell.split_direction not in ("horizontal", "vertical"):
                return None
            horizontal = cell.split_direction == "horizontal"
            fixed = [getattr(c, 'override_width_mm' if horizontal else 'override_height_mm', 0.0)
                     for c in children]
            overhead = 0.0
            label_space = 0.0
            flags = []
            if horizontal:
                above_h = max((strip_of(c, "label_row_above") for c in children), default=0.0)
                below_h = max((strip_of(c, "label_row_below") for c in children), default=0.0)
                if not hoist_above and above_h > 0:
                    overhead += above_h + gap
                if not hoist_below and below_h > 0:
                    overhead += below_h + gap
                for c in children:
                    flags.append((hoist_above and placements.get(c.id) != "label_row_above",
                                  hoist_below and placements.get(c.id) != "label_row_below"))
            else:
                for i, c in enumerate(children):
                    on_top = bool(i == 0 and hoist_above and LayoutEngine._wants_outer_edge(
                        c, "label_row_above", "above", placements))
                    on_bottom = bool(i == n - 1 and hoist_below and LayoutEngine._wants_outer_edge(
                        c, "label_row_below", "below", placements))
                    if not on_top and strip_of(c, "label_row_above") > 0:
                        label_space += strip_of(c, "label_row_above") + gap
                    if not on_bottom and strip_of(c, "label_row_below") > 0:
                        label_space += strip_of(c, "label_row_below") + gap
                    flags.append((on_top and placements.get(c.id) != "label_row_above",
                                  on_bottom and placements.get(c.id) != "label_row_below"))

            child_models = [build(c, fa, fb) for c, (fa, fb) in zip(children, flags)]
            ratio_children = [i for i in range(n) if fixed[i] <= 0]
            valid = [child_models[i] for i in ratio_children if child_models[i] is not None]
            if not valid:
                return None
            mean_a = sum(m[0] for m in valid) / len(valid)
            models: List = [None] * n
            for i in ratio_children:
                models[i] = child_models[i] if child_models[i] is not None else (
                    mean_a, side_of(children[i]))

            if horizontal:
                a = sum(models[i][0] for i in ratio_children)
                s = (sum(models[i][1] for i in ratio_children) - a * overhead
                     + sum(fixed) + (n - 1) * gap + entry["side"])
            else:
                k_sum = sum(1.0 / models[i][0] for i in ratio_children)
                a = 1.0 / k_sum
                s = a * (sum(models[i][1] / models[i][0] for i in ratio_children)
                         - sum(fixed) - (n - 1) * gap - label_space) + entry["side"]

            entry.update(horizontal=horizontal, models=models, fixed=fixed,
                         ratio_children=ratio_children,
                         overhead=overhead, label_space=label_space)
            entry["model"] = (a, s)
            return entry["model"]

        def assign(cell: Cell, slot_w: float, slot_h: float):
            """Set split_ratios of *cell* (and descendants) for a slot of this size."""
            entry = info.get(cell.id)
            if cell.is_leaf or entry is None or entry["model"] is None:
                return
            children = cell.children
            n = len(children)
            pic_w = max(0.0, slot_w - entry["side"])
            ratios = list(cell.split_ratios) if cell.split_ratios else [1.0] * n
            while len(ratios) < n:
                ratios.append(1.0)
            ratios = ratios[:n]
            fixed = entry["fixed"]
            models = entry["models"]
            ratio_children = entry["ratio_children"]

            if entry["horizontal"]:
                child_h = max(0.0, slot_h - entry["overhead"])
                for i in ratio_children:
                    ratios[i] = max(1e-3, round(models[i][0] * child_h + models[i][1], 4))
                cell.split_ratios = ratios
                avail = max(0.0, pic_w - (n - 1) * gap - sum(fixed))
                ratio_sum = sum(ratios[i] for i in ratio_children) or 1.0
                for i, child in enumerate(children):
                    child_w = fixed[i] if fixed[i] > 0 else ratios[i] / ratio_sum * avail
                    assign(child, child_w, child_h)
            else:
                for i in ratio_children:
                    ratios[i] = max(1e-3, round((pic_w - models[i][1]) / models[i][0], 4))
                cell.split_ratios = ratios
                avail = max(0.0, slot_h - (n - 1) * gap - entry["label_space"] - sum(fixed))
                ratio_sum = sum(ratios[i] for i in ratio_children) or 1.0
                for i, child in enumerate(children):
                    child_h = fixed[i] if fixed[i] > 0 else ratios[i] / ratio_sum * avail
                    assign(child, pic_w, child_h)

        # Row solve: each column slot is a_j * H + s_j, so the row height H
        # follows from the content width minus gaps and side strips.
        sorted_rows = sorted(project.rows, key=lambda r: r.index)
        fixed_grid = getattr(project, "grid_mode", "stretch") == "fixed"
        max_col_count = max((r.column_count for r in sorted_rows if r.column_count > 0), default=0)
        unit = ((content_width - (max_col_count - 1) * gap) / max_col_count
                if fixed_grid and max_col_count > 0 else 0.0)

        new_row_settings = []
        by_index: Dict[int, dict] = {}
        row_heights: Dict[int, float] = {}
        row_cols: Dict[int, list] = {}
        for row in sorted_rows:
            r_dict = row.to_dict()
            new_row_settings.append(r_dict)
            by_index[row.index] = r_dict
            k = row.column_count
            if k <= 0:
                continue

            col_map = {c.col_index: c for c in project.cells if c.row_index == row.index}
            cols = [col_map.get(i) for i in range(k)]
            has_above = strips_above.get(row.index, 0.0) > 0
            has_below = strips_below.get(row.index, 0.0) > 0
            models = []
            for cell in cols:
                if cell is None:
                    models.append(None)
                    continue
                models.append(build(
                    cell,
                    has_above and placements.get(cell.id) != "label_row_above",
                    has_below and placements.get(cell.id) != "label_row_below"))

            valid = [m for m in models if m is not None]
            if valid:
                mean_a = sum(m[0] for m in valid) / len(valid)
                slot_models = []
                for cell, m in zip(cols, models):
                    if m is not None:
                        slot_models.append(m)
                    else:
                        slot_models.append((mean_a, side_of(cell) if cell is not None else 0.0))
            else:
                slot_models = [(1.0, 0.0)] * k

            sum_a = sum(a for a, _ in slot_models)
            sum_s = sum(s for _, s in slot_models)
            avail = unit * k if fixed_grid else content_width - (k - 1) * gap
            height = max(1.0, (avail - sum_s) / sum_a)
            row_heights[row.index] = height
            row_cols[row.index] = cols

            ratios = [max(1e-3, a * height + s) for a, s in slot_models]
            min_r = min(ratios)
            r_dict['column_ratios'] = [round(r / min_r, 2) for r in ratios]

        if row_heights:
            min_h = min(row_heights.values())
            for idx, height in row_heights.items():
                by_index[idx]['height_ratio'] = round(height / min_h, 2)

        # Page height: rows, gaps and every reserved band. Rows take the
        # height ratios just written, so use those to split the row total.
        total_row_h = sum(row_heights.values())
        total_ratio = sum(by_index[idx]['height_ratio'] for idx in row_heights)
        actual_heights = {
            idx: by_index[idx]['height_ratio'] / total_ratio * total_row_h
            for idx in row_heights
        } if total_ratio > 0 else {}

        # Top-down split ratios from the sizes each column will actually get.
        for row in sorted_rows:
            if row.index not in actual_heights:
                continue
            k = row.column_count
            norm = by_index[row.index]['column_ratios']
            avail = unit * k if fixed_grid else content_width - (k - 1) * gap
            total = sum(norm)
            for i, cell in enumerate(row_cols[row.index]):
                if cell is not None:
                    assign(cell, norm[i] / total * avail, actual_heights[row.index])

        total_natural_height = total_row_h
        num_rows = len(new_row_settings)
        if num_rows > 1:
            total_natural_height += (num_rows - 1) * gap

        for bucket in (strips_above, strips_below):
            for size in bucket.values():
                total_natural_height += size + gap

        for bucket in (bands_top, bands_bottom):
            for labels in bucket.values():
                _slot_of, slot_geoms = LayoutEngine._band_slot_assignment(project, labels)
                for thickness, slot_gap in slot_geoms:
                    total_natural_height += thickness + slot_gap

        # Add margins
        optimal_page_height = total_natural_height + project.margin_top_mm + project.margin_bottom_mm

        return {
            "rows": new_row_settings,
            "optimal_page_height_mm": round(optimal_page_height, 1)
        }
