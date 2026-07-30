from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from .data_model import Project, Cell, GroupLabel, RowTemplate

#: Placements that pull a cell label out of the image and into its own strip.
OUT_OF_CELL_PLACEMENTS = (
    "label_row_above", "label_row_below", "label_col_left", "label_col_right",
)


@dataclass
class LayoutResult:
    cell_rects: Dict[str, Tuple[float, float, float, float]]
    row_heights: Dict[int, float]
    figure_rects: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)
    label_rects: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)
    row_rects: Dict[int, Tuple[float, float, float, float]] = field(default_factory=dict)  # row_index -> (x, y, w, h)
    # group_label_id -> (x, y, w, h) band the label draws into, in mm.
    group_label_rects: Dict[str, Tuple[float, float, float, float]] = field(default_factory=dict)

class LayoutEngine:
    @staticmethod
    def _label_row_height_mm(project: Project) -> float:
        """Height of a label row based on label font settings."""
        h = project.label_font_size * 1.2 + 2.0
        return max(5.0, min(50.0, h))

    @staticmethod
    def _label_col_width_mm(project: Project) -> float:
        """Width of a label column based on label font settings (same formula as row height)."""
        w = project.label_font_size * 1.2 + 2.0
        return max(5.0, min(50.0, w))

    # ------------------------------------------------------------------
    # Cell-label placement resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _strip_size_mm(project: Project, font_size_pt: float, horizontal: bool) -> float:
        """Thickness of a cell-label strip, honouring the project override."""
        override = project.label_row_height if horizontal else project.label_col_width
        if override and override > 0:
            return override
        size = font_size_pt if font_size_pt and font_size_pt > 0 else project.label_font_size
        return max(5.0, min(50.0, size * 1.2 + 2.0))

    @staticmethod
    def resolve_label_placements(project: Project) -> Tuple[Dict[str, str], Dict[str, float]]:
        """Map each labelled cell to its effective out-of-cell placement.

        Returns ``(placements, strip_sizes)`` covering only cells whose label
        actually leaves the image; ``in_cell`` labels are absent so callers can
        treat membership as "needs a reserved strip". Per-label overrides beat
        ``Project.label_placement``, which is what makes mixed placement work.
        """
        placements: Dict[str, str] = {}
        strip_sizes: Dict[str, float] = {}
        for item in project.text_items:
            if item.scope != 'cell' or getattr(item, 'subtype', None) == 'corner':
                continue
            if not item.parent_id:
                continue
            placement = project.effective_label_placement(item)
            if placement not in OUT_OF_CELL_PLACEMENTS:
                continue
            horizontal = placement in ("label_row_above", "label_row_below")
            placements[item.parent_id] = placement
            strip_sizes[item.parent_id] = LayoutEngine._strip_size_mm(
                project, item.font_size_pt, horizontal
            )
        return placements, strip_sizes

    # ------------------------------------------------------------------
    # Group labels
    # ------------------------------------------------------------------

    @staticmethod
    def group_label_thickness_mm(group_label: GroupLabel) -> float:
        """Band thickness: explicit value, else derived from font and bracket."""
        if group_label.thickness_mm and group_label.thickness_mm > 0:
            return group_label.thickness_mm
        thickness = group_label.font_size_pt * 1.2 + 2.0
        if group_label.bracket_style != "none":
            thickness += group_label.bracket_gap_mm + group_label.bracket_tick_mm
        return max(4.0, min(60.0, thickness))

    @staticmethod
    def _row_by_cell_id(project: Project) -> Dict[str, int]:
        """Map every cell (including nested ones) to its top-level row index."""
        mapping: Dict[str, int] = {}

        def walk(cell: Cell, row_index: int):
            mapping[cell.id] = row_index
            for child in cell.children:
                walk(child, row_index)

        for cell in project.cells:
            walk(cell, cell.row_index)
        return mapping

    @staticmethod
    def group_label_target_ids(project: Project, group_label: GroupLabel) -> List[str]:
        """Cell ids a group label spans. ``row_index`` targets the whole row."""
        if group_label.row_index is not None:
            return [c.id for c in project.cells if c.row_index == group_label.row_index]
        return list(group_label.cell_ids)

    @staticmethod
    def _group_label_row(project: Project, group_label: GroupLabel,
                         row_by_cell: Dict[str, int]) -> Optional[int]:
        """Row whose band a top/bottom group label reserves space in."""
        if group_label.row_index is not None:
            return group_label.row_index
        rows = [row_by_cell[cid] for cid in group_label.cell_ids if cid in row_by_cell]
        if not rows:
            return None
        # A span reaching several rows attaches to the row it sits against.
        return min(rows) if group_label.side == "top" else max(rows)

    @staticmethod
    def _collect_group_bands(project: Project):
        """Bucket group labels by the edge they occupy.

        Returns ``(top, bottom, left, right)`` where top/bottom map a row index
        to the labels stacked on that edge (ordered outermost-first) and
        left/right are flat lists sharing one page-wide gutter so every row
        stays column-aligned.
        """
        row_by_cell = LayoutEngine._row_by_cell_id(project)
        top: Dict[int, List[GroupLabel]] = {}
        bottom: Dict[int, List[GroupLabel]] = {}
        left: List[GroupLabel] = []
        right: List[GroupLabel] = []

        for group_label in getattr(project, 'group_labels', []) or []:
            if not LayoutEngine.group_label_target_ids(project, group_label):
                continue
            side = group_label.side
            if side == "left":
                left.append(group_label)
            elif side == "right":
                right.append(group_label)
            elif side in ("top", "bottom"):
                row = LayoutEngine._group_label_row(project, group_label, row_by_cell)
                if row is None:
                    continue
                bucket = top if side == "top" else bottom
                bucket.setdefault(row, []).append(group_label)

        # Level 0 must end up nearest the artwork: top bands are walked
        # downwards, bottom bands upwards, hence the opposite sort orders.
        # Sorts are stable: equal levels keep creation order (first-added
        # sits outermost), never the random id.
        for labels in top.values():
            labels.sort(key=lambda g: -g.level)
        for labels in bottom.values():
            labels.sort(key=lambda g: g.level)
        left.sort(key=lambda g: g.level)
        right.sort(key=lambda g: g.level)
        return top, bottom, left, right

    @staticmethod
    def _band_slot_assignment(project: Project, labels: List[GroupLabel]
                              ) -> Tuple[Dict[str, int], List[Tuple[float, float]]]:
        """Interval-coloring for one edge bucket.

        Labels arrive sorted outermost-first.  Two labels whose target cell
        spans are DISJOINT share a band slot (same y, side by side) — only
        overlapping spans force a new, inner slot.  A slot's thickness/gap
        are the maxima of its members so every band fits.
        """
        slot_of: Dict[str, int] = {}
        slot_spans: List[set] = []
        slot_geoms: List[Tuple[float, float]] = []
        for group_label in labels:
            span = set(LayoutEngine.group_label_target_ids(project, group_label))
            thickness = LayoutEngine.group_label_thickness_mm(group_label)
            for idx, occupied in enumerate(slot_spans):
                if not (occupied & span):
                    occupied |= span
                    th, gp = slot_geoms[idx]
                    slot_geoms[idx] = (max(th, thickness), max(gp, group_label.gap_mm))
                    slot_of[group_label.id] = idx
                    break
            else:
                slot_spans.append(span)
                slot_geoms.append((thickness, group_label.gap_mm))
                slot_of[group_label.id] = len(slot_spans) - 1
        return slot_of, slot_geoms

    @staticmethod
    def _gutter_mm(group_labels: List[GroupLabel]) -> float:
        """Width a side gutter must reserve to fit its widest band."""
        if not group_labels:
            return 0.0
        return max(
            LayoutEngine.group_label_thickness_mm(g) + g.gap_mm
            for g in group_labels
        )

    @staticmethod
    def _bbox(rects: List[Tuple[float, float, float, float]]):
        if not rects:
            return None
        x0 = min(r[0] for r in rects)
        y0 = min(r[1] for r in rects)
        x1 = max(r[0] + r[2] for r in rects)
        y1 = max(r[1] + r[3] for r in rects)
        return (x0, y0, x1 - x0, y1 - y0)

    @staticmethod
    def _group_label_bbox(project: Project, group_label: GroupLabel,
                          cell_rects: Dict[str, Tuple[float, float, float, float]]):
        ids = LayoutEngine.group_label_target_ids(project, group_label)
        return LayoutEngine._bbox([cell_rects[i] for i in ids if i in cell_rects])

    @staticmethod
    def shared_label_eligible(cells: List) -> bool:
        """True when a selection can host one shared label.

        A span only makes sense over adjacent cells of a single row:
        scattered cells would produce a caption covering unrelated artwork.
        """
        if not cells:
            return False
        if len({c.row_index for c in cells}) != 1:
            return False
        cols = sorted({c.col_index for c in cells})
        return cols == list(range(cols[0], cols[0] + len(cols)))

    @staticmethod
    def group_label_auto_level(project: Project, cell_ids: List[str],
                               row_index: Optional[int], side: str) -> int:
        """Nesting level for a new label: count of same-side labels whose span
        strictly contains the new span.  Narrower runs nest nearer the
        artwork, matching the table super-header convention (level 0 sits
        closest, higher levels stack further out)."""
        if row_index is not None:
            new_span = {c.id for c in project.cells if c.row_index == row_index}
        else:
            new_span = set(cell_ids)
        level = 0
        for other in getattr(project, 'group_labels', []) or []:
            if other.side != side:
                continue
            other_span = set(LayoutEngine.group_label_target_ids(project, other))
            if other_span and new_span < other_span:
                level += 1
        return min(level, 5)

    @staticmethod
    def group_label_opposite_side(side: str) -> Optional[str]:
        """The only drag destination: spans flip vertically, rows horizontally."""
        return {"top": "bottom", "bottom": "top",
                "left": "right", "right": "left"}.get(side)

    @staticmethod
    def group_label_candidate_rect(
        project: Project, group_label: GroupLabel, side: str,
        layout_result: 'LayoutResult',
    ):
        """Rect the band would occupy on *side*, from the current layout.

        Used for drag-target hints: close enough to the post-reflow
        geometry to guide the eye without mutating the project.
        """
        bbox = LayoutEngine._group_label_bbox(
            project, group_label, layout_result.cell_rects)
        if bbox is None:
            return None
        x, y, w, h = bbox
        thickness = LayoutEngine.group_label_thickness_mm(group_label)
        gap = group_label.gap_mm
        if side == "top":
            return (x, y - gap - thickness, w, thickness)
        if side == "bottom":
            return (x, y + h + gap, w, thickness)
        if side == "left":
            return (x - gap - thickness, y, thickness, h)
        if side == "right":
            return (x + w + gap, y, thickness, h)
        return None

    @staticmethod
    def _compute_col_widths(r_temp: RowTemplate, content_width: float, gap_mm: float) -> List[float]:
        """Compute column widths for a row template."""
        col_count = r_temp.column_count
        if col_count <= 0:
            return []
        total_horizontal_gaps = (col_count - 1) * gap_mm if col_count > 1 else 0
        available_width = content_width - total_horizontal_gaps

        col_ratios = r_temp.column_ratios if r_temp.column_ratios else [1.0] * col_count
        while len(col_ratios) < col_count:
            col_ratios.append(1.0)
        col_ratios = col_ratios[:col_count]

        total_ratio = sum(col_ratios)
        if total_ratio <= 0:
            total_ratio = col_count
        return [(r / total_ratio) * available_width for r in col_ratios]

    @staticmethod
    def calculate_freeform_layout(project: Project) -> LayoutResult:
        """Freeform pipeline: cells use their own absolute position/size fields."""
        cell_rects: Dict[str, Tuple[float, float, float, float]] = {}
        for cell in project.cells:
            # Only top-level leaf cells contribute directly
            if cell.is_leaf:
                cell_rects[cell.id] = (
                    cell.freeform_x_mm,
                    cell.freeform_y_mm,
                    cell.freeform_w_mm,
                    cell.freeform_h_mm,
                )
            else:
                # Split cells: use freeform rect as parent, then sub-layout children
                sub_rects: Dict[str, Tuple[float, float, float, float]] = {}
                sub_label: Dict[str, Tuple[float, float, float, float]] = {}
                parent_rect = (cell.freeform_x_mm, cell.freeform_y_mm,
                               cell.freeform_w_mm, cell.freeform_h_mm)
                LayoutEngine._layout_subcells(cell, parent_rect, project.gap_mm,
                                              sub_rects, sub_label, {}, {})
                cell_rects.update(sub_rects)
        return LayoutResult(
            cell_rects=cell_rects, row_heights={}, figure_rects=dict(cell_rects),
            group_label_rects=LayoutEngine._freeform_group_label_rects(project, cell_rects),
        )

    @staticmethod
    def _freeform_group_label_rects(
        project: Project,
        cell_rects: Dict[str, Tuple[float, float, float, float]],
    ) -> Dict[str, Tuple[float, float, float, float]]:
        """Place group-label bands just outside their target's bounding box.

        Freeform mode has no grid to reflow, so bands are positioned rather
        than reserved; overlap is the user's call, matching how freeform
        treats cells themselves.
        """
        rects: Dict[str, Tuple[float, float, float, float]] = {}
        for group_label in getattr(project, 'group_labels', []) or []:
            bbox = LayoutEngine._group_label_bbox(project, group_label, cell_rects)
            if bbox is None:
                continue
            x, y, w, h = bbox
            thickness = LayoutEngine.group_label_thickness_mm(group_label)
            gap = group_label.gap_mm
            if group_label.side == "top":
                rects[group_label.id] = (x, y - gap - thickness, w, thickness)
            elif group_label.side == "bottom":
                rects[group_label.id] = (x, y + h + gap, w, thickness)
            elif group_label.side == "left":
                rects[group_label.id] = (x - gap - thickness, y, thickness, h)
            else:  # right
                rects[group_label.id] = (x + w + gap, y, thickness, h)
        return rects

    @staticmethod
    def calculate_layout(project: Project) -> LayoutResult:
        """
        Calculates the geometry for all cells in the project.
        All units are in millimeters.
        """
        if getattr(project, 'layout_mode', 'grid') == 'freeform':
            return LayoutEngine.calculate_freeform_layout(project)

        gap_mm = project.gap_mm
        
        # 1. Calculate content area
        content_width = project.page_width_mm - project.margin_left_mm - project.margin_right_mm
        content_height = project.page_height_mm - project.margin_top_mm - project.margin_bottom_mm
        
        if content_width <= 0 or content_height <= 0:
            return LayoutResult({}, {})

        # 2. Determine number of rows
        row_templates = sorted(project.rows, key=lambda r: r.index)
        if not row_templates:
            return LayoutResult({}, {})
            
        num_rows = len(row_templates)

        # Effective placement per labelled cell (per-label override beats the
        # project default), so one figure can mix in-cell and out-of-cell labels.
        placements, strip_sizes = LayoutEngine.resolve_label_placements(project)

        # Group-label bands claim space before anything else is measured.
        bands_top, bands_bottom, bands_left, bands_right = \
            LayoutEngine._collect_group_bands(project)
        gutter_left = LayoutEngine._gutter_mm(bands_left)
        gutter_right = LayoutEngine._gutter_mm(bands_right)
        content_x = project.margin_left_mm + gutter_left
        content_width = max(0.0, content_width - gutter_left - gutter_right)
        if content_width <= 0:
            return LayoutResult({}, {})

        # Per-row cell-label strips. A row reserves one strip above and/or one
        # below, thick enough for the largest label that lands in it.
        strips_above: Dict[int, float] = {}
        strips_below: Dict[int, float] = {}
        for cell in project.cells:
            placement = placements.get(cell.id)
            if placement == "label_row_above":
                bucket = strips_above
            elif placement == "label_row_below":
                bucket = strips_below
            else:
                continue
            size = strip_sizes.get(cell.id, 0.0)
            bucket[cell.row_index] = max(bucket.get(cell.row_index, 0.0), size)

        # 3. Calculate row heights. Every reserved band costs its thickness
        # plus one gap, so the walk below and this budget stay in step.
        total_vertical_gaps = (num_rows - 1) * gap_mm if num_rows > 1 else 0
        reserved_height = 0.0
        for row_index in strips_above:
            reserved_height += strips_above[row_index] + gap_mm
        for row_index in strips_below:
            reserved_height += strips_below[row_index] + gap_mm
        # Slot assignment per (side, row): disjoint spans share one band.
        band_slots_info: Dict[Tuple[str, int], Tuple[Dict[str, int], List[Tuple[float, float]]]] = {}
        for side, bucket in (("top", bands_top), ("bottom", bands_bottom)):
            for row_idx, labels in bucket.items():
                slot_of, slot_geoms = LayoutEngine._band_slot_assignment(project, labels)
                band_slots_info[(side, row_idx)] = (slot_of, slot_geoms)
                for thickness, slot_gap in slot_geoms:
                    reserved_height += thickness + slot_gap

        available_height_for_rows = content_height - total_vertical_gaps - reserved_height
        
        if available_height_for_rows < 0:
            available_height_for_rows = 0
            
        total_ratio = sum(r.height_ratio for r in row_templates)
        if total_ratio == 0:
            total_ratio = num_rows
        
        row_heights = {}
        current_y = project.margin_top_mm

        # Per row: (above_y, above_h, below_y, below_h, pic_y, pic_h,
        #           row_template, band_slots) where band_slots maps a group
        #           label id to its (y, thickness).
        calculated_row_geometries = []

        for r_temp in row_templates:
            ratio = r_temp.height_ratio if total_ratio > 0 else 1.0
            pic_h = (ratio / total_ratio) * available_height_for_rows
            row_heights[r_temp.index] = pic_h

            band_slots: Dict[str, Tuple[float, float]] = {}
            y = current_y

            # Outer-to-inner: group bands, then the cell-label strip.
            # Same-slot (disjoint-span) labels share one y — side by side.
            slot_of, slot_geoms = band_slots_info.get(("top", r_temp.index), ({}, []))
            for slot_idx, (thickness, slot_gap) in enumerate(slot_geoms):
                for group_label in bands_top.get(r_temp.index, []):
                    if slot_of.get(group_label.id) == slot_idx:
                        band_slots[group_label.id] = (y, thickness)
                y += thickness + slot_gap

            above_h = strips_above.get(r_temp.index, 0.0)
            above_y = None
            if above_h > 0:
                above_y = y
                y += above_h + gap_mm

            pic_y = y
            y = pic_y + pic_h

            below_h = strips_below.get(r_temp.index, 0.0)
            below_y = None
            if below_h > 0:
                y += gap_mm
                below_y = y
                y += below_h

            slot_of, slot_geoms = band_slots_info.get(("bottom", r_temp.index), ({}, []))
            for slot_idx, (thickness, slot_gap) in enumerate(slot_geoms):
                y += slot_gap
                for group_label in bands_bottom.get(r_temp.index, []):
                    if slot_of.get(group_label.id) == slot_idx:
                        band_slots[group_label.id] = (y, thickness)
                y += thickness

            calculated_row_geometries.append(
                (above_y, above_h, below_y, below_h, pic_y, pic_h, r_temp, band_slots)
            )
            current_y = y + gap_mm
            
        # 4. Handle grid mode configuration
        grid_mode = getattr(project, "grid_mode", "stretch")
        row_alignment = getattr(project, "row_alignment", "center")
        
        # Calculate standard column width for fixed grid mode
        max_col_count = max((r.column_count for r in row_templates), default=1)
        standard_col_widths = []
        if grid_mode == "fixed" and max_col_count > 0:
            # Create a dummy row template with max columns to compute standard widths
            # We assume all rows in fixed mode share the column ratios of the widest row
            # If multiple rows have the same max width but different ratios, we just use the first one
            widest_row = next(r for r in row_templates if r.column_count == max_col_count)
            standard_col_widths = LayoutEngine._compute_col_widths(widest_row, content_width, gap_mm)
            
        # 5. Calculate cell rectangles and label cell rectangles
        cell_rects = {}
        label_rects: Dict[str, Tuple[float, float, float, float]] = {}
        
        for (above_y, above_h, below_y, below_h, pic_y, pic_h,
             r_temp, _band_slots) in calculated_row_geometries:
            col_count = r_temp.column_count
            if col_count <= 0:
                continue

            if grid_mode == "fixed" and max_col_count > 0:
                # Use standard column widths up to this row's column count
                col_widths = standard_col_widths[:col_count]
                row_width = sum(col_widths) + (col_count - 1) * gap_mm if col_count > 1 else sum(col_widths)
                
                # Apply row alignment offset
                if row_alignment == "left":
                    x_offset = content_x
                elif row_alignment == "right":
                    x_offset = content_x + content_width - row_width
                else: # center (default)
                    x_offset = content_x + (content_width - row_width) / 2.0
            else:
                # Stretch mode (default behavior)
                col_widths = LayoutEngine._compute_col_widths(r_temp, content_width, gap_mm)
                x_offset = content_x
                row_width = content_width

            row_cells = [c for c in project.cells if c.row_index == r_temp.index]
            
            for cell in row_cells:
                if cell.col_index >= col_count:
                    continue
                
                x_pos = x_offset
                for i in range(cell.col_index):
                    x_pos += col_widths[i] + gap_mm
                
                col_w = col_widths[cell.col_index]
                placement = placements.get(cell.id)

                # Reserve a label strip on the left or right edge of the picture cell.
                pic_x_eff = x_pos
                pic_w_eff = col_w
                lbl_side_rect = None
                if placement in ("label_col_left", "label_col_right"):
                    label_col_w = strip_sizes.get(cell.id, 0.0)
                    strip = min(label_col_w, col_w - 1.0) if col_w > 1.0 else 0.0
                    if strip > 0:
                        if placement == "label_col_left":
                            lbl_side_rect = (x_pos, pic_y, strip, pic_h)
                            pic_x_eff = x_pos + strip + gap_mm
                            pic_w_eff = max(0.0, col_w - strip - gap_mm)
                        else:  # label_col_right
                            lbl_side_rect = (x_pos + col_w - strip, pic_y, strip, pic_h)
                            pic_w_eff = max(0.0, col_w - strip - gap_mm)

                cell_rects[cell.id] = (pic_x_eff, pic_y, pic_w_eff, pic_h)

                # Label cell rect: for top-level cells (leaf or container) that have a numbering label
                if placement == "label_row_above" and above_y is not None:
                    label_rects[cell.id] = (x_pos, above_y, col_w, above_h)
                elif placement == "label_row_below" and below_y is not None:
                    label_rects[cell.id] = (x_pos, below_y, col_w, below_h)
                elif lbl_side_rect is not None:
                    label_rects[cell.id] = lbl_side_rect

                # Recursively layout sub-cells
                if not cell.is_leaf:
                    LayoutEngine._layout_subcells(
                        cell, (pic_x_eff, pic_y, pic_w_eff, pic_h),
                        gap_mm, cell_rects, label_rects,
                        placements, strip_sizes
                    )

        figure_rects: Dict[str, Tuple[float, float, float, float]] = dict(cell_rects)

        # Apply grid size overrides (including size-group resolution)
        if getattr(project, 'layout_mode', 'grid') == 'grid':
            # Resolve per-cell effective overrides. Size groups take precedence over per-cell overrides.
            effective_overrides = LayoutEngine._resolve_group_overrides(project, cell_rects)
            for cell in project.get_all_leaf_cells():
                if cell.id in cell_rects:
                    sx, sy, sw, sh = cell_rects[cell.id]
                    eff_ow, eff_oh = effective_overrides.get(
                        cell.id,
                        (getattr(cell, 'override_width_mm', 0.0),
                         getattr(cell, 'override_height_mm', 0.0))
                    )
                    ow = eff_ow
                    oh = eff_oh

                    if ow > 0 or oh > 0:
                        fw = ow if ow > 0 else sw
                        fh = oh if oh > 0 else sh
                        
                        align_h = getattr(cell, 'align_h', 'center')
                        align_v = getattr(cell, 'align_v', 'center')
                        
                        if align_h == 'left':
                            fx = sx
                        elif align_h == 'right':
                            fx = sx + sw - fw
                        else:
                            fx = sx + (sw - fw) / 2.0
                            
                        if align_v == 'top':
                            fy = sy
                        elif align_v == 'bottom':
                            fy = sy + sh - fh
                        else:
                            fy = sy + (sh - fh) / 2.0
                            
                        cell_rects[cell.id] = (fx, fy, fw, fh)
                        figure_rects[cell.id] = (fx, fy, fw, fh)

        # Compute row bounding rects (include label strips if present)
        row_rects: Dict[int, Tuple[float, float, float, float]] = {}
        row_spans: Dict[int, Tuple[float, float]] = {}
        for (above_y, above_h, below_y, below_h, pic_y, pic_h,
             r_temp, _band_slots) in calculated_row_geometries:
            col_count = r_temp.column_count
            
            # Re-calculate x_offset and row_width for bounding rect
            if grid_mode == "fixed" and max_col_count > 0:
                col_widths = standard_col_widths[:col_count]
                row_width = sum(col_widths) + (col_count - 1) * gap_mm if col_count > 1 else sum(col_widths)
                if row_alignment == "left":
                    x_offset = content_x
                elif row_alignment == "right":
                    x_offset = content_x + content_width - row_width
                else: # center
                    x_offset = content_x + (content_width - row_width) / 2.0
            else:
                x_offset = content_x
                row_width = content_width

            top_y = pic_y if above_y is None else min(above_y, pic_y)
            bot_y = pic_y + pic_h
            if below_y is not None:
                bot_y = max(bot_y, below_y + below_h)
            row_rects[r_temp.index] = (x_offset, top_y, row_width, bot_y - top_y)
            row_spans[r_temp.index] = (x_offset, row_width)

        group_label_rects = LayoutEngine._compute_group_label_rects(
            project, calculated_row_geometries, cell_rects, row_spans,
            bands_left, bands_right, content_x, content_width,
        )

        return LayoutResult(cell_rects, row_heights, figure_rects=figure_rects,
                            label_rects=label_rects, row_rects=row_rects,
                            group_label_rects=group_label_rects)

    @staticmethod
    def _compute_group_label_rects(
        project: Project,
        calculated_row_geometries: list,
        cell_rects: Dict[str, Tuple[float, float, float, float]],
        row_spans: Dict[int, Tuple[float, float]],
        bands_left: List[GroupLabel],
        bands_right: List[GroupLabel],
        content_x: float,
        content_width: float,
    ) -> Dict[str, Tuple[float, float, float, float]]:
        """Turn reserved band slots into concrete mm rectangles.

        Top/bottom bands take their y from the row walk and their x-span from
        the target (whole row, or the bounding box of the spanned cells).
        Left/right bands sit in the shared gutter, hugging the artwork so
        bands of differing thickness still align with the figure edge.
        """
        rects: Dict[str, Tuple[float, float, float, float]] = {}

        for (_above_y, _above_h, _below_y, _below_h, _pic_y, _pic_h,
             r_temp, band_slots) in calculated_row_geometries:
            if not band_slots:
                continue
            row_x, row_w = row_spans.get(r_temp.index, (content_x, content_width))
            for group_label_id, (band_y, thickness) in band_slots.items():
                group_label = project.find_group_label(group_label_id)
                if group_label is None:
                    continue
                if group_label.row_index is not None:
                    x, w = row_x, row_w
                else:
                    bbox = LayoutEngine._group_label_bbox(project, group_label, cell_rects)
                    if bbox is None:
                        continue
                    x, w = bbox[0], bbox[2]
                rects[group_label_id] = (x, band_y, w, thickness)

        content_right = content_x + content_width
        for group_label in bands_left:
            bbox = LayoutEngine._group_label_bbox(project, group_label, cell_rects)
            if bbox is None:
                continue
            thickness = LayoutEngine.group_label_thickness_mm(group_label)
            x = content_x - group_label.gap_mm - thickness
            rects[group_label.id] = (x, bbox[1], thickness, bbox[3])

        for group_label in bands_right:
            bbox = LayoutEngine._group_label_bbox(project, group_label, cell_rects)
            if bbox is None:
                continue
            thickness = LayoutEngine.group_label_thickness_mm(group_label)
            x = content_right + group_label.gap_mm
            rects[group_label.id] = (x, bbox[1], thickness, bbox[3])

        return rects

    @staticmethod
    def _resolve_group_overrides(
        project: 'Project',
        natural_cell_rects: Dict[str, Tuple[float, float, float, float]],
    ) -> Dict[str, Tuple[float, float]]:
        """Resolve each cell's effective (override_w, override_h) accounting for size groups.

        Rules:
        - Ungrouped cell: return its own (override_width_mm, override_height_mm).
        - Cell in a group:
            * If group.pinned_width_mm  > 0: effective width  = pinned_width.
              Else: effective width  = min of natural widths of members (program-controlled shared).
            * Same for height independently.
          Per-cell override_width_mm / override_height_mm are ignored for grouped cells
          (the group owns the shared size).
        """
        result: Dict[str, Tuple[float, float]] = {}
        groups = getattr(project, 'size_groups', []) or []
        if not groups:
            # No groups: just return per-cell overrides.
            for cell in project.get_all_leaf_cells():
                result[cell.id] = (
                    getattr(cell, 'override_width_mm', 0.0),
                    getattr(cell, 'override_height_mm', 0.0),
                )
            return result

        # Pre-compute natural sizes per group (for program-controlled shared sizing).
        group_natural_min_w: Dict[str, float] = {}
        group_natural_min_h: Dict[str, float] = {}
        for g in groups:
            members = [c for c in project.get_all_leaf_cells() if c.size_group_id == g.id]
            ws, hs = [], []
            for m in members:
                if m.id in natural_cell_rects:
                    _, _, nw, nh = natural_cell_rects[m.id]
                    if nw > 0:
                        ws.append(nw)
                    if nh > 0:
                        hs.append(nh)
            group_natural_min_w[g.id] = min(ws) if ws else 0.0
            group_natural_min_h[g.id] = min(hs) if hs else 0.0

        # Resolve per-cell effective overrides.
        for cell in project.get_all_leaf_cells():
            gid = getattr(cell, 'size_group_id', None)
            if gid:
                g = next((x for x in groups if x.id == gid), None)
                if g is None:
                    # Orphan reference: fall back to per-cell.
                    result[cell.id] = (
                        getattr(cell, 'override_width_mm', 0.0),
                        getattr(cell, 'override_height_mm', 0.0),
                    )
                    continue
                eff_w = g.pinned_width_mm if g.pinned_width_mm > 0 else group_natural_min_w.get(g.id, 0.0)
                eff_h = g.pinned_height_mm if g.pinned_height_mm > 0 else group_natural_min_h.get(g.id, 0.0)
                result[cell.id] = (eff_w, eff_h)
            else:
                result[cell.id] = (
                    getattr(cell, 'override_width_mm', 0.0),
                    getattr(cell, 'override_height_mm', 0.0),
                )
        return result

    @staticmethod
    def _layout_subcells(
        parent_cell: 'Cell',
        parent_rect: Tuple[float, float, float, float],
        gap_mm: float,
        cell_rects: Dict[str, Tuple[float, float, float, float]],
        label_rects: Dict[str, Tuple[float, float, float, float]],
        placements: Dict[str, str],
        strip_sizes: Dict[str, float],
    ):
        """Recursively compute geometry for sub-cells within a parent cell.

        Sub-cells honour the ``label_row_above`` / ``label_row_below``
        placements; side strips are a top-level feature because a nested
        column strip would fight the parent's split ratios.
        """
        children = parent_cell.children
        if not children:
            return

        def strip_for(child, wanted: str) -> float:
            """Strip thickness this child needs on the *wanted* edge, else 0."""
            if placements.get(child.id) != wanted:
                return 0.0
            return strip_sizes.get(child.id, 0.0)

        px, py, pw, ph = parent_rect
        n = len(children)
        ratios = list(parent_cell.split_ratios) if parent_cell.split_ratios else [1.0] * n
        while len(ratios) < n:
            ratios.append(1.0)
        ratios = ratios[:n]
        total_ratio = sum(ratios)
        if total_ratio <= 0:
            total_ratio = float(n)

        total_gap = (n - 1) * gap_mm if n > 1 else 0.0

        if parent_cell.split_direction == "vertical":
            # --- Vertical stacking: divide height ---
            # Account for label strips around children and fixed-height children.
            label_space = 0.0
            fixed_h_total = 0.0
            ratio_sum = 0.0
            for i, child in enumerate(children):
                for edge in ("label_row_above", "label_row_below"):
                    size = strip_for(child, edge)
                    if size > 0:
                        label_space += size + gap_mm
                oh = getattr(child, 'override_height_mm', 0.0)
                if oh > 0:
                    fixed_h_total += oh
                else:
                    ratio_sum += ratios[i]
            if ratio_sum <= 0:
                ratio_sum = 1.0

            available = ph - total_gap - label_space - fixed_h_total
            if available < 0:
                available = 0
            current_y = py
            for i, child in enumerate(children):
                above = strip_for(child, "label_row_above")
                if above > 0:
                    label_rects[child.id] = (px, current_y, pw, above)
                    current_y += above + gap_mm

                oh = getattr(child, 'override_height_mm', 0.0)
                child_h = oh if oh > 0 else (ratios[i] / ratio_sum) * available
                child_rect = (px, current_y, pw, child_h)
                cell_rects[child.id] = child_rect

                if not child.is_leaf:
                    LayoutEngine._layout_subcells(
                        child, child_rect, gap_mm, cell_rects,
                        label_rects, placements, strip_sizes
                    )
                current_y += child_h + gap_mm

                below = strip_for(child, "label_row_below")
                if below > 0:
                    label_rects[child.id] = (px, current_y, pw, below)
                    current_y += below + gap_mm

        elif parent_cell.split_direction == "horizontal":
            # --- Horizontal stacking: divide width ---
            # Account for fixed-width children; ratio children share the remainder.
            fixed_w_total = 0.0
            ratio_sum = 0.0
            for i, child in enumerate(children):
                ow = getattr(child, 'override_width_mm', 0.0)
                if ow > 0:
                    fixed_w_total += ow
                else:
                    ratio_sum += ratios[i]
            if ratio_sum <= 0:
                ratio_sum = 1.0

            available = max(0.0, pw - total_gap - fixed_w_total)

            # Side-by-side children must share one baseline, so a strip wanted
            # by any one of them is reserved across the whole band. Height is
            # the thickest request on that edge.
            above_h = max((strip_for(c, "label_row_above") for c in children), default=0.0)
            below_h = max((strip_for(c, "label_row_below") for c in children), default=0.0)
            above_overhead = (above_h + gap_mm) if above_h > 0 else 0.0
            below_overhead = (below_h + gap_mm) if below_h > 0 else 0.0
            img_py = py + above_overhead
            img_ph = max(0.0, ph - above_overhead - below_overhead)
            below_y = img_py + img_ph + gap_mm

            current_x = px
            for i, child in enumerate(children):
                ow = getattr(child, 'override_width_mm', 0.0)
                child_w = ow if ow > 0 else (ratios[i] / ratio_sum) * available

                # Label rect: spans the child's width, sits in the reserved strip
                if strip_for(child, "label_row_above") > 0:
                    label_rects[child.id] = (current_x, py, child_w, above_h)
                elif strip_for(child, "label_row_below") > 0:
                    label_rects[child.id] = (current_x, below_y, child_w, below_h)

                child_rect = (current_x, img_py, child_w, img_ph)
                cell_rects[child.id] = child_rect

                if not child.is_leaf:
                    LayoutEngine._layout_subcells(
                        child, child_rect, gap_mm, cell_rects,
                        label_rects, placements, strip_sizes
                    )
                current_x += child_w + gap_mm
