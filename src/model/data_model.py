import json
import os
import uuid
from dataclasses import dataclass, field, fields
from typing import List, Optional, Dict, Any
from .enums import FitMode, LabelPosition, PageSizePreset
from src.version import APP_VERSION

@dataclass
class TextItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    text: str = "Text"
    font_family: str = "Arial"
    font_size_pt: int = 12
    font_weight: str = "normal" # normal, bold
    color: str = "#000000"
    
    # Position
    scope: str = "global" # global, cell
    subtype: Optional[str] = None # numbering, corner, or None
    parent_id: Optional[str] = None # if scope is cell
    
    # For global/floating text: absolute canvas position in MILLIMETRES.
    # Scene coordinates are in mm (page_rect is in mm), so these values are
    # DPI-independent and stable across canvas resizes.
    x: float = 0.0
    y: float = 0.0

    # Rotation in degrees, applied around the text's visual centre.
    # 0 = upright, 90 = reads top-to-bottom, etc. Arbitrary values allowed.
    rotation: float = 0.0

    # For anchored text (e.g. labels)
    anchor: Optional[str] = None # top_left, etc.
    offset_x: float = 0.0
    offset_y: float = 0.0

    # Background box (for label aesthetics on dark images).
    bg_enabled: bool = False
    bg_color: str = "#FFFFFF"
    bg_padding_mm: float = 0.6

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "text": self.text,
            "font_family": self.font_family,
            "font_size_pt": self.font_size_pt,
            "font_weight": self.font_weight,
            "color": self.color,
            "scope": self.scope,
            "subtype": self.subtype,
            "parent_id": self.parent_id,
            "x": self.x,
            "y": self.y,
            "rotation": self.rotation,
            "anchor": self.anchor,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
            "bg_enabled": self.bg_enabled,
            "bg_color": self.bg_color,
            "bg_padding_mm": self.bg_padding_mm,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextItem':
        # Filter to known fields so older/newer saves don't crash the loader.
        allowed = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in allowed}
        return cls(**clean)

@dataclass
class PiPItem:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    pip_type: str = "external"          # "zoom" | "external"
    image_path: Optional[str] = None    # None means use parent image (zoom type)
    crop_left: float = 0.0
    crop_top: float = 0.0
    crop_right: float = 0.30
    crop_bottom: float = 0.30
    x: float = 0.62
    y: float = 0.62
    w: float = 0.33
    h: float = 0.33
    border_enabled: bool = True
    border_color: str = "#FFFFFF"
    border_width_pt: float = 1.5
    border_style: str = "solid"   # "solid" | "dashed"
    show_origin_box: bool = True
    origin_box_color: str = "#FFFFFF"
    origin_box_style: str = "solid"
    origin_box_width_pt: float = 1.0

    # Scale bar properties
    scale_bar_enabled: bool = False
    scale_bar_mode: str = "rgb"
    scale_bar_um_per_px: float = 0.0  # 0.0 means inherit from parent if zoom type
    scale_bar_length_um: float = 10.0
    scale_bar_unit: str = "µm"
    scale_bar_color: str = "#FFFFFF"
    scale_bar_show_text: bool = True
    scale_bar_thickness_mm: float = 0.5
    scale_bar_position: str = "bottom_right"
    scale_bar_offset_x: float = 2.0
    scale_bar_offset_y: float = 2.0
    scale_bar_custom_text: Optional[str] = None
    scale_bar_text_size_mm: float = 2.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "pip_type": self.pip_type,
            "image_path": self.image_path,
            "crop_left": self.crop_left,
            "crop_top": self.crop_top,
            "crop_right": self.crop_right,
            "crop_bottom": self.crop_bottom,
            "x": self.x,
            "y": self.y,
            "w": self.w,
            "h": self.h,
            "border_enabled": self.border_enabled,
            "border_color": self.border_color,
            "border_width_pt": self.border_width_pt,
            "border_style": self.border_style,
            "show_origin_box": self.show_origin_box,
            "origin_box_color": self.origin_box_color,
            "origin_box_style": self.origin_box_style,
            "origin_box_width_pt": self.origin_box_width_pt,
            "scale_bar_enabled": self.scale_bar_enabled,
            "scale_bar_mode": self.scale_bar_mode,
            "scale_bar_um_per_px": self.scale_bar_um_per_px,
            "scale_bar_length_um": self.scale_bar_length_um,
            "scale_bar_unit": self.scale_bar_unit,
            "scale_bar_color": self.scale_bar_color,
            "scale_bar_show_text": self.scale_bar_show_text,
            "scale_bar_thickness_mm": self.scale_bar_thickness_mm,
            "scale_bar_position": self.scale_bar_position,
            "scale_bar_offset_x": self.scale_bar_offset_x,
            "scale_bar_offset_y": self.scale_bar_offset_y,
            "scale_bar_custom_text": self.scale_bar_custom_text,
            "scale_bar_text_size_mm": self.scale_bar_text_size_mm,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PiPItem':
        allowed = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in allowed}
        return cls(**clean)


