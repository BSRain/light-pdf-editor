"""Generated OCR fixture benchmark; engine-only, excluding GUI and process IPC."""
import json
from pathlib import Path
import statistics
import tempfile
import time
import pymupdf as fitz
from pdf_core import add_text, windows_fonts
from ocr_core import snapshot, recognize
from process_metrics import process_memory


def main():
    with fitz.open() as original:
        page=original.new_page(width=420,height=260)
        add_text(page,55,65,'金额 5000 元\nInvoice 12345',20,(0,0,0),windows_fonts().get('微软雅黑'),300,100)
        pixels=page.get_pixmap(matrix=fitz.Matrix(3,3))
        with fitz.open() as scanned:
            page=scanned.new_page(width=420,height=260)
            page.insert_image(page.rect,pixmap=pixels)
            started=time.perf_counter()
            data=snapshot(page,[40,50,370,175])
            render_ms=(time.perf_counter()-started)*1000
            times=[]
            for _ in range(3):
                started=time.perf_counter();result=recognize(data)
                times.append(round((time.perf_counter()-started)*1000,2))
                assert '5000' in result['text'] and '金额' in result['text'].replace(' ','')
    print(json.dumps(dict(scope='Generated 330x125 pt Chinese/English crop. Direct engine only, excludes GUI and IPC. Not representative of all scans.',
        dpi=data['dpi'],pixels=data['width']*data['height'],render_ms=round(render_ms,2),recognition_ms=times,
        median_ms=round(statistics.median(times),2),memory=process_memory(),
        model_bytes=sum(p.stat().st_size for p in Path('ocr_data').glob('*.traineddata'))),indent=2))

if __name__=='__main__': main()
