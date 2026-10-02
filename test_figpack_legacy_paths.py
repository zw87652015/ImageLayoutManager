"""Regression: legacy figpack bundles whose project.json still carries raw
original (non-``figpack:`` marker) image paths — e.g. a mapped-drive ``U:\\…``
path while the manifest recorded the UNC form ``\\\\server\\share\\…``.
"""

import hashlib
import json
import os
import sys
import tempfile
import unittest
import zipfile
from unittest.mock import patch

from src.utils.figpack.errors import BundleError, BundleSecurityError
from src.utils.figpack.package_manager import (
    PROJECT_JSON, METADATA_JSON, FIGPACK_FORMAT_VERSION,
    unpack_project, _resolve_resource_paths,
)

ROOT = os.path.dirname(os.path.abspath(__file__))

UNC = '\\\\fakeserver-xyz\\share_root\\Photos\\DJI\\'
DRIVE = 'U:/Photos/DJI/'


def _jpeg(tag: bytes) -> bytes:
    import io
    from PIL import Image
    img = Image.new('RGB', (8, 8))
    img.putpixel((0, 0), (tag[0], 40, 90))
    buf = io.BytesIO()
    img.save(buf, format='JPEG')
    return buf.getvalue()


def _project(cells):
    return {
        'schema_version': 4,
        'typography_mode': 'points',
        'cells': cells,
    }


def _cell(cid, image_path=None, children=None, pips=None, osp=None):
    return {
        'id': cid,
        'image_path': image_path,
        'original_source_path': osp,
        'children': children or [],
        'pip_items': pips or [],
    }


def _pip(pid, image_path, pip_type='external'):
    return {'id': pid, 'pip_type': pip_type, 'image_path': image_path}


def _write_bundle(path, project_data, manifest, assets):
    meta = {
        'figpack_format_version': FIGPACK_FORMAT_VERSION,
        'manifest': manifest,
    }
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(PROJECT_JSON, json.dumps(project_data).encode('utf-8'))
        zf.writestr(METADATA_JSON, json.dumps(meta).encode('utf-8'))
        for ap, data in assets.items():
            zf.writestr(ap, data)


def _record(rid, archive_path, orig, data, status='ok'):
    return {
        'archive_path': archive_path,
        'original_source_path': orig,
        'sha256': hashlib.sha256(data).hexdigest(),
        'size_bytes': len(data),
        'status': status,
    }


def _guard_fake_sources():
    """Fail loudly if the loader ever touches a fake original path."""
    real_exists = os.path.exists
    real_isfile = os.path.isfile
    real_realpath = os.path.realpath

    def is_fake(p):
        s = str(p).upper().replace('/', '\\')
        return (s.startswith('U:\\') or s.startswith('V:\\')
                or 'FAKESERVER' in s)

    def check(fn):
        def wrapped(p, *a, **k):
            if is_fake(p):
                raise AssertionError(f'probed original path: {p!r}')
            return fn(p, *a, **k)
        return wrapped

    return patch.multiple(
        os.path,
        exists=check(real_exists),
        isfile=check(real_isfile),
        realpath=check(real_realpath),
    )


