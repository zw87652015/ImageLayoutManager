import io
import os
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from PyQt6.QtCore import QEvent, QMimeData, QPoint, QUrl, Qt
from PyQt6.QtGui import QImage, QKeyEvent, QPixmap
from PyQt6.QtWidgets import QApplication, QLineEdit, QMenu, QMessageBox

from src.utils.clipboard_paste import (
    ClipboardContent, GVML_FORMAT, image_matches, read_clipboard,
    relocate_pasted_images, store_clipboard_image, store_image,
)


def _gvml_mime(media_name='image1.png', media=b'', crop=None,
               svg=None, pics=1, thumb=None):
    """Build a QMimeData carrying a synthetic PowerPoint GVML payload."""
    pics_xml = ''
    rels_xml = ''
    for i in range(pics):
        svg_blip = '<extLst><ext><svgBlip r:embed="rIdSvg"/></ext></extLst>' \
            if svg and i == 0 else ''
        src_rect = f'<srcRect {crop}/>' if crop and i == 0 else ''
        pics_xml += (
            f'<pic><blipFill><blip r:embed="rId{i}">{svg_blip}</blip>'
            f'{src_rect}</blipFill></pic>')
        rels_xml += (f'<Relationship Id="rId{i}" '
                     f'Target="../media/{media_name}"/>')
    if svg:
        rels_xml += ('<Relationship Id="rIdSvg" '
                     'Target="../media/image1.svg"/>')
    drawing = ('<root xmlns:r="http://schemas.openxmlformats.org/'
               f'officeDocument/2006/relationships">{pics_xml}</root>'
               ).encode()
    rels = f'<Relationships>{rels_xml}</Relationships>'.encode()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w') as zf:
        zf.writestr('clipboard/drawings/drawing1.xml', drawing)
        zf.writestr('clipboard/drawings/_rels/drawing1.xml.rels', rels)
        zf.writestr(f'clipboard/media/{media_name}', media)
        if svg:
            zf.writestr('clipboard/media/image1.svg', svg)
    mime = QMimeData()
    mime.setData(GVML_FORMAT, buf.getvalue())
    if thumb is not None:
        mime.setImageData(thumb)
    return mime


def _encoded_image(w, h, color, fmt='PNG'):
    from PIL import Image
    buf = io.BytesIO()
    Image.new('RGB', (w, h), color).save(buf, fmt)
    return buf.getvalue()
from src.utils.figpack.cache_manager import (
    PASTED_IMAGES_DIRNAME, cleanup_orphans, pasted_images_root,
)


def _png_bytes(color):
    img = QImage(8, 6, QImage.Format.Format_ARGB32)
    img.fill(color)
    return img


