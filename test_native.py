"""Original text replacement and page rotation regression tests."""
from pathlib import Path
import tempfile
import unittest
import pymupdf as fitz
from pdf_core import add_text,windows_fonts,text_spans
from pdf_worker import Engine


class NativeTests(unittest.TestCase):
    def test_repeat_edit_empty_delete_and_render_rejection(self):
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.pdf'
            with fitz.open() as d:
                d.new_page(width=400,height=250).insert_text((40,60),'12345',fontsize=18)
                d.save(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                original=e.doc[0].get_pixmap().samples
                with patch('original_text.verify_original_rendering',side_effect=ValueError('Unsupported rendering')):
                    with self.assertRaises(ValueError):
                        e.run(dict(kind='native_info',index=0,revision=e.revision,point=[45,55]))
                self.assertEqual(original,e.doc[0].get_pixmap().samples);self.assertFalse(e.history)
                for text in ('123456','1234',''):
                    info=e.run(dict(kind='native_info',index=0,revision=e.revision,point=[45,55]))
                    request=dict(index=0,revision=e.revision,target=info['target'],text=text)
                    e.run(dict(kind='native_preview',**request))
                    e.run(dict(kind='native_replace',**request))
                    self.assertEqual(e.doc[0].get_text().strip(),text)
                for _ in range(3):e.run(dict(kind='undo'))
                self.assertEqual(original,e.doc[0].get_pixmap().samples)
            finally:e.doc.close()

    def test_rotate_current_page_export_undo_redo_and_invalid_delta(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.pdf'
            with fitz.open() as d:
                for _ in range(2):d.new_page(width=400,height=250).insert_text((40,60),'12345')
                d.save(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                for delta in (0,45,True,360):
                    with self.assertRaises(ValueError):e.run(dict(kind='rotate',index=0,revision=e.revision,delta=delta))
                self.assertFalse(e.history)
                e.run(dict(kind='rotate',index=0,revision=e.revision,delta=90))
                self.assertEqual([p.rotation for p in e.doc],[90,0])
                e.run(dict(kind='undo'));self.assertEqual(e.doc[0].rotation,0)
                e.run(dict(kind='redo'));self.assertEqual(e.doc[0].rotation,90)
                output=Path(folder)/'rotated.pdf';e.run(dict(kind='save',path=str(output)))
                with fitz.open(output) as d:self.assertEqual([p.rotation for p in d],[90,0])
                with fitz.open(path) as d:self.assertEqual([p.rotation for p in d],[0,0])
            finally:e.doc.close()

    def test_original_digits_keep_font_color_baseline_and_undo(self):
        for font in (None,windows_fonts().get('Arial')):
            with self.subTest(font=font),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'source.pdf'
                with fitz.open() as doc:
                    p=doc.new_page(width=400,height=250)
                    if font: add_text(p,40,40,'12345',18,(.2,.3,.7),font,200,50)
                    else: p.insert_text((40,60),'12345',fontname='hebo',fontsize=18,color=(.2,.3,.7))
                    p.insert_text((40,170),'KEEP');doc.save(path)
                e=Engine();e.run(dict(kind='open',path=str(path)))
                try:
                    before=e.doc[0].get_pixmap().samples
                    original=text_spans(e.doc[0])[0]
                    info=e.run(dict(kind='native_info',index=0,revision=e.revision,point=[45,55]))
                    request=dict(kind='native_replace',index=0,revision=e.revision,target=info['target'],text='123459')
                    e.run(request)
                    span=next(s for s in text_spans(e.doc[0]) if '123459' in s['text'])
                    self.assertEqual(span['font'],original['font']);self.assertEqual(span['color'],original['color'])
                    self.assertAlmostEqual(span['size'],18,places=3);self.assertAlmostEqual(span['baseline'],original['baseline'],places=3)
                    self.assertIn('KEEP',e.doc[0].get_text())
                    e.run(dict(kind='undo'));self.assertEqual(before,e.doc[0].get_pixmap().samples)
                finally:e.doc.close()

    def test_rotated_cropped_encrypted_text_and_preview(self):
        from original_text import prepare,preview
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'source.pdf'
                with fitz.open() as d:
                    p=d.new_page(width=400,height=250);p.insert_text((50,70),'12345',fontsize=18)
                    p.draw_rect(fitz.Rect(30,30,350,220),color=(0,0,0))
                    p.set_cropbox(fitz.Rect(20,20,380,240));p.set_rotation(rotation)
                    d.save(path,encryption=fitz.PDF_ENCRYPT_AES_256,user_pw='test',owner_pw='owner')
                e=Engine();e.run(dict(kind='open',path=str(path),password='test'))
                try:
                    point=fitz.Point(35,45)*e.doc[0].rotation_matrix
                    info=e.run(dict(kind='native_info',index=0,revision=e.revision,point=list(point)))
                    before=e.doc[0].get_pixmap().samples
                    request=dict(index=0,revision=e.revision,target=info['target'],text='1234')
                    image=e.run(dict(kind='native_preview',**request))['image']
                    self.assertEqual(before,e.doc[0].get_pixmap().samples)
                    e.run(dict(kind='native_replace',**request))
                    self.assertIn('1234',e.doc[0].get_text());self.assertNotIn('12345',e.doc[0].get_text())
                    output=Path(folder)/'saved.pdf';e.run(dict(kind='save',path=str(output)))
                    with fitz.open(output) as d:
                        self.assertTrue(d.needs_pass);self.assertTrue(d.authenticate('test'));self.assertEqual(d[0].rotation,rotation)
                    e.run(dict(kind='undo'));self.assertEqual(before,e.doc[0].get_pixmap().samples)
                finally:e.doc.close()

    def test_collision_missing_glyph_and_stale_request_do_not_modify(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.pdf'
            with fitz.open() as d:
                p=d.new_page(width=400,height=250);p.insert_text((40,60),'12345',fontsize=18);p.insert_text((98,60),'KEEP',fontsize=18,fontname='tiro')
                d.save(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                info=e.run(dict(kind='native_info',index=0,revision=e.revision,point=[45,55]))
                before=e.doc[0].get_pixmap().samples
                for text,revision in [('1234567890',e.revision),('中文',e.revision),('1234',e.revision-1)]:
                    with self.assertRaises(ValueError):
                        e.run(dict(kind='native_replace',index=0,revision=revision,target=info['target'],text=text))
                    self.assertEqual(before,e.doc[0].get_pixmap().samples);self.assertFalse(e.history)
            finally:e.doc.close()

    def test_rotation_preserves_objects_project_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'source.pdf'
            with fitz.open() as doc:
                doc.new_page(width=400,height=250).insert_text((40,50),'Source');doc.save(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                e.run(dict(kind='insert',index=0,spec=dict(x=50,y=80,width=200,height=50,text='Editable',size=14,color=[0,0,0])))
                before=e.doc[0].get_pixmap().samples
                for _ in range(4):e.run(dict(kind='rotate',index=0,revision=e.revision,delta=90))
                self.assertEqual(before,e.doc[0].get_pixmap().samples);self.assertEqual(len(e.objects),1)
                e.run(dict(kind='rotate',index=0,revision=e.revision,delta=-90))
                project=Path(folder)/'rotated.lpdf';e.run(dict(kind='save_project',path=str(project)))
                e.run(dict(kind='open',path=str(project)))
                self.assertEqual(e.doc[0].rotation,270);self.assertEqual(len(e.objects),1)
                e.run(dict(kind='rotate',index=0,revision=e.revision,delta=90))
                obj=next(iter(e.objects.values()))
                e.run(dict(kind='begin_edit',index=0,revision=e.revision,object_id=obj['id']))
                self.assertEqual(e.edit_id,obj['id'])
            finally:e.end_edit();e.doc.close()
