from PyQt6.QtWidgets import QGraphicsPixmapItem, QGraphicsRectItem, QGraphicsDropShadowEffect, QGraphicsView
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QPixmap
from PyQt6.QtCore import (QObject, QEvent, QTimer, QPointF, QRectF,
                          QElapsedTimer,
                          pyqtSignal, Qt, QVariantAnimation, QEasingCurve)


class DragManager(QObject):
    """Manages animated drag-and-drop of cells with spring physics.

    State machine: IDLE → DRAGGING → ANIMATING → IDLE
    - Ghost item follows mouse with spring-lag interpolation (~60 fps).
    - Drop target highlighted with translucent overlay.
    - On drop: ghost slides to target then swap is emitted.
    - On cancel (Escape / invalid target): ghost springs back to origin.
    - Supports multi-cell drag: N selected cells are moved together.
    """

    swap_requested = pyqtSignal(str, str)  # source_id, target_id (single)
    multi_swap_requested = pyqtSignal(list, list)  # source_ids, target_ids

    # Tuning constants
    SPRING_SMOOTH_TIME = 0.07   # seconds; lower = tighter follow
    GHOST_OPACITY = 0.82
    GHOST_SCALE = 1.05          # Slight lift enlargement (target)
    GHOST_PX_WIDTH = 300        # Capture resolution
    HIGHLIGHT_FILL = QColor(0, 122, 204, 60)
    HIGHLIGHT_BORDER = QColor(0, 122, 204, 180)
    REJECT_FILL = QColor(204, 0, 0, 40)
    REJECT_BORDER = QColor(204, 0, 0, 140)
    TICK_MS = 16                # ~60 fps
    DROP_DURATION_MS = 180
    CANCEL_DURATION_MS = 250
    LIFT_DURATION_MS = 140      # pickup: scale + opacity fade
    SOURCE_DIM_OPACITY = 0.3
    ROTATION_MAX_DEG = 5.0
    ROTATION_VELOCITY_SCALE = 0.008   # deg per (px/s)
    ROTATION_SMOOTH_FACTOR = 0.18     # per-tick rotation lerp
    HIGHLIGHT_FADE_MS = 140

    def __init__(self, scene):
        super().__init__(scene)
        self.scene = scene
        self._active = False
        self._animating = False  # True during drop/cancel animation

        # Source state (multi-cell aware)
        self._source_cell = None          # The cell under the mouse at drag start
        self._source_id = None
        self._source_scene_rect = QRectF()
        self._source_cells = []           # All dragged CellItems (sorted row-major)
        self._source_ids = []             # Their IDs

        # Ghost
        self._ghost = None          # QGraphicsPixmapItem
        self._ghost_scene_pos = QPointF()
        self._ghost_display_w = 0.0
        self._ghost_display_h = 0.0
        self._base_scale = 1.0
        self._ghost_scale_factor = 1.0  # multiplier animated during lift

        # Mouse
        self._mouse_scene_pos = QPointF()
        self._last_mouse_scene_pos = QPointF()

        # Spring physics state
        self._velocity = QPointF(0.0, 0.0)
        self._current_rotation = 0.0
        self._tick_timer = QElapsedTimer()

        # Transient animations (keep refs so GC doesn't kill them)
        self._lift_anims: list = []
        self._highlight_anims: list = []
        self._swap_slide_anims: list = []   # target-cell slide during drop
        self._swap_slide_pairs: list = []   # (item, final_QPointF) to snap on finish

        # Target highlight
        self._highlights = []       # list of QGraphicsRectItems
        self._target_ids = []

        # Spring timer
        self._timer = QTimer(self)
        self._timer.setInterval(self.TICK_MS)
        self._timer.timeout.connect(self._spring_tick)

        # Drop / cancel animation
        self._anim = None
        self._anim_start = QPointF()
        self._anim_end = QPointF()

        # View state saved during drag
        self._saved_drag_mode = None
        self._view = None  # reference to the view during drag

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    @property
    def is_active(self):
        return self._active

    def start_drag(self, cell_item, scene_pos):
        """Begin a drag operation on *cell_item* (and all other selected cells)."""
        if self._active or self._animating:
            return

        from src.canvas.cell_item import CellItem

        self._active = True
        self._animating = False
        self._source_cell = cell_item
        self._source_id = cell_item.cell_id
        self._mouse_scene_pos = scene_pos

        self._source_scene_rect = QRectF(
            cell_item.pos().x(), cell_item.pos().y(),
            cell_item.rect().width(), cell_item.rect().height(),
        )

        # Collect all selected non-label cells, sorted by position (row-major)
        selected = [
            i for i in self.scene.selectedItems()
            if isinstance(i, CellItem) and not i.is_label_cell
        ]
        if not selected or cell_item not in selected:
            selected = [cell_item]
        selected.sort(key=lambda i: (i.pos().y(), i.pos().x()))
        self._source_cells = selected
        self._source_ids = [i.cell_id for i in selected]

        # Create ghost BEFORE dimming sources (so capture is at full opacity)
        self._create_ghost(cell_item, scene_pos)

        # Animate: fade sources, lift ghost (scale + opacity)
        self._start_lift_animations()

        # Release any implicit mouse grab the cell item may hold
        cell_item.ungrabMouse()

        # Install event filter on the viewport and disable rubber-band
        views = self.scene.views()
        if views:
            self._view = views[0]
            self._saved_drag_mode = self._view.dragMode()
            self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
            vp = self._view.viewport()
            vp.setMouseTracking(True)
            vp.installEventFilter(self)
            self._view.setCursor(Qt.CursorShape.ClosedHandCursor)

        self._tick_timer.start()
        self._last_mouse_scene_pos = QPointF(scene_pos)
        self._velocity = QPointF(0.0, 0.0)
        self._current_rotation = 0.0
        self._timer.start()

    # ------------------------------------------------------------------
    # Ghost creation
    # ------------------------------------------------------------------

    def _create_ghost(self, cell_item, scene_pos):
        cell_w = self._source_scene_rect.width()
        cell_h = self._source_scene_rect.height()
        if cell_w <= 0 or cell_h <= 0:
            return

        aspect = cell_h / cell_w
        cap_w = self.GHOST_PX_WIDTH
        cap_h = max(1, int(cap_w * aspect))

        pixmap = QPixmap(cap_w, cap_h)
        pixmap.fill(Qt.GlobalColor.transparent)

        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.scene.render(
            painter,
            QRectF(0, 0, cap_w, cap_h),
            self._source_scene_rect,
        )
        painter.end()

        self._ghost = QGraphicsPixmapItem(pixmap)
        self._ghost.setZValue(1000)
        # Start at full opacity; lift animation will fade to GHOST_OPACITY
        self._ghost.setOpacity(1.0)

        # Scale so the ghost matches cell size (pre-lift, scale_factor=1.0)
        self._base_scale = cell_w / cap_w
        self._ghost_scale_factor = 1.0
        self._ghost.setScale(self._base_scale * self._ghost_scale_factor)

        # Rotate/scale about ghost center (for tilt + lift).
        # NOTE: origin is in LOCAL pixmap units (pre-scale). Visible center in
        # scene coords = pos + (cap_w/2, cap_h/2) regardless of scale.
        self._ghost_origin_offset = QPointF(cap_w / 2.0, cap_h / 2.0)
        self._ghost.setTransformOriginPoint(self._ghost_origin_offset)

        self._ghost_display_w = cell_w * self.GHOST_SCALE
        self._ghost_display_h = cell_h * self.GHOST_SCALE

        # Centre on mouse: pos = mouse - origin_offset (in local pixmap units)
        self._ghost_scene_pos = QPointF(
            scene_pos.x() - self._ghost_origin_offset.x(),
            scene_pos.y() - self._ghost_origin_offset.y(),
        )
        self._ghost.setPos(self._ghost_scene_pos)

        # Drop shadow
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(18)
        shadow.setColor(QColor(0, 0, 0, 70))
        shadow.setOffset(3, 3)
        self._ghost.setGraphicsEffect(shadow)

        self.scene.addItem(self._ghost)

    # ------------------------------------------------------------------
    # Lift (pickup) animation
    # ------------------------------------------------------------------

    def _start_lift_animations(self):
        # Ghost scale: 1.0 -> GHOST_SCALE
        scale_anim = QVariantAnimation(self)
        scale_anim.setDuration(self.LIFT_DURATION_MS)
        scale_anim.setStartValue(1.0)
        scale_anim.setEndValue(self.GHOST_SCALE)
        scale_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        scale_anim.valueChanged.connect(self._on_lift_scale)
        scale_anim.finished.connect(lambda a=scale_anim: self._discard_lift_anim(a))
        scale_anim.start()
        self._lift_anims.append(scale_anim)

        # Ghost opacity: 1.0 -> GHOST_OPACITY
        op_anim = QVariantAnimation(self)
        op_anim.setDuration(self.LIFT_DURATION_MS)
        op_anim.setStartValue(1.0)
        op_anim.setEndValue(self.GHOST_OPACITY)
        op_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        op_anim.valueChanged.connect(
            lambda v: self._ghost and self._ghost.setOpacity(float(v))
        )
        op_anim.finished.connect(lambda a=op_anim: self._discard_lift_anim(a))
        op_anim.start()
        self._lift_anims.append(op_anim)

        # Source cells opacity: 1.0 -> SOURCE_DIM_OPACITY
        for item in self._source_cells:
            src_anim = QVariantAnimation(self)
            src_anim.setDuration(self.LIFT_DURATION_MS)
            src_anim.setStartValue(1.0)
            src_anim.setEndValue(self.SOURCE_DIM_OPACITY)
            src_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
            src_anim.valueChanged.connect(
                lambda v, it=item: self._safe_set_opacity(it, float(v))
            )
            src_anim.finished.connect(lambda a=src_anim: self._discard_lift_anim(a))
            src_anim.start()
            self._lift_anims.append(src_anim)

    def _on_lift_scale(self, v):
        if not self._ghost:
            return
        self._ghost_scale_factor = float(v)
        self._ghost.setScale(self._base_scale * self._ghost_scale_factor)

    def _discard_lift_anim(self, anim):
        try:
            self._lift_anims.remove(anim)
        except ValueError:
            pass
        anim.deleteLater()

    @staticmethod
    def _safe_set_opacity(item, v):
        try:
            item.setOpacity(v)
        except RuntimeError:
            pass

    # ------------------------------------------------------------------
    # Spring physics (timer-driven) — critically damped + rotation tilt
    # ------------------------------------------------------------------

    def _spring_tick(self):
        if not self._ghost or not self._active or self._animating:
            return

        # Real dt in seconds (clamped)
        dt_ms = self._tick_timer.restart()
        dt = dt_ms / 1000.0
        if dt <= 0 or dt > 0.1:
            dt = self.TICK_MS / 1000.0

        target = QPointF(
            self._mouse_scene_pos.x() - self._ghost_origin_offset.x(),
            self._mouse_scene_pos.y() - self._ghost_origin_offset.y(),
        )

        # Critically damped spring (Game Programming Gems 4, Ch 1.10)
        omega = 2.0 / max(self.SPRING_SMOOTH_TIME, 1e-4)
        x = omega * dt
        exp_factor = 1.0 / (1.0 + x + 0.48 * x * x + 0.235 * x * x * x)

        change_x = self._ghost_scene_pos.x() - target.x()
        change_y = self._ghost_scene_pos.y() - target.y()
        temp_x = (self._velocity.x() + omega * change_x) * dt
        temp_y = (self._velocity.y() + omega * change_y) * dt

        new_vx = (self._velocity.x() - omega * temp_x) * exp_factor
        new_vy = (self._velocity.y() - omega * temp_y) * exp_factor
        new_x = target.x() + (change_x + temp_x) * exp_factor
        new_y = target.y() + (change_y + temp_y) * exp_factor

        self._velocity = QPointF(new_vx, new_vy)
        self._ghost_scene_pos = QPointF(new_x, new_y)
        self._ghost.setPos(self._ghost_scene_pos)

        # Mouse velocity (px/s) for tilt
        mvx = (self._mouse_scene_pos.x() - self._last_mouse_scene_pos.x()) / dt
        self._last_mouse_scene_pos = QPointF(self._mouse_scene_pos)

        # Target rotation clamped, smoothed toward target
        target_rot = mvx * self.ROTATION_VELOCITY_SCALE
        if target_rot > self.ROTATION_MAX_DEG:
            target_rot = self.ROTATION_MAX_DEG
        elif target_rot < -self.ROTATION_MAX_DEG:
            target_rot = -self.ROTATION_MAX_DEG
        self._current_rotation += (target_rot - self._current_rotation) * self.ROTATION_SMOOTH_FACTOR
        self._ghost.setRotation(self._current_rotation)

    # ------------------------------------------------------------------
    # Target detection & highlighting
    # ------------------------------------------------------------------

    def _get_all_cells_sorted(self):
        """Return all non-label CellItems sorted in row-major order."""
        from src.canvas.cell_item import CellItem
        items = [i for i in self.scene.cell_items.values() if not i.is_label_cell]
        items.sort(key=lambda i: (i.pos().y(), i.pos().x()))
        return items

    def _find_target_cell(self, scene_pos):
        """Find the single cell under the cursor (not one of the sources)."""
        from src.canvas.cell_item import CellItem
        for item in self.scene.items(scene_pos):
            if (isinstance(item, CellItem)
                    and not item.is_label_cell
                    and item.cell_id not in self._source_ids):
                return item
        return None

    def _get_cell_model(self, cell_id):
        """Return the Cell data model for a given cell_id, or None."""
        project = getattr(self.scene, 'project', None)
        if project and hasattr(project, 'find_cell_by_id'):
            return project.find_cell_by_id(cell_id)
        return None

    def _detect_source_shape(self):
        """Detect if sources form a row, column, or arbitrary selection.
        Returns ('row', row_index, sorted_col_offsets),
                ('col', col_index, sorted_row_offsets), or
                ('arbitrary', None, None).
        """
        models = [self._get_cell_model(cid) for cid in self._source_ids]
        if any(m is None for m in models):
            return 'arbitrary', None, None

        row_indices = {m.row_index for m in models}
        col_indices = {m.col_index for m in models}

        if len(row_indices) == 1:
            # All sources in the same row → row selection
            row_idx = next(iter(row_indices))
            col_offsets = sorted(m.col_index for m in models)
            # Normalize to relative offsets from the minimum
            min_col = col_offsets[0]
            return 'row', row_idx, [c - min_col for c in col_offsets]

        if len(col_indices) == 1:
            # All sources in the same column → column selection
            col_idx = next(iter(col_indices))
            row_offsets = sorted(m.row_index for m in models)
            min_row = row_offsets[0]
            return 'col', col_idx, [r - min_row for r in row_offsets]

        return 'arbitrary', None, None

    def _find_target_cells(self, scene_pos):
        """Find N target cells starting from the cell under cursor.
        Preserves row/column shape of the source selection when possible.
        Returns (target_items, valid) where valid=True if placement is possible."""
        n = len(self._source_ids)
        anchor = self._find_target_cell(scene_pos)
        if not anchor:
            return [], False

        if n == 1:
            return [anchor], True

        shape, shape_idx, offsets = self._detect_source_shape()
        anchor_model = self._get_cell_model(anchor.cell_id)

        if shape == 'row' and anchor_model is not None:
            # Try to place sources into the same row as the anchor, preserving
            # relative column offsets.
            anchor_col = anchor_model.col_index
            # Build id->item map for fast lookup
            id_to_item = {cid: item for cid, item in self.scene.cell_items.items()
                          if not item.is_label_cell}
            targets = []
            for rel_col in offsets:
                target_col = anchor_col + rel_col
                # Find a cell in the anchor's row with this col_index
                candidate = None
                for cid, item in id_to_item.items():
                    m = self._get_cell_model(cid)
                    if m and m.row_index == anchor_model.row_index and m.col_index == target_col:
                        candidate = item
                        break
                if candidate is None:
                    # Column doesn't exist in target row → fall through to arbitrary
                    targets = []
                    break
                targets.append(candidate)

            if targets:
                target_ids = {t.cell_id for t in targets}
                source_ids = set(self._source_ids)
                if target_ids & source_ids:
                    if target_ids != source_ids:
                        return targets, False
                    return [], False
                return targets, True

        if shape == 'col' and anchor_model is not None:
            # Try to place sources into the same column as the anchor, preserving
            # relative row offsets.
            anchor_row = anchor_model.row_index
            id_to_item = {cid: item for cid, item in self.scene.cell_items.items()
                          if not item.is_label_cell}
            targets = []
            for rel_row in offsets:
                target_row = anchor_row + rel_row
                candidate = None
                for cid, item in id_to_item.items():
                    m = self._get_cell_model(cid)
                    if m and m.row_index == target_row and m.col_index == anchor_model.col_index:
                        candidate = item
                        break
                if candidate is None:
                    targets = []
                    break
                targets.append(candidate)

            if targets:
                target_ids = {t.cell_id for t in targets}
                source_ids = set(self._source_ids)
                if target_ids & source_ids:
                    if target_ids != source_ids:
                        return targets, False
                    return [], False
                return targets, True

        # Arbitrary / fallback: consecutive row-major placement
        all_cells = self._get_all_cells_sorted()
        id_to_idx = {i.cell_id: idx for idx, i in enumerate(all_cells)}
        anchor_idx = id_to_idx.get(anchor.cell_id)
        if anchor_idx is None:
            return [], False

        targets = []
        for offset in range(n):
            idx = anchor_idx + offset
            if idx >= len(all_cells):
                return [anchor], False
            targets.append(all_cells[idx])

        target_ids = {t.cell_id for t in targets}
        source_ids = set(self._source_ids)
        if target_ids & source_ids:
            if target_ids != source_ids:
                return targets, False
            return [], False

        return targets, True

    def _update_highlights(self, targets, valid):
        """Show highlight rectangles on target cells with a smooth crossfade."""
        new_ids = [t.cell_id for t in targets]
        if new_ids == self._target_ids:
            return
        self._target_ids = new_ids

        # Fade out old highlights
        for h in self._highlights:
            self._fade_highlight(h, h.opacity(), 0.0, remove_on_finish=True)
        self._highlights.clear()

        fill = self.HIGHLIGHT_FILL if valid else self.REJECT_FILL
        border = self.HIGHLIGHT_BORDER if valid else self.REJECT_BORDER

        for t in targets:
            h = QGraphicsRectItem(t.rect())
            h.setPos(t.pos())
            h.setZValue(999)
            h.setBrush(QBrush(fill))
            pen = QPen(border, 2)
            pen.setCosmetic(True)
            h.setPen(pen)
            h.setOpacity(0.0)
            self.scene.addItem(h)
            self._highlights.append(h)
            self._fade_highlight(h, 0.0, 1.0, remove_on_finish=False)

    def _fade_highlight(self, item, v_from, v_to, remove_on_finish):
        anim = QVariantAnimation(self)
        anim.setDuration(self.HIGHLIGHT_FADE_MS)
        anim.setStartValue(float(v_from))
        anim.setEndValue(float(v_to))
        anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        anim.valueChanged.connect(
            lambda v, it=item: self._safe_set_opacity(it, float(v))
        )

        def _finish(it=item, a=anim):
            if remove_on_finish:
                try:
                    self.scene.removeItem(it)
                except RuntimeError:
                    pass
            try:
                self._highlight_anims.remove(a)
            except ValueError:
                pass
            a.deleteLater()

        anim.finished.connect(_finish)
        self._highlight_anims.append(anim)
        anim.start()

    # ------------------------------------------------------------------
    # Mouse event handlers (called via eventFilter)
    # ------------------------------------------------------------------

    def _on_mouse_move(self, scene_pos):
        self._mouse_scene_pos = scene_pos
        targets, valid = self._find_target_cells(scene_pos)
        if targets:
            self._update_highlights(targets, valid)
        else:
            # Clear highlights when not over any cell
            self._update_highlights([], True)

    def _on_mouse_release(self, scene_pos):
        self._timer.stop()
        self._animating = True

        # Remove highlights immediately
        for h in self._highlights:
            self.scene.removeItem(h)
        self._highlights.clear()
        self._target_ids = []

        targets, valid = self._find_target_cells(scene_pos)
        if valid and targets:
            self._animate_drop(targets)
        else:
            self._animate_cancel()

    # ------------------------------------------------------------------
    # Drop / cancel animations (QVariantAnimation on QPointF)
    # ------------------------------------------------------------------

    def _animate_drop(self, target_cells):
        first_target_cell = target_cells[0]
        # Target: ghost visible center lands on target cell center.
        # With center origin, pos = target_center - origin_offset.
        tw = first_target_cell.rect().width()
        th = first_target_cell.rect().height()
        tx = first_target_cell.pos().x() + tw / 2.0
        ty = first_target_cell.pos().y() + th / 2.0
        self._anim_start = QPointF(self._ghost_scene_pos)
        self._anim_end = QPointF(
            tx - self._ghost_origin_offset.x(),
            ty - self._ghost_origin_offset.y(),
        )

        source_ids = list(self._source_ids)
        target_ids = [t.cell_id for t in target_cells]

        # Animate each target cell sliding to the matching source cell's position
        # (the "other half" of the swap). Source cells themselves stay dimmed in
        # place — the ghost represents them visually until drop finishes.
        self._swap_slide_anims = []
        self._swap_slide_pairs = []
        for src_cell, tgt_cell in zip(self._source_cells, target_cells):
            start_pos = QPointF(tgt_cell.pos())
            end_pos = QPointF(src_cell.pos())
            self._swap_slide_pairs.append((tgt_cell, end_pos))

            slide = QVariantAnimation(self)
            slide.setDuration(self.DROP_DURATION_MS)
            slide.setStartValue(0.0)
            slide.setEndValue(1.0)
            slide.setEasingCurve(QEasingCurve.Type.OutCubic)
            slide.valueChanged.connect(
                lambda v, it=tgt_cell, s=start_pos, e=end_pos:
                self._safe_set_pos(it, s.x() + (e.x() - s.x()) * float(v),
                                       s.y() + (e.y() - s.y()) * float(v))
            )
            slide.start()
            self._swap_slide_anims.append(slide)

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self.DROP_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(lambda: self._on_drop_finished(source_ids, target_ids))
        self._anim.start()

    @staticmethod
    def _safe_set_pos(item, x, y):
        try:
            item.setPos(x, y)
        except RuntimeError:
            pass

    def _animate_cancel(self):
        # Return ghost visible center to source cell center.
        sx = self._source_scene_rect.x() + self._source_scene_rect.width() / 2.0
        sy = self._source_scene_rect.y() + self._source_scene_rect.height() / 2.0
        self._anim_start = QPointF(self._ghost_scene_pos)
        self._anim_end = QPointF(
            sx - self._ghost_origin_offset.x(),
            sy - self._ghost_origin_offset.y(),
        )

        self._anim = QVariantAnimation(self)
        self._anim.setStartValue(0.0)
        self._anim.setEndValue(1.0)
        self._anim.setDuration(self.CANCEL_DURATION_MS)
        self._anim.setEasingCurve(QEasingCurve.Type.OutBack)
        self._anim.valueChanged.connect(self._on_anim_value)
        self._anim.finished.connect(self._cleanup)
        self._anim.start()

    def _on_anim_value(self, t):
        if self._ghost:
            x = self._anim_start.x() + (self._anim_end.x() - self._anim_start.x()) * t
            y = self._anim_start.y() + (self._anim_end.y() - self._anim_start.y()) * t
            self._ghost.setPos(x, y)

    def _on_drop_finished(self, source_ids, target_ids):
        # Snap each target cell to its exact final slide position before the
        # data-level swap fires, so refresh doesn't cause a visible blink.
        for item, final_pos in self._swap_slide_pairs:
            self._safe_set_pos(item, final_pos.x(), final_pos.y())
        self._cleanup()
        if len(source_ids) == 1 and len(target_ids) == 1:
            self.swap_requested.emit(source_ids[0], target_ids[0])
        else:
            self.multi_swap_requested.emit(source_ids, target_ids)

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    def _cleanup(self):
        self._timer.stop()

        if self._anim:
            self._anim.stop()
            self._anim.deleteLater()
            self._anim = None

        # Stop any in-flight lift animations
        for a in list(self._lift_anims):
            a.stop()
            a.deleteLater()
        self._lift_anims.clear()

        # Stop any in-flight highlight animations
        for a in list(self._highlight_anims):
            a.stop()
            a.deleteLater()
        self._highlight_anims.clear()

        # Stop any in-flight target-slide animations
        for a in list(self._swap_slide_anims):
            a.stop()
            a.deleteLater()
        self._swap_slide_anims.clear()
        self._swap_slide_pairs.clear()

        if self._ghost:
            self.scene.removeItem(self._ghost)
            self._ghost = None

        for h in self._highlights:
            try:
                self.scene.removeItem(h)
            except RuntimeError:
                pass
        self._highlights.clear()

        # Restore opacity on all source cells
        for item in self._source_cells:
            try:
                item.setOpacity(1.0)
            except RuntimeError:
                pass  # item was deleted

        if self._view:
            vp = self._view.viewport()
            vp.removeEventFilter(self)
            self._view.unsetCursor()
            if self._saved_drag_mode is not None:
                self._view.setDragMode(self._saved_drag_mode)
                self._saved_drag_mode = None
            self._view = None

        self._active = False
        self._animating = False
        self._source_cell = None
        self._source_id = None
        self._source_cells = []
        self._source_ids = []
        self._target_ids = []
        self._ghost_scene_pos = QPointF()
        self._mouse_scene_pos = QPointF()

    # ------------------------------------------------------------------
    # Event filter (installed on the QGraphicsView during drag)
    # ------------------------------------------------------------------

    def eventFilter(self, obj, event):
        if not self._active:
            return False

        etype = event.type()

        # During animation, only block moves — press/release pass through so
        # other items (add-row/column buttons, etc.) remain clickable.
        if self._animating:
            return etype == QEvent.Type.MouseMove

        if etype == QEvent.Type.MouseMove:
            if self._view:
                scene_pos = self._view.mapToScene(event.position().toPoint())
                self._on_mouse_move(scene_pos)
            return True

        if etype == QEvent.Type.MouseButtonRelease:
            if event.button() == Qt.MouseButton.LeftButton:
                if self._view:
                    scene_pos = self._view.mapToScene(event.position().toPoint())
                    self._on_mouse_release(scene_pos)
                return True

        if etype == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_Escape:
                self._timer.stop()
                self._animating = True
                for h in self._highlights:
                    self.scene.removeItem(h)
                self._highlights.clear()
                self._target_ids = []
                self._animate_cancel()
                return True

        return False
