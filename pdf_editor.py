"""Local PDF text editor. Run with Python 3.10+."""
from pathlib import Path
import os
import tempfile
import sys
import hashlib
import math
from functools import lru_cache
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog, colorchooser
import pymupdf as fitz
from PIL import Image, ImageTk
from tkinterdnd2 import TkinterDnD, DND_FILES


def windows_fonts():
    folder = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts'
    names = {'微软雅黑': 'msyh.ttc', '宋体': 'simsun.ttc', '黑体': 'simhei.ttf',
             '楷体': 'simkai.ttf', '仿宋': 'simfang.ttf', 'Arial': 'arial.ttf',
             'Times New Roman': 'times.ttf', 'Consolas': 'consola.ttf'}
    return {name: str(folder / file) for name, file in names.items() if (folder / file).exists()}


@lru_cache(maxsize=24)
def load_font(path):
    return fitz.Font(fontfile=path)


def bold_font_path(path):
    if not path:
        return None
    path = Path(path)
    variants = {'msyh.ttc': 'msyhbd.ttc', 'arial.ttf': 'arialbd.ttf',
                'times.ttf': 'timesbd.ttf', 'consola.ttf': 'consolab.ttf'}
    name = variants.get(path.name.lower())
    candidate = path.with_name(name) if name else None
    return str(candidate) if candidate and candidate.exists() else None


def add_text(page, x, y, text, size, color, fontfile=None, width=None, height=None, bold=False):
    page_width, page_height = page.rect.width, page.rect.height
    if not (0 <= x < page_width and 0 <= y < page_height):
        raise ValueError('请在页面内点击。')
    box_width = page_width - x - 6 if width is None else width
    box_height = page_height - y - 6 if height is None else height
    if box_width <= 0 or box_height <= 0 or x + box_width > page_width or y + box_height > page_height:
        raise ValueError('文字框超出页面，请移动位置或减小文字框尺寸。')
    rect = fitz.Rect(x, y, x + box_width, y + box_height) * page.derotation_matrix
    synthetic_bold = False
    if bold:
        variant = bold_font_path(fontfile)
        if variant:
            fontfile = variant
        else:
            synthetic_bold = not (fontfile and load_font(fontfile).is_bold)
    fontname = 'china-s'
    if fontfile:
        font = load_font(fontfile)
        missing = set(c for c in text if not c.isspace() and not font.has_glyph(ord(c)))
        if missing:
            raise ValueError('当前字体不支持这些字符：' + ''.join(sorted(missing))[:16] + '。请选择其他字体。')
        fontname = 'PE' + hashlib.sha256(str(fontfile).encode()).hexdigest()[:16]
    remaining = page.insert_textbox(rect, text, fontsize=size, fontname=fontname, fontfile=fontfile,
                                   color=color, fill=color, rotate=page.rotation,
                                   render_mode=2 if synthetic_bold else 0,
                                   border_width=size * 0.025 if synthetic_bold else 0.05)
    if remaining < 0:
        raise ValueError('文字框放不下这些文字，请增大文字框或减小字号。')


def delete_text(page, visible_rect):
    rect = fitz.Rect(visible_rect) * page.derotation_matrix
    # Avoid applying any redactions already in the source document.
    if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in (page.annots() or [])):
        raise ValueError('本页有已有的涂黑标记，请先在原软件中处理这些标记。')
    chars = [c for b in page.get_text('rawdict')['blocks'] if 'lines' in b
             for line in b['lines'] for span in line['spans'] for c in span['chars']
             if fitz.Rect(c['bbox']).intersects(rect)]
    if not chars:
        raise ValueError('选区内没有可删除的文字。扫描件中的文字是图片，暂不支持。')
    page.add_redact_annot(rect, fill=False, cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)


