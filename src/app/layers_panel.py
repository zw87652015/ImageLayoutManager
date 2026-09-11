import os

from src.app.i18n import tr
from src.app.theme import get_layers_tree_stylesheet, get_tokens, LIGHT
from src.utils.image_proxy import image_format_name

from PyQt6.QtCore import Qt, QSize, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPen, QPainter, QPainterPath, QBrush, QFont, QFontMetrics, QPixmap,
    QPalette,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator, QStyledItemDelegate, QStyleOptionViewItem,
    QApplication, QStyle, QAbstractItemView,
)

# ── Data roles stored on every QTreeWidgetItem ──────────────────────────────
_ROLE_ID   = Qt.ItemDataRole.UserRole          # cell/text id
_ROLE_TYPE = Qt.ItemDataRole.UserRole + 1      # "row"|"split"|"text_group"|"cell_filled"|"cell_empty"|"text_leaf"|"pip_item"
_ROLE_IMG  = Qt.ItemDataRole.UserRole + 2      # image path (cell_filled/pip_item only)
_ROLE_META = Qt.ItemDataRole.UserRole + 3      # right-side meta string (e.g. "2 cells")
_ROLE_ZIDX = Qt.ItemDataRole.UserRole + 4      # cell.z_index, only set when non-default (cell_filled/cell_empty)

# Item types that participate in drag-to-reorder, and which "kind" of
# z-stack they reorder within (see _BranchlessTree._compatible_target).
_DRAG_KINDS = {"cell_filled": "cell", "cell_empty": "cell", "pip_item": "pip"}


class _BranchlessTree(QTreeWidget):
    """QTreeWidget with branch lines/decorators suppressed, plus restricted
    drag-and-drop for reordering the Z-stack.

    This is deliberately *not* Qt's generic internal-move reparenting: rows
    stay in their existing row/column grouping (that grouping is a stable
    structural identity, unrelated to draw order — see AGENTS.md), and a
    drag never moves an item to a new parent. It only ever emits
    ``reorder_requested`` so the caller can push an undoable command that
    changes ``z_index`` (cells) or list order (PiP insets); the tree is
    then rebuilt by the normal ``refresh()`` path.
    """
    reorder_requested = pyqtSignal(str, str, bool)  # dragged_id, target_id, place_above

    def drawBranches(self, painter, rect, index):
        pass  # prevent Qt native style from drawing connecting lines

    @staticmethod
    def _drag_kind(item):
        if item is None:
            return None
        return _DRAG_KINDS.get(item.data(0, _ROLE_TYPE))

    def _compatible_target(self, dragged, target):
        if dragged is None or target is None or dragged is target:
            return False
        kind = self._drag_kind(dragged)
        if kind is None or kind != self._drag_kind(target):
            return False
        # PiP insets only make sense stacked against insets of the *same*
        # cell; leaf cells reorder against any other leaf cell in the project.
        return kind == "cell" or dragged.parent() is target.parent()

    def dragMoveEvent(self, event):
        target = self.itemAt(event.position().toPoint())
        if self._compatible_target(self.currentItem(), target):
            super().dragMoveEvent(event)
        else:
            event.ignore()

    def dropEvent(self, event):
        dragged = self.currentItem()
        target = self.itemAt(event.position().toPoint())
        if not self._compatible_target(dragged, target):
            event.ignore()
            return
        pos = self.dropIndicatorPosition()
        place_above = pos != QAbstractItemView.DropIndicatorPosition.BelowItem
        dragged_id = dragged.data(0, _ROLE_ID)
        target_id = target.data(0, _ROLE_ID)
        # Never let Qt perform its own reparenting move — we only reorder
        # z-stack data and rely on refresh() to redraw the (unchanged) tree.
        event.setDropAction(Qt.DropAction.IgnoreAction)
        event.accept()
        if dragged_id and target_id:
            self.reorder_requested.emit(dragged_id, target_id, place_above)

    def mouseMoveEvent(self, event):
        # Open-hand cursor hints that a row can be picked up and dropped
        # onto another one to reorder the z-stack.
        item = self.itemAt(event.position().toPoint())
        if self._drag_kind(item) is not None:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        else:
            self.viewport().unsetCursor()
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        self.viewport().unsetCursor()
        super().leaveEvent(event)


