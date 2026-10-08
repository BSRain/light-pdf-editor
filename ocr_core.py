"""Bounded, offline OCR. No document or recognized text is written to disk."""
import base64
import math
from pathlib import Path
import statistics
import sys
import pymupdf as fitz
from pdf_core import sample_background

MAX_PIXELS = 12_000_000
LANGUAGES = ('chi_sim+eng', 'eng')


def checked_rect(page, values):
    rect = fitz.Rect(values)
    if not all(math.isfinite(v) for v in rect) or rect.is_empty or not page.rect.contains(rect) or min(rect.width, rect.height) < 3:
        raise ValueError('请在页面内框选至少 3 × 3 pt 的文字区域。')
    return rect


def snapshot(page, values):
    rect = checked_rect(page, values)
    if not any(fitz.Rect(info['bbox']).intersects(rect * page.derotation_matrix) for info in page.get_image_info()):
        raise ValueError('选区内没有图片；原生 PDF 文字请使用文字工具。')
    scale = min(300 / 72, math.sqrt((MAX_PIXELS - 20000) / (rect.width * rect.height)))
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=rect, colorspace=fitz.csRGB, alpha=False, annots=False)
    if pix.width * pix.height > MAX_PIXELS:
        raise ValueError('选区过大，请缩小识别范围。')
    try:
        fill = sample_background(page, list(rect))
        background_warning = ''
    except ValueError:
        fill = [1, 1, 1]
        background_warning = '选区外无可用底色，暂用白色；请手动检查或选择底色。'
    return dict(image=base64.b64encode(pix.tobytes('png')).decode('ascii'),
                rect=list(rect), origin=[pix.x / scale, pix.y / scale], scale=scale,
                width=pix.width, height=pix.height, dpi=round(scale * 72),
                fill_color=fill, background_warning=background_warning)


def language_directory():
    return (Path(sys.executable).parent if getattr(sys, 'frozen', False) else Path(__file__).parent) / 'ocr_data'


def recognize(data, language='chi_sim+eng', tessdata=None, fontfile=None):
    if language not in LANGUAGES:
        raise ValueError('请选择简体中文＋英文或英文。')
    folder = Path(tessdata) if tessdata is not None else language_directory()
    if not all((folder / (name + '.traineddata')).is_file() for name in language.split('+')):
        raise ValueError('OCR 语言包缺失，请完整解压包含 ocr_data 的新版程序。普通 PDF 编辑仍可使用。')
    if not (0 < data['width'] * data['height'] <= MAX_PIXELS):
        raise ValueError('OCR 图像超过像素上限。')
    pix = fitz.Pixmap(base64.b64decode(data['image'], validate=True))
    if pix.width != data['width'] or pix.height != data['height'] or pix.n != 3:
        raise ValueError('OCR 图像尺寸或颜色格式不匹配。')
    # Force a known resolution: OCR PDF coordinates are then exactly pixel units.
    pix.set_dpi(72, 72)
    pdf = pix.pdfocr_tobytes(language=language, tessdata=str(folder))
    lines = []
    rect = fitz.Rect(data['rect'])
    scale = data['scale']
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError('无效的 OCR 缩放比例。')
    ox, oy = data['origin']
    with fitz.open(stream=pdf, filetype='pdf') as doc:
        for block in doc[0].get_text('dict')['blocks']:
            for line in block.get('lines', []):
                text = ''.join(span['text'] for span in line['spans']).strip()
                if not text:
                    continue
                x0,y0,x1,y1 = line['bbox']
                bounds = fitz.Rect(ox+x0/scale, oy+y0/scale, ox+x1/scale, oy+y1/scale) & rect
                if not bounds.is_empty:
                    lines.append(dict(text=text, bbox=list(bounds)))
    if not lines:
        raise ValueError('未识别到文字。请框选清晰的横排印刷文字，适当留出边距后重试。')
    if sum(len(line['text']) for line in lines) > 20000:
        raise ValueError('识别文字过多，请分块转换。')
    if len(lines) > 200:
        raise ValueError('识别行数超过 200，请分块转换。')
    from ocr_layout import match_line
    for line in lines:
        line['spec'] = match_line(data, line, fontfile, pix)
    return dict(text='\n'.join(line['text'] for line in lines), lines=lines,
                size=max(4, min(96, statistics.median(line['bbox'][3]-line['bbox'][1] for line in lines))))


def main():
    import json
    for raw in sys.stdin:
        request = {}
        try:
            if len(raw) > 64 * 1024 * 1024:
                raise ValueError('OCR 请求过大。')
            request = json.loads(raw)
            result = recognize(request['snapshot'], request.get('language', 'chi_sim+eng'), fontfile=request.get('fontfile'))
            response = dict(id=request['id'], data=result)
        except Exception as exc:
            response = dict(id=request.get('id'), error=str(exc))
        print(json.dumps(response, ensure_ascii=False), flush=True)
