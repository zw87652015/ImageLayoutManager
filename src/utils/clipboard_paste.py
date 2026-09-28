"""Clipboard-paste helpers for images and plain text.

No widgets or dialogs here — ``read_clipboard`` interprets a
``QMimeData``, ``store_image`` persists a bitmap into the figpack
cache's ``pasted_images`` store (content-addressed), ``image_matches``
decides whether a payload duplicates a cell's existing image, and
``relocate_pasted_images`` copies pasted files into a ``.figlayout``
sidecar ``<name>_assets/`` folder on save.
"""

from __future__ import annotations

import hashlib
import io
import os
import posixpath
import re
import shutil
import zipfile
from dataclasses import dataclass
from typing import Optional
from xml.etree import ElementTree

from PyQt6.QtCore import QMimeData
from PyQt6.QtGui import QImage

IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif",
    ".webp", ".svg", ".pdf", ".eps",
}

# PowerPoint puts the full-resolution picture (plus crop info) in a GVML
# zip while the plain bitmap is only a small preview.
GVML_FORMAT = 'application/x-qt-windows-mime;value="Art::GVML ClipFormat"'

# Raw clipboard formats worth decoding when no original is available.
_RASTER_FORMATS = (
    'application/x-qt-windows-mime;value="PNG"', "image/png",
    'application/x-qt-windows-mime;value="JFIF"', "image/jpeg",
)

_R_EMBED = "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _read_office_picture(mime: QMimeData):
    """Extract the original picture from a GVML clipboard payload.

    Returns ``(image, image_data, image_suffix)`` — a cropped/decoded
    QImage, or original encoded bytes + suffix, or ``None`` when the
    payload isn't a single decodable picture.
    """
    if GVML_FORMAT not in mime.formats():
        return None
    try:
        zf = zipfile.ZipFile(io.BytesIO(bytes(mime.data(GVML_FORMAT))))
        drawing = zf.read("clipboard/drawings/drawing1.xml")
        rels_xml = zf.read("clipboard/drawings/_rels/drawing1.xml.rels")
        rels_root = ElementTree.fromstring(rels_xml)
        root = ElementTree.fromstring(drawing)
    except (zipfile.BadZipFile, KeyError, OSError, ElementTree.ParseError):
        return None
    rels = {}
    for rel in rels_root.iter():
        if _local_name(rel.tag) == "Relationship":
            rels[rel.get("Id")] = rel.get("Target")

    def _resolve(rid):
        target = rels.get(rid)
        if not target:
            return None
        return posixpath.normpath(
            posixpath.join("clipboard/drawings", target))

    pics = [e for e in root.iter() if _local_name(e.tag) == "pic"]
    if len(pics) != 1:
        return None
    pic = pics[0]
    blip = src_rect = svg_blip = None
    for e in pic.iter():
        name = _local_name(e.tag)
        if name == "blip" and blip is None:
            blip = e
        elif name == "srcRect" and src_rect is None:
            src_rect = e
        elif name == "svgBlip" and svg_blip is None:
            svg_blip = e
    if blip is None:
        return None

    def _crop_fractions():
        if src_rect is None:
            return None
        vals = []
        for attr in ("l", "t", "r", "b"):
            try:
                vals.append(max(0.0, float(src_rect.get(attr, 0.0))))
            except (TypeError, ValueError):
                vals.append(0.0)
        return vals if any(v > 0 for v in vals) else None

    crop = _crop_fractions()

    if svg_blip is not None and crop is None:
        member = _resolve(svg_blip.get(_R_EMBED))
        if member is None:
            return None
        try:
            return None, zf.read(member), ".svg"
        except KeyError:
            return None

    member = _resolve(blip.get(_R_EMBED))
    if member is None:
        return None
    try:
        media = zf.read(member)
    except KeyError:
        return None
    image = QImage.fromData(media)
    if image.isNull():
        return None
    if crop is not None:
        l, t, r, b = crop
        w, h = image.width(), image.height()
        rect = image.rect().adjusted(
            round(w * l / 100000), round(h * t / 100000),
            -round(w * r / 100000), -round(h * b / 100000))
        cropped = image.copy(rect)
        if cropped.isNull():
            return None
        return cropped, None, None
    suffix = os.path.splitext(member)[1].lower()
    if suffix == ".jpeg":
        suffix = ".jpg"
    return image, media, suffix


