import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.model.data_model import Project
from src.model.migrations import migrate_project_data
from src.version import APP_VERSION


LEGACY_PROJECT = {
    'name': 'Legacy figure',
    'page_width_mm': 180.0,
    'page_height_mm': 90.0,
    'dpi': 300,
    'rows': [{'index': 0, 'column_count': 1}],
    'cells': [{
        'id': 'panel-a', 'row_index': 0, 'col_index': 0,
        'image_path': None, 'scale_bar_mode': 'bayer',
        'nested_layout_path': None,
        'children': [{
            'id': 'child-a', 'scale_bar_mode': 'rgb',
            'raster_text_regions': [{'id': 'region-a', 'text': 'BTO-np', 'x': 10, 'y': 20,
                                     'w': 100, 'h': 25, 'font_size_px': 28.5,
                                     'group_id': 'text-group', 'enabled': False}],
        }],
    }],
    'svg_text_groups': [{'id': 'text-group', 'name': 'Axes', 'font_size_pt': 9.5, 'members': []}],
    'text_items': [{'id': 'label-a', 'text': 'A', 'scope': 'cell', 'parent_id': 'child-a',
                    'font_size_pt': 11, 'color': '#123456', 'x': 3.5, 'y': 6.25}],
}


class ProjectMigrationTests(unittest.TestCase):
    def test_new_saves_have_an_independent_schema_version(self):
        from src.model.migrations import PROJECT_SCHEMA_VERSION
        project = Project()
        data = project.to_dict()
        self.assertEqual(data['schema_version'], PROJECT_SCHEMA_VERSION)
        self.assertEqual(data['file_version'], APP_VERSION)
        with patch('src.model.data_model.APP_VERSION', '999.0.0'):
            data = project.to_dict()
        self.assertEqual(data['schema_version'], PROJECT_SCHEMA_VERSION)
        self.assertEqual(Project.from_dict(data).page_width_mm, project.page_width_mm)

    def test_migration_is_copying_idempotent_and_preserves_writer_version(self):
        raw = copy.deepcopy(LEGACY_PROJECT)
        raw['file_version'] = '2.0.0'
        before = copy.deepcopy(raw)
        migrated = migrate_project_data(raw)
        self.assertEqual(raw, before)
        self.assertIsNot(migrated, raw)
        self.assertEqual(migrated['file_version'], '2.0.0')
        self.assertEqual(migrated['schema_version'], 1)
        self.assertEqual(migrate_project_data(migrated), migrated)
        self.assertNotIn('nested_layout_path', migrated['cells'][0])
        self.assertEqual(migrated['cells'][0]['scale_bar_um_per_px'], 0.2569)
        self.assertEqual(migrated['cells'][0]['children'][0]['scale_bar_um_per_px'], 0.1301)

    def test_supported_legacy_versions_preserve_settings_and_new_field_defaults(self):
        for version in (None, '1.0.0', '2.0.0', '3.0.0', APP_VERSION):
            with self.subTest(version=version):
                raw = copy.deepcopy(LEGACY_PROJECT)
                if version is not None:
                    raw['file_version'] = version
                project = Project.from_dict(raw)
                self.assertEqual(project.page_width_mm, 180)
                self.assertEqual(project.dpi, 300)
                self.assertEqual(project.margin_left_mm, 10)
                self.assertEqual(project.svg_text_groups[0].font_size_pt, 9.5)
                self.assertEqual(project.cells[0].scale_bar_um_per_px, 0.2569)
                region = project.cells[0].children[0].raster_text_regions[0]
                self.assertFalse(region.enabled)
                self.assertEqual(region.font_size_px, 28.5)
                self.assertEqual(region.group_id, 'text-group')
                self.assertEqual(region.chars, [])
                self.assertFalse(region.foreign_excluded)
                self.assertIsNone(region.warning)
                label = project.text_items[0]
                self.assertEqual((label.font_size_pt, label.color, label.x, label.y),
                                 (11, '#123456', 3.5, 6.25))
                self.assertEqual(label.anchor, 'top_left_inside')
                self.assertEqual(Project.from_dict(project.to_dict()).to_dict(), project.to_dict())

    def test_future_files_are_rejected_without_mutation(self):
        from src.model.migrations import UnsupportedProjectVersion, PROJECT_SCHEMA_VERSION
        for data in ({'file_version': '999.0.0'},
                     {'file_version': APP_VERSION, 'schema_version': PROJECT_SCHEMA_VERSION + 1},
                     {'file_version': '999.0.0', 'schema_version': 0}):
            original = copy.deepcopy(data)
            with self.subTest(data=data), self.assertRaisesRegex(UnsupportedProjectVersion, 'upgrade|newer'):
                Project.from_dict(data)
            self.assertEqual(data, original)

    def test_malformed_versions_and_containers_report_clear_errors(self):
        from src.model.migrations import ProjectMigrationError
        for data in ([], None, {'file_version': 'garbage'}, {'file_version': 3.3},
                     {'schema_version': True}, {'schema_version': '1'}, {'schema_version': -1},
                     {'schema_version': None}, {'cells': {}}, {'cells': [None]},
                     {'cells': [{'children': 'bad'}]}):
            with self.subTest(data=data), self.assertRaises(ProjectMigrationError):
                Project.from_dict(data)

    def test_file_loading_never_rewrites_original_and_matches_direct_loading(self):
        with tempfile.TemporaryDirectory() as folder:
            for ext in ('.json', '.figlayout'):
                path = Path(folder) / ('Legacy figure' + ext)
                path.write_text(json.dumps(LEGACY_PROJECT), encoding='utf-8')
                before = path.read_bytes()
                loaded = Project.load_from_file(str(path))
                self.assertEqual(loaded.to_dict(), Project.from_dict(LEGACY_PROJECT).to_dict())
                self.assertEqual(path.read_bytes(), before)
                output = Path(folder) / ('Upgraded' + ext)
                loaded.save_to_file(str(output))
                self.assertEqual(json.loads(output.read_text(encoding='utf-8'))['schema_version'], 1)
                self.assertEqual(path.read_bytes(), before)

    def test_removed_nested_content_is_not_silently_lost(self):
        from src.model.migrations import ProjectMigrationError
        raw = {'cells': [{'id': 'nested', 'nested_layout_path': 'inner.figlayout'}]}
        with self.assertRaisesRegex(ProjectMigrationError, 'nested layout'):
            Project.from_dict(raw)
        self.assertEqual(raw['cells'][0]['nested_layout_path'], 'inner.figlayout')

    def test_migration_chain_runs_in_order_and_cannot_skip_missing_steps(self):
        import src.model.migrations as migrations
        raw = {'file_version': '2.0.0'}
        calls = []

        def upgrade_one(data):
            calls.append(data['schema_version'])
            data['fixture_revision_two'] = True
            return data

        with patch.object(migrations, 'PROJECT_SCHEMA_VERSION', 2):
            with patch.dict(migrations.SCHEMA_MIGRATIONS, {1: upgrade_one}):
                upgraded = migrations.migrate_project_data(raw)
                self.assertEqual(calls, [1])
                self.assertEqual(upgraded['schema_version'], 2)
                self.assertTrue(upgraded['fixture_revision_two'])
                self.assertEqual(migrations.migrate_project_data(upgraded), upgraded)
                self.assertEqual(calls, [1])
            with self.assertRaisesRegex(migrations.ProjectMigrationError, 'No migration'):
                migrations.migrate_project_data(raw)
        self.assertEqual(raw, {'file_version': '2.0.0'})

    def test_upgrade_save_failure_preserves_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'legacy.figlayout'
            path.write_text(json.dumps(LEGACY_PROJECT), encoding='utf-8')
            before = path.read_bytes()
            project = Project.load_from_file(str(path))
            with patch('src.utils.figpack.atomic_write.os.replace', side_effect=OSError('test failure')):
                with self.assertRaisesRegex(OSError, 'test failure'):
                    project.save_to_file(str(path))
            self.assertEqual(path.read_bytes(), before)
            self.assertEqual(list(Path(folder).iterdir()), [path])
            project.save_to_file(str(path))
            self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['schema_version'], 1)

    def test_cli_uses_the_same_version_guard(self):
        from src.cli.main import _load_project
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'future.figlayout'
            path.write_text(json.dumps({'schema_version': 999}), encoding='utf-8')
            with self.assertRaisesRegex(SystemExit, 'upgrade ILM'):
                _load_project(str(path))

    def test_recovery_style_double_migration_is_harmless(self):
        raw = copy.deepcopy(LEGACY_PROJECT)
        recovered = Project.from_dict(migrate_project_data(raw))
        self.assertEqual(recovered.to_dict(), Project.from_dict(raw).to_dict())
        self.assertEqual(raw, LEGACY_PROJECT)

    def test_legacy_render_matches_explicit_layout_after_load_and_resave(self):
        import os
        os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
        from PIL import Image, ImageDraw
        from PyQt6.QtWidgets import QApplication
        from src.export.image_exporter import ImageExporter
        from src.model.data_model import Cell
        type(self)._app = QApplication.instance() or QApplication([])
        with tempfile.TemporaryDirectory() as folder:
            asset = Path(folder) / 'panel.png'
            image = Image.new('RGB', (60, 30), 'white')
            ImageDraw.Draw(image).rectangle((5, 3, 30, 25), fill='red')
            image.save(asset)
            expected = Project(layout_mode='freeform', page_width_mm=100, page_height_mm=80, dpi=96,
                               cells=[Cell(id='a', image_path=str(asset), freeform_x_mm=10,
                                           freeform_y_mm=15, freeform_w_mm=50, freeform_h_mm=40,
                                           rotation=90, crop_right=0.8)])
            raw = expected.to_dict()
            raw.pop('schema_version')
            raw['file_version'] = '2.0.0'
            raw.pop('svg_text_groups')
            raw.pop('group_labels')
            raw['cells'][0].pop('raster_text_regions')
            raw['cells'][0].pop('svg_normalize_text')
            raw['cells'][0].pop('svg_normalize_text_pt')
            path = Path(folder) / 'legacy.figlayout'
            path.write_text(json.dumps(raw), encoding='utf-8')
            original_asset = asset.read_bytes()
            original_file = path.read_bytes()
            reference = ImageExporter.render_to_qimage(expected)
            loaded = Project.load_from_file(str(path))
            self.assertEqual(reference, ImageExporter.render_to_qimage(loaded))
            self.assertEqual(path.read_bytes(), original_file)
            output = Path(folder) / 'upgraded.figlayout'
            loaded.save_to_file(str(output))
            self.assertEqual(reference, ImageExporter.render_to_qimage(Project.load_from_file(str(output))))
            self.assertEqual(asset.read_bytes(), original_asset)

    def test_in_memory_layout_geometry_survives_upgrade(self):
        from src.model.layout_engine import LayoutEngine
        legacy = {
            'file_version': '2.0.0', 'page_width_mm': 120, 'page_height_mm': 70,
            'margin_left_mm': 0, 'margin_right_mm': 0, 'margin_top_mm': 0, 'margin_bottom_mm': 0,
            'layout_mode': 'freeform', 'cells': [
                {'id': 'a', 'freeform_x_mm': 5, 'freeform_y_mm': 7,
                 'freeform_w_mm': 40, 'freeform_h_mm': 30, 'rotation': 90, 'fit_mode': 'cover',
                 'crop_left': 0.1, 'crop_right': 0.9},
                {'id': 'b', 'freeform_x_mm': 60, 'freeform_y_mm': 10,
                 'freeform_w_mm': 50, 'freeform_h_mm': 20},
            ],
        }
        project = Project.from_dict(legacy)
        rects = LayoutEngine.calculate_layout(project).cell_rects
        self.assertEqual(rects, {'a': (5, 7, 40, 30), 'b': (60, 10, 50, 20)})
        self.assertEqual(project.cells[0].rotation, 90)
        self.assertEqual(project.cells[0].fit_mode, 'cover')
        self.assertEqual((project.cells[0].crop_left, project.cells[0].crop_right), (0.1, 0.9))
        self.assertEqual(LayoutEngine.calculate_layout(Project.from_dict(project.to_dict())).cell_rects, rects)


if __name__ == '__main__':
    unittest.main()
