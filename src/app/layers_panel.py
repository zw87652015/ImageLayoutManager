import os

from src.app.i18n import tr
from src.app.theme import get_layers_tree_stylesheet, get_tokens, LIGHT

from PyQt6.QtCore import Qt, QSize, QRect, QRectF, pyqtSignal
from PyQt6.QtGui import (
    QColor, QPen, QPainter, QPainterPath, QBrush, QFont, QFontMetrics, QPixmap,
    QPalette,
)
from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QTreeWidget, QTreeWidgetItem,
    QTreeWidgetItemIterator, QStyledItemDelegate, QStyleOptionViewItem,
    QApplication, QStyle,
)

class _BranchlessTree(QTreeWidget):
    """QTreeWidget with branch lines and decorators completely suppressed."""
    def drawBranches(self, painter, rect, index):
        pass  # prevent Qt native style from drawing connecting lines


# ── Data roles stored on every QTreeWidgetItem ──────────────────────────────
_ROLE_ID   = Qt.ItemDataRole.UserRole          # cell/text id
_ROLE_TYPE = Qt.ItemDataRole.UserRole + 1      # "row"|"split"|"text_group"|"cell_filled"|"cell_empty"|"text_leaf"
_ROLE_IMG  = Qt.ItemDataRole.UserRole + 2      # image path (cell_filled only)
_ROLE_META = Qt.ItemDataRole.UserRole + 3      # right-side meta string (e.g. "2 cells")


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

        # text
        text_x  = tx + self.THUMB + self.PAD
        text_rect = QRect(text_x, r.top(), r.right() - text_x - 4, r.height())
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
            if itype == "cell_filled":
                tree_item.setData(0, _ROLE_IMG, cell.image_path)

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
                if pip_img:
                    pip_tree_item.setData(0, _ROLE_IMG, pip_img)
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
