"""Editable project metadata inside a PDF attachment (encrypted with its PDF)."""
import hashlib
import json
import math

ATTACHMENT = 'light-pdf-editor-project-v1.json'
MAX_MANIFEST = 8 * 1024 * 1024


def page_signature(page):
    doc = page.parent
    data = dict(media=list(page.mediabox), crop=list(page.cropbox), rotation=page.rotation,
                contents=[(x, hashlib.sha256(doc.xref_stream(x)).hexdigest()) for x in page.get_contents()])
    return hashlib.sha256(json.dumps(data, sort_keys=True).encode()).hexdigest()


def write_manifest(doc, objects, serial, index, recovery=False, draft=None):
    has_alignment = any('align' in obj['spec'] for obj in objects.values()) or (draft is not None and 'align' in draft['spec'])
    format_version = 4 if any('page_rotation' in o for o in objects.values()) else (3 if has_alignment else (2 if recovery else 1))
    data = dict(format='light-pdf-editor', version=format_version, objects=objects, serial=serial, index=index,
                recovery=recovery, draft=draft,
                pages=[page_signature(p) for p in doc])
    content = json.dumps(data, ensure_ascii=False, allow_nan=False).encode('utf-8')
    if len(content) > MAX_MANIFEST:
        raise ValueError('工程文字信息超过 8 MiB，请分开保存文档。')
    if ATTACHMENT in doc.embfile_names():
        doc.embfile_del(ATTACHMENT)
    doc.embfile_add(ATTACHMENT, content, filename=ATTACHMENT, desc='Light PDF Editor editable project')


def require(condition):
    if not condition:
        raise ValueError('工程文字信息损坏，未打开该工程。')


def validate_spec(page, spec, allow_empty=False):
    require(set(spec) <= {'x', 'y', 'width', 'height', 'text', 'size', 'color', 'fontfile', 'bold', 'line_spacing', 'align'})
    require(isinstance(spec['text'], str) and (allow_empty or spec['text'].strip()))
    for name in ('x', 'y', 'width', 'height', 'size'):
        require(type(spec[name]) in (int, float) and math.isfinite(spec[name]))
    require(0 < spec['size'] <= 1000 and spec['width'] > 0 and spec['height'] > 0)
    require(spec['x'] >= 0 and spec['y'] >= 0)
    require(spec['x'] + spec['width'] <= page.rect.width + .001)
    require(spec['y'] + spec['height'] <= page.rect.height + .001)
    require(len(spec['color']) == 3 and all(type(c) in (int, float) and 0 <= c <= 1 for c in spec['color']))
    require(spec.get('fontfile') is None or isinstance(spec['fontfile'], str))
    require(type(spec.get('bold', False)) is bool)
    require(type(spec.get('align', 0)) is int and spec.get('align', 0) in (0, 1, 2))
    spacing = spec.get('line_spacing')
    require(spacing is None or (type(spacing) in (int, float) and math.isfinite(spacing) and 0 < spacing <= 1000))


def read_manifest(doc):
    if ATTACHMENT not in doc.embfile_names():
        raise ValueError('不是有效的轻简 PDF 工程文件。')
    if doc.embfile_info(ATTACHMENT)['size'] > MAX_MANIFEST:
        raise ValueError('工程信息过大，无法打开。')
    try:
        data = json.loads(doc.embfile_get(ATTACHMENT))
        if data['format'] != 'light-pdf-editor' or type(data['version']) is not int or data['version'] not in (1, 2, 3, 4):
            raise ValueError('工程版本不支持，请使用匹配版本的软件。')
        if data['pages'] != [page_signature(p) for p in doc]:
            raise ValueError('工程中的 PDF 页面已被其他软件改变，无法安全恢复文字框。')
        objects = data['objects']
        require(isinstance(objects, dict))
        require(type(data['serial']) is int and data['serial'] >= 0)
        require(type(data['index']) is int and 0 <= data['index'] < len(doc))
        used = set()
        for key, obj in objects.items():
            require(key == obj['id'] and key.isdecimal() and 0 < int(key) <= data['serial'])
            require(type(obj['index']) is int and 0 <= obj['index'] < len(doc))
            spec = obj['spec']
            require('align' not in spec or data['version'] in (3,4))
            page = doc[obj['index']]
            from page_rotation import object_frame
            if 'page_rotation' in obj:
                require(data['version']==4 and type(obj['page_rotation']) is int and obj['page_rotation'] in (0,90,180,270))
            frame,matrix=object_frame(page,obj)
            validate_spec(frame, spec)
            require(type(obj['offset']) in (int, float) and math.isfinite(obj['offset']) and obj['offset'] > 0)
            import pymupdf as fitz
            expected=list(fitz.Rect(spec['x'],spec['y'],spec['x']+spec['width'],spec['y']+spec['height'])*matrix)
            require(len(obj['bbox'])==4 and all(abs(a-b)<.001 for a,b in zip(obj['bbox'],expected)))
            require(obj['streams'])
            for xref, digest in obj['streams']:
                require(type(xref) is int and xref in page.get_contents() and xref not in used)
                require(hashlib.sha256(doc.xref_stream(xref)).hexdigest() == digest)
                used.add(xref)
        draft = data.get('draft')
        if draft is not None:
            require(data['version'] in (2, 3, 4) and data.get('recovery') is True)
            require(type(draft['index']) is int and draft['index'] == data['index'])
            require('align' not in draft['spec'] or data['version'] in (3,4))
            validate_spec(doc[draft['index']], draft['spec'], allow_empty=True)
            require(type(draft['offset']) in (int, float) and math.isfinite(draft['offset']) and draft['offset'] > 0)
            edit_id = draft['editing_id']
            require(edit_id is None or (isinstance(edit_id, str) and edit_id in objects and objects[edit_id]['index'] == draft['index']))
        return data
    except (KeyError, TypeError, AssertionError, json.JSONDecodeError, OverflowError) as exc:
        raise ValueError('工程文字信息损坏，未打开该工程。') from exc
