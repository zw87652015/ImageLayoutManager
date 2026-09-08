import copy
import json
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from src.model.data_model import Cell, Project, TextItem
from src.model.migrations import (
    PROJECT_SCHEMA_VERSION,
    ProjectMigrationError,
    UnsupportedProjectVersion,
    migrate_project_data,
)
from src.utils.figpack import package_manager
from src.utils.figpack.errors import BundleError, BundleSecurityError
from src.version import APP_VERSION


class ProjectBundleCompatibilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def make_bundle(self, data, *, format_version=1, asset_name=None):
        path = self.root / 'synthetic.figpack'
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_STORED) as archive:
            archive.writestr('metadata.json', json.dumps({
                'figpack_format_version': format_version,
                'manifest': {},
            }))
            archive.writestr('project.json', json.dumps(data))
            if asset_name is not None:
                archive.writestr(asset_name, b'synthetic asset bytes')
        return path

    def assert_legacy_bundle_compatible(self, version_fields):
        raw = {
            'name': 'legacy',
            'page_width_mm': 123.0,
            'cells': [{'id': 'legacy-cell', 'image_path': None}],
            **version_fields,
        }
        original = copy.deepcopy(raw)
        archive = self.make_bundle(raw)
        archive_bytes = archive.read_bytes()
        archive_mtime = archive.stat().st_mtime_ns
        plain_path = self.root / 'legacy.json'
        plain_path.write_text(json.dumps(raw), encoding='utf-8')
        plain_bytes = plain_path.read_bytes()

        result = package_manager.unpack_project(str(archive), str(self.root / 'unpacked'))

        self.assertEqual(result.project_data['schema_version'], PROJECT_SCHEMA_VERSION)
        self.assertEqual(result.project_data, migrate_project_data(raw))
        self.assertEqual(result.asset_count, 0)
        self.assertEqual(result.missing_count, 0)
        self.assertEqual(result.metadata['figpack_format_version'], 1)
        for key, expected in {
            'label_align': 'center',
            'label_offset_x': 0.0,
            'label_offset_y': 0.0,
            'label_row_height': 0.0,
        }.items():
            self.assertEqual(result.project_data[key], expected)
        if 'file_version' in raw:
            self.assertEqual(result.project_data['file_version'], raw['file_version'])
        else:
            self.assertNotIn('file_version', result.project_data)
        bundled = Project.from_dict(result.project_data).to_dict()
        self.assertEqual(bundled, Project.from_dict(raw).to_dict())
        self.assertEqual(bundled, Project.load_from_file(str(plain_path)).to_dict())
        self.assertEqual(raw, original)
        self.assertEqual(archive.read_bytes(), archive_bytes)
        self.assertEqual(archive.stat().st_mtime_ns, archive_mtime)
        self.assertEqual(plain_path.read_bytes(), plain_bytes)
        self.assertFalse((self.root / 'unpacked' / '.extracting').exists())

    def test_synthetic_unversioned_bundle_matches_plain_project_loading(self):
        self.assert_legacy_bundle_compatible({})

    def test_synthetic_older_app_bundle_matches_plain_project_loading(self):
        self.assert_legacy_bundle_compatible({'file_version': '0.9.0'})

    def assert_project_rejected_before_extraction(self, raw, error_type, code):
        archive = self.make_bundle(raw, asset_name='assets/probe.bin')
        before = archive.read_bytes()
        target = self.root / 'rejected'
        with self.assertRaises(error_type) as migration_error:
            migrate_project_data(raw)
        with patch.object(package_manager, '_stream_extract') as extract:
            with self.assertRaises(BundleError) as raised:
                package_manager.unpack_project(str(archive), str(target))
        extract.assert_not_called()
        self.assertEqual(raised.exception.code, code)
        self.assertEqual(str(raised.exception), str(migration_error.exception))
        self.assertTrue(str(raised.exception).strip())
        self.assertIsInstance(raised.exception.__cause__, error_type)
        self.assertFalse((target / 'assets').exists())
        self.assertEqual(archive.read_bytes(), before)

    def test_future_project_schema_is_rejected_before_asset_extraction(self):
        self.assert_project_rejected_before_extraction(
            {'schema_version': PROJECT_SCHEMA_VERSION + 1, 'file_version': APP_VERSION},
            UnsupportedProjectVersion,
            'unsupported_project_version',
        )

    def test_future_app_only_legacy_is_rejected_before_asset_extraction(self):
        self.assert_project_rejected_before_extraction(
            {'file_version': '999999.0.0', 'cells': []},
            UnsupportedProjectVersion,
            'unsupported_project_version',
        )

    def test_invalid_project_data_is_wrapped_before_asset_extraction(self):
        for raw in ([], {'schema_version': 'invalid', 'cells': []}):
            with self.subTest(raw=raw):
                self.assert_project_rejected_before_extraction(
                    raw, ProjectMigrationError, 'invalid_project_data',
                )

    def test_migration_error_preserves_actionable_message(self):
        archive = self.make_bundle({}, asset_name='assets/probe.bin')
        message = 'Project data is invalid; restore an earlier saved copy.'
        error = ProjectMigrationError(message)
        with patch.object(package_manager, 'migrate_project_data', side_effect=error):
            with patch.object(package_manager, '_stream_extract') as extract:
                with self.assertRaises(BundleError) as raised:
                    package_manager.unpack_project(str(archive), str(self.root / 'invalid'))
        self.assertEqual(raised.exception.code, 'invalid_project_data')
        self.assertEqual(str(raised.exception), message)
        self.assertIs(raised.exception.__cause__, error)
        extract.assert_not_called()

    def test_container_version_gate_precedes_project_migration(self):
        archive = self.make_bundle({}, format_version=2, asset_name='assets/probe.bin')
        with patch.object(package_manager, 'migrate_project_data') as migrate:
            with patch.object(package_manager, '_stream_extract') as extract:
                with self.assertRaises(BundleError) as raised:
                    package_manager.unpack_project(str(archive), str(self.root / 'future-container'))
        self.assertEqual(raised.exception.code, 'unsupported_version')
        migrate.assert_not_called()
        extract.assert_not_called()

    def test_zip_safety_still_precedes_project_migration(self):
        archive = self.make_bundle({}, asset_name='../escaped.bin')
        with patch.object(package_manager, 'migrate_project_data') as migrate:
            with patch.object(package_manager, '_stream_extract') as extract:
                with self.assertRaises(BundleSecurityError):
                    package_manager.unpack_project(str(archive), str(self.root / 'unsafe'))
        migrate.assert_not_called()
        extract.assert_not_called()
        self.assertFalse((self.root / 'escaped.bin').exists())

    def test_current_schema_pack_save_roundtrip_preserves_known_fields(self):
        asset = self.root / 'panel.svg'
        asset.write_text(
            '<svg xmlns="http://www.w3.org/2000/svg" width="10" height="10">'
            '<rect width="10" height="10" fill="red"/></svg>',
            encoding='utf-8',
        )
        project = Project(
            name='roundtrip',
            page_width_mm=174.0,
            page_height_mm=93.0,
            dpi=300,
            layout_mode='freeform',
            label_align='right',
            label_offset_x=1.25,
            figure_number='Figure 2',
            figure_title='Compatibility roundtrip',
            cells=[Cell(
                id='panel', image_path=str(asset), original_source_path=str(asset),
                rotation=90, crop_left=0.1, freeform_x_mm=8.0,
                freeform_w_mm=42.0, scale_bar_enabled=True,
            )],
            text_items=[TextItem(id='caption', text='Known caption', x=4.0, y=6.0)],
        )
        expected = project.to_dict()
        self.assertEqual(expected['schema_version'], PROJECT_SCHEMA_VERSION)
        output = self.root / 'roundtrip.figpack'
        packed = package_manager.pack_project(project, str(output))
        self.assertEqual(packed.asset_count, 1)
        before = output.read_bytes()
        with zipfile.ZipFile(output) as archive:
            saved = json.loads(archive.read('project.json'))
        self.assertEqual(saved['schema_version'], PROJECT_SCHEMA_VERSION)
        self.assertEqual(saved['file_version'], APP_VERSION)

        unpacked = package_manager.unpack_project(str(output), str(self.root / 'first'))
        self.assertEqual(unpacked.asset_count, 1)
        restored = Project.from_dict(unpacked.project_data)
        self.assertEqual(Path(restored.cells[0].image_path).read_bytes(), asset.read_bytes())
        normalized = restored.to_dict()
        normalized['cells'][0]['image_path'] = str(asset)
        self.assertEqual(normalized, expected)
        self.assertEqual(project.to_dict(), expected)

        resaved = self.root / 'resaved.figpack'
        package_manager.pack_project(restored, str(resaved))
        again = package_manager.unpack_project(str(resaved), str(self.root / 'second'))
        normalized = Project.from_dict(again.project_data).to_dict()
        self.assertEqual(Path(normalized['cells'][0]['image_path']).read_bytes(), asset.read_bytes())
        normalized['cells'][0]['image_path'] = str(asset)
        self.assertEqual(normalized, expected)
        self.assertEqual(output.read_bytes(), before)


if __name__ == '__main__':
    unittest.main()
