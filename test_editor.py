"""Core and Qt/worker regression tests. Run with python -m unittest -v."""
import base64
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
import pymupdf as fitz
from PySide6.QtCore import QPoint, QPointF, Qt, QMimeData, QUrl
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtTest import QTest
from pdf_core import add_text, delete_text, windows_fonts, text_spans
from pdf_worker import Engine
from pdf_editor import Editor
from alignment import snap_box, nearest_span, match_font


def fixture(path, rotation=0, encrypted=False):
    with fitz.open() as doc:
        page = doc.new_page(width=640, height=800)
        page.set_rotation(rotation)
        font = windows_fonts().get('Arial')
        add_text(page, 50, 100, 'Reference text', 18, (0.1, 0.2, 0.7), font, 220, 70, True)
        add_text(page, 50, 210, 'DELETE ME', 14, (0, 0, 0), font, 220, 70)
        page.draw_rect(fitz.Rect(20, 20, 600, 700), color=(0.8, 0.8, 0.8))
        doc.new_page(width=400, height=500).insert_text((30, 60), 'Second page')
        if encrypted:
            doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner-test', user_pw='user-test')
        else:
            doc.save(path)


class CoreTests(unittest.TestCase):
    def test_baseline_snapping_is_not_box_top_alignment(self):
        span = dict(bbox=[50, 100, 150, 125], baseline=120, horizontal=True)
        x, y, guides = snap_box(52, 103, 200, 80, 15, [span], 4)
        self.assertEqual((x, y), (50, 105))
        self.assertIn(('h', 120), guides)
        self.assertIn(('v', 50), guides)
        self.assertEqual(nearest_span(60, 110, [span]), span)
        self.assertIsNone(nearest_span(500, 400, [span]))
        self.assertEqual(match_font('ABCDEE+Arial-BoldMT', windows_fonts()), 'Arial')
        self.assertIsNone(match_font('UnavailableCustomFont', windows_fonts()))

    def test_rotated_preview_baseline_matches_export(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'source.pdf'
                fixture(path, rotation)
                engine = Engine()
                data = engine.run(dict(kind='open', path=str(path)))
                reference = next(s for s in data['spans'] if 'Reference' in s['text'])
                self.assertTrue(reference['horizontal'])
                spec = dict(x=300, y=0, width=210, height=100, size=18, color=(0.1, 0.2, 0.7),
                            fontfile=windows_fonts().get('Arial'), bold=True, text='Aligned text')
                preview = engine.run(dict(kind='preview', spec=spec, scale=2))
                spec['y'] = reference['baseline'] - preview['baseline_offset']
                modified = engine.run(dict(kind='insert', index=0, spec=spec))
                inserted = next(s for s in modified['spans'] if 'Aligned' in s['text'])
                self.assertAlmostEqual(inserted['baseline'], reference['baseline'], delta=0.02)
                output = Path(directory) / 'output.pdf'
                engine.run(dict(kind='save', path=str(output)))
                with fitz.open(output) as saved:
                    self.assertIn('Aligned text', saved[0].get_text().replace('\xa0', ' '))
                engine.doc.close()

    def test_true_deletion_and_undo_preserve_graphics(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'original.pdf'
            fixture(path)
            engine = Engine()
            engine.run(dict(kind='open', path=str(path)))
            target = engine.doc[0].search_for('DELETE ME')[0]
            count = len(engine.doc[0].get_drawings())
            engine.run(dict(kind='delete', index=0, rect=list(target)))
            self.assertNotIn('DELETE ME', engine.doc[0].get_text().replace('\xa0', ' '))
            self.assertEqual(len(engine.doc[0].get_drawings()), count)
            engine.run(dict(kind='undo'))
            self.assertIn('DELETE ME', engine.doc[0].get_text().replace('\xa0', ' '))
            engine.doc.close()

    def test_encrypted_save_after_undo_and_original_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'secret.pdf'
            fixture(path, encrypted=True)
            engine = Engine()
            self.assertTrue(engine.run(dict(kind='open', path=str(path)))['password_required'])
            engine.run(dict(kind='open', path=str(path), password='user-test'))
            rect = engine.doc[0].search_for('DELETE ME')[0]
            engine.run(dict(kind='delete', index=0, rect=list(rect)))
            engine.run(dict(kind='undo'))
            with self.assertRaises(ValueError):
                engine.run(dict(kind='save', path=str(path)))
            output = Path(directory) / 'copy.pdf'
            engine.run(dict(kind='save', path=str(output)))
            with fitz.open(output) as saved:
                self.assertTrue(saved.needs_pass)
                self.assertTrue(saved.authenticate('user-test'))
                self.assertIn('DELETE ME', saved[0].get_text().replace('\xa0', ' '))
            engine.doc.close()

    def test_preview_overflow_transaction_and_tile_bound(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'source.pdf'
            fixture(path)
            engine = Engine()
            engine.run(dict(kind='open', path=str(path)))
            before = engine.doc[0].get_text().replace('\xa0', ' ')
            spec = dict(x=0, y=0, width=12, height=12, text='Too long for this tiny box', size=40, color=(0, 0, 0))
            with self.assertRaises(ValueError):
                engine.run(dict(kind='insert', index=0, spec=spec))
            self.assertEqual(before, engine.doc[0].get_text().replace('\xa0', ' '))
            tile = engine.run(dict(kind='tile', index=0, revision=engine.revision, scale=4,
                                   clip=[0, 0, 128, 128]))
            pix = fitz.Pixmap(base64.b64decode(tile['image']))
            self.assertEqual((pix.width, pix.height), (512, 512))
            self.assertTrue(engine.run(dict(kind='tile', index=0, revision=-1))['stale'])
            engine.doc.close()

    def test_chinese_bold_and_font_embedding(self):
        for name in ('微软雅黑', '宋体'):
            font = windows_fonts().get(name)
            if not font:
                continue
            with self.subTest(font=name), fitz.open() as doc:
                p = doc.new_page()
                add_text(p, 40, 50, '加粗文字测试', 20, (0, 0, 0), font, 400, 100, True)
                normal = doc.new_page()
                add_text(normal, 40, 50, '加粗文字测试', 20, (0, 0, 0), font, 400, 100, False)
                with fitz.open(stream=doc.tobytes(), filetype='pdf') as saved:
                    self.assertIn('加粗文字测试', saved[0].get_text().replace('\xa0', ' '))
                    self.assertNotEqual(saved[0].get_pixmap().samples, saved[1].get_pixmap().samples)
                    self.assertTrue(any(len(saved.extract_font(f[0])[3]) > 1000 for f in saved[0].get_fonts()))


class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / '中文 空格.pdf'
        fixture(self.path)
        self.messages = []
        self.warning = patch.object(QMessageBox, 'warning', side_effect=lambda *a: self.messages.append(a[-1]))
        self.critical = patch.object(QMessageBox, 'critical', side_effect=lambda *a: self.messages.append(a[-1]))
        self.warning.start()
        self.critical.start()
        self.editor = Editor()
        self.editor.show()
        self.editor.open_pdf(str(self.path))
        self.wait(lambda: self.editor.path is not None and not self.editor.busy)

    def wait(self, predicate, seconds=15):
        end = time.perf_counter() + seconds
        while time.perf_counter() < end:
            QApplication.processEvents()
            if predicate():
                return
            time.sleep(0.01)
        self.fail('Timed out. Messages: ' + repr(self.messages) + ' Worker: ' + self.editor.client.stderr + ' Preview: ' + self.editor.preview_label.text())

    def tearDown(self):
        e = self.editor
        e.tile_timer.stop()
        e.preview_timer.stop()
        e.client.close()
        e.busy = False
        e.dirty = False
        e.cancel()
        e.close()
        self.warning.stop()
        self.critical.stop()
        self.temp.cleanup()
        self.assertEqual(self.messages, [])

    def make_draft(self):
        e = self.editor
        span = next(s for s in e.spans if 'Reference' in s['text'])
        e.sample(QPointF(span['bbox'][0] + 5, span['baseline'] - 3))
        e.text_input.setPlainText('Aligned text')
        e.place(QPointF(300, span['baseline'] + 2))
        self.wait(lambda: e.draft is not None and e.draft.valid)
        return span

    def test_qt_pdf_drop_with_chinese_and_spaces(self):
        e = self.editor
        other = Path(self.temp.name) / '另一个 文件.pdf'
        fixture(other)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(other))])
        enter = QDragEnterEvent(QPoint(100, 100), Qt.DropAction.CopyAction, mime,
                               Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(e.view.viewport(), enter)
        self.assertTrue(enter.isAccepted())
        drop = QDropEvent(QPointF(100, 100), Qt.DropAction.CopyAction, mime,
                         Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(e.view.viewport(), drop)
        self.assertTrue(drop.isAccepted())
        self.wait(lambda: e.path == other and not e.busy)

    def test_worker_is_separate_and_zoom_does_not_request_pdf_per_event(self):
        e = self.editor
        self.assertNotEqual(e.client.process.processId(), os.getpid())
        self.wait(lambda: bool(e.tile_items))
        e.tile_timer.stop()
        initial = e.client.serial
        for _ in range(20):
            e.view.set_zoom(e.view.zoom * 1.02, QPoint(300, 250))
        self.assertEqual(e.client.serial, initial)
        self.wait(lambda: e.client.serial > initial)
        self.assertLessEqual(e.cache_bytes, 64 * 1024 * 1024)

    def test_sample_snap_commit_save_and_undo(self):
        e = self.editor
        span = self.make_draft()
        self.assertAlmostEqual(e.size.value(), 18)
        self.assertTrue(e.bold.isChecked())
        self.assertAlmostEqual(e.draft.y() + e.draft.offset, span['baseline'], delta=0.02)
        e.apply()
        self.wait(lambda: not e.busy and e.draft is None)
        inserted = next(s for s in e.spans if 'Aligned' in s['text'])
        self.assertAlmostEqual(inserted['baseline'], span['baseline'], delta=0.02)
        output = Path(self.temp.name) / 'saved.pdf'
        with patch('pdf_editor.QFileDialog.getSaveFileName', return_value=(str(output), 'PDF')):
            e.save()
        self.wait(lambda: not e.busy and output.exists())
        with fitz.open(output) as doc:
            self.assertIn('Aligned text', doc[0].get_text().replace('\xa0', ' '))
        e.view.setFocus()
        e.undo()
        self.wait(lambda: not e.busy)
        self.assertFalse(any('Aligned' in s['text'] for s in e.spans))

    def test_drag_and_resize_using_qt_mouse_events(self):
        e = self.editor
        self.make_draft()
        e.snap.setChecked(False)
        draft = e.draft
        before = draft.pos()
        center = e.view.mapFromScene(draft.mapToScene(QPointF(40, 40)))
        QTest.mousePress(e.view.viewport(), Qt.MouseButton.LeftButton, pos=center)
        QTest.mouseMove(e.view.viewport(), center + QPoint(30, 20), delay=20)
        QTest.mouseRelease(e.view.viewport(), Qt.MouseButton.LeftButton, pos=center + QPoint(30, 20))
        self.assertGreater(draft.x(), before.x())
        self.assertGreater(draft.y(), before.y())
        width, height = draft.w, draft.h
        corner = e.view.mapFromScene(draft.mapToScene(QPointF(width, height)))
        QTest.mousePress(e.view.viewport(), Qt.MouseButton.LeftButton, pos=corner)
        QTest.mouseMove(e.view.viewport(), corner + QPoint(20, 20), delay=20)
        QTest.mouseRelease(e.view.viewport(), Qt.MouseButton.LeftButton, pos=corner + QPoint(20, 20))
        self.assertGreater(draft.w, width)
        self.assertGreater(draft.h, height)
        self.wait(lambda: draft.valid)

    def test_pointer_zoom_and_move_reuses_text_preview(self):
        e = self.editor
        self.make_draft()
        e.view.set_zoom(2)
        e.view.centerOn(QPointF(300, 300))
        point = QPoint(250, 220)
        before = e.view.mapToScene(point)
        preview = e.draft.pixmap.cacheKey()
        version = e.preview_version
        e.view.set_zoom(2.4, point)
        after = e.view.mapToScene(point)
        self.assertLess((after - before).manhattanLength(), 2)
        e.draft.setPos(e.draft.pos() + QPointF(10, 10))
        e.draft_changed(False)
        self.assertEqual(e.preview_version, version)
        self.assertEqual(e.draft.pixmap.cacheKey(), preview)

    def test_click_delete_and_undo(self):
        e = self.editor
        span = next(s for s in e.spans if 'DELETE' in s['text'])
        e.mode.setCurrentIndex(e.mode.findData('erase'))
        x0, y0, x1, y1 = span['bbox']
        point = e.view.mapFromScene(QPointF((x0 + x1) / 2, (y0 + y1) / 2))
        QTest.mouseMove(e.view.viewport(), point)
        QTest.mouseClick(e.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        self.wait(lambda: not e.busy)
        self.assertFalse(any('DELETE' in s['text'] for s in e.spans))
        self.assertTrue(any('Reference' in s['text'] for s in e.spans))
        e.undo()
        self.wait(lambda: not e.busy)
        self.assertTrue(any('DELETE' in s['text'] for s in e.spans))

    def test_box_delete_via_mouse_and_export(self):
        e = self.editor
        span = next(s for s in e.spans if 'DELETE' in s['text'])
        e.mode.setCurrentIndex(e.mode.findData('delete'))
        x0, y0, x1, y1 = span['bbox']
        start = e.view.mapFromScene(QPointF(x0 - 2, y0 - 2))
        end = e.view.mapFromScene(QPointF(x1 + 2, y1 + 2))
        QTest.mousePress(e.view.viewport(), Qt.MouseButton.LeftButton, pos=start)
        QTest.mouseMove(e.view.viewport(), end, delay=20)
        QTest.mouseRelease(e.view.viewport(), Qt.MouseButton.LeftButton, pos=end)
        self.wait(lambda: not e.busy)
        self.assertFalse(any('DELETE' in s['text'] for s in e.spans))
        output = Path(self.temp.name) / 'deleted.pdf'
        with patch('pdf_editor.QFileDialog.getSaveFileName', return_value=(str(output), 'PDF')):
            e.save()
        self.wait(lambda: not e.busy and output.exists())
        with fitz.open(output) as doc:
            self.assertNotIn('DELETE', doc[0].get_text())
            self.assertTrue(doc[0].get_drawings())

    def test_delete_key_removes_draft_not_original(self):
        e = self.editor
        self.make_draft()
        original = list(e.spans)
        point = e.view.mapFromScene(e.draft.mapToScene(QPointF(30, 30)))
        QTest.mouseClick(e.view.viewport(), Qt.MouseButton.LeftButton, pos=point)
        QTest.keyClick(e.view.viewport(), Qt.Key.Key_Delete)
        self.assertIsNone(e.draft)
        self.assertEqual(e.spans, original)
        self.assertFalse(e.dirty)

    def test_stale_preview_and_page_results_are_ignored(self):
        e = self.editor
        self.make_draft()
        current = e.draft.pixmap.cacheKey()
        e.on_result(dict(request=dict(kind='preview', epoch=e.epoch, version=e.preview_version - 1),
                         data=dict(image='invalid', baseline_offset=999)))
        self.assertEqual(e.draft.pixmap.cacheKey(), current)
        e.cancel()
        e.turn(1)
        self.wait(lambda: not e.busy and e.index == 1)
        self.assertTrue(any('Second page' in s['text'] for s in e.spans))
        e.on_result(dict(request=dict(kind='tile', epoch=e.epoch - 1), data=dict(image='invalid')))
        self.assertEqual(e.index, 1)


if __name__ == '__main__':
    unittest.main()
