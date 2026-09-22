import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile
from email.parser import Parser
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_licenses

LICENSES_DIR = ROOT / "licenses"


class FakeDist:
    def __init__(self, name, version, requires=(), files=None,
                 files_root=None):
        self._name = name
        self.version = version
        self._requires = list(requires)
        self.files = [Path(f) for f in (files or [])]
        self._files_root = Path(files_root) if files_root else None
        meta = Parser().parsestr(
            f"Name: {name}\nVersion: {version}\n")
        meta['Requires-Dist'] = None
        self._meta_raw = meta

    @property
    def metadata(self):
        msg = Parser().parsestr(f"Name: {self._name}\nVersion: {self.version}\n")
        for r in self._requires:
            msg['Requires-Dist'] = r
        return msg

    def read_text(self, name):
        return f"Name: {self._name}\nVersion: {self.version}\n"

    def locate_file(self, rel):
        base = self._files_root or Path(tempfile.gettempdir())
        return base / str(rel)


def _fake_distribution(mapping):
    table = {build_licenses.canonicalize_name(k): v
             for k, v in mapping.items()}

    def dist(name):
        key = build_licenses.canonicalize_name(name)
        if key not in table:
            raise build_licenses.metadata.PackageNotFoundError(name)
        return table[key]
    return dist


class TestVendoredLicenses(unittest.TestCase):

    def test_vendor_sha256_matches_origins(self):
        origins = json.loads(
            (LICENSES_DIR / "origins.json").read_text(encoding="utf-8"))
        self.assertGreaterEqual(len(origins), 7)
        for entry in origins:
            path = LICENSES_DIR / entry["file"]
            self.assertTrue(path.is_file(), entry["file"])
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            self.assertEqual(digest, entry["sha256"], entry["file"])
            self.assertTrue(entry["source"], entry["file"])

    def test_gnu_texts_are_complete(self):
        gpl = (LICENSES_DIR / "GPL-3.0.txt").read_text(encoding="utf-8")
        self.assertIn("GNU GENERAL PUBLIC LICENSE", gpl)
        self.assertIn("Version 3", gpl)
        self.assertIn("END OF TERMS AND CONDITIONS", gpl)
        self.assertGreater(len(gpl), 30000)
        agpl = (LICENSES_DIR / "AGPL-3.0.txt").read_text(encoding="utf-8")
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", agpl)
        self.assertIn("END OF TERMS AND CONDITIONS", agpl)
        self.assertGreater(len(agpl), 30000)
        lgpl = (LICENSES_DIR / "LGPL-3.0.txt").read_text(encoding="utf-8")
        self.assertIn("GNU LESSER GENERAL PUBLIC LICENSE", lgpl)


class TestDependencyTraversal(unittest.TestCase):

    def _reqfile(self, td, lines):
        p = Path(td) / "requirements.txt"
        p.write_text("\n".join(lines) + "\n", encoding="utf-8")
        return p

    def test_extras_and_marker_traversal(self):
        dists = {
            "a": FakeDist("a", "1.0", requires=[
                'b; extra == "feat"',
                "c>=1.0",
            ]),
            "b": FakeDist("b", "2.0"),
            "c": FakeDist("c", "1.5", requires=['d[sub]']),
            "d": FakeDist("d", "3.0", requires=['e; extra == "sub"']),
            "e": FakeDist("e", "1.0"),
            "pyinstaller": FakeDist("pyinstaller", "6.0"),
        }
        with tempfile.TemporaryDirectory() as td:
            req = self._reqfile(td, ["a[feat]==1.0",
                                     "never-pkg; sys_platform == 'never'"])
            with mock.patch.object(build_licenses.metadata, "distribution",
                                   _fake_distribution(dists)):
                names = [build_licenses._dist_name(d)
                         for d in build_licenses.dependency_distributions(req)]
        self.assertIn("b", names)
        self.assertIn("e", names)
        self.assertIn("pyinstaller", names)
        self.assertNotIn("never-pkg", names)
        self.assertEqual(names, sorted(names))

        dists2 = dict(dists)
        with tempfile.TemporaryDirectory() as td:
            req = self._reqfile(td, ["a==1.0"])
            with mock.patch.object(build_licenses.metadata, "distribution",
                                   _fake_distribution(dists2)):
                names = [build_licenses._dist_name(d)
                         for d in build_licenses.dependency_distributions(req)]
        self.assertNotIn("b", names)
        self.assertIn("e", names)

    def test_late_constraint_and_base_marker(self):
        dists = {
            "a": FakeDist("a", "1.0", requires=['b[opt]>=2.0']),
            "b": FakeDist("b", "1.5",
                          requires=['c; extra == "opt"',
                                    'd; extra == ""']),
            "c": FakeDist("c", "1.0", requires=["b<2.0"]),
            "d": FakeDist("d", "1.0"),
            "pyinstaller": FakeDist("pyinstaller", "6.0"),
        }
        with tempfile.TemporaryDirectory() as td:
            req = self._reqfile(td, ["a"])
            with mock.patch.object(build_licenses.metadata, "distribution",
                                   _fake_distribution(dists)):
                with self.assertRaises(RuntimeError):
                    build_licenses.dependency_distributions(req)
        dists["b"] = FakeDist("b", "2.5",
                              requires=['c; extra == "opt"',
                                        'd; extra == ""'])
        with tempfile.TemporaryDirectory() as td:
            req = self._reqfile(td, ["a"])
            with mock.patch.object(build_licenses.metadata, "distribution",
                                   _fake_distribution(dists)):
                with self.assertRaises(RuntimeError):
                    build_licenses.dependency_distributions(req)
        dists["c"] = FakeDist("c", "1.0")
        with tempfile.TemporaryDirectory() as td:
            req = self._reqfile(td, ["a"])
            with mock.patch.object(build_licenses.metadata, "distribution",
                                   _fake_distribution(dists)):
                names = [build_licenses._dist_name(d)
                         for d in build_licenses.dependency_distributions(req)]
        self.assertIn("d", names)
        self.assertIn("c", names)

    def test_version_mismatch_and_missing_raise(self):
        dists = {
            "a": FakeDist("a", "0.5"),
            "pyinstaller": FakeDist("pyinstaller", "6.0"),
        }
        with tempfile.TemporaryDirectory() as td:
            req = self._reqfile(td, ["a>=1.0"])
            with mock.patch.object(build_licenses.metadata, "distribution",
                                   _fake_distribution(dists)):
                with self.assertRaises(RuntimeError):
                    build_licenses.dependency_distributions(req)
        with tempfile.TemporaryDirectory() as td:
            req = self._reqfile(td, ["not-installed-pkg"])
            with mock.patch.object(build_licenses.metadata, "distribution",
                                   _fake_distribution(dists)):
                with self.assertRaises(RuntimeError):
                    build_licenses.dependency_distributions(req)