class LayersDelegate(QStyledItemDelegate):
    """Custom item delegate: thumbnail + text + accent selection + left bar."""

    THUMB   = 20   # thumbnail square size (logical px)
    PAD     = 4    # horizontal padding
    BAR_W   = 2    # width of the accent left-edge bar when selected
    ITEM_H  = 30   # row height for cell items
    GROUP_H = 24   # row height for group header items

    def __init__(self, tree: _BranchlessTree, parent=None):
        super().__init__(parent)
        self._tree = tree
        self._tokens: dict = {}
        self._cache: dict[str, QPixmap] = {}

    def apply_tokens(self, tokens: dict) -> None:
        self._tokens = tokens
        self._cache.clear()

    # ── sizing ───────────────────────────────────────────────────────────────

    def sizeHint(self, option, index) -> QSize:
        itype = index.data(_ROLE_TYPE) or ""
        h = self.GROUP_H if itype in ("row", "text_group", "split") else self.ITEM_H
        return QSize(option.rect.width(), h)

    # ── painting ─────────────────────────────────────────────────────────────

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        t = self._tokens
        accent     = QColor(t.get("accent",    "#0891B2"))
        text_c     = QColor(t.get("text",      "#1C1C1E"))
        text_sec   = QColor(t.get("text_sec",  "#6E6E73"))
        ph_c       = QColor(t.get("placeholder","#AEAEB2"))

        r: QRect = option.rect
        is_sel   = bool(option.state & QStyle.StateFlag.State_Selected)
        is_hover = bool(option.state & QStyle.StateFlag.State_MouseOver)
        itype    = index.data(_ROLE_TYPE) or "cell_empty"
        is_group = itype in ("row", "text_group", "split")

        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        # ── background ───────────────────────────────────────────────────────
        if is_sel:
            bg = QColor(accent); bg.setAlpha(28)
            painter.fillRect(r, bg)
            inset = 4
            painter.fillRect(QRect(r.left(), r.top() + inset, self.BAR_W, r.height() - 2 * inset), accent)
        elif is_hover:
            painter.fillRect(r, QColor(0, 0, 0, 10))

        # ── group header ─────────────────────────────────────────────────────
        if is_group:
            if not is_sel:
                painter.fillRect(r, QColor(0, 0, 0, 6))
            col = accent if is_sel else text_sec
            # left-side chevron (matches mockup .row-header .chevron position)
            self._draw_chevron(painter, r, index, col)
            CHEV_W = 16
            label = index.data() or ""
            meta  = index.data(_ROLE_META) or ""
            fnt = QFont(painter.font())
            fnt.setPointSizeF(max(7.0, fnt.pointSizeF() * 0.85))
            fnt.setWeight(QFont.Weight.DemiBold)
            painter.setFont(fnt)
            fm = QFontMetrics(fnt)
            painter.setPen(col)
            meta_reserved = 0
            if meta:
                meta_w = fm.horizontalAdvance(meta) + self.PAD
                meta_reserved = meta_w + 4
                meta_col = QColor(accent if is_sel else text_sec)
                meta_col.setAlpha(160)
                painter.setPen(meta_col)
                painter.drawText(
                    QRect(r.right() - meta_reserved, r.top(), meta_w, r.height()),
                    Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight, meta
                )
                painter.setPen(col)
            text_r = QRect(r.left() + CHEV_W, r.top(), r.width() - CHEV_W - meta_reserved - 4, r.height())
            painter.drawText(text_r, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, label)
            painter.restore()
            return

        # ── cell / text-leaf item ─────────────────────────────────────────────
        tx = r.left() + self.BAR_W + self.PAD
        ty = r.top() + (r.height() - self.THUMB) // 2
        thumb_r = QRect(tx, ty, self.THUMB, self.THUMB)

        image_path = index.data(_ROLE_IMG) if itype in ("cell_filled", "pip_item") else None
        if image_path:
            pm = self._thumbnail(image_path)
            if pm and not pm.isNull():
                painter.drawPixmap(thumb_r, pm)
            else:
                self._draw_empty_thumb(painter, thumb_r, ph_c)
        else:
            self._draw_empty_thumb(painter, thumb_r, ph_c)

        # format badge — right-aligned chip naming the source file type, so a
        # mixed-format figure is readable without opening each panel.
        badge = index.data(_ROLE_META) or ""
        badge_reserved = 0
        if badge and itype in ("cell_filled", "pip_item"):
            badge_font = QFont(painter.font())
            badge_font.setPointSizeF(max(6.5, badge_font.pointSizeF() * 0.78))
            badge_font.setWeight(QFont.Weight.DemiBold)
            badge_fm = QFontMetrics(badge_font)
            badge_w = badge_fm.horizontalAdvance(badge) + 10
            badge_h = badge_fm.height() + 2
            badge_r = QRect(r.right() - badge_w - 6, r.top() + (r.height() - badge_h) // 2, badge_w, badge_h)
            badge_col = QColor(accent if is_sel else text_sec)
            fill = QColor(badge_col)
            fill.setAlpha(26)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(badge_r, 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            badge_col.setAlpha(210)
            painter.setPen(badge_col)
            painter.setFont(badge_font)
            painter.drawText(badge_r, Qt.AlignmentFlag.AlignCenter, badge)
            badge_reserved = badge_w + 10

        # stacking-order chip — a cell's position in *this* list reflects
        # row/column, not z-order (see AGENTS.md), so dragging a row to
        # reorder its z-stack needs its own feedback. Shown only once the
        # cell has actually been moved out of the default stacking order
        # (drag or Bring to Front/Send to Back), so plain non-overlapping
        # grids stay uncluttered.
        z_val = index.data(_ROLE_ZIDX)
        z_reserved = 0
        if z_val is not None and itype in ("cell_filled", "cell_empty"):
            z_text = f"Z{z_val:+d}"
            z_font = QFont(painter.font())
            z_font.setPointSizeF(max(6.5, z_font.pointSizeF() * 0.78))
            z_font.setWeight(QFont.Weight.DemiBold)
            z_fm = QFontMetrics(z_font)
            z_w = z_fm.horizontalAdvance(z_text) + 10
            z_h = z_fm.height() + 2
            z_r = QRect(r.right() - badge_reserved - z_w - 6,
                        r.top() + (r.height() - z_h) // 2, z_w, z_h)
            z_col = QColor(accent if is_sel else text_sec)
            fill = QColor(z_col)
            fill.setAlpha(26)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(fill)
            painter.drawRoundedRect(z_r, 3, 3)
            painter.setBrush(Qt.BrushStyle.NoBrush)
            z_col.setAlpha(210)
            painter.setPen(z_col)
            painter.setFont(z_font)
            painter.drawText(z_r, Qt.AlignmentFlag.AlignCenter, z_text)
            z_reserved = z_w + 10

        # text
        text_x  = tx + self.THUMB + self.PAD
        text_rect = QRect(text_x, r.top(), r.right() - text_x - 4 - badge_reserved - z_reserved, r.height())
        col = accent if is_sel else (text_c if itype in ("cell_filled", "pip_item", "text_leaf") else text_sec)
        painter.setPen(col)
        fnt = QFont(painter.font())
        fnt.setPointSizeF(max(8.0, fnt.pointSizeF() * 0.92))
        painter.setFont(fnt)
        fm = QFontMetrics(fnt)
        elided = fm.elidedText(index.data() or "", Qt.TextElideMode.ElideRight, text_rect.width())
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft, elided)

        painter.restore()

    # ── helpers ───────────────────────────────────────────────────────────────

    def _draw_chevron(self, painter: QPainter, rect: QRect, index, color: QColor) -> None:
        item = self._tree.itemFromIndex(index)
        expanded = item.isExpanded() if item else True
        cx = rect.left() + 8   # left-side, matching mockup .row-header .chevron
        cy = rect.center().y()
        s  = 4
        path = QPainterPath()
        if expanded:
            path.moveTo(cx - s, cy - 2); path.lineTo(cx, cy + s - 2); path.lineTo(cx + s, cy - 2)
        else:
            path.moveTo(cx - 2, cy - s); path.lineTo(cx + s - 2, cy); path.lineTo(cx - 2, cy + s)
        pen = QPen(color, 1.5, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(path)

    def _draw_empty_thumb(self, painter: QPainter, rect: QRect, color: QColor) -> None:
        pen = QPen(color, 1, Qt.PenStyle.DashLine)
        pen.setDashPattern([3.0, 3.0])
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(rect.adjusted(1, 1, -1, -1))

    def _thumbnail(self, path: str) -> QPixmap:
        if path not in self._cache:
            pm = QPixmap()
            if os.path.exists(path):
                raw = QPixmap(path)
                if not raw.isNull():
                    side = self.THUMB * 2
                    scaled = raw.scaled(side, side,
                                        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                                        Qt.TransformationMode.SmoothTransformation)
                    # centre-crop to side×side
                    ox = (scaled.width()  - side) // 2
                    oy = (scaled.height() - side) // 2
                    cropped = scaled.copy(ox, oy, side, side)
                    cropped.setDevicePixelRatio(2.0)
                    pm = cropped
            self._cache[path] = pm
        return self._cache[path]


# ── Layers Panel ──────────────────────────────────────────────────────────────

class LayersPanel(QWidget):
    items_selected        = pyqtSignal(list)         # [cell_id, …]
    context_menu_requested = pyqtSignal(list, object) # ([cell_ids], QPoint)
    reorder_requested       = pyqtSignal(str, str, bool)  # dragged_id, target_id, place_above

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumWidth(200)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        # Header
        self.header_label = QLabel(tr("layers_header"))
        self.header_label.setStyleSheet(
            "font-weight: 600; font-size: 11px; letter-spacing: 1px;"
            " padding: 0 2px; color: #888888;"
        )
        layout.addWidget(self.header_label)

        # Tree
        self.tree = _BranchlessTree()
        self.tree.setHeaderHidden(True)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.ExtendedSelection)
        self.tree.setIndentation(14)
        self.tree.setRootIsDecorated(False)   # delegate draws the chevrons
        self.tree.setUniformRowHeights(False)
        self.tree.viewport().setMouseTracking(True)
        self.tree.setMouseTracking(True)

        # Drag-and-drop reordering of the Z-stack (panels) / PiP insets —
        # an alternative to Bring to Front / Send to Back for the common
        # "grab this and put it where I want" case. See _BranchlessTree.
        self.tree.setDragEnabled(True)
        self.tree.setAcceptDrops(True)
        self.tree.setDropIndicatorShown(True)
        self.tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tree.reorder_requested.connect(self.reorder_requested.emit)

        # Custom delegate
        self._delegate = LayersDelegate(self.tree, self.tree)
        self.tree.setItemDelegate(self._delegate)

        # Make Qt's built-in selection highlight fully transparent so the
        # delegate's accent bar is the only selection visual.
        pal = self.tree.palette()
        pal.setColor(QPalette.ColorRole.Highlight, QColor(0, 0, 0, 0))
        pal.setColor(QPalette.ColorRole.HighlightedText,
                     pal.color(QPalette.ColorRole.Text))
        self.tree.setPalette(pal)

        # Apply initial theme (visual only — public API sets the real theme)
        self._apply_tree_stylesheet(LIGHT)
        self._delegate.apply_tokens(get_tokens(LIGHT))

        self.tree.itemSelectionChanged.connect(self._on_selection_changed)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.customContextMenuRequested.connect(self._on_context_menu)
        layout.addWidget(self.tree)

        self._project = None
        self._is_updating = False

    # ── theme ────────────────────────────────────────────────────────────────

    def apply_theme(self, tokens: dict) -> None:
        """Update all visuals from design tokens. Called by main_window on theme switch."""
        self._delegate.apply_tokens(tokens)
        theme = "dark" if tokens.get("canvas_bg", "").startswith("#1") else "light"
        self._apply_tree_stylesheet(theme)
        self.tree.update()

    def _apply_tree_stylesheet(self, theme: str) -> None:
        """Apply the base QSS (delegate handles selection/hover, QSS does layout)."""
        self.tree.setStyleSheet(get_layers_tree_stylesheet(theme))

    # ── project / refresh ─────────────────────────────────────────────────────

    def set_project(self, project):
        self._project = project
        self.refresh()

    def refresh(self):
        if not self._project:
            return

        self._is_updating = True
        self.tree.clear()

        for r in sorted(self._project.rows, key=lambda r: r.index):
            cells_in_row = sorted(
                [c for c in self._project.cells if c.row_index == r.index],
                key=lambda c: c.col_index
            )
            row_item = QTreeWidgetItem(self.tree, [f"{tr('layers_row')} {r.index + 1}"])
            row_item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            row_item.setData(0, _ROLE_TYPE, "row")
            n = len(cells_in_row)
            row_item.setData(0, _ROLE_META, f"{n} {'cell' if n == 1 else 'cells'}")

            for c in cells_in_row:
                self._add_cell_tree_item(row_item, c, col_label=f"C{c.col_index + 1}")

            row_item.setExpanded(True)

        global_texts = [t for t in self._project.text_items if t.scope == "global"]
        if global_texts:
            text_root = QTreeWidgetItem(self.tree, [tr("layers_text_items")])
            text_root.setFlags(Qt.ItemFlag.ItemIsEnabled)
            text_root.setData(0, _ROLE_TYPE, "text_group")
            for t in global_texts:
                preview = (t.text[:18] + "…") if len(t.text) > 18 else t.text
                t_item = QTreeWidgetItem(text_root, [f'"{preview}"'])
                t_item.setData(0, _ROLE_ID, t.id)
                t_item.setData(0, _ROLE_TYPE, "text_leaf")
                # Global text always draws above every cell (fixed Z), so it
                # doesn't participate in z-stack drag-and-drop.
                t_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            text_root.setExpanded(True)

        self._is_updating = False

    def _add_cell_tree_item(self, parent_item, cell, col_label=""):
        if cell.split_direction != "none" and cell.children:
            split_label = tr("layers_split_v") if cell.split_direction == "vertical" else tr("layers_split_h")
            node = QTreeWidgetItem(parent_item, [f"{col_label}  {split_label}"])
            node.setData(0, _ROLE_ID, cell.id)
            node.setData(0, _ROLE_TYPE, "split")
            node.setFlags(Qt.ItemFlag.ItemIsEnabled)
            for i, child in enumerate(cell.children):
                self._add_cell_tree_item(node, child, col_label=f"{tr('layers_sub')} {i + 1}")
            node.setExpanded(True)
        else:
            if cell.image_path and not cell.is_placeholder:
                name  = os.path.basename(cell.image_path)
                label = f"{col_label}  {name}"
                itype = "cell_filled"
            else:
                label = f"{col_label}  {tr('layers_empty')}"
                itype = "cell_empty"

            tree_item = QTreeWidgetItem(parent_item, [label])
            tree_item.setData(0, _ROLE_ID, cell.id)
            tree_item.setData(0, _ROLE_TYPE, itype)
            # Explicit drag/drop flags: a leaf cell can be dragged onto any
            # other leaf cell (anywhere in the tree) to reorder the global
            # z-stack — see _BranchlessTree._compatible_target.
            tree_item.setFlags(
                tree_item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
            )
            z_index = getattr(cell, 'z_index', 0)
            if z_index:
                tree_item.setData(0, _ROLE_ZIDX, z_index)
            if itype == "cell_filled":
                tree_item.setData(0, _ROLE_IMG, cell.image_path)
                tree_item.setData(0, _ROLE_META, image_format_name(cell.image_path))

            pip_items = getattr(cell, 'pip_items', [])
            for pip in pip_items:
                if pip.pip_type == "zoom":
                    pip_label = f"  \u2295 {tr('layers_zoom_inset')}"
                    pip_img = cell.image_path
                else:
                    fname = os.path.basename(pip.image_path) if pip.image_path else tr('layers_empty')
                    pip_label = f"  \u2295 {fname}"
                    pip_img = pip.image_path
                pip_tree_item = QTreeWidgetItem(tree_item, [pip_label])
                pip_tree_item.setData(0, _ROLE_ID, pip.id)
                pip_tree_item.setData(0, _ROLE_TYPE, "pip_item")
                # PiP list order *is* the stacking order (last = frontmost),
                # so dragging one onto a sibling under the same cell directly
                # reorders cell.pip_items — see _BranchlessTree._compatible_target.
                pip_tree_item.setFlags(
                    pip_tree_item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
                )
                if pip_img:
                    pip_tree_item.setData(0, _ROLE_IMG, pip_img)
                    pip_tree_item.setData(0, _ROLE_META, image_format_name(pip_img))
            if pip_items:
                tree_item.setExpanded(True)

    # ── selection ─────────────────────────────────────────────────────────────

    def select_item(self, target_id):
        self._is_updating = True
        self.tree.clearSelection()
        if target_id is not None:
            lookup_id = target_id.removeprefix("label_")
            it = QTreeWidgetItemIterator(self.tree)
            while it.value():
                item = it.value()
                if item.data(0, _ROLE_ID) == lookup_id:
                    item.setSelected(True)
                    self.tree.scrollToItem(item)
                    break
                it += 1
        self._is_updating = False

    # ── i18n ──────────────────────────────────────────────────────────────────

    def retranslate_ui(self):
        self.header_label.setText(tr("layers_header"))
        self.refresh()

    # ── internals ────────────────────────────────────────────────────────────

    def _on_selection_changed(self):
        if self._is_updating:
            return
        ids = [
            item.data(0, _ROLE_ID)
            for item in self.tree.selectedItems()
            if item.data(0, _ROLE_ID)
        ]
        if ids:
            self.items_selected.emit(ids)

    def _on_context_menu(self, pos):
        # Prioritise the item under the cursor — right-clicking an unselected
        # item (common for PiP sub-items) should still show its menu.
        clicked = self.tree.itemAt(pos)
        if clicked and clicked.data(0, _ROLE_ID):
            # Select it so the menu handler finds it via selectedItems() too
            self.tree.setCurrentItem(clicked)
            ids = [clicked.data(0, _ROLE_ID)]
        else:
            ids = [
                item.data(0, _ROLE_ID)
                for item in self.tree.selectedItems()
                if item.data(0, _ROLE_ID)
            ]
        if ids:
            self.context_menu_requested.emit(ids, self.tree.viewport().mapToGlobal(pos))
