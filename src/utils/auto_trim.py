import os
from collections import Counter

from PIL import Image, ImageChops

TOLERANCE = 24
BORDER_UNIFORM = 0.6
PAD_FRAC = 0.01
MIN_CHANGE = 0.005


def _flatten(img):
    rgba = img.convert("RGBA")
    white = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
    return Image.alpha_composite(white, rgba).convert("RGB")


def _border_pixels(region):
    w, h = region.size
    px = region.load()
    coords = [(x, 0) for x in range(w)] + [(x, h - 1) for x in range(w)]
    coords += [(0, y) for y in range(1, h - 1)] + [(w - 1, y) for y in range(1, h - 1)]
    return coords, px


def _background(region):
    coords, px = _border_pixels(region)
    bins = Counter(tuple(c >> 4 for c in px[xy]) for xy in coords)
    best = bins.most_common(1)[0][0]
    members = [px[xy] for xy in coords if tuple(c >> 4 for c in px[xy]) == best]
    return tuple(round(sum(channel) / len(members)) for channel in zip(*members))


def _mask(region, background):
    diff = ImageChops.difference(region, Image.new("RGB", region.size, background))
    r, g, b = diff.split()
    lit = ImageChops.lighter(ImageChops.lighter(r, g), b)
    return lit.point(lambda v: 255 if v > TOLERANCE else 0)


def _border_empty_share(mask):
    coords, px = _border_pixels(mask)
    empty = sum(1 for xy in coords if px[xy] == 0)
    return empty / len(coords)


def content_box(img, crop=(0.0, 0.0, 1.0, 1.0)):
    cl, ct, cr, cb = crop
    rgb = _flatten(img)
    full_w, full_h = rgb.size
    x0 = max(0, min(full_w - 1, round(cl * full_w)))
    x1 = max(x0 + 1, min(full_w, round(cr * full_w)))
    y0 = max(0, min(full_h - 1, round(ct * full_h)))
    y1 = max(y0 + 1, min(full_h, round(cb * full_h)))
    region = rgb.crop((x0, y0, x1, y1))
    w, h = region.size
    mask = _mask(region, _background(region))
    if _border_empty_share(mask) < BORDER_UNIFORM:
        return None
    bbox = mask.getbbox()
    if bbox is None:
        return None
    bx0, by0, bx1, by1 = bbox
    pad = max(2, round(PAD_FRAC * max(bx1 - bx0, by1 - by0)))
    bx0, by0 = max(0, bx0 - pad), max(0, by0 - pad)
    bx1, by1 = min(w, bx1 + pad), min(h, by1 + pad)
    left = cl + bx0 / w * (cr - cl)
    top = ct + by0 / h * (cb - ct)
    right = cl + bx1 / w * (cr - cl)
    bottom = ct + by1 / h * (cb - ct)
    moved = (left - cl, top - ct, cr - right, cb - bottom)
    if all(m < MIN_CHANGE for m in moved):
        return None
    return (round(left, 6), round(top, 6), round(right, 6), round(bottom, 6))


def load_trim_image(path, max_size=1600):
    if not path or not os.path.isfile(path):
        return None
    ext = os.path.splitext(path)[1].lower()
    try:
        if ext in (".svg", ".pdf", ".eps"):
            from PyQt6.QtGui import QImage
            from src.utils.image_proxy import ThumbnailWorker
            worker = ThumbnailWorker(path, max_size, None)
            qimage = worker._load_svg() if ext == ".svg" else worker._load_pdf()
            if qimage is None or qimage.isNull():
                return None
            qimage = qimage.convertToFormat(QImage.Format.Format_RGBA8888)
            bits = qimage.constBits()
            bits.setsize(qimage.sizeInBytes())
            return Image.frombuffer("RGBA", (qimage.width(), qimage.height()), bytes(bits),
                                    "raw", "RGBA", qimage.bytesPerLine(), 1).copy()
        with Image.open(path) as src:
            img = src.convert("RGBA")
        img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)
        return img.copy()
    except Exception:
        return None
