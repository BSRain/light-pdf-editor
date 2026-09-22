"""PDF operations shared by the isolated worker and tests."""
from pathlib import Path
import os
import hashlib
from functools import lru_cache
import pymupdf as fitz


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
    if box_width <= 0 or box_height <= 0 or x + box_width > page_width + 0.001 or y + box_height > page_height + 0.001:
        raise ValueError('文字框超出页面，请移动位置或减小文字框尺寸。')
    rect = fitz.Rect(x, y, min(x + box_width, page_width), min(y + box_height, page_height)) * page.derotation_matrix
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


def baseline_offset(fontfile, size, bold=False):
    if bold:
        fontfile = bold_font_path(fontfile) or fontfile
    font = load_font(fontfile) if fontfile else fitz.Font('china-s')
    return font.ascender * size


def text_spans(page):
    result = []
    matrix = page.rotation_matrix
    zero = fitz.Point(0, 0) * matrix
    flags = fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES
    for block in page.get_text('dict', flags=flags)['blocks']:
        for line in block.get('lines', []):
            direction = fitz.Point(line['dir']) * matrix - zero
            for span in line['spans']:
                if not span['text'].strip():
                    continue
                box = fitz.Rect(span['bbox']) * matrix
                origin = fitz.Point(span['origin']) * matrix
                result.append(dict(text=span['text'], bbox=list(box), baseline=origin.y,
                                   x=origin.x, size=span['size'], font=span['font'],
                                   color=span['color'], bold=bool(span['flags'] & 16),
                                   horizontal=abs(direction.y) < 0.02 and direction.x > 0.98))
    return result
