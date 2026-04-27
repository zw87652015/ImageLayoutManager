"""
Pure-logic safety checks for ZIP archives (plan.md §3.3, §6.2, §6.3).

This module never touches the filesystem. Every public helper either
returns a clean result or raises :class:`BundleSecurityError` /
:class:`BundleError`. This separation is deliberate: it lets us fuzz
the validators against a corpus of malicious archives without
shelling out actual extraction.

Threats covered:

  * **zip-slip**       — entries naming ``../`` or absolute paths that
                         would write outside ``target_dir``.
  * **zip-bomb**       — entries with implausible compression ratios,
                         absurd declared sizes, or absurd entry counts.
  * **encrypted**      — entries with the encryption flag set
                         (we don't support keyed bundles in v1).
  * **symlink**        — entries flagged as symlinks in their POSIX
                         ``external_attr`` (could be used to escape
                         the target on extract).
  * **multi-disk**     — entries with ``disk_number_start != 0``
                         (we don't support spanned archives).
  * **self-extracting** — archives with executable stub bytes prepended
                         (the central directory is still a valid ZIP
                         but we want a *clean* ZIP, not "ZIP that's
                         also a Windows .exe").

Every check that *can* be done up-front against a freshly-opened
``zipfile.ZipFile`` is exposed via :func:`validate_archive_shape`;
per-entry checks live in :func:`validate_entry`.
"""

from __future__ import annotations

import os
import zipfile
from dataclasses import dataclass
from typing import Iterable, List, Optional

from src.utils.figpack.encoding import normalize_archive_name
from src.utils.figpack.errors import BundleError, BundleSecurityError


# ──────────────────────────────────────────────────────────────────────
# Default limits (overridable from package_manager)
# ──────────────────────────────────────────────────────────────────────

DEFAULT_MAX_ENTRIES = 50_000
DEFAULT_MAX_UNCOMPRESSED_BYTES = 50 * 1024**3  # 50 GiB
DEFAULT_MAX_ENTRY_BYTES = 20 * 1024**3         # 20 GiB single entry
DEFAULT_MAX_RATIO = 1000.0                      # uncompressed/compressed

# ZIP general-purpose-bit-flag bits we care about.
_GPB_ENCRYPTED = 0x0001

# POSIX file-type bits in (external_attr >> 16). 0o120000 = symlink.
_S_IFMT = 0o170000
_S_IFLNK = 0o120000

# Bytes that mark "this is a SFX wrapper, not a clean ZIP". Our archive
# format never emits these, so on read we treat them as suspicious.
_SFX_MAGIC_PREFIXES = (
    b"MZ",          # PE/Windows .exe
    b"\x7fELF",     # ELF/Linux
    b"\xfe\xed\xfa\xce",  # Mach-O 32-bit big-endian
    b"\xfe\xed\xfa\xcf",  # Mach-O 64-bit big-endian
    b"\xce\xfa\xed\xfe",  # Mach-O 32-bit little-endian
    b"\xcf\xfa\xed\xfe",  # Mach-O 64-bit little-endian
    b"\xca\xfe\xba\xbe",  # Mach-O universal
)

# A clean ZIP starts with the local-file-header magic.
_LFH_MAGIC = b"PK\x03\x04"
# An empty ZIP (no entries) starts with the end-of-central-directory.
_EOCD_MAGIC = b"PK\x05\x06"


# ──────────────────────────────────────────────────────────────────────
# Result / limit dataclasses
# ──────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class SafetyLimits:
    max_entries: int = DEFAULT_MAX_ENTRIES
    max_uncompressed_bytes: int = DEFAULT_MAX_UNCOMPRESSED_BYTES
    max_entry_bytes: int = DEFAULT_MAX_ENTRY_BYTES
    max_ratio: float = DEFAULT_MAX_RATIO


@dataclass(frozen=True)
class ValidatedEntry:
    """Result of :func:`validate_entry` — safe to extract.

    ``relpath`` is the canonical POSIX entry name (NFC, BiDi-stripped,
    no traversal). ``dest_abspath`` is the final on-disk path inside
    ``target_dir``; it has been ``realpath``-checked for containment.
    """
    info: zipfile.ZipInfo
    relpath: str
    dest_abspath: str


# ──────────────────────────────────────────────────────────────────────
# Archive-level validation
# ──────────────────────────────────────────────────────────────────────

def _starts_with_sfx_stub(path: str) -> bool:
    """True iff the file's first bytes look like an executable stub.

    We only inspect the first 8 bytes; a clean ZIP must start with
    ``PK\\x03\\x04`` (local file header) or ``PK\\x05\\x06`` (empty
    archive's end-of-central-directory).
    """
    try:
        with open(path, "rb") as f:
            head = f.read(8)
    except OSError:
        return False
    if not head:
        return False
    if head.startswith(_LFH_MAGIC) or head.startswith(_EOCD_MAGIC):
        return False
    return any(head.startswith(magic) for magic in _SFX_MAGIC_PREFIXES)


