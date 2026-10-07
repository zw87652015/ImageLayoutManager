"""Qt view layer for the in-memory Plot Editor worksheet.

``WorksheetModel`` is a ``QAbstractTableModel`` over ``Worksheet``.
``WorksheetView`` is the main grid; a frozen ``_LabelOverlay`` child shows
the three meta rows above the frozen viewport and shares the same model
and selection model.
"""

from __future__ import annotations

from PyQt6.QtCore import (QAbstractTableModel, QEasingCurve,
                          QItemSelection, QItemSelectionModel, QModelIndex,
                          QPersistentModelIndex, QVariantAnimation, Qt)
from PyQt6.QtGui import QPalette
from PyQt6.QtWidgets import (QAbstractItemDelegate, QAbstractItemView,
                             QApplication, QFrame,
                             QHeaderView, QLineEdit, QMenu, QMessageBox,
                             QStyle, QStyledItemDelegate, QStyleFactory,
                             QStyleOptionViewItem, QTableView, QWidget)

from src.app.motion import start_animation
from src.app.theme import get_tokens, token_color

from .i18n import tr
from ilmplot.mathtext import has_math
from .worksheet import (DESIGNATION_TEXT, META_LABELS, META_ROWS,
                        WorksheetLimitError, parse_tsv, to_tsv)

_META_KEYS = ('meta_long_name', 'meta_units', 'meta_comments')
_DESIGNATION_KEYS = {'xErr': 'design_xerr', 'yErr': 'design_yerr',
                     'yErrPlus': 'design_yerr_plus',
                     'yErrMinus': 'design_yerr_minus',
                     'Label': 'design_label',
                     'Disregard': 'design_disregard'}


def _meta_label(row):
    return tr(_META_KEYS[row])


def _designation_label(designation, text):
    key = _DESIGNATION_KEYS.get(designation)
    return tr(key) if key is not None else text
from .zoom import ZOOM_MAX, ZOOM_MIN, next_zoom


