"""Real raster removal, page isolation, encrypted export and undo."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image
import pymupdf as fitz
from pdf_worker import Engine


def scan_fixture(path, rotation=0, encrypted=False, shared=False):
    stream = io.BytesIO()
    Image.new('RGB', (300, 300), (0, 0, 0)).save(stream, format='PNG')
    with fitz.open() as doc:
        page = doc.new_page(width=300, height=300)
        xref = page.insert_image(page.rect, stream=stream.getvalue())
        page.insert_text((65, 95), 'SECRET', fontsize=12, render_mode=3)
        page.set_rotation(rotation)
        if shared:
            doc.new_page(width=300, height=300).insert_image(fitz.Rect(0,0,300,300), xref=xref)
        options = dict(encryption=fitz.PDF_ENCRYPT_AES_256, owner_pw='owner', user_pw='test') if encrypted else {}
        doc.save(path, **options)


class ImageEraseTests(unittest.TestCase):
    def test_rotations_export_removes_pixels_ocr_and_unused_original(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation), tempfile.TemporaryDirectory() as folder:
                path = Path(folder)/'scan.pdf'
                scan_fixture(path, rotation)
                e = Engine()
                try:
                    e.run(dict(kind='open', path=str(path)))
                    old_digest = hashlib.sha256(e.doc.xref_stream(e.doc[0].get_images()[0][0])).hexdigest()
                    original = e.doc[0].get_pixmap().samples
                    area = fitz.Rect(55,65,125,110) * e.doc[0].rotation_matrix
                    e.run(dict(kind='erase_image', index=0, revision=e.revision, rect=list(area)))
                    self.assertNotIn('SECRET', e.doc[0].get_text())
                    self.assertEqual(e.doc[0].get_pixmap().pixel(round(area.tl.x+5),round(area.tl.y+5)), (255,255,255))
                    e.run(dict(kind='undo', index=0))
                    self.assertEqual(e.doc[0].get_pixmap().samples, original)
                    e.run(dict(kind='redo', index=0))
                    target = Path(folder)/'export.pdf'
                    e.run(dict(kind='save', path=str(target)))
                    with fitz.open(target) as doc:
                        self.assertNotIn('SECRET', doc[0].get_text())
                        self.assertEqual(doc[0].get_pixmap().pixel(round(area.tl.x+5),round(area.tl.y+5)), (255,255,255))
                        self.assertEqual(doc[0].get_pixmap().pixel(10,10), (0,0,0))
                        for xref in range(1,doc.xref_length()):
                            if doc.xref_is_stream(xref):
                                self.assertNotEqual(hashlib.sha256(doc.xref_stream(xref)).hexdigest(), old_digest)
                finally:
                    e.end_edit()
                    if e.doc: e.doc.close()

    def test_encrypted_shared_image_and_project_keep_other_page_unchanged(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'scan.pdf'
            scan_fixture(path, encrypted=True, shared=True)
            e = Engine()
            try:
                e.run(dict(kind='open', path=str(path), password='test'))
                other = e.doc[1].get_pixmap().samples
                e.run(dict(kind='erase_image', index=0, revision=e.revision, rect=[55,65,125,110]))
                self.assertEqual(e.doc[1].get_pixmap().samples, other)
                for kind, ext in [('save','.pdf'),('save_project','.lpdf')]:
                    target = Path(folder)/('result'+ext)
                    e.run(dict(kind=kind, path=str(target), index=0))
                    with fitz.open(target) as doc:
                        self.assertTrue(doc.needs_pass)
                        self.assertTrue(doc.authenticate('test'))
                        self.assertEqual(doc[0].get_pixmap().pixel(70,80),(255,255,255))
                        self.assertEqual(doc[1].get_pixmap().samples,other)
            finally:
                e.end_edit()
                if e.doc: e.doc.close()

    def test_cropped_transparent_scan_and_distant_editable_text(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'crop.pdf'
            stream=io.BytesIO()
            Image.new('RGBA',(300,300),(0,0,0,180)).save(stream,format='PNG')
            with fitz.open() as doc:
                page=doc.new_page(width=300,height=300)
                page.insert_image(page.rect,stream=stream.getvalue())
                page.set_cropbox(fitz.Rect(20,20,280,280))
                page.set_rotation(90)
                doc.save(path)
            e=Engine()
            try:
                e.run(dict(kind='open',path=str(path)))
                spec=dict(x=150,y=170,width=100,height=50,text='Keep',size=12,color=(1,0,0))
                result=e.run(dict(kind='insert',index=0,spec=spec))
                obj=result['objects'][0]
                area=[40,40,90,90]
                e.run(dict(kind='erase_image',index=0,revision=e.revision,rect=area))
                self.assertEqual(e.doc[0].get_pixmap().pixel(60,60),(255,255,255))
                self.assertIn(obj['id'],e.objects)
                e.run(dict(kind='begin_edit',index=0,revision=e.revision,object_id=obj['id']))
                e.run(dict(kind='update_object',index=0,revision=e.revision,object_id=obj['id'],spec=dict(spec,text='Edited')))
                self.assertIn('Edited',e.doc[0].get_text())
            finally:
                e.end_edit()
                if e.doc: e.doc.close()

    def test_no_image_and_existing_redactions_fail_without_history(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'text.pdf'
            with fitz.open() as doc:
                doc.new_page().insert_text((50,80),'Keep text')
                doc.save(path)
            e = Engine()
            try:
                e.run(dict(kind='open',path=str(path)))
                before=e.doc[0].get_pixmap().samples
                with self.assertRaisesRegex(ValueError,'没有图片'):
                    e.run(dict(kind='erase_image',index=0,revision=e.revision,rect=[40,40,200,100]))
                self.assertEqual(e.doc[0].get_pixmap().samples,before)
                self.assertFalse(e.history)
                e.doc[0].add_redact_annot(fitz.Rect(40,40,200,100))
                with self.assertRaisesRegex(ValueError,'已有'):
                    e.run(dict(kind='erase_image',index=0,revision=e.revision,rect=[40,40,200,100]))
                self.assertFalse(e.history)
            finally:
                e.end_edit()
                if e.doc: e.doc.close()
