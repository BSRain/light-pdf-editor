"""Reproducible Qt zoom benchmark on generated documents, not user files."""
import json
from pathlib import Path
import statistics
import sys
import tempfile
import time
import pymupdf as fitz
from PySide6.QtCore import QPoint, QPointF, QRectF, Qt
from PySide6.QtGui import QWheelEvent, QFont
from PySide6.QtWidgets import QApplication
from PySide6.QtTest import QTest
from pdf_editor import Editor
from pdf_core import add_text, windows_fonts


def wait_until(predicate, editor, seconds=30):
    end = time.perf_counter() + seconds
    while time.perf_counter() < end:
        QApplication.processEvents()
        if predicate():
            return
        time.sleep(0.005)
    raise RuntimeError('Timed out: ' + editor.client.stderr)


def make_document(path, kind):
    with fitz.open() as doc:
        page = doc.new_page(width=595, height=842)
        if kind == 'image':
            width, height = 1800, 2400
            row = bytes(v for x in range(width) for v in (220 + x % 32, 224 + x % 24, 226 + x % 20))
            pix = fitz.Pixmap(fitz.csRGB, width, height, row * height, False)
            page.insert_image(page.rect, pixmap=pix)
        if kind == 'vector':
            for i in range(1600):
                y = 20 + i * 0.48
                page.draw_line((20, y), (570, y), color=(0.6, 0.7, 0.8), width=0.2)
        for i in range(40):
            page.insert_text((45, 45 + i * 18), 'PDF zoom test - baseline alignment 0123456789', fontsize=11)
        doc.save(path, deflate=True)


def run():
    app = QApplication.instance() or QApplication([])
    app.setFont(QFont('Microsoft YaHei UI', 10))
    editor = Editor()
    editor.show()
    results = {}
    try:
        with tempfile.TemporaryDirectory() as directory:
            for kind in ('text', 'vector', 'image'):
                path = Path(directory) / (kind + '.pdf')
                make_document(path, kind)
                editor.open_pdf(str(path))
                wait_until(lambda: editor.path == path and not editor.busy, editor)
                wait_until(lambda: not editor.tile_timer.isActive() and editor.client.active is None
                           and not editor.client.tiles and bool(editor.tile_items), editor)
                durations = []
                viewport = editor.view.viewport()
                point = viewport.rect().center()
                for delta in ([120] * 8 + [-120] * 8) * 3:
                    event = QWheelEvent(QPointF(point), QPointF(viewport.mapToGlobal(point)), QPoint(),
                                        QPoint(0, delta), Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier,
                                        Qt.ScrollPhase.NoScrollPhase, False)
                    start = time.perf_counter()
                    QApplication.sendEvent(viewport, event)
                    QApplication.processEvents()
                    durations.append((time.perf_counter() - start) * 1000)
                    QTest.qWait(16)
                start = time.perf_counter()
                wait_until(lambda: not editor.tile_timer.isActive() and editor.client.active is None
                           and not editor.client.tiles, editor)
                results[kind] = dict(wheel_and_event_paint_median_ms=round(statistics.median(durations), 2),
                                     p95_ms=round(sorted(durations)[int(len(durations) * .95)], 2),
                                     settle_ms=round((time.perf_counter() - start) * 1000, 2),
                                     cache_mb=round(editor.cache_bytes / 1024 / 1024, 2))
            if '--screenshot' in sys.argv:
                path = Path(directory) / '对齐示例.pdf'
                fonts = windows_fonts()
                font = fonts.get('微软雅黑')
                with fitz.open() as doc:
                    page = doc.new_page()
                    add_text(page, 48, 42, '合同信息', 22, (0.1, 0.18, 0.3), font, 450, 70, True)
                    for text, y in [('项目名称：', 130), ('负责人：', 190), ('备注：', 250)]:
                        add_text(page, 48, y, text, 14, (0.15, 0.2, 0.3), font, 450, 60)
                    doc.save(path)
                editor.open_pdf(str(path))
                wait_until(lambda: editor.path == path and not editor.busy, editor)
                span = next(s for s in editor.spans if '项目' in s['text'])
                editor.sample(QPointF(55, span['baseline'] - 4))
                editor.text_input.setPlainText('合同资料整理')
                editor.place(QPointF(145, span['baseline'] + 2))
                wait_until(lambda: editor.draft and editor.draft.valid and not editor.client.tiles, editor)
                QTest.qWait(150)
                editor.grab().save('ui_preview.png')
                editor.cancel()
                editor.mode.setCurrentIndex(editor.mode.findData('precise'))
                editor.view.select_characters(QRectF(48, 40, 44, 32), QPointF())
                QTest.qWait(150)
                editor.grab().save('ui_precision.png')
                editor.cancel()
            editor.client.close()
    finally:
        editor.client.close()
        editor.dirty = False
        editor.busy = False
        editor.cancel()
        editor.close()
    report = dict(note='Synthetic fixtures; measures wheel dispatch plus GUI event processing, not total PDF render latency.',
                  qt='6.8.3', results=results)
    Path('qt_benchmark.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    run()
