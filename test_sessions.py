"""Session-object editing integration tests: PDF content, not only UI state."""
from pathlib import Path
import tempfile
import unittest
import pymupdf as fitz
from pdf_core import text_characters, windows_fonts
from pdf_worker import Engine
from test_editor import fixture
from alignment import word_at


class SessionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / 'source.pdf'
        fixture(self.path)
        self.engine = Engine()
        self.engine.run(dict(kind='open', path=str(self.path)))
        self.spec = dict(x=50, y=100, width=230, height=80, text='Session text', size=18,
                         fontfile=windows_fonts().get('Arial'), color=(1, 0, 0), bold=True)

    def tearDown(self):
        self.engine.end_edit()
        self.engine.doc.close()
        self.temp.cleanup()

    def add(self, spec=None, index=0):
        return self.engine.run(dict(kind='insert', index=index, spec=spec or self.spec))['objects'][-1]

    def begin(self, obj):
        return self.engine.run(dict(kind='begin_edit', index=obj['index'],
                                   revision=self.engine.revision, object_id=obj['id']))

    def update(self, obj, spec):
        return self.engine.run(dict(kind='update_object', index=obj['index'], object_id=obj['id'],
                                   revision=self.engine.revision, spec=spec))

    def test_overlapping_original_is_preserved_through_update_undo_redo(self):
        e = self.engine
        before = text_characters(e.doc[0])
        obj = self.add()
        self.begin(obj)
        self.assertEqual(text_characters(e.edit_doc[0]), before)
        self.assertIn('Session', e.doc[0].get_text())
        edited = dict(self.spec, x=300, y=170, text='Moved text', size=22, bold=False, color=(0, 0, 1))
        result = self.update(obj, edited)
        self.assertIsNone(e.edit_doc)
        self.assertNotIn('Session', e.doc[0].get_text())
        self.assertIn('Moved', e.doc[0].get_text())
        self.assertEqual(text_characters(e.doc[0])[:len(before)], before)
        self.assertEqual(result['objects'][0]['spec'], edited)
        e.run(dict(kind='undo'))
        self.assertEqual(e.objects[obj['id']]['spec'], self.spec)
        self.assertIn('Session', e.doc[0].get_text())
        e.run(dict(kind='redo'))
        self.assertEqual(e.objects[obj['id']]['spec'], edited)
        self.begin(e.objects[obj['id']])
        self.assertEqual(text_characters(e.edit_doc[0]), before)

    def test_cancel_has_no_history_or_dirty_change_and_blocks_save(self):
        e = self.engine
        obj = self.add()
        output = Path(self.temp.name) / 'saved.pdf'
        e.run(dict(kind='save', path=str(output)))
        chars, history = text_characters(e.doc[0]), len(e.history)
        self.begin(obj)
        self.assertFalse(e.dirty)
        with self.assertRaisesRegex(ValueError, '应用或取消'):
            e.run(dict(kind='save', path=str(output)))
        e.run(dict(kind='cancel_edit'))
        self.assertEqual(text_characters(e.doc[0]), chars)
        self.assertEqual(len(e.history), history)
        self.assertFalse(e.dirty)

    def test_failed_update_preserves_original_and_remains_editable(self):
        e = self.engine
        obj = self.add()
        before = text_characters(e.doc[0])
        self.begin(obj)
        with self.assertRaises(ValueError):
            self.update(obj, dict(self.spec, width=12, height=12, size=50))
        self.assertEqual(text_characters(e.doc[0]), before)
        self.assertEqual(e.objects[obj['id']]['spec'], self.spec)
        self.assertIsNotNone(e.edit_doc)
        self.update(obj, dict(self.spec, text='Fixed text'))
        self.assertIn('Fixed', e.doc[0].get_text())

    def test_save_keeps_two_objects_editable_and_export_has_no_old_text(self):
        e = self.engine
        first = self.add()
        second = self.add(dict(self.spec, y=300, text='Other text'))
        output = Path(self.temp.name) / 'saved.pdf'
        e.run(dict(kind='save', path=str(output)))
        self.begin(first)
        self.update(first, dict(self.spec, text='Replacement'))
        e.run(dict(kind='save', path=str(output)))
        self.begin(second)
        self.update(second, dict(self.spec, y=320, text='Second edited'))
        e.run(dict(kind='save', path=str(output)))
        with fitz.open(output) as saved:
            text = saved[0].get_text()
            self.assertIn('Replacement', text)
            self.assertIn('Second', text)
            self.assertNotIn('Session', text)
            self.assertNotIn('Other', text)
            self.assertTrue(saved[0].get_drawings())
        # Reopening is intentionally a new session: no stale xrefs are recovered.
        e.run(dict(kind='open', path=str(output)))
        self.assertFalse(e.objects)

    def test_redaction_retires_page_objects_and_undo_restores_identity(self):
        e = self.engine
        first = self.add()
        second = self.add(dict(self.spec, x=30, y=150), index=1)
        target = e.doc[0].search_for('DELETE')[0]
        result = e.run(dict(kind='delete', index=0, rect=list(target)))
        self.assertEqual(result['objects'], [])
        self.assertIn(second['id'], e.objects)
        e.run(dict(kind='undo'))
        self.assertIn(first['id'], e.objects)
        self.begin(e.objects[first['id']])
        self.assertNotIn('Session', e.edit_doc[0].get_text())

    def test_rotated_encrypted_edit_export_and_undo(self):
        e = self.engine
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                path = Path(self.temp.name) / f'encrypted-{rotation}.pdf'
                fixture(path, rotation=rotation, encrypted=True)
                e.run(dict(kind='open', path=str(path), password='user-test'))
                original = text_characters(e.doc[0])
                obj = self.add()
                self.begin(obj)
                self.assertEqual(text_characters(e.edit_doc[0]), original)
                self.update(obj, dict(self.spec, text='Changed', x=300))
                e.run(dict(kind='undo'))
                e.run(dict(kind='redo'))
                output = Path(self.temp.name) / f'output-{rotation}.pdf'
                e.run(dict(kind='save', path=str(output)))
                with fitz.open(output) as saved:
                    self.assertTrue(saved.needs_pass)
                    self.assertTrue(saved.authenticate('user-test'))
                    self.assertEqual(text_characters(saved[0])[:len(original)], original)
                    self.assertIn('Changed', saved[0].get_text())
                    self.assertNotIn('Session', saved[0].get_text())
                self.begin(e.objects[obj['id']])
                e.run(dict(kind='cancel_edit'))

    def test_word_selection_respects_punctuation_line_and_rotation(self):
        with fitz.open() as doc:
            p = doc.new_page()
            p.insert_text((50, 80), "can't stop, next", fontsize=18)
            p.insert_text((50, 110), 'Another line', fontsize=18)
            for angle in (0, 90, 180, 270):
                p.set_rotation(angle)
                chars = text_characters(p)
                target = chars[2]
                x0, y0, x1, y1 = target['bbox']
                selected = word_at((x0+x1)/2, (y0+y1)/2, chars)
                self.assertEqual(''.join(c['text'] for c in selected), "can't")
                target = next(c for c in chars if c['text'] == ',')
                x0, y0, x1, y1 = target['bbox']
                self.assertEqual(''.join(c['text'] for c in word_at((x0+x1)/2, (y0+y1)/2, chars)), ',')


if __name__ == '__main__':
    unittest.main()
