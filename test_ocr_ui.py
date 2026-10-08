"""Native OCR dialog, worker isolation and confirmation checks."""
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
from PySide6.QtCore import QTimer,QRectF
from PySide6.QtWidgets import QApplication,QMessageBox
from pdf_editor import Editor
from test_ocr import scan


class OcrUiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])

    def wait(self, predicate, seconds=25):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.app.processEvents()
            if predicate(): return
            time.sleep(.01)
        self.fail('Timed out: '+repr(self.errors))

    def setUp(self):
        self.folder=tempfile.TemporaryDirectory();self.path=Path(self.folder.name)/'scan.pdf';scan(self.path)
        self.errors=[]
        self.warning=patch.object(QMessageBox,'warning',side_effect=lambda *args:self.errors.append(args[-1]));self.warning.start()
        self.e=Editor();self.e.show();self.e.open_pdf(str(self.path));self.wait(lambda:self.e.path is not None and not self.e.busy)

    def tearDown(self):
        if self.e.ocr_dialog: self.e.ocr_dialog.reject()
        self.e.client.close();self.e.busy=False;self.e.dirty=False;self.e.cancel(local=True);self.e.close()
        self.warning.stop();self.folder.cleanup()

    def run_dialog(self, action):
        finished=[];end=time.monotonic()+25
        def drive():
            dialog=self.e.ocr_dialog
            if dialog is None: return
            try:
                if time.monotonic()>end: raise AssertionError('OCR dialog timeout: '+dialog.status.text())
                if action(dialog): finished.append(True)
            except Exception as exc:
                self.errors.append(str(exc));dialog.reject();finished.append(True)
        timer=QTimer();timer.setInterval(30);timer.timeout.connect(drive);timer.start()
        try:
            self.e.start_ocr(QRectF(40,50,330,125))
            self.wait(lambda:finished and self.e.ocr_dialog is None and not self.e.busy,35)
        finally:timer.stop()
        self.assertEqual(self.errors,[])

    def test_recognize_correct_preview_confirm_editable_and_undo(self):
        stage=[]
        def drive(d):
            if not stage and not d.recognizing and '5000' in d.text.toPlainText():
                d.grouping.setCurrentIndex(1)
                d.text.setPlainText('金额 6000 元\nInvoice 12345');d.size.setValue(18);stage.append('corrected')
                self.assertFalse(d.confirm.isEnabled())
            elif stage and d.confirm.isEnabled():
                d.grab().save(str(Path('tmp')/'ocr-dialog.png'))
                d.confirm.click();return True
        self.run_dialog(drive)
        self.assertTrue(self.e.dirty);self.assertEqual(len(self.e.objects),1)
        self.assertIn('6000',self.e.objects[0]['spec']['text'])
        self.e.undo();self.wait(lambda:not self.e.busy)
        self.assertFalse(self.e.objects);self.assertFalse(self.e.characters)
        self.e.redo();self.wait(lambda:not self.e.busy);self.assertEqual(len(self.e.objects),1)

    def test_line_correction_does_not_change_other_line(self):
        stage=[]
        def drive(d):
            if not stage and not d.recognizing and len(d.line_specs)==2:
                self.assertEqual(d.layout_kind,0)
                other=dict(d.line_specs[1]);stage.append(other)
                d.text.setPlainText('金额 6000 元')
                self.assertEqual(d.line_specs[1],other)
            elif stage and d.confirm.isEnabled():
                d.grab().save('tmp/ocr-lines-dialog.png')
                d.confirm.click();return True
        self.run_dialog(drive)
        self.assertEqual(len(self.e.objects),2)
        self.assertIn('6000',self.e.objects[0]['spec']['text'])
        self.assertEqual(self.e.objects[1]['spec'],stage[0])
        self.e.undo();self.wait(lambda:not self.e.busy)
        self.assertFalse(self.e.objects)

    def test_unavailable_font_invalidates_approved_preview(self):
        stage=[]
        def drive(d):
            if not stage and d.confirm.isEnabled():
                d.font.addItem('Missing font',str(Path(self.folder.name)/'missing.ttf'))
                d.font.setCurrentIndex(d.font.count()-1)
                self.assertFalse(d.confirm.isEnabled())
                self.assertIn('字体',d.status.text())
                stage.append(True);d.reject();return True
        self.run_dialog(drive)
        self.assertFalse(self.e.dirty)

    def test_ocr_timeout_does_not_stop_pdf_worker(self):
        import sys
        from pdf_client import PdfClient
        original=self.e.client
        def client(parent,**kwargs):
            return PdfClient(parent,worker_command=[sys.executable,'-u','-c','import time;time.sleep(30)'],timeout_ms=100)
        def drive(d):
            if '超时' in d.status.text():
                self.assertFalse(d.confirm.isEnabled());d.reject();return True
        with patch('ocr_dialog.PdfClient',side_effect=client): self.run_dialog(drive)
        self.assertIs(self.e.client,original);self.assertFalse(original.dead);self.assertFalse(self.e.dirty)

    def test_cancel_recognition_keeps_unsaved_session(self):
        self.e.epoch+=1;self.e.set_busy(True)
        self.e.client.command('insert',epoch=self.e.epoch,index=0,spec=dict(x=20,y=195,width=350,height=50,text='Unsaved',size=12,color=[0,0,0]))
        self.wait(lambda:not self.e.busy)
        client=self.e.client;objects=self.e.objects.copy()
        def drive(d):
            if d.client is not None:
                d.stop_recognition();self.assertFalse(d.confirm.isEnabled());d.reject();return True
        self.run_dialog(drive)
        self.assertIs(self.e.client,client);self.assertFalse(client.dead);self.assertTrue(self.e.dirty);self.assertEqual(self.e.objects,objects)

if __name__=='__main__':unittest.main()
