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


def write_manifest(doc, objects, serial, index):
    data = dict(format='light-pdf-editor', version=1, objects=objects, serial=serial, index=index,
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


def read_manifest(doc):
    if ATTACHMENT not in doc.embfile_names():
        raise ValueError('不是有效的轻简 PDF 工程文件。')
    if doc.embfile_info(ATTACHMENT)['size'] > MAX_MANIFEST:
        raise ValueError('工程信息过大，无法打开。')
    try:
        data = json.loads(doc.embfile_get(ATTACHMENT))
        if data['format'] != 'light-pdf-editor' or data['version'] != 1:
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
            require(set(spec) <= {'x', 'y', 'width', 'height', 'text', 'size', 'color', 'fontfile', 'bold', 'line_spacing'})
            require(isinstance(spec['text'], str) and spec['text'].strip())
            for name in ('x', 'y', 'width', 'height', 'size'):
                require(type(spec[name]) in (int, float) and math.isfinite(spec[name]))
            require(0 < spec['size'] <= 1000 and spec['width'] > 0 and spec['height'] > 0)
            page = doc[obj['index']]
            require(spec['x'] >= 0 and spec['y'] >= 0)
            require(spec['x'] + spec['width'] <= page.rect.width + .001)
            require(spec['y'] + spec['height'] <= page.rect.height + .001)
            require(len(spec['color']) == 3 and all(type(c) in (int, float) and 0 <= c <= 1 for c in spec['color']))
            require(spec.get('fontfile') is None or isinstance(spec['fontfile'], str))
            require(type(spec.get('bold', False)) is bool)
            spacing = spec.get('line_spacing')
            require(spacing is None or (type(spacing) in (int, float) and math.isfinite(spacing) and 0 < spacing <= 1000))
            require(type(obj['offset']) in (int, float) and math.isfinite(obj['offset']) and obj['offset'] > 0)
            require(obj['bbox'] == [spec['x'], spec['y'], spec['x'] + spec['width'], spec['y'] + spec['height']])
            require(obj['streams'])
            for xref, digest in obj['streams']:
                require(type(xref) is int and xref in page.get_contents() and xref not in used)
                require(hashlib.sha256(doc.xref_stream(xref)).hexdigest() == digest)
                used.add(xref)
        return data
    except (KeyError, TypeError, AssertionError, json.JSONDecodeError, OverflowError) as exc:
        raise ValueError('工程文字信息损坏，未打开该工程。') from exc
