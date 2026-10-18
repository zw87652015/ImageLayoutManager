"""Qt-free tests for the distribution-aware update flow."""

import hashlib
import io
import os
import sys
import tempfile
import threading
import unittest

from src.utils import distribution
from src.utils.distribution import install_channel
from src.utils.update_release import (
    DownloadCancelled, DownloadError, Installer, cached_installer_path,
    download_installer, is_newer, parse_release, parse_version,
    should_notify, verify_file,
)

PAYLOAD = b"setup-bytes" * 1000
SHA = hashlib.sha256(PAYLOAD).hexdigest()
SIZE = len(PAYLOAD)


def _release_dict(installer=None):
    data = {"version": "9.9.9", "url": "https://example.com/page"}
    if installer is not None:
        data["windows_installer"] = installer
    return data


class ParseReleaseTest(unittest.TestCase):
    def test_valid(self):
        rel = parse_release(_release_dict(
            {"url": "https://x/i.exe", "sha256": SHA.upper(), "size": SIZE}))
        self.assertEqual(rel.version, "9.9.9")
        self.assertEqual(rel.page_url, "https://example.com/page")
        self.assertEqual(rel.installer.sha256, SHA)  # lower-cased
        self.assertEqual(rel.installer.size, SIZE)

    def test_http_url_rejected(self):
        rel = parse_release(_release_dict(
            {"url": "http://x/i.exe", "sha256": SHA, "size": SIZE}))
        self.assertIsNone(rel.installer)

    def test_bad_sha_rejected(self):
        rel = parse_release(_release_dict(
            {"url": "https://x/i.exe", "sha256": "zz", "size": SIZE}))
        self.assertIsNone(rel.installer)

    def test_invalid_installer_fields(self):
        for block in ({"url": "https://x", "sha256": SHA, "size": -1},
                      {"url": "https://x", "sha256": SHA, "size": "12"},
                      {"url": "https://x", "size": SIZE},
                      {"sha256": SHA, "size": SIZE}):
            with self.subTest(block=block):
                self.assertIsNone(parse_release(_release_dict(block)).installer)

    def test_no_installer_block(self):
        rel = parse_release(_release_dict())
        self.assertIsNone(rel.installer)

    def test_no_version(self):
        self.assertIsNone(parse_release({"url": "https://x"}))
        self.assertIsNone(parse_release({}))
        self.assertIsNotNone(parse_release({"tag_name": "v1.2"}))


class VersionCompareTest(unittest.TestCase):
    def test_parse_version(self):
        self.assertEqual(parse_version("v3.7.0"), (3, 7, 0))
        self.assertEqual(parse_version("x"), (0,))

    def test_is_newer(self):
        self.assertTrue(is_newer("3.8", "3.7.0"))
        self.assertFalse(is_newer("3.7.0", "3.7.0"))
        self.assertFalse(is_newer("3.6", "3.7.0"))

    def test_should_notify(self):
        self.assertTrue(should_notify("3.8", "3.7.0", ""))
        self.assertFalse(should_notify("3.8", "3.7.0", "3.8"))
        self.assertFalse(should_notify("3.6", "3.7.0", ""))


class InstallChannelTest(unittest.TestCase):
    def setUp(self):
        self._env = os.environ.get("ILM_INSTALL_CHANNEL")
        self._platform = sys.platform
        self._frozen = getattr(sys, "frozen", None)

    def tearDown(self):
        if self._env is None:
            os.environ.pop("ILM_INSTALL_CHANNEL", None)
        else:
            os.environ["ILM_INSTALL_CHANNEL"] = self._env
        sys.platform = self._platform
        if self._frozen is None:
            try:
                del sys.frozen
            except AttributeError:
                pass
        else:
            sys.frozen = self._frozen

    def test_env_override(self):
        os.environ["ILM_INSTALL_CHANNEL"] = "store"
        self.assertEqual(install_channel(), "store")

    def test_env_ignored_when_invalid(self):
        os.environ["ILM_INSTALL_CHANNEL"] = "bogus"
        sys.platform = "linux"
        self.assertEqual(install_channel(), "source")

    def test_store_when_packaged(self):
        os.environ.pop("ILM_INSTALL_CHANNEL", None)
        sys.platform = "win32"
        sys.frozen = True

        class K32:
            @staticmethod
            def GetCurrentPackageFullName(_len, _buf):
                return 122

        class WinDLL:
            kernel32 = K32

        orig = getattr(sys.modules.get("ctypes"), "windll", None)
        import ctypes
        ctypes.windll = WinDLL
        try:
            self.assertEqual(install_channel(), "store")
        finally:
            ctypes.windll = orig

    def test_not_packaged_frozen_win32(self):
        os.environ.pop("ILM_INSTALL_CHANNEL", None)
        sys.platform = "win32"
        sys.frozen = True

        class K32:
            @staticmethod
            def GetCurrentPackageFullName(_len, _buf):
                return 15700

        class WinDLL:
            kernel32 = K32

        import ctypes
        orig = ctypes.windll
        ctypes.windll = WinDLL
        try:
            self.assertEqual(install_channel(), "installer")
        finally:
            ctypes.windll = orig

    def test_kernel32_exception_falls_through(self):
        os.environ.pop("ILM_INSTALL_CHANNEL", None)
        sys.platform = "win32"
        sys.frozen = False

        class K32:
            @staticmethod
            def GetCurrentPackageFullName(_len, _buf):
                raise OSError("nope")

        class WinDLL:
            kernel32 = K32

        import ctypes
        orig = ctypes.windll
        ctypes.windll = WinDLL
        try:
            self.assertEqual(install_channel(), "source")
        finally:
            ctypes.windll = orig

    def test_frozen_darwin(self):
        os.environ.pop("ILM_INSTALL_CHANNEL", None)
        sys.platform = "darwin"
        sys.frozen = True
        self.assertEqual(install_channel(), "macos")


