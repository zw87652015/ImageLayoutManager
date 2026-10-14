"""SVG text font-size manager: a live preview with clickable text, and text group chips.

Layout
------
Left : interactive preview of the SVG. Each text is outlined in its group's colour
       (ungrouped: dashed grey). Click selects a text, Ctrl toggles, and dragging a
       rubber band selects every text it crosses. Hovering shows the text, its size and group.
Right: the element list (a colour dot shows each text's group) above the group chips.
       A click on a chip assigns the selected texts to that group; "+" makes a group
       at the selection's size; "∅" removes the selection from its groups.
"""

import os
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem,
    QLabel, QSplitter, QWidget, QFrame, QSizePolicy, QMenu,
)
from PyQt6.QtCore import Qt, pyqtSignal, QByteArray, QRectF, QPointF
from PyQt6.QtGui import QKeySequence, QPalette, QPainter, QImage, QColor, QPen, QBrush, QShortcut
from PyQt6.QtSvg import QSvgRenderer

from src.utils.svg_text_utils import (format_text_size, get_svg_text_elements,
                                      svg_text_preview_source, svg_text_rows,
                                      text_preview_rects)
from src.utils.editable_plot import plot_reflows
from ilmplot.document import has_plot_metadata
from src.app.help_dialog import show_context_help
from src.app.i18n import tr
from src.app.text_groups_widget import section_label
from src.app.text_group_chips import TextGroupChips, chip_hint, dot_icon, group_colour, populate_group_menu
from src.utils.text_group_assign import assign_svg, new_svg_group, ungroup_svg

_RENDER_MAX = 480


class SvgTextPreview(QWidget):
    """Clickable preview of the SVG with per-group outlines (modelled on RasterTextPreview)."""

    selection_changed = pyqtSignal(list)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._image = None
        self._rects = {}
        self._colours = {}
        self._tips = {}
        self._selected = []
        self._failed = ""
        self._hover = None
        self._rubber = None
        self._rubber_additive = False
        self.setMinimumSize(280, 280)
        self.setMouseTracking(True)
        self.setAccessibleName(tr("svgtxt_preview_label"))

    def set_content(self, image, rects, colours, tips):
        self._image = image
        self._rects = dict(rects)
        self._colours = dict(colours)
        self._tips = dict(tips)
        self._failed = ""
        self._hover = None
        self.update()

    def set_failed(self, text):
        self._image = None
        self._rects = {}
        self._failed = text
        self.update()

    def set_selected(self, keys):
        self._selected = list(keys)
        self.update()

    def _transform(self):
        if self._image is None or self._image.isNull():
            return None
        bounds = QRectF(self.rect()).adjusted(8, 8, -8, -8)
        scale = min(bounds.width() / self._image.width(), bounds.height() / self._image.height())
        left = bounds.center().x() - self._image.width() * scale / 2
        top = bounds.center().y() - self._image.height() * scale / 2
        return scale, left, top

    def _to_widget(self, rect):
        scale, left, top = self._transform()
        return QRectF(left + rect.x() * scale, top + rect.y() * scale, rect.width() * scale, rect.height() * scale)

    def _key_at(self, pos):
        if self._transform() is None:
            return None
        for key, rect in self._rects.items():
            if self._to_widget(rect).contains(pos):
                return key
        return None

    def paintEvent(self, event):
        painter = QPainter(self)
        pal = self.palette()
        painter.fillRect(self.rect(), pal.color(pal.ColorRole.AlternateBase))
        if self._image is None:
            painter.setPen(pal.color(pal.ColorRole.Text))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._failed or tr("svgtxt_preview_failed"))
            painter.end()
            return
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        scale, left, top = self._transform()
        target = QRectF(left, top, self._image.width() * scale, self._image.height() * scale)
        painter.drawImage(target, self._image)
        highlight = pal.color(QPalette.ColorRole.Highlight)
        for key, rect in self._rects.items():
            widget_rect = self._to_widget(rect).adjusted(-2, -2, 2, 2)
            selected = key in self._selected
            colour = self._colours.get(key)
            if colour:
                fill = QColor(colour)
                fill.setAlpha(46)
                painter.setPen(QPen(QColor(colour), 3 if selected else 1.5))
                painter.setBrush(QBrush(fill))
            elif selected:
                painter.setPen(QPen(highlight, 3))
                painter.setBrush(Qt.BrushStyle.NoBrush)
            else:
                painter.setPen(QPen(pal.color(QPalette.ColorRole.Mid), 1, Qt.PenStyle.DashLine))
                painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(widget_rect)
        if self._rubber is not None:
            painter.setPen(QPen(highlight, 1, Qt.PenStyle.DashLine))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRect(QRectF(self._rubber[0], self._rubber[1]).normalized())
        painter.end()

    def mousePressEvent(self, event):
        self.setFocus()
        if event.button() != Qt.MouseButton.LeftButton or self._transform() is None:
            return
        key = self._key_at(event.position())
        additive = bool(event.modifiers() & Qt.KeyboardModifier.ControlModifier)
        if key is None:
            self._rubber = (event.position(), event.position())
            self._rubber_additive = additive
            if not additive:
                self._selected = []
                self.selection_changed.emit([])
            self.update()
            return
        if additive:
            keys = [k for k in self._selected if k != key] if key in self._selected else self._selected + [key]
        else:
            keys = [key]
        self._selected = keys
        self.selection_changed.emit(list(keys))
        self.update()

    def mouseMoveEvent(self, event):
        if self._rubber is not None:
            self._rubber = (self._rubber[0], event.position())
            self.update()
            return
        key = self._key_at(event.position())
        if key != self._hover:
            self._hover = key
            self.setToolTip(self._tips.get(key, "") if key else "")
            self.update()

    def mouseReleaseEvent(self, event):
        if self._rubber is None or event.button() != Qt.MouseButton.LeftButton:
            return
        area = QRectF(self._rubber[0], self._rubber[1]).normalized()
        self._rubber = None
        hits = [k for k, rect in self._rects.items() if self._to_widget(rect).intersects(area)]
        if self._rubber_additive:
            keys = self._selected + [k for k in hits if k not in self._selected]
        else:
            keys = hits
        self._selected = keys
        self.selection_changed.emit(list(keys))
        self.update()

    def leaveEvent(self, event):
        self._hover = None
        self.setToolTip("")
        super().leaveEvent(event)



