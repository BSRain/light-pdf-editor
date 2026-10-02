"""Navigation correctness, lazy work bounds and worker isolation."""
import base64
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pymupdf as fitz
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage
from PySide6.QtWidgets import QApplication, QMessageBox
from pdf_worker import Engine
import test_editor as helpers


class NavigationTests(unittest.TestCase):
    setUpClass = classmethod(helpers.QtTests.setUpClass.__func__)
    setUp = helpers.QtTests.setUp
    tearDown = helpers.QtTests.tearDown
    wait = helpers.QtTests.wait
    make_draft = helpers.QtTests.make_draft

    def test_jump_bounds_and_draft_guard(self):
        e = self.editor
        for target in (-1, e.count, 0):
            e.go_to_page(target)
            self.assertFalse(e.busy)
        self.make_draft()
        with patch.object(QMessageBox, 'information') as message:
            e.go_to_page(1)
            message.assert_called_once()
        self.assertEqual(e.index, 0)
        self.assertIsNotNone(e.draft)
        e.cancel()
        e.go_to_page(1)
        self.wait(lambda: e.index == 1 and not e.busy)
        self.assertFalse(e.next_action.isEnabled())
        self.assertTrue(e.prev_action.isEnabled())

    def test_thumbnails_lazy_and_stale_result_ignored(self):
        e = self.editor
        e.schedule_thumbnails()
        self.assertEqual(e.client.thumbnails, [])
        self.assertTrue(e.page_list.item(0).icon().isNull())
        e.pages_dock.show()
        self.wait(lambda: not e.page_list.item(0).icon().isNull())
        self.assertEqual(e.page_list.count(), 2)
        e.receive_thumbnail(dict(request=dict(index=0, generation=e.thumbnail_generation-1,
                                             revision=e.revision), data=dict(image='invalid')))
        self.assertFalse(e.page_list.item(0).icon().isNull())
        e.pages_dock.hide()
        self.assertEqual(e.client.thumbnails, [])

    def test_large_document_bounded_group_and_visible_requests(self):
        e = self.editor
        path = Path(self.temp.name) / 'many.pdf'
        with fitz.open() as doc:
            for _ in range(101):
                doc.new_page()
            doc.save(path)
        e.open_pdf(str(path))
        self.wait(lambda: e.path == path and not e.busy)
        e.pages_dock.show()
        QApplication.processEvents()
        e.schedule_thumbnails()
        self.assertEqual(e.page_list.count(), 20)
        self.assertLess(len(e.client.thumbnails), 20)
        e.go_to_page(100)
        self.wait(lambda: e.index == 100 and not e.busy)
        self.assertEqual(e.thumbnail_start, 100)
        self.assertEqual(e.page_list.count(), 1)
        self.assertFalse(e.next_group.isEnabled())
        e.show_thumbnail_group(80)
        self.assertEqual(e.page_list.count(), 20)
        self.assertEqual(e.index, 100)
        self.assertEqual(e.page_list.item(0).data(Qt.ItemDataRole.UserRole), 80)

    def test_erasure_guard(self):
        e = self.editor
        from PySide6.QtCore import QRectF
        e.mode.setCurrentIndex(e.mode.findData('erase_image'))
        e.preview_image_erase(QRectF(40,40,50,50))
        with patch.object(QMessageBox, 'information'):
            e.go_to_page(1)
        self.assertEqual(e.index, 0)
        self.assertIsNotNone(e.erase_selection)


class ThumbnailWorkerTests(unittest.TestCase):
    def test_small_rotated_encrypted_thumbnail_preserves_display_cache(self):
        from test_editor import fixture
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'encrypted.pdf'
            fixture(path, rotation=90, encrypted=True)
            engine = Engine()
            try:
                data = engine.run(dict(kind='open', path=str(path), password='user-test'))
                display, key = engine.display, engine.display_key
                result = engine.run(dict(kind='thumbnail', index=1, revision=data['revision']))
                image = QImage.fromData(base64.b64decode(result['image']), 'PNG')
                self.assertLessEqual(image.width(), 131)
                self.assertLessEqual(image.height(), 171)
                self.assertIs(engine.display, display)
                self.assertEqual(engine.display_key, key)
                self.assertTrue(engine.run(dict(kind='thumbnail', index=0, revision=-1))['stale'])
                self.assertFalse(engine.dirty)
            finally:
                engine.doc.close()


class NavigationSchedulingTests(unittest.TestCase):
    def test_edit_preview_and_tiles_precede_thumbnails(self):
        from collections import deque
        from types import SimpleNamespace
        from unittest.mock import Mock
        from PySide6.QtCore import QProcess
        from pdf_editor import PdfClient
        process = Mock()
        process.state.return_value = QProcess.ProcessState.Running
        client = SimpleNamespace(stopping=False, dead=False, active=None, process=process,
            commands=deque([dict(kind='insert')]), preview=dict(kind='preview'),
            tiles=[dict(kind='tile')], thumbnails=[dict(kind='thumbnail')], serial=0)
        for kind in ('insert', 'preview', 'tile', 'thumbnail'):
            PdfClient.dispatch(client)
            self.assertEqual(client.active['kind'], kind)
            client.active = None
        self.assertEqual(process.write.call_count, 4)
