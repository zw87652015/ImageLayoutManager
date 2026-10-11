"""Image-encoding pass for PDF export.

Qt's PDF engine re-encodes every drawn raster as JPEG (~q94) regardless of
source format. ``PdfRasterLog`` records each raster drawn into the QPdfWriter
so that, after painting, ``apply`` can replace the stream of each Qt-written
image XObject in place (same xref, so placement, clip, z-order and SMask are
untouched) with lossless Flate pixels, the original JPEG bytes, or a fresh
JPEG at the requested quality.
"""
import base64
import hashlib
import io
import itertools
import os
import re
import shutil
import tempfile
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, Optional

from PIL import Image

from src.app.i18n import translate

IMAGE_MODES = ("lossless", "lossy")
DEFAULT_IMAGE_MODE = "lossless"
DEFAULT_JPEG_QUALITY = 90
SIGNATURE_SIZE = 16
MATCH_THRESHOLD = 10.0

_ISSUE_KEYS = {
    "pass_skipped": "pdf_issue_pass_skipped",
    "pass_failed": "pdf_issue_pass_failed",
    "no_match": "pdf_issue_no_match",
    "still_jpeg": "pdf_issue_still_jpeg",
    "audit_failed": "pdf_issue_audit_failed",
}


@dataclass
class PdfIssue:
    """A structured export problem; ``format_issue`` localises it."""
    code: str
    params: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return format_issue(self, "en")


@dataclass
class PdfExportReport:
    images_total: int = 0
    images_replaced: int = 0
    issues: list = field(default_factory=list)
    lossless_verified: bool = False

    @property
    def warnings(self) -> list:
        return [issue.text for issue in self.issues]


def _owner_phrase(owner: Optional[dict], lang: str) -> str:
    if not owner:
        return translate("pdf_owner_none", lang)
    where = _where_phrase(owner, lang)
    source = owner.get("source")
    if source and where:
        return translate("pdf_owner_src_where", lang).format(source=source, where=where)
    if source:
        return translate("pdf_owner_src", lang).format(source=source)
    if where:
        return translate("pdf_owner_where", lang).format(where=where)
    return translate("pdf_owner_none", lang)


def _where_phrase(owner: dict, lang: str) -> str:
    if owner.get("kind") == "cell":
        return translate("pdf_where_cell", lang).format(row=owner["row"], col=owner["col"])
    if owner.get("kind") == "pip":
        return translate("pdf_where_pip", lang).format(index=owner["index"],
                                                       cell=_where_phrase(owner["cell"], lang))
    return ""


def format_issue(issue: PdfIssue, lang: str = "en") -> str:
    key = _ISSUE_KEYS.get(issue.code)
    if key is None:
        return issue.code
    params = dict(issue.params)
    if issue.code == "no_match":
        source = params.get("source")
        params["source"] = (translate("pdf_src_named", lang).format(source=source) if source
                            else translate("pdf_src_unknown", lang))
    elif issue.code == "still_jpeg":
        if params.get("x") is None:
            key = "pdf_issue_still_jpeg_nopos"
        params["owner"] = _owner_phrase(params.get("owner"), lang)
        params["svg_hint"] = translate("pdf_issue_svg_raster", lang) if params.get("svg_has_raster") else ""
    return translate(key, lang).format(**params)


def validate_image_settings(mode, quality):
    if mode not in IMAGE_MODES:
        raise ValueError(f"image_mode must be one of {IMAGE_MODES}, got {mode!r}")
    if isinstance(quality, bool) or not isinstance(quality, int) or not 1 <= quality <= 100:
        raise ValueError(f"jpeg_quality must be an int in 1..100, got {quality!r}")


def coerce_image_settings(mode, quality) -> tuple:
    """Lenient counterpart for persisted settings: falls back to defaults."""
    if mode not in IMAGE_MODES:
        mode = DEFAULT_IMAGE_MODE
    try:
        quality = int(quality)
    except (TypeError, ValueError):
        quality = DEFAULT_JPEG_QUALITY
    return mode, min(100, max(1, quality))


def is_passthrough_jpeg(path: str) -> bool:
    try:
        with Image.open(path) as im:
            return im.format == "JPEG" and im.mode in ("RGB", "L")
    except Exception:
        return False


def _signature(img: Image.Image) -> bytes:
    return img.convert("RGB").resize((SIGNATURE_SIZE, SIGNATURE_SIZE), Image.Resampling.BOX).tobytes()


