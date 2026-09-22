import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_licenses
import build_msix

REPO_VERSION = build_licenses._app_version(ROOT)
IDENTITY = 'Example.ImageLayoutManager'
PUBLISHER = 'CN=00000000-0000-0000-0000-000000000000'
DISPLAY = 'Escapes & <chars> "quoted"'

NS = {'': 'http://schemas.microsoft.com/appx/manifest/foundation/windows10',
      'uap': 'http://schemas.microsoft.com/appx/manifest/uap/windows10',
      'uap3': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/3',
      'uap5': 'http://schemas.microsoft.com/appx/manifest/uap/windows10/5',
      'desktop4':
          'http://schemas.microsoft.com/appx/manifest/desktop/windows10/4',
      'rescap':
          'http://schemas.microsoft.com/appx/manifest/foundation/'
          'windows10/restrictedcapabilities'}


def _fake_bundle(td):
    bundle = Path(td) / 'bundle'
    internal = bundle / '_internal' / 'licenses'
    internal.mkdir(parents=True)
    (bundle / 'ImageLayoutManager.exe').write_bytes(b'exe')
    (bundle / 'imagelayout-cli.exe').write_bytes(b'cli')
    (internal / 'components.json').write_text(json.dumps(
        {'source_status': 'incomplete',
         'app_version': REPO_VERSION}), encoding='utf-8')
    return bundle


class TestMsixVersion(unittest.TestCase):

    def test_valid(self):
        self.assertEqual(build_msix.msix_version('3.4.2'), '3.4.2.0')
        self.assertEqual(build_msix.msix_version('1.2.3.0'), '1.2.3.0')

    def test_invalid(self):
        for bad in ('3.4', '3.4.2.1', '0.1.2', '65536.1.2', '1.2.3.4.5',
                    'a.b.c', '../1.2.3', '1.2.x', ''):
            with self.subTest(bad=bad):
                with self.assertRaises(ValueError):
                    build_msix.msix_version(bad)


class TestManifest(unittest.TestCase):

    def test_structure_and_escaping(self):
        xml_text = build_msix.build_manifest(IDENTITY, PUBLISHER, DISPLAY,
                                             '3.4.2.0')
        root = ET.fromstring(xml_text)
        ident = root.find('Identity', NS)
        self.assertEqual(ident.get('Name'), IDENTITY)
        self.assertEqual(ident.get('Publisher'), PUBLISHER)
        self.assertEqual(ident.get('Version'), '3.4.2.0')
        self.assertEqual(ident.get('ProcessorArchitecture'), 'x64')
        pdn = root.find('Properties/PublisherDisplayName', NS)
        self.assertEqual(pdn.text, DISPLAY)
        self.assertIn('&amp;', xml_text)
        langs = [r.get('Language')
                 for r in root.findall('Resources/Resource', NS)]
        self.assertEqual(langs, ['en-us', 'zh-cn'])
        app = root.find('Applications/Application', NS)
        self.assertEqual(app.get('EntryPoint'),
                         'Windows.FullTrustApplication')
        self.assertEqual(app.get('Executable'),
                         'App\\ImageLayoutManager.exe')
        self.assertEqual(
            app.get(f'{{{NS["desktop4"]}}}SupportsMultipleInstances'),
            'true')
        assoc = app.find(
            'Extensions/uap3:Extension/uap3:FileTypeAssociation', NS)
        self.assertIsNotNone(assoc)
        self.assertEqual(assoc.get('Parameters'), '"%1"')
        types = [f.text for f in assoc.findall(
            'uap:SupportedFileTypes/uap:FileType', NS)]
        self.assertEqual(types, ['.figlayout', '.figpack'])
        alias = app.find('Extensions/uap5:Extension', NS)
        self.assertEqual(alias.get('Executable'), 'App\\imagelayout-cli.exe')
        aea = alias.find('uap5:AppExecutionAlias', NS)
        self.assertEqual(aea.get(f'{{{NS["desktop4"]}}}Subsystem'),
                         'console')
        cap = root.find('Capabilities/rescap:Capability', NS)
        self.assertIsNotNone(cap)
        self.assertEqual(cap.get('Name'), 'runFullTrust')


