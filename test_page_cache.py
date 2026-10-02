"""Cache correctness across state transitions and exact character geometry."""
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import pymupdf as fitz
import pdf_worker
from pdf_core import text_characters
from pdf_worker import Engine
import test_sessions as sessions


class PageCacheTests(unittest.TestCase):
    setUp = sessions.SessionTests.setUp
    tearDown = sessions.SessionTests.tearDown
    add = sessions.SessionTests.add
    begin = sessions.SessionTests.begin
    update = sessions.SessionTests.update

    def test_hits_are_equal_and_return_values_are_isolated(self):
        e = self.engine
        original = e.metadata(0)
        with patch('pdf_worker.text_characters', side_effect=AssertionError('cache miss')):
            hit = e.metadata(0)
        self.assertEqual(json.dumps(original, sort_keys=True), json.dumps(hit, sort_keys=True))
        hit['characters'][0]['text'] = 'BAD'
        hit['spans'].clear()
        self.assertEqual(e.metadata(0), original)

    def test_byte_budget_lru_and_oversize_bypass(self):
        e = self.engine
        e.PAGE_CACHE_COUNT = 1
        e.clear_page_cache()
        e.metadata(0); e.metadata(1)
        self.assertEqual(list(e.page_cache), [1])
        self.assertEqual(e.page_cache_bytes, sum(map(len,e.page_cache.values())))
        e.PAGE_CACHE_COUNT = 4
        e.clear_page_cache()
        e.metadata(0); e.metadata(1)
        costs = {key: len(value) for key,value in e.page_cache.items()}
        e.PAGE_CACHE_LIMIT = max(costs.values())
        e.clear_page_cache()
        e.metadata(0); e.metadata(1)
        self.assertEqual(list(e.page_cache), [1])
        self.assertLessEqual(e.page_cache_bytes, e.PAGE_CACHE_LIMIT)
        e.PAGE_CACHE_LIMIT = e.page_cache_bytes
        e.clear_page_cache()
        e.metadata(1); e.metadata(0)
        self.assertLessEqual(e.page_cache_bytes, e.PAGE_CACHE_LIMIT)
        e.PAGE_CACHE_LIMIT = 1
        e.clear_page_cache()
        e.metadata(0)
        self.assertEqual(e.page_cache_bytes, 0)
        self.assertFalse(e.page_cache)

    def test_insert_delete_undo_redo_refresh_content(self):
        e = self.engine
        original = e.metadata(0)
        obj = self.add()
        inserted = e.metadata(0)
        self.assertNotEqual(inserted['thumbnail'], original['thumbnail'])
        deleted = e.run(dict(kind='delete', index=0, rect=obj['bbox']))
        self.assertNotEqual(deleted['characters'], inserted['characters'])
        undo = e.run(dict(kind='undo', index=0))
        self.assertEqual(undo['characters'], inserted['characters'])
        redo = e.run(dict(kind='redo', index=0))
        self.assertEqual(redo['thumbnail'], deleted['thumbnail'])

    def test_reedit_cancel_and_update_do_not_reuse_wrong_document(self):
        e = self.engine
        obj = self.add()
        committed = e.metadata(0)
        editing = self.begin(obj)
        self.assertNotEqual(editing['characters'], committed['characters'])
        self.assertEqual(e.metadata(0)['characters'], editing['characters'])
        cancelled = e.run(dict(kind='cancel_edit', index=0))
        self.assertEqual(cancelled['thumbnail'], committed['thumbnail'])
        self.begin(obj)
        updated = self.update(obj, dict(self.spec, text='Replacement'))
        self.assertNotEqual(updated['characters'], committed['characters'])
        self.assertEqual(e.metadata(0)['thumbnail'], updated['thumbnail'])

    def test_save_flags_are_fresh_without_reextracting_page(self):
        e = self.engine
        self.add()
        self.assertTrue(e.metadata(0)['dirty'])
        e.run(dict(kind='save', path=str(Path(self.temp.name)/'saved.pdf')))
        with patch('pdf_worker.text_characters', side_effect=AssertionError('cache miss')):
            page = e.metadata(0)
        self.assertFalse(page['dirty'])
        self.assertTrue(page['can_undo'])

    def test_partial_failed_mutation_rolls_back_cache(self):
        e = self.engine
        original = e.metadata(0)
        real = pdf_worker.add_text
        def fail_after_write(*args, **kwargs):
            real(*args, **kwargs)
            raise ValueError('injected failure')
        with patch('pdf_worker.add_text', side_effect=fail_after_write):
            with self.assertRaisesRegex(ValueError, 'injected'):
                self.add()
        self.assertEqual(e.metadata(0), original)

    def test_open_encrypted_other_document_clears_old_content(self):
        e = self.engine
        original = e.metadata(0)
        path = Path(self.temp.name)/'different.pdf'
        with fitz.open() as doc:
            doc.new_page().insert_text((30,50),'Other encrypted document')
            doc.save(path, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='test', owner_pw='owner')
        opened = e.run(dict(kind='open',path=str(path),password='test'))
        self.assertNotEqual(opened['characters'],original['characters'])
        self.assertEqual(opened,e.metadata(0))
        self.assertEqual(len(e.page_cache),1)


class CharacterGeometryTests(unittest.TestCase):
    def test_fast_path_matches_original_geometry_with_crop_and_rotations(self):
        for rotation in (0,90,180,270):
            with self.subTest(rotation=rotation), fitz.open() as doc:
                page=doc.new_page(width=650,height=800)
                page.insert_text((70,110),'Exact geometry 012345',fontsize=17)
                page.set_cropbox(fitz.Rect(20,30,620,770))
                page.set_rotation(rotation)
                flags=(fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES)|fitz.TEXT_INHIBIT_SPACES|fitz.TEXT_ACCURATE_ASCENDERS
                expected=[]; line_id=0
                for block in page.get_text('rawdict',flags=flags)['blocks']:
                    for line in block.get('lines',[]):
                        for span in line['spans']:
                            for char in span['chars']:
                                expected.append(dict(id=len(expected),text=char['c'],bbox=list(fitz.Rect(char['bbox'])*page.rotation_matrix),line=line_id))
                        line_id+=1
                self.assertEqual(text_characters(page),expected)