def _distance(a: bytes, b: bytes) -> float:
    return sum(abs(x - y) for x, y in zip(a, b)) / len(a)


def _decode_rgb(doc, xref: int) -> Image.Image:
    import fitz
    pix = fitz.Pixmap(doc, xref)
    if pix.colorspace is None or pix.colorspace.n not in (1, 3):
        pix = fitz.Pixmap(fitz.csRGB, pix)
    mode = {(1, 0): "L", (3, 0): "RGB", (1, 1): "LA", (3, 1): "RGBA"}[(pix.colorspace.n, pix.alpha)]
    img = Image.frombuffer(mode, (pix.width, pix.height), pix.samples, "raw", mode, pix.stride, 1)
    return img.convert("RGB")


def _png_idat(png: bytes) -> bytes:
    parts, pos = [], 8
    while pos < len(png):
        length = int.from_bytes(png[pos:pos + 4], "big")
        if png[pos + 4:pos + 8] == b"IDAT":
            parts.append(png[pos + 8:pos + 8 + length])
        pos += 12 + length
    return b"".join(parts)


@dataclass
class _Entry:
    size: tuple
    signature: bytes
    loader: Callable[[], Image.Image]
    jpeg_bytes: Optional[Callable[[], bytes]]
    source: Optional[str]
    optional: bool = False  # SVG-embedded: Qt may skip or share the draw, so no match is not an issue


def _file_reader(path: str) -> Callable[[], bytes]:
    def read() -> bytes:
        with open(path, "rb") as handle:
            return handle.read()
    return read


class PdfRasterLog:
    """Rasters drawn into a QPdfWriter, in first-draw order."""

    def __init__(self):
        self._entries = {}
        self._svg_ids = itertools.count()

    def record(self, qimage, pil_rgba: Image.Image, loader: Callable[[], Image.Image],
               jpeg_path: Optional[str] = None, source: Optional[str] = None):
        """``loader`` must return a fresh RGBA image of exactly the pixels drawn;
        ``jpeg_path`` is set only when those pixels are the file's decoded pixels;
        ``source`` is a display name for the drawn file, used in issues."""
        key = qimage.cacheKey()
        if key not in self._entries:
            self._entries[key] = _Entry(pil_rgba.size, _signature(pil_rgba), loader,
                                        _file_reader(jpeg_path) if jpeg_path else None, source)

    def record_decoded(self, pil_rgba: Image.Image, loader: Callable[[], Image.Image],
                       jpeg_bytes: Optional[bytes] = None, source: Optional[str] = None):
        """One SVG-embedded ``<image>`` draw. Never deduplicated: each element is its own entry."""
        self._entries[("svg", next(self._svg_ids))] = _Entry(
            pil_rgba.size, _signature(pil_rgba), loader,
            (lambda: jpeg_bytes) if jpeg_bytes is not None else None, source, optional=True)

    def apply(self, output_path: str, mode: str, quality: int = DEFAULT_JPEG_QUALITY,
              owners: Optional[list] = None, offset_mm: tuple = (0.0, 0.0)) -> PdfExportReport:
        """Replace the logged images in ``output_path``, then audit it (lossless only).

        ``owners`` is ``[(rect_mm, owner_dict)]`` in project page mm and ``offset_mm``
        is the export-region origin, so issue positions are reported in project page
        mm. Never raises; on failure the PDF is left as Qt wrote it. Must run before the
        vector stamps (``_stamp_*``): the audit covers every image XObject in the file,
        and PDF/EPS cell sources stamped later keep their own embedded content.
        """
        report = PdfExportReport(images_total=len(self._entries))
        passthrough = self._rewrite(output_path, mode, quality, report) if self._entries else {}
        if mode == "lossless":
            _audit_lossless(output_path, passthrough, report, owners or [], offset_mm)
        return report

    def _rewrite(self, output_path: str, mode: str, quality: int, report: PdfExportReport) -> dict:
        """Returns {xref: (length, sha256)} for passthrough replacements that were saved."""
        try:
            import fitz
            doc = fitz.open(output_path)
        except Exception as exc:
            report.issues.append(PdfIssue("pass_skipped", {"error": str(exc)}))
            return {}
        saved = None
        matches = []
        passthrough = {}
        try:
            matches = self._match(doc, report)
            if matches:
                for xref, entry in matches:
                    digest = _replace(doc, xref, entry, mode, quality)
                    if digest is not None:
                        passthrough[xref] = digest
                fd, saved = tempfile.mkstemp(suffix=".pdf")
                os.close(fd)
                doc.save(saved, incremental=False, encryption=fitz.PDF_ENCRYPT_NONE)
        except Exception as exc:
            report.issues.append(PdfIssue("pass_failed", {"error": str(exc)}))
            if saved is not None and os.path.exists(saved):
                os.remove(saved)
            saved = None
        finally:
            doc.close()
        if saved is None:
            return {}
        try:
            shutil.move(saved, output_path)
        except Exception as exc:
            report.issues.append(PdfIssue("pass_failed", {"error": str(exc)}))
            os.remove(saved)
            return {}
        report.images_replaced = len(matches)
        return passthrough

    def _match(self, doc, report: PdfExportReport) -> list:
        candidates = {}
        for info in doc.get_page_images(0, full=True):
            candidates.setdefault(info[0], (info[2], info[3]))
        signatures = {}
        used = set()
        matches = []
        for entry in self._entries.values():
            hit = None
            for xref in sorted(candidates):
                if xref in used or candidates[xref] != entry.size:
                    continue
                if xref not in signatures:
                    signatures[xref] = _signature(_decode_rgb(doc, xref))
                if _distance(signatures[xref], entry.signature) < MATCH_THRESHOLD:
                    hit = xref
                    break
            if hit is None:
                if not entry.optional:
                    report.issues.append(PdfIssue("no_match", {
                        "size": f"{entry.size[0]}x{entry.size[1]}", "source": entry.source}))
            else:
                used.add(hit)
                matches.append((hit, entry))
        return matches


