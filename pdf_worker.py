"""Isolated PDF owner. One JSON command/response per line over QProcess pipes."""
import base64
from copy import deepcopy
from collections import Counter, OrderedDict
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import pymupdf as fitz
from process_metrics import process_memory
from project_file import ATTACHMENT, write_manifest, read_manifest, validate_spec
from pdf_core import sample_background, erase_image_region, add_text, delete_text, text_spans, baseline_offset, text_characters, delete_characters, ruling_lines


class Engine:
    PAGE_CACHE_LIMIT = 16 * 1024 * 1024
    PAGE_CACHE_COUNT = 4

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
        self.objects = {}
        self.object_serial = 0
        self.edit_doc = None
        self.edit_id = None
        self.page_cache = OrderedDict()
        self.page_cache_bytes = 0
        self.page_cache_identity = None

    def clear_page_cache(self):
        self.page_cache.clear()
        self.page_cache_bytes = 0
        self.page_cache_identity = None

    def metadata(self, index):
        # Only immutable page content is cached. Session state is rebuilt below.
        identity = (self.revision, id(self.doc), id(self.edit_doc))
        if identity != self.page_cache_identity:
            self.clear_page_cache()
            self.page_cache_identity = identity
        cached = self.page_cache.pop(index, None)
        if cached is not None:
            self.page_cache[index] = cached
            content = json.loads(cached)
        else:
            page = (self.edit_doc if self.edit_doc is not None else self.doc)[index]
            scale = min(0.6, (700000 / (page.rect.width * page.rect.height)) ** 0.5)
            pix = self.get_display(index).get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            content = dict(width=page.rect.width, height=page.rect.height,
                spans=text_spans(page), characters=text_characters(page), ruling_lines=[list(line) for line in ruling_lines(page)],
                thumbnail=self.image(pix), scale=scale)
            # Serialized bytes give an exact payload budget and isolated return values.
            cached = json.dumps(content, ensure_ascii=False, separators=(',', ':')).encode('utf-8')
            if len(cached) <= self.PAGE_CACHE_LIMIT and self.PAGE_CACHE_COUNT > 0:
                while self.page_cache and (len(self.page_cache) >= self.PAGE_CACHE_COUNT or
                        self.page_cache_bytes + len(cached) > self.PAGE_CACHE_LIMIT):
                    _, removed = self.page_cache.popitem(last=False)
                    self.page_cache_bytes -= len(removed)
                self.page_cache[index] = cached
                self.page_cache_bytes += len(cached)
        return dict(content, path=str(self.path), index=index, count=len(self.doc), revision=self.revision,
                    objects=[deepcopy(o) for o in self.objects.values() if o['index'] == index],
                    dirty=self.dirty, can_undo=bool(self.history), can_redo=bool(self.future))

    @staticmethod
    def image(pix):
        return base64.b64encode(pix.tobytes('png')).decode('ascii')

    def get_display(self, index):
        key = (self.revision, index)
        if self.display_key != key:
            self.display = (self.edit_doc if self.edit_doc is not None else self.doc)[index].get_displaylist()
            self.display_key = key
        return self.display

    def restore(self, data):
        self.clear_page_cache()
        candidate = fitz.open(stream=data, filetype='pdf')
        if candidate.needs_pass and not candidate.authenticate(self.password):
            candidate.close()
            raise ValueError('恢复加密文件失败。')
        self.doc.close()
        self.doc = candidate
        self.display = None
        self.display_key = None

    def copy_document(self):
        candidate = fitz.open(stream=self.doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP), filetype='pdf')
        if candidate.needs_pass and not candidate.authenticate(self.password):
            candidate.close()
            raise ValueError('复制加密文档失败。')
        return candidate

    def end_edit(self):
        self.clear_page_cache()
        if self.edit_doc is not None:
            self.edit_doc.close()
        self.edit_doc = None
        self.edit_id = None
        self.display = None
        self.display_key = None

    def remove_object(self, doc, obj):
        contents = doc[obj['index']].get_contents()
        for xref, digest in obj['streams']:
            if xref not in contents or hashlib.sha256(doc.xref_stream(xref)).hexdigest() != digest:
                raise ValueError('文字对象已被其他操作改变，无法重新编辑。请撤销该操作后再试。')
        removed = {xref for xref, _ in obj['streams']}
        remaining = ' '.join(f'{xref} 0 R' for xref in contents if xref not in removed)
        doc.xref_set_key(doc[obj['index']].xref, 'Contents', '[' + remaining + ']')

    def insert_object(self, index, spec, object_id=None):
        before = set(self.doc[index].get_contents())
        add_text(self.doc[index], **spec)
        streams = [x for x in self.doc[index].get_contents() if x not in before]
        if not streams:
            raise ValueError('没有生成可编辑文字，请输入非空文字。')
        if object_id is None:
            self.object_serial += 1
            object_id = str(self.object_serial)
        self.objects[object_id] = dict(id=object_id, index=index, spec=deepcopy(spec),
            offset=baseline_offset(spec.get('fontfile'), spec['size'], spec.get('bold', False)),
            bbox=[spec['x'], spec['y'], spec['x'] + spec['width'], spec['y'] + spec['height']],
            streams=[(x, hashlib.sha256(self.doc.xref_stream(x)).hexdigest()) for x in streams])

    def delete_preserving_objects(self, index, rect=None, ids=None, images=False, fill_color=(1,1,1)):
        chars = text_characters(self.doc[index])
        original_fonts = self.doc[index].get_fonts()
        if ids is not None:
            selected = set(ids)
            if not selected or not selected.issubset(range(len(chars))):
                raise ValueError('文字选区已失效，请重新选择。')
            targets = [c for c in chars if c['id'] in selected]
            areas = [fitz.Rect(c['bbox']) for c in targets]
        else:
            areas = [fitz.Rect(rect)]
        survivors = [o for o in self.objects.values() if o['index'] == index and
                     not any(fitz.Rect(o['bbox']).intersects(area) for area in areas)]
        # Retire an overlapping cluster together to preserve paint order relative
        # to rewritten objects; detached survivors are reattached above that base.
        page_objects = [o for o in self.objects.values() if o['index'] == index]
        while True:
            survivor_ids = {o['id'] for o in survivors}
            retired = [o for o in page_objects if o['id'] not in survivor_ids]
            independent = [o for o in survivors if not any(
                fitz.Rect(o['bbox']).intersects(fitz.Rect(other['bbox'])) for other in retired)]
            if len(independent) == len(survivors):
                break
            survivors = independent
        order = self.doc[index].get_contents()
        survivors.sort(key=lambda o: min(order.index(xref) for xref, _ in o['streams']))
        # Keep original streams intact outside the deletion region. Redaction may
        # rewrite every stream still attached to the page, even distant ones.
        for obj in survivors:
            self.remove_object(self.doc, obj)
        if ids is not None:
            signatures = Counter((c['text'], *c['bbox']) for c in targets)
            remapped = []
            for char in text_characters(self.doc[index]):
                key = (char['text'], *char['bbox'])
                if signatures[key]:
                    remapped.append(char['id'])
                    signatures[key] -= 1
            if any(signatures.values()):
                raise ValueError('无法可靠定位所选文字，已取消删除。')
            delete_characters(self.doc[index], remapped)
        else:
            if images:
                erase_image_region(self.doc[index], rect, fill_color)
            else:
                delete_text(self.doc[index], rect)
        contents = self.doc[index].get_contents()
        for obj in survivors:
            contents.extend(xref for xref, _ in obj['streams'])
        if survivors:
            # Redaction drops unused font resources while the surviving streams
            # are detached. Restore their original font references before reuse.
            owner, prefix = self.doc[index].xref, 'Resources/'
            kind, value = self.doc.xref_get_key(owner, 'Resources')
            if kind == 'xref':
                owner, prefix = int(value.split()[0]), ''
            kind, value = self.doc.xref_get_key(owner, prefix + 'Font')
            if kind == 'xref':
                owner, prefix = int(value.split()[0]), ''
            else:
                prefix += 'Font/'
            present = {font[4] for font in self.doc[index].get_fonts()}
            for font in original_fonts:
                if font[4] not in present:
                    self.doc.xref_set_key(owner, prefix + font[4], f'{font[0]} 0 R')
        refs = ' '.join(f'{xref} 0 R' for xref in contents)
        self.doc.xref_set_key(self.doc[index].xref, 'Contents', '[' + refs + ']')
        survivor_ids = {o['id'] for o in survivors}
        self.objects = {key: obj for key, obj in self.objects.items()
                        if obj['index'] != index or key in survivor_ids}

    def validate_conversion(self, index, request):
        from ocr_core import checked_rect
        if request.get('revision') != self.revision:
            raise ValueError('页面已变化，请重新识别。')
        rect = checked_rect(self.doc[index], request['rect'])
        specs = request.get('specs', [request.get('spec')])
        if not isinstance(specs,list) or not 1 <= len(specs) <= 200:
            raise ValueError('请保留 1 至 200 个文字框，过多时请分块转换。')
        total = 0
        for spec in specs:
            if not isinstance(spec,dict):
                raise ValueError('转换文字信息不完整。')
            validate_spec(self.doc[index], spec)
            total += len(spec['text'])
            box = fitz.Rect(spec['x'], spec['y'], spec['x']+spec['width'], spec['y']+spec['height'])
            if not rect.contains(box):
                raise ValueError('转换文字必须位于原选区内。')
        if total > 20000:
            raise ValueError('文字过多，请分块转换。')
        if any(o['index'] == index and fitz.Rect(o['bbox']).intersects(rect) for o in self.objects.values()):
            raise ValueError('选区与已有可编辑文字框重叠，请缩小范围。')
        return specs

    def limit_history(self):
        # Shared undo/redo budget. A single oversize snapshot is retained.
        while len(self.history) + len(self.future) > 1 and (
            len(self.history) + len(self.future) > 20 or
            sum(len(h[0]) for h in self.history + self.future) > 128000000
        ):
            (self.history if self.history else self.future).pop(0)

    def run(self, request):
        kind = request['kind']
        if kind == 'metrics':
            return process_memory()
        if kind == 'open':
            candidate = fitz.open(request['path'])
            password = request.get('password', '')
            if candidate.needs_pass and not candidate.authenticate(password):
                candidate.close()
                return {'password_required': True}
            if not candidate.page_count:
                candidate.close()
                raise ValueError('文件中没有页面。')
            try:
                project = read_manifest(candidate) if Path(request['path']).suffix.lower() == '.lpdf' else None
            except Exception:
                candidate.close()
                raise
            self.end_edit()
            self.objects = project['objects'] if project else {}
            self.object_serial = project['serial'] if project else 0
            if self.doc:
                self.doc.close()
            self.doc, self.path, self.password = candidate, Path(request['path']).resolve(), password
            self.revision += 1
            self.history = []
            self.future = []
            self.dirty = False
            self.display_key = None
            result = self.metadata(project['index'] if project else 0)
            if project and project.get('recovery'):
                result['recovery_draft'] = project.get('draft')
                result['recovery'] = True
            return result
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
        if kind == 'thumbnail':
            if request.get('revision') != self.revision:
                return {'stale': True}
            # Committed document only; do not replace the active page display-list cache.
            page = self.doc[index]
            scale = min(130 / page.rect.width, 170 / page.rect.height)
            pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), alpha=False)
            return dict(image=self.image(pix))
        if kind == 'sample_background':
            if request.get('revision') != self.revision:
                raise ValueError('页面已变化，请重新取色。')
            return dict(color=sample_background(self.doc[index], request.get('rect'), request.get('point')))
        if kind == 'begin_edit':
            if self.edit_doc is not None:
                raise ValueError('请先应用或取消当前文字编辑。')
            obj = self.objects.get(request.get('object_id'))
            if not obj or obj['index'] != index or request.get('revision') != self.revision:
                raise ValueError('文字对象已失效，请重新选择。')
            candidate = self.copy_document()
            try:
                self.remove_object(candidate, obj)
            except Exception:
                candidate.close()
                raise
            self.edit_doc, self.edit_id = candidate, obj['id']
            self.revision += 1
            result = self.metadata(index)
            result['edit_object'] = deepcopy(obj)
            return result
        if kind == 'cancel_edit':
            self.end_edit()
            self.revision += 1
            return self.metadata(index)
        if self.edit_doc is not None and kind not in ('tile', 'update_object', 'autosave'):
            raise ValueError('请先应用或取消当前文字编辑。')
        if kind in ('ocr_snapshot', 'ocr_preview'):
            if request.get('revision') != self.revision:
                raise ValueError('页面已变化，请重新识别。')
            from ocr_core import snapshot
            if kind == 'ocr_snapshot':
                return snapshot(self.doc[index], request['rect'])
            specs = self.validate_conversion(index, request)
            with self.copy_document() as preview:
                erase_image_region(preview[index], request['rect'], request['fill_color'])
                for spec in specs:
                    add_text(preview[index], **spec)
                rect = fitz.Rect(request['rect'])
                scale = min(2, (2_000_000 / (rect.width * rect.height)) ** .5)
                pix = preview[index].get_pixmap(matrix=fitz.Matrix(scale,scale), clip=rect, alpha=False)
                return dict(image=self.image(pix))
        if kind == 'page':
            return self.metadata(index)
        if kind == 'tile':
            if request['revision'] != self.revision:
                return {'stale': True}
            pix = self.get_display(index).get_pixmap(matrix=fitz.Matrix(request['scale'], request['scale']),
                                                      clip=fitz.Rect(request['clip']), alpha=False)
            return dict(image=self.image(pix), x=pix.x, y=pix.y, scale=request['scale'])
        if kind in ('insert', 'delete', 'delete_chars', 'erase_image', 'update_object', 'ocr_convert'):
            before = self.doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)
            before_objects = deepcopy(self.objects)
            before_serial = self.object_serial
            try:
                if kind == 'insert':
                    self.insert_object(index, request['spec'])
                elif kind == 'update_object':
                    obj = self.objects.get(request.get('object_id'))
                    if not obj or obj['index'] != index or self.edit_id != obj['id'] or request.get('revision') != self.revision:
                        raise ValueError('文字对象已失效，请取消后重新选择。')
                    self.remove_object(self.doc, obj)
                    self.insert_object(index, request['spec'], obj['id'])
                elif kind == 'ocr_convert':
                    specs = self.validate_conversion(index, request)
                    self.delete_preserving_objects(index, rect=request['rect'], images=True, fill_color=request['fill_color'])
                    for spec in specs:
                        self.insert_object(index, spec)
                elif kind == 'erase_image':
                    if request.get('revision') != self.revision:
                        raise ValueError('页面已变化，请重新选择图片区域。')
                    self.delete_preserving_objects(index, rect=request['rect'], images=True, fill_color=request.get('fill_color', (1,1,1)))
                elif kind == 'delete_chars':
                    if request.get('revision') != self.revision:
                        raise ValueError('页面已变化，请重新选择文字。')
                    self.delete_preserving_objects(index, ids=request['ids'])
                else:
                    self.delete_preserving_objects(index, rect=request['rect'])
            except Exception:
                self.restore(before)
                self.objects = before_objects
                self.object_serial = before_serial
                raise
            self.end_edit()
            self.future = []
            self.history.append((before, self.dirty, index, before_objects))
            self.limit_history()
            self.dirty = True
            self.revision += 1
            return self.metadata(index)
        if kind in ('undo', 'redo'):
            source, destination = (self.history, self.future) if kind == 'undo' else (self.future, self.history)
            if source:
                data, dirty, edited_page, objects = source[-1]
                current = self.doc.tobytes(encryption=fitz.PDF_ENCRYPT_KEEP)
                self.restore(data)
                source.pop()
                destination.append((current, self.dirty, edited_page, deepcopy(self.objects)))
                self.objects = deepcopy(objects)
                self.dirty, index = dirty, edited_page
                self.limit_history()
                self.revision += 1
            return self.metadata(index)
        if kind in ('save', 'save_project', 'autosave'):
            target = Path(request['path']).resolve()
            if target == self.path:
                raise ValueError('请选择新的文件名，保留当前打开的原始文件。')
            if kind == 'save' and target.suffix.lower() == '.lpdf':
                raise ValueError('普通 PDF 请使用 .pdf 扩展名；保存工程请使用“保存工程”。')
            if kind in ('save_project', 'autosave') and target.suffix.lower() != '.lpdf':
                raise ValueError('工程文件请使用 .lpdf 扩展名。')
            temp = None
            try:
                fd, temp = tempfile.mkstemp(suffix='.pdf', dir=target.parent)
                os.close(fd)
                with self.copy_document() as export:
                    if ATTACHMENT in export.embfile_names():
                        export.embfile_del(ATTACHMENT)
                    if kind in ('save_project', 'autosave'):
                        draft = request.get('draft') if kind == 'autosave' else None
                        if draft is not None:
                            validate_spec(self.doc[index], draft['spec'], allow_empty=True)
                            if draft['index'] != index or draft['editing_id'] != self.edit_id:
                                raise ValueError('恢复副本中的草稿状态已变化，请重试。')
                        write_manifest(export, self.objects, self.object_serial, index,
                                       recovery=kind == 'autosave', draft=draft)
                    # Projects retain xref numbers used by editable-object references.
                    export.save(temp, garbage=2 if kind == 'save' else 1,
                                deflate=True, encryption=fitz.PDF_ENCRYPT_KEEP)
                os.replace(temp, target)
                if kind == 'autosave':
                    return {'saved': str(target)}
                self.dirty = False
                self.history = [(data, True, i, objects) for data, _, i, objects in self.history]
                self.future = [(data, True, i, objects) for data, _, i, objects in self.future]
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
    engine.end_edit()
    if engine.doc:
        engine.doc.close()


if __name__ == '__main__':
    main()