@dataclass
class SvgTextMember:
    svg_path: str = ""
    element_key: str = ""  # id attr or _pos_{N}

    def to_dict(self) -> Dict[str, Any]:
        return {"svg_path": self.svg_path, "element_key": self.element_key}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SvgTextMember':
        return cls(svg_path=data.get("svg_path", ""), element_key=data.get("element_key", ""))


@dataclass
class SvgTextGroup:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Text Group"
    font_size_pt: float = 12.0
    members: List['SvgTextMember'] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "font_size_pt": self.font_size_pt,
            "members": [m.to_dict() for m in self.members],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SvgTextGroup':
        return cls(
            id=data.get("id", str(uuid.uuid4())),
            name=data.get("name", "Text Group"),
            font_size_pt=float(data.get("font_size_pt", 12.0)),
            members=[SvgTextMember.from_dict(m) for m in data.get("members", [])],
        )


@dataclass
class SizeGroup:
    """A named group that forces member cells to share the same W/H.

    - pinned_width_mm / pinned_height_mm > 0 -> user-pinned absolute size
    - 0 -> program-controlled (layout engine picks min of members' natural size)
    """
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Group"
    pinned_width_mm: float = 0.0
    pinned_height_mm: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "pinned_width_mm": self.pinned_width_mm,
            "pinned_height_mm": self.pinned_height_mm,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SizeGroup':
        allowed = {f.name for f in fields(cls)}
        clean = {k: v for k, v in data.items() if k in allowed}
        return cls(**clean)


