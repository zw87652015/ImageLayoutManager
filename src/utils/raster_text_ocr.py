"""Pluggable text-detection backends for raster text size matching.

Only *detection* is used downstream: every backend must return axis-aligned
boxes in source-image pixels.  Recognised text (when available) is shown to
the user as a label; it never drives geometry.

Backends
--------
rapidocr   Default and shipped: ``pip install rapidocr onnxruntime``.
tesseract  ``pytesseract`` + a system Tesseract install.
command    Any user-provided executable.  The template receives ``{image}``
           (a PNG path) and must print JSON: a list of objects with
           ``x, y, w, h`` (pixels) and optional ``text`` / ``confidence`` /
           ``chars`` (a list of ``{"c", "x", "y", "w", "h"}`` per-character
           boxes), or a list of ``[x, y, w, h]`` arrays.

The active backend is chosen in Preferences (``ocr_backend`` /
``ocr_command``).  ``ocr_backend == "none"`` disables the feature.
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from typing import List, Optional

from PIL import Image

BACKEND_NONE = "none"
BACKEND_RAPIDOCR = "rapidocr"
BACKEND_TESSERACT = "tesseract"
BACKEND_COMMAND = "command"
BACKENDS = (BACKEND_RAPIDOCR, BACKEND_TESSERACT, BACKEND_COMMAND, BACKEND_NONE)
DEFAULT_BACKEND = BACKEND_RAPIDOCR


@dataclass
class DetectedText:
    x: int
    y: int
    w: int
    h: int
    text: str = ""
    confidence: float = 1.0
    # Per-character boxes ``[char, x, y, w, h]`` (image pixels) when the
    # backend can provide them. Used as a "judge" when deciding which ink
    # inside a box belongs to the text (a hyphen, an i-dot) and which does
    # not (a diagram pointer). Empty when unavailable.
    chars: list = field(default_factory=list)


class OcrUnavailable(RuntimeError):
    """Raised when the configured backend cannot run."""


def _quad_to_box(points) -> tuple:
    xs = [float(p[0]) for p in points]
    ys = [float(p[1]) for p in points]
    x0, y0 = int(round(min(xs))), int(round(min(ys)))
    x1, y1 = int(round(max(xs))), int(round(max(ys)))
    return x0, y0, max(1, x1 - x0), max(1, y1 - y0)


class RapidOcrBackend:
    name = BACKEND_RAPIDOCR
    _engine = None

    @staticmethod
    def available() -> Optional[str]:
        from importlib.util import find_spec
        if find_spec("rapidocr") is None and find_spec("rapidocr_onnxruntime") is None:
            return "rapidocr is not installed (pip install rapidocr onnxruntime)"
        return None

    @classmethod
    def _get_engine(cls):
        if cls._engine is None:
            try:
                from rapidocr import RapidOCR
            except ImportError:
                from rapidocr_onnxruntime import RapidOCR
            cls._engine = RapidOCR()
        return cls._engine

    @classmethod
    def detect(cls, image: Image.Image) -> List[DetectedText]:
        import numpy as np
        engine = cls._get_engine()
        arr = np.array(image.convert("RGB"))
        word_results = None
        try:
            # Per-character boxes: the recogniser's CTC alignment split into
            # one quad per character (full line height, char-wide).
            result = engine(arr, return_word_box=True, return_single_char_box=True)
            word_results = getattr(result, "word_results", None)
        except TypeError:
            result = engine(arr)
        if isinstance(result, tuple):
            # rapidocr_onnxruntime API: (list of [quad, text, score], elapse)
            entries, _elapse = result
            boxes = [e[0] for e in entries or []]
            txts = [e[1] for e in entries or []]
            scores = [e[2] for e in entries or []]
        else:
            boxes = list(result.boxes) if result.boxes is not None else []
            txts = list(result.txts) if result.txts is not None else [""] * len(boxes)
            scores = list(result.scores) if result.scores is not None else [1.0] * len(boxes)
        out = []
        for i, (quad, txt, score) in enumerate(zip(boxes, txts, scores)):
            x, y, w, h = _quad_to_box(quad)
            chars = []
            if word_results is not None and i < len(word_results):
                for item in word_results[i] or ():
                    try:
                        ch, _conf, cquad = item[0], item[1], item[2]
                        cx, cy, cw, chh = _quad_to_box(cquad)
                        chars.append([str(ch), cx, cy, cw, chh])
                    except Exception:
                        continue
            out.append(DetectedText(x, y, w, h, str(txt or ""), float(score or 0.0), chars))
        return out


class TesseractBackend:
    name = BACKEND_TESSERACT

    @staticmethod
    def available() -> Optional[str]:
        try:
            import pytesseract
        except ImportError:
            return "pytesseract is not installed"
        try:
            pytesseract.get_tesseract_version()
        except Exception as exc:
            return f"Tesseract executable not found ({exc})"
        return None

    @staticmethod
    def detect(image: Image.Image) -> List[DetectedText]:
        import pytesseract
        rgb = image.convert("RGB")
        data = pytesseract.image_to_data(rgb, output_type=pytesseract.Output.DICT)
        # Character boxes come from a separate call; coordinates use a
        # bottom-left origin ("x1 y1 x2 y2" with y measured from the bottom).
        char_boxes = []
        try:
            H = rgb.height
            for line in pytesseract.image_to_boxes(rgb).splitlines():
                parts = line.split()
                if len(parts) >= 5:
                    ch, x1, y1, x2, y2 = parts[0], *map(int, parts[1:5])
                    char_boxes.append([ch, x1, H - y2, max(1, x2 - x1), max(1, y2 - y1)])
        except Exception:
            char_boxes = []
        out = []
        for i, txt in enumerate(data["text"]):
            if not str(txt).strip():
                continue
            conf = float(data["conf"][i]) if str(data["conf"][i]).replace('.', '', 1).lstrip('-').isdigit() else 0.0
            x, y, w, h = int(data["left"][i]), int(data["top"][i]), int(data["width"][i]), int(data["height"][i])
            chars = [c for c in char_boxes
                     if c[1] + c[3] / 2 >= x and c[1] + c[3] / 2 <= x + w
                     and c[2] + c[4] / 2 >= y and c[2] + c[4] / 2 <= y + h]
            out.append(DetectedText(x, y, w, h, str(txt), max(0.0, conf) / 100.0, chars))
        return out


class CommandBackend:
    name = BACKEND_COMMAND

    def __init__(self, template: str):
        self.template = template or ""

    def available(self) -> Optional[str]:
        if not self.template.strip():
            return "no OCR command configured"
        if "{image}" not in self.template:
            return "OCR command must contain the {image} placeholder"
        return None

    def detect(self, image: Image.Image) -> List[DetectedText]:
        fd, png_path = tempfile.mkstemp(suffix=".png")
        os.close(fd)
        try:
            image.convert("RGB").save(png_path, "PNG")
            args = [a.replace("{image}", png_path)
                    for a in shlex.split(self.template, posix=(sys.platform != "win32"))]
            proc = subprocess.run(args, capture_output=True, text=True, timeout=300)
        finally:
            try:
                os.remove(png_path)
            except OSError:
                pass
        if proc.returncode != 0:
            raise OcrUnavailable(proc.stderr.strip() or f"OCR command exited with {proc.returncode}")
        payload = json.loads(proc.stdout or "[]")
        if isinstance(payload, dict):
            payload = payload.get("results", payload.get("boxes", []))
        out = []
        for item in payload:
            if isinstance(item, dict):
                if "points" in item:
                    x, y, w, h = _quad_to_box(item["points"])
                else:
                    x, y, w, h = (int(round(float(item[k]))) for k in ("x", "y", "w", "h"))
                chars = []
                for c in item.get("chars", []) or []:
                    try:
                        if isinstance(c, dict):
                            chars.append([str(c.get("c", c.get("char", "")))]
                                         + [int(round(float(c[k]))) for k in ("x", "y", "w", "h")])
                        else:
                            chars.append([str(c[0])] + [int(round(float(v))) for v in c[1:5]])
                    except Exception:
                        continue
                out.append(DetectedText(x, y, w, h, str(item.get("text", "")),
                                        float(item.get("confidence", 1.0)), chars))
            else:
                x, y, w, h = (int(round(float(v))) for v in item[:4])
                out.append(DetectedText(x, y, w, h))
        return out


def get_backend(name: str, command: str = ""):
    """Return a backend object for *name*, or None when OCR is disabled."""
    if name == BACKEND_RAPIDOCR:
        return RapidOcrBackend
    if name == BACKEND_TESSERACT:
        return TesseractBackend
    if name == BACKEND_COMMAND:
        return CommandBackend(command)
    return None


def backend_status(name: str, command: str = "") -> Optional[str]:
    """None when the backend is ready, else a human-readable reason."""
    backend = get_backend(name, command)
    if backend is None:
        return "OCR is disabled"
    return backend.available()


def configured_backend():
    """Backend selected in Preferences, or None if disabled / unusable."""
    from src.app.preferences_dialog import get_pref
    name = get_pref("ocr_backend", DEFAULT_BACKEND)
    command = get_pref("ocr_command", "")
    if backend_status(name, command) is not None:
        return None
    return get_backend(name, command)


def detect_text(image: Image.Image, backend=None) -> List[DetectedText]:
    backend = backend or configured_backend()
    if backend is None:
        raise OcrUnavailable("No OCR backend is configured")
    return backend.detect(image)