class PathsTest(unittest.TestCase):
    def test_cached_installer_path(self):
        self.assertEqual(
            cached_installer_path("/c", "3.7.0"),
            os.path.join("/c", "updates", "ImageLayoutManager_Setup_3.7.0.exe"))

    def test_verify_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = os.path.join(td, "i.exe")
            with open(p, "wb") as f:
                f.write(PAYLOAD)
            self.assertTrue(verify_file(p, SHA, SIZE))
            self.assertFalse(verify_file(p, SHA, SIZE + 1))
            self.assertFalse(verify_file(p, "0" * 64, SIZE))
            self.assertFalse(verify_file(p + ".missing", SHA, SIZE))


class _Resp:
    def __init__(self, data, chunk=None):
        self._io = io.BytesIO(data)
        self._chunk = chunk

    def read(self, n):
        if self._chunk is not None:
            return self._io.read(min(n, self._chunk))
        return self._io.read(n)

    def close(self):
        pass


def _opener(data, chunk=None, fails=None):
    def open_(req, timeout=None):
        if fails is not None:
            raise fails
        return _Resp(data, chunk)
    return open_


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.td = tempfile.TemporaryDirectory()
        self.dest = os.path.join(self.td.name, "setup.exe")
        self.inst = Installer("https://x/i.exe", SHA, SIZE)

    def tearDown(self):
        self.td.cleanup()

    def test_success(self):
        calls = []
        out = download_installer(
            self.inst, self.dest, progress=lambda d, t: calls.append(d),
            opener=_opener(PAYLOAD, chunk=1024))
        self.assertEqual(out, self.dest)
        with open(self.dest, "rb") as f:
            self.assertEqual(f.read(), PAYLOAD)
        self.assertFalse(os.path.exists(self.dest + ".part"))
        self.assertTrue(calls)
        self.assertEqual(calls[-1], SIZE)

    def test_hash_mismatch(self):
        inst = Installer("https://x/i.exe", "0" * 64, SIZE)
        with self.assertRaises(DownloadError) as ctx:
            download_installer(inst, self.dest, opener=_opener(PAYLOAD))
        self.assertEqual(ctx.exception.code, "hash")
        self.assertFalse(os.path.exists(self.dest))
        self.assertFalse(os.path.exists(self.dest + ".part"))

    def test_oversize_aborts_early(self):
        inst = Installer("https://x/i.exe", "0" * 64, SIZE - 1)
        with self.assertRaises(DownloadError) as ctx:
            download_installer(inst, self.dest, opener=_opener(PAYLOAD))
        self.assertEqual(ctx.exception.code, "size")
        self.assertFalse(os.path.exists(self.dest + ".part"))

    def test_cancel(self):
        cancel = threading.Event()

        def progress(done, total):
            cancel.set()

        with self.assertRaises(DownloadCancelled):
            download_installer(self.inst, self.dest, progress=progress,
                               cancel=cancel, opener=_opener(PAYLOAD, chunk=64))
        self.assertFalse(os.path.exists(self.dest + ".part"))
        self.assertFalse(os.path.exists(self.dest))

    def test_network_error(self):
        with self.assertRaises(DownloadError) as ctx:
            download_installer(self.inst, self.dest,
                               opener=_opener(b"", fails=OSError("down")))
        self.assertEqual(ctx.exception.code, "network")
        self.assertFalse(os.path.exists(self.dest + ".part"))


if __name__ == "__main__":
    unittest.main()
