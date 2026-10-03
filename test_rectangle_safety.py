"""Rectangle deletion must roll back unexpected changes outside its selection."""
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch
import pymupdf as fitz
from pdf_worker import Engine

class RectangleVerificationTests(unittest.TestCase):
    def test_unexpected_survivor_loss_rolls_back_whole_transaction(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'source.pdf'
            with fitz.open() as doc:
                p=doc.new_page();p.insert_text((30,50),'DELETE');p.insert_text((30,150),'KEEP');doc.save(path)
            e=Engine();original=e.run(dict(kind='open',path=str(path)))
            real=fitz.Page.apply_redactions
            def corrupt(page,**kwargs):
                page.add_redact_annot(fitz.Rect(20,130,150,160),fill=False)
                return real(page,**kwargs)
            try:
                with patch.object(fitz.Page,'apply_redactions',corrupt):
                    with self.assertRaises(ValueError): e.run(dict(kind='delete',index=0,rect=[20,30,150,60]))
                after=e.metadata(0)
                self.assertEqual(after['characters'],original['characters'])
                self.assertEqual(after['thumbnail'],original['thumbnail'])
                self.assertFalse(e.history)
            finally: e.end_edit();e.doc.close()
