"""Native Qt original-text and rotation workflows."""
import time
import unittest
from PySide6.QtCore import QTimer,QPointF
import test_editor as helpers


class NativeUiTests(unittest.TestCase):
    setUpClass=classmethod(helpers.QtTests.setUpClass.__func__)
    setUp=helpers.QtTests.setUp
    tearDown=helpers.QtTests.tearDown
    wait=helpers.QtTests.wait

    def test_edit_original_preview_confirm_and_undo(self):
        e=self.editor;span=e.spans[0];before=span['text'];stage=[];errors=[]
        deadline=time.monotonic()+20
        def drive():
            d=e.native_dialog
            if d is None:return
            if time.monotonic()>deadline:
                errors.append(d.status.text());d.reject();return
            if not stage:
                d.text.setText(d.text.text()+'1');stage.append(True)
            elif d.confirm.isEnabled():
                d.grab().save('tmp/original-text-dialog.png');d.confirm.click();stage.append(True)
        timer=QTimer();timer.setInterval(30);timer.timeout.connect(drive);timer.start()
        try:
            box=span['bbox'];e.edit_original_at(QPointF(box[0]+3,(box[1]+box[3])/2))
            self.wait(lambda:(len(stage)==2 or errors) and not e.busy and e.native_dialog is None,25)
            self.assertEqual(errors,[])
            self.assertTrue(any(s['text']==before+'1' for s in e.spans))
            e.undo();self.wait(lambda:not e.busy)
            self.assertTrue(any(s['text']==before for s in e.spans))
        finally:timer.stop()

    def test_rotation_actions_and_draft_guard(self):
        e=self.editor;size=e.page_rect.size()
        e.rotate_page(90);self.wait(lambda:not e.busy)
        self.assertEqual(e.page_rect.width(),size.height());self.assertEqual(e.page_rect.height(),size.width())
        e.undo();self.wait(lambda:not e.busy);self.assertEqual(e.page_rect.size(),size)
        e.text_input.setPlainText('Draft');e.place(QPointF(250,350));self.wait(lambda:e.draft and e.draft.valid)
        revision=e.revision;e.rotate_page(-90)
        self.assertEqual(e.revision,revision);self.assertIsNotNone(e.draft)
