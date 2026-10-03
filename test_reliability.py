"""Fault-injection tests for worker supervision and safe rectangle deletion."""
import tempfile,time,sys
from pathlib import Path
import unittest
from unittest.mock import patch
from PySide6.QtWidgets import QApplication,QMessageBox
from PySide6.QtCore import QProcess
from pdf_editor import PdfClient
import test_editor as helpers

class SupervisionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.app=QApplication.instance() or QApplication([])
    def wait(self,predicate,seconds=3):
        end=time.monotonic()+seconds
        while time.monotonic()<end:
            self.app.processEvents()
            if predicate(): return
            time.sleep(.005)
        self.fail('Expected worker state was not reached')
    def test_hung_request_becomes_recoverable_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'hang.py';script.write_text('import sys,time\nfor line in sys.stdin: time.sleep(30)\n')
            client=PdfClient(worker_command=[sys.executable,'-u',str(script)],timeout_ms=100)
            errors=[];client.failed.connect(errors.append)
            try:
                client.command('page',epoch=1,index=0)
                self.wait(lambda: client.dead)
                self.wait(lambda: client.process.state()==QProcess.ProcessState.NotRunning)
                self.assertEqual(len(errors),1)
                self.assertIn('超时',errors[0])
                self.assertFalse(client.commands)
            finally: client.close()
    def test_oversize_unterminated_frame_kills_worker_and_clears_buffer(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'flood.py';script.write_text('import sys,time\nfor line in sys.stdin:\n sys.stdout.write("x"*8192);sys.stdout.flush();time.sleep(30)\n')
            client=PdfClient(worker_command=[sys.executable,'-u',str(script)],timeout_ms=2000)
            client.MAX_FRAME_BYTES=1024
            try:
                client.command('page',epoch=1,index=0)
                self.wait(lambda: client.dead)
                self.assertLessEqual(len(client.buffer),1024)
                self.wait(lambda: client.process.state()==QProcess.ProcessState.NotRunning)
            finally: client.close()
    def test_diagnostic_log_has_stderr_but_no_request_secrets(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict('os.environ',LOCALAPPDATA=directory):
            client=PdfClient()
            try:
                client.active=dict(kind='open',id=42,password='PASSWORD-SECRET',spec=dict(text='DOCUMENT-SECRET'))
                client.stderr='synthetic traceback detail'
                client.failure('Synthetic failure')
                logs=list(Path(directory).rglob('worker-*.log'))
                self.assertEqual(len(logs),1)
                contents=logs[0].read_text(encoding='utf-8')
                self.assertIn('synthetic traceback detail',contents)
                self.assertNotIn('PASSWORD-SECRET',contents)
                self.assertNotIn('DOCUMENT-SECRET',contents)
            finally: client.close()

    def test_fragmented_responses_and_idle_do_not_timeout(self):
        with tempfile.TemporaryDirectory() as directory:
            script=Path(directory)/'echo.py'
            script.write_text('import sys,json,time\nfor line in sys.stdin:\n r=json.loads(line);s=json.dumps(dict(id=r["id"],data=dict(ok=True)))+"\\n"\n sys.stdout.write(s[:3]);sys.stdout.flush();time.sleep(.02);sys.stdout.write(s[3:]);sys.stdout.flush()\n')
            client=PdfClient(worker_command=[sys.executable,'-u',str(script)],timeout_ms=250)
            replies=[];client.result.connect(replies.append)
            try:
                client.command('page');client.command('page')
                self.wait(lambda: len(replies)==2)
                self.assertFalse(client.watchdog.isActive())
                from PySide6.QtTest import QTest
                QTest.qWait(350)
                self.assertFalse(client.dead)
                self.assertTrue(all(r['data']['ok'] for r in replies))
            finally:client.close()

    def test_wrong_id_and_noise_are_recoverable_protocol_failures(self):
        for output in ('noise\n','{"id":999,"data":{}}\n','{"id":1,"data":[],"error":"bad"}\n'):
            with self.subTest(output=output),tempfile.TemporaryDirectory() as directory:
                script=Path(directory)/'invalid.py'
                script.write_text('import sys,time\nfor line in sys.stdin:\n sys.stdout.write('+repr(output)+');sys.stdout.flush();time.sleep(30)\n')
                client=PdfClient(worker_command=[sys.executable,'-u',str(script)],timeout_ms=2000)
                errors=[];client.failed.connect(errors.append)
                try:
                    client.command('page')
                    self.wait(lambda: client.dead)
                    self.assertEqual(len(errors),1)
                    self.assertNotIn('超时',errors[0])
                    self.wait(lambda: client.process.state()==QProcess.ProcessState.NotRunning)
                finally:client.close()

    def test_unwritable_log_does_not_prevent_failure_recovery(self):
        client=PdfClient();errors=[];client.failed.connect(errors.append)
        try:
            with patch('worker_diagnostics.Path.write_text',side_effect=OSError('read only')):
                client.failure('failure')
            self.assertTrue(client.dead)
            self.assertEqual(len(errors),1)
            self.assertIn('无法写入',errors[0])
        finally:client.close()

class ManualRestartTests(unittest.TestCase):
    setUpClass=classmethod(helpers.QtTests.setUpClass.__func__)
    setUp=helpers.QtTests.setUp
    tearDown=helpers.QtTests.tearDown
    wait=helpers.QtTests.wait
    def test_busy_live_worker_can_be_restarted_or_cancelled(self):
        e=self.editor;old=e.client
        e.set_busy(True)
        self.assertTrue(e.restart_action.isEnabled())
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.No): e.restart_worker()
        self.assertIs(e.client,old)
        with patch.object(QMessageBox,'question',return_value=QMessageBox.StandardButton.Yes): e.restart_worker()
        self.wait(lambda: e.client is not old and not e.busy)
        self.assertEqual(e.path,self.path)

