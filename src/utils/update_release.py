"""Release-manifest parsing and installer download/verify (Qt-free).

``latest.json`` may carry an optional ``"windows_installer"`` block:
``{"url": "https://…/ImageLayoutManager_Setup_<ver>.exe",
   "sha256": "<64 hex>", "size": <bytes>}``.
Only well-formed entries produce an ``Installer`` — anything else falls
back to link-only update notices.
"""

import hashlib
import os
import re
import urllib.request
from dataclasses import dataclass
from typing import Optional

_SHA_RE = re.compile(r"^[0-9a-f]{64}$")
_CHUNK = 256 * 1024


def parse_version(v: str):
    """Return a tuple of ints for simple semver comparison, ignoring leading 'v'."""
    v = v.lstrip("vV")
    try:
        return tuple(int(x) for x in v.split("."))
    except ValueError:
        return (0,)


def is_newer(latest: str, current: str) -> bool:
    return parse_version(latest) > parse_version(current)


def should_notify(latest: str, current: str, skipped: str) -> bool:
    """True when *latest* is newer and the user didn't skip that version."""
    return is_newer(latest, current) and latest != skipped


@dataclass
class Installer:
    url: str
    sha256: str
    size: int


@dataclass
class Release:
    version: str
    page_url: str
    installer: Optional[Installer] = None


def parse_release(data: dict) -> Optional[Release]:
    """Build a Release from latest.json content, or None without a version."""
    version = data.get("version") or data.get("tag_name") or ""
    if not version:
        return None
    page_url = data.get("url") or data.get("html_url") or ""
    installer = None
    block = data.get("windows_installer")
    if isinstance(block, dict):
        url = block.get("url") or ""
        sha = str(block.get("sha256") or "").lower()
        size = block.get("size")
        if (isinstance(url, str) and url.startswith("https://")
                and _SHA_RE.match(sha)
                and isinstance(size, int) and not isinstance(size, bool)
                and size > 0):
            installer = Installer(url, sha, size)
    return Release(version=version, page_url=page_url, installer=installer)


def cached_installer_path(cache_dir: str, version: str) -> str:
    return os.path.join(cache_dir, "updates",
                        f"ImageLayoutManager_Setup_{version}.exe")


def verify_file(path: str, sha256: str, size: int) -> bool:
    """True when *path* has exactly *size* bytes and the given SHA-256."""
    try:
        if os.path.getsize(path) != size:
            return False
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(1 << 20), b""):
                h.update(chunk)
        return h.hexdigest() == sha256
    except OSError:
        return False


class DownloadError(Exception):
    """Download failed; ``code`` is "network" | "size" | "hash"."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


class DownloadCancelled(Exception):
    pass


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def download_installer(installer: Installer, dest: str, progress=None,
                       cancel=None, opener=urllib.request.urlopen) -> str:
    """Stream *installer.url* to *dest* via a ``dest + '.part'`` temp file.

    ``progress(done, total)`` is called after each 256 KiB chunk;
    ``cancel.is_set()`` aborts with ``DownloadCancelled``; oversize/hash
    mismatches raise ``DownloadError``; network failures become
    ``DownloadError("network")``.  On success the file lands at *dest*
    (``os.replace``) and its path is returned.
    """
    part = dest + ".part"
    os.makedirs(os.path.dirname(part) or ".", exist_ok=True)
    done = 0
    h = hashlib.sha256()
    resp = None
    try:
        req = urllib.request.Request(
            installer.url,
            headers={"User-Agent": "AcademicFigureLayout-UpdateChecker"})
        resp = opener(req, timeout=30)
        with open(part, "wb") as f:
            while True:
                if cancel is not None and cancel.is_set():
                    raise DownloadCancelled()
                chunk = resp.read(_CHUNK)
                if not chunk:
                    break
                done += len(chunk)
                if done > installer.size:
                    raise DownloadError("size")
                f.write(chunk)
                h.update(chunk)
                if progress:
                    progress(done, installer.size)
        if done != installer.size:
            raise DownloadError("size")
        if h.hexdigest() != installer.sha256:
            raise DownloadError("hash")
        os.replace(part, dest)
        return dest
    except (DownloadCancelled, DownloadError):
        _remove(part)
        raise
    except Exception as exc:
        _remove(part)
        raise DownloadError("network") from exc
    finally:
        if resp is not None:
            try:
                resp.close()
            except Exception:
                pass
