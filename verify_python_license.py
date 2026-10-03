"""Non-UI checks for build_licenses._python_interpreter_license().

Patches sys.prefix/sys.base_prefix/sysconfig.get_path and restricts
Path.is_file to a TemporaryDirectory so ancestor scans cannot observe
license files on the real filesystem.
"""

import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import build_licenses

PSF_TEXT = b'Python Software Foundation License Version 2\n'
OTHER_TEXT = b'Apache License\nVersion 2.0, January 2004\n'

_REAL_IS_FILE = Path.is_file
_REAL_GET_PATH = sysconfig.get_path


def _within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except ValueError:
        return False


class PythonInterpreterLicenseTests(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name)

    def _run(self, base_prefix, prefix, stdlib):
        root = self.root

        def fake_is_file(self):
            return _within(self, root) and _REAL_IS_FILE(self)

        def fake_get_path(name, *args, **kwargs):
            if name == 'stdlib':
                return str(stdlib)
            return _REAL_GET_PATH(name, *args, **kwargs)

        with mock.patch.object(sys, 'base_prefix', str(base_prefix)), \
                mock.patch.object(sys, 'prefix', str(prefix)), \
                mock.patch.object(sysconfig, 'get_path', fake_get_path), \
                mock.patch.object(Path, 'is_file', fake_is_file):
            return build_licenses._python_interpreter_license()

    def _toolchain(self):
        """CI-like layout: toolcache base_prefix, distinct venv prefix."""
        base = self.root / 'toolcache' / 'Python' / '3.13.0' / 'x64'
        prefix = self.root / 'venv'
        stdlib = base / 'lib' / 'python3.13'
        for d in (base, prefix, stdlib):
            d.mkdir(parents=True, exist_ok=True)
        return base, prefix, stdlib

    def _license(self, path: Path, text: bytes = PSF_TEXT) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(text)
        return path

    def test_license_txt_at_prefix(self):
        base = self.root / 'python'
        base.mkdir()
        expected = self._license(base / 'LICENSE.txt')
        self.assertEqual(self._run(base, base, base / 'lib'), expected)

    def test_license_python_txt_at_prefix(self):
        base = self.root / 'python'
        base.mkdir()
        expected = self._license(base / 'LICENSE_PYTHON.txt')
        self.assertEqual(self._run(base, base, base / 'lib'), expected)

    def test_stdlib_license_txt(self):
        base, prefix, stdlib = self._toolchain()
        expected = self._license(stdlib / 'LICENSE.txt')
        self.assertEqual(self._run(base, prefix, stdlib), expected)

    def test_stdlib_license(self):
        base, prefix, stdlib = self._toolchain()
        expected = self._license(stdlib / 'LICENSE')
        self.assertEqual(self._run(base, prefix, stdlib), expected)

    def test_homebrew_ancestor_license(self):
        formula = self.root / 'Cellar' / 'python@3.13' / '3.13.11'
        base = (formula / 'Frameworks' / 'Python.framework'
                / 'Versions' / '3.13')
        base.mkdir(parents=True)
        expected = self._license(formula / 'LICENSE')
        self.assertEqual(self._run(base, base, base / 'lib'), expected)

    def test_unrelated_prefix_license_rejected_stdlib_selected(self):
        base, prefix, stdlib = self._toolchain()
        self._license(prefix / 'LICENSE.txt', OTHER_TEXT)
        self._license(base / 'LICENSE.txt', OTHER_TEXT)
        expected = self._license(stdlib / 'LICENSE.txt')
        self.assertEqual(self._run(base, prefix, stdlib), expected)

    def test_no_valid_license_returns_none(self):
        base, prefix, stdlib = self._toolchain()
        self._license(prefix / 'LICENSE.txt', OTHER_TEXT)
        self.assertIsNone(self._run(base, prefix, stdlib))

    def test_prefix_preferred_over_stdlib(self):
        base, prefix, stdlib = self._toolchain()
        expected = self._license(prefix / 'LICENSE.txt')
        self._license(stdlib / 'LICENSE.txt')
        self.assertEqual(self._run(base, prefix, stdlib), expected)


if __name__ == '__main__':
    unittest.main()
