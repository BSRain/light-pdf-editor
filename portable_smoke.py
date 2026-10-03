"""Explicit --smoke-test mode for testing the packaged application itself."""
import json
import os
from pathlib import Path
import sys
import time
import traceback
import pymupdf as fitz
from PySide6.QtGui import QColor, QDragEnterEvent, QDropEvent
from PySide6.QtCore import QPoint, QPointF, QRectF, QMimeData, QUrl, Qt, QTimer
from PySide6.QtWidgets import QApplication, QMessageBox
from pdf_core import windows_fonts
from version import __version__


def run(editor, output):
    output = Path(output).resolve()
    output.mkdir(parents=True, exist_ok=True)
    report = dict(version=__version__, frozen=bool(getattr(sys, 'frozen', False)),
                  executable=sys.executable, worker=editor.client.process.program(), checks=[])
    expected_dialogs = []
    unexpected_dialogs = []
    expect_crash = False
    expect_restart = False
    restart_dialogs = []
    def handle_test_dialogs():
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QMessageBox) and widget.isVisible():
                if expect_restart and widget.windowTitle() == '停止并重启处理进程':
                    restart_dialogs.append(widget.text())
                    widget.done(QMessageBox.StandardButton.Yes)
                    continue
                if expect_crash and widget.windowTitle() == 'PDF 处理进程已停止':
                    expected_dialogs.append(widget.text())
                else:
                    unexpected_dialogs.append(widget.windowTitle() + ': ' + widget.text())
                widget.done(QMessageBox.StandardButton.Ok)
    dialog_timer = QTimer(editor)
    dialog_timer.setInterval(30)
    dialog_timer.timeout.connect(handle_test_dialogs)
    dialog_timer.start()
    def wait(predicate):
        end = time.monotonic() + 30
        while time.monotonic() < end:
            QApplication.processEvents()
            if unexpected_dialogs:
                raise RuntimeError('Unexpected dialog: ' + unexpected_dialogs[-1])
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
            doc.new_page().insert_text((40, 60), "Navigation second page")
            doc.save(source)
        mime = QMimeData()
        mime.setUrls([QUrl.fromLocalFile(str(source))])
        enter = QDragEnterEvent(QPoint(100,100), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(editor.view.viewport(), enter)
        drop = QDropEvent(QPointF(100,100), Qt.DropAction.CopyAction, mime, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier)
        QApplication.sendEvent(editor.view.viewport(), drop)
        if not enter.isAccepted() or not drop.isAccepted():
            raise AssertionError('PDF drop events were rejected')
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
        report['checks'].append('PDF drop events, open, render and visible apply/cancel controls')
        previous_client = editor.client
        expect_restart = True
        editor.restart_worker()
        expect_restart = False
        wait(lambda: editor.client is not previous_client and editor.path == source and not editor.busy)
        if len(restart_dialogs) != 1:
            raise AssertionError('Manual restart did not show exactly one confirmation')
        report['checks'].append('manual live-worker restart confirmation and reopen')
        editor.pages_dock.show()
        wait(lambda: not editor.page_list.item(0).icon().isNull())
        if editor.width() > available.width() or editor.height() > available.height():
            raise AssertionError('Navigation panel exceeds available screen geometry')
        editor.grab().save(str(output / 'navigation.png'))
        editor.go_to_page(1)
        wait(lambda: editor.index == 1 and not editor.busy)
        editor.go_to_page(0)
        wait(lambda: editor.index == 0 and not editor.busy)
        editor.pages_dock.hide()
        report['checks'].append('lazy thumbnails and page jump roundtrip')
        wait(lambda: not editor.tile_timer.isActive() and editor.client.active is None and not editor.client.tiles)
        editor.view.set_zoom(2.3)
        editor.schedule_tiles()
        if not editor.fallback_tiles:
            raise AssertionError('Previous sharp preview was discarded during zoom')
        wait(lambda: not editor.tile_timer.isActive() and editor.client.active is None and not editor.client.tiles)
        if editor.fallback_tiles or not editor.wanted.issubset(editor.tile_items):
            raise AssertionError('Zoom transition did not finish with current tiles')
        report['checks'].append('bounded sharp-preview transition during zoom')
        editor.view.set_zoom(2)
        editor.view.centerOn(editor.page_rect.center())
        QApplication.processEvents()
        point = editor.view.viewport().rect().center()
        before = editor.view.mapToScene(point)
        editor.view.set_zoom(editor.view.zoom*1.2, point)
        after = editor.view.mapToScene(point)
        if (after-before).manhattanLength() > 3:
            raise AssertionError('Zoom pointer position drifted')
        editor.fit_page()
        report['checks'].append('pointer-anchored zoom')
        editor.view.select_characters(QRectF(38, 45, 160, 20), QPointF())
        editor.delete_characters()
        wait(lambda: not editor.busy)
        editor.go_to_page(1)
        wait(lambda: editor.index == 1 and not editor.busy)
        editor.go_to_page(0)
        wait(lambda: editor.index == 0 and not editor.busy)
        if any('Portable source' in span['text'] for span in editor.spans):
            raise AssertionError('Deletion did not remove source text')
        editor.undo(); wait(lambda: not editor.busy)
        report['checks'].append('precise deletion, cache invalidation on revisit and undo')
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
        scan = output / 'scan.pdf'
        with fitz.open() as doc:
            page = doc.new_page(width=200, height=200)
            pix = fitz.Pixmap(fitz.csRGB, fitz.IRect(0,0,200,200), False)
            pix.set_rect(pix.irect, (232,219,170))
            pix.set_rect(fitz.IRect(45,45,70,70), (0,0,0))
            page.insert_image(page.rect, pixmap=pix)
            doc.save(scan)
        editor.open_pdf(str(scan))
        wait(lambda: not editor.busy and editor.path == scan)
        editor.mode.setCurrentIndex(editor.mode.findData('erase_image'))
        editor.use_auto_background()
        editor.delete_selection(QRectF(40,40,40,40))
        if editor.dirty or editor.erase_selection is None:
            raise AssertionError('Image selection edited before confirmation')
        wait(lambda: editor.erase_color_ready)
        editor.apply()
        wait(lambda: not editor.busy)
        scan_output = output / 'scan-erased.pdf'
        editor.set_busy(True)
        editor.client.command('save', path=str(scan_output), epoch=editor.epoch)
        wait(lambda: not editor.busy and scan_output.exists())
        with fitz.open(scan_output) as doc:
            pix = doc[0].get_pixmap()
            if any(abs(a-b)>1 for a,b in zip(pix.pixel(50,50),(232,219,170))) or pix.pixel(10,10) != (232,219,170):
                raise AssertionError('Image-region erasure did not preserve outside pixels')
        report['checks'].append('scanned-image erasure, automatic background fill and export')
        editor.mode.setCurrentIndex(editor.mode.findData('add'))
        editor.text_input.setPlainText('Recovered draft')
        editor.coords['width'].setValue(170)
        editor.coords['height'].setValue(55)
        editor.place(QPointF(10,140))
        wait(lambda: editor.draft and editor.draft.valid)
        editor.recovery_path = output / 'recovery.lpdf'
        editor.recovery_toggle.blockSignals(True)
        editor.recovery_toggle.setChecked(True)
        editor.recovery_toggle.blockSignals(False)
        editor.autosave()
        wait(lambda: editor.recovery_path.exists() and not editor.recovery_pending)
        recovery = editor.recovery_path
        expect_crash = True
        editor.client.process.kill()
        wait_end = time.monotonic()+5
        while not editor.client.dead and time.monotonic()<wait_end:
            QApplication.processEvents(); time.sleep(.01)
        if not editor.client.dead: raise AssertionError('Worker did not exit')
        expect_crash = False
        if len(expected_dialogs) != 1: raise AssertionError('Crash warning was not displayed exactly once')
        editor.cancel(local=True)
        editor.dirty = False
        editor.open_pdf(str(recovery))
        wait(lambda: not editor.busy and editor.draft and editor.draft.valid)
        if editor.text_input.toPlainText() != 'Recovered draft':
            raise AssertionError('Recovery lost unapplied draft')
        report['checks'].append('worker crash and unapplied-draft recovery')
        report['ok'] = True
    except Exception:
        report['ok'] = False
        report['error'] = traceback.format_exc()
    finally:
        dialog_timer.stop()
        editor.recovery_timer.stop()
        editor.preview_timer.stop()
        editor.tile_timer.stop()
        editor.client.close()
        editor.busy = editor.dirty = False
        editor.cancel(local=True)
        editor.close()
        (output / 'smoke-report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return 0 if report['ok'] else 1