def validate_archive_shape(
    zf: zipfile.ZipFile,
    *,
    archive_path: Optional[str] = None,
    limits: SafetyLimits = SafetyLimits(),
) -> List[zipfile.ZipInfo]:
    """One-shot up-front checks before any extraction begins.

    Returns the list of file entries (directories filtered out) that
    will be passed to :func:`validate_entry` one-by-one. Raises
    :class:`BundleSecurityError` on any of:

      * SFX stub prepended to the archive (only checked when
        ``archive_path`` is provided).
      * Any entry with ``disk_number_start != 0`` (multi-disk span).
      * More than ``limits.max_entries`` entries.
    """
    # 1. SFX-stub guard — cheap byte sniff.
    if archive_path is not None and _starts_with_sfx_stub(archive_path):
        raise BundleSecurityError(
            "archive starts with executable stub (self-extracting "
            "archives are not accepted)",
            code="zip_sfx_stub",
        )

    infos = zf.infolist()

    # 2. Entry-count guard.
    if len(infos) > limits.max_entries:
        raise BundleSecurityError(
            f"archive has too many entries ({len(infos)} > "
            f"{limits.max_entries})",
            code="zip_too_many_entries",
        )

    # 3. Multi-disk rejection. The ZIP central-directory field
    # "disk number where file starts" is exposed by zipfile as
    # ``ZipInfo.volume`` (an int slot). Any non-zero value means the
    # entry's bytes live on a different disk of a spanned archive,
    # which we don't support.
    file_entries: List[zipfile.ZipInfo] = []
    for info in infos:
        if getattr(info, "volume", 0) != 0:
            raise BundleSecurityError(
                "multi-disk (spanned) archives are not supported",
                code="zip_multi_disk",
            )
        if not info.is_dir():
            file_entries.append(info)

    return file_entries


# ──────────────────────────────────────────────────────────────────────
# Per-entry validation
# ──────────────────────────────────────────────────────────────────────

def validate_entry(
    info: zipfile.ZipInfo,
    target_real_dir: str,
    *,
    running_uncompressed_total: int = 0,
    limits: SafetyLimits = SafetyLimits(),
) -> ValidatedEntry:
    """Validate a single ZIP entry and resolve its on-disk destination.

    ``target_real_dir`` MUST already be the realpath of the working
    directory (caller does this once and reuses).

    ``running_uncompressed_total`` is the number of uncompressed bytes
    accumulated by entries already validated in this archive; we use
    it to enforce :attr:`SafetyLimits.max_uncompressed_bytes`. This
    keeps the function pure (no internal state) — caller is responsible
    for adding ``info.file_size`` after a successful return.

    Raises :class:`BundleSecurityError` for any policy violation.
    """
    # 1. Encryption.
    if info.flag_bits & _GPB_ENCRYPTED:
        raise BundleSecurityError(
            f"encrypted archive entry: {info.filename!r}",
            code="zip_encrypted",
        )

    # 2. Symlink (POSIX file-type bits in external_attr).
    mode = (info.external_attr >> 16) & _S_IFMT
    if mode == _S_IFLNK:
        raise BundleSecurityError(
            f"symlink archive entry: {info.filename!r}",
            code="zip_symlink",
        )

    # 3. Per-entry size guard (declared file_size; before any extraction).
    if info.file_size > limits.max_entry_bytes:
        raise BundleSecurityError(
            f"entry {info.filename!r} declares "
            f"{info.file_size} bytes, exceeds limit "
            f"{limits.max_entry_bytes}",
            code="zip_entry_too_large",
        )

    # 4. Cumulative-size guard (zip-bomb).
    new_total = running_uncompressed_total + info.file_size
    if new_total > limits.max_uncompressed_bytes:
        raise BundleSecurityError(
            f"archive uncompressed total exceeds "
            f"{limits.max_uncompressed_bytes} bytes "
            f"(at entry {info.filename!r})",
            code="zip_bomb_total",
        )

    # 5. Compression-ratio guard. compress_size of 0 is legal for empty
    # files — only check when it's non-trivial.
    if info.compress_size > 0:
        ratio = info.file_size / info.compress_size
        if ratio > limits.max_ratio:
            raise BundleSecurityError(
                f"entry {info.filename!r} has implausible compression "
                f"ratio {ratio:.0f}:1 (limit {limits.max_ratio:.0f}:1)",
                code="zip_bomb_ratio",
            )

    # 6. Path normalization (NFC, BiDi strip, drop traversal). Delegated
    # to encoding.normalize_archive_name which raises BundleSecurityError
    # for parent-traversal / absolute / drive-letter / control-char names.
    relpath = normalize_archive_name(info.filename)

    # 7. Final realpath containment check. We don't follow symlinks in
    # the *target* dir at this point because the working directory is
    # newly created by us; but we use realpath to collapse any "."/".."
    # the caller might have left in target_real_dir.
    target_real = os.path.realpath(target_real_dir)
    dest = os.path.realpath(
        os.path.join(target_real, *relpath.split("/"))
    )
    # commonpath raises on different drive letters — treat that as
    # "not contained".
    try:
        common = os.path.commonpath([dest, target_real])
    except ValueError:
        common = ""
    if common != target_real:
        raise BundleSecurityError(
            f"entry {info.filename!r} resolves outside target dir "
            f"({dest!r} not under {target_real!r})",
            code="zip_slip",
        )

    return ValidatedEntry(info=info, relpath=relpath, dest_abspath=dest)


# ──────────────────────────────────────────────────────────────────────
# Convenience: validate every entry, accumulate sizes
# ──────────────────────────────────────────────────────────────────────

def iter_validated_entries(
    zf: zipfile.ZipFile,
    target_dir: str,
    *,
    archive_path: Optional[str] = None,
    limits: SafetyLimits = SafetyLimits(),
) -> Iterable[ValidatedEntry]:
    """Yield :class:`ValidatedEntry` for every file entry in ``zf``.

    All checks are applied; if anything fails the iterator raises and
    the caller gets the partial sequence already yielded. Pre-flight
    archive-shape validation runs once before the first yield, so a
    bomb-style "millions of zero-byte entries" is rejected up front.
    """
    target_real = os.path.realpath(target_dir)
    file_entries = validate_archive_shape(
        zf, archive_path=archive_path, limits=limits
    )
    running = 0
    for info in file_entries:
        ve = validate_entry(
            info, target_real,
            running_uncompressed_total=running,
            limits=limits,
        )
        running += info.file_size
        yield ve
