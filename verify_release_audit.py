import base64
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

import audit_release


class Response(io.BytesIO):
    url = 'https://files.pythonhosted.org/example.tar.gz'


class ReleaseAuditTests(unittest.TestCase):
    def test_digest_matches_record_without_using_local_paths(self):
        payload = b'example native file'
        sha256 = hashlib.sha256(payload).hexdigest()
        item = mock.Mock()
        item.__fspath__ = mock.Mock(return_value='example/runtime.dll')
        item.__str__ = mock.Mock(return_value='example/runtime.dll')
        item.hash = SimpleNamespace(mode='sha256', value=base64.urlsafe_b64encode(bytes.fromhex(sha256)).decode().rstrip('='))
        dist = SimpleNamespace(metadata={'Name': 'Example_Package'}, version='1.0', files=[item])
        index = audit_release.record_index([dist], {'runtime.dll'})
        self.assertEqual(index[('runtime.dll', sha256)], [{'name': 'example-package', 'version': '1.0', 'record_path': 'example/runtime.dll'}])
        self.assertFalse(index[('runtime.dll', '0' * 64)])

    def test_inventory_covers_unmatched_native_and_embedded_modules(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            legal = root / '_internal' / 'licenses'
            legal.mkdir(parents=True)
            (legal / 'components.json').write_text(json.dumps({'app_version': '1.0.0', 'components': []}), encoding='utf-8')
            for name in ('ImageLayoutManager.exe', 'imagelayout-cli.exe', 'unexpected.dll'):
                (root / name).write_bytes(b'not a real executable')
            reader = SimpleNamespace(toc={'PYZ.pyz': (0, 0, 0, 0, 'z')}, open_embedded_archive=lambda name: SimpleNamespace(toc={'extra.module': (), 'sys': ()}))
            dist = SimpleNamespace(metadata={'Name': 'Extra'}, version='2.0')
            with mock.patch('PyInstaller.archive.readers.CArchiveReader', return_value=reader), mock.patch.object(audit_release.metadata, 'distributions', return_value=[]), mock.patch.object(audit_release.metadata, 'packages_distributions', return_value={'extra': ['Extra']}), mock.patch.object(audit_release.metadata, 'distribution', return_value=dist):
                report = audit_release.inventory(root)
            self.assertEqual(len(report['files']), 4)
            self.assertIn('unexpected.dll', report['native_files_without_record_match'])
            self.assertEqual(report['additional_distribution_candidates'], [{'name': 'extra', 'version': '2.0'}])
            self.assertEqual(report['source_status'], 'incomplete')
            self.assertNotIn(str(root), json.dumps(report))
            self.assertEqual(report['executable_archives'][0]['python_modules'], ['extra.module', 'sys'])

    def test_reparse_input_rejected(self):
        with tempfile.TemporaryDirectory() as td, mock.patch.object(audit_release, '_is_reparse', return_value=True):
            with self.assertRaises(ValueError):
                list(audit_release.regular_files(Path(td)))

    def test_download_hash_size_and_incomplete_status(self):
        payload = b'source archive bytes'
        release = {'info': {'name': 'Example', 'version': '1.0'}, 'urls': [{'packagetype': 'sdist', 'filename': 'example-1.0.tar.gz', 'url': Response.url, 'size': len(payload), 'digests': {'sha256': hashlib.sha256(payload).hexdigest()}}]}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(audit_release.urllib.request, 'urlopen', side_effect=[Response(json.dumps(release).encode()), Response(payload)]):
                result = audit_release.fetch_source({'name': 'example', 'version': '1.0'}, Path(td))
            self.assertEqual(result['status'], 'sdist_downloaded_not_correspondence_verified')
            path = Path(td) / result['archives'][0]['path']
            self.assertEqual(path.read_bytes(), payload)
            self.assertNotIn(td, json.dumps(result))

    def test_download_bad_hash_is_not_accepted(self):
        payload = b'bad source archive'
        release = {'info': {'name': 'example', 'version': '1.0'}, 'urls': [{'packagetype': 'sdist', 'filename': 'example-1.0.tar.gz', 'url': Response.url, 'size': len(payload), 'digests': {'sha256': '0' * 64}}]}
        with tempfile.TemporaryDirectory() as td:
            with mock.patch.object(audit_release.urllib.request, 'urlopen', side_effect=[Response(json.dumps(release).encode()), Response(payload)]):
                result = audit_release.fetch_source({'name': 'example', 'version': '1.0'}, Path(td))
            self.assertEqual(result['status'], 'unresolved')
            self.assertFalse((Path(td) / 'example' / 'example-1.0.tar.gz').exists())

    def test_missing_source_is_explicit(self):
        release = {'info': {'name': 'example', 'version': '1.0'}, 'urls': []}
        with tempfile.TemporaryDirectory() as td, mock.patch.object(audit_release.urllib.request, 'urlopen', return_value=Response(json.dumps(release).encode())):
            result = audit_release.fetch_source({'name': 'example', 'version': '1.0'}, Path(td))
        self.assertEqual(result['status'], 'unresolved')
        self.assertIn('no non-yanked', result['reason'])

    def test_untrusted_hosts_rejected(self):
        for url in ('http://files.pythonhosted.org/a', 'https://example.test/a', 'https://user:pass@pypi.org/a', 'file:///tmp/archive'):
            with self.subTest(url=url), self.assertRaises(ValueError):
                audit_release.safe_source_url(url)

    def test_output_must_be_new_and_outside_bundle(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            bundle = root / 'bundle'
            bundle.mkdir()
            for output in (bundle, bundle / 'audit', root):
                with self.subTest(output=output.name), self.assertRaises(SystemExit):
                    audit_release.main(['inventory', '--bundle', str(bundle), '--output', str(output)])


if __name__ == '__main__':
    unittest.main()