@dataclass
class Cell:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    row_index: int = 0
    col_index: int = 0
    
    # Content
    image_path: Optional[str] = None
    # Sticky original-source path: set once at first pack/import, never
    # rewritten by save. Used by figpack to keep deterministic asset
    # paths stable across pack→unpack→repack cycles. See plan.md §6.5.
    original_source_path: Optional[str] = None
    
    # Layout/Style
    fit_mode: str = FitMode.CONTAIN.value
    rotation: int = 0  # 0, 90, 180, 270 degrees
    align_h: str = "center"  # left, center, right
    align_v: str = "center"  # top, center, bottom
    padding_top: float = 0.0
    padding_bottom: float = 0.0
    padding_left: float = 0.0
    padding_right: float = 0.0
    
    # If it is a placeholder
    is_placeholder: bool = False

    # Sub-cell hierarchy
    children: List['Cell'] = field(default_factory=list)
    split_direction: str = "none"  # "none" | "horizontal" | "vertical"
    split_ratios: List[float] = field(default_factory=list)

    # Scale bar (microscopy)
    scale_bar_enabled: bool = False
    scale_bar_mode: str = "rgb"  # mapping name chosen by the user
    scale_bar_um_per_px: float = 0.1301  # µm per source-image pixel for the chosen mapping
    scale_bar_length_um: float = 10.0
    scale_bar_color: str = "#FFFFFF"  # white or black
    scale_bar_show_text: bool = True
    scale_bar_thickness_mm: float = 0.5
    scale_bar_position: str = "bottom_right"  # bottom_left | bottom_center | bottom_right
    scale_bar_offset_x: float = 2.0
    scale_bar_offset_y: float = 2.0
    scale_bar_custom_text: Optional[str] = None  # If set, overrides auto-generated "X µm" text
    scale_bar_text_size_mm: float = 2.0  # Font size in mm for scale bar text
    scale_bar_unit: str = "µm"  # Display unit for the length field (m/cm/dm/mm/µm/nm/pm/fm)

    # Freeform layout (used when Project.layout_mode == "freeform")
    freeform_x_mm: float = 0.0
    freeform_y_mm: float = 0.0
    freeform_w_mm: float = 50.0
    freeform_h_mm: float = 50.0
    z_index: int = 0
    
    # Grid override size (0 means auto). Per-cell absolute pin (when NOT in a size group).
    override_width_mm: float = 0.0
    override_height_mm: float = 0.0

    # Size group membership (forces shared W/H with other members). None = ungrouped.
    size_group_id: Optional[str] = None

    # Crop (normalized fractions 0.0–1.0 of original image dimensions, before rotation)
    crop_left: float = 0.0
    crop_top: float = 0.0
    crop_right: float = 1.0
    crop_bottom: float = 1.0

    # PiP insets
    pip_items: List[PiPItem] = field(default_factory=list)

    @property
    def is_leaf(self) -> bool:
        return len(self.children) == 0

    def get_all_leaves(self) -> List['Cell']:
        if self.is_leaf:
            return [self]
        result = []
        for child in self.children:
            result.extend(child.get_all_leaves())
        return result

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "image_path": self.image_path,
            "original_source_path": self.original_source_path,
            "fit_mode": self.fit_mode,
            "rotation": self.rotation,
            "align_h": self.align_h,
            "align_v": self.align_v,
            "padding_top": self.padding_top,
            "padding_bottom": self.padding_bottom,
            "padding_left": self.padding_left,
            "padding_right": self.padding_right,
            "is_placeholder": self.is_placeholder,
            "scale_bar_enabled": self.scale_bar_enabled,
            "scale_bar_mode": self.scale_bar_mode,
            "scale_bar_um_per_px": self.scale_bar_um_per_px,
            "scale_bar_length_um": self.scale_bar_length_um,
            "scale_bar_color": self.scale_bar_color,
            "scale_bar_show_text": self.scale_bar_show_text,
            "scale_bar_thickness_mm": self.scale_bar_thickness_mm,
            "scale_bar_position": self.scale_bar_position,
            "scale_bar_offset_x": self.scale_bar_offset_x,
            "scale_bar_offset_y": self.scale_bar_offset_y,
            "scale_bar_custom_text": self.scale_bar_custom_text,
            "scale_bar_text_size_mm": self.scale_bar_text_size_mm,
            "scale_bar_unit": self.scale_bar_unit,
            "freeform_x_mm": self.freeform_x_mm,
            "freeform_y_mm": self.freeform_y_mm,
            "freeform_w_mm": self.freeform_w_mm,
            "freeform_h_mm": self.freeform_h_mm,
            "override_width_mm": self.override_width_mm,
            "override_height_mm": self.override_height_mm,
            "size_group_id": self.size_group_id,
            "z_index": self.z_index,
            "crop_left": self.crop_left,
            "crop_top": self.crop_top,
            "crop_right": self.crop_right,
            "crop_bottom": self.crop_bottom,
            "children": [c.to_dict() for c in self.children],
            "split_direction": self.split_direction,
            "split_ratios": self.split_ratios,
            "pip_items": [p.to_dict() for p in self.pip_items],
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], project_dir: Optional[str] = None) -> 'Cell':
        # Backward compatibility: older projects may not have scale bar fields
        payload = dict(data)
        payload.setdefault("rotation", 0)
        payload.setdefault("scale_bar_enabled", False)
        payload.setdefault("scale_bar_mode", "rgb")
        # Backward compat: derive µm/px from the old mode string when not present
        if "scale_bar_um_per_px" not in payload:
            _legacy = {"rgb": 0.1301, "bayer": 0.2569}
            payload["scale_bar_um_per_px"] = _legacy.get(payload.get("scale_bar_mode", "rgb"), 0.1301)
        payload.setdefault("scale_bar_length_um", 10.0)
        payload.setdefault("scale_bar_color", "#FFFFFF")
        payload.setdefault("scale_bar_show_text", True)
        payload.setdefault("scale_bar_thickness_mm", 0.5)
        payload.setdefault("scale_bar_position", "bottom_right")
        payload.setdefault("scale_bar_offset_x", 2.0)
        payload.setdefault("scale_bar_offset_y", 2.0)
        payload.setdefault("scale_bar_custom_text", None)
        payload.setdefault("scale_bar_text_size_mm", 2.0)
        payload.setdefault("scale_bar_unit", "µm")
        payload.setdefault("freeform_x_mm", 0.0)
        payload.setdefault("freeform_y_mm", 0.0)
        payload.setdefault("freeform_w_mm", 50.0)
        payload.setdefault("freeform_h_mm", 50.0)
        payload.setdefault("override_width_mm", 0.0)
        payload.setdefault("override_height_mm", 0.0)
        payload.setdefault("size_group_id", None)
        payload.setdefault("z_index", 0)
        payload.setdefault("split_direction", "none")
        payload.setdefault("split_ratios", [])
        payload.setdefault("crop_left", 0.0)
        payload.setdefault("crop_top", 0.0)
        payload.setdefault("crop_right", 1.0)
        payload.setdefault("crop_bottom", 1.0)
        
        # Drop legacy keys from removed features so older project files
        # still load on newer builds (nested layouts removed Apr 2026).
        payload.pop("nested_layout_path", None)

        # Handle children separately (recursive deserialization)
        children_data = payload.pop("children", [])
        pip_items_data = payload.pop("pip_items", [])
        
        # Resolve image path: try absolute first, then relative to project file
        if payload.get("image_path") and project_dir:
            abs_path = payload["image_path"]
            # If absolute path doesn't exist, try relative to project directory
            if not os.path.isfile(abs_path):
                filename = os.path.basename(abs_path)
                relative_path = os.path.join(project_dir, filename)
                if os.path.isfile(relative_path):
                    payload["image_path"] = relative_path
        
        cell = cls(**payload)
        cell.children = [Cell.from_dict(c, project_dir) for c in children_data]
        cell.pip_items = [PiPItem.from_dict(p) for p in pip_items_data]
        return cell