def _largest_bitmap(mime: QMimeData) -> Optional[QImage]:
    best = None
    if mime.hasImage():
        image = QImage(mime.imageData())
        if not image.isNull():
            best = image
    for fmt in _RASTER_FORMATS:
        if fmt not in mime.formats():
            continue
        image = QImage.fromData(mime.data(fmt))
        if not image.isNull() and (
                best is None
                or image.width() * image.height()
                > best.width() * best.height()):
            best = image
    return best


@dataclass
class ClipboardContent:
    """What the clipboard offers, reduced to supported payload kinds.

    Excel/PowerPoint put both a bitmap and plain text on the clipboard
    for text copies; ``preferred`` then reports ``"text"`` so Ctrl+V
    pastes text while the bitmap stays reachable via the cell menu.
    """
    image: Optional[QImage] = None
    image_path: Optional[str] = None
    text: Optional[str] = None
    # True when the clipboard only links a web image (<img> in HTML, no
    # bitmap/file payload). Purely a hint flag — the HTML is never
    # fetched or used as content.
    web_image_link: bool = False
    # Original encoded bytes (e.g. the GVML media member) to store
    # verbatim instead of re-encoding; ``image`` still holds the decoded
    # QImage for comparison/display.
    image_data: Optional[bytes] = None
    image_suffix: Optional[str] = None

    @property
    def has_image(self) -> bool:
        return bool(self.image_path) or (
            self.image is not None and not self.image.isNull()) \
            or bool(self.image_data)

    @property
    def preferred(self) -> Optional[str]:
        if self.image_path:
            return "image"
        has_bitmap = (self.image is not None
                      and not self.image.isNull()) or bool(self.image_data)
        if has_bitmap and not self.text:
            return "image"
        if self.text:
            return "text"
        if has_bitmap:
            return "image"
        return None


def read_clipboard(mime: Optional[QMimeData]) -> ClipboardContent:
    """Classify a clipboard payload; rich formats are never used."""
    content = ClipboardContent()
    if mime is None:
        return content
    urls = mime.urls() if mime.hasUrls() else []
    if len(urls) == 1 and urls[0].isLocalFile():
        path = urls[0].toLocalFile()
        if (os.path.isfile(path)
                and os.path.splitext(path)[1].lower() in IMAGE_EXTENSIONS):
            content.image_path = path
    if content.image_path is None:
        office = _read_office_picture(mime)
        if office is not None:
            image, data, suffix = office
            if image is not None and not image.isNull():
                content.image = image
            content.image_data = data
            content.image_suffix = suffix
        else:
            content.image = _largest_bitmap(mime)
    if mime.hasText():
        text = mime.text().replace("\r\n", "\n").replace("\r", "\n")
        text = text.rstrip()
        if text.strip():
            content.text = text
    if not content.has_image and mime.hasHtml() \
            and re.search(r"<img\b", mime.html(), re.I):
        content.web_image_link = True
    return content


def store_image(image: QImage, root: str) -> str:
    """Write *image* as PNG under *root*, content-addressed; returns the
    absolute path. Identical pixels reuse the existing file."""
    argb = image.convertToFormat(QImage.Format.Format_ARGB32)
    digest = hashlib.sha256(
        argb.bits().asstring(argb.sizeInBytes())
        + argb.width().to_bytes(8, "little")
        + argb.height().to_bytes(8, "little")
    ).hexdigest()[:16]
    path = os.path.join(root, f"pasted-{digest}.png")
    if not os.path.exists(path):
        os.makedirs(root, exist_ok=True)
        argb.save(path, "PNG")
    return os.path.abspath(path)


