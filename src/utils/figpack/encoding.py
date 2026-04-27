"""
Unicode & filename-encoding helpers for .figpack.

All invariants from plan.md §2.5 live here so the rest of the package
manager can stay small and readable. Users' source paths may contain
any script (Arabic, Hebrew, CJK, Hangul, Devanagari, Thai, Mongolian,
Cyrillic, …); this module's job is to pass those through safely while
stripping cross-platform-unsafe bytes and spoofing vectors.

Public helpers:

* ``to_nfc(s)``                 — normalize to Unicode NFC form
* ``strip_bidi(s)``             — remove BiDi override control chars
* ``sanitize_basename(name)``   — strip bytes unsafe on Win/macOS
* ``normalize_archive_name(n)`` — validate + normalize a ZIP entry name
* ``asset_archive_path(p)``     — deterministic assets/<hash>/<name>
* ``hash_abs_path(p)``          — stable sha1[:12] over NFC UTF-8 bytes
"""

from __future__ import annotations

import hashlib
import os
import re
import unicodedata
from typing import Tuple

# ──────────────────────────────────────────────────────────────────────
# Constants
# ──────────────────────────────────────────────────────────────────────

# BiDi overrides — filename-spoofing vector; always stripped from the
# archive path. Kept in metadata.json.original_basename for display.
_BIDI_OVERRIDES = {
    "\u202A", "\u202B", "\u202C", "\u202D", "\u202E",  # LRE/RLE/PDF/LRO/RLO
    "\u2066", "\u2067", "\u2068", "\u2069",            # LRI/RLI/FSI/PDI
}

