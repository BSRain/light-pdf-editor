"""Isolated PDF owner. One JSON command/response per line over QProcess pipes."""
import base64
import json
import os
from pathlib import Path
import sys
import tempfile
import pymupdf as fitz
from pdf_core import add_text, delete_text, text_spans, baseline_offset, text_characters, delete_characters


class Engine:
    def __init__(self):
        self.doc = None
        self.path = None
        self.password = ''
        self.revision = 0
        self.history = []
        self.future = []
        self.dirty = False
        self.display = None
        self.display_key = None

    def metadata(self, index):
        page = self.doc[index]
        scale = min(0.6, (700000 / (page.rect.width * page.rect.height)) ** 0.5)
        pix = self.get_display(index).get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
        return dict(path=str(self.path), index=index, count=len(self.doc), revision=self.revision,
                    width=page.rect.width, height=page.rect.height, spans=text_spans(page), characters=text_characters(page),
                    dirty=self.dirty, can_undo=bool(self.history), can_redo=bool(self.future), thumbnail=self.image(pix), scale=scale)

    @staticmethod
    def image(pix):
        return base64.b64encode(pix.tobytes('png')).decode('ascii')

    def get_display(self, index):
        key = (self.revision, index)
        if self.display_key != key:
            self.display = self.doc[index].get_displaylist()
            self.display_key = key
        return self.display

    def restore(self, data):
        candidate = fitz.open(stream=data, filetype='pdf')
        if candidate.needs_pass and not candidate.authenticate(self.password):
            candidate.close()
            raise ValueError('恢复加密文件失败。')
        self.doc.close()
        self.doc = candidate
        self.display = None
        self.display_key = None

    def limit_history(self):
        # Shared undo/redo budget. A single oversize snapshot is retained.
        while len(self.history) + len(self.future) > 1 and (
            len(self.history) + len(self.future) > 20 or
            sum(len(h[0]) for h in self.history + self.future) > 128000000
        ):
            (self.history if self.history else self.future).pop(0)

    def run(self, request):
        kind = request['kind']
        if kind == 'open':
            candidate = fitz.open(request['path'])
            password = request.get('password', '')
            if candidate.needs_pass and not candidate.authenticate(password):
                candidate.close()
                return {'password_required': True}
            if not candidate.page_count:
                candidate.close()
                raise ValueError('文件中没有页面。')
            if self.doc:
                self.doc.close()
            self.doc, self.path, self.password = candidate, Path(request['path']).resolve(), password
            self.revision += 1
            self.history = []
            self.future = []
            self.dirty = False
            self.display_key = None
            return self.metadata(0)
        if kind == 'preview':
            spec = dict(request['spec'])
            spec['x'], spec['y'] = 0, 0
            if not spec['text'].strip():
                raise ValueError('请先输入文字。')
            with fitz.open() as doc:
                page = doc.new_page(width=spec['width'], height=spec['height'])
                add_text(page, **spec)
                offset = baseline_offset(spec.get('fontfile'), spec['size'], spec.get('bold', False))
                trace = page.get_texttrace()
                if trace and trace[0]['chars']:
                    offset = trace[0]['chars'][0][2][1]
                scale = min(request.get('scale', 2), 4, (2000000 / (spec['width'] * spec['height'])) ** 0.5)
                pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=True)
                return dict(image=self.image(pix), baseline_offset=offset)
        if self.doc is None:
            raise ValueError('请先打开 PDF。')
        index = request.get('index', 0)
        if kind == 'page':
            return self.metadata(index)
        if kind == 'tile':
            if request['revision'] != self.revision:
                return {'stale': True}
            pix = self.get_display(index).get_pixmap(matrix=fitz.Matrix(request['scale'], request['scale']),
                                                      clip=fitz.Rect(request['clip']), alpha=False)
            return dict(image=self.image(pix), x=pix.x, y=pix.y, scale=request['scale'])
        if kind in ('insert', 'delete', 'delete_chars'):
            before = self.doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)
            try:
                if kind == 'insert':
                    add_text(self.doc[index], **request['spec'])
                elif kind == 'delete_chars':
                    if request.get('revision') != self.revision:
                        raise ValueError('页面已变化，请重新选择文字。')
                    delete_characters(self.doc[index], request['ids'])
                else:
                    delete_text(self.doc[index], request['rect'])
            except Exception:
                self.restore(before)
                raise
            self.future = []
            self.history.append((before, self.dirty, index))
            self.limit_history()
            self.dirty = True
            self.revision += 1
            return self.metadata(index)
        if kind in ('undo', 'redo'):
            source, destination = (self.history, self.future) if kind == 'undo' else (self.future, self.history)
            if source:
                data, dirty, edited_page = source[-1]
                current = self.doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)
                self.restore(data)
                source.pop()
                destination.append((current, self.dirty, edited_page))
                self.dirty, index = dirty, edited_page
                self.limit_history()
                self.revision += 1
            return self.metadata(index)
        if kind == 'save':
            target = Path(request['path']).resolve()
            if target == self.path:
                raise ValueError('请选择新的文件名，保留原始 PDF。')
            temp = None
            try:
                fd, temp = tempfile.mkstemp(suffix='.pdf', dir=target.parent)
                os.close(fd)
                self.doc.save(temp, garbage=4, deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                os.replace(temp, target)
                self.dirty = False
                self.history = [(data, True, i) for data, _, i in self.history]
                self.future = [(data, True, i) for data, _, i in self.future]
                return {'saved': str(target)}
            finally:
                if temp and os.path.exists(temp):
                    os.unlink(temp)
        raise ValueError('未知操作：' + kind)


def main():
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    fitz.TOOLS.mupdf_display_errors(False)
    fitz.TOOLS.mupdf_display_warnings(False)
    engine = Engine()
    for line in sys.stdin:
        request = {}
        try:
            request = json.loads(line)
            result = {'id': request['id'], 'data': engine.run(request)}
        except Exception as exc:
            result = {'id': request.get('id'), 'error': str(exc)}
        print(json.dumps(result, ensure_ascii=False), flush=True)
    if engine.doc:
        engine.doc.close()


if __name__ == '__main__':
    main()
