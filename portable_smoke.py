"""Explicit --smoke-test mode for testing the packaged application itself."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import pymupdf as fitz
from PySide6.QtCore import QPointF, QRectF
from PySide6.QtWidgets import QApplication
from pdf_core import windows_fonts
from version import __version__


def run(editor, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(version=__version__, frozen=bool(getattr(sys, 'frozen', False)),
                  executable=sys.executable, worker=editor.client.process.program(), checks=[])
    def wait(predicate):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            QApplication.processEvents()
            if editor.client.dead:
                raise RuntimeError('Worker exited: ' + editor.client.stderr)
            if predicate():
                return
            time.sleep(.01)
        raise TimeoutError(editor.client.stderr + ' / ' + editor.preview_label.text())
    try:
        source = output / '示例 source.pdf'
        with fitz.open() as doc:
            page = doc.new_page()
            page.insert_text((40, 60), 'Portable source')
            page.draw_rect(fitz.Rect(40, 100, 400, 260))
            doc.save(source)
        editor.open_pdf(str(source))
        wait(lambda: editor.path == source and not editor.busy)
        available = editor.screen().availableGeometry()
        report['window'] = dict(width=editor.width(), height=editor.height(),
                                available_width=available.width(), available_height=available.height(),
                                device_pixel_ratio=editor.devicePixelRatioF())
        if editor.width() > available.width() or editor.height() > available.height():
            raise AssertionError('Window exceeds available screen geometry')
        for button in (editor.apply_button, editor.cancel_button):
            if button.visibleRegion().boundingRect() != button.rect():
                raise AssertionError('Apply/cancel controls are clipped')
        report['checks'].append('open, render and visible apply/cancel controls')
        editor.view.select_characters(QRectF(38, 45, 160, 20), QPointF())
        editor.delete_characters()
        wait(lambda: not editor.busy)
        if any('Portable source' in span['text'] for span in editor.spans):
            raise AssertionError('Deletion did not remove source text')
        editor.undo(); wait(lambda: not editor.busy)
        report['checks'].append('precise deletion and undo')
        editor.text_input.setPlainText('便携版验证\nPortable verification')
        editor.size.setValue(14)
        editor.line_spacing.setValue(26)
        editor.text_align.setCurrentIndex(editor.text_align.findData(1))
        editor.font_combo.setCurrentText('内置中文字体')
        editor.place_cell(QPointF(100, 160))
        wait(lambda: editor.draft and editor.draft.valid)
        editor.apply()
        wait(lambda: not editor.busy and editor.draft is None)
        if not any('Portable' in s['text'] for s in editor.spans):
            raise AssertionError('Inserted text missing')
        report['checks'].append('cell placement, Chinese/English text and line spacing')
        editor.undo(); wait(lambda: not editor.busy)
        if editor.objects: raise AssertionError('Undo retained object')
        editor.redo(); wait(lambda: not editor.busy)
        if not editor.objects: raise AssertionError('Redo lost object')
        report['checks'].append('undo/redo')
        editor.view.set_zoom(1.25)
        wait(lambda: bool(editor.tile_items) and not editor.client.tiles)
        project = output / 'portable.lpdf'
        editor.set_busy(True)
        editor.client.command('save_project', path=str(project), index=0, epoch=editor.epoch)
        wait(lambda: not editor.busy and project.exists())
        editor.open_pdf(str(project))
        wait(lambda: not editor.busy and editor.path == project)
        obj = editor.objects[0]
        editor.edit_at(QPointF(obj['bbox'][0]+10, obj['bbox'][1]+10))
        wait(lambda: not editor.busy and editor.draft and editor.draft.valid)
        if editor.text_align.currentData() != 1: raise AssertionError('Project lost centered alignment')
        editor.text_input.setPlainText('工程重开验证\nReopened portable project')
        wait(lambda: editor.draft.valid)
        editor.apply(); wait(lambda: not editor.busy)
        report['checks'].append('project save/reopen/re-edit')
        exported = output / 'export.pdf'
        editor.set_busy(True)
        editor.client.command('save', path=str(exported), epoch=editor.epoch)
        wait(lambda: not editor.busy and exported.exists())
        with fitz.open(exported) as doc:
            if 'Reopened' not in doc[0].get_text(): raise AssertionError('Export text missing')
            if doc.embfile_count(): raise AssertionError('Export retained project metadata')
        report['checks'].append('PDF export and metadata removal')
        wait(lambda: bool(editor.tile_items) and not editor.client.active and not editor.client.tiles and not editor.tile_timer.isActive())
        editor.grab().save(str(output / 'portable_ui.png'))
        encrypted = output / 'encrypted.pdf'
        with fitz.open() as doc:
            doc.new_page()
            doc.save(encrypted, encryption=fitz.PDF_ENCRYPT_AES_256, user_pw='portable-test', owner_pw='portable-owner')
        editor.epoch += 1
        editor.set_busy(True)
        editor.client.command('open', path=str(encrypted), password='portable-test', epoch=editor.epoch)
        wait(lambda: not editor.busy and editor.path == encrypted)
        editor.text_input.setPlainText('Encrypted portable text')
        editor.place(QPointF(50, 100))
        wait(lambda: editor.draft and editor.draft.valid)
        editor.apply(); wait(lambda: not editor.busy)
        encrypted_output = output / 'encrypted-export.pdf'
        editor.set_busy(True)
        editor.client.command('save', path=str(encrypted_output), epoch=editor.epoch)
        wait(lambda: not editor.busy and encrypted_output.exists())
        with fitz.open(encrypted_output) as doc:
            if not doc.needs_pass or not doc.authenticate('portable-test'):
                raise AssertionError('Export lost encryption')
            if 'Encrypted' not in doc[0].get_text(): raise AssertionError('Encrypted export lost text')
        report['checks'].append('AES-256 open, edit and encrypted export')
        report['ok'] = True
    except Exception:
        report['ok'] = False
        report['error'] = traceback.format_exc()
    finally:
        editor.recovery_timer.stop()
        editor.preview_timer.stop()
        editor.tile_timer.stop()
        editor.client.close()
        editor.busy = editor.dirty = False
        editor.cancel(local=True)
        editor.close()
        (output / 'smoke-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