def store_clipboard_image(content: ClipboardContent, root: str) -> str:
    """Store a clipboard image payload; original bytes are kept verbatim."""
    if content.image_data:
        digest = hashlib.sha256(content.image_data).hexdigest()[:16]
        path = os.path.join(
            root, f"pasted-{digest}{content.image_suffix or '.png'}")
        if not os.path.exists(path):
            os.makedirs(root, exist_ok=True)
            with open(path, "wb") as fh:
                fh.write(content.image_data)
        return os.path.abspath(path)
    return store_image(content.image, root)


def _argb(image: QImage) -> QImage:
    return image.convertToFormat(QImage.Format.Format_ARGB32)


def image_matches(existing_path: Optional[str],
                  content: ClipboardContent) -> bool:
    """True when *content* duplicates the image at *existing_path*."""
    if not existing_path or not os.path.isfile(existing_path):
        return False
    if content.image_path:
        if os.path.normcase(os.path.abspath(existing_path)) == \
                os.path.normcase(os.path.abspath(content.image_path)):
            return True
        try:
            if _files_identical(existing_path, content.image_path):
                return True
        except OSError:
            pass
        a = QImage(existing_path)
        b = QImage(content.image_path)
        if a.isNull() or b.isNull():
            return False
        return a.size() == b.size() and _argb(a) == _argb(b)
    if content.image is None and content.image_data:
        try:
            with open(existing_path, "rb") as fh:
                return fh.read() == content.image_data
        except OSError:
            return False
    if content.image is not None and not content.image.isNull():
        existing = QImage(existing_path)
        if existing.isNull():
            return False
        if existing.size() != content.image.size():
            return False
        return _argb(existing) == _argb(content.image)
    return False


def _files_identical(a: str, b: str) -> bool:
    if os.path.getsize(a) != os.path.getsize(b):
        return False
    h1, h2 = hashlib.sha256(), hashlib.sha256()
    with open(a, "rb") as fa, open(b, "rb") as fb:
        for chunk in iter(lambda: fa.read(1024 * 1024), b""):
            h1.update(chunk)
        for chunk in iter(lambda: fb.read(1024 * 1024), b""):
            h2.update(chunk)
    return h1.digest() == h2.digest()


def _inside(path: str, root: str) -> bool:
    try:
        return os.path.commonpath([
            os.path.normcase(os.path.abspath(path)),
            os.path.normcase(os.path.abspath(root)),
        ]) == os.path.normcase(os.path.abspath(root))
    except ValueError:
        return False


def relocate_pasted_images(project, layout_path: str,
                           pasted_root: str) -> tuple[str, list[str]]:
    """Copy project images living under *pasted_root* into the sidecar
    ``<layout basename>_assets/`` next to *layout_path* and rewrite the
    references. Returns ``(assets_dir, copied_paths)``."""
    base = os.path.splitext(os.path.basename(layout_path))[0]
    assets_dir = os.path.join(os.path.dirname(layout_path),
                              f"{base}_assets")
    copied: list[str] = []

    def _paths():
        for cell in project.get_all_leaf_cells():
            yield cell, "image_path"
            for pip in getattr(cell, "pip_items", []) or []:
                yield pip, "image_path"

    targets = []
    for obj, attr in _paths():
        path = getattr(obj, attr, None)
        if path and os.path.isfile(path) and _inside(path, pasted_root):
            targets.append((obj, attr, path))
    if not targets:
        return assets_dir, copied

    os.makedirs(assets_dir, exist_ok=True)
    for obj, attr, src in targets:
        dst = os.path.join(assets_dir, os.path.basename(src))
        if not (os.path.isfile(dst) and _files_identical(src, dst)):
            shutil.copy2(src, dst)
            copied.append(dst)
        setattr(obj, attr, dst)
    return assets_dir, copied
