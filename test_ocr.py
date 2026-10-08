"""OCR conversion: real engine recognition, atomic editing and coordinate checks."""
from pathlib import Path
import tempfile
import unittest
import pymupdf as fitz
from pdf_core import windows_fonts, add_text
from pdf_worker import Engine


def scan(path, rotation=0, crop=False, encrypted=False):
    with fitz.open() as raster:
        page = raster.new_page(width=420, height=260)
        add_text(page, 55, 65, '金额 5000 元\nInvoice 12345', 20, (0,0,0), windows_fonts().get('微软雅黑'), 300, 100)
        image = page.get_pixmap(matrix=fitz.Matrix(3,3)).tobytes('png')
    with fitz.open() as doc:
        p=doc.new_page(width=420,height=260)
        p.insert_image(p.rect, stream=image)
        if crop: p.set_cropbox(fitz.Rect(20,20,400,240))
        p.set_rotation(rotation)
        doc.save(path, **(dict(encryption=fitz.PDF_ENCRYPT_AES_256,owner_pw='owner',user_pw='test') if encrypted else {}))


class OcrTests(unittest.TestCase):
    def test_real_chinese_english_recognition_and_positions(self):
        from ocr_core import recognize
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scan.pdf';scan(path)
            e=Engine()
            try:
                e.run(dict(kind='open',path=str(path)))
                before=e.doc[0].get_pixmap().samples
                snapshot=e.run(dict(kind='ocr_snapshot',index=0,revision=e.revision,rect=[40,50,370,175]))
                result=recognize(snapshot, 'chi_sim+eng')
                text=result['text'].replace(' ','')
                self.assertIn('5000',text);self.assertIn('金额',text);self.assertIn('Invoice12345',text)
                for line in result['lines']:
                    self.assertTrue(fitz.Rect(snapshot['rect']).contains(fitz.Rect(line['bbox'])))
                self.assertEqual(before,e.doc[0].get_pixmap().samples)
                self.assertFalse(e.history)
            finally: e.doc.close()

    def test_conversion_is_one_undoable_edit_and_project_reopens(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation),tempfile.TemporaryDirectory() as folder:
                path=Path(folder)/'scan.pdf';scan(path,rotation,crop=True,encrypted=True)
                e=Engine()
                try:
                    e.run(dict(kind='open',path=str(path),password='test'))
                    before=e.doc[0].get_pixmap().samples
                    area=fitz.Rect(20,30,355,160)*e.doc[0].rotation_matrix
                    snapshot=e.run(dict(kind='ocr_snapshot',index=0,revision=e.revision,rect=list(area)))
                    spec=dict(x=area.x0,y=area.y0,width=area.width,height=area.height,text='Changed 6000',size=12,color=[0,0,0],fontfile=windows_fonts().get('Arial'))
                    e.run(dict(kind='ocr_convert',index=0,revision=e.revision,rect=list(area),spec=spec,fill_color=[1,1,1]))
                    self.assertEqual(len(e.history),1);self.assertEqual(len(e.objects),1)
                    self.assertIn('Changed 6000',e.doc[0].get_text().replace('\xa0',' '))
                    converted=e.doc[0].get_pixmap().samples
                    self.assertNotEqual(before,converted)
                    e.run(dict(kind='undo'));self.assertEqual(before,e.doc[0].get_pixmap().samples);self.assertFalse(e.objects)
                    e.run(dict(kind='redo'));self.assertEqual(converted,e.doc[0].get_pixmap().samples)
                    project=Path(folder)/'edit.lpdf';e.run(dict(kind='save_project',path=str(project)))
                    e.run(dict(kind='open',path=str(project),password='test'))
                    obj=next(iter(e.objects.values()))
                    e.run(dict(kind='begin_edit',index=0,revision=e.revision,object_id=obj['id']))
                    spec['text']='Edited 7000'
                    e.run(dict(kind='update_object',index=0,revision=e.revision,object_id=obj['id'],spec=spec))
                    self.assertIn('Edited 7000',e.doc[0].get_text().replace('\xa0',' '));self.assertNotIn('6000',e.doc[0].get_text().replace('\xa0',' '))
                    e.run(dict(kind='delete',index=0,rect=list(area)))
                    self.assertNotIn('7000',e.doc[0].get_text().replace('\xa0',' '))
                    # Removing the replacement cannot bring the original raster words back.
                    pixels=e.doc[0].get_pixmap(clip=area+(1,1,-1,-1), alpha=False).samples
                    self.assertEqual(set(pixels),{255})
                finally: e.end_edit();e.doc.close()

    def test_preview_matches_commit_and_does_not_edit(self):
        import base64
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scan.pdf';scan(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                before=e.doc[0].get_pixmap().samples
                req=dict(kind='ocr_preview',index=0,revision=e.revision,rect=[40,50,370,175],fill_color=[.95,.9,.8],
                    spec=dict(x=55,y=65,width=315,height=110,text='Preview 9000',size=16,color=[0,0,0],fontfile=windows_fonts().get('Arial')))
                result=e.run(req)
                self.assertEqual(before,e.doc[0].get_pixmap().samples);self.assertFalse(e.history)
                req['kind']='ocr_convert';e.run(req)
                actual=e.doc[0].get_pixmap(matrix=fitz.Matrix(2,2),clip=fitz.Rect(req['rect']),alpha=False)
                self.assertEqual(fitz.Pixmap(base64.b64decode(result['image'])).samples,actual.samples)
            finally: e.doc.close()

    def test_missing_models_pixel_budget_and_source_validation(self):
        from ocr_core import recognize,snapshot,MAX_PIXELS
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scan.pdf';scan(path)
            with fitz.open(path) as doc:
                data=snapshot(doc[0],[40,50,370,175])
                with self.assertRaisesRegex(ValueError,'语言包缺失'): recognize(data,tessdata=folder)
                with self.assertRaises(ValueError): snapshot(doc[0],[-1,0,100,100])
            with fitz.open() as doc:
                page=doc.new_page(width=4000,height=4000)
                image=fitz.Pixmap(fitz.csRGB,fitz.IRect(0,0,10,10),False);image.clear_with(255)
                page.insert_image(page.rect,pixmap=image)
                data=snapshot(page,list(page.rect))
                self.assertLessEqual(data['width']*data['height'],MAX_PIXELS)
                self.assertLess(data['dpi'],300)
                self.assertTrue(data['background_warning'])
                self.assertEqual(data['fill_color'],[1,1,1])
            with fitz.open() as doc:
                page=doc.new_page()
                with self.assertRaisesRegex(ValueError,'没有图片'): snapshot(page,[10,10,100,100])

    def test_bad_layout_and_stale_conversion_preserve_document(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scan.pdf';scan(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                before=e.doc[0].get_pixmap().samples
                req=dict(kind='ocr_convert',index=0,revision=e.revision,rect=[40,50,370,175],fill_color=[1,1,1],spec=dict(x=40,y=50,width=330,height=125,text='Too large',size=200,color=[0,0,0]))
                with self.assertRaisesRegex(ValueError,'放不下|宽度小于'): e.run(req)
                self.assertEqual(before,e.doc[0].get_pixmap().samples);self.assertFalse(e.history);self.assertFalse(e.objects)
                req['revision']-=1
                with self.assertRaisesRegex(ValueError,'页面已变化'): e.run(req)
                self.assertEqual(before,e.doc[0].get_pixmap().samples)
            finally: e.doc.close()

if __name__=='__main__': unittest.main()