class ReadClipboardTests(unittest.TestCase):

    def test_plain_text_html_dropped_and_crlf_normalized(self):
        mime = QMimeData()
        mime.setText('a\r\nb\rc\n\n')
        mime.setHtml('<b>a</b>')
        content = read_clipboard(mime)
        self.assertEqual(content.text, 'a\nb\nc')
        self.assertEqual(content.preferred, 'text')
        self.assertFalse(content.has_image)

    def test_whitespace_only_text_is_none(self):
        mime = QMimeData()
        mime.setText('   \n\t ')
        self.assertIsNone(read_clipboard(mime).text)

    def test_bitmap(self):
        mime = QMimeData()
        mime.setImageData(_png_bytes(0xFF00FF00))
        content = read_clipboard(mime)
        self.assertTrue(content.has_image)
        self.assertEqual(content.preferred, 'image')

    def test_single_image_file_url(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / 'pic.png'
            _png_bytes(0xFF0000FF).save(str(p))
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(p))])
            content = read_clipboard(mime)
            self.assertEqual(os.path.normpath(content.image_path),
                             os.path.normpath(str(p)))
            self.assertEqual(content.preferred, 'image')

    def test_non_image_and_multi_urls_ignored(self):
        with tempfile.TemporaryDirectory() as td:
            f = Path(td) / 'notes.txt'
            f.write_text('x')
            img = Path(td) / 'p.png'
            _png_bytes(0xFF0000FF).save(str(img))
            mime = QMimeData()
            mime.setUrls([QUrl.fromLocalFile(str(f))])
            self.assertIsNone(read_clipboard(mime).image_path)
            mime.setUrls([QUrl.fromLocalFile(str(img)),
                          QUrl.fromLocalFile(str(img))])
            self.assertIsNone(read_clipboard(mime).image_path)

    def test_gvml_single_picture_full_res(self):
        media, = [_encoded_image(400, 300, 'red')]
        thumb = _png_bytes(0xFF00FF00)  # 8x6 preview
        mime = _gvml_mime(media=media, thumb=thumb)
        content = read_clipboard(mime)
        self.assertIsNotNone(content.image)
        self.assertEqual((content.image.width(), content.image.height()),
                         (400, 300))
        self.assertEqual(content.image_data, media)
        self.assertEqual(content.image_suffix, '.png')
        with tempfile.TemporaryDirectory() as td:
            path = store_clipboard_image(content, td)
            self.assertTrue(path.endswith('.png'))
            self.assertEqual(Path(path).read_bytes(), media)

    def test_gvml_jpeg_suffix(self):
        media = _encoded_image(50, 40, 'blue', 'JPEG')
        content = read_clipboard(
            _gvml_mime(media_name='image1.jpeg', media=media))
        self.assertEqual(content.image_suffix, '.jpg')
        self.assertEqual(content.image_data, media)

    def test_gvml_src_rect_crop(self):
        media = _encoded_image(400, 300, 'green')
        content = read_clipboard(
            _gvml_mime(media=media, crop='l="25000"'))
        self.assertIsNone(content.image_data)
        self.assertEqual((content.image.width(), content.image.height()),
                         (300, 300))

    def test_gvml_svg_blip_returns_vector_bytes(self):
        media = _encoded_image(200, 150, 'black')
        svg = b'<svg xmlns="http://www.w3.org/2000/svg"/>'
        content = read_clipboard(
            _gvml_mime(media=media, svg=svg))
        self.assertEqual(content.image_suffix, '.svg')
        self.assertEqual(content.image_data, svg)
        self.assertTrue(content.has_image)

    def test_gvml_two_pics_falls_back_to_bitmap(self):
        media = _encoded_image(400, 300, 'red')
        mime = _gvml_mime(media=media, pics=2, thumb=_png_bytes(0xFFAAAAAA))
        content = read_clipboard(mime)
        self.assertIsNone(content.image_data)
        self.assertEqual((content.image.width(), content.image.height()),
                         (8, 6))

    def test_gvml_corrupt_zip_falls_back(self):
        mime = QMimeData()
        mime.setData(GVML_FORMAT, b'not a zip')
        mime.setImageData(_png_bytes(0xFF123456))
        content = read_clipboard(mime)
        self.assertTrue(content.has_image)
        self.assertIsNone(content.image_data)

    def test_largest_raw_bitmap_wins_without_gvml(self):
        mime = QMimeData()
        mime.setImageData(_png_bytes(0xFF00FF00))  # 8x6
        mime.setData('application/x-qt-windows-mime;value="PNG"',
                     _encoded_image(300, 200, 'red'))
        content = read_clipboard(mime)
        self.assertEqual((content.image.width(), content.image.height()),
                         (300, 200))

    def test_office_text_box_still_text(self):
        # Art::Text ClipFormat is not GVML — text stays preferred.
        mime = QMimeData()
        mime.setData(
            'application/x-qt-windows-mime;value="Art::Text ClipFormat"',
            b'junk')
        mime.setImageData(_png_bytes(0xFF00FF00))
        mime.setText('text box')
        content = read_clipboard(mime)
        self.assertEqual(content.preferred, 'text')

    def test_preferred_text_beats_bitmap(self):
        mime = QMimeData()
        mime.setImageData(_png_bytes(0xFF00FF00))
        mime.setText('cell text')
        self.assertEqual(read_clipboard(mime).preferred, 'text')

    def test_web_image_link_flag(self):
        mime = QMimeData()
        mime.setHtml('<p><img src="https://x.test/a.png"></p>')
        mime.setText('alt')
        self.assertTrue(read_clipboard(mime).web_image_link)
        mime = QMimeData()
        mime.setHtml('<p><img src="https://x.test/a.png"></p>')
        mime.setImageData(_png_bytes(0xFF00FF00))
        self.assertFalse(read_clipboard(mime).web_image_link)
        mime = QMimeData()
        mime.setHtml('<p>no image</p>')
        self.assertFalse(read_clipboard(mime).web_image_link)


