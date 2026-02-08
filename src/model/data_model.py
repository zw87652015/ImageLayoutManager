import json
import os
import uuid
from dataclasses import dataclass, field
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
    
    # For global text or manual positioning
    x: float = 0.0
    y: float = 0.0
    
    # For anchored text (e.g. labels)
    anchor: Optional[str] = None # top_left, etc.
    offset_x: float = 0.0
    offset_y: float = 0.0

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
            "anchor": self.anchor,
            "offset_x": self.offset_x,
            "offset_y": self.offset_y,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TextItem':
        return cls(**data)

@dataclass
class Cell:
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    row_index: int = 0
    col_index: int = 0
    
    # Content
    image_path: Optional[str] = None
    
    # Layout/Style
    fit_mode: str = FitMode.CONTAIN.value
    rotation: int = 0  # 0, 90, 180, 270 degrees
    align_h: str = "center"  # left, center, right
    align_v: str = "center"  # top, center, bottom
    padding_top: float = 2.0
    padding_bottom: float = 2.0
    padding_left: float = 2.0
    padding_right: float = 2.0
    
    # If it is a placeholder
    is_placeholder: bool = False

    # Nested layout (sub-figure from another .figlayout file)
    nested_layout_path: Optional[str] = None  # absolute path to .figlayout file

    # Scale bar (microscopy)
    scale_bar_enabled: bool = False
    scale_bar_mode: str = "rgb"  # "rgb" | "bayer"
    scale_bar_length_um: float = 10.0
    scale_bar_color: str = "#FFFFFF"  # white or black
    scale_bar_show_text: bool = True
    scale_bar_thickness_mm: float = 0.5
    scale_bar_position: str = "bottom_right"  # bottom_left | bottom_center | bottom_right
    scale_bar_offset_x: float = 2.0
    scale_bar_offset_y: float = 2.0
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "image_path": self.image_path,
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
            "scale_bar_length_um": self.scale_bar_length_um,
            "scale_bar_color": self.scale_bar_color,
            "scale_bar_show_text": self.scale_bar_show_text,
            "scale_bar_thickness_mm": self.scale_bar_thickness_mm,
            "scale_bar_position": self.scale_bar_position,
            "scale_bar_offset_x": self.scale_bar_offset_x,
            "scale_bar_offset_y": self.scale_bar_offset_y,
            "nested_layout_path": self.nested_layout_path,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any], project_dir: Optional[str] = None) -> 'Cell':
        # Backward compatibility: older projects may not have scale bar fields
        payload = dict(data)
        payload.setdefault("rotation", 0)
        payload.setdefault("scale_bar_enabled", False)
        payload.setdefault("scale_bar_mode", "rgb")
        payload.setdefault("scale_bar_length_um", 10.0)
        payload.setdefault("scale_bar_color", "#FFFFFF")
        payload.setdefault("scale_bar_show_text", True)
        payload.setdefault("scale_bar_thickness_mm", 0.5)
        payload.setdefault("scale_bar_position", "bottom_right")
        payload.setdefault("scale_bar_offset_x", 2.0)
        payload.setdefault("scale_bar_offset_y", 2.0)
        payload.setdefault("nested_layout_path", None)
        
        # Resolve image path: try absolute first, then relative to project file
        if payload.get("image_path") and project_dir:
            abs_path = payload["image_path"]
            # If absolute path doesn't exist, try relative to project directory
            if not os.path.isfile(abs_path):
                filename = os.path.basename(abs_path)
                relative_path = os.path.join(project_dir, filename)
                if os.path.isfile(relative_path):
                    payload["image_path"] = relative_path
        
        return cls(**payload)

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
class Project:
    name: str = "Untitled Project"
    
    # Page Settings
    page_width_mm: float = 210.0
    page_height_mm: float = 297.0
    margin_left_mm: float = 10.0
    margin_right_mm: float = 10.0
    margin_top_mm: float = 10.0
    margin_bottom_mm: float = 10.0
    gap_mm: float = 2.0  # Gap between cells
    
    dpi: int = 600
    
    # Layout
    rows: List[RowTemplate] = field(default_factory=list)
    cells: List[Cell] = field(default_factory=list)
    
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
    label_attach_to: str = "figure" # "grid" (cell boundary) or "figure" (image content area)
    label_align: str = "center" # "left", "center", "right" — preset for label position in label cells
    label_offset_x: float = 0.0  # mm, horizontal offset for fine-tuning label position
    label_offset_y: float = 0.0  # mm, vertical offset for fine-tuning label position
    label_row_height: float = 0.0  # mm, 0 = auto (computed from font size)

    # Global Corner Label Settings
    corner_label_font_family: str = "Arial"
    corner_label_font_size: int = 12
    corner_label_font_weight: str = "bold"
    corner_label_color: str = "#000000"

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
            "rows": [r.to_dict() for r in self.rows],
            "cells": [c.to_dict() for c in self.cells],
            "text_items": [t.to_dict() for t in self.text_items],
            "label_scheme": self.label_scheme,
            "label_placement": self.label_placement,
            "label_font_family": self.label_font_family,
            "label_font_size": self.label_font_size,
            "label_font_weight": self.label_font_weight,
            "label_color": self.label_color,
            "label_anchor": self.label_anchor,
            "label_attach_to": self.label_attach_to,
            "label_align": self.label_align,
            "label_offset_x": self.label_offset_x,
            "label_offset_y": self.label_offset_y,
            "label_row_height": self.label_row_height,
            "corner_label_font_family": self.corner_label_font_family,
            "corner_label_font_size": self.corner_label_font_size,
            "corner_label_font_weight": self.corner_label_font_weight,
            "corner_label_color": self.corner_label_color,
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
        
        p.rows = [RowTemplate.from_dict(r) for r in data.get("rows", [])]
        p.cells = [Cell.from_dict(c, project_dir) for c in data.get("cells", [])]
        p.text_items = [TextItem.from_dict(t) for t in data.get("text_items", [])]
        
        p.label_scheme = data.get("label_scheme", "(a)")
        p.label_placement = data.get("label_placement", "in_cell")
        p.label_font_family = data.get("label_font_family", "Arial")
        p.label_font_size = data.get("label_font_size", 12)
        p.label_font_weight = data.get("label_font_weight", "bold")
        p.label_color = data.get("label_color", "#000000")
        p.label_anchor = data.get("label_anchor", LabelPosition.TOP_LEFT.value)
        p.label_attach_to = data.get("label_attach_to", "figure")
        p.label_align = data.get("label_align", "center")
        p.label_offset_x = data.get("label_offset_x", 0.0)
        p.label_offset_y = data.get("label_offset_y", 0.0)
        p.label_row_height = data.get("label_row_height", 0.0)
        
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
