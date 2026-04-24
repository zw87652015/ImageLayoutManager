from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsItem, QStyleOptionGraphicsItem
from PyQt6.QtGui import QFont, QColor, QPainter, QPixmap
from PyQt6.QtCore import Qt, QRectF, pyqtSignal

class TextGraphicsItem(QGraphicsTextItem):
    # Signal to notify model update when text changes or moves
    item_changed = pyqtSignal(str, object) # text_item_id, changes_dict

    def __init__(self, text_item_id: str, text: str, parent=None):
        super().__init__(text, parent)
        self.text_item_id = text_item_id

        # Flags
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)

        # Interaction
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        # We handle double click to edit, so initially just movable

        self.setAcceptHoverEvents(True)

        # Default Style
        self.setDefaultTextColor(QColor("black"))

        # State
        self.is_editing = False

        # Cell-scoped label info (set by canvas_scene for constrained movement)
        self.cell_bounds = None  # (cx, cy, cw, ch) - content area bounds
        self.anchor = None  # e.g., "top_left_inside"
        self.scope = "global"  # "global" or "cell"

        # Math rendering cache (populated by _update_math_cache)
        self._math_pixmap: QPixmap | None = None
        self._math_rect: QRectF | None = None
        self._font_family = ""
        self._font_size_pt = 12.0
        self._font_weight = "normal"
        self._color_hex = "#000000"

        # Background box behind the text (label aesthetic).
        self._bg_enabled = False
        self._bg_color = "#FFFFFF"
        self._bg_padding_mm = 0.6

    def update_style(self, font_family, font_size_pt, font_weight, color_hex):
        self._font_family = font_family
        self._font_size_pt = font_size_pt
        self._font_weight = font_weight
        self._color_hex = color_hex

        # Use a base font size of 24pt for quality, then scale to desired size
        # This avoids extreme scaling (1/72) which causes pixelation
        # Scale factor = desired_size / base_size = font_size_pt / 24
        base_pt = 24
        font = QFont(font_family, base_pt)
        if font_weight == "bold":
            font.setBold(True)
        self.setFont(font)
        self.setDefaultTextColor(QColor(color_hex))

        # Linear scaling: 1pt -> 1/24 scale, 24pt -> 1.0 scale, 72pt -> 3.0 scale
        scale = font_size_pt / base_pt
        self.setScale(scale)

        # Try to build a math-rendered pixmap; if successful, scale becomes 1.0
        self._update_math_cache()

    def _update_math_cache(self):
        """Re-render math to pixmap if the current text contains $...$ expressions."""
        from src.utils.math_text import has_math, render_math_to_qimage, strip_html, MATH_RENDER_DPI
        plain = strip_html(self.toHtml()) or self.toPlainText()
        if not has_math(plain):
            self._math_pixmap = None
            self._math_rect = None
            return

        result = render_math_to_qimage(
            plain,
            self._font_size_pt,
            self._font_family,
            self._font_weight,
            self._color_hex,
            dpi=MATH_RENDER_DPI,
        )
        if result is None:
            self._math_pixmap = None
            self._math_rect = None
            return

        img, w_mm, h_mm = result
        self._math_pixmap = QPixmap.fromImage(img)
        self._math_rect = QRectF(0.0, 0.0, w_mm, h_mm)
        # Math items render at natural scene size; no font scale needed
        self.setScale(1.0)

    def set_background(self, enabled: bool, color_hex: str, padding_mm: float):
        self._bg_enabled = bool(enabled)
        self._bg_color = color_hex or "#FFFFFF"
        self._bg_padding_mm = max(0.0, float(padding_mm))
        self.update()

    def boundingRect(self) -> QRectF:
        if self._math_rect is not None:
            rect = QRectF(self._math_rect)
        else:
            rect = super().boundingRect()
        if self._bg_enabled and self._bg_padding_mm > 0:
            # Bounding rect is in item coords; scale applies to the whole item.
            s = self.scale() or 1.0
            pad = self._bg_padding_mm / s
            rect = rect.adjusted(-pad, -pad, pad, pad)
        return rect

    def mouseDoubleClickEvent(self, event):
        if self.textInteractionFlags() == Qt.TextInteractionFlag.NoTextInteraction:
            self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
            self.setFocus()
            self.is_editing = True
        super().mouseDoubleClickEvent(event)

    def focusOutEvent(self, event):
        self.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        if self.is_editing:
            self.is_editing = False
            # Emit change
            # We emit HTML to support rich text
            self.item_changed.emit(self.text_item_id, {"text": self.toHtml()})
            # Also clear selection to look cleaner
            self.setSelected(False)
        super().focusOutEvent(event)

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            # We might want to limit this frequency or handle it in the Scene/Controller
            # For now, just let it move. Actual model update usually happens on mouse release.
            pass
        return super().itemChange(change, value)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if self.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsMovable:
            if self.scope == "cell" and self.cell_bounds and self.anchor:
                # For cell-scoped labels, calculate offset from anchor position
                cx, cy, cw, ch = self.cell_bounds
                pos = self.pos()
                scale = self.scale()
                text_width = self.boundingRect().width() * scale
                text_height = self.boundingRect().height() * scale
                
                # Calculate offset based on anchor
                if "left" in self.anchor:
                    offset_x = pos.x() - cx
                elif "right" in self.anchor:
                    offset_x = cx + cw - pos.x() - text_width
                else:
                    offset_x = 0
                
                if "top" in self.anchor:
                    offset_y = pos.y() - cy
                elif "bottom" in self.anchor:
                    offset_y = cy + ch - pos.y() - text_height
                else:
                    offset_y = 0
                
                # Clamp offsets to keep label inside cell
                offset_x = max(0, offset_x)
                offset_y = max(0, offset_y)
                
                self.item_changed.emit(self.text_item_id, {
                    "offset_x": offset_x,
                    "offset_y": offset_y
                })
            else:
                # Global text: use absolute x,y
                self.item_changed.emit(self.text_item_id, {
                    "x": self.pos().x(),
                    "y": self.pos().y()
                })

    def paint(self, painter, option, widget):
        if self._bg_enabled:
            painter.save()
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(self._bg_color))
            painter.drawRect(self.boundingRect())
            painter.restore()
        if self._math_pixmap is not None and not self._math_pixmap.isNull():
            painter.drawPixmap(self._math_rect.toRect(), self._math_pixmap)
            return
        super().paint(painter, option, widget)