class Editor:
    def __init__(self, root):
        self.root = root
        self.doc = None
        self.path = None
        self.index = 0
        self.zoom = 1.25
        self.history = []
        self.dirty = False
        self.color = (0, 0, 0)
        self.start = None
        self.selection = None
        self.anchor = None
        self.preview_job = None
        self.drag_state = None
        self.preview_valid = False
        self.fit_mode = False
        self.resize_job = None
        self.origin = (20, 20)
        self.fonts = windows_fonts()
        self.revision = 0
        self.display_key = None
        self.display_list = None
        self.sharp_image = None
        self.sharp_key = None
        self.sharp_zoom = None
        self.zoom_job = None
        root.title('轻简 PDF · 文字编辑器')
        root.geometry('1280x860')
        root.minsize(980, 680)
        root.option_add('*Font', ('Microsoft YaHei UI', 10))
        style = ttk.Style()
        style.theme_use('vista' if 'vista' in style.theme_names() else 'clam')
        style.configure('TButton', padding=(12, 7))
        toolbar = ttk.Frame(root, padding=12)
        toolbar.pack(fill='x')
        for label, command in [('打开 PDF', self.open), ('另存为', self.save), ('撤销', self.undo)]:
            ttk.Button(toolbar, text=label, command=command).pack(side='left', padx=3)
        self.mode = tk.StringVar(value='add')
        for label, value in [('添加文字', 'add'), ('框选删除', 'delete')]:
            ttk.Radiobutton(toolbar, text=label, variable=self.mode, value=value,
                            command=self.change_mode).pack(side='left', padx=12)
        nav = ttk.Frame(root, padding=(12, 0, 12, 10))
        nav.pack(fill='x')
        ttk.Button(nav, text='上一页', command=lambda: self.turn(-1)).pack(side='left')
        self.page_label = ttk.Label(nav, text='尚未打开文件', width=24, anchor='center')
        self.page_label.pack(side='left')
        ttk.Button(nav, text='下一页', command=lambda: self.turn(1)).pack(side='left')
        ttk.Button(nav, text='适合页面', command=self.fit_page).pack(side='left', padx=12)
        ttk.Button(nav, text='−', command=lambda: self.scale(-0.25)).pack(side='right')
        self.zoom_label = ttk.Label(nav, text='125%', width=7, anchor='center')
        self.zoom_label.pack(side='right')
        ttk.Button(nav, text='+', command=lambda: self.scale(0.25)).pack(side='right')
        body = ttk.Frame(root)
        body.pack(fill='both', expand=True)
        self.build_panel(body)
        area = ttk.Frame(body)
        area.pack(side='left', fill='both', expand=True)
        area.rowconfigure(0, weight=1)
        area.columnconfigure(0, weight=1)
        self.canvas = tk.Canvas(area, bg='#dce2ea', highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky='nsew')
        vs = ttk.Scrollbar(area, orient='vertical', command=lambda *args: self.scroll_view('y', *args))
        hs = ttk.Scrollbar(area, orient='horizontal', command=lambda *args: self.scroll_view('x', *args))
        vs.grid(row=0, column=1, sticky='ns')
        hs.grid(row=1, column=0, sticky='ew')
        self.canvas.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.canvas.create_text(390, 230, text='拖入 PDF，开始编辑\n\n也可以点击左上角“打开 PDF”',
                                fill='#59677b', font=('Microsoft YaHei UI', 20), justify='center')
        self.status = tk.StringVar(value='文件仅在本机处理。原文件不会自动覆盖。')
        ttk.Label(root, textvariable=self.status, padding=10).pack(fill='x')
        self.canvas.bind('<ButtonPress-1>', self.press)
        self.canvas.bind('<B1-Motion>', self.drag)
        self.canvas.bind('<ButtonRelease-1>', self.release)
        self.canvas.bind('<MouseWheel>', self.wheel_zoom)
        self.canvas.bind('<Shift-MouseWheel>', self.wheel_scroll)
        self.canvas.bind('<Motion>', self.hover)
        root.bind('<Control-o>', lambda e: self.open())
        root.bind('<Control-s>', lambda e: self.save())
        root.bind('<Control-z>', self.shortcut_undo)
        root.bind('<Escape>', lambda e: self.cancel_preview())
        root.bind('<Control-Return>', lambda e: self.apply_preview())
        for key, dx, dy in [('Left', -1, 0), ('Right', 1, 0), ('Up', 0, -1), ('Down', 0, 1)]:
            self.canvas.bind('<' + key + '>', lambda e, x=dx, y=dy: self.nudge(x, y))
            self.canvas.bind('<Shift-' + key + '>', lambda e, x=dx, y=dy: self.nudge(x * 10, y * 10))
        self.canvas.bind('<Configure>', self.on_resize)
        if hasattr(root, 'drop_target_register') and hasattr(root, 'TkdndVersion'):
            for widget in (root, self.canvas):
                widget.drop_target_register(DND_FILES)
                widget.dnd_bind('<<Drop>>', self.drop_file)

        root.protocol('WM_DELETE_WINDOW', self.close)

    def build_panel(self, parent):
        ui_scale = max(1, float(self.root.tk.call('tk', 'scaling')) / (96 / 72))
        panel_width = int(290 * ui_scale)
        outer = ttk.Frame(parent, width=panel_width)
        outer.pack(side='right', fill='y')
        outer.pack_propagate(False)
        footer = ttk.Frame(outer, padding=(12, 8))
        footer.pack(side='bottom', fill='x')
        scroller = ttk.Frame(outer)
        scroller.pack(fill='both', expand=True)
        self.panel_canvas = tk.Canvas(scroller, highlightthickness=0, width=panel_width - 20,
                                      background=ttk.Style().lookup('TFrame', 'background') or '#f0f0f0')
        bar = ttk.Scrollbar(scroller, orient='vertical', command=self.panel_canvas.yview)
        bar.pack(side='right', fill='y')
        self.panel_canvas.pack(side='left', fill='both', expand=True)
        self.panel_canvas.configure(yscrollcommand=bar.set)
        panel = ttk.Frame(self.panel_canvas, padding=(12, 10))
        panel_window = self.panel_canvas.create_window(0, 0, window=panel, anchor='nw')
        panel.bind('<Configure>', lambda e: self.panel_canvas.configure(scrollregion=self.panel_canvas.bbox('all')))
        self.panel_canvas.bind('<Configure>', lambda e: self.panel_canvas.itemconfigure(panel_window, width=e.width))
        self.panel_canvas.bind('<MouseWheel>', lambda e: self.panel_canvas.yview_scroll(-int(e.delta / 120) * 3, 'units'))
        ttk.Label(panel, text='文字属性', font=('Microsoft YaHei UI', 13, 'bold')).pack(anchor='w')
        ttk.Label(panel, text='输入文字 → 点击定位 → 应用', padding=(0, 8)).pack(anchor='w')
        self.text_input = tk.Text(panel, height=4, wrap='word', undo=True, relief='solid', borderwidth=1)
        self.text_input.pack(fill='x')
        self.text_input.bind('<<Modified>>', self.text_changed)
        ttk.Label(panel, text='字体', padding=(0, 10, 0, 4)).pack(anchor='w')
        self.font_name = tk.StringVar(value=next(iter(self.fonts), '内置宋体'))
        self.font_combo = ttk.Combobox(panel, textvariable=self.font_name, state='readonly',
                                      values=list(self.fonts) or ['内置宋体'])
        self.font_combo.pack(fill='x')
        ttk.Button(panel, text='选择字体文件…', command=self.import_font).pack(fill='x', pady=5)
        line = ttk.Frame(panel)
        line.pack(fill='x', pady=6)
        ttk.Label(line, text='字号 (pt)').pack(side='left')
        self.size = tk.StringVar(value='14')
        ttk.Spinbox(line, from_=6, to=96, width=5, textvariable=self.size).pack(side='left', padx=8)
        self.color_button = ttk.Button(line, text='颜色 ■', command=self.choose_color)
        self.color_button.pack(side='right')
        self.bold = tk.BooleanVar(value=False)
        ttk.Checkbutton(panel, text='B  加粗', variable=self.bold, command=self.queue_preview).pack(anchor='w', pady=(2, 4))
        ttk.Separator(panel).pack(fill='x', pady=10)
        ttk.Label(panel, text='位置与文字框 (pt)').pack(anchor='w')
        self.coords = {}
        position_grid = ttk.Frame(panel)
        position_grid.pack(fill='x', pady=4)
        position_grid.columnconfigure(1, weight=1)
        position_grid.columnconfigure(3, weight=1)
        for i, (key, label, value) in enumerate([('x', 'X', '40'), ('y', 'Y', '40'),
                                                ('width', '宽', '260'), ('height', '高', '100')]):
            row, col = divmod(i, 2)
            ttk.Label(position_grid, text=label).grid(row=row, column=col * 2, padx=(0, 5), pady=4)
            var = tk.StringVar(value=value)
            self.coords[key] = var
            ttk.Spinbox(position_grid, from_=0, to=20000, increment=1, textvariable=var, width=7).grid(
                row=row, column=col * 2 + 1, sticky='ew', padx=(0, 8), pady=4)
            var.trace_add('write', self.queue_preview)
        self.preview_message = tk.StringVar(value='点击页面放置文字框。')
        ttk.Label(footer, textvariable=self.preview_message, wraplength=panel_width - 45, padding=(0, 8)).pack(fill='x')
        actions = ttk.Frame(footer)
        actions.pack(fill='x')
        self.apply_button = ttk.Button(actions, text='应用 Ctrl+Enter', command=self.apply_preview, state='disabled')
        self.apply_button.pack(side='left', fill='x', expand=True)
        ttk.Button(actions, text='取消 Esc', command=self.cancel_preview).pack(side='left', padx=(6, 0))
        ttk.Label(footer, text='框内拖动，边角拉伸；滚轮缩放。\nShift + 滚轮滚动页面。',
                  wraplength=panel_width - 40, foreground='#59677b').pack(fill='x', pady=8)
        self.size.trace_add('write', self.queue_preview)
        self.font_name.trace_add('write', self.queue_preview)

    def text_changed(self, event=None):
        if self.text_input.edit_modified():
            self.text_input.edit_modified(False)
            self.queue_preview()

    def shortcut_undo(self, event):
        if event.widget is not self.text_input:
            self.undo()
            return 'break'

    def import_font(self):
        path = filedialog.askopenfilename(filetypes=[('字体文件', '*.ttf *.otf *.ttc')])
        if path:
            try:
                font = load_font(path)
                name = font.name + ' · ' + Path(path).name
                self.fonts[name] = path
                self.font_combo.configure(values=list(self.fonts))
                self.font_name.set(name)
            except Exception as exc:
                messagebox.showerror('字体无法使用', str(exc))

    def drop_file(self, event):
        paths = self.root.tk.splitlist(event.data)
        if len(paths) != 1 or Path(paths[0]).suffix.lower() != '.pdf' or not Path(paths[0]).is_file():
            messagebox.showinfo('拖入 PDF', '请每次拖入一个 PDF 文件。')
            return 'refuse_drop'
        self.open(paths[0])
        return 'copy'

    def change_mode(self):
        if self.mode.get() != 'add':
            self.cancel_preview()
        self.hint()

    def hint(self):
        self.canvas.configure(cursor='crosshair' if self.mode.get() == 'add' else 'tcross')
        self.status.set('框内拖动定位，四边和四角调整大小；滚轮缩放，Shift + 滚轮滚动页面。' if self.mode.get() == 'add'
                        else '拖动框选需要删除的文字；与选框相交的字符会被删除。Ctrl+Z 撤销。')

    def queue_preview(self, *args):
        if self.drag_state is not None and self.preview_job:
            return
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
        self.preview_job = self.root.after(60 if self.drag_state is not None else 180, self.refresh_preview)

    def preview_args(self):
        coords = {key: float(var.get()) for key, var in self.coords.items()}
        size = float(self.size.get())
        if not 6 <= size <= 96:
            raise ValueError('字号应在 6 到 96 pt 之间。')
        text = self.text_input.get('1.0', 'end-1c')
        if not text.strip():
            raise ValueError('请在右侧输入文字。')
        return dict(**coords, text=text, size=size, color=self.color,
                    fontfile=self.fonts.get(self.font_name.get()), bold=self.bold.get())

    def refresh_preview(self):
        self.preview_job = None
        if self.doc:
            self.render()

    def cancel_preview(self):
        self.anchor = None
        self.drag_state = None
        if self.preview_job:
            self.root.after_cancel(self.preview_job)
            self.preview_job = None
        self.preview_valid = False
        self.apply_button.configure(state='disabled')
        self.preview_message.set('点击页面放置文字框。')
        if self.doc:
            self.render()

    def apply_preview(self):
        if not self.doc or self.anchor is None:
            return
        try:
            args = self.preview_args()
        except (ValueError, TypeError) as exc:
            messagebox.showerror('请检查文字设置', str(exc))
            return
        if self.edit(lambda page: add_text(page, **args)):
            self.cancel_preview()
            self.status.set('文字已添加。可继续添加，或另存为 PDF。')

    def nudge(self, dx, dy):
        if self.anchor is not None:
            try:
                self.coords['x'].set(f"{float(self.coords['x'].get()) + dx:.1f}")
                self.coords['y'].set(f"{float(self.coords['y'].get()) + dy:.1f}")
            except ValueError:
                pass
        return 'break'

    def on_resize(self, event=None):
        if self.resize_job:
            self.root.after_cancel(self.resize_job)
        self.resize_job = self.root.after(200, self.resize_view)

    def resize_view(self):
        self.resize_job = None
        if self.doc:
            if self.fit_mode:
                self.fit_page()
            else:
                self.render()

    def fit_page(self):
        if self.doc:
            rect = self.doc[self.index].rect
            self.zoom = max(0.1, min((self.canvas.winfo_width() - 48) / rect.width,
                                    (self.canvas.winfo_height() - 48) / rect.height, 3))
            self.fit_mode = True
            self.render()
            self.canvas.xview_moveto(0)
            self.canvas.yview_moveto(0)

    def discard(self):
        return not (self.dirty or self.anchor is not None) or messagebox.askyesno('未保存的修改', '有未保存的修改或文字预览，是否放弃？')

    def open(self, path=None):
        if not self.discard():
            return
        path = path or filedialog.askopenfilename(filetypes=[('PDF 文件', '*.pdf')])
        if not path:
            return
        candidate = None
        try:
            candidate = fitz.open(path)
            if candidate.needs_pass:
                password = simpledialog.askstring('加密文件', '请输入 PDF 密码：', show='*')
                if password is None or not candidate.authenticate(password):
                    raise ValueError('未提供正确密码。')
            if not candidate.page_count:
                raise ValueError('文件没有可显示的页面。')
            if self.doc:
                self.doc.close()
            self.doc, candidate = candidate, None
            self.path = Path(path)
            self.index, self.history, self.dirty = 0, [], False
            self.anchor = None
            self.fit_page()
            self.render()
            self.hint()
        except Exception as exc:
            messagebox.showerror('打开失败', str(exc))
        finally:
            if candidate is not None:
                candidate.close()

    def content_key(self):
        page = self.doc[self.index]
        preview = None
        if self.anchor is not None and self.mode.get() == 'add':
            preview = (tuple(v.get() for v in self.coords.values()), self.text_input.get('1.0', 'end-1c'),
                       self.size.get(), self.fonts.get(self.font_name.get()), self.color, self.bold.get())
        return (self.doc, self.revision, self.index, page.rotation, tuple(page.cropbox), preview)

    def prepare_display(self, key):
        if self.display_key == key:
            return
        page = self.doc[self.index]
        preview_doc = None
        self.preview_valid = False
        self.apply_button.configure(state='disabled')
        try:
            if self.anchor is not None and self.mode.get() == 'add':
                try:
                    args = self.preview_args()
                    preview_doc = fitz.open()
                    preview_doc.insert_pdf(self.doc, from_page=self.index, to_page=self.index)
                    add_text(preview_doc[0], **args)
                    page = preview_doc[0]
                    self.preview_valid = True
                    self.apply_button.configure(state='normal')
                    self.preview_message.set('实际排版预览；拖动蓝框后点击应用。')
                except (ValueError, TypeError, RuntimeError) as exc:
                    self.preview_message.set(str(exc) or '请输入有效的位置和文字框尺寸。')
            self.display_list = page.get_displaylist()
            self.display_key = key
        finally:
            if preview_doc is not None:
                preview_doc.close()

    def render(self, fast=False, focus=None):
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job)
            self.zoom_job = None
        page = self.doc[self.index]
        effective = min(self.zoom, (20_000_000 / (page.rect.width * page.rect.height)) ** 0.5)
        self.render_zoom = effective
        key = self.content_key()
        self.prepare_display(key)
        width, height = math.ceil(page.rect.width * effective), math.ceil(page.rect.height * effective)
        ox = max(20, (self.canvas.winfo_width() - width) / 2)
        oy = max(20, (self.canvas.winfo_height() - height) / 2)
        self.origin = (ox, oy)
        total_w = max(width + 40, self.canvas.winfo_width())
        total_h = max(height + 40, self.canvas.winfo_height())
        self.canvas.configure(scrollregion=(0, 0, total_w, total_h))
        if focus is not None:
            point, x, y = focus
            self.canvas.xview_moveto((ox + point[0] * effective - x) / total_w)
            self.canvas.yview_moveto((oy + point[1] * effective - y) / total_h)
        quick = fast and self.sharp_key == key and self.sharp_image is not None
        image_x, image_y = ox, oy
        if quick:
            # Scale only the visible part, so 400% zoom does not allocate a full-page bitmap per wheel tick.
            x0 = max(0, min(width - 1, math.floor(self.canvas.canvasx(0) - ox)))
            y0 = max(0, min(height - 1, math.floor(self.canvas.canvasy(0) - oy)))
            x1 = min(width, max(x0 + 1, math.ceil(self.canvas.canvasx(self.canvas.winfo_width()) - ox)))
            y1 = min(height, max(y0 + 1, math.ceil(self.canvas.canvasy(self.canvas.winfo_height()) - oy)))
            sx, sy = self.sharp_image.width / width, self.sharp_image.height / height
            image = self.sharp_image.transform((x1 - x0, y1 - y0), Image.Transform.EXTENT,
                                               (x0 * sx, y0 * sy, x1 * sx, y1 * sy),
                                               resample=Image.Resampling.BILINEAR)
            image_x, image_y = ox + x0, oy + y0
        else:
            if self.sharp_key != key or self.sharp_zoom != effective:
                pix = self.display_list.get_pixmap(matrix=fitz.Matrix(effective, effective), alpha=False)
                self.sharp_image = Image.frombytes('RGB', (pix.width, pix.height), pix.samples)
                self.sharp_key, self.sharp_zoom = key, effective
            image = self.sharp_image
        self.photo = ImageTk.PhotoImage(image)
        self.canvas.delete('all')
        self.canvas.create_rectangle(ox + 4, oy + 4, ox + width + 4, oy + height + 4,
                                     fill='#bcc4cf', outline='')
        self.canvas.create_image(image_x, image_y, image=self.photo, anchor='nw')
        self.draw_box()
        self.page_label.configure(text=f'第 {self.index + 1} / {len(self.doc)} 页')
        self.zoom_label.configure(text=f'{effective:.0%}')
        self.root.title(f'{"* " if self.dirty else ""}{self.path.name} · 轻简 PDF')
        if quick:
            self.zoom_job = self.root.after(150, self.finish_zoom)

    def finish_zoom(self):
        if self.zoom_job:
            self.root.after_cancel(self.zoom_job)
            self.zoom_job = None
        if self.doc:
            self.render()

    def scroll_view(self, axis, *args):
        if self.zoom_job:
            self.finish_zoom()
        (self.canvas.xview if axis == 'x' else self.canvas.yview)(*args)

    def point(self, event):
        return ((self.canvas.canvasx(event.x) - self.origin[0]) / self.render_zoom,
                (self.canvas.canvasy(event.y) - self.origin[1]) / self.render_zoom)

    def box_values(self):
        return tuple(float(self.coords[k].get()) for k in ('x', 'y', 'width', 'height'))

    @staticmethod
    def handles(box):
        x, y, w, h = box
        return {'nw': (x, y), 'n': (x + w / 2, y), 'ne': (x + w, y),
                'e': (x + w, y + h / 2), 'se': (x + w, y + h),
                's': (x + w / 2, y + h), 'sw': (x, y + h), 'w': (x, y + h / 2)}

    def draw_box(self):
        self.canvas.delete('preview')
        if self.anchor is None or self.mode.get() != 'add':
            return
        try:
            box = self.box_values()
        except ValueError:
            return
        x, y, w, h = box
        ox, oy = self.origin
        z = self.render_zoom
        color = '#0078d4' if self.preview_valid else '#d83b01'
        self.canvas.create_rectangle(ox + x * z, oy + y * z, ox + (x + w) * z, oy + (y + h) * z,
                                     outline=color, width=2, dash=(5, 3), tags='preview')
        self.canvas.create_text(ox + x * z, oy + y * z - 10,
                                text='框内拖动 · 边角调整大小', anchor='sw', fill=color, tags='preview')
        radius = self.handle_radius()
        for name, (hx, hy) in self.handles(box).items():
            cx, cy = ox + hx * z, oy + hy * z
            self.canvas.create_rectangle(cx - radius, cy - radius, cx + radius, cy + radius,
                                         outline=color, fill='white', width=2, tags=('preview', 'handle-' + name))

    def handle_radius(self):
        return 4 * max(1, float(self.root.tk.call('tk', 'scaling')) / (96 / 72))

    def hit_box(self, point):
        if self.anchor is None or self.mode.get() != 'add':
            return None
        try:
            box = self.box_values()
        except ValueError:
            return None
        x, y = point
        tolerance = (self.handle_radius() + 3) / self.render_zoom
        # Corners take priority when a box is small on screen.
        positions = self.handles(box)
        for name in ('nw', 'ne', 'se', 'sw', 'n', 'e', 's', 'w'):
            hx, hy = positions[name]
            if abs(x - hx) <= tolerance and abs(y - hy) <= tolerance:
                return name
        bx, by, w, h = box
        if bx <= x <= bx + w and by <= y <= by + h:
            return 'move'
        return None

    def hover(self, event):
        if not self.doc or self.drag_state is not None:
            return
        hit = self.hit_box(self.point(event))
        cursors = {'move': 'fleur', 'nw': 'size_nw_se', 'se': 'size_nw_se',
                   'ne': 'size_ne_sw', 'sw': 'size_ne_sw', 'n': 'sb_v_double_arrow',
                   's': 'sb_v_double_arrow', 'e': 'sb_h_double_arrow', 'w': 'sb_h_double_arrow'}
        cursor = cursors.get(hit, 'crosshair' if self.mode.get() == 'add' else 'tcross')
        try:
            self.canvas.configure(cursor=cursor)
        except tk.TclError:
            self.canvas.configure(cursor='fleur' if hit else 'crosshair')

    def set_box(self, box):
        for key, value in zip(('x', 'y', 'width', 'height'), box):
            # Preserve enough precision at fractional PDF page boundaries.
            self.coords[key].set(f'{value:.6f}'.rstrip('0').rstrip('.') or '0')

    def press(self, event):
        if not self.doc:
            return
        if self.zoom_job:
            self.finish_zoom()
        point = self.point(event)
        hit = self.hit_box(point)
        # Border handles can extend a few pixels beyond the page.
        if not hit and not self.doc[self.index].rect.contains(fitz.Point(point)):
            return
        self.canvas.focus_set()
        if self.mode.get() == 'add':
            if hit:
                self.drag_state = (hit, point, self.box_values())
            else:
                x, y = point
                rect = self.doc[self.index].rect
                try:
                    _, _, w, h = self.box_values()
                except ValueError:
                    w, h = 260, 100
                w, h = min(max(12, w), rect.width), min(max(12, h), rect.height)
                x, y = min(x, rect.width - w), min(y, rect.height - h)
                self.anchor = (x, y)
                box = (x, y, w, h)
                self.drag_state = ('move', point, box)
                self.set_box(box)
                self.draw_box()
        else:
            self.start = point

    def drag(self, event):
        if self.mode.get() == 'add' and self.drag_state is not None:
            kind, start, box = self.drag_state
            px, py = self.point(event)
            dx, dy = px - start[0], py - start[1]
            x, y, w, h = box
            rect = self.doc[self.index].rect
            if kind == 'move':
                x = max(0, min(x + dx, max(0, rect.width - w)))
                y = max(0, min(y + dy, max(0, rect.height - h)))
            else:
                right, bottom = x + w, y + h
                if 'w' in kind:
                    x = max(0, min(x + dx, right - 12))
                if 'e' in kind:
                    right = min(rect.width, max(x + 12, right + dx))
                if 'n' in kind:
                    y = max(0, min(y + dy, bottom - 12))
                if 's' in kind:
                    bottom = min(rect.height, max(y + 12, bottom + dy))
                w, h = right - x, bottom - y
            self.set_box((x, y, w, h))
            self.draw_box()
            return
        if self.start is None:
            return
        self.canvas.delete('selection')
        x, y = self.start
        self.canvas.create_rectangle(x * self.render_zoom + self.origin[0], y * self.render_zoom + self.origin[1],
                                     self.canvas.canvasx(event.x), self.canvas.canvasy(event.y),
                                     outline='#e34b55', width=2, dash=(4, 3), tags='selection')

    def release(self, event):
        if self.drag_state is not None:
            self.drag(event)
            self.drag_state = None
            if self.preview_job:
                self.root.after_cancel(self.preview_job)
                self.preview_job = None
            self.render()
            self.hover(event)
            return
        if self.start is None:
            return
        x, y = self.start
        x2, y2 = self.point(event)
        self.start = None
        self.canvas.delete('selection')
        rect = fitz.Rect(min(x, x2), min(y, y2), max(x, x2), max(y, y2)) & self.doc[self.index].rect
        if rect.width > 2 and rect.height > 2:
            self.edit(lambda p: delete_text(p, rect))

    def zoom_at(self, zoom, x, y):
        if not self.doc or self.drag_state is not None or self.start is not None:
            return
        point = self.point(type('Pointer', (), {'x': x, 'y': y})())
        page = self.doc[self.index].rect
        limit = min(4, (20_000_000 / (page.width * page.height)) ** 0.5)
        self.zoom = min(limit, max(min(0.1, limit), zoom))
        self.fit_mode = False
        self.render(fast=True, focus=(point, x, y))

    def wheel_zoom(self, event):
        if self.doc and event.delta:
            steps = max(-4, min(4, event.delta / 120))
            self.zoom_at(self.render_zoom * (1.12 ** steps), event.x, event.y)
        return 'break'

    def wheel_scroll(self, event):
        if self.zoom_job:
            self.finish_zoom()
        if self.doc and self.drag_state is None and self.start is None:
            if event.delta:
                direction = -1 if event.delta > 0 else 1
                self.canvas.yview_scroll(direction * max(1, round(abs(event.delta) / 120)) * 3, 'units')
        return 'break'

    def edit(self, operation):
        before = self.doc.tobytes()
        try:
            operation(self.doc[self.index])
        except Exception as exc:
            self.doc.close()
            self.doc = fitz.open(stream=before, filetype='pdf')
            messagebox.showerror('未完成修改', str(exc))
            return False
        self.history.append((before, self.index, self.dirty))
        # Bound undo memory for larger documents.
        while len(self.history) > 1 and (len(self.history) > 20 or sum(len(h[0]) for h in self.history) > 128_000_000):
            self.history.pop(0)
        self.dirty = True
        self.revision += 1
        self.render()
        self.status.set('修改已应用，可 Ctrl+Z 撤销；点击“另存为”导出 PDF。')
        return True

    def undo(self):
        if self.anchor is not None:
            self.cancel_preview()
            return
        if not self.history:
            return
        data, self.index, self.dirty = self.history.pop()
        self.doc.close()
        self.doc = fitz.open(stream=data, filetype='pdf')
        self.render()
        self.status.set('已撤销上一次修改。')

    def save(self):
        if not self.doc:
            return
        if self.anchor is not None:
            if not messagebox.askyesno('文字尚未应用', '是否先应用当前文字，再保存？（选“否”返回编辑）'):
                return
            self.apply_preview()
            if self.anchor is not None:
                return
        path = filedialog.asksaveasfilename(defaultextension='.pdf', initialfile=self.path.stem + '_已修改.pdf',
                                          filetypes=[('PDF 文件', '*.pdf')])
        if not path:
            return
        if Path(path).resolve() == self.path.resolve():
            messagebox.showinfo('保留原文件', '请选择另一个文件名，保留原始 PDF。')
            return
        temp = None
        try:
            fd, temp = tempfile.mkstemp(suffix='.pdf', dir=str(Path(path).parent))
            os.close(fd)
            self.doc.save(temp, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
            os.replace(temp, path)
            self.dirty = False
            # Any undo after exporting changes the exported state.
            self.history = [(data, index, True) for data, index, _ in self.history]
            self.render()
            self.status.set(f'已保存：{path}')
        except Exception as exc:
            messagebox.showerror('保存失败', str(exc))
        finally:
            if temp and os.path.exists(temp):
                os.unlink(temp)

    def turn(self, delta):
        if self.doc and 0 <= self.index + delta < len(self.doc):
            if self.anchor is not None:
                messagebox.showinfo('文字尚未应用', '请先应用或取消当前文字，再切换页面。')
                return
            self.index += delta
            if self.fit_mode:
                self.fit_page()
            else:
                self.render()
            self.canvas.yview_moveto(0)

    def scale(self, delta):
        if self.doc:
            self.zoom_at(self.render_zoom + delta, self.canvas.winfo_width() / 2,
                         self.canvas.winfo_height() / 2)

    def choose_color(self):
        rgb, _ = colorchooser.askcolor(title='选择文字颜色')
        if rgb:
            self.color = tuple(c / 255 for c in rgb)
            self.color_button.configure(text='颜色 ' + '#%02x%02x%02x' % tuple(int(c) for c in rgb))
            self.queue_preview()

    def close(self):
        if self.discard():
            for job in (self.preview_job, self.resize_job, self.zoom_job):
                if job:
                    self.root.after_cancel(job)
            if self.doc:
                self.doc.close()
            self.root.destroy()


if __name__ == '__main__':
    if sys.platform == 'win32':
        import ctypes
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except (AttributeError, OSError):
            ctypes.windll.user32.SetProcessDPIAware()
    root = TkinterDnD.Tk()
    app = Editor(root)
    if len(sys.argv) > 1:
        root.after(100, lambda: app.open(sys.argv[1]))
    root.mainloop()
