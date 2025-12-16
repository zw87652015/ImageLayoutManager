import json
import uuid
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any
from .enums import FitMode, LabelPosition, PageSizePreset

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
    align_h: str = "center"  # left, center, right
    align_v: str = "center"  # top, center, bottom
    padding_top: float = 2.0
    padding_bottom: float = 2.0
    padding_left: float = 2.0
    padding_right: float = 2.0
    
    # If it is a placeholder
    is_placeholder: bool = False
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "row_index": self.row_index,
            "col_index": self.col_index,
            "image_path": self.image_path,
            "fit_mode": self.fit_mode,
            "align_h": self.align_h,
            "align_v": self.align_v,
            "padding_top": self.padding_top,
            "padding_bottom": self.padding_bottom,
            "padding_left": self.padding_left,
            "padding_right": self.padding_right,
            "is_placeholder": self.is_placeholder,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Cell':
        return cls(**data)

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
    label_font_family: str = "Arial"
    label_font_size: int = 12
    label_font_weight: str = "bold"
    label_color: str = "#000000" # black or white (#FFFFFF)
    label_anchor: str = LabelPosition.TOP_LEFT.value
    label_attach_to: str = "figure" # "grid" (cell boundary) or "figure" (image content area)

    # Global Corner Label Settings
    corner_label_font_family: str = "Arial"
    corner_label_font_size: int = 12
    corner_label_font_weight: str = "bold"
    corner_label_color: str = "#000000"

    def to_dict(self) -> Dict[str, Any]:
        return {
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
            "label_font_family": self.label_font_family,
            "label_font_size": self.label_font_size,
            "label_font_weight": self.label_font_weight,
            "label_color": self.label_color,
            "label_anchor": self.label_anchor,
            "label_attach_to": self.label_attach_to,
            "corner_label_font_family": self.corner_label_font_family,
            "corner_label_font_size": self.corner_label_font_size,
            "corner_label_font_weight": self.corner_label_font_weight,
            "corner_label_color": self.corner_label_color,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Project':
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
        p.cells = [Cell.from_dict(c) for c in data.get("cells", [])]
        p.text_items = [TextItem.from_dict(t) for t in data.get("text_items", [])]
        
        p.label_scheme = data.get("label_scheme", "(a)")
        p.label_font_family = data.get("label_font_family", "Arial")
        p.label_font_size = data.get("label_font_size", 12)
        p.label_font_weight = data.get("label_font_weight", "bold")
        p.label_color = data.get("label_color", "#000000")
        p.label_anchor = data.get("label_anchor", LabelPosition.TOP_LEFT.value)
        p.label_attach_to = data.get("label_attach_to", "figure")
        
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
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return cls.from_dict(data)
