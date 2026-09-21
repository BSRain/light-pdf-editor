import unittest
import tkinter as tk
from pathlib import Path
import pymupdf as fitz
from pdf_editor import add_text, delete_text, Editor, windows_fonts, bold_font_path
from tkinterdnd2 import TkinterDnD
from unittest.mock import patch
from types import SimpleNamespace
import tempfile


class EditorTests(unittest.TestCase):
    def test_edit_and_reopen(self):
        for rotation in (0, 90, 180, 270):
            with self.subTest(rotation=rotation):
                doc = fitz.open()
                p = doc.new_page(width=500, height=600)
                p.draw_rect(fitz.Rect(20, 20, 450, 300), fill=(0.9, 0.95, 1))
                p.insert_text((50, 80), 'DELETE ME')
                p.insert_text((50, 140), 'KEEP ME')
                p.set_rotation(rotation)
                target = p.search_for('DELETE ME')[0] * p.rotation_matrix
                delete_text(p, target)
                add_text(p, 40, 340, '新增文字 ABC 123', 14, (0, 0, 0))
                reopened = fitz.open(stream=doc.tobytes(garbage=4, deflate=True), filetype='pdf')
                page = reopened[0]
                text = page.get_text()
                self.assertNotIn('DELETE', text)
                self.assertIn('KEEP ME', text)
                self.assertIn('新增文字', text)
                self.assertEqual(len(page.get_drawings()), 1)
                bbox = page.search_for('新增文字')[0] * page.rotation_matrix
                self.assertAlmostEqual(bbox.x0, 40, delta=3)
                self.assertAlmostEqual(bbox.y0, 340, delta=8)
                page.get_pixmap()
                reopened.close()
                doc.close()

    def test_overflow_does_not_insert(self):
        doc = fitz.open()
        p = doc.new_page()
        with self.assertRaises(ValueError):
            add_text(p, p.rect.width - 10, p.rect.height - 10, 'too long', 30, (0, 0, 0))
        self.assertEqual(p.get_text(), '')
        doc.close()

    def test_font_embedding_and_rotations(self):
        fonts = windows_fonts()
        for name in ('微软雅黑', '宋体', '楷体'):
            if name not in fonts:
                continue
            for rotation in (0, 90, 180, 270):
                with self.subTest(font=name, rotation=rotation):
                    doc = fitz.open()
                    p = doc.new_page(width=500, height=600)
                    p.set_rotation(rotation)
                    add_text(p, 40, 180, '字体测试 ABC', 18, (0, 0, 0), fonts[name], 300, 100)
                    data = doc.tobytes(garbage=4)
                    saved = fitz.open(stream=data, filetype='pdf')
                    self.assertIn('字体测试', saved[0].get_text())
                    rect = saved[0].search_for('字体测试')[0] * saved[0].rotation_matrix
                    self.assertAlmostEqual(rect.x0, 40, delta=3)
                    self.assertTrue(170 < rect.y0 < 215)
                    self.assertTrue(any(len(saved.extract_font(f[0])[3]) > 1000 for f in saved[0].get_fonts()))
                    saved.close()
                    doc.close()

    def test_drop_preview_apply_save(self):
        root = TkinterDnD.Tk()
        root.withdraw()
        app = Editor(root)
        try:
            self.assertTrue(root.TkdndVersion)
            self.assertTrue(app.canvas.dnd_bind('<<Drop>>'))
            with tempfile.TemporaryDirectory() as directory:
                source = Path(directory) / '中文 带空格.pdf'
                doc = fitz.open()
                doc.new_page()
                source.write_bytes(doc.tobytes())
                doc.close()
                event = SimpleNamespace(data='{' + str(source) + '}')
                self.assertEqual(app.drop_file(event), 'copy')
                self.assertEqual(app.path, source)
                app.text_input.insert('1.0', '预览文字 ABC')
                app.anchor = (40, 40)
                app.render()
                self.assertTrue(app.preview_valid, app.preview_message.get())
                self.assertEqual(app.doc[0].get_text(), '')
                preview_pixels = bytes(app.photo.tk.call(app.photo, 'data', '-format', 'png'))
                app.apply_preview()
                self.assertIsNone(app.anchor)
                self.assertIn('预览文字', app.doc[0].get_text())
                # Compare exact underlying PDF renders, without selection overlay.
                final_pixels = bytes(app.photo.tk.call(app.photo, 'data', '-format', 'png'))
                self.assertEqual(preview_pixels, final_pixels)
                target = Path(directory) / '输出 文件.pdf'
                with patch('pdf_editor.filedialog.asksaveasfilename', return_value=str(target)):
                    app.save()
                saved = fitz.open(target)
                self.assertIn('预览文字', saved[0].get_text())
                saved.close()
                original = fitz.open(source)
                self.assertEqual(original[0].get_text(), '')
                original.close()
                app.undo()
                self.assertEqual(app.doc[0].get_text(), '')
                with patch('pdf_editor.messagebox.showinfo') as info:
                    self.assertEqual(app.drop_file(SimpleNamespace(data='{one.pdf} {two.pdf}')), 'refuse_drop')
                    info.assert_called_once()
        finally:
            for job in (app.preview_job, app.resize_job, app.zoom_job):
                if job:
                    root.after_cancel(job)
            if app.doc:
                app.doc.close()
            root.destroy()

    def test_bold_font_and_synthetic_bold_survive_export(self):
        fonts = windows_fonts()
        for name in ('微软雅黑', '宋体'):
            if name not in fonts:
                continue
            with self.subTest(font=name):
                doc = fitz.open()
                regular = doc.new_page()
                add_text(regular, 40, 50, '加粗文字 Bold', 24, (0.1, 0.2, 0.8), fonts[name])
                normal_pixels = regular.get_pixmap().samples
                bold_page = doc.new_page()
                add_text(bold_page, 40, 50, '加粗文字 Bold', 24, (0.1, 0.2, 0.8), fonts[name], bold=True)
                saved = fitz.open(stream=doc.tobytes(garbage=4), filetype='pdf')
                self.assertIn('加粗文字', saved[1].get_text())
                self.assertNotEqual(normal_pixels, saved[1].get_pixmap().samples)
                if bold_font_path(fonts[name]):
                    self.assertTrue(any('bold' in f[3].lower() for f in saved[1].get_fonts()))
                else:
                    traces = saved[1].get_texttrace()
                    self.assertTrue(any(t['type'] == 1 for t in traces))
                    for trace in traces:
                        for actual, wanted in zip(trace['color'], (0.1, 0.2, 0.8)):
                            self.assertAlmostEqual(actual, wanted, places=5)
                saved.close()
                doc.close()

    def test_ui_and_undo(self):
        root = tk.Tk()
        root.withdraw()
        app = Editor(root)
        app.doc = fitz.open()
        app.doc.new_page()
        app.path = Path('test.pdf')
        app.render()
        app.edit(lambda p: add_text(p, 50, 50, '测试文字', 14, (0, 0, 0)))
        self.assertTrue(app.dirty)
        app.undo()
        self.assertEqual(app.doc[0].get_text(), '')
        self.assertFalse(app.dirty)
        app.doc.close()
        root.destroy()


class InteractionTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.app = Editor(self.root)
        self.root.update_idletasks()
        self.root.update()
        app = self.app
        app.doc = fitz.open()
        app.doc.new_page(width=1000, height=1200)
        app.path = Path('interaction-test.pdf')
        app.zoom = 1.5
        app.anchor = (160, 200)
        app.set_box((160, 200, 240, 140))
        app.render()

    def tearDown(self):
        app = self.app
        for job in (app.preview_job, app.resize_job, app.zoom_job):
            if job:
                self.root.after_cancel(job)
        app.doc.close()
        self.root.destroy()

    def event_at(self, x, y, **kwargs):
        app = self.app
        return SimpleNamespace(x=app.origin[0] + x * app.render_zoom - app.canvas.canvasx(0),
                               y=app.origin[1] + y * app.render_zoom - app.canvas.canvasy(0), **kwargs)

    def test_all_resize_handles_keep_opposite_edges_fixed(self):
        app = self.app
        initial = (160, 200, 240, 140)
        for rotation in (0, 90):
            app.doc[0].set_rotation(rotation)
            for name in ('nw', 'n', 'ne', 'e', 'se', 's', 'sw', 'w'):
                with self.subTest(rotation=rotation, handle=name):
                    app.set_box(initial)
                    app.render()
                    self.assertEqual(sum(bool(app.canvas.find_withtag('handle-' + h))
                                         for h in app.handles(initial)), 8)
                    hx, hy = app.handles(initial)[name]
                    event = self.event_at(hx, hy)
                    app.hover(event)
                    app.press(event)
                    self.assertEqual(app.drag_state[0], name)
                    app.drag(self.event_at(hx + 30, hy + 20))
                    app.release(self.event_at(hx + 30, hy + 20))
                    x, y, w, h = app.box_values()
                    self.assertAlmostEqual(x, 190 if 'w' in name else 160)
                    self.assertAlmostEqual(y, 220 if 'n' in name else 200)
                    self.assertAlmostEqual(x + w, 430 if 'e' in name else 400)
                    self.assertAlmostEqual(y + h, 360 if 's' in name else 340)
                    self.assertEqual(app.size.get(), '14')
                    self.assertEqual(app.doc[0].get_text(), '')

    def test_move_after_scroll_and_clamp_to_page(self):
        app = self.app
        app.canvas.xview_moveto(0.08)
        app.canvas.yview_moveto(0.08)
        app.press(self.event_at(250, 260))
        self.assertEqual(app.drag_state[0], 'move')
        app.drag(self.event_at(300, 300))
        app.release(self.event_at(300, 300))
        self.assertEqual(app.box_values(), (210, 240, 240, 140))
        app.press(self.event_at(300, 300))
        app.release(self.event_at(3000, 3000))
        self.assertEqual(app.box_values(), (760, 1060, 240, 140))

    def test_resize_minimum_and_page_limits(self):
        app = self.app
        app.press(self.event_at(400, 340))
        app.release(self.event_at(0, 0))
        self.assertEqual(app.box_values(), (160, 200, 12, 12))
        app.set_box((160, 200, 240, 140))
        app.render()
        app.press(self.event_at(160, 200))
        app.release(self.event_at(-100, -100))
        self.assertEqual(app.box_values(), (0, 0, 400, 340))
        app.press(self.event_at(400, 340))
        app.release(self.event_at(2000, 2000))
        self.assertEqual(app.box_values(), (0, 0, 1000, 1200))
        # Handles remain reachable on the outside of a page edge.
        app.press(self.event_at(-2, -2))
        self.assertEqual(app.drag_state[0], 'nw')

    def test_zoom_reuses_layout_and_refreshes_sharp_image(self):
        app = self.app
        app.text_input.insert('1.0', '缓存与加粗测试')
        with patch('pdf_editor.add_text', wraps=add_text) as insert:
            app.render()
            display = app.display_list
            sharp = app.sharp_image
            self.assertEqual(insert.call_count, 1)
            for _ in range(5):
                app.wheel_zoom(SimpleNamespace(x=300, y=250, delta=120))
            self.assertEqual(insert.call_count, 1)
            self.assertIs(app.display_list, display)
            self.assertIs(app.sharp_image, sharp)
            self.assertIsNotNone(app.zoom_job)
            self.assertLessEqual(app.photo.width(), app.canvas.winfo_width() + 1)
            app.finish_zoom()
            self.assertIsNone(app.zoom_job)
            self.assertEqual(app.sharp_zoom, app.render_zoom)
            self.assertIsNot(app.sharp_image, sharp)
            self.assertEqual(insert.call_count, 1)
            app.bold.set(True)
            app.render()
            self.assertEqual(insert.call_count, 2)
            bold_pixels = app.sharp_image.tobytes()
            app.apply_preview()
            self.assertEqual(app.sharp_image.tobytes(), bold_pixels)
            self.assertIn('缓存与加粗测试', app.doc[0].get_text())
            app.undo()
            self.assertEqual(app.doc[0].get_text(), '')
            self.assertNotEqual(app.sharp_image.tobytes(), bold_pixels)

    def test_wheel_preserves_pointer_and_pdf_geometry(self):
        app = self.app
        app.canvas.xview_moveto(0.15)
        app.canvas.yview_moveto(0.16)
        event = SimpleNamespace(x=300, y=250, delta=120)
        before_point = app.point(event)
        before_box = app.box_values()
        zoom = app.render_zoom
        self.assertEqual(app.wheel_zoom(event), 'break')
        self.assertGreater(app.render_zoom, zoom)
        for actual, expected in zip(app.point(event), before_point):
            self.assertAlmostEqual(actual, expected, delta=1)
        self.assertEqual(app.box_values(), before_box)
        app.wheel_zoom(SimpleNamespace(x=300, y=250, delta=-120))
        self.assertAlmostEqual(app.render_zoom, zoom)
        app.wheel_zoom(SimpleNamespace(x=300, y=250, delta=15))
        self.assertGreater(app.render_zoom, zoom)
        current_zoom = app.render_zoom
        before_scroll = app.canvas.yview()
        app.wheel_scroll(SimpleNamespace(delta=-120))
        self.assertNotEqual(app.canvas.yview(), before_scroll)
        self.assertEqual(app.render_zoom, current_zoom)
        self.assertTrue(app.canvas.bind('<MouseWheel>'))
        self.assertTrue(app.canvas.bind('<Shift-MouseWheel>'))


if __name__ == '__main__':
    unittest.main()