def _svg_has_raster(path: Optional[str]) -> bool:
    if not path or not path.lower().endswith(".svg"):
        return False
    try:
        with open(path, "rb") as handle:
            return b"<image" in handle.read()
    except OSError:
        return False


def _attribute(owners: list, cx: float, cy: float) -> Optional[dict]:
    best = None
    for (x, y, w, h), owner in owners:
        if x <= cx <= x + w and y <= cy <= y + h and (best is None or w * h < best[0]):
            best = (w * h, owner)
    return best[1] if best else None


def _still_jpeg_issue(doc, page, xref: int, owners: list, offset_mm: tuple) -> PdfIssue:
    size = f"{doc.xref_get_key(xref, 'Width')[1]}x{doc.xref_get_key(xref, 'Height')[1]}"
    rects = page.get_image_rects(xref) if page is not None else []
    if not rects:
        return PdfIssue("still_jpeg", {"size": size, "x": None, "y": None, "owner": None,
                                       "svg_has_raster": False})
    rect = rects[0]
    scale = 25.4 / 72.0
    x = rect.x0 * scale + offset_mm[0]
    y = rect.y0 * scale + offset_mm[1]
    w = (rect.x1 - rect.x0) * scale
    h = (rect.y1 - rect.y0) * scale
    owner = _attribute(owners, x + w / 2, y + h / 2)
    svg_has_raster = _svg_has_raster(owner.get("path")) if owner else False
    return PdfIssue("still_jpeg", {
        "size": size,
        "x": round(x, 1),
        "y": round(y, 1),
        "owner": {k: v for k, v in owner.items() if k != "path"} if owner else None,
        "svg_has_raster": svg_has_raster,
    })


def _audit_lossless(output_path: str, passthrough: dict, report: PdfExportReport,
                    owners: list, offset_mm: tuple):
    """Flag JPEG/JPX images that are not byte-identical source files.

    Every image XObject in the file is checked, including those nested in Form
    XObjects. A DCT/JPX image passes only if it is a passthrough replacement whose
    raw stream still matches the recorded length and sha256.
    """
    try:
        import fitz
        with fitz.open(output_path) as doc:
            page = doc[0] if doc.page_count else None
            for xref in range(1, doc.xref_length()):
                if doc.xref_get_key(xref, "Subtype") != ("name", "/Image"):
                    continue
                if not any(name in doc.xref_get_key(xref, "Filter")[1] for name in ("DCTDecode", "JPXDecode")):
                    continue
                raw = doc.xref_stream_raw(xref)
                if passthrough.get(xref) != (len(raw), hashlib.sha256(raw).hexdigest()):
                    report.issues.append(_still_jpeg_issue(doc, page, xref, owners, offset_mm))
        if not report.issues:
            report.lossless_verified = True
    except Exception as exc:
        report.issues.append(PdfIssue("audit_failed", {"error": str(exc)}))