# Windows reserved basenames (case-insensitive, with or without extension).
_WINDOWS_RESERVED = {
    "con", "prn", "aux", "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}

# Characters illegal in Windows filenames. We strip them everywhere so a
# figpack written on macOS can be extracted on Windows without collision.
_WINDOWS_ILLEGAL = '<>:"|?*\\/'
_WINDOWS_ILLEGAL_RE = re.compile(f"[{re.escape(_WINDOWS_ILLEGAL)}]")

# Control chars U+0000–U+001F and U+007F.
_CTRL_RE = re.compile(r"[\x00-\x1f\x7f]")

# Maximum basename length before we fall back to a hashed short name.
_MAX_BASENAME_LEN = 150


# ──────────────────────────────────────────────────────────────────────
# Normalisation primitives
# ──────────────────────────────────────────────────────────────────────

def to_nfc(s: str) -> str:
    """Unicode NFC normalization.

    macOS HFS+ traditionally returned NFD; APFS preserves what was
    given; Windows stores NFC. Normalizing once at ingestion is the
    only way to get deterministic hashes across OSes.
    """
    return unicodedata.normalize("NFC", s)


def strip_bidi(s: str) -> str:
    """Remove all BiDi override / isolate characters.

    These characters are a well-known filename-spoofing vector
    (``invoice<U+202E>gpj.exe`` displays as ``invoiceexe.jpg``).
    Archive paths never contain them; the original (unstripped) string
    is kept in ``metadata.json`` for display only.
    """
    if not s:
        return s
    return "".join(ch for ch in s if ch not in _BIDI_OVERRIDES)


def _fix_surrogates(s: str) -> str:
    """Replace unpaired UTF-16 surrogates with U+FFFD.

    Python's ``os.fsdecode`` can leave lone surrogates in strings read
    from filesystems whose bytes don't decode cleanly as UTF-8 (rare
    on modern systems but possible on Windows paths created by older
    tools). We replace them so downstream ``.encode('utf-8')`` calls
    don't raise.
    """
    try:
        s.encode("utf-8")
        return s
    except UnicodeEncodeError:
        return s.encode("utf-8", "surrogatepass").decode("utf-8", "replace")


# ──────────────────────────────────────────────────────────────────────
# Basename sanitization (for archive entries)
# ──────────────────────────────────────────────────────────────────────

def sanitize_basename(name: str) -> str:
    """Produce a cross-platform-safe basename.

    Rules (plan.md §2.5 §4):
      * NFC-normalize.
      * Strip BiDi overrides.
      * Strip control chars U+0000–U+001F and U+007F.
      * Strip Windows-illegal bytes ``<>:"|?*\\/``.
      * Refuse Windows reserved stems (CON, PRN, …): prefix with ``_``.
      * If the result exceeds ``_MAX_BASENAME_LEN`` chars, keep the
        extension and shorten the stem with a 10-char sha1 tag so the
        result is still unique and recoverable via metadata.
      * Non-ASCII (Arabic / CJK / Hangul / Devanagari / Thai / Mongolian
        / Cyrillic / …) characters pass through untouched.

    The original (unsanitized) name should be preserved separately by
    the caller (in ``metadata.json``) for human display and round-trip.
    """
    if not name:
        return "_unnamed"

    name = _fix_surrogates(name)
    name = to_nfc(name)
    name = strip_bidi(name)
    name = _CTRL_RE.sub("", name)
    name = _WINDOWS_ILLEGAL_RE.sub("", name)

    # Trim leading/trailing whitespace and dots (Windows strips trailing
    # dots silently; we do it up front so archive + extracted names match).
    name = name.strip().strip(".")
    if not name:
        return "_unnamed"

    # Windows reserved stem guard. Compare case-insensitively against the
    # portion before the first dot.
    stem = name.split(".", 1)[0].lower()
    if stem in _WINDOWS_RESERVED:
        name = "_" + name

    # Length cap. We keep the extension to preserve content-type cues.
    if len(name) > _MAX_BASENAME_LEN:
        stem, dot, ext = name.rpartition(".")
        if not dot:
            stem, ext = name, ""
        tag = hashlib.sha1(name.encode("utf-8")).hexdigest()[:10]
        keep = _MAX_BASENAME_LEN - len(tag) - len(ext) - 2  # -2 for "." and "_"
        keep = max(keep, 1)
        name = f"{stem[:keep]}_{tag}" + (f".{ext}" if ext else "")

    return name


# ──────────────────────────────────────────────────────────────────────
# ZIP entry name validation
# ──────────────────────────────────────────────────────────────────────

def normalize_archive_name(name: str) -> str:
    """Validate and canonicalize an incoming ZIP entry name.

    This is the last line of defence before any ``os.path.join`` with
    the target directory. Returns a POSIX-style relative path composed
    of NFC-normalized, BiDi-stripped segments.

    Raises :class:`BundleSecurityError` for any of:

      * absolute paths (leading ``/`` or ``\\``)
      * Windows drive letters (``C:\\…``, ``C:…``)
      * parent-directory traversal (``..``)
      * empty segments
      * lone surrogates that cannot be recovered
      * segments that reduce to empty after sanitization

    ZIP entries of directories (trailing ``/``) are signalled by an
    empty final segment and handled by the caller via ``info.is_dir()``.
    """
    # Import locally to avoid circular import on package __init__.
    from src.utils.figpack.errors import BundleSecurityError

    if not name:
        raise BundleSecurityError("empty archive entry name", code="zip_empty_name")

    original = name
    name = _fix_surrogates(name)

    # Reject absolute paths. Check both POSIX and Windows forms before
    # any further normalisation; normalisation could otherwise hide
    # e.g. "C:" as a harmless segment.
    if name.startswith("/") or name.startswith("\\"):
        raise BundleSecurityError(
            f"absolute path in archive: {original!r}", code="zip_absolute"
        )
    if len(name) >= 2 and name[1] == ":":
        raise BundleSecurityError(
            f"drive-letter path in archive: {original!r}", code="zip_drive"
        )

    # Normalise slashes → '/' then split.
    parts = name.replace("\\", "/").split("/")

    # Trailing slash = directory entry; strip the empty final segment.
    if parts and parts[-1] == "":
        parts = parts[:-1]

    clean: list[str] = []
    for seg in parts:
        if seg in ("", "."):
            # Empty segments usually mean "//" in the middle of a path;
            # treat them as a traversal attempt rather than silently
            # collapsing.
            raise BundleSecurityError(
                f"empty path segment in {original!r}", code="zip_empty_segment"
            )
        if seg == "..":
            raise BundleSecurityError(
                f"parent-directory traversal in {original!r}", code="zip_parent"
            )
        seg = to_nfc(seg)
        seg = strip_bidi(seg)
        if _CTRL_RE.search(seg):
            raise BundleSecurityError(
                f"control character in {original!r}", code="zip_control_char"
            )
        clean.append(seg)

    if not clean:
        raise BundleSecurityError(
            f"archive entry resolves to empty path: {original!r}",
            code="zip_empty",
        )

    return "/".join(clean)


# ──────────────────────────────────────────────────────────────────────
# Deterministic archive paths
# ──────────────────────────────────────────────────────────────────────

def hash_abs_path(abspath: str, *, length: int = 12) -> str:
    """Stable short hash of an absolute path.

    Computed over the NFC-normalized UTF-8 encoding so that the same
    logical file produces the same hash whether the packer is running
    on Windows (NFC) or macOS (historically NFD).

    ``length`` defaults to 12 hex chars (48 bits): at 1 000 assets this
    gives a birthday-collision probability ≈ 1.8e-9.
    """
    canonical = to_nfc(os.path.abspath(abspath))
    return hashlib.sha1(canonical.encode("utf-8")).hexdigest()[:length]


def asset_archive_path(abspath: str) -> Tuple[str, str]:
    """Return ``(archive_path, hashed_dir)`` for an asset source path.

    The in-archive path is::

        assets/<hash_abs_path(abspath)>/<sanitize_basename(basename)>

    Both halves are returned so callers can store the hashed-dir
    component in ``metadata.json`` alongside the deterministic path.
    """
    base = sanitize_basename(os.path.basename(abspath))
    h = hash_abs_path(abspath)
    return f"assets/{h}/{base}", h