@dataclass
class RowTemplate:
    index: int = 0
    column_count: int = 1
    height_ratio: float = 1.0 # Relative height compared to other rows
    column_ratios: List[float] = field(default_factory=list) # Per-column width ratios (empty = equal)
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "index": self.index,
            "column_count": self.column_count,
            "height_ratio": self.height_ratio,
            "column_ratios": self.column_ratios,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'RowTemplate':
        return cls(
            index=data.get("index", 0),
            column_count=data.get("column_count", 1),
            height_ratio=data.get("height_ratio", 1.0),
            column_ratios=data.get("column_ratios", [])
        )

@dataclass
class ExportRegion:
    """User-defined export area on the page (mm, scene coordinates).

    When set, exporters clip the output to this rectangle instead of using the
    full page. None = use full page (default behaviour).
    """
    x_mm: float = 0.0
    y_mm: float = 0.0
    w_mm: float = 100.0
    h_mm: float = 100.0

    def to_dict(self) -> Dict[str, Any]:
        return {
            "x_mm": self.x_mm, "y_mm": self.y_mm,
            "w_mm": self.w_mm, "h_mm": self.h_mm,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ExportRegion':
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in allowed})


@dataclass
class Project:
    name: str = "Untitled Project"
    
    # Page Settings
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    margin_left_mm: float = 0.0
    margin_right_mm: float = 0.0
    margin_top_mm: float = 0.0
    margin_bottom_mm: float = 0.0
    gap_mm: float = 2.0  # Gap between cells
    
    dpi: int = 600
    
    # Layout Mode: "grid" uses rows/columns, "freeform" uses per-cell absolute positions
    layout_mode: str = "grid"
    
    # Grid Settings
    grid_mode: str = "stretch" # "stretch" or "fixed"
    row_alignment: str = "center" # "left", "center", "right"
    
    # Layout
    rows: List[RowTemplate] = field(default_factory=list)
    cells: List[Cell] = field(default_factory=list)

    # Size Groups (force shared W/H across member cells in grid mode)
    size_groups: List[SizeGroup] = field(default_factory=list)

    # SVG Text Groups (shared font-size overrides for SVG text elements)
    svg_text_groups: List[SvgTextGroup] = field(default_factory=list)

    # Text
    text_items: List[TextItem] = field(default_factory=list)
    
    # Global Label Settings (Numbering)
    label_scheme: str = "(a)" # (a), (A), a, A
    label_placement: str = "in_cell"
    label_font_family: str = "Arial"
    label_font_size: int = 12
    label_font_weight: str = "bold"
    label_color: str = "#000000" # black or white (#FFFFFF)
    label_anchor: str = LabelPosition.TOP_LEFT.value
    label_align: str = "center" # "left", "center", "right" — preset for label position in label cells
    label_offset_x: float = 0.0  # mm, horizontal offset for fine-tuning label position
    label_offset_y: float = 0.0  # mm, vertical offset for fine-tuning label position
    label_row_height: float = 0.0  # mm, 0 = auto (computed from font size)
    label_col_width: float = 10.0  # mm, width of label column for label_col_left/right placement

    # TIFF export colour model: "rgb" (default) or "cmyk" (print-ready).
    tiff_color_mode: str = "rgb"
    # Absolute path to a CMYK ICC profile (*.icc/*.icm). None = auto-detect a
    # system-installed profile, falling back to naive convert('CMYK') if none.
    cmyk_icc_profile_path: Optional[str] = None
    # ICC rendering intent for sRGB->CMYK conversion (PIL.ImageCms ints):
    # 0 Perceptual, 1 Relative Colorimetric (default), 2 Saturation, 3 Absolute.
    cmyk_rendering_intent: int = 1

    # Export Region (None = export full page). If set, exporters clip to this rect.
    export_region: Optional[ExportRegion] = None

    # Global Corner Label Settings
    corner_label_font_family: str = "Arial"
    corner_label_font_size: int = 12
    corner_label_font_weight: str = "bold"
    corner_label_color: str = "#000000"

    def get_all_leaf_cells(self) -> List[Cell]:
        result = []
        for cell in self.cells:
            result.extend(cell.get_all_leaves())
        return result

    def find_cell_by_id(self, cell_id: str) -> Optional[Cell]:
        def _search(cell):
            if cell.id == cell_id:
                return cell
            for child in cell.children:
                found = _search(child)
                if found:
                    return found
            return None
        for cell in self.cells:
            found = _search(cell)
            if found:
                return found
        return None

    def find_size_group(self, group_id: str) -> Optional[SizeGroup]:
        for g in self.size_groups:
            if g.id == group_id:
                return g
        return None

    def size_group_members(self, group_id: str) -> List[Cell]:
        return [c for c in self.get_all_leaf_cells() if c.size_group_id == group_id]

    def remove_size_group(self, group_id: str):
        """Delete a group and unassign all its members."""
        for c in self.get_all_leaf_cells():
            if c.size_group_id == group_id:
                c.size_group_id = None
        self.size_groups = [g for g in self.size_groups if g.id != group_id]

    def find_parent_of(self, cell_id: str) -> Optional[Cell]:
        def _search(parent, target_id):
            for child in parent.children:
                if child.id == target_id:
                    return parent
                found = _search(child, target_id)
                if found:
                    return found
            return None
        for cell in self.cells:
            if cell.id == cell_id:
                return None  # Top-level cell has no parent
            found = _search(cell, cell_id)
            if found:
                return found
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "file_version": APP_VERSION,
            "name": self.name,
            "page_width_mm": self.page_width_mm,
            "page_height_mm": self.page_height_mm,
            "margin_left_mm": self.margin_left_mm,
            "margin_right_mm": self.margin_right_mm,
            "margin_top_mm": self.margin_top_mm,
            "margin_bottom_mm": self.margin_bottom_mm,
            "gap_mm": self.gap_mm,
            "dpi": self.dpi,
            "layout_mode": self.layout_mode,
            "grid_mode": self.grid_mode,
            "row_alignment": self.row_alignment,
            "rows": [r.to_dict() for r in self.rows],
            "cells": [c.to_dict() for c in self.cells],
            "size_groups": [g.to_dict() for g in self.size_groups],
            "svg_text_groups": [g.to_dict() for g in self.svg_text_groups],
            "text_items": [t.to_dict() for t in self.text_items],
            "label_scheme": self.label_scheme,
            "label_placement": self.label_placement,
            "label_font_family": self.label_font_family,
            "label_font_size": self.label_font_size,
            "label_font_weight": self.label_font_weight,
            "label_color": self.label_color,
            "label_anchor": self.label_anchor,
            "label_align": self.label_align,
            "label_offset_x": self.label_offset_x,
            "label_offset_y": self.label_offset_y,
            "label_row_height": self.label_row_height,
            "label_col_width": self.label_col_width,
            "tiff_color_mode": self.tiff_color_mode,
            "cmyk_icc_profile_path": self.cmyk_icc_profile_path,
            "cmyk_rendering_intent": self.cmyk_rendering_intent,
            "corner_label_font_family": self.corner_label_font_family,
            "corner_label_font_size": self.corner_label_font_size,
            "corner_label_font_weight": self.corner_label_font_weight,
            "corner_label_color": self.corner_label_color,
            "export_region": self.export_region.to_dict() if self.export_region else None,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], project_dir: Optional[str] = None) -> 'Project':
        p = cls()
        p.name = data.get("name", "Untitled Project")
        p.page_width_mm = data.get("page_width_mm", 210.0)
        p.page_height_mm = data.get("page_height_mm", 297.0)
        p.margin_left_mm = data.get("margin_left_mm", 10.0)
        p.margin_right_mm = data.get("margin_right_mm", 10.0)
        p.margin_top_mm = data.get("margin_top_mm", 10.0)
        p.margin_bottom_mm = data.get("margin_bottom_mm", 10.0)
        p.gap_mm = data.get("gap_mm", 2.0)
        p.dpi = data.get("dpi", 600)
        
        p.layout_mode = data.get("layout_mode", "grid")
        p.grid_mode = data.get("grid_mode", "stretch")
        p.row_alignment = data.get("row_alignment", "center")
        
        p.rows = [RowTemplate.from_dict(r) for r in data.get("rows", [])]
        p.cells = [Cell.from_dict(c, project_dir) for c in data.get("cells", [])]
        p.size_groups = [SizeGroup.from_dict(g) for g in data.get("size_groups", [])]
        p.svg_text_groups = [SvgTextGroup.from_dict(g) for g in data.get("svg_text_groups", [])]
        p.text_items = [TextItem.from_dict(t) for t in data.get("text_items", [])]

        # Prune orphan group references (group deleted but cell still refers to it)
        valid_group_ids = {g.id for g in p.size_groups}
        for c in p.get_all_leaf_cells():
            if c.size_group_id and c.size_group_id not in valid_group_ids:
                c.size_group_id = None
        
        p.label_scheme = data.get("label_scheme", "(a)")
        p.label_placement = data.get("label_placement", "in_cell")
        p.label_font_family = data.get("label_font_family", "Arial")
        p.label_font_size = data.get("label_font_size", 12)
        p.label_font_weight = data.get("label_font_weight", "bold")
        p.label_color = data.get("label_color", "#000000")
        p.label_anchor = data.get("label_anchor", LabelPosition.TOP_LEFT.value)
        p.label_align = data.get("label_align", "center")
        p.label_offset_x = data.get("label_offset_x", 0.0)
        p.label_offset_y = data.get("label_offset_y", 0.0)
        p.label_row_height = data.get("label_row_height", 0.0)
        p.label_col_width = data.get("label_col_width", 10.0)
        p.tiff_color_mode = data.get("tiff_color_mode", "rgb")
        p.cmyk_icc_profile_path = data.get("cmyk_icc_profile_path", None)
        p.cmyk_rendering_intent = int(data.get("cmyk_rendering_intent", 1))
        
        er = data.get("export_region")
        p.export_region = ExportRegion.from_dict(er) if er else None

        p.corner_label_font_family = data.get("corner_label_font_family", "Arial")
        p.corner_label_font_size = data.get("corner_label_font_size", 12)
        p.corner_label_font_weight = data.get("corner_label_font_weight", "bold")
        p.corner_label_color = data.get("corner_label_color", "#000000")

        default_label_anchor = p.label_anchor or LabelPosition.TOP_LEFT.value
        if not default_label_anchor.endswith("_inside"):
            default_label_anchor = f"{default_label_anchor}_inside"
        for t in p.text_items:
            if t.scope == "cell" and t.parent_id and not t.anchor:
                t.anchor = default_label_anchor

        return p

    def save_to_file(self, filepath: str):
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(self.to_dict(), f, indent=4)

    @classmethod
    def load_from_file(cls, filepath: str) -> 'Project':
        from src.model.migrations import migrate_project_data
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        data = migrate_project_data(data)
        # Always derive the project name from the filename
        data["name"] = os.path.splitext(os.path.basename(filepath))[0]
        project_dir = os.path.dirname(os.path.abspath(filepath))
        return cls.from_dict(data, project_dir)
