"""Alignment, line pitch and bordered-cell layout regression fixtures."""
import tempfile
from pathlib import Path
import unittest
import pymupdf as fitz
from pdf_core import add_text, ruling_lines, text_spans, windows_fonts
from pdf_worker import Engine
from alignment import snap_box, sample_line_spacing, containing_cell, match_font


class LayoutTests(unittest.TestCase):
    def test_local_column_beats_closer_remote_baseline(self):
        spans = [dict(bbox=[40, 90, 180, 125], baseline=120, horizontal=True),
                 dict(bbox=[350, 90, 490, 125], baseline=123, horizontal=True)]
        x, y, guides = snap_box(50, 108, 400, 80, 15, spans, 6)
        self.assertEqual(y + 15, 120)
        self.assertIn(('h', 120), guides)
        x, y, guides = snap_box(360, 105, 100, 80, 15, spans, 6)
        self.assertEqual(y + 15, 123)

    def test_line_spacing_ignores_other_columns_and_font_sizes(self):
        source = dict(bbox=[40, 80, 150, 100], baseline=100, size=12, horizontal=True)
        neighbor = dict(bbox=[40, 104, 160, 124], baseline=124, size=12, horizontal=True)
        other = dict(bbox=[300, 96, 460, 116], baseline=116, size=12, horizontal=True)
        heading = dict(bbox=[40, 110, 160, 130], baseline=130, size=24, horizontal=True)
        self.assertEqual(sample_line_spacing(source, [source, neighbor, other, heading]), 24)
        self.assertIsNone(sample_line_spacing(source, [source, other, heading]))
        self.assertIsNone(sample_line_spacing(dict(source, horizontal=False), [neighbor]))

    def test_imported_font_family_and_narrow_font_fallback(self):
        available = ['Arial', '宋体', 'MyCustomFont-Regular.ttf']
        self.assertEqual(match_font('ABCDEF+MyCustomFont-Bold', available), 'MyCustomFont-Regular.ttf')
        self.assertEqual(match_font('Helvetica-BoldOblique', available), 'Arial')
        self.assertIsNone(match_font('ArialNarrow', available))
        self.assertIsNone(match_font('UnknownFont', available))

    def test_explicit_line_pitch_preview_export_rotations_and_reedit(self):
        for angle in (0, 90, 180, 270):
            with self.subTest(rotation=angle), tempfile.TemporaryDirectory() as folder:
                path = Path(folder) / 'layout.pdf'
                with fitz.open() as doc:
                    p = doc.new_page(width=600, height=800)
                    p.set_rotation(angle)
                    doc.save(path)
                e = Engine()
                try:
                    e.run(dict(kind='open', path=str(path)))
                    spec = dict(x=40, y=60, width=250, height=140, text='First line\nSecond line\nThird line',
                                size=14, color=(0, 0, 0), fontfile=windows_fonts()['Arial'], line_spacing=26)
                    preview = e.run(dict(kind='preview', spec=spec))
                    result = e.run(dict(kind='insert', spec=spec))
                    spans = result['spans']
                    self.assertEqual(len(spans), 3)
                    self.assertAlmostEqual(spans[0]['baseline'], 60 + preview['baseline_offset'], delta=.02)
                    for a, b in zip(spans, spans[1:]):
                        self.assertAlmostEqual(b['baseline'] - a['baseline'], 26, delta=.02)
                    obj = result['objects'][0]
                    e.run(dict(kind='begin_edit', object_id=obj['id'], revision=e.revision))
                    edited = dict(spec, line_spacing=30)
                    e.run(dict(kind='update_object', object_id=obj['id'], revision=e.revision, spec=edited))
                    output = Path(folder) / 'out.pdf'
                    e.run(dict(kind='save', path=str(output)))
                    with fitz.open(output) as saved:
                        spans = text_spans(saved[0])
                        self.assertAlmostEqual(spans[1]['baseline']-spans[0]['baseline'], 30, delta=.02)
                    e.run(dict(kind='undo'))
                    self.assertEqual(e.objects[obj['id']]['spec']['line_spacing'], 26)
                finally:
                    e.end_edit(); e.doc.close()

    def test_rotated_grid_cells_and_broken_borders(self):
        for angle in (0, 90, 180, 270):
            with self.subTest(rotation=angle), fitz.open() as doc:
                p = doc.new_page(width=600, height=800)
                p.set_rotation(angle)
                # Draw using visible coordinates, so expected cells stay fixed.
                for x in (40, 220, 400):
                    p.draw_line(fitz.Point(x, 60) * p.derotation_matrix, fitz.Point(x, 260) * p.derotation_matrix)
                for y in (60, 160, 260):
                    p.draw_line(fitz.Point(40, y) * p.derotation_matrix, fitz.Point(400, y) * p.derotation_matrix)
                lines = ruling_lines(p)
                self.assertEqual(containing_cell(100, 100, lines), (40, 60, 220, 160))
                self.assertEqual(containing_cell(300, 200, lines), (220, 160, 400, 260))
                self.assertIsNone(containing_cell(20, 30, lines))
                self.assertIsNone(containing_cell(100, 100, [s for s in lines if not (s[0]=='h' and s[1]==60)]))

    def test_chinese_bold_line_pitch_and_tight_box_guard(self):
        fonts = windows_fonts()
        for name in ('Arial', '微软雅黑', '宋体'):
            for bold in (False, True):
                with self.subTest(font=name, bold=bold), fitz.open() as doc:
                    p = doc.new_page()
                    text = 'First\nSecond' if name == 'Arial' else '第一行\n第二行'
                    add_text(p, 40, 50, text, 14, (0, 0, 0), fonts[name], 200, 120, bold, 26)
                    spans = text_spans(p)
                    self.assertAlmostEqual(spans[1]['baseline']-spans[0]['baseline'], 26, delta=.02)
                    before = p.get_text()
                    with self.assertRaises(ValueError):
                        add_text(p, 40, 200, text, 14, (0, 0, 0), fonts[name], 200, 15, bold, 2)
                    self.assertEqual(p.get_text(), before)

    def test_invalid_line_pitch_rejected_without_change(self):
        with fitz.open() as doc:
            p = doc.new_page()
            with self.assertRaises(ValueError):
                add_text(p, 40, 50, 'No change', 14, (0, 0, 0), line_spacing=-1)
            self.assertEqual(p.get_text(), '')


if __name__ == '__main__':
    unittest.main()
