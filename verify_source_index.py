import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

import build_source_index  # noqa: E402
from src.version import APP_VERSION

SOURCES_JSON = ROOT / 'licenses' / 'sources.json'
SOURCES_MD = ROOT / 'SOURCES.md'

HTTPS_SHA_TYPES = ('pypi_sdist', 'release_archive', 'conda_recipe_upstream')


def _fixture(overrides=None):
    data = {
        'schema_version': 1,
        'app_version': APP_VERSION,
        'python_version': '3.13.15',
        'index_status': 'pointers_recorded',
        'source_status': 'incomplete',
        'application_source_archive': 'app-source.zip',
        'application_source_sha256': 'a' * 64,
        'build_steps': ['step one'],
        'component_count': 3,
        'no_open_source_counterpart': [],
        'unresolved': [],
        'components': [
            {'name': 'example-py', 'version': '1.0', 'role': 'dependency',
             'kind': 'python', 'license_expression': 'MIT',
             'status': 'sdist_downloaded_not_correspondence_verified',
             'source': {'type': 'pypi_sdist',
                        'url': 'https://example.test/pkg-1.0.tar.gz',
                        'sha256': 'b' * 64}},
            {'name': 'example-native', 'version': '2.0',
             'role': 'native upstream notices',
             'kind': 'native', 'license_expression': None,
             'status': 'archive_hash_verified',
             'source': {'type': 'release_archive',
                        'url': 'https://example.test/nat-2.0.zip',
                        'sha256': 'c' * 64}},
            {'name': 'example-git', 'version': '3.0', 'role': 'dependency',
             'kind': 'python', 'license_expression': 'Apache 2.0',
             'status': 'commit_archive_downloaded',
             'source': {'type': 'git_commit',
                        'repo': 'https://github.com/example/proj',
                        'commit': 'd' * 40}},
        ],
    }
    if overrides:
        data.update(overrides)
    return data


class TestCommittedIndex(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        if not SOURCES_JSON.is_file():
            raise unittest.SkipTest('licenses/sources.json not committed')
        cls.data = json.loads(SOURCES_JSON.read_text(encoding='utf-8'))

    def test_every_component_has_source_or_unresolved(self):
        unresolved = {u['name'] for u in self.data['unresolved']}
        for comp in self.data['components']:
            if comp['name'] in unresolved:
                continue
            self.assertIsInstance(comp.get('source'), dict, comp['name'])

    def test_url_and_hash_shapes(self):
        for comp in self.data['components']:
            source = comp.get('source') or {}
            kind = source.get('type')
            if kind in HTTPS_SHA_TYPES:
                self.assertTrue(
                    source.get('url', '').startswith('https://'),
                    comp['name'])
                self.assertTrue(
                    re.fullmatch(r'[0-9a-f]{64}',
                                 source.get('sha256', '')),
                    comp['name'])
            elif kind == 'git_commit':
                self.assertTrue(
                    re.fullmatch(r'[0-9a-f]{40}',
                                 source.get('commit', '')),
                    comp['name'])

    def test_check_current_and_component_count(self):
        candidates = sorted(
            (ROOT / 'build').glob(
                'store-candidate-*/dist/ImageLayoutManager/_internal/'
                'licenses/components.json'))
        matched = None
        for path in candidates:
            try:
                m = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            if m.get('app_version') == APP_VERSION:
                matched = m
        if matched is None:
            self.skipTest(
                f'no built candidate for {APP_VERSION} under build/')
        self.assertEqual(build_source_index.main(['check']), 0)
        self.assertEqual(self.data['component_count'],
                         len(matched['components']))


class TestRender(unittest.TestCase):

    def test_render_contains_names_and_is_deterministic(self):
        data = _fixture()
        text1 = build_source_index.render(data)
        text2 = build_source_index.render(data)
        self.assertEqual(text1, text2)
        for comp in data['components']:
            self.assertIn(comp['name'], text1)

    def test_exceptions_section_for_proprietary(self):
        data = _fixture()
        data['components'].append({
            'name': 'Conda vc14_runtime runtime notices',
            'version': '14.0', 'kind': 'native',
            'role': 'native upstream notices',
            'license_expression': None, 'status': 'recorded',
            'source': {'type': 'proprietary_redistributable',
                       'notes': 'No open-source counterpart.'}})
        data['no_open_source_counterpart'] = [
            {'name': 'Conda vc14_runtime runtime notices',
             'version': '14.0',
             'reason': 'No open-source counterpart.'}]
        data['component_count'] = 4
        text = build_source_index.render(data)
        self.assertIn('## Exceptions', text)
        self.assertIn('vc14_runtime', text.split('## Exceptions')[1])
        row = next(l for l in text.splitlines()
                   if 'vc14_runtime' in l and l.startswith('|'))
        self.assertIn('no open-source counterpart', row)


class TestMirrorCanonicalisation(unittest.TestCase):

    def test_jaist_mirror_maps_to_download_qt_io(self):
        record = {'url': 'https://ftp.jaist.ac.jp/pub/qtproject/archive/'
                         'qt/6.11/6.11.2/submodules/qtbase-src.zip',
                  'sha256': 'e' * 64}
        source = build_source_index._archive_source(record)
        self.assertTrue(source['url'].startswith(
            'https://download.qt.io/archive/'))
        self.assertEqual(
            source['downloaded_from_mirror'],
            'https://ftp.jaist.ac.jp/pub/qtproject/archive/'
            'qt/6.11/6.11.2/submodules/qtbase-src.zip')
        self.assertEqual(source['sha256'], 'e' * 64)


class TestCheckFailures(unittest.TestCase):

    def _staged(self, td, data, write_md=True):
        json_path = Path(td) / 'sources.json'
        md_path = Path(td) / 'SOURCES.md'
        json_path.write_text(json.dumps(data), encoding='utf-8')
        if write_md:
            md_path.write_text(build_source_index.render(data),
                               encoding='utf-8')
        return mock.patch.multiple(
            build_source_index, SOURCES_JSON=json_path,
            SOURCES_MD=md_path)

    def test_missing_sources_json(self):
        with tempfile.TemporaryDirectory() as td:
            with self._staged(td, _fixture()):
                (Path(td) / 'sources.json').unlink()
                self.assertEqual(build_source_index.main(['check']), 2)

    def test_version_mismatch(self):
        with tempfile.TemporaryDirectory() as td:
            data = _fixture({'app_version': '0.0.0'})
            with self._staged(td, data):
                self.assertEqual(build_source_index.main(['check']), 2)

    def test_stale_sources_md(self):
        with tempfile.TemporaryDirectory() as td:
            with self._staged(td, _fixture()):
                (Path(td) / 'SOURCES.md').write_text(
                    'stale\n', encoding='utf-8')
                self.assertEqual(build_source_index.main(['check']), 2)

    def test_fresh_check_passes(self):
        with tempfile.TemporaryDirectory() as td:
            with self._staged(td, _fixture()):
                self.assertEqual(build_source_index.main(['check']), 0)


class TestCollectNoCandidate(unittest.TestCase):

    def test_no_matching_candidate_fails(self):
        with tempfile.TemporaryDirectory() as td:
            with self.assertRaises(SystemExit):
                build_source_index.collect(Path(td))


if __name__ == '__main__':
    unittest.main()