_SVG_SKIP_TAGS = {"pattern", "mask", "clipPath", "marker"}
_XLINK_HREF = "{http://www.w3.org/1999/xlink}href"
_LENGTH = re.compile(r"\s*([0-9]*\.?[0-9]+)")


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _hidden(elem) -> bool:
    style = (elem.get("style") or "").replace(" ", "").lower()
    return elem.get("display") == "none" or "display:none" in style or elem.get("visibility") == "hidden"


def _has_drawn_size(elem) -> bool:
    for name in ("width", "height"):
        match = _LENGTH.match(elem.get(name) or "")
        if not match or float(match.group(1)) <= 0:
            return False
    return True


def _svg_image_elements(root) -> list:
    """``<image>`` elements Qt draws at their source pixels, in document order.

    Pattern/mask/clipPath/marker content is rasterised by Qt rather than drawn at source
    pixels, and ``<defs>`` images only count when the document has a ``<use>`` to share them.
    Hidden or unsized images get no XObject from Qt, so they are skipped too.
    """
    has_use = any(_local_name(elem.tag) == "use" for elem in root.iter())
    found = []

    def walk(elem, in_defs: bool):
        tag = _local_name(elem.tag)
        if tag in _SVG_SKIP_TAGS or _hidden(elem):
            return
        in_defs = in_defs or tag == "defs"
        if tag == "image":
            if (not in_defs or has_use) and _has_drawn_size(elem):
                found.append(elem)
            return
        for child in elem:
            walk(child, in_defs)

    walk(root, False)
    return found


def _decode_data_uri(uri: str) -> Optional[bytes]:
    uri = uri.strip()
    if not uri.lower().startswith("data:image/") or "," not in uri:
        return None
    head, _, payload = uri.partition(",")
    if ";base64" in head.lower():
        return base64.b64decode(re.sub(r"\s+", "", payload))
    return urllib.parse.unquote_to_bytes(payload)


def _decode_rgba(data: bytes) -> Image.Image:
    with Image.open(io.BytesIO(data)) as im:
        return im.convert("RGBA")


def log_svg_images(log: PdfRasterLog, svg_bytes: bytes, source: Optional[str]):
    """Record each data-URI raster in ``svg_bytes``, the exact bytes handed to QSvgRenderer.

    File and remote hrefs are ignored (Qt cannot resolve them from bytes, so they draw
    nothing here). Anything that fails to decode is skipped and left to the audit.
    """
    try:
        root = ET.fromstring(svg_bytes)
    except Exception:
        return
    for elem in _svg_image_elements(root):
        try:
            raw = _decode_data_uri(elem.get(_XLINK_HREF) or elem.get("href") or "")
            if raw is None:
                continue
            with Image.open(io.BytesIO(raw)) as im:
                fmt, mode = im.format, im.mode
                pil = im.convert("RGBA")
        except Exception:
            continue
        jpeg_bytes = raw if fmt == "JPEG" and mode in ("RGB", "L") else None
        log.record_decoded(pil, lambda data=raw: _decode_rgba(data), jpeg_bytes, source)


def _replace(doc, xref: int, entry: _Entry, mode: str, quality: int):
    """Replace one image stream. Returns (length, sha256) for an original-file passthrough, else None."""
    width = entry.size[0]
    digest = None
    if mode == "lossless" and entry.jpeg_bytes:
        data = entry.jpeg_bytes()
        with Image.open(io.BytesIO(data)) as im:
            colorspace = "DeviceGray" if im.mode == "L" else "DeviceRGB"
        digest = (len(data), hashlib.sha256(data).hexdigest())
        filter_name, parms = "DCTDecode", None
    elif mode == "lossless":
        buf = io.BytesIO()
        entry.loader().convert("RGB").save(buf, "PNG")
        data = _png_idat(buf.getvalue())
        colorspace = "DeviceRGB"
        filter_name = "FlateDecode"
        parms = f"<</Predictor 15/Colors 3/BitsPerComponent 8/Columns {width}>>"
    else:
        buf = io.BytesIO()
        entry.loader().convert("RGB").save(buf, "JPEG", quality=quality, optimize=True,
                                           subsampling=0 if quality >= 90 else -1)
        data = buf.getvalue()
        colorspace = "DeviceRGB"
        filter_name, parms = "DCTDecode", None
    doc.update_stream(xref, data, new=False, compress=False)
    doc.xref_set_key(xref, "Filter", f"/{filter_name}")
    if parms:
        doc.xref_set_key(xref, "DecodeParms", parms)
    doc.xref_set_key(xref, "ColorSpace", f"/{colorspace}")
    return digest