class StoreAndMatchTests(unittest.TestCase):

    def test_store_image_dedupes_identical_pixels(self):
        with tempfile.TemporaryDirectory() as td:
            p1 = store_image(_png_bytes(0xFF112233), td)
            p2 = store_image(_png_bytes(0xFF112233), td)
            p3 = store_image(_png_bytes(0xFF445566), td)
            self.assertEqual(p1, p2)
            self.assertNotEqual(p1, p3)
            self.assertEqual(len(list(Path(td).iterdir())), 2)

    def test_image_matches_bitmap_and_file(self):
        with tempfile.TemporaryDirectory() as td:
            existing = Path(td) / 'cell.png'
            _png_bytes(0xFF00FF00).save(str(existing))
            same = ClipboardContent(image=_png_bytes(0xFF00FF00))
            diff = ClipboardContent(image=_png_bytes(0xFF112233))
            self.assertTrue(image_matches(str(existing), same))
            self.assertFalse(image_matches(str(existing), diff))
            self.assertFalse(image_matches(None, same))
            other = Path(td) / 'other.png'
            _png_bytes(0xFF00FF00).save(str(other))
            self.assertTrue(image_matches(
                str(existing), ClipboardContent(image_path=str(other))))
            self.assertTrue(image_matches(
                str(existing), ClipboardContent(image_path=str(existing))))
            other.write_text('junk')
            self.assertFalse(image_matches(
                str(existing), ClipboardContent(image_path=str(other))))


class CacheAndRelocateTests(unittest.TestCase):

    def test_cleanup_orphans_keeps_pasted_images(self):
        with tempfile.TemporaryDirectory() as td:
            pasted = pasted_images_root(td)
            Path(pasted, 'a.png').write_bytes(b'x')
            workdir = Path(td) / 'abc__deed'
            workdir.mkdir()
            deleted = cleanup_orphans(td)
            self.assertTrue(Path(pasted).is_dir())
            self.assertFalse(workdir.exists())
            self.assertEqual(deleted, [str(workdir)])

    def test_relocate_pasted_images(self):
        from src.model.data_model import Cell, PiPItem, Project, RowTemplate
        with tempfile.TemporaryDirectory() as td:
            root = Path(td) / 'cache' / PASTED_IMAGES_DIRNAME
            root.mkdir(parents=True)
            kept = root / 'pasted-a.png'
            kept.write_bytes(b'AAAA')
            pip_img = root / 'pasted-b.png'
            pip_img.write_bytes(b'BBBB')
            outside = Path(td) / 'real.png'
            outside.write_bytes(b'CC')
            cell = Cell(image_path=str(kept))
            cell.pip_items = [PiPItem(image_path=str(pip_img))]
            other = Cell(image_path=str(outside))
            project = Project(rows=[RowTemplate()], cells=[cell, other])
            layout = Path(td) / 'fig.figlayout'
            assets_dir, copied = relocate_pasted_images(
                project, str(layout), str(root))
            self.assertEqual(Path(assets_dir), Path(td) / 'fig_assets')
            self.assertEqual(sorted(Path(c).name for c in copied),
                             ['pasted-a.png', 'pasted-b.png'])
            self.assertTrue(cell.image_path.startswith(assets_dir))
            self.assertTrue(cell.pip_items[0].image_path.startswith(
                assets_dir))
            self.assertEqual(other.image_path, str(outside))
            _dir, copied2 = relocate_pasted_images(
                project, str(layout), str(root))
            self.assertEqual(copied2, [])