class LegacyPathResolutionTests(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = self._tmp.name
        self.bundle = os.path.join(self.root, 'in.figpack')
        self.out = os.path.join(self.root, 'out')

    def _unpack(self):
        with _guard_fake_sources():
            return unpack_project(self.bundle, self.out)

    def test_mapped_drive_to_unc_nested_and_pip(self):
        img = _jpeg(b'A')
        manifest = {'res_1': _record(
            'res_1', 'assets/h1/one.JPG', UNC + 'one.JPG', img)}
        proj = _project([
            _cell('outer', children=[
                _cell('inner', image_path=DRIVE + 'one.JPG'),
            ]),
            _cell('host', image_path=DRIVE + 'one.JPG',
                  pips=[
                      _pip('p1', DRIVE + 'one.JPG'),
                      _pip('pz', None, pip_type='zoom'),
                  ]),
        ])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/h1/one.JPG': img})
        res = self._unpack()
        self.assertEqual(res.missing_count, 0)
        inner = res.project_data['cells'][0]['children'][0]
        host = res.project_data['cells'][1]
        target = os.path.join(os.path.realpath(self.out),
                              'assets', 'h1', 'one.JPG')
        for holder in (inner, host, host['pip_items'][0]):
            self.assertEqual(holder['image_path'], target)
            self.assertEqual(holder['original_source_path'],
                             UNC + 'one.JPG')
        self.assertIsNone(host['pip_items'][1]['image_path'])
        with open(target, 'rb') as f:
            self.assertEqual(f.read(), img)

    def test_exact_lexical_variants(self):
        img = _jpeg(b'B')
        cases = {
            'res_u': (UNC + 'two.JPG', 'assets/h2/two.JPG',
                      '\\\\fakeserver-xyz\\share_root\\Photos\\DJI\\two.JPG'),
            'res_s': (UNC + 'three.JPG', 'assets/h3/three.JPG',
                      '//fakeserver-xyz/share_root/photos/dji/three.jpg'),
        }
        manifest = {rid: _record(rid, ap, orig, img)
                    for rid, (orig, ap, _ip) in cases.items()}
        proj = _project([
            _cell('c_u', image_path=cases['res_u'][2]),
            _cell('c_s', image_path=cases['res_s'][2]),
        ])
        _write_bundle(self.bundle, proj, manifest,
                      {v[1]: img for v in cases.values()})
        res = self._unpack()
        self.assertEqual(res.missing_count, 0)
        self.assertTrue(res.project_data['cells'][0]['image_path']
                        .endswith('two.JPG'))
        self.assertTrue(res.project_data['cells'][1]['image_path']
                        .endswith('three.JPG'))

    def test_posix_paths_case_sensitive(self):
        img = _jpeg(b'C')
        manifest = {'res_p': _record(
            'res_p', 'assets/hp/photo.jpg', '/home/u/photos/photo.jpg', img)}
        proj = _project([
            _cell('ok', image_path='/home/u/photos/photo.jpg'),
            _cell('nocase', image_path='/Home/U/Photos/Photo.JPG'),
        ])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/hp/photo.jpg': img})
        res = self._unpack()
        cells = res.project_data['cells']
        self.assertTrue(cells[0]['image_path'].endswith('photo.jpg'))
        self.assertEqual(cells[1]['image_path'],
                         '/Home/U/Photos/Photo.JPG')

    def test_markers_still_resolve(self):
        img = _jpeg(b'D')
        manifest = {'res_m': _record(
            'res_m', 'assets/hm/m.jpg', 'C:\\orig\\m.jpg', img)}
        proj = _project([_cell('m', image_path='figpack:res_m')])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/hm/m.jpg': img})
        res = self._unpack()
        cell = res.project_data['cells'][0]
        self.assertTrue(cell['image_path'].endswith('m.jpg'))
        self.assertEqual(res.missing_count, 0)

    def test_missing_marker_and_missing_status(self):
        img = _jpeg(b'E')
        manifest = {'res_bad': _record(
            'res_bad', 'assets/hb/b.jpg', UNC + 'b.jpg', img,
            status='missing')}
        proj = _project([
            _cell('gone', image_path='figpack:res_absent'),
            _cell('bad', image_path='figpack:res_bad'),
            _cell('leg_missing', image_path=DRIVE + 'b.jpg'),
        ])
        _write_bundle(self.bundle, proj, manifest, {})
        res = self._unpack()
        cells = res.project_data['cells']
        self.assertIsNone(cells[0]['image_path'])
        self.assertIsNone(cells[1]['image_path'])
        self.assertEqual(cells[1]['original_source_path'], UNC + 'b.jpg')
        self.assertIsNone(cells[2]['image_path'])
        self.assertEqual(cells[2]['original_source_path'], UNC + 'b.jpg')
        self.assertEqual(res.missing_count, 3)

    def test_ambiguous_alias_raises(self):
        img = _jpeg(b'F')
        manifest = {
            'r1': _record('r1', 'assets/h1/x.JPG', UNC + 'x.JPG', img),
            'r2': _record('r2', 'assets/h2/x.JPG',
                          '\\\\othersrv\\other\\Photos\\DJI\\x.JPG', img),
        }
        proj = _project([_cell('c', image_path=DRIVE + 'x.JPG')])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/h1/x.JPG': img, 'assets/h2/x.JPG': img})
        with self.assertRaises(BundleError) as cm:
            self._unpack()
        self.assertEqual(cm.exception.code, 'ambiguous_resource')

    def test_same_basename_different_dirs_no_match(self):
        img = _jpeg(b'G')
        manifest = {'r1': _record(
            'r1', 'assets/h1/y.JPG', UNC + 'y.JPG', img)}
        proj = _project([
            _cell('c', image_path='U:/Other/Dir/y.JPG'),
            _cell('d',
                  image_path='\\\\othersrv\\other\\Photos\\DJI\\y.JPG'),
        ])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/h1/y.JPG': img})
        res = self._unpack()
        cells = res.project_data['cells']
        self.assertEqual(cells[0]['image_path'], 'U:/Other/Dir/y.JPG')
        self.assertEqual(cells[1]['image_path'],
                         '\\\\othersrv\\other\\Photos\\DJI\\y.JPG')
        self.assertEqual(res.missing_count, 0)

    def test_drive_relative_and_drive_to_drive_no_alias(self):
        img = _jpeg(b'R')
        manifest = {
            'r1': _record('r1', 'assets/h1/rel.JPG', UNC + 'rel.JPG', img),
            'r2': _record('r2', 'assets/h2/d.JPG',
                          'V:\\Photos\\DJI\\d.JPG', img),
        }
        proj = _project([
            _cell('rel', image_path='U:Photos\\DJI\\rel.JPG'),
            _cell('d2d', image_path='U:/Photos/DJI/d.JPG'),
        ])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/h1/rel.JPG': img, 'assets/h2/d.JPG': img})
        res = self._unpack()
        cells = res.project_data['cells']
        self.assertEqual(cells[0]['image_path'], 'U:Photos\\DJI\\rel.JPG')
        self.assertEqual(cells[1]['image_path'], 'U:/Photos/DJI/d.JPG')
        self.assertEqual(res.missing_count, 0)

    def test_image_path_alias_beats_stale_sticky_alias(self):
        img = _jpeg(b'S')
        manifest = {
            'r1': _record('r1', 'assets/h1/x.JPG', UNC + 'x.JPG', img),
            'r2': _record('r2', 'assets/h2/y.JPG',
                          '\\\\othersrv\\other\\Photos\\DJI\\y.JPG', img),
        }
        proj = _project([
            _cell('c', image_path=DRIVE + 'x.JPG',
                  osp='V:\\Photos\\DJI\\y.JPG'),
        ])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/h1/x.JPG': img, 'assets/h2/y.JPG': img})
        res = self._unpack()
        cell = res.project_data['cells'][0]
        self.assertTrue(cell['image_path'].endswith('x.JPG'))
        self.assertEqual(cell['original_source_path'], UNC + 'x.JPG')
        self.assertEqual(res.missing_count, 0)

    def test_malicious_archive_path_rejected(self):
        img = _jpeg(b'H')
        for bad in ('../outside.jpg', 'C:/evil.jpg', '/abs/e.jpg'):
            manifest = {'r1': _record('r1', bad, UNC + 'z.JPG', img)}
            proj = _project([_cell('c', image_path=DRIVE + 'z.JPG')])
            _write_bundle(self.bundle, proj, manifest, {})
            with self.assertRaises(BundleSecurityError, msg=bad):
                self._unpack()

    def test_original_source_path_exact_match(self):
        img = _jpeg(b'I')
        manifest = {'r1': _record(
            'r1', 'assets/h1/o.JPG', UNC + 'o.JPG', img)}
        proj = _project([_cell('c', image_path='E:/elsewhere/o.JPG',
                               osp=UNC + 'o.JPG')])
        _write_bundle(self.bundle, proj, manifest,
                      {'assets/h1/o.JPG': img})
        res = self._unpack()
        cell = res.project_data['cells'][0]
        self.assertTrue(cell['image_path'].endswith('o.JPG'))


class PackUnpackRoundtripTests(unittest.TestCase):

    def test_marker_bundle_roundtrip_unchanged(self):
        from src.model.data_model import Cell, Project
        from src.utils.figpack.package_manager import pack_project
        with tempfile.TemporaryDirectory() as tmp:
            src = os.path.realpath(os.path.join(tmp, 'panel.jpg'))
            with open(src, 'wb') as f:
                f.write(_jpeg(b'Z'))
            project = Project()
            cell = Cell()
            cell.image_path = src
            project.cells = [cell]
            bundle = os.path.join(tmp, 'rt.figpack')
            pack_project(project, bundle)
            out = os.path.join(tmp, 'out')
            res = unpack_project(bundle, out)
            self.assertEqual(res.missing_count, 0)
            cell_d = res.project_data['cells'][0]
            real_out = os.path.realpath(out)
            self.assertTrue(os.path.realpath(cell_d['image_path'])
                            .startswith(real_out + os.sep))
            with open(cell_d['image_path'], 'rb') as f:
                extracted = f.read()
            with open(src, 'rb') as f:
                self.assertEqual(extracted, f.read())
            self.assertEqual(cell_d['original_source_path'], src)
            loaded = Project.from_dict(res.project_data)
            leaves = loaded.get_all_leaf_cells()
            self.assertEqual(len(leaves), 1)
            from PIL import Image
            with Image.open(leaves[0].image_path) as im, \
                    Image.open(src) as source:
                self.assertEqual(im.size, (8, 8))
                self.assertEqual(im.convert('RGB').getpixel((0, 0)),
                                 source.convert('RGB').getpixel((0, 0)))


_CHILD_SRC = r'''
import faulthandler
import runpy
import sys

faulthandler.dump_traceback_later(15, repeat=True)

BUNDLE = sys.argv[1]
SETTINGS_DIR = sys.argv[2]

from PyQt6.QtCore import QSettings, QTimer, Qt
from PyQt6.QtWidgets import QApplication

QSettings.setDefaultFormat(QSettings.Format.IniFormat)
QSettings.setPath(QSettings.Format.IniFormat, QSettings.Scope.UserScope,
                  SETTINGS_DIR)

REAL_EXEC = QApplication.exec


def exec_probe():
    def tick():
        try:
            app = QApplication.instance()
            mw = next((w for w in app.topLevelWidgets()
                       if w.__class__.__name__ == 'MainWindow'), None)
            if mw is None or getattr(mw, 'project', None) is None:
                QTimer.singleShot(1000, tick)
                return
            if not mw.testAttribute(
                    Qt.WidgetAttribute.WA_DeleteOnClose):
                print('MISSING_WA_DELETE_ON_CLOSE', flush=True)
                app.exit(2)
                return
            cells = mw.project.get_all_leaf_cells()
            tabs = getattr(mw, '_tabs', [])
            wd = getattr(tabs[0], 'bundle_workdir', None) if tabs else None
            import os
            root = os.path.realpath(wd.path) if wd is not None else ''
            with_img = [c for c in cells if c.image_path]
            inside = [c for c in with_img
                      if root and os.path.realpath(c.image_path)
                      .startswith(root + os.sep)]
            from src.utils.image_proxy import get_image_proxy
            proxy = get_image_proxy()
            pending = len(proxy._loading)
            cached = sum(1 for c in with_img if c.image_path in proxy._cache)
            print('HEARTBEAT: leaf_cells={} inside_workdir={} '
                  'loading={} cached={}'.format(
                      len(cells), len(inside), pending, cached),
                  flush=True)
            if (len(with_img) == 8 and len(inside) == 8
                    and pending == 0 and cached == 8):
                print('DONE: resolved and cached', flush=True)
                mw.close()
                QTimer.singleShot(500, app.quit)
                return
            QTimer.singleShot(1000, tick)
        except Exception:
            import traceback
            traceback.print_exc()
            QApplication.instance().exit(3)

    QTimer.singleShot(1000, tick)
    return REAL_EXEC()


QApplication.exec = staticmethod(exec_probe)

sys.path.insert(0, r'REPO_ROOT')
from src.utils import crash_recovery

_orig_install = crash_recovery.install_excepthook


def _install(window=None):
    _orig_install(window)
    sys.excepthook = sys.__excepthook__


crash_recovery.install_excepthook = _install

sys.argv = ['main.py', BUNDLE]
runpy.run_path('main.py', run_name='__main__')
'''


class ShutdownRegressionTests(unittest.TestCase):

    def test_mainwindow_wa_delete_on_close_clean_exit(self):
        import subprocess
        from src.model.data_model import Cell, Project
        from src.utils.figpack.package_manager import pack_project

        with tempfile.TemporaryDirectory() as tmp:
            from src.model.data_model import RowTemplate
            project = Project()
            cells = []
            for i in range(8):
                src = os.path.realpath(os.path.join(tmp, f'p{i}.jpg'))
                with open(src, 'wb') as f:
                    f.write(_jpeg(bytes([0x20 + i])))
                c = Cell()
                c.row_index = 0
                c.col_index = i
                c.image_path = src
                cells.append(c)
            project.cells = cells
            project.rows = [RowTemplate(index=0, column_count=8)]
            bundle = os.path.join(tmp, 'probe.figpack')
            pack_project(project, bundle)

            settings_dir = os.path.join(tmp, 'settings')
            child = os.path.join(tmp, 'child.py')
            with open(child, 'w', encoding='utf-8') as f:
                f.write(_CHILD_SRC.replace('REPO_ROOT', ROOT))

            env = dict(os.environ)
            env['LOCALAPPDATA'] = os.path.join(tmp, 'localappdata')
            if os.name == 'nt':
                env.pop('QT_QPA_PLATFORM', None)
            else:
                env['QT_QPA_PLATFORM'] = 'offscreen'

            proc = subprocess.run(
                [sys.executable, '-u', '-X', 'faulthandler', child,
                 bundle, settings_dir],
                cwd=ROOT, env=env, capture_output=True, text=True,
                timeout=30)
            self.assertNotIn('MISSING_WA_DELETE_ON_CLOSE', proc.stdout)
            self.assertIn('DONE: resolved and cached', proc.stdout)
            self.assertEqual(proc.returncode, 0,
                             proc.stdout[-2000:] + proc.stderr[-2000:])


class DirectResolveFallbackTests(unittest.TestCase):
    """``extracted_names=None`` exercises the local isfile path."""

    def test_direct_missing_entry_marks_none(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = _project([_cell('c', image_path='figpack:r1')])
            manifest = {'r1': _record('r1', 'assets/h/a.jpg',
                                      'C:\\o\\a.jpg', b'x')}
            missing = _resolve_resource_paths(project, manifest, tmp)
            self.assertEqual(missing, 1)
            self.assertIsNone(project['cells'][0]['image_path'])
            self.assertEqual(project['cells'][0]['original_source_path'],
                             'C:\\o\\a.jpg')


if __name__ == '__main__':
    unittest.main()