class TestSourceSnapshot(unittest.TestCase):

    def _fake_project(self, td):
        root = Path(td) / "proj"
        (root / "src" / "app").mkdir(parents=True)
        (root / "assets").mkdir()
        (root / "docs").mkdir()
        (root / "licenses").mkdir()
        (root / "src" / "version.py").write_text(
            'APP_VERSION = "9.9.9"\n', encoding="utf-8")
        (root / "src" / "app" / "x.py").write_text("x=1\n",
                                                   encoding="utf-8")
        (root / "src" / "app" / "junk.pyc").write_bytes(b"\x00")
        (root / "assets" / "icon.ico").write_bytes(b"ico")
        (root / "docs" / "guide.md").write_text("g\n", encoding="utf-8")
        (root / "licenses" / "GPL-3.0.txt").write_text("g\n",
                                                      encoding="utf-8")
        (root / "main.py").write_text("m\n", encoding="utf-8")
        (root / "LICENSE").write_text("L\n", encoding="utf-8")
        (root / "NOTICE").write_text("N\n", encoding="utf-8")
        (root / ".env").write_text("SECRET=1\n", encoding="utf-8")
        (root / "extra-root.txt").write_text("e\n", encoding="utf-8")
        (root / "cert.pem").write_text("p\n", encoding="utf-8")
        return root

    def test_allowlist_and_zip(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._fake_project(td)
            files = build_licenses.application_source_files(root)
            resolved = root.resolve()
            rels = {p.resolve().relative_to(resolved).as_posix()
                    for p in files}
            self.assertIn("main.py", rels)
            self.assertIn("src/app/x.py", rels)
            self.assertNotIn(".env", rels)
            self.assertNotIn("cert.pem", rels)
            self.assertNotIn("extra-root.txt", rels)
            self.assertNotIn("src/app/junk.pyc", rels)
            staging = Path(td) / "out"
            staging.mkdir()
            zip_path = build_licenses.create_application_source(
                root, staging)
            self.assertEqual(
                zip_path.name,
                "ImageLayoutManager-9.9.9-application-source.zip")
            with zipfile.ZipFile(zip_path) as zf:
                names = zf.namelist()
                infos = {i.filename: i for i in zf.infolist()}
                main_bytes = zf.read("main.py")
            self.assertIn("main.py", names)
            self.assertNotIn(".env", names)
            self.assertNotIn("extra-root.txt", names)
            self.assertTrue(all(
                i.compress_type == zipfile.ZIP_DEFLATED
                for i in infos.values()))
            self.assertEqual(main_bytes,
                             (root / "main.py").read_bytes())

    def test_version_must_be_filename_safe(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"
            (root / "src").mkdir(parents=True)
            (root / "src" / "version.py").write_text(
                'APP_VERSION = "beta x"\n', encoding="utf-8")
            staging = Path(td) / "out"
            staging.mkdir()
            with self.assertRaises(RuntimeError):
                build_licenses.create_application_source(root, staging)

    def test_symlink_escape_excluded(self):
        with tempfile.TemporaryDirectory() as td:
            root = self._fake_project(td)
            outside = Path(td) / "outside.py"
            outside.write_text("o\n", encoding="utf-8")
            link = root / "src" / "app" / "link.py"
            try:
                os.symlink(outside, link)
            except (OSError, NotImplementedError):
                self.skipTest("symlinks unavailable")
            files = build_licenses.application_source_files(root)
            self.assertNotIn(link.resolve(), [p.resolve() for p in files])

    def test_contained_file_rejects_traversal_and_reparse(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok.txt").write_text("o", encoding="utf-8")
            (root / "sub" / "deep").mkdir(parents=True)
            (root / "sub" / "deep" / "n.txt").write_text("n",
                                                        encoding="utf-8")
            helper = build_licenses._contained_regular_file
            self.assertIsNone(helper(root, "../evil.txt"))
            self.assertIsNone(helper(root, "sub/../../evil.txt"))
            self.assertIsNone(helper(root, str(root.parent / "abs.txt")))
            self.assertIsNone(
                helper(root, str((root / "ok.txt").resolve())))
            self.assertIsNone(helper(root, "Q:/foreign/drive.txt"))
            self.assertIsNone(helper(root, "/etc/passwd"))
            self.assertIsNone(helper(root, 12345))
            self.assertIsNotNone(helper(root, "ok.txt"))
            self.assertIsNotNone(helper(root, "sub/deep/n.txt"))
            real = helper(root, "ok.txt")
            with mock.patch.object(build_licenses, "_is_reparse",
                                   return_value=True):
                self.assertIsNone(helper(root, "ok.txt"))
            with mock.patch.object(Path, "is_symlink", return_value=True):
                self.assertIsNone(helper(root, "ok.txt"))
            with mock.patch.object(Path, "is_junction",
                                   return_value=True, create=True):
                self.assertIsNone(helper(root, "ok.txt"))
            self.assertEqual(real, (root / "ok.txt").resolve())

    def test_vendored_uses_relative_contained_paths(self):
        seen = []
        real = build_licenses._contained_regular_file

        def spy(root, path):
            seen.append(path)
            return real(root, path)

        with mock.patch.object(build_licenses, "_contained_regular_file",
                               spy):
            build_licenses._verify_vendored(LICENSES_DIR)
        for arg in seen:
            self.assertFalse(Path(arg).is_absolute(), arg)
            self.assertNotIn(":", str(arg))

    def test_application_source_files_real_repo(self):
        files = build_licenses.application_source_files(ROOT)
        rels = {p.relative_to(ROOT.resolve()).as_posix() for p in files}
        self.assertIn("main.py", rels)
        self.assertIn("verify_licenses.py", rels)
        self.assertTrue(any(r.startswith("src/app/") for r in rels))
        self.assertTrue(any(r.startswith("licenses/") for r in rels))
        self.assertFalse(any("..'" in r or r.startswith("/")
                             for r in rels))

    def test_output_inside_source_trees_rejected(self):
        for sub in ("src", "assets", "docs", "licenses"):
            with self.subTest(sub=sub):
                with self.assertRaises(RuntimeError):
                    build_licenses.prepare_licenses(ROOT, ROOT / sub / "x")
        with self.assertRaises(RuntimeError):
            build_licenses.prepare_licenses(ROOT, ROOT)


class TestPrepareLicenses(unittest.TestCase):

    def test_prepare_into_fresh_output(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "stage"
            staging = build_licenses.prepare_licenses(ROOT, out)
            self.assertEqual(staging, out.resolve())
            self.assertTrue((staging / "index.html").is_file())
            self.assertTrue((staging / "LICENSE").is_file())
            self.assertTrue((staging / "NOTICE").is_file())
            self.assertTrue((staging / "licenses" / "GPL-3.0.txt")
                            .is_file())
            self.assertTrue((staging / "installed-versions.txt").is_file())
            py = staging / "python"
            self.assertTrue(py.is_dir() and any(py.iterdir()))
            manifest = json.loads(
                (staging / "components.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["schema_version"], 1)
            self.assertEqual(manifest["source_status"], "incomplete")
            self.assertEqual(manifest["scope"], build_licenses.SCOPE)
            self.assertEqual(manifest["pending"], build_licenses.PENDING)
            native = [c["name"] for c in manifest["components"]
                      if "native upstream notices" in (c.get("role") or "")]
            dists = [c["name"] for c in manifest["components"]
                     if c["name"] not in set(native)]
            self.assertEqual(dists, sorted(dists))
            self.assertEqual(native, sorted(native))
            self.assertEqual(
                [c["name"] for c in manifest["components"]],
                dists + native)
            self.assertIn("Qt Base upstream notices", native)
            pymupdf = next(c for c in manifest["components"]
                           if c["name"] == "pymupdf")
            self.assertIn("components/pymupdf/AGPL-3.0.txt",
                          pymupdf["license_files"])
            pyi = next(c for c in manifest["components"]
                       if c["name"] == "pyinstaller")
            self.assertEqual(pyi.get("role"), "build tool")
            mpl = next(c for c in manifest["components"]
                       if c["name"] == "matplotlib")
            self.assertTrue(any("LICENSE_DEJAVU" in f
                                for f in mpl["license_files"]))
            self.assertTrue(any("LICENSE_STIX" in f
                                for f in mpl["license_files"]))
            archive = staging / manifest["application_source_archive"]
            self.assertTrue(archive.is_file())
            self.assertEqual(
                manifest["application_source_sha256"],
                hashlib.sha256(archive.read_bytes()).hexdigest())
            for comp in manifest["components"]:
                for rel in comp["license_files"]:
                    self.assertTrue((staging / rel).is_file(),
                                    f"missing {rel}")
            html_text = (staging / "index.html").read_text(
                encoding="utf-8")
            self.assertIn(build_licenses.TOP_PARAGRAPH, html_text)
            self.assertNotIn("http://", html_text.split("<body>", 1)[0])
            self.assertNotIn("https://", html_text.split("<body>", 1)[0])
            for href in re.findall(r'href="([^"]+)"', html_text):
                self.assertTrue((staging / href).is_file(),
                                f"index href missing: {href}")
            with zipfile.ZipFile(archive) as zf:
                names = zf.namelist()
            self.assertIn("verify_licenses.py", names)
            self.assertIn("build_licenses.py", names)
            self.assertIn("installed-versions.txt", names)

    def test_vendored_tamper_fails_closed(self):
        with tempfile.TemporaryDirectory() as td:
            lic = Path(td) / "licenses"
            shutil.copytree(LICENSES_DIR, lic)
            (lic / "AGPL-3.0.txt").write_text("stub\n", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_licenses._verify_vendored(lic)
        with tempfile.TemporaryDirectory() as td:
            lic = Path(td) / "licenses"
            shutil.copytree(LICENSES_DIR, lic)
            (lic / "GPL-3.0.txt").unlink()
            with self.assertRaises(RuntimeError):
                build_licenses._verify_vendored(lic)
        with tempfile.TemporaryDirectory() as td:
            lic = Path(td) / "licenses"
            shutil.copytree(LICENSES_DIR, lic)
            data = json.loads(
                (lic / "origins.json").read_text(encoding="utf-8"))
            for o in data:
                if o["file"] == "LGPL-3.0.txt":
                    o["sha256"] = "0" * 64
            (lic / "origins.json").write_text(
                json.dumps(data), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_licenses._verify_vendored(lic)
        with tempfile.TemporaryDirectory() as td:
            lic = Path(td) / "licenses"
            shutil.copytree(LICENSES_DIR, lic)
            (lic / "origins.json").unlink()
            with self.assertRaises(RuntimeError):
                build_licenses._verify_vendored(lic)

    def test_missing_root_notice_or_license_fails(self):
        import shutil as _sh
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"
            (root / "src").mkdir(parents=True)
            (root / "src" / "version.py").write_text(
                'APP_VERSION = "1.0.0"\n', encoding="utf-8")
            shutil.copytree(LICENSES_DIR, root / "licenses")
            (root / "LICENSE").write_text("L\n", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_licenses.prepare_licenses(root, Path(td) / "out")

    def test_output_rejects_occupied_dir(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "busy"
            out.mkdir()
            (out / "file.txt").write_text("x", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_licenses.prepare_licenses(ROOT, out)

    def test_no_fallback_for_unknown_version(self):
        self.assertIsNone(build_licenses._verified_fallback(
            "rapidocr", "9.9.9", LICENSES_DIR))
        self.assertIsNone(build_licenses._verified_fallback(
            "flatbuffers", "0.0.0", LICENSES_DIR))
        self.assertIsNotNone(build_licenses._verified_fallback(
            "rapidocr", "3.9.1", LICENSES_DIR))

    def test_sources_md_packaged_and_required(self):
        with tempfile.TemporaryDirectory() as td:
            out = Path(td) / "stage"
            staging = build_licenses.prepare_licenses(ROOT, out)
            self.assertTrue((staging / "SOURCES.md").is_file())
            self.assertEqual(
                (staging / "SOURCES.md").read_bytes(),
                (ROOT / "SOURCES.md").read_bytes())
            html_text = (staging / "index.html").read_text(
                encoding="utf-8")
            self.assertIn('href="SOURCES.md"', html_text)
            self.assertTrue(
                (staging / "licenses" / "sources.json").is_file())
            manifest = json.loads(
                (staging / "components.json").read_text(encoding="utf-8"))
            with zipfile.ZipFile(
                    staging / manifest["application_source_archive"]
                    ) as zf:
                names = zf.namelist()
            self.assertIn("SOURCES.md", names)
            self.assertIn("build_source_index.py", names)
            self.assertIn("verify_source_index.py", names)

    def test_missing_sources_md_fails(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "proj"
            (root / "src").mkdir(parents=True)
            (root / "src" / "version.py").write_text(
                'APP_VERSION = "1.0.0"\n', encoding="utf-8")
            shutil.copytree(LICENSES_DIR, root / "licenses")
            (root / "LICENSE").write_text("L\n", encoding="utf-8")
            (root / "NOTICE").write_text("N\n", encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_licenses.prepare_licenses(root, Path(td) / "out")

    def test_check_release_exits_two(self):
        with tempfile.TemporaryDirectory() as td:
            result = subprocess.run(
                [sys.executable, "build_licenses.py", "--check-release",
                 "--output", str(Path(td) / "stage")],
                cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                errors="replace", timeout=300)
        self.assertEqual(result.returncode, 2)


class TestBuildScriptRouting(unittest.TestCase):

    def test_scripts_include_licenses_dir(self):
        inst = (ROOT / "build_installer_windows.py").read_text(
            encoding="utf-8")
        self.assertIn("prepare_licenses(project_root)", inst)
        self.assertIn('--add-data={legal_dir};licenses', inst)
        self.assertGreaterEqual(
            inst.count("--add-data={legal_dir};licenses"), 2)
        onefile = (ROOT / "build_onefile.py").read_text(encoding="utf-8")
        self.assertIn("prepare_licenses(project_root)", onefile)
        self.assertIn("(str(legal_dir), 'licenses')", onefile)
        macos = (ROOT / "build_onefile_macos.py").read_text(
            encoding="utf-8")
        self.assertIn("prepare_licenses(project_root)", macos)
        self.assertIn("--add-data={legal_dir}:licenses", macos)


class TestLicenseDialog(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
        from PyQt6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def _leaves(self, dlg):
        out = []
        for i in range(dlg._tree.topLevelItemCount()):
            g = dlg._tree.topLevelItem(i)
            for j in range(g.childCount()):
                out.append((g, g.child(j)))
        return out

    def _leaf_labels(self, dlg):
        return [c.text(0) for _g, c in self._leaves(dlg)]

    def _frozen_fixture(self, td, components, origins=None,
                        archive=True):
        root = Path(td) / "licenses"
        root.mkdir()
        (root / "index.html").write_text("<html></html>",
                                         encoding="utf-8")
        (root / "NOTICE").write_text("N", encoding="utf-8")
        (root / "LICENSE").write_text("L", encoding="utf-8")
        (root / "components.json").write_text(
            json.dumps({"components": components}), encoding="utf-8")
        for comp in components:
            for rel in comp["license_files"]:
                f = root / rel
                f.parent.mkdir(parents=True, exist_ok=True)
                f.write_text(f"license text {rel}", encoding="utf-8")
        if origins is not None:
            (root / "licenses").mkdir(exist_ok=True)
            (root / "licenses" / "origins.json").write_text(
                origins if isinstance(origins, str)
                else json.dumps(origins), encoding="utf-8")
        if archive:
            (root / "ImageLayoutManager-9.9.9-application-source.zip"
             ).write_bytes(b"PK\x05\x06" + b"\x00" * 18)
        return root

    def _frozen_dialog(self, td):
        from src.app import license_dialog as ld
        with mock.patch.object(sys, "frozen", True, create=True), \
             mock.patch.object(sys, "_MEIPASS", td, create=True):
            return ld.LicenseDialog()

    def test_dev_mode_renders_local_text_both_languages(self):
        from src.app import i18n
        from src.app.license_dialog import LicenseDialog
        for lang in ("en", "zh"):
            i18n.set_language(lang)
            dlg = LicenseDialog()
            self.assertEqual(dlg.windowTitle(), i18n.tr("licenses_title"))
            self.assertEqual(dlg._tree.topLevelItemCount(), 2)
            self.assertGreater(len(self._leaves(dlg)), 3)
            labels = self._leaf_labels(dlg)
            self.assertIn("NOTICE", labels)
            self.assertTrue(any("GPL-3.0.txt" in l for l in labels))
            notice_leaf = next(
                c for _g, c in self._leaves(dlg)
                if c.text(0) == "NOTICE")
            dlg._tree.setCurrentItem(notice_leaf)
            text = dlg._view.toPlainText()
            self.assertIn("Apache", text)
            self.assertNotIn("<html", text.lower()[:50])
            self.assertIsNone(dlg._archive)
            with mock.patch(
                    "src.app.license_dialog.QDesktopServices.openUrl"
            ) as open_url:
                dlg._open_source()
            open_url.assert_not_called()
            self.assertIn(i18n.tr("licenses_dev_source").split(":")[0],
                          dlg._view.toPlainText())
            dlg.deleteLater()
        i18n.set_language("en")

    def test_frozen_missing_materials_error(self):
        from src.app import license_dialog as ld
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "_MEIPASS", td, create=True):
                dlg = ld.LicenseDialog()
                from PyQt6.QtWidgets import QLabel
                texts = [w.text() for w in dlg.findChildren(QLabel)]
                self.assertTrue(
                    any("missing" in t or "缺少" in t for t in texts))
                dlg.deleteLater()

    def test_frozen_lists_packaged_files_and_archive(self):
        from src.app import license_dialog as ld
        with tempfile.TemporaryDirectory() as td:
            self._frozen_fixture(td, [
                {"name": "dep", "version": "1.0",
                 "license_files": ["components/dep/METADATA.txt"]}])
            dlg = self._frozen_dialog(td)
            self.assertIsNotNone(dlg._archive)
            group_labels = [dlg._tree.topLevelItem(i).text(0)
                            for i in range(dlg._tree.topLevelItemCount())]
            self.assertTrue(any("dep 1.0" in l for l in group_labels))
            with mock.patch.object(ld.QDesktopServices, "openUrl"
                                   ) as open_url:
                dlg._open_source()
            open_url.assert_called_once()
            dlg.deleteLater()

    def test_safe_join_rejects_bad_inputs(self):
        from src.app.license_dialog import _safe_join
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "ok.txt").write_text("o", encoding="utf-8")
            self.assertIsNone(_safe_join(root, "../x"))
            self.assertIsNone(_safe_join(root, "sub/../../x"))
            self.assertIsNone(_safe_join(root, str(root.parent / "a.txt")))
            self.assertIsNone(_safe_join(root, "/etc/passwd"))
            self.assertIsNone(_safe_join(root, 123))
            self.assertIsNone(_safe_join(root, None))
            self.assertIsNotNone(_safe_join(root, "ok.txt"))
            with mock.patch("src.app.license_dialog._is_reparse",
                            return_value=True):
                self.assertIsNone(_safe_join(root, "ok.txt"))

    def test_frozen_malformed_manifest_shows_missing(self):
        from src.app import license_dialog as ld
        from PyQt6.QtWidgets import QLabel
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "licenses"
            root.mkdir()
            (root / "index.html").write_text("<html></html>",
                                             encoding="utf-8")
            (root / "components.json").write_text(
                json.dumps([1, 2, 3]), encoding="utf-8")
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "_MEIPASS", td, create=True):
                dlg = ld.LicenseDialog()
                texts = [w.text() for w in dlg.findChildren(QLabel)]
                self.assertTrue(
                    any("missing" in t or "缺少" in t for t in texts))
                self.assertFalse(dlg._source_btn.isEnabled())
                dlg.deleteLater()

    def test_frozen_no_archive_disables_source_button(self):
        from src.app import license_dialog as ld
        from PyQt6.QtWidgets import QLabel
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "licenses"
            root.mkdir()
            (root / "index.html").write_text("<html></html>",
                                             encoding="utf-8")
            (root / "NOTICE").write_text("N", encoding="utf-8")
            (root / "LICENSE").write_text("L", encoding="utf-8")
            (root / "components.json").write_text(json.dumps({
                "components": []}), encoding="utf-8")
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "_MEIPASS", td, create=True):
                dlg = ld.LicenseDialog()
                self.assertIsNone(dlg._archive)
                self.assertFalse(dlg._source_btn.isEnabled())
                dlg.deleteLater()

    def test_frozen_missing_manifest_warns(self):
        from src.app import license_dialog as ld
        from PyQt6.QtWidgets import QLabel
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / "licenses"
            root.mkdir()
            (root / "index.html").write_text("<html></html>",
                                             encoding="utf-8")
            (root / "NOTICE").write_text("N", encoding="utf-8")
            (root / "LICENSE").write_text("L", encoding="utf-8")
            with mock.patch.object(sys, "frozen", True, create=True), \
                 mock.patch.object(sys, "_MEIPASS", td, create=True):
                dlg = ld.LicenseDialog()
                texts = [w.text() for w in dlg.findChildren(QLabel)]
                self.assertTrue(
                    any("missing" in t or "缺少" in t for t in texts))
                dlg.deleteLater()

    def test_frozen_tree_groups_and_counts(self):
        with tempfile.TemporaryDirectory() as td:
            comps = [
                {"name": "dep1", "version": "1.0",
                 "license_files": ["components/dep1/LICENSE.txt",
                                   "licenses/native/qt/aa.txt"]},
                {"name": "dep2", "version": "2.0",
                 "license_files": ["components/dep2/LICENCE",
                                   "licenses/native/qt/aa.txt"]},
            ]
            self._frozen_fixture(td, comps)
            dlg = self._frozen_dialog(td)
            self.assertEqual(dlg._tree.topLevelItemCount(), 4)
            for i in range(dlg._tree.topLevelItemCount()):
                g = dlg._tree.topLevelItem(i)
                self.assertGreater(g.childCount(), 0)
                self.assertFalse(g.isExpanded()
                                 and g.text(0) != "This application")
            from PyQt6.QtCore import Qt
            leaves = self._leaves(dlg)
            paths = {c.data(0, Qt.ItemDataRole.UserRole)
                     for _g, c in leaves}
            self.assertEqual(len(leaves), len(paths))
            self.assertEqual(len(leaves), 6)
            cur = dlg._tree.currentItem()
            self.assertIsNotNone(cur)
            self.assertIsNotNone(cur.parent())
            self.assertTrue(dlg._view.toPlainText())
            dlg.deleteLater()

    def test_frozen_component_group_summary(self):
        with tempfile.TemporaryDirectory() as td:
            comps = [{"name": "dep1", "version": "1.0",
                      "role": "build tool",
                      "project_urls": ["https://example.test"],
                      "license_files": ["components/dep1/LICENSE.txt"]}]
            self._frozen_fixture(td, comps)
            dlg = self._frozen_dialog(td)
            group = next(
                dlg._tree.topLevelItem(i)
                for i in range(dlg._tree.topLevelItemCount())
                if "dep1" in dlg._tree.topLevelItem(i).text(0))
            self.assertIn("1 file", group.text(0))
            self.assertNotIn("1 files", group.text(0))
            dlg._tree.setCurrentItem(group)
            text = dlg._view.toPlainText()
            self.assertIn("dep1", text)
            self.assertIn("1.0", text)
            self.assertIn("build tool", text)
            self.assertIn("https://example.test", text)
            dlg.deleteLater()

    def test_frozen_malformed_origins_still_works(self):
        for origins in ("{not json", json.dumps([1, "x", None])):
            with self.subTest(origins=origins):
                with tempfile.TemporaryDirectory() as td:
                    comps = [{"name": "dep1", "version": "1.0",
                              "license_files": [
                                  "licenses/native/qt/aa.txt"]}]
                    self._frozen_fixture(td, comps, origins=origins)
                    dlg = self._frozen_dialog(td)
                    from PyQt6.QtWidgets import QLabel
                    texts = [w.text() for w in dlg.findChildren(QLabel)]
                    self.assertFalse(
                        any("missing" in t or "缺少" in t
                            for t in texts))
                    leaf = dlg._tree.topLevelItem(1).child(0)
                    self.assertEqual(leaf.text(0), "aa.txt")
                    self.assertEqual(leaf.toolTip(0),
                                     "licenses/native/qt/aa.txt")
                    dlg._tree.setCurrentItem(leaf)
                    self.assertIn("aa.txt", dlg._view.toPlainText())
                    dlg.deleteLater()

    def test_frozen_origins_labels_and_zh(self):
        from src.app import i18n
        i18n.set_language("zh")
        try:
            with tempfile.TemporaryDirectory() as td:
                comps = [{"name": "dep1", "version": "1.0",
                          "license_files": ["licenses/native/qt/aa.txt"]}]
                origins = [{"file": "native/qt/aa.txt",
                            "source": "https://example.test/a.zip",
                            "sha256": "0" * 64,
                            "archive_member":
                                "qt-src-1.0/LICENSES/BSD.txt"}]
                self._frozen_fixture(td, comps, origins=origins)
                dlg = self._frozen_dialog(td)
                self.assertEqual(dlg._tree.topLevelItem(0).text(0),
                                 "本应用")
                leaf = dlg._tree.topLevelItem(1).child(0)
                self.assertEqual(leaf.text(0), "LICENSES/BSD.txt")
                self.assertEqual(leaf.toolTip(0),
                                 "licenses/native/qt/aa.txt")
                self.assertIn("1 个文件",
                              dlg._tree.topLevelItem(1).text(0))
                other = dlg._tree.topLevelItem(2)
                self.assertEqual(other.text(0), "其他随附材料")
                dlg.deleteLater()
        finally:
            i18n.set_language("en")

    def test_zh_labels_and_no_network(self):
        from src.app import i18n
        from src.app import license_dialog as ld
        i18n.set_language("zh")
        try:
            def _boom(*a, **k):
                raise AssertionError("network access attempted")
            with mock.patch("urllib.request.urlopen", _boom):
                dlg = ld.LicenseDialog()
                self.assertEqual(dlg.windowTitle(), "许可协议与源码")
                from PyQt6.QtWidgets import QPushButton
                texts = [b.text() for b in dlg.findChildren(QPushButton)]
                self.assertIn("打开应用源码所在位置", texts)
                self.assertIn("代码仓库", texts)
                first = dlg._tree.topLevelItem(0).child(0)
                dlg._tree.setCurrentItem(first)
                self.assertTrue(dlg._view.toPlainText())
                dlg.deleteLater()
        finally:
            i18n.set_language("en")


class TestNativeNoticesAndExtraOrigins(unittest.TestCase):

    def _licenses_copy(self, td, extra_files=(), extra_entries=()):
        lic = Path(td) / "licenses"
        lic.mkdir()
        origins = json.loads(
            (LICENSES_DIR / "origins.json").read_text(encoding="utf-8"))
        keep = [e for e in origins if "component" not in e]
        for e in keep:
            dest = lic / e["file"]
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LICENSES_DIR / e["file"], dest)
        (lic / "origins.json").write_text(json.dumps(keep),
                                         encoding="utf-8")
        for rel, data in extra_files:
            dest = lic / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(data)
        if extra_entries:
            (lic / "origins.json").write_text(
                json.dumps(keep + list(extra_entries)), encoding="utf-8")
        return lic

    def _entry(self, file, data, **kw):
        e = {"file": file, "source": "https://example.test/src.tar.gz",
             "sha256": hashlib.sha256(data).hexdigest()}
        e.update(kw)
        return e

    def test_extra_origin_verified_and_tamper_rejected(self):
        data = b"extra vendored license text\n"
        with tempfile.TemporaryDirectory() as td:
            lic = self._licenses_copy(
                td, [("extra-notice.txt", data)],
                [self._entry("extra-notice.txt", data)])
            build_licenses._verify_vendored(lic)
            (lic / "extra-notice.txt").write_bytes(b"tampered\n")
            with self.assertRaises(RuntimeError):
                build_licenses._verify_vendored(lic)

    def test_invalid_origins_shapes_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            lic = self._licenses_copy(td)
            origins = json.loads(
                (lic / "origins.json").read_text(encoding="utf-8"))
            dup = dict(origins[0])
            (lic / "origins.json").write_text(
                json.dumps(origins + [dup]), encoding="utf-8")
            with self.assertRaises(RuntimeError):
                build_licenses._verify_vendored(lic)
        for bad in ('{"file": "x"}', '[42]', '[{"file": "x",'
                    ' "source": "", "sha256": "abc"}]'):
            with self.subTest(bad=bad):
                with tempfile.TemporaryDirectory() as td:
                    lic = self._licenses_copy(td)
                    (lic / "origins.json").write_text(
                        bad, encoding="utf-8")
                    with self.assertRaises(RuntimeError):
                        build_licenses._verify_vendored(lic)

    def test_native_grouping_and_bindings(self):
        data1, data2 = b"qt notice A\n", b"qt notice B\n"
        binding = {"kind": "distribution", "name": "ExampleQt",
                   "version": "6.11.2"}
        entries = [
            self._entry("native/qt/aa-LICENSE.txt", data1,
                        component="Qt Base source notices",
                        component_version="6.11.2", platform="win32",
                        binding=binding),
            self._entry("native/qt/bb-LICENSE.txt", data2,
                        component="Qt Base source notices",
                        component_version="6.11.2",
                        binding=binding),
            self._entry("native/mac/cc-LICENSE.txt", b"mac only\n",
                        component="Mac Only", component_version="1.0",
                        platform="darwin",
                        binding={"kind": "bogus"}),
        ]
        with tempfile.TemporaryDirectory() as td:
            lic = self._licenses_copy(
                td,
                [("native/qt/aa-LICENSE.txt", data1),
                 ("native/qt/bb-LICENSE.txt", data2),
                 ("native/mac/cc-LICENSE.txt", b"mac only\n")],
                entries)
            build_licenses._verify_vendored(lic)
            real_dist = build_licenses.metadata.distribution

            def fake(name):
                if build_licenses.canonicalize_name(name) == "exampleqt":
                    return FakeDist("ExampleQt", "6.11.2")
                return real_dist(name)

            with mock.patch.object(build_licenses.metadata,
                                   "distribution", fake):
                comps = build_licenses._native_notice_components(lic)
            self.assertEqual(len(comps), 1)
            comp = comps[0]
            self.assertEqual(comp["name"], "Qt Base source notices")
            self.assertEqual(comp["version"], "6.11.2")
            self.assertEqual(
                comp["role"],
                "native upstream notices; may include optional "
                "source components")
            self.assertIsNone(comp["license_expression"])
            self.assertEqual(
                comp["license_files"],
                ["licenses/native/qt/aa-LICENSE.txt",
                 "licenses/native/qt/bb-LICENSE.txt"])
            self.assertEqual(comp["project_urls"],
                             ["https://example.test/src.tar.gz"])
            for rel in comp["license_files"]:
                self.assertTrue((lic.parent / rel).is_file(), rel)

            def bad_ver(name):
                if build_licenses.canonicalize_name(name) == "exampleqt":
                    return FakeDist("ExampleQt", "0.0.0")
                return real_dist(name)

            with mock.patch.object(build_licenses.metadata,
                                   "distribution", bad_ver):
                with self.assertRaises(RuntimeError):
                    build_licenses._native_notice_components(lic)

            def missing(name):
                raise build_licenses.metadata.PackageNotFoundError(name)

            with mock.patch.object(build_licenses.metadata,
                                   "distribution", missing):
                with self.assertRaises(RuntimeError):
                    build_licenses._native_notice_components(lic)

    def test_runtime_file_binding(self):
        data = b"runtime license\n"
        lib = b"fake dll bytes\n"
        entries = [
            self._entry(
                "native/rt/dd-LICENSE.txt", data,
                component="Runtime Lib", component_version="1.0",
                platform=sys.platform,
                binding={"kind": "runtime_file",
                         "path": "Library/bin/libfake.dll",
                         "sha256": hashlib.sha256(lib).hexdigest()}),
        ]
        with tempfile.TemporaryDirectory() as td:
            lic = self._licenses_copy(
                td, [("native/rt/dd-LICENSE.txt", data)], entries)
            prefix = Path(td) / "env"
            target = prefix / "Library" / "bin" / "libfake.dll"
            target.parent.mkdir(parents=True)
            target.write_bytes(lib)
            with mock.patch.object(sys, "prefix", str(prefix)):
                comps = build_licenses._native_notice_components(lic)
            self.assertEqual(len(comps), 1)
            target.write_bytes(b"different\n")
            with mock.patch.object(sys, "prefix", str(prefix)):
                with self.assertRaises(RuntimeError):
                    build_licenses._native_notice_components(lic)

    def test_additional_requirements_and_pyinstaller_deps(self):
        dists = {
            "a": FakeDist("a", "1.0"),
            "extra": FakeDist("extra", "2.0", requires=["bootdep>=1"]),
            "bootdep": FakeDist("bootdep", "1.2"),
            "pyinstaller": FakeDist("pyinstaller", "6.0",
                                    requires=["bootdep>=1"]),
        }
        with tempfile.TemporaryDirectory() as td:
            req = Path(td) / "requirements.txt"
            req.write_text("a==1.0\n", encoding="utf-8")
            with mock.patch.object(build_licenses.metadata,
                                   "distribution",
                                   _fake_distribution(dists)):
                names = [build_licenses._dist_name(d) for d in
                         build_licenses.dependency_distributions(
                             req, extra_requirements=["extra==2"])]
            self.assertIn("extra", names)
            self.assertIn("bootdep", names)
            self.assertIn("pyinstaller", names)
            dists["bootdep"] = FakeDist("bootdep", "0.5")
            with mock.patch.object(build_licenses.metadata,
                                   "distribution",
                                   _fake_distribution(dists)):
                with self.assertRaises(RuntimeError):
                    build_licenses.dependency_distributions(
                        req, extra_requirements=["extra==2"])

    def test_index_native_role_and_links(self):
        data = b"native text\n"
        binding = {"kind": "distribution", "name": "PyInstaller",
                   "version": None}
        with tempfile.TemporaryDirectory() as td:
            import importlib.metadata as im
            binding["version"] = im.version("pyinstaller")
            lic = self._licenses_copy(
                td, [("native/qt/aa-LICENSE.txt", data)],
                [self._entry("native/qt/aa-LICENSE.txt", data,
                             component="Qt Base source notices",
                             component_version="6.11.2",
                             platform=sys.platform, binding=binding)])
            root = Path(td) / "proj"
            (root / "src").mkdir(parents=True)
            (root / "src" / "version.py").write_text(
                'APP_VERSION = "1.0.0"\n', encoding="utf-8")
            (root / "requirements.txt").write_text("", encoding="utf-8")
            (root / "LICENSE").write_text("L\n", encoding="utf-8")
            (root / "NOTICE").write_text("N\n", encoding="utf-8")
            (root / "SOURCES.md").write_text("S\n", encoding="utf-8")
            shutil.copytree(lic, root / "licenses")
            staging = build_licenses.prepare_licenses(
                root, Path(td) / "out")
            manifest = json.loads(
                (staging / "components.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["source_status"], "incomplete")
            native = next(c for c in manifest["components"]
                          if c["name"] == "Qt Base source notices")
            self.assertIn("native upstream notices", native["role"])
            html_text = (staging / "index.html").read_text(
                encoding="utf-8")
            self.assertIn("native upstream notices", html_text)
            native_li = next(
                line for line in html_text.splitlines()
                if "Qt Base source notices" in line)
            self.assertNotIn("build tool", native_li)
            for href in re.findall(r'href="([^"]+)"', html_text):
                self.assertTrue((staging / href).is_file(),
                                f"index href missing: {href}")


class _BadStrMeta:
    def __init__(self, msg):
        self._m = msg

    def __getattr__(self, key):
        return getattr(self._m, key)

    def __getitem__(self, key):
        return self._m[key]

    def __str__(self):
        from email.errors import HeaderParseError
        raise HeaderParseError("embedded header")


class _EggDist(FakeDist):
    def __init__(self, name, version, pkg_info, **kw):
        super().__init__(name, version, **kw)
        self._pkg_info = pkg_info

    @property
    def metadata(self):
        return _BadStrMeta(super().metadata)

    def read_text(self, name):
        if name == "METADATA":
            return None
        if name == "PKG-INFO":
            return self._pkg_info
        return None


class TestMetadataFallbackAndBindingCache(unittest.TestCase):

    def test_pkg_info_fallback(self):
        pkg_info = ("Name: eggpkg\nVersion: 1.0\nLicense: MIT\n"
                    "Project-URL: Home, https://example.test\n"
                    "Description: embedded\n\nheaders\n")
        with tempfile.TemporaryDirectory() as td:
            files_root = Path(td) / "site-packages"
            (files_root / "eggpkg").mkdir(parents=True)
            (files_root / "eggpkg" / "LICENSE.txt").write_text(
                "MIT text\n", encoding="utf-8")
            (files_root / "pyi").mkdir()
            (files_root / "pyi" / "LICENSE.txt").write_text(
                "GPL text\n", encoding="utf-8")
            dists = {
                "eggpkg": _EggDist("eggpkg", "1.0", pkg_info,
                                   files=["eggpkg/LICENSE.txt"],
                                   files_root=files_root),
                "pyinstaller": FakeDist(
                    "pyinstaller", "6.0",
                    files=["pyi/LICENSE.txt"], files_root=files_root),
            }
            root = Path(td) / "proj"
            (root / "src").mkdir(parents=True)
            (root / "src" / "version.py").write_text(
                'APP_VERSION = "1.0.0"\n', encoding="utf-8")
            (root / "requirements.txt").write_text("eggpkg\n",
                                                  encoding="utf-8")
            (root / "LICENSE").write_text("L\n", encoding="utf-8")
            (root / "NOTICE").write_text("N\n", encoding="utf-8")
            (root / "SOURCES.md").write_text("S\n", encoding="utf-8")
            origins = json.loads((LICENSES_DIR / "origins.json")
                                 .read_text(encoding="utf-8"))
            keep = [e for e in origins if "component" not in e]
            (root / "licenses").mkdir()
            for e in keep:
                shutil.copy2(LICENSES_DIR / e["file"],
                             root / "licenses" / e["file"])
            (root / "licenses" / "origins.json").write_text(
                json.dumps(keep), encoding="utf-8")
            with mock.patch.object(build_licenses.metadata,
                                   "distribution",
                                   _fake_distribution(dists)):
                staging = build_licenses.prepare_licenses(
                    root, Path(td) / "out")
            meta = (staging / "components" / "eggpkg"
                    / "METADATA.txt").read_text(encoding="utf-8")
            self.assertEqual(meta, pkg_info)

    def test_binding_verified_once_per_call(self):
        data1, data2 = b"notice one\n", b"notice two\n"
        lib = b"fake dll bytes\n"
        binding = {"kind": "runtime_file",
                   "path": "Library/bin/libfake.dll",
                   "sha256": hashlib.sha256(lib).hexdigest()}
        entries = [
            {"file": "native/rt/aa-LICENSE.txt",
             "source": "https://example.test/a.tar.gz",
             "sha256": hashlib.sha256(data1).hexdigest(),
             "component": "Runtime Lib", "component_version": "1.0",
             "binding": dict(binding)},
            {"file": "native/rt/bb-LICENSE.txt",
             "source": "https://example.test/a.tar.gz",
             "sha256": hashlib.sha256(data2).hexdigest(),
             "component": "Runtime Lib", "component_version": "1.0",
             "binding": dict(binding)},
        ]
        with tempfile.TemporaryDirectory() as td:
            lic = Path(td) / "licenses"
            lic.mkdir()
            for e, d in zip(entries, (data1, data2)):
                dest = lic / e["file"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(d)
            origins = json.loads(
                (LICENSES_DIR / "origins.json").read_text(encoding="utf-8"))
            keep = [e for e in origins if "component" not in e]
            for e in keep:
                dest = lic / e["file"]
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(LICENSES_DIR / e["file"], dest)
            (lic / "origins.json").write_text(
                json.dumps(keep + entries), encoding="utf-8")
            prefix = Path(td) / "env"
            target = prefix / "Library" / "bin" / "libfake.dll"
            target.parent.mkdir(parents=True)
            target.write_bytes(lib)
            calls = []
            real = build_licenses._contained_regular_file

            def spy(root, path):
                calls.append(str(path))
                return real(root, path)

            with mock.patch.object(sys, "prefix", str(prefix)), \
                 mock.patch.object(build_licenses,
                                   "_contained_regular_file", spy):
                comps = build_licenses._native_notice_components(lic)
            self.assertEqual(len(comps), 1)
            self.assertEqual(len(comps[0]["license_files"]), 2)
            self.assertEqual(
                calls.count("Library/bin/libfake.dll"), 1)
            target.write_bytes(b"different\n")
            with mock.patch.object(sys, "prefix", str(prefix)):
                with self.assertRaises(RuntimeError):
                    build_licenses._native_notice_components(lic)


if __name__ == "__main__":
    unittest.main()