class MemorySettings:
    def __init__(self):
        self.data = {'language': 'en', 'theme': 'light',
                     'autosave_interval_s': 0}

    def value(self, key, default=None, **_):
        return self.data.get(key, default)

    def setValue(self, key, value):
        self.data[key] = value

    def contains(self, key):
        return key in self.data

    def remove(self, key):
        self.data.pop(key, None)

    def sync(self):
        pass


class MainWindowPasteTests(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        import src.app.main_window as mw
        self.mw = mw
        self.settings = MemorySettings()
        self.temp = tempfile.TemporaryDirectory()
        self.paste_root = str(Path(self.temp.name) / 'cache' /
                              PASTED_IMAGES_DIRNAME)
        self.boxes = []
        self.box_role = QMessageBox.ButtonRole.RejectRole
        self.patches = [
            patch.object(mw, 'QSettings', return_value=self.settings),
            patch.object(mw, 'SnapshotStore', return_value=MagicMock()),
            patch.object(mw, 'cleanup_orphans'),
            patch.object(mw, 'register_pre_delete_hook'),
            patch.object(mw, 'HAS_OPENGL', False),
            patch.object(mw.MainWindow, '_start_update_check'),
            patch.object(mw.QMessageBox, 'exec',
                         lambda box: self._exec_box(box)),
            patch.object(mw.QMessageBox, 'warning',
                         lambda *a, **k: None),
            patch.object(mw.MainWindow, '_pasted_images_root',
                         return_value=self.paste_root),
        ]
        for p in self.patches:
            p.start()
        self.window = mw.MainWindow()
        self.window._autosave_timer.stop()
        if self.window.welcome_window is not None:
            self.window.welcome_window.hide()
        cb = QApplication.clipboard()
        self._old_clip = QMimeData()
        old = cb.mimeData()
        if old is not None:
            for fmt in old.formats():
                self._old_clip.setData(fmt, old.data(fmt))
        self.app.processEvents()

    def tearDown(self):
        QApplication.clipboard().setMimeData(self._old_clip)
        from src.utils.image_proxy import get_image_proxy
        get_image_proxy().shutdown()
        for tab in self.window._tabs:
            tab.undo_stack.clear()
        self.window.close()
        self.app.processEvents()
        for p in self.patches:
            p.stop()
        self.temp.cleanup()

    def _exec_box(self, box):
        self.boxes.append(box)
        ok = box.button(QMessageBox.StandardButton.Ok)
        if ok is not None:
            ok.click()
            return 0
        for b in box.buttons():
            if box.buttonRole(b) == self.box_role:
                b.click()
                break
        return 0

    def set_clipboard(self, mime):
        QApplication.clipboard().setMimeData(mime)
        self.app.processEvents()

    def image_mime(self, argb=0xFF00FF00):
        mime = QMimeData()
        mime.setImageData(_png_bytes(argb))
        return mime

    def cells(self):
        return self.window.project.get_all_leaf_cells()

    def select(self, cell, clear=True):
        from src.canvas.cell_item import CellItem
        if clear:
            self.window.scene.clearSelection()
        for it in self.window.scene.items():
            if isinstance(it, CellItem) and it.cell_id == cell.id:
                it.setSelected(True)
                return it
        raise AssertionError('no CellItem for cell')

    def test_paste_bitmap_into_empty_selected_cell(self):
        self.set_clipboard(self.image_mime())
        cell = self.cells()[0]
        self.select(cell)
        self.window._on_paste_clipboard()
        self.assertTrue(cell.image_path.startswith(self.paste_root))
        self.assertFalse(cell.is_placeholder)
        self.assertTrue(Path(cell.image_path).is_file())
        self.assertTrue(self.window._tabs[0].assets_dirty)
        self.assertEqual(self.window.undo_stack.undoText(), 'Paste Image')

    def test_identical_image_pushes_nothing(self):
        img = _png_bytes(0xFF00FF00)
        p = Path(self.temp.name) / 'same.png'
        img.save(str(p))
        self.cells()[0].image_path = str(p)
        self.cells()[0].is_placeholder = False
        self.set_clipboard(self.image_mime(0xFF00FF00))
        cell = self.cells()[0]
        self.select(cell)
        n = self.window.undo_stack.count()
        self.window._on_paste_clipboard()
        self.assertEqual(self.window.undo_stack.count(), n)

    def test_different_image_replaces_and_undo_restores(self):
        p = Path(self.temp.name) / 'old.png'
        _png_bytes(0xFF0000FF).save(str(p))
        cell = self.cells()[0]
        cell.image_path = str(p)
        cell.is_placeholder = False
        self.set_clipboard(self.image_mime(0xFF00FF00))
        self.select(cell)
        self.window._on_paste_clipboard()
        self.assertNotEqual(cell.image_path, str(p))
        self.window.undo_stack.undo()
        self.assertEqual(cell.image_path, str(p))

    def test_multi_select_cancel_and_paste_anyway(self):
        cells = self.cells()[:2]
        for i, c in enumerate(cells):
            self.select(c, clear=(i == 0))
        self.set_clipboard(self.image_mime())
        self.box_role = QMessageBox.ButtonRole.RejectRole
        self.window._on_paste_clipboard()
        self.assertEqual(self.window.undo_stack.count(), 0)
        self.assertTrue(all(c.image_path is None for c in cells))
        self.box_role = QMessageBox.ButtonRole.AcceptRole
        self.window._on_paste_clipboard()
        self.assertTrue(all(
            c.image_path and c.image_path.startswith(self.paste_root)
            for c in cells))
        self.assertEqual(self.window.undo_stack.count(), 1)

    def test_text_paste_creates_floating_text(self):
        mime = QMimeData()
        mime.setText('hello world')
        self.set_clipboard(mime)
        cell = self.cells()[0]
        item = self.select(cell)
        self.window._on_paste_clipboard()
        added = [t for t in self.window.project.text_items
                 if t.scope == 'global' and t.text == 'hello world']
        self.assertEqual(len(added), 1)
        center = item.sceneBoundingRect().center()
        self.assertAlmostEqual(added[0].x, center.x())
        self.assertAlmostEqual(added[0].y, center.y())

    def test_no_selection_image_is_noop(self):
        self.set_clipboard(self.image_mime())
        n = self.window.undo_stack.count()
        self.window._on_paste_clipboard()
        self.assertEqual(self.window.undo_stack.count(), n)

    def test_text_item_focus_bails(self):
        mime = QMimeData()
        mime.setText('x')
        self.set_clipboard(mime)
        fake = Mock()
        fake.textInteractionFlags.return_value = (
            Qt.TextInteractionFlag.TextEditorInteraction)
        with patch.object(self.window.scene, 'focusItem',
                          return_value=fake):
            self.window._on_paste_clipboard()
        self.assertEqual(self.window.undo_stack.count(), 0)

    def test_empty_menu_has_paste_text_action(self):
        mime = QMimeData()
        mime.setText('abc')
        self.set_clipboard(mime)
        menus = []
        orig_exec = QMenu.exec
        with patch.object(QMenu, 'exec',
                          lambda m, *a: menus.append(m) or 0):
            self.window._on_empty_context_menu(QPoint(50, 50),
                                               QPoint(50, 50))
            self.app.processEvents()
        self.assertTrue(menus)
        labels = [a.text() for a in menus[0].actions()]
        from src.app.i18n import tr
        self.assertIn(tr('ctx_paste_text'), labels)

    def test_cell_menu_paste_actions_enabled_state(self):
        self.set_clipboard(self.image_mime())
        menus = []
        with patch.object(QMenu, 'exec',
                          lambda m, *a: menus.append(m) or 0):
            self.window._on_cell_context_menu(
                self.cells()[0].id, False, QPoint(30, 30))
        self.assertTrue(menus)
        from src.app.i18n import tr
        acts = {a.text(): a for a in menus[0].actions()}
        self.assertTrue(acts[tr('ctx_paste_image')].isEnabled())
        self.assertFalse(acts[tr('ctx_paste_text')].isEnabled())

    def test_save_figlayout_relocates_and_notifies(self):
        cell = self.cells()[0]
        pasted = Path(self.paste_root)
        pasted.mkdir(parents=True)
        img = pasted / 'pasted-x.png'
        img.write_bytes(b'IMGDATA')
        cell.image_path = str(img)
        cell.is_placeholder = False
        target = str(Path(self.temp.name) / 'out.figlayout')
        self.assertTrue(self.window._save_project_to_path(
            target, notify_pasted=True))
        self.assertTrue(self.boxes)
        self.assertIn('figpack', self.boxes[0].windowTitle().lower()
                      + self.boxes[0].text().lower())
        assets = Path(self.temp.name) / 'out_assets'
        self.assertTrue((assets / 'pasted-x.png').is_file())
        self.assertTrue(cell.image_path.startswith(str(assets)))

    def test_save_default_shows_no_notice(self):
        cell = self.cells()[0]
        pasted = Path(self.paste_root)
        pasted.mkdir(parents=True)
        img = pasted / 'pasted-y.png'
        img.write_bytes(b'IMGDATA')
        cell.image_path = str(img)
        cell.is_placeholder = False
        target = str(Path(self.temp.name) / 'out.figlayout')
        self.assertTrue(self.window._save_project_to_path(target))
        self.assertFalse(self.boxes)

    def test_web_link_hint_after_text_paste(self):
        from src.app.i18n import tr
        mime = QMimeData()
        mime.setHtml('<p><img src="https://x.test/a.png"></p>')
        mime.setText('linked text')
        self.set_clipboard(mime)
        self.select(self.cells()[0])
        self.window._on_paste_clipboard()
        added = [t for t in self.window.project.text_items
                 if t.scope == 'global' and t.text == 'linked text']
        self.assertEqual(len(added), 1)
        self.assertFalse(any(c.image_path for c in self.cells()))
        self.assertEqual(self.window.statusBar().currentMessage(),
                         tr('status_paste_web_image_link'))

    def test_web_link_hint_only(self):
        from src.app.i18n import tr
        mime = QMimeData()
        mime.setHtml('<p><img src="https://x.test/a.png"></p>')
        self.set_clipboard(mime)
        n = self.window.undo_stack.count()
        self.window._on_paste_clipboard()
        self.assertEqual(self.window.undo_stack.count(), n)
        self.assertEqual(self.window.statusBar().currentMessage(),
                         tr('status_paste_web_image_link'))

    def test_cell_menu_web_link_tooltip(self):
        from src.app.i18n import tr
        mime = QMimeData()
        mime.setHtml('<p><img src="https://x.test/a.png"></p>')
        self.set_clipboard(mime)
        menus = []
        with patch.object(QMenu, 'exec',
                          lambda m, *a: menus.append(m) or 0):
            self.window._on_cell_context_menu(
                self.cells()[0].id, False, QPoint(30, 30))
        act = next(a for a in menus[0].actions()
                   if a.text() == tr('ctx_paste_image'))
        self.assertFalse(act.isEnabled())
        self.assertEqual(act.toolTip(), tr('status_paste_web_image_link'))
        self.assertTrue(menus[0].toolTipsVisible())

    def test_gvml_paste_stores_full_res(self):
        media = _encoded_image(400, 300, 'red')
        self.set_clipboard(_gvml_mime(media=media,
                                      thumb=_png_bytes(0xFF00FF00)))
        cell = self.cells()[0]
        self.select(cell)
        self.window._on_paste_clipboard()
        self.assertTrue(cell.image_path.startswith(self.paste_root))
        stored = QImage(cell.image_path)
        self.assertEqual((stored.width(), stored.height()), (400, 300))

    def test_ctrl_v_shortcut_override_in_lineedit(self):
        spy = Mock()
        self.window._act_paste.triggered.connect(spy)
        le = QLineEdit(self.window)
        le.setFocus()
        self.app.processEvents()
        ev = QKeyEvent(QEvent.Type.ShortcutOverride, Qt.Key.Key_V,
                       Qt.KeyboardModifier.ControlModifier)
        QApplication.sendEvent(le, ev)
        self.assertTrue(ev.isAccepted())
        spy.assert_not_called()


if __name__ == '__main__':
    unittest.main()
