import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

import numpy as np
from PIL import Image
from PyQt6.QtCore import QPointF, Qt
from PyQt6.QtGui import QImage, QPainterPath, QPalette
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from src.app.raster_text_overlay import text_envelope_path
from src.app.raster_text_inspector import RasterTextInspectorWindow, RasterTextPreview
from src.app.theme import build_palette
from src.model.data_model import Cell, Project, RasterTextRegion, SvgTextGroup
from src.utils.raster_text_utils import apply_raster_text_overrides, get_raster_text_mask


class EnvelopeTests(unittest.TestCase):
    def setUp(self):
        self.mask = np.zeros((40, 90), dtype=float)
        self.mask[4:32, 5:20] = 1
        self.mask[15:32, 26:39] = 1
        self.mask[15:32, 45:58] = 1
        self.mask[15:32, 65:77] = 1

    def test_connected_rounded_step_encloses_ink_not_height_gap(self):
        path = text_envelope_path(self.mask)
        self.assertEqual(len(path.toSubpathPolygons()), 1)
        self.assertTrue(path.contains(QPointF(10, 6)))
        self.assertTrue(path.contains(QPointF(30, 16)))
        self.assertFalse(path.contains(QPointF(30, 6)))
        ys, xs = np.nonzero(self.mask)
        self.assertTrue(all(path.contains(QPointF(x + 0.5, y + 0.5)) for y, x in zip(ys, xs)))
        self.assertTrue(any(path.elementAt(i).type == QPainterPath.ElementType.CurveToElement
                            for i in range(path.elementCount())))
        for i in range(1, path.elementCount()):
            a, b = path.elementAt(i - 1), path.elementAt(i)
            if b.type == QPainterPath.ElementType.LineToElement:
                self.assertTrue(abs(a.x - b.x) < 1e-6 or abs(a.y - b.y) < 1e-6)

    def test_dot_and_dash_join_into_one_envelope(self):
        self.mask[5:8, 68:73] = 1
        self.mask[21:24, 60:63] = 1
        path = text_envelope_path(self.mask)
        self.assertTrue(path.contains(QPointF(70, 6)))
        self.assertTrue(path.contains(QPointF(61, 22)))
        self.assertEqual(len(path.toSubpathPolygons()), 1)

    def test_protected_content_and_origins(self):
        protected = np.zeros((50, 110), dtype=bool)
        protected[9:12, 32:39] = True
        path = text_envelope_path(self.mask, origin=(100, 80), protected_mask=protected,
                                  protected_origin=(90, 75))
        for y, x in zip(*np.nonzero(protected)):
            self.assertFalse(path.contains(QPointF(90 + x + 0.5, 75 + y + 0.5)))
        self.assertTrue(path.contains(QPointF(110, 105)))

    def test_protected_neighbor_does_not_hide_selected_ink(self):
        protected = np.zeros_like(self.mask, dtype=bool)
        protected[11:14, 28:34] = True
        path = text_envelope_path(self.mask, protected_mask=protected)
        ys, xs = np.nonzero(self.mask)
        self.assertTrue(all(path.contains(QPointF(x + 0.5, y + 0.5)) for y, x in zip(ys, xs)))
        for y, x in zip(*np.nonzero(protected)):
            self.assertFalse(path.contains(QPointF(x + 0.5, y + 0.5)))

    def test_empty_tiny_and_vertical_masks(self):
        self.assertTrue(text_envelope_path(np.zeros((0, 0))).isEmpty())
        self.assertTrue(text_envelope_path(np.zeros((5, 5))).isEmpty())
        self.assertFalse(text_envelope_path(np.ones((1, 1))).isEmpty())
        float_path = text_envelope_path(self.mask)
        byte_path = text_envelope_path((self.mask * 255).astype(np.uint8))
        self.assertEqual(float_path, byte_path)
        vertical = text_envelope_path(self.mask.T, vertical=True)
        self.assertTrue(vertical.contains(QPointF(16, 30)))
        self.assertFalse(vertical.contains(QPointF(6, 30)))


class PreviewTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'panel.png'
        arr = np.full((120, 260, 3), 255, dtype=np.uint8)
        arr[40:64, 60:74] = 0
        arr[48:64, 82:94] = 0
        arr[48:64, 101:113] = 0
        arr[48:64, 120:132] = 0
        self.source = Image.fromarray(arr)
        self.source.save(self.path)
        self.region = RasterTextRegion(x=57, y=37, w=79, h=30, font_size_px=30,
                                       text='Aaaa', background='#ffffff')
        self.group = SvgTextGroup(font_size_pt=16)
        self.cell = Cell(image_path=str(self.path), freeform_w_mm=90,
                         freeform_h_mm=120 * 90 / 260, raster_text_regions=[self.region])
        self.project = Project(layout_mode='freeform', cells=[self.cell], svg_text_groups=[self.group])
        self.original_bytes = self.path.read_bytes()

    def dialog(self):
        with patch('src.app.raster_text_inspector.backend_status', return_value=None):
            dialog = RasterTextInspectorWindow(str(self.path), self.project, self.cell)
        self.addCleanup(dialog.close)
        dialog.show()
        self.app.processEvents()
        return dialog

    def test_preview_mask_tracks_applied_and_skipped_geometry(self):
        entry = {'id': self.region.id, 'x': 57, 'y': 37, 'w': 79, 'h': 30,
                 'scale': 1.4, 'anchor': 'right', 'background': '#ffffff'}
        masks = {}
        rendered, report = apply_raster_text_overrides(self.source, {'regions': [entry]}, overlay_masks=masks)
        without_overlays, export_report = apply_raster_text_overrides(self.source, {'regions': [entry]})
        self.assertEqual(rendered.tobytes(), without_overlays.tobytes())
        self.assertEqual(report, export_report)
        self.assertEqual(report[0]['status'], 'applied')
        data = masks[self.region.id]
        self.assertNotEqual(data['origin'], (57, 37))
        path = text_envelope_path(data['alpha'], data['origin'])
        arr = np.asarray(rendered)
        ys, xs = np.nonzero(np.max(255 - arr[..., :3], axis=2) > 127)
        self.assertTrue(all(path.contains(QPointF(x + 0.5, y + 0.5)) for y, x in zip(ys, xs)))
        masks = {}
        entry['scale'] = 20
        _, report = apply_raster_text_overrides(self.source, {'regions': [entry]}, overlay_masks=masks)
        self.assertEqual(report[0]['status'], 'skipped_bounds')
        self.assertEqual(masks[self.region.id]['origin'], (57, 37))
        self.assertEqual(self.path.read_bytes(), self.original_bytes)

    def test_selection_click_hover_and_resizing_do_not_reprocess(self):
        dialog = self.dialog()
        preview = dialog._preview_label
        with patch.object(dialog, '_load_image', wraps=dialog._load_image) as load:
            dialog._list.item(0).setSelected(True)
            self.assertEqual(preview._selected, {self.region.id})
            dialog._list.clearSelection()
            point = preview.image_transform().map(QPointF(66, 50)).toPoint()
            QTest.mouseMove(preview, point)
            self.assertEqual(preview._hovered, self.region.id)
            QTest.mouseClick(preview, Qt.MouseButton.LeftButton, pos=point)
            self.assertTrue(dialog._list.item(0).isSelected())
            QTest.mouseClick(preview, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ControlModifier, point)
            self.assertFalse(dialog._list.item(0).isSelected())
            for w, h in ((1100, 720), (1300, 820)):
                dialog.resize(w, h)
                self.app.processEvents()
                point = preview.image_transform().map(QPointF(66, 50))
                self.assertEqual(preview._hit_test(point)['id'], self.region.id)
            load.assert_not_called()

    def test_assigning_a_warned_region_enables_it(self):
        self.region.warning = 'touching'
        self.region.enabled = False
        dialog = self.dialog()
        self.assertEqual(dialog._report, {})
        dialog._list.item(0).setSelected(True)
        dialog._group_combo.setCurrentIndex(dialog._group_combo.findData(self.group.id))
        dialog._on_assign()
        self.assertTrue(self.region.enabled)
        self.assertEqual(self.region.group_id, self.group.id)
        self.assertEqual(dialog._report.get(self.region.id), 'applied')
        self.assertEqual(dialog._list.item(0).checkState(), Qt.CheckState.Checked)
        dialog._list.item(0).setCheckState(Qt.CheckState.Unchecked)
        self.assertFalse(self.region.enabled)
        from src.app.raster_text_region_delegate import REGION_DETAILS_ROLE
        from src.app.i18n import tr
        self.assertEqual(dialog._list.item(0).data(REGION_DETAILS_ROLE)['status'], tr('rastertxt_paused_status'))

    def test_region_row_separates_group_size_and_warning(self):
        from src.app.raster_text_region_delegate import REGION_DETAILS_ROLE
        from src.app.i18n import tr
        self.region.text = 'BTO-np ' * 30
        self.region.group_id = self.group.id
        self.region.warning = 'touching'
        self.region.enabled = False
        dialog = self.dialog()
        item = dialog._list.item(0)
        details = item.data(REGION_DETAILS_ROLE)
        self.assertEqual(details['text'], self.region.text)
        self.assertEqual(details['group'], self.group.name)
        self.assertEqual(details['status'], tr('rastertxt_paused_status'))
        self.assertEqual(details['warning'], tr('rastertxt_reason_touching'))
        self.assertIn(self.region.text, item.toolTip())
        self.assertIn(tr('rastertxt_review_tip'), item.toolTip())
        self.assertEqual(item.data(Qt.ItemDataRole.AccessibleTextRole), item.text())
        for theme in ('light', 'dark'):
            dialog.setPalette(build_palette(theme))
            dialog._list.grab()
        self.assertGreater(dialog._list.visualItemRect(item).height(), 60)
        self.assertFalse(dialog._list.horizontalScrollBar().isVisible())

    def test_row_selection_and_checkbox_are_separate_controls(self):
        from PyQt6.QtWidgets import QStyleOptionViewItem
        self.region.enabled = False
        dialog = self.dialog()
        listing = dialog._list
        rect = listing.visualItemRect(listing.item(0))
        QTest.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton,
                         pos=rect.topLeft() + QPointF(100, 15).toPoint())
        self.assertTrue(listing.item(0).isSelected())
        self.assertFalse(self.region.enabled)
        option = QStyleOptionViewItem()
        option.initFrom(listing)
        option.widget = listing
        option.rect = rect
        point = listing.itemDelegate().check_rect(option).center()
        QTest.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertTrue(self.region.enabled)
        QTest.mouseClick(listing.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.assertFalse(self.region.enabled)
        QTest.keyClick(listing, Qt.Key.Key_Space)
        self.assertTrue(self.region.enabled)

    def test_row_group_and_status_update_when_assignment_changes(self):
        from src.app.raster_text_region_delegate import REGION_DETAILS_ROLE
        from src.app.i18n import tr
        dialog = self.dialog()
        details = dialog._list.item(0).data(REGION_DETAILS_ROLE)
        self.assertIsNone(details['group'])
        self.assertEqual(details['status'], tr('rastertxt_assign_status'))
        dialog._list.item(0).setSelected(True)
        dialog._group_combo.setCurrentIndex(dialog._group_combo.findData(self.group.id))
        dialog._on_assign()
        details = dialog._list.item(0).data(REGION_DETAILS_ROLE)
        self.assertEqual(details['group'], self.group.name)
        self.assertEqual(details['status'], tr('rastertxt_applied_status'))
        dialog._chk_original.setChecked(True)
        self.assertEqual(dialog._list.item(0).data(REGION_DETAILS_ROLE)['status'], tr('rastertxt_original_status'))
        dialog._on_ungroup()
        self.assertIsNone(dialog._list.item(0).data(REGION_DETAILS_ROLE)['group'])

    def test_original_mode_and_deleted_regions_refresh_envelopes(self):
        self.region.group_id = self.group.id
        dialog = self.dialog()
        applied = dialog._preview_label._overlays[0]['path']
        dialog._chk_original.setChecked(True)
        original = dialog._preview_label._overlays[0]['path']
        self.assertNotEqual(applied.boundingRect(), original.boundingRect())
        alpha, foreign, origin = get_raster_text_mask(self.source, self.region)
        expected = text_envelope_path(alpha, origin, foreign, origin)
        self.assertEqual(original, expected)
        self.cell.raster_text_regions.clear()
        dialog.refresh()
        self.assertEqual(dialog._preview_label._overlays, [])

    def test_border_and_fill_do_not_tint_protected_content(self):
        preview = RasterTextPreview()
        self.addCleanup(preview.close)
        mask = np.zeros((80, 160))
        mask[20:60, 20:55] = 1
        mask[38:60, 70:110] = 1
        foreign = np.zeros_like(mask, dtype=bool)
        foreign[28:34, 74:82] = True
        pixels = np.full((80, 160, 3), 255, dtype=np.uint8)
        pixels[foreign] = [200, 0, 0]
        image = QImage(pixels.tobytes(), 160, 80, 480, QImage.Format.Format_RGB888).copy()
        envelope = text_envelope_path(mask, protected_mask=foreign)
        preview.set_selected(['r'])
        preview.show()
        for size in ((280, 220), (640, 400)):
            preview.resize(*size)
            self.app.processEvents()
            preview.set_content(image, [])
            point = preview.image_transform().map(QPointF(78, 31)).toPoint()
            before = preview.grab().toImage().pixelColor(point)
            preview.set_content(image, [{'id': 'r', 'path': envelope, 'enabled': True, 'tooltip': ''}])
            after = preview.grab().toImage().pixelColor(point)
            self.assertEqual(before, after)

    def test_theme_accent_transparency_and_selected_outline(self):
        preview = RasterTextPreview()
        self.addCleanup(preview.close)
        image = QImage(100, 80, QImage.Format.Format_RGB32)
        image.fill(Qt.GlobalColor.white)
        mask = np.zeros((80, 100))
        mask[20:60, 20:80] = 1
        path = text_envelope_path(mask)
        preview.resize(420, 340)
        preview.set_content(image, [{'id': 'r', 'path': path, 'enabled': True, 'tooltip': 'test'}])
        preview.show()
        self.app.processEvents()
        for theme in ('light', 'dark'):
            preview.setPalette(build_palette(theme))
            preview.set_selected([])
            point = preview.image_transform().map(QPointF(50, 40)).toPoint()
            normal = preview.grab().toImage().pixelColor(point)
            preview.set_selected(['r'])
            selected = preview.grab().toImage().pixelColor(point)
            accent = preview.palette().color(QPalette.ColorRole.Highlight)
            self.assertNotEqual(normal, selected)
            for channel in ('red', 'green', 'blue'):
                expected = round(255 * (1 - 55 / 255) + getattr(accent, channel)() * 55 / 255)
                self.assertAlmostEqual(getattr(selected, channel)(), expected, delta=1)


if __name__ == '__main__':
    unittest.main()