class WorksheetModel(QAbstractTableModel):
    """Table model exposing a ``Worksheet`` (cached row/column counts)."""

    def __init__(self, worksheet, theme, parent=None):
        super().__init__(parent)
        self._ws = worksheet
        self._tokens = get_tokens(theme)
        self._rows = worksheet.display_rows()
        self._cols = worksheet.column_count
        worksheet.add_listener(self._on_event)

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._rows

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else self._cols

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid():
            return None
        if role in (Qt.ItemDataRole.DisplayRole, Qt.ItemDataRole.EditRole):
            return self._ws.grid_text(index.column(), index.row())
        if role == Qt.ItemDataRole.TextAlignmentRole:
            if index.row() < META_ROWS:
                align = Qt.AlignmentFlag.AlignLeft
            else:
                v = self._ws.value(index.column(),
                                   index.row() - META_ROWS)
                align = (Qt.AlignmentFlag.AlignRight
                         if isinstance(v, float)
                         else Qt.AlignmentFlag.AlignLeft)
            return int(align | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ForegroundRole:
            if index.row() < META_ROWS:
                return token_color(self._tokens['text_sec'])
            if self._ws.column(index.column()).designation == 'Disregard':
                return token_color(self._tokens['text_tert'])
        return None

    def setData(self, index, value, role=Qt.ItemDataRole.EditRole):
        if not index.isValid() or role != Qt.ItemDataRole.EditRole:
            return False
        self._ws.set_block(index.column(), index.row(),
                           [[value if value is not None else '']])
        return True

    def flags(self, index):
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return (Qt.ItemFlag.ItemIsSelectable | Qt.ItemFlag.ItemIsEnabled
                | Qt.ItemFlag.ItemIsEditable)

    def headerData(self, section, orientation,
                   role=Qt.ItemDataRole.DisplayRole):
        if role != Qt.ItemDataRole.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return self._ws.header_label(section)
        if section < META_ROWS:
            return _meta_label(section)
        return str(section - META_ROWS + 1)

    def _on_event(self, ev):
        kind = ev[0]
        if kind == 'cells':
            _tag, c0, g0, c1, g1 = ev
            self.dataChanged.emit(self.index(g0, c0), self.index(g1, c1))
            self._sync_rows()
        elif kind == 'rows_inserted':
            _tag, at, count = ev
            first = META_ROWS + at
            self.beginInsertRows(QModelIndex(), first, first + count - 1)
            self._rows += count
            self.endInsertRows()
            self._sync_rows()
        elif kind == 'rows_removed':
            _tag, at, count = ev
            first = META_ROWS + at
            last = min(first + count - 1, self._rows - 1)
            if first <= last:
                self.beginRemoveRows(QModelIndex(), first, last)
                self._rows -= last - first + 1
                self.endRemoveRows()
            self._sync_rows()
        elif kind == 'columns_inserted':
            _tag, at, count, _animate = ev
            self.beginInsertColumns(QModelIndex(), at, at + count - 1)
            self._cols += count
            self.endInsertColumns()
        elif kind == 'columns_removed':
            _tag, at, count = ev
            self.beginRemoveColumns(QModelIndex(), at, at + count - 1)
            self._cols -= count
            self.endRemoveColumns()
        elif kind == 'header':
            _tag, c0, c1 = ev
            self.headerDataChanged.emit(Qt.Orientation.Horizontal, c0, c1)
            self.dataChanged.emit(self.index(0, c0),
                                  self.index(self._rows - 1, c1))
        elif kind == 'reset':
            self.beginResetModel()
            self._rows = self._ws.display_rows()
            self._cols = self._ws.column_count
            self.endResetModel()

    def _sync_rows(self):
        new = self._ws.display_rows()
        if new > self._rows:
            self.beginInsertRows(QModelIndex(), self._rows, new - 1)
            self._rows = new
            self.endInsertRows()
        elif new < self._rows:
            self.beginRemoveRows(QModelIndex(), new, self._rows - 1)
            self._rows = new
            self.endRemoveRows()


class _LabelOverlay(QTableView):
    """Frozen meta-row strip sharing the main view's model/selection."""

    def __init__(self, main):
        super().__init__(main)
        self._main = main
        self.setStyle(main._cell_style)
        self.setObjectName('plotWorksheetLabels')
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.horizontalHeader().hide()
        self.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.setTabKeyNavigation(True)
        self.setCornerButtonEnabled(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(main._cell_menu)
        self.verticalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalHeader().customContextMenuRequested.connect(
            main._meta_row_menu)
        self.verticalHeader().sectionClicked.connect(main._select_meta_row)

    def scrollTo(self, index, hint=QAbstractItemView.ScrollHint.EnsureVisible):
        if not index.isValid():
            return
        x = self.columnViewportPosition(index.column())
        w = self.columnWidth(index.column())
        bar = self.horizontalScrollBar()
        if x < 0:
            bar.setValue(bar.value() + x)
        elif x + w > self.viewport().width():
            bar.setValue(bar.value() + x + w - self.viewport().width())

    def moveCursor(self, action, modifiers):
        result = super().moveCursor(action, modifiers)
        if result.isValid() and result.row() >= META_ROWS:
            self._main._focus_data_row(result.row() - META_ROWS,
                                       result.column())
            return self.currentIndex()
        return result

    def closeEditor(self, editor, hint):
        super().closeEditor(editor, hint)
        if hint == QAbstractItemDelegate.EndEditHint.SubmitModelCache:
            cur = self.currentIndex()
            if not cur.isValid():
                return
            if cur.row() >= META_ROWS - 1:
                self._main._focus_data_row(0, cur.column())
            else:
                self.selectionModel().setCurrentIndex(
                    self.model().index(cur.row() + 1, cur.column()),
                    QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def wheelEvent(self, event):
        QApplication.sendEvent(self._main.viewport(), event)

    def keyPressEvent(self, event):
        self._main._shared_key(self, event)
        event.accept()


class WorksheetDelegate(QStyledItemDelegate):
    """Line editor for worksheet cells; paints meta-row math inline."""

    def createEditor(self, parent, option, index):
        editor = QLineEdit(parent)
        editor.setObjectName('plotWorksheetEditor')
        editor.setFrame(False)
        return editor

    def paint(self, painter, option, index):
        text = index.data(Qt.ItemDataRole.DisplayRole) or ''
        if index.row() >= META_ROWS or not has_math(text):
            super().paint(painter, option, index)
            return
        opt = QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        from .math_render import math_pixmap
        role = (QPalette.ColorRole.HighlightedText
                if opt.state & QStyle.StateFlag.State_Selected
                else QPalette.ColorRole.Text)
        pm = math_pixmap(text, opt.font, opt.palette.color(role),
                         painter.device().devicePixelRatioF())
        if pm is None:
            super().paint(painter, option, index)
            return
        widget = opt.widget
        style = widget.style() if widget is not None \
            else QApplication.style()
        opt.text = ''
        painter.save()
        style.drawControl(QStyle.ControlElement.CE_ItemViewItem,
                          opt, painter, widget)
        text_rect = style.subElementRect(
            QStyle.SubElement.SE_ItemViewItemText, opt, widget)
        dpr = pm.devicePixelRatio() or 1.0
        logical_h = pm.height() / dpr
        if 0 < text_rect.height() < logical_h:
            scale = text_rect.height() / logical_h
            pm = pm.scaled(
                pm.size() * scale,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation)
            pm.setDevicePixelRatio(dpr)
            logical_h = pm.height() / dpr
        painter.setClipRect(opt.rect)
        y = opt.rect.center().y() - logical_h / 2
        painter.drawPixmap(text_rect.left(), int(y), pm)
        painter.restore()


class WorksheetView(QTableView):
    """Main worksheet grid with a frozen meta-label overlay."""

    def __init__(self, worksheet, theme, scale=1.0, parent=None):
        super().__init__(parent)
        self.worksheet = worksheet
        self._tokens = get_tokens(theme)
        self._theme = theme
        self._base_scale = scale
        self._zoom = 1.0
        from . import chrome
        self.setObjectName('plotWorksheet')
        self._cell_style = QStyleFactory.create('Fusion')
        self._cell_style.setParent(self)
        self.setStyle(self._cell_style)
        self.setStyleSheet(chrome.worksheet_stylesheet(theme, scale))
        self.ensurePolished()
        self.setModel(WorksheetModel(worksheet, theme, self))
        self.setItemDelegate(WorksheetDelegate(self))
        self.setSelectionMode(
            QAbstractItemView.SelectionMode.ExtendedSelection)
        self.setSelectionBehavior(
            QAbstractItemView.SelectionBehavior.SelectItems)
        self.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.AnyKeyPressed)
        self.setTabKeyNavigation(True)
        self.setCornerButtonEnabled(False)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._cell_menu)

        for header in (self.horizontalHeader(),):
            header.setDefaultSectionSize(96)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
            header.setHighlightSections(True)
            header.setContextMenuPolicy(
                Qt.ContextMenuPolicy.CustomContextMenu)
            header.customContextMenuRequested.connect(self._column_menu)
        self.verticalHeader().setContextMenuPolicy(
            Qt.ContextMenuPolicy.CustomContextMenu)
        self.verticalHeader().customContextMenuRequested.connect(
            self._row_menu)
        row_h = self._row_height()
        for view in (self,):
            view.verticalHeader().setDefaultSectionSize(row_h)
            view.verticalHeader().setSectionResizeMode(
                QHeaderView.ResizeMode.Fixed)
        self.horizontalHeader().sectionPressed.connect(
            self._prune_meta_selection)
        self.horizontalHeader().sectionEntered.connect(
            self._prune_meta_selection)
        self.horizontalHeader().sectionClicked.connect(
            self._prune_meta_selection)

        self._labels = _LabelOverlay(self)
        self._labels.setModel(self.model())
        self._labels.setSelectionModel(self.selectionModel())
        self._labels.setItemDelegate(WorksheetDelegate(self._labels))
        self._labels.verticalHeader().setDefaultSectionSize(row_h)
        self._labels.verticalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Fixed)
        self._labels.horizontalHeader().setHighlightSections(True)

        self._labels.ensurePolished()
        self._hide_meta_rows()
        self._sync_vheader_width()
        self._sync_overlay_columns()

        self._labels.verticalScrollBar().valueChanged.connect(
            lambda v: v and self._labels.verticalScrollBar().setValue(0))

        self._syncing = False
        self.horizontalScrollBar().valueChanged.connect(
            lambda v: self._sync_hscroll(self._labels, v))
        self._labels.horizontalScrollBar().valueChanged.connect(
            lambda v: self._sync_hscroll(self, v))
        self.horizontalHeader().sectionResized.connect(
            lambda i, _o, n: self._labels.setColumnWidth(i, n))
        self.model().modelReset.connect(self._on_model_reset)
        self.model().rowsInserted.connect(self._sync_vheader_width)
        self.model().rowsRemoved.connect(self._sync_vheader_width)
        self.model().modelReset.connect(self._sync_vheader_width)

        self._animations = []
        self.worksheet.add_listener(self._on_ws_event)

    # ── geometry ───────────────────────────────────────────────────────

    def _hide_meta_rows(self):
        for r in range(META_ROWS):
            self.setRowHidden(r, True)

    def _sync_vheader_width(self, *args):
        fm = self.fontMetrics()
        texts = [_meta_label(r) for r in range(META_ROWS)]
        texts.append(str(max(1, self.model().rowCount() - META_ROWS)))
        w = max(fm.horizontalAdvance(t) for t in texts) + 16
        self.verticalHeader().setFixedWidth(w)
        self._labels.verticalHeader().setFixedWidth(w)
        self.updateGeometries()

    def _sync_overlay_columns(self):
        for c in range(self.model().columnCount()):
            self._labels.setColumnWidth(c, self.columnWidth(c))

    def _on_model_reset(self):
        self._hide_meta_rows()
        self._sync_overlay_columns()

    def _on_ws_event(self, ev):
        kind = ev[0]
        if kind == 'rows_inserted':
            _tag, at, count = ev
            self._animate_sections(Qt.Orientation.Vertical,
                                   META_ROWS + at, count)
        elif kind == 'columns_inserted':
            _tag, at, count, animate = ev
            if animate:
                self._animate_sections(Qt.Orientation.Horizontal,
                                       at, count)
            self._sync_overlay_columns()
        elif kind == 'columns_removed':
            self._sync_overlay_columns()

    def _resize_section(self, orientation, pindex, size):
        if not pindex.isValid():
            return
        if orientation == Qt.Orientation.Vertical:
            self.verticalHeader().resizeSection(pindex.row(), size)
        else:
            self.setColumnWidth(pindex.column(), size)

    def _animate_sections(self, orientation, first, count):
        model = self.model()
        if orientation == Qt.Orientation.Vertical:
            target = self.verticalHeader().defaultSectionSize()
            pindexes = [QPersistentModelIndex(
                model.index(first + i, 0)) for i in range(count)]
        else:
            target = self.horizontalHeader().defaultSectionSize()
            pindexes = [QPersistentModelIndex(
                model.index(META_ROWS, first + i)) for i in range(count)]
        anim = QVariantAnimation(self)
        anim.setStartValue(0.0)
        anim.setEndValue(1.0)
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)

        def on_value(v):
            for p in pindexes:
                self._resize_section(orientation, p, round(target * v))

        def finish():
            for p in pindexes:
                self._resize_section(orientation, p, target)
            if entry in self._animations:
                self._animations.remove(entry)

        entry = (anim, finish)
        anim.valueChanged.connect(lambda v: on_value(v))
        anim.finished.connect(finish)
        for p in pindexes:
            self._resize_section(orientation, p, 0)
        self._animations.append(entry)
        start_animation(anim, 250, spatial=True)
        if anim.duration() == 0:
            finish()

    # ── zoom ───────────────────────────────────────────────────────────

    def zoom(self):
        return self._zoom

    def _row_height(self):
        return self.fontMetrics().height() + 8

    def set_zoom(self, z):
        z = min(ZOOM_MAX, max(ZOOM_MIN, z))
        if z == self._zoom:
            return
        old = self._zoom
        self._zoom = z
        for anim, _finish in list(self._animations):
            anim.stop()
        from . import chrome
        self.setStyleSheet(chrome.worksheet_stylesheet(
            self._theme, self._base_scale * z))
        self.ensurePolished()
        self._labels.ensurePolished()
        row_h = self._row_height()
        for view in (self, self._labels):
            header = view.verticalHeader()
            header.setDefaultSectionSize(row_h)
            for r in range(self.model().rowCount()):
                if not view.isRowHidden(r):
                    header.resizeSection(r, row_h)
        ratio = z / old
        for c in range(self.model().columnCount()):
            self.setColumnWidth(
                c, max(1, round(self.columnWidth(c) * ratio)))
        self.horizontalHeader().setDefaultSectionSize(round(96 * z))
        self._sync_vheader_width()
        self.updateGeometries()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            steps = event.angleDelta().y() / 120.0
            pos = event.position()
            h, v = (self.horizontalScrollBar().value(),
                    self.verticalScrollBar().value())
            old = self._zoom
            self.set_zoom(next_zoom(self._zoom, steps))
            ratio = self._zoom / old
            if ratio != 1.0:
                self.horizontalScrollBar().setValue(
                    round((h + pos.x()) * ratio - pos.x()))
                self.verticalScrollBar().setValue(
                    round((v + pos.y()) * ratio - pos.y()))
            event.accept()
            return
        super().wheelEvent(event)

    def _sync_hscroll(self, other, value):
        if self._syncing:
            return
        self._syncing = True
        other.horizontalScrollBar().setValue(value)
        self._syncing = False

    def updateGeometries(self):
        if getattr(self, '_labels', None) is None:
            super().updateGeometries()
            return
        if getattr(self, '_in_update_geometries', False):
            return
        self._in_update_geometries = True
        try:
            super().updateGeometries()
            vh = self.verticalHeader().width()
            hh = self.horizontalHeader().height()
            labels_h = sum(self._labels.rowHeight(r)
                           for r in range(META_ROWS))
            self.setViewportMargins(vh, hh + labels_h, 0, 0)
            vg = self.viewport().geometry()
            self.verticalHeader().setGeometry(
                vg.left() - vh, vg.top(), vh, vg.height())
            self.horizontalHeader().setGeometry(
                vg.left(), vg.top() - labels_h - hh, vg.width(), hh)
            self._labels.setGeometry(
                vg.left() - vh, vg.top() - labels_h,
                vh + vg.width(), labels_h)
            self._labels.raise_()
        finally:
            self._in_update_geometries = False

    # ── selection helpers ──────────────────────────────────────────────

    def _select_rect(self, rect, scroll=True):
        c0, g0, c1, g1 = rect
        model = self.model()
        sel = QItemSelection(model.index(g0, c0), model.index(g1, c1))
        sm = self.selectionModel()
        sm.select(sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        sm.setCurrentIndex(model.index(g0, c0),
                           QItemSelectionModel.SelectionFlag.NoUpdate)
        if scroll and g0 >= META_ROWS:
            self.scrollTo(model.index(g0, c0))

    def _selected_box(self):
        idxs = self.selectionModel().selectedIndexes()
        if not idxs:
            cur = self.currentIndex()
            return (cur.column(), cur.row(), cur.column(), cur.row())
        cols = [i.column() for i in idxs]
        rows = [i.row() for i in idxs]
        return (min(cols), min(rows), max(cols), max(rows))

    def _prune_meta_selection(self, *args):
        sm = self.selectionModel()
        model = self.model()
        sel = sm.selection()
        pruned = QItemSelection()
        dirty = False
        for r in sel:
            top = max(r.top(), META_ROWS)
            if r.top() < META_ROWS:
                dirty = True
            if top <= r.bottom():
                pruned.select(model.index(top, r.left()),
                              model.index(r.bottom(), r.right()))
        if dirty:
            sm.select(pruned,
                      QItemSelectionModel.SelectionFlag.ClearAndSelect)
            cur = sm.currentIndex()
            if cur.isValid():
                sm.setCurrentIndex(
                    cur, QItemSelectionModel.SelectionFlag.NoUpdate)

    def _select_column(self, col):
        model = self.model()
        last = model.rowCount() - 1
        sel = QItemSelection(model.index(META_ROWS, col),
                             model.index(last, col))
        self.selectionModel().select(
            sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def _select_meta_row(self, row):
        model = self.model()
        sel = QItemSelection(model.index(row, 0),
                             model.index(row, model.columnCount() - 1))
        self.selectionModel().select(
            sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)

    def _focus_data_row(self, data_row, col):
        self.setFocus()
        index = self.model().index(META_ROWS + data_row, col)
        self.selectionModel().setCurrentIndex(
            index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
        self.scrollTo(index)

    # ── keyboard ───────────────────────────────────────────────────────

    def moveCursor(self, action, modifiers):
        cur = self.currentIndex()
        if modifiers & Qt.KeyboardModifier.ControlModifier:
            model = self.model()
            last_row = META_ROWS + max(self.worksheet.row_count - 1, 0)
            if action == QAbstractItemView.CursorAction.MoveUp:
                return model.index(META_ROWS, cur.column())
            if action == QAbstractItemView.CursorAction.MoveDown:
                return model.index(last_row, cur.column())
            if action == QAbstractItemView.CursorAction.MoveLeft:
                return model.index(cur.row(), 0)
            if action == QAbstractItemView.CursorAction.MoveRight:
                return model.index(cur.row(), model.columnCount() - 1)
        if (action == QAbstractItemView.CursorAction.MoveUp
                and cur.row() == META_ROWS):
            self._labels.setFocus()
            index = self.model().index(META_ROWS - 1, cur.column())
            self.selectionModel().setCurrentIndex(
                index, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            return self.currentIndex()
        return super().moveCursor(action, modifiers)

    def _shared_key(self, view, event):
        key = event.key()
        mods = event.modifiers()
        if (key == Qt.Key.Key_0
                and mods & Qt.KeyboardModifier.ControlModifier):
            self.set_zoom(1.0)
            cur = view.currentIndex()
            if cur.isValid():
                self.scrollTo(cur)
            event.accept()
            return
        cur = view.currentIndex()
        if cur.isValid() and (cur.row() < META_ROWS) != (view is self._labels):
            owner = self._labels if cur.row() < META_ROWS else self
            owner.setFocus()
            self._shared_key(owner, event)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if (cur.isValid()
                    and view.state()
                    != QAbstractItemView.State.EditingState):
                step = -1 if mods & Qt.KeyboardModifier.ShiftModifier else 1
                row = cur.row() + step
                if view is self:
                    row = max(META_ROWS,
                              min(row, self.model().rowCount() - 1))
                else:
                    if row >= META_ROWS:
                        self._focus_data_row(0, cur.column())
                        return
                    row = max(0, row)
                self.selectionModel().setCurrentIndex(
                    self.model().index(row, cur.column()),
                    QItemSelectionModel.SelectionFlag.ClearAndSelect)
                if view is self:
                    self.scrollTo(self.model().index(row, cur.column()))
                return
        elif key == Qt.Key.Key_Backspace:
            self.clear_selection_contents()
            return
        QTableView.keyPressEvent(view, event)

    def keyPressEvent(self, event):
        self._shared_key(self, event)

    def closeEditor(self, editor, hint):
        super().closeEditor(editor, hint)
        if hint == QAbstractItemDelegate.EndEditHint.SubmitModelCache:
            cur = self.currentIndex()
            if cur.isValid():
                row = min(cur.row() + 1, self.model().rowCount() - 1)
                self.selectionModel().setCurrentIndex(
                    self.model().index(row, cur.column()),
                    QItemSelectionModel.SelectionFlag.ClearAndSelect)

    # ── clipboard / edit API ───────────────────────────────────────────

    def copy(self):
        if (not self.selectionModel().selectedIndexes()
                and not self.currentIndex().isValid()):
            return
        c0, g0, c1, g1 = self._selected_box()
        selected = {(i.row(), i.column())
                    for i in self.selectionModel().selectedIndexes()}
        rows = []
        for g in range(g0, g1 + 1):
            rows.append([
                self.worksheet.grid_text(c, g) if (g, c) in selected
                else '' for c in range(c0, c1 + 1)])
        QApplication.clipboard().setText(to_tsv(rows))

    def cut(self):
        if (not self.selectionModel().selectedIndexes()
                and not self.currentIndex().isValid()):
            return
        self.copy()
        box = self._selected_box()
        rect = self.worksheet.clear([box], label='Cut')
        if rect:
            self._select_rect(rect)

    def paste(self):
        rows = parse_tsv(QApplication.clipboard().text())
        if not rows:
            return
        if (not self.selectionModel().selectedIndexes()
                and not self.currentIndex().isValid()):
            box = (0, META_ROWS, 0, META_ROWS)
        else:
            box = self._selected_box()
        try:
            if (len(rows) == 1 and len(rows[0]) == 1
                    and (box[2] - box[0] + 1) * (box[3] - box[1] + 1) > 1):
                rect = self.worksheet.fill(box, rows[0][0])
            else:
                rect = self.worksheet.set_block(box[0], box[1], rows,
                                                label='Paste')
        except WorksheetLimitError as e:
            QMessageBox.warning(self, tr('ws_paste_title'), str(e))
            return
        if rect:
            self._select_rect(rect)

    def clear_selection_contents(self):
        idxs = self.selectionModel().selectedIndexes()
        if not idxs:
            return
        rects = [(r.left(), r.top(), r.right(), r.bottom())
                 for r in self.selectionModel().selection()]
        if not rects:
            box = self._selected_box()
            rects = [box]
        rect = self.worksheet.clear(rects, label='Clear')
        if rect:
            self._select_rect(rect)

    def selected_columns(self):
        return sorted({i.column() for i in
                       self.selectionModel().selectedIndexes()})

    def select_all(self):
        model = self.model()
        self._select_rect((0, META_ROWS, model.columnCount() - 1,
                           model.rowCount() - 1), scroll=False)

    def undo(self):
        rect = self.worksheet.undo()
        if rect:
            self._select_rect(rect)

    def redo(self):
        rect = self.worksheet.redo()
        if rect:
            self._select_rect(rect)

    # ── context menus ──────────────────────────────────────────────────

    def _menu_columns(self, logical):
        model = self.model()
        last = model.rowCount() - 1
        cols = set()
        for r in self.selectionModel().selection():
            if r.top() <= META_ROWS and r.bottom() >= last:
                cols.update(range(r.left(), r.right() + 1))
        if logical not in cols:
            self._select_column(logical)
            return [logical]
        return sorted(cols)

    def _menu_rows(self, logical):
        model = self.model()
        last = model.columnCount() - 1
        rows = set()
        for r in self.selectionModel().selection():
            if r.left() <= 0 and r.right() >= last:
                for row in range(max(r.top(), META_ROWS),
                                 r.bottom() + 1):
                    rows.add(row)
        if logical not in rows:
            sel = QItemSelection(model.index(logical, 0),
                                 model.index(logical, last))
            self.selectionModel().select(
                sel, QItemSelectionModel.SelectionFlag.ClearAndSelect)
            return [logical]
        return sorted(rows)

    def _insert_columns(self, at, count):
        try:
            self._after_edit(self.worksheet.insert_columns(at, count))
        except WorksheetLimitError as e:
            QMessageBox.warning(self, tr('ws_insert_column_title'),
                                str(e))

    def _column_boundary(self, header, pos):
        grip = header.style().pixelMetric(
            QStyle.PixelMetric.PM_HeaderGripMargin, None, header)
        if header.count() and abs(
                pos.x() - header.sectionViewportPosition(0)) <= grip:
            return 0
        for i in range(header.count()):
            x = (header.sectionViewportPosition(i)
                 + header.sectionSize(i))
            if abs(pos.x() - x) <= grip:
                return i + 1
        return None

    def _column_menu(self, pos):
        header = self.horizontalHeader()
        logical = header.logicalIndexAt(pos)
        boundary = self._column_boundary(header, pos)
        if boundary is not None:
            menu = QMenu(self)
            menu.addAction(tr('ws_insert_column_here'),
                           lambda: self._insert_columns(boundary, 1))
            menu.exec(header.mapToGlobal(pos))
            return
        if logical < 0:
            return
        cols = self._menu_columns(logical)
        menu = QMenu(self)
        set_as = menu.addMenu(tr('menu_set_as'))
        current = self.worksheet.column(cols[0]).designation
        shared = all(self.worksheet.column(c).designation == current
                     for c in cols)
        for designation, text in DESIGNATION_TEXT.items():
            a = set_as.addAction(_designation_label(designation, text))
            a.setCheckable(True)
            a.setChecked(shared and current == designation)
            a.triggered.connect(
                lambda checked=False, d=designation:
                    self._after_edit(
                        self.worksheet.set_designation(cols, d)))
        menu.addSeparator()
        menu.addAction(tr('ws_insert_column_left'),
                       lambda: self._insert_columns(cols[0], len(cols)))
        menu.addAction(tr('ws_insert_column_right'),
                       lambda: self._insert_columns(cols[-1] + 1,
                                                    len(cols)))
        menu.addAction(tr('ws_add_column'),
                       lambda: self._insert_columns(
                           self.worksheet.column_count, 1))
        delete = menu.addAction(
            tr('ws_delete_column'), lambda: self._after_edit(
                self.worksheet.remove_columns(cols)))
        delete.setEnabled(len(cols) < self.worksheet.column_count)
        menu.addAction(tr('ws_clear_column'), lambda: self._after_edit(
            self.worksheet.clear(
                [(c, META_ROWS, c, self.model().rowCount() - 1)
                 for c in cols],
                label='Clear')))
        menu.exec(header.mapToGlobal(pos))

    def _row_menu(self, pos):
        header = self.verticalHeader()
        logical = header.logicalIndexAt(pos)
        if logical < META_ROWS:
            return
        rows = [r for r in self._menu_rows(logical)]
        if not rows:
            return
        contiguous = rows[-1] - rows[0] + 1 == len(rows)
        runs = [[rows[0]]]
        for r in rows[1:]:
            if r == runs[-1][-1] + 1:
                runs[-1].append(r)
            else:
                runs.append([r])
        menu = QMenu(self)
        ins = menu.addAction(tr('ws_insert_rows'),
                             lambda: self._after_edit(
                                 self.worksheet.insert_rows(
                                     rows[0] - META_ROWS, len(rows))))
        dele = menu.addAction(tr('ws_delete_rows'),
                              lambda: self._after_edit(
                                  self.worksheet.remove_rows(
                                      rows[0] - META_ROWS, len(rows))))
        ins.setEnabled(contiguous)
        dele.setEnabled(contiguous)
        menu.addAction(tr('ws_clear'), lambda: self._after_edit(
            self.worksheet.clear(
                [(0, run[0], self.model().columnCount() - 1, run[-1])
                 for run in runs],
                label='Clear')))
        menu.exec(header.mapToGlobal(pos))

    def _meta_row_menu(self, pos):
        header = self._labels.verticalHeader()
        logical = header.logicalIndexAt(pos)
        if 0 <= logical < META_ROWS:
            self._select_meta_row(logical)
        self._cell_menu(pos, map_from=self._labels.verticalHeader())

    def _cell_menu(self, pos, map_from=None):
        source = map_from if map_from is not None else self.sender()
        if not isinstance(source, QWidget):
            source = self
        menu = QMenu(self)
        menu.addAction(tr('act_cut'), self.cut)
        menu.addAction(tr('act_copy'), self.copy)
        menu.addAction(tr('act_paste'), self.paste)
        menu.addAction(tr('ws_clear'), self.clear_selection_contents)
        menu.exec(source.mapToGlobal(pos))

    def _after_edit(self, rect):
        if rect:
            self._select_rect(rect)
