"""Startup failures must be understandable without Qt or a console."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import app_entry


class StartupTests(unittest.TestCase):
    def test_incomplete_bundle_lists_missing_components(self):
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            with self.assertRaisesRegex(app_entry.IncompleteBundle,'PdfWorker.exe'):
                app_entry.validate_bundle(root)
            for name in ('PdfWorker.exe','_internal/PySide6/Qt6Core.dll','_internal/PySide6/plugins/platforms/qwindows.dll'):
                path=root/name; path.parent.mkdir(parents=True,exist_ok=True); path.write_bytes(b'test')
            app_entry.validate_bundle(root)
            (root/'_internal/PySide6/plugins/platforms/qwindows.dll').unlink()
            with self.assertRaisesRegex(app_entry.IncompleteBundle,'qwindows.dll'):
                app_entry.validate_bundle(root)

    def test_headless_failure_writes_report_and_log_without_dialog(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('os.environ',{'LOCALAPPDATA':folder}):
            app_entry.report_failure(RuntimeError('missing dependency'), 'Trace details', Path(folder)/'report')
            report=json.loads((Path(folder)/'report/smoke-report.json').read_text(encoding='utf-8'))
            self.assertFalse(report['ok'])
            self.assertTrue(report['startup_failure'])
            self.assertIn('missing dependency',report['error'])
            logs=list((Path(folder)/'LightPDFEditor/logs').glob('*.log'))
            self.assertEqual(len(logs),1)
            self.assertEqual(logs[0].read_text(encoding='utf-8'),'Trace details')

    def test_failure_logging_tolerates_unwritable_directories(self):
        with patch.object(Path,'mkdir',side_effect=PermissionError):
            self.assertIsNone(app_entry.write_startup_log('diagnostic'))

    def test_launcher_catches_import_error_before_qt(self):
        with tempfile.TemporaryDirectory() as folder, patch.dict('sys.modules',{'pdf_editor':None}), patch('sys.argv',['app_entry.py','--smoke-test',folder]), patch('app_entry.write_startup_log',return_value=None):
            self.assertEqual(app_entry.main(),1)
            self.assertTrue(json.loads((Path(folder)/'smoke-report.json').read_text(encoding='utf-8'))['startup_failure'])
