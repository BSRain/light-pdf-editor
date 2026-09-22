"""Project roundtrips verify rendered content, encryption and atomic failure."""
from pathlib import Path
import tempfile
import json
import unittest
from unittest.mock import patch
import pymupdf as fitz
from pdf_worker import Engine
from pdf_core import windows_fonts
from project_file import ATTACHMENT


class ProjectTests(unittest.TestCase):
    def test_roundtrip_without_source_rotations_and_export(self):
        for angle in (0, 90, 180, 270):
            with self.subTest(rotation=angle), tempfile.TemporaryDirectory() as folder:
                source = Path(folder) / 'source.pdf'
                target = Path(folder) / 'project.lpdf'
                with fitz.open() as doc:
                    p = doc.new_page(width=600, height=800)
                    p.set_rotation(angle)
                    doc.new_page()
                    doc.save(source)
                e = Engine()
                try:
                    e.run(dict(kind='open', path=str(source)))
                    spec = dict(x=50, y=100, width=260, height=120, text='工程第一行\n第二行',
                                size=16, color=(0, 0, 0), fontfile=windows_fonts()['微软雅黑'], bold=True, line_spacing=28)
                    e.run(dict(kind='insert', spec=spec))
                    e.run(dict(kind='insert', index=1, spec=dict(spec, text='另一页')))
                    pixels = e.doc[0].get_pixmap().samples
                    e.run(dict(kind='save_project', path=str(target), index=1))
                    e.doc.close(); e.doc = None
                    source.unlink()
                    result = e.run(dict(kind='open', path=str(target)))
                    self.assertEqual(result['index'], 1)
                    self.assertEqual(len(e.objects), 2)
                    self.assertFalse(result['can_undo'])
                    self.assertEqual(e.doc[0].get_pixmap().samples, pixels)
                    obj = e.objects['1']
                    e.run(dict(kind='begin_edit', object_id='1', revision=e.revision))
                    e.run(dict(kind='update_object', object_id='1', revision=e.revision, spec=dict(spec, text='已重新编辑')))
                    output = Path(folder) / 'export.pdf'
                    e.run(dict(kind='save', path=str(output)))
                    with fitz.open(output) as doc:
                        self.assertNotIn(ATTACHMENT, doc.embfile_names())
                        self.assertIn('已重新编辑', doc[0].get_text())
                        self.assertNotIn('工程第一行', doc[0].get_text())
                    second = Path(folder) / 'second.lpdf'
                    e.run(dict(kind='save_project', path=str(second)))
                    e.run(dict(kind='open', path=str(second)))
                    self.assertEqual(e.objects['1']['spec']['text'], '已重新编辑')
                finally:
                    e.end_edit()
                    if e.doc: e.doc.close()

    def test_encrypted_project_requires_password_and_encrypts_manifest(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'secret.pdf', Path(folder)/'secret.lpdf'
            with fitz.open() as doc:
                doc.new_page()
                doc.save(source, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='user123', owner_pw='owner123')
            e = Engine()
            try:
                e.run(dict(kind='open', path=str(source), password='user123'))
                spec = dict(x=30, y=40, width=200, height=100, text='SECRET_EDITABLE_TEXT_123', size=12, color=(0,0,0))
                e.run(dict(kind='insert', spec=spec))
                e.run(dict(kind='save_project', path=str(target)))
                content = target.read_bytes()
                self.assertNotIn(b'SECRET_EDITABLE_TEXT_123', content)
                self.assertNotIn(b'user123', content)
                with fitz.open(target) as doc:
                    self.assertTrue(doc.needs_pass)
                    self.assertTrue(doc.authenticate('user123'))
                    self.assertIn(b'SECRET_EDITABLE_TEXT_123', doc.embfile_get(ATTACHMENT))
                result = e.run(dict(kind='open', path=str(target), password='wrong'))
                self.assertTrue(result['password_required'])
                self.assertEqual(e.path, source.resolve())
                result = e.run(dict(kind='open', path=str(target), password='user123'))
                self.assertEqual(result['objects'][0]['spec']['text'], spec['text'])
                e.run(dict(kind='begin_edit', object_id='1', revision=e.revision))
                e.run(dict(kind='update_object', object_id='1', revision=e.revision, spec=dict(spec,text='UPDATED')))
            finally:
                e.end_edit()
                if e.doc: e.doc.close()

    def test_bad_manifest_rejected_without_replacing_active_document(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'source.pdf', Path(folder)/'project.lpdf'
            with fitz.open() as doc:
                doc.new_page(); doc.save(source)
            e = Engine()
            try:
                e.run(dict(kind='open', path=str(source)))
                spec = dict(x=30, y=40, width=200, height=100, text='Safe text', size=12, color=(0,0,0))
                e.run(dict(kind='insert', spec=spec))
                e.run(dict(kind='save_project', path=str(target)))
                for case in ('version', 'stream', 'bounds', 'nan'):
                    with self.subTest(case=case), fitz.open(target) as doc:
                        data = json.loads(doc.embfile_get(ATTACHMENT))
                        if case == 'version': data['version'] = 999
                        elif case == 'stream': data['objects']['1']['streams'][0][1] = 'wrong'
                        elif case == 'bounds': data['objects']['1']['spec']['width'] = 100000
                        else: data['objects']['1']['spec']['size'] = float('nan')
                        doc.embfile_del(ATTACHMENT)
                        doc.embfile_add(ATTACHMENT, json.dumps(data).encode())
                        broken = Path(folder)/(case + '.lpdf')
                        doc.save(broken)
                        with self.assertRaises(ValueError):
                            e.run(dict(kind='open', path=str(broken)))
                        self.assertEqual(e.path, source.resolve())
                        self.assertIn('Safe text', e.doc[0].get_text())
            finally:
                e.end_edit()
                if e.doc: e.doc.close()

    def test_modified_project_rejected_and_failed_save_preserves_target(self):
        with tempfile.TemporaryDirectory() as folder:
            source, target = Path(folder)/'source.pdf', Path(folder)/'project.lpdf'
            with fitz.open() as doc:
                doc.new_page(); doc.save(source)
            e = Engine()
            try:
                e.run(dict(kind='open', path=str(source)))
                e.run(dict(kind='save_project', path=str(target)))
                original = target.read_bytes()
                with patch('pdf_worker.os.replace', side_effect=OSError('simulated failure')):
                    with self.assertRaises(OSError):
                        e.run(dict(kind='save_project', path=str(target)))
                self.assertEqual(target.read_bytes(), original)
                self.assertEqual(sorted(p.name for p in Path(folder).iterdir()), ['project.lpdf','source.pdf'])
                modified = Path(folder)/'changed.lpdf'
                with fitz.open(target) as doc:
                    doc[0].insert_text((40,50), 'External change')
                    doc.save(modified)
                with self.assertRaisesRegex(ValueError, '页面已被'):
                    e.run(dict(kind='open', path=str(modified)))
                self.assertEqual(e.path, source.resolve())
                self.assertEqual(e.doc[0].get_text(), '')
            finally:
                e.end_edit()
                if e.doc: e.doc.close()


if __name__ == '__main__':
    unittest.main()
