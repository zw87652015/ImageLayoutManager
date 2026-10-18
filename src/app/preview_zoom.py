"""Qt-free zoom/pan state for the Match Text Size previews.

The base transform centres the image in the view with ``MARGIN`` px of
padding. ``zoom`` multiplies that fit scale; ``pan`` is the widget-pixel
offset of the image centre from its fitted (centred) position.
"""

ZOOM_MIN, ZOOM_MAX, MARGIN = 1.0, 32.0, 8.0


class ZoomPan:
    def __init__(self):
        self.zoom = 1.0
        self.pan = (0.0, 0.0)

    @property
    def fitted(self) -> bool:
        return self.zoom == ZOOM_MIN and self.pan == (0.0, 0.0)

    @staticmethod
    def _fit_scale(view_w, view_h, img_w, img_h):
        return min((view_w - 2 * MARGIN) / img_w, (view_h - 2 * MARGIN) / img_h)

    def _pan_limit(self, view, scaled):
        """Max |pan| on one axis; None means the image fits (pan pinned to 0)."""
        if scaled <= view - 2 * MARGIN:
            return None
        return (scaled - view) / 2 + MARGIN

    def _clamp_pan(self, view_w, view_h, img_w, img_h):
        scale = self._fit_scale(view_w, view_h, img_w, img_h) * self.zoom
        px, py = self.pan
        for axis, (view, scaled) in enumerate(((view_w, img_w * scale),
                                               (view_h, img_h * scale))):
            limit = self._pan_limit(view, scaled)
            value = 0.0 if limit is None else max(-limit, min(limit, self.pan[axis]))
            if axis == 0:
                px = value
            else:
                py = value
        self.pan = (px, py)

    def transform(self, view_w, view_h, img_w, img_h):
        """(scale, left, top) mapping image pixels to widget pixels."""
        if view_w <= 0 or view_h <= 0 or img_w <= 0 or img_h <= 0:
            return 1.0, 0.0, 0.0
        scale = self._fit_scale(view_w, view_h, img_w, img_h) * self.zoom
        left = view_w / 2 - img_w * scale / 2 + self.pan[0]
        top = view_h / 2 - img_h * scale / 2 + self.pan[1]
        return scale, left, top

    def zoom_at(self, px, py, steps, view_w, view_h, img_w, img_h):
        """Zoom by ``1.2 ** steps`` about widget point (px, py)."""
        if view_w <= 0 or view_h <= 0 or img_w <= 0 or img_h <= 0:
            return
        scale, left, top = self.transform(view_w, view_h, img_w, img_h)
        ix, iy = (px - left) / scale, (py - top) / scale   # image point under cursor
        self.zoom = min(ZOOM_MAX, max(ZOOM_MIN, self.zoom * 1.2 ** steps))
        if self.zoom == ZOOM_MIN:
            self.pan = (0.0, 0.0)
            return
        scale = self._fit_scale(view_w, view_h, img_w, img_h) * self.zoom
        # Solve for pan so the same image point stays under (px, py).
        pan_x = px - ix * scale - (view_w / 2 - img_w * scale / 2)
        pan_y = py - iy * scale - (view_h / 2 - img_h * scale / 2)
        self.pan = (pan_x, pan_y)
        self._clamp_pan(view_w, view_h, img_w, img_h)

    def pan_by(self, dx, dy, view_w, view_h, img_w, img_h):
        if view_w <= 0 or view_h <= 0 or img_w <= 0 or img_h <= 0:
            return
        self.pan = (self.pan[0] + dx, self.pan[1] + dy)
        self._clamp_pan(view_w, view_h, img_w, img_h)

    def reset(self):
        self.zoom = 1.0
        self.pan = (0.0, 0.0)
