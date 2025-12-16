from PyQt6.QtWidgets import QGraphicsTextItem, QGraphicsItem, QStyleOptionGraphicsItem
from PyQt6.QtGui import QFont, QColor, QPainter
from PyQt6.QtCore import Qt, pyqtSignal

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

    def update_style(self, font_family, font_size_pt, font_weight, color_hex):
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
        # Remove the dashed line box when focused/selected if desired, 
        # or customize selection look.
        # For now, keeping default Qt behavior but can remove the option.state check if needed.
        
        # If we want to hide the dashed border on selection (optional):
        # option.state &= ~QStyle.State_Selected
        super().paint(painter, option, widget)
