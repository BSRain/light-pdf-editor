"""Independent OCR rows, style matching and atomic multi-object conversion."""
import base64
from pathlib import Path
import tempfile
import unittest
import pymupdf as fitz
from pdf_core import add_text,windows_fonts
from pdf_worker import Engine
from ocr_core import snapshot


class OcrLineTests(unittest.TestCase):
    def test_matching_preserves_ink_position_size_and_color(self):
        from ocr_layout import match_line, ink_bounds
        font=windows_fonts().get('Arial')
        with fitz.open() as doc:
            p=doc.new_page(width=400,height=180)
            add_text(p,60,40,'Invoice 5000',24,(.75,.1,.15),font,300,65)
            pix=p.get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
            data=dict(image=base64.b64encode(pix.tobytes('png')).decode(),rect=[0,0,400,180],origin=[0,0],scale=3,width=pix.width,height=pix.height,fill_color=[1,1,1])
            line=dict(text='Invoice 5000',bbox=[50,35,300,80])
            spec=match_line(data,line,font,pix=pix)
            self.assertAlmostEqual(spec['size'],24,delta=1)
            self.assertAlmostEqual(spec['color'][0],.75,delta=.08)
            with fitz.open() as result:
                page=result.new_page(width=400,height=180);add_text(page,**spec)
                actual=page.get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
                a,_=ink_bounds(pix,[150,105,900,240],[255,255,255])
                b,_=ink_bounds(actual,[0,0,actual.width,actual.height],[255,255,255])
                for x,y in zip(a,b): self.assertAlmostEqual(x/3,y/3,delta=2)

    def test_real_recognition_matches_each_line_separately(self):
        from ocr_core import recognize
        font=windows_fonts().get('Arial')
        with fitz.open() as raster:
            p=raster.new_page(width=400,height=200)
            add_text(p,35,30,'RED TOTAL 5000',24,(.8,0,0),font,330,45)
            add_text(p,80,110,'Blue reference 12345',14,(0,.1,.8),font,280,35)
            pix=p.get_pixmap(matrix=fitz.Matrix(3,3),alpha=False)
            data=dict(image=base64.b64encode(pix.tobytes('png')).decode(),rect=[0,0,400,200],origin=[0,0],scale=3,width=pix.width,height=pix.height,fill_color=[1,1,1])
            result=recognize(data,'eng',fontfile=font)
            self.assertEqual(len(result['lines']),2)
            a,b=[line['spec'] for line in result['lines']]
            self.assertGreater(a['size'],b['size']+5)
            self.assertGreater(a['color'][0],.65);self.assertLess(a['color'][2],.15)
            self.assertGreater(b['color'][2],.65);self.assertLess(b['color'][0],.15)
            self.assertAlmostEqual(a['x'],35,delta=3);self.assertAlmostEqual(b['x'],80,delta=3)

    def test_multiple_lines_remain_independent_and_one_undo(self):
        from test_ocr import scan
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scan.pdf';scan(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                before=e.doc[0].get_pixmap().samples
                specs=[dict(x=55,y=y,width=280,height=28,text=text,size=16,color=color,fontfile=windows_fonts().get('Arial')) for y,text,color in [(65,'First 5000',[.8,0,0]),(110,'Second 12345',[0,0,.8])]]
                request=dict(kind='ocr_convert',index=0,revision=e.revision,rect=[40,50,370,175],specs=specs,fill_color=[1,1,1])
                preview=e.run(dict(request,kind='ocr_preview'))
                self.assertFalse(e.objects);self.assertFalse(e.history)
                e.run(request)
                expected=fitz.Pixmap(base64.b64decode(preview['image'])).samples
                actual=e.doc[0].get_pixmap(matrix=fitz.Matrix(2,2),clip=fitz.Rect(request['rect']),alpha=False).samples
                self.assertEqual(expected,actual)
                self.assertEqual(len(e.objects),2);self.assertEqual(len(e.history),1)
                objects=list(e.objects.values());other=objects[1].copy()
                e.run(dict(kind='begin_edit',index=0,revision=e.revision,object_id=objects[0]['id']))
                changed=dict(specs[0],text='Changed 6000')
                e.run(dict(kind='update_object',index=0,revision=e.revision,object_id=objects[0]['id'],spec=changed))
                self.assertEqual(e.objects[other['id']],other)
                e.run(dict(kind='undo'));e.run(dict(kind='undo'))
                self.assertEqual(e.doc[0].get_pixmap().samples,before);self.assertFalse(e.objects)
                e.run(dict(kind='redo'));self.assertEqual(len(e.objects),2)
                project=Path(folder)/'rows.lpdf';e.run(dict(kind='save_project',path=str(project)))
                e.run(dict(kind='open',path=str(project)));self.assertEqual(len(e.objects),2)
            finally:e.end_edit();e.doc.close()

    def test_later_row_failure_rolls_back_all_rows(self):
        from test_ocr import scan
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'scan.pdf';scan(path)
            e=Engine();e.run(dict(kind='open',path=str(path)))
            try:
                before=e.doc[0].get_pixmap().samples
                specs=[dict(x=50,y=60,width=300,height=30,text='Good',size=12,color=[0,0,0]),dict(x=50,y=110,width=300,height=30,text='Bad too large',size=200,color=[0,0,0])]
                with self.assertRaisesRegex(ValueError,'放不下|宽度小于'):
                    e.run(dict(kind='ocr_convert',index=0,revision=e.revision,rect=[40,50,370,175],specs=specs,fill_color=[1,1,1]))
                self.assertEqual(before,e.doc[0].get_pixmap().samples);self.assertFalse(e.objects);self.assertFalse(e.history);self.assertEqual(e.object_serial,0)
            finally:e.doc.close()