class TestLayoutAndRejects(unittest.TestCase):

    def test_output_and_containment_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = _fake_bundle(td)
            out = Path(td) / 'existing'
            out.mkdir()
            code = build_msix.main([
                '--bundle', str(bundle), '--output', str(out),
                '--identity-name', IDENTITY, '--publisher', PUBLISHER,
                '--publisher-display-name', DISPLAY])
            self.assertEqual(code, 1)
            out2 = bundle / 'inner'
            code = build_msix.main([
                '--bundle', str(bundle), '--output', str(out2),
                '--identity-name', IDENTITY, '--publisher', PUBLISHER,
                '--publisher-display-name', DISPLAY])
            self.assertEqual(code, 1)
            self.assertFalse(out2.exists())
            out3 = Path(td) / 'outer'
            inner = _fake_bundle(str(out3))
            code = build_msix.main([
                '--bundle', str(inner), '--output', str(out3),
                '--identity-name', IDENTITY, '--publisher', PUBLISHER,
                '--publisher-display-name', DISPLAY])
            self.assertEqual(code, 1)
            self.assertFalse((out3 / 'layout').exists())

    def _run(self, bundle, out):
        return build_msix.main([
            '--bundle', str(bundle), '--output', str(out),
            '--identity-name', IDENTITY, '--publisher', PUBLISHER,
            '--publisher-display-name', DISPLAY])

    def test_missing_exe_and_licenses_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = Path(td) / 'bundle'
            bundle.mkdir()
            (bundle / 'ImageLayoutManager.exe').write_bytes(b'x')
            out = Path(td) / 'o'
            self.assertEqual(self._run(bundle, out), 1)
            self.assertFalse(out.exists())
        with tempfile.TemporaryDirectory() as td:
            bundle = _fake_bundle(td)
            (bundle / 'ImageLayoutManager.exe').unlink()
            out = Path(td) / 'o'
            self.assertEqual(self._run(bundle, out), 1)
            self.assertFalse(out.exists())

    def test_missing_cli_exe_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = _fake_bundle(td)
            (bundle / 'imagelayout-cli.exe').unlink()
            out = Path(td) / 'o'
            self.assertEqual(self._run(bundle, out), 1)
            self.assertFalse(out.exists())

    def test_reparse_bundle_member_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = _fake_bundle(td)
            with mock.patch.object(build_msix, '_is_reparse',
                                   return_value=True):
                out = Path(td) / 'o'
                self.assertEqual(self._run(bundle, out), 1)
                self.assertFalse(out.exists())

    def test_directory_reparse_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = _fake_bundle(td)
            real_dir = (bundle / '_internal').resolve()
            real = build_msix._is_reparse
            with mock.patch.object(
                    build_msix, '_is_reparse',
                    lambda p: True if Path(p).resolve() == real_dir
                    else real(p)):
                out = Path(td) / 'o'
                self.assertEqual(self._run(bundle, out), 1)
                self.assertFalse(out.exists())

    def test_root_reparse_rejected(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = _fake_bundle(td)
            real = build_msix._is_reparse
            with mock.patch.object(
                    build_msix, '_is_reparse',
                    lambda p: True if p == bundle.absolute() else real(p)):
                out = Path(td) / 'o'
                self.assertEqual(self._run(bundle, out), 1)
                self.assertFalse(out.exists())

    def test_malformed_manifest_rejected(self):
        cases = [
            '[1, 2]',
            '{bad json',
            json.dumps({'source_status': 'incomplete',
                        'app_version': '9.9.9'}),
            json.dumps({'source_status': 'incomplete'}),
            json.dumps({'source_status': 'complete',
                        'app_version': REPO_VERSION}),
        ]
        for text in cases:
            with self.subTest(text=text):
                with tempfile.TemporaryDirectory() as td:
                    bundle = _fake_bundle(td)
                    (bundle / '_internal' / 'licenses'
                     / 'components.json').write_text(
                        text, encoding='utf-8')
                    out = Path(td) / 'o'
                    self.assertEqual(self._run(bundle, out), 1)
                    self.assertFalse(out.exists())

    def test_layout_only_without_makeappx(self):
        with tempfile.TemporaryDirectory() as td:
            bundle = _fake_bundle(td)
            out = Path(td) / 'msix'
            code = build_msix.main([
                '--bundle', str(bundle), '--output', str(out),
                '--identity-name', IDENTITY, '--publisher', PUBLISHER,
                '--publisher-display-name', DISPLAY])
            self.assertEqual(code, 0)
            layout = out / 'layout'
            manifest = ET.parse(layout / 'AppxManifest.xml').getroot()
            self.assertEqual(
                manifest.find('Identity', NS).get('Version'),
                build_msix.msix_version(REPO_VERSION))
            self.assertTrue(
                (layout / 'App' / 'ImageLayoutManager.exe').is_file())
            self.assertTrue((layout / 'AppxManifest.xml').is_file())
            self.assertTrue(
                (layout / 'Assets' / 'StoreLogo.png').is_file())
            self.assertEqual(
                len(list(out.glob('*.msix'))), 0)


class TestInstallerIsolation(unittest.TestCase):

    def test_onedir_only_args_and_no_iscc(self):
        import build_installer_windows as biw
        captured = []

        def fake_prepare(project_root, output=None,
                         additional_requirements=()):
            self.assertEqual(list(additional_requirements), ['extrapkg'])
            d = Path(output)
            d.mkdir(parents=True, exist_ok=True)
            (d / 'index.html').write_text('x', encoding='utf-8')
            return d

        def fake_run(args, *, isolated, runner):
            self.assertTrue(isolated)
            captured.append(list(args))
            name = next(a.split('=', 1)[1] for a in args
                        if a.startswith('--name='))
            dist = Path(next(a.split('=', 1)[1] for a in args
                             if a.startswith('--distpath='))) / name
            dist.mkdir(parents=True, exist_ok=True)
            (dist / f'{name}.exe').write_bytes(b'x')
            (dist / '_internal').mkdir(exist_ok=True)

        with tempfile.TemporaryDirectory() as td:
            out_root = Path(td) / 'fresh-out'
            with mock.patch.object(biw, 'ensure_iscc',
                                   side_effect=AssertionError(
                                       'ensure_iscc called')), \
                 mock.patch.object(biw, 'run_pyinstaller', fake_run), \
                 mock.patch.dict(sys.modules,
                                 {'build_licenses': mock.Mock(
                                     prepare_licenses=fake_prepare)}):
                code = biw.main(['--onedir-only',
                                 '--output-root', str(out_root),
                                 '--additional-requirement', 'extrapkg'])
            self.assertEqual(code, 0)
            self.assertGreaterEqual(len(captured), 1)
            for args in captured:
                self.assertNotIn('--clean', args)
                self.assertNotIn('--noconfirm', args)
                self.assertNotIn('--collect-binaries=PyQt6', args)
                self.assertNotIn('--collect-data=PyQt6', args)
                self.assertNotIn('--hidden-import=shiboken6', args)
                self.assertNotIn('--collect-submodules=matplotlib',
                                 args)
                distpaths = [a for a in args
                             if a.startswith('--distpath=')]
                self.assertTrue(any(d.endswith('\\dist')
                                    for d in distpaths))
                self.assertTrue(any(a.startswith('--specpath=')
                                    for a in args))
                self.assertTrue(any(a.startswith('--workpath=')
                                    for a in args))
            self.assertTrue(
                (out_root / 'dist' / 'ImageLayoutManager').is_dir())

    def test_isolated_build_environment(self):
        import build_installer_windows as biw
        with tempfile.TemporaryDirectory() as td:
            prefix = Path(td) / 'env'
            (prefix / 'Library' / 'bin').mkdir(parents=True)
            win = Path(td) / 'Windows'
            (win / 'System32').mkdir(parents=True)
            foreign = Path(td) / 'foreign-bin'
            foreign.mkdir()
            sentinel_env = {
                'PATH': os.pathsep.join(
                    [str(foreign), str(prefix / 'Library' / 'bin')]),
                'SystemRoot': str(win),
                'PYTHONPATH': str(foreign),
                'QT_PLUGIN_PATH': str(foreign),
            }
            before = os.environ.copy()
            with mock.patch.dict(os.environ, sentinel_env,
                                 clear=True), \
                 mock.patch.object(sys, 'prefix', str(prefix)):
                env = biw.isolated_build_environment()
            self.assertEqual(os.environ, before)
            self.assertNotIn('PYTHONPATH', env)
            self.assertNotIn('QT_PLUGIN_PATH', env)
            self.assertEqual(env['CONDA_PREFIX'], str(prefix))
            parts = env['PATH'].split(os.pathsep)
            self.assertNotIn(str(foreign), parts)
            self.assertIn(str(prefix / 'Library' / 'bin'), parts)
            self.assertIn(str(win / 'System32'), parts)

    def test_run_pyinstaller_isolated_subprocess(self):
        import build_installer_windows as biw
        calls = []
        with mock.patch.object(biw.subprocess, 'run',
                               lambda *a, **k: calls.append((a, k))):
            biw.run_pyinstaller(['--onedir', 'x.py'], isolated=True,
                                runner=lambda a: None)
        self.assertEqual(len(calls), 1)
        cmd = calls[0][0][0]
        self.assertEqual(cmd[:3],
                         [sys.executable, '-m', 'PyInstaller'])
        self.assertTrue(calls[0][1].get('check'))
        self.assertIsInstance(calls[0][1].get('env'), dict)

    def test_argument_guards(self):
        import build_installer_windows as biw
        with self.assertRaises(SystemExit):
            biw.main(['--output-root', 'x'])
        with self.assertRaises(SystemExit):
            biw.main(['--onedir-only'])
        with self.assertRaises(SystemExit):
            biw.main(['--additional-requirement', 'pip'])


class TestSourceSnapshotIncludesNewFiles(unittest.TestCase):

    def test_new_scripts_in_root_files(self):
        import build_licenses
        for name in ('build_msix.py', 'verify_msix.py',
                     'audit_release.py', 'verify_release_audit.py'):
            self.assertIn(name, build_licenses.ROOT_FILES)
        files = build_licenses.application_source_files(ROOT)
        rels = {p.relative_to(ROOT.resolve()).as_posix() for p in files}
        self.assertIn('build_msix.py', rels)
        self.assertIn('verify_msix.py', rels)


if __name__ == '__main__':
    unittest.main()
