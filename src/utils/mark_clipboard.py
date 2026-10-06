"""Clipboard payload format for vector marks.

Marks travel on the system clipboard under their own MIME type only — no
text fallback — so image/text paste logic is never polluted, and payloads
work across tabs and app instances.
"""
import copy
import json
import uuid

from src.model.data_model import Mark

MARKS_MIME = "application/x-ilm-marks+json"
_FORMAT = "ilm-marks"
_VERSION = 1


def marks_to_payload(marks) -> bytes:
    """Serialise marks (pass them in z-order) to UTF-8 JSON bytes."""
    return json.dumps({
        "format": _FORMAT,
        "version": _VERSION,
        "marks": [m.to_dict() for m in marks],
    }).encode("utf-8")


def marks_from_payload(data: bytes):
    """Parse clipboard bytes back into Marks with fresh ids.

    Raises ValueError on any malformed payload (bad JSON, wrong
    format/version, invalid mark, empty list).
    """
    try:
        doc = json.loads(bytes(data).decode("utf-8"))
    except Exception as exc:
        raise ValueError("marks payload is not valid JSON") from exc
    if (not isinstance(doc, dict) or doc.get("format") != _FORMAT
            or doc.get("version") != _VERSION
            or not isinstance(doc.get("marks"), list)
            or not doc["marks"]):
        raise ValueError("not a supported marks payload")
    marks = []
    for raw in doc["marks"]:
        try:
            mark = Mark.from_dict(raw)
        except Exception as exc:
            raise ValueError("invalid mark in payload") from exc
        mark.id = str(uuid.uuid4())
        mark.points = copy.deepcopy(mark.points)
        marks.append(mark)
    return marks


def offset_marks(marks, dx_mm: float, dy_mm: float):
    """New Mark copies with every point translated and fresh ids."""
    out = []
    for m in marks:
        nm = copy.deepcopy(m)
        nm.id = str(uuid.uuid4())
        nm.points = [[p[0] + dx_mm, p[1] + dy_mm] for p in nm.points]
        out.append(nm)
    return out


def _same_geometry(a: Mark, b: Mark) -> bool:
    return (a.kind == b.kind and a.closed == b.closed
            and [list(p) for p in a.points] == [list(p) for p in b.points])


def paste_offset_steps(payload_marks, project_marks, count: int) -> int:
    """Cascade step k for a paste (offset = 2 mm * k).

    `count` is how many times this payload has already been pasted into the
    target project. When the project still holds a mark whose geometry equals
    a payload mark's — i.e. the copied originals still sit at the same spot —
    the next paste is shifted one extra step so it lands beside the previous
    copy instead of on top of the source.
    """
    if any(_same_geometry(pm, m)
           for pm in payload_marks for m in project_marks):
        return count + 1
    return count
