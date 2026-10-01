"""PDF operations shared by the isolated worker and tests."""
from pathlib import Path
import os
import hashlib
import math
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


def add_text(page, x, y, text, size, color, fontfile=None, width=None, height=None, bold=False, line_spacing=None, align=0):
    if type(align) is not int or align not in (0, 1, 2):
        raise ValueError('请选择左对齐、居中或右对齐。')
    if line_spacing is not None and line_spacing <= 0:
        raise ValueError('行距必须大于零，或选择自动。')
    page_width, page_height = page.rect.width, page.rect.height
    if not (0 <= x < page_width and 0 <= y < page_height):
        raise ValueError('请在页面内点击。')
    box_width = page_width - x - 6 if width is None else width
    box_height = page_height - y - 6 if height is None else height
    if box_width <= 0 or box_height <= 0 or x + box_width > page_width + 0.001 or y + box_height > page_height + 0.001:
        raise ValueError('文字框超出页面，请移动位置或减小文字框尺寸。')
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
    metrics = load_font(fontfile) if fontfile else fitz.Font('china-s')
    widest = max((metrics.text_length(c, fontsize=size) if fontfile else size
                  for c in set(text) if not c.isspace()), default=0)
    if widest > box_width + .001:
        raise ValueError('文字框宽度小于单个字符，请加宽文字框或减小字号。')
    default_factor = 1.2 if metrics.ascender - metrics.descender <= 1 else metrics.ascender - metrics.descender
    factor = line_spacing / baseline_offset(fontfile, size) if line_spacing is not None else default_factor
    # Let MuPDF wrap words with ample vertical space, then test the actual last
    # baseline and descent. Its own fit estimate reserves a full extra line step.
    layout_height = min(100000000, max(box_height, (len(text) + 1) * size * factor + abs(metrics.descender * size)) * 2)
    layout_rect = fitz.Rect(x, y, x + box_width, y + layout_height) * page.derotation_matrix
    shape = page.new_shape()
    remaining = shape.insert_textbox(layout_rect, text, fontsize=size, fontname=fontname, fontfile=fontfile,
                                   color=color, fill=color, rotate=page.rotation, align=align,
                                   lineheight=factor,
                                   render_mode=2 if synthetic_bold else 0,
                                   border_width=0.025 if synthetic_bold else 0.05)
    if remaining >= 0:
        count = shape.text_cont.count('TJ\n')
        pitch = metrics.ascender * size * factor
        actual_height = size * (metrics.ascender - metrics.descender) + max(0, count - 1) * pitch
        if actual_height > box_height + 0.001:
            remaining = -1
    if remaining < 0:
        raise ValueError('文字框放不下这些文字，请增大文字框或减小字号。')
    shape.commit()


def delete_text(page, visible_rect):
    rect = fitz.Rect(visible_rect) * page.derotation_matrix
    # Avoid applying any redactions already in the source document.
    if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in (page.annots() or [])):
        raise ValueError('本页有已有的涂黑标记，请先在原软件中处理这些标记。')
    chars = [c for b in page.get_text('rawdict', flags=(fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES) | fitz.TEXT_ACCURATE_ASCENDERS)['blocks'] if 'lines' in b
             for line in b['lines'] for span in line['spans'] for c in span['chars']
             if fitz.Rect(c['bbox']).intersects(rect)]
    if not chars:
        raise ValueError('选区内没有可删除的文字。扫描件中的文字是图片，暂不支持。')
    page.add_redact_annot(rect, fill=False, cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)


def erase_image_region(page, visible_rect):
    """Blank actual image pixels and remove any OCR text in the selected area."""
    visible = fitz.Rect(visible_rect)
    if not all(math.isfinite(v) for v in visible) or visible.is_empty:
        raise ValueError('请选择有效的图片区域。')
    visible &= page.rect
    if visible.is_empty:
        raise ValueError('选区不在页面内。')
    rect = visible * page.derotation_matrix
    if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in (page.annots() or [])):
        raise ValueError('本页有已有的涂黑标记，请先在原软件中处理这些标记。')
    if not any(fitz.Rect(info['bbox']).intersects(rect) for info in page.get_image_info()):
        raise ValueError('选区内没有图片，请使用文字删除工具。')
    page.add_redact_annot(rect, fill=False, cross_out=False)
    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                          graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                          text=fitz.PDF_REDACT_TEXT_REMOVE)


def baseline_offset(fontfile, size, bold=False):
    if bold:
        fontfile = bold_font_path(fontfile) or fontfile
    font = load_font(fontfile) if fontfile else fitz.Font('china-s')
    return font.ascender * size


def text_spans(page):
    result = []
    matrix = page.rotation_matrix
    zero = fitz.Point(0, 0) * matrix
    # Accurate font metrics avoid shifted boxes from rounded PDF descriptors,
    # notably SimSun on 180-degree pages. Keep character selection in sync.
    flags = (fitz.TEXTFLAGS_DICT & ~fitz.TEXT_PRESERVE_IMAGES) | fitz.TEXT_ACCURATE_ASCENDERS
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


def text_characters(page):
    """Stable per-page character IDs, in visible coordinates; no image extraction."""
    matrix = page.rotation_matrix
    result = []
    flags = (fitz.TEXTFLAGS_RAWDICT & ~fitz.TEXT_PRESERVE_IMAGES) | fitz.TEXT_INHIBIT_SPACES | fitz.TEXT_ACCURATE_ASCENDERS
    line_id = 0
    for block in page.get_text('rawdict', flags=flags)['blocks']:
        for line in block.get('lines', []):
            for span in line['spans']:
                for char in span['chars']:
                    result.append(dict(id=len(result), text=char['c'],
                                       bbox=list(fitz.Rect(char['bbox']) * matrix), line=line_id))
            line_id += 1
    return result


