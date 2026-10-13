"""Tile geometry for PictogramCombo (Qt-free)."""


def row_width(count, tile_w, gap=4):
    if count <= 0:
        return 0
    return count * tile_w + gap * (count - 1)


def tile_rects(width, count, *, min_w=28, max_w=44, gap=4, height=30):
    """(x, y, w, h) per tile, left-aligned from x = 0."""
    if count <= 0:
        return []
    tile_w = (width - gap * (count - 1)) / count
    tile_w = min(max_w, max(min_w, tile_w))
    return [(i * (tile_w + gap), 0.0, tile_w, float(height)) for i in range(count)]


def tile_at(x, y, rects):
    """Index of the tile containing (x, y), or -1. Left/top edges are inside."""
    for i, (rx, ry, rw, rh) in enumerate(rects):
        if rx <= x < rx + rw and ry <= y < ry + rh:
            return i
    return -1
