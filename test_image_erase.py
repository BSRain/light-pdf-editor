"""Real raster removal, page isolation, encrypted export and undo."""
import hashlib
import io
from pathlib import Path
import tempfile
import unittest
from PIL import Image, ImageDraw
import pymupdf as fitz
from pdf_worker import Engine
from pdf_core import sample_background, erase_image_region


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


class BackgroundFillTests(unittest.TestCase):
    def test_auto_background_rotations_pixel_erasure_and_color_export(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation), fitz.open() as doc:
                im=Image.new('RGB',(300,300),(232,219,170))
                ImageDraw.Draw(im).rectangle((70,80,120,100),fill=(0,0,0))
                stream=io.BytesIO(); im.save(stream,format='PNG')
                page=doc.new_page(width=300,height=300)
                page.insert_image(page.rect,stream=stream.getvalue())
                page.set_rotation(rotation)
                area=fitz.Rect(60,70,130,110)*page.rotation_matrix
                color=sample_background(page,list(area))
                self.assertEqual([round(v*255) for v in color],[232,219,170])
                erase_image_region(page,list(area),color)
                with fitz.open(stream=doc.tobytes(garbage=2),filetype='pdf') as saved:
                    pix=saved[0].get_pixmap()
                    pt=area.tl+fitz.Point(15,15)
                    self.assertTrue(all(abs(a-b)<=1 for a,b in zip(pix.pixel(int(pt.x),int(pt.y)),(232,219,170))))
                    # Extracting the new raster cannot recover the removed black text.
                    for info in saved[0].get_images():
                        image=fitz.Pixmap(saved,info[0])
                        self.assertNotEqual(image.pixel(90,90),(0,0,0))

    def test_page_point_sampling_and_invalid_fill(self):
        with fitz.open() as doc:
            p=doc.new_page(width=100,height=100)
            p.draw_rect(p.rect,color=None,fill=(.2,.4,.6))
            color=sample_background(p,point=[50,50])
            self.assertTrue(all(abs(a-b)<.01 for a,b in zip(color,(.2,.4,.6))))
            with self.assertRaises(ValueError):
                erase_image_region(p,[10,10,20,20],[-1,1,1])
            with self.assertRaises(ValueError):
                sample_background(p,point=[-1,50])