class CharacterRectIndex:
    """Conservative Y-band lookup; retain source order for overlap subtraction."""
    def __init__(self, rects):
        self.rects = rects
        self.bands = {}
        self.wide = []
        for index, rect in enumerate(rects):
            bands = self.band_range(rect)
            if bands is None:
                self.wide.append(index)
            else:
                for band in bands:
                    self.bands.setdefault(band, []).append(index)

    @staticmethod
    def band_range(rect):
        if not math.isfinite(rect.y0) or not math.isfinite(rect.y1):
            return None
        first, last = math.floor(rect.y0 / 32), math.floor(rect.y1 / 32)
        # Huge/abnormal glyph boxes fall back to a scan, never unbounded buckets.
        return range(first, last + 1) if 0 <= last - first < 64 else None

    def candidates(self, rect):
        bands = self.band_range(rect)
        if bands is None:
            return self.rects
        indices = set(self.wide)
        for band in bands:
            indices.update(self.bands.get(band, ()))
        return [self.rects[index] for index in sorted(indices)]


def delete_characters(page, ids):
    """Use exclusive glyph regions so adjacent/overlapping glyphs are protected."""
    if any(a.type[0] == fitz.PDF_ANNOT_REDACT for a in (page.annots() or [])):
        raise ValueError('本页有已有的涂黑标记，请先在原软件中处理这些标记。')
    chars = text_characters(page)
    selected = set(ids)
    if not selected or not selected.issubset(range(len(chars))):
        raise ValueError('文字选区已失效，请重新选择。')
    protected = [fitz.Rect(c['bbox']) * page.derotation_matrix for c in chars if c['id'] not in selected]
    protected_index = CharacterRectIndex(protected)
    regions = []
    for char in chars:
        if char['id'] not in selected:
            continue
        box = fitz.Rect(char['bbox']) * page.derotation_matrix
        pieces = [box]
        for other in protected_index.candidates(box):
            if not box.intersects(other):
                continue
            remaining = []
            for part in pieces:
                overlap = part & other
                if overlap.is_empty:
                    remaining.append(part)
                    continue
                remaining.extend(r for r in (
                    fitz.Rect(part.x0, part.y0, overlap.x0, part.y1),
                    fitz.Rect(overlap.x1, part.y0, part.x1, part.y1),
                    fitz.Rect(overlap.x0, part.y0, overlap.x1, overlap.y0),
                    fitz.Rect(overlap.x0, overlap.y1, overlap.x1, part.y1)
                ) if r.width > 0.1 and r.height > 0.1)
            pieces = remaining
            if not pieces:
                break
        if not pieces:
            raise ValueError('所选字符与其他文字完全重叠，无法单独删除。请扩大选区包含重叠文字。')
        region = max(pieces, key=lambda r: r.get_area())
        dx, dy = min(0.1, region.width / 4), min(0.1, region.height / 4)
        regions.append(fitz.Rect(region.x0 + dx, region.y0 + dy, region.x1 - dx, region.y1 - dy))
    for region in regions:
        page.add_redact_annot(region, fill=False, cross_out=False)
    page.apply_redactions(images=0, graphics=0, text=0)
    # Confirm geometry as well as text: identical letters elsewhere must survive.
    expected = [c for c in chars if c['id'] not in selected]
    actual = text_characters(page)
    if len(expected) != len(actual) or any(
        a['text'] != b['text'] or any(abs(x - y) > 0.05 for x, y in zip(a['bbox'], b['bbox']))
        for a, b in zip(expected, actual)
    ):
        raise ValueError('此 PDF 的字符布局无法安全分离，已取消删除并保留原文。')


def ruling_lines(page):
    """Visible axis-aligned stroked segments for explicit bordered-cell placement."""
    lines = []
    matrix = page.rotation_matrix
    for drawing in page.get_drawings():
        if drawing.get('type') not in ('s', 'fs') or drawing.get('width', 1) > 3:
            continue
        for item in drawing['items']:
            pairs = []
            if item[0] == 'l':
                pairs = [(item[1], item[2])]
            elif item[0] == 're':
                rect = item[1]
                pairs = [(rect.tl, rect.tr), (rect.tr, rect.br), (rect.br, rect.bl), (rect.bl, rect.tl)]
            for a, b in pairs:
                a, b = a * matrix, b * matrix
                if abs(a.y - b.y) < .05 and abs(a.x - b.x) >= 10:
                    lines.append(('h', round((a.y + b.y) / 2, 2), min(a.x, b.x), max(a.x, b.x)))
                elif abs(a.x - b.x) < .05 and abs(a.y - b.y) >= 10:
                    lines.append(('v', round((a.x + b.x) / 2, 2), min(a.y, b.y), max(a.y, b.y)))
                if len(lines) > 5000:
                    return []
    # Merge touching grid segments so a row split at columns remains a border.
    merged = []
    for axis, coord, start, end in sorted(lines):
        if merged and merged[-1][0] == axis and abs(merged[-1][1] - coord) < .1 and start <= merged[-1][3] + .5:
            merged[-1] = (axis, merged[-1][1], min(merged[-1][2], start), max(merged[-1][3], end))
        else:
            merged.append((axis, coord, start, end))
    return merged