class SvgTextInspectorWindow(QDialog):
    """Unified SVG text manager: select texts in the preview, assign them to groups, set sizes."""

    groups_changed = pyqtSignal()

    def __init__(self, svg_path: str, project, cell=None, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.svg_path = svg_path
        self.project = project
        self._cell = cell
        self._sizes = {}
        self._preview_base = None
        self._preview_rects = {}

        self.setWindowTitle(tr("svgtxt_inspector_title"))
        QShortcut(QKeySequence(Qt.Key.Key_F1), self, activated=lambda: show_context_help(self, "text_sizes"))
        self.setWindowFlags(
            Qt.WindowType.Window |
            Qt.WindowType.WindowCloseButtonHint |
            Qt.WindowType.WindowMaximizeButtonHint
        )
        self.setMinimumSize(780, 540)
        self.resize(980, 640)

        self._build_ui()
        self._refresh_all()

    # ──────────────────────────────────────────────────────────────────
    # UI construction
    # ──────────────────────────────────────────────────────────────────

    def _build_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(10, 10, 10, 10)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        root.addWidget(splitter)

        # ── Left: preview ──────────────────────────────────────────────
        left = QWidget()
        lv = QVBoxLayout(left)
        lv.setContentsMargins(0, 0, 0, 0)
        lv.setSpacing(4)

        lv.addWidget(QLabel(tr("svgtxt_preview_label")))

        self._norm_label = QLabel()
        self._norm_label.setStyleSheet("color: palette(link); font-style: italic;")
        self._norm_label.setWordWrap(True)
        lv.addWidget(self._norm_label)

        self._preview_label = SvgTextPreview()
        self._preview_label.selection_changed.connect(self._on_preview_selection)
        lv.addWidget(self._preview_label, 1)
        splitter.addWidget(left)

        # ── Right: elements + group chips ──────────────────────────────
        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        rv.setSpacing(8)

        rv.addWidget(self._section_label(tr("svgtxt_elements_label")))

        self._size_hint = QLabel()
        self._size_hint.setWordWrap(True)
        rv.addWidget(self._size_hint)

        self._elem_list = QListWidget()
        self._elem_list.setSelectionMode(QListWidget.SelectionMode.ExtendedSelection)
        self._elem_list.setMinimumHeight(120)
        self._elem_list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self._elem_list.customContextMenuRequested.connect(self._on_elem_context_menu)
        self._elem_list.itemSelectionChanged.connect(self._on_list_selection)
        rv.addWidget(self._elem_list, 2)

        div = QFrame()
        div.setFrameShape(QFrame.Shape.HLine)
        rv.addWidget(div)

        rv.addWidget(self._section_label(tr("text_chips_label")))
        self._chip_hint = QLabel()
        self._chip_hint.setWordWrap(True)
        rv.addWidget(self._chip_hint)
        self._groups_widget = TextGroupChips(self.project)
        self._groups_widget.assign_requested.connect(self._on_assign)
        self._groups_widget.new_group_requested.connect(self._on_new_group)
        self._groups_widget.groups_changed.connect(self._on_groups_edited)
        self._groups_widget.members_requested.connect(self._on_members_requested)
        rv.addWidget(self._groups_widget, 1)

        splitter.addWidget(right)
        splitter.setChildrenCollapsible(False)
        left.setMinimumWidth(300)
        right.setMinimumWidth(380)
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([480, 500])

    _section_label = staticmethod(section_label)

    # ──────────────────────────────────────────────────────────────────
    # Refresh helpers
    # ──────────────────────────────────────────────────────────────────

    def _refresh_all(self):
        self._refresh_size_hint()
        self._refresh_elements()
        self._refresh_preview()
        self._groups_widget.refresh()
        self._update_selection_info()

    def _refresh_size_hint(self):
        native = self._cell is not None and has_plot_metadata(self.svg_path)
        self._size_hint.setVisible(native)
        if native:
            on = plot_reflows(self.project, self._cell)
            self._size_hint.setText(tr("svgtxt_size_reflow_on" if on
                                       else "svgtxt_size_reflow_off"))

    def _element_rows(self):
        if self._cell is None:
            return [{'key': e['key'], 'text': e['text'], 'size_pt': None}
                    for e in get_svg_text_elements(self.svg_path)]
        return svg_text_rows(self.project, self._cell)

    def _svg_file_bytes(self):
        try:
            with open(self.svg_path, 'rb') as fh:
                return fh.read()
        except OSError:
            return None

    def _group_of_key(self):
        """element key -> (group id, group name) for this SVG."""
        return {
            m.element_key: (g.id, g.name)
            for g in self.project.svg_text_groups
            for m in g.members
            if m.svg_path == self.svg_path
        }

    def _refresh_preview(self):
        source = svg_text_preview_source(self.project, self._cell) if self._cell else None
        if source is not None:
            key_bytes, positioned, processed = source
        else:
            key_bytes, positioned, processed = self._svg_file_bytes(), False, None

        if self._cell and getattr(self._cell, 'svg_normalize_text', False):
            pt = getattr(self._cell, 'svg_normalize_text_pt', 8.0)
            self._norm_label.setText(tr("svgtxt_norm_active_hint").format(pt=pt))
        else:
            self._norm_label.setText("")

        renderer = QSvgRenderer(QByteArray(processed)) if processed else QSvgRenderer(self.svg_path)
        if not renderer.isValid():
            self._preview_label.set_failed(tr("svgtxt_preview_failed"))
            self._preview_base = None
            self._preview_rects = {}
            return
        sz = renderer.defaultSize()
        if sz.isEmpty():
            sz.setWidth(400); sz.setHeight(400)
        scale = min(_RENDER_MAX / sz.width(), _RENDER_MAX / sz.height(), 1.0)
        w, h = int(sz.width() * scale), int(sz.height() * scale)
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(Qt.GlobalColor.transparent)
        p = QPainter(img)
        renderer.render(p)
        p.end()
        self._preview_base = img
        self._preview_rects = (text_preview_rects(key_bytes, None, w, h, positioned)
                               if key_bytes else {})
        groups = self._group_of_key()
        texts = {r['key']: r['text'] for r in self._element_rows()}
        colours = {}
        tips = {}
        for key, rect in self._preview_rects.items():
            text = texts.get(key, key)
            size = self._sizes.get(key)
            group = groups.get(key)
            colours[key] = group_colour(self.project, group[0]) if group else None
            size_text = f" · {format_text_size(size)} pt" if size is not None else ""
            tips[key] = f"{text[:60]}{size_text} · {group[1] if group else tr('text_chip_ungrouped')}"
        self._preview_label.set_content(img, self._preview_rects, colours, tips)
        self._preview_label.set_selected(self._selected_keys())

    def _refresh_elements(self):
        sel_keys = set(self._selected_keys())
        self._elem_list.blockSignals(True)
        self._elem_list.clear()
        groups = self._group_of_key()
        self._sizes = {}
        for el in self._element_rows():
            label = el['text'][:60]
            if el['size_pt'] is not None:
                self._sizes[el['key']] = round(el['size_pt'], 1)
                label = f"{label} · {format_text_size(el['size_pt'])} pt"
            group = groups.get(el['key'])
            suffix = f"  [{group[1]}]" if group else ""
            item = QListWidgetItem(f"{label}{suffix}")
            item.setData(Qt.ItemDataRole.UserRole, el['key'])
            colour = group_colour(self.project, group[0]) if group else None
            if colour:
                item.setIcon(dot_icon(colour))
            self._elem_list.addItem(item)
            if el['key'] in sel_keys:
                item.setSelected(True)
        self._elem_list.blockSignals(False)

    def _update_selection_info(self):
        keys = self._selected_keys()
        size = self._sizes.get(keys[0]) if keys else None
        self._groups_widget.set_selection_info(len(keys), size)
        self._chip_hint.setText(chip_hint(len(keys), len(self.project.svg_text_groups)))

    def _on_elem_context_menu(self, pos):
        item = self._elem_list.itemAt(pos)
        if item is not None and not item.isSelected():
            self._elem_list.clearSelection()
            item.setSelected(True)
        keys = self._selected_keys()
        if not keys:
            return
        menu = QMenu(self)
        group_of_key = self._group_of_key()
        populate_group_menu(
            menu, self.project, self._on_assign, self._on_new_group,
            lambda: self._on_assign(None),
            can_remove=any(key in group_of_key for key in keys),
        )
        menu.exec(self._elem_list.viewport().mapToGlobal(pos))

    def _on_groups_edited(self):
        self._groups_widget.refresh()
        self._refresh_elements()
        self._refresh_preview()
        self._update_selection_info()
        self.groups_changed.emit()

    def _on_members_requested(self, group_id):
        group = next((g for g in self.project.svg_text_groups if g.id == group_id), None)
        if group is None:
            return
        keys = [m.element_key for m in group.members if m.svg_path == self.svg_path]
        self._select_keys(keys)

    def _select_keys(self, keys):
        self._elem_list.blockSignals(True)
        for index in range(self._elem_list.count()):
            item = self._elem_list.item(index)
            item.setSelected(item.data(Qt.ItemDataRole.UserRole) in keys)
        self._elem_list.blockSignals(False)
        self._update_highlight()

    # ──────────────────────────────────────────────────────────────────
    # Selection
    # ──────────────────────────────────────────────────────────────────

    def _selected_keys(self):
        return [item.data(Qt.ItemDataRole.UserRole) for item in self._elem_list.selectedItems()
                if item.data(Qt.ItemDataRole.UserRole)]

    def _on_list_selection(self):
        self._update_highlight()

    def _on_preview_selection(self, keys):
        self._select_keys(keys)

    def _update_highlight(self):
        keys = self._selected_keys()
        self._preview_label.set_selected(keys)
        self._update_selection_info()

    # ──────────────────────────────────────────────────────────────────
    # Membership (same effect as the former combo / buttons)
    # ──────────────────────────────────────────────────────────────────

    def _on_assign(self, group_id):
        keys = self._selected_keys()
        if group_id is None:
            if ungroup_svg(self.project, self.svg_path, keys):
                self._on_groups_edited()
            return
        if assign_svg(self.project, self.svg_path, keys, group_id):
            self._on_groups_edited()

    def _on_new_group(self):
        keys = self._selected_keys()
        size = self._sizes.get(keys[0]) if keys else None
        if size is not None:
            name = tr("svgtxt_plot_group_name").format(pt=format_text_size(size))
            font_size = size
        else:
            name = tr("svgtxt_default_group_name")
            font_size = 12.0
        gid = new_svg_group(self.project, name, font_size)
        if keys:
            assign_svg(self.project, self.svg_path, keys, gid)
        self._on_groups_edited()

    def refresh(self):
        """Re-populate after external changes (e.g. project reload)."""
        self._refresh_all()
