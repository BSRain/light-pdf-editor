"""Qt UI; PDF parsing, editing and rendering run in pdf_worker.py."""
from collections import OrderedDict
import base64
import json
import math
from pathlib import Path
import sys
from datetime import datetime
from uuid import uuid4
from PySide6.QtCore import Qt, Signal, QTimer, QPointF, QRectF, QSize, QEvent
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap, QImage, QFont, QPainterPath, QIcon
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QGraphicsView, QGraphicsScene,
    QGraphicsObject, QVBoxLayout, QHBoxLayout, QFormLayout, QLabel, QPushButton, QToolBar, QComboBox,
    QDoubleSpinBox, QCheckBox, QPlainTextEdit, QDockWidget, QFileDialog, QMessageBox,
    QColorDialog, QInputDialog, QLineEdit, QScrollArea, QStyleFactory, QSpinBox, QListWidget, QListWidgetItem)
from pdf_core import windows_fonts
from alignment import snap_box, nearest_span, match_font, word_at, sample_line_spacing, containing_cell
from version import __version__
from pdf_client import PdfClient
from ocr_dialog import OcrDialog


class FocusWheelMixin:
    """Scrolling past a property must not silently change the document style."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def wheelEvent(self, event):
        if self.hasFocus():
            super().wheelEvent(event)
        else:
            event.ignore()


class PropertyComboBox(FocusWheelMixin, QComboBox):
    pass


class PropertySpinBox(FocusWheelMixin, QDoubleSpinBox):
    pass



def decode_pixmap(data):
    image = QImage.fromData(base64.b64decode(data), 'PNG')
    if image.isNull():
        raise ValueError('预览图像解码失败。')
    return QPixmap.fromImage(image)


class Draft(QGraphicsObject):
    changed = Signal(bool)

    def __init__(self, editor, width=260, height=90):
        super().__init__()
        self.editor = editor
        self.w, self.h = width, height
        self.snap_enabled = True
        self.minimum_size = 12
        self.offset = editor.size.value() * 1.1
        self.pixmap = None
        self.valid = False
        self.gesture = None
        self.setZValue(20)
        self.setAcceptHoverEvents(True)
        self.setFlag(self.GraphicsItemFlag.ItemIsFocusable)

    def boundingRect(self):
        return QRectF(-64, -64, self.w + 128, self.h + 128)

    def handles(self):
        return {'nw': (0, 0), 'n': (self.w / 2, 0), 'ne': (self.w, 0), 'e': (self.w, self.h / 2),
                'se': (self.w, self.h), 's': (self.w / 2, self.h), 'sw': (0, self.h), 'w': (0, self.h / 2)}

    def hit(self, point):
        tolerance = 7 / self.editor.view.zoom
        positions = self.handles()
        for name in ('nw', 'ne', 'se', 'sw', 'n', 'e', 's', 'w'):
            x, y = positions[name]
            if abs(point.x() - x) <= tolerance and abs(point.y() - y) <= tolerance:
                return name
        if QRectF(0, 0, self.w, self.h).contains(point):
            return 'move'
        return None

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.pixmap is not None:
            painter.drawPixmap(QRectF(0, 0, self.w, self.h), self.pixmap, QRectF(self.pixmap.rect()))
        color = QColor('#0078d4' if self.valid else '#b85c00')
        pen = QPen(color, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(QRectF(0, 0, self.w, self.h))
        painter.drawLine(QPointF(0, self.offset), QPointF(self.w, self.offset))
        pen.setStyle(Qt.PenStyle.SolidLine)
        painter.setPen(pen)
        painter.setBrush(Qt.GlobalColor.white)
        radius = 4 / self.editor.view.zoom
        for x, y in self.handles().values():
            painter.drawRect(QRectF(x - radius, y - radius, radius * 2, radius * 2))

    def hoverMoveEvent(self, event):
        hit = self.hit(event.pos())
        cursors = {'move': Qt.CursorShape.SizeAllCursor, 'nw': Qt.CursorShape.SizeFDiagCursor,
                   'se': Qt.CursorShape.SizeFDiagCursor, 'ne': Qt.CursorShape.SizeBDiagCursor,
                   'sw': Qt.CursorShape.SizeBDiagCursor, 'n': Qt.CursorShape.SizeVerCursor,
                   's': Qt.CursorShape.SizeVerCursor, 'e': Qt.CursorShape.SizeHorCursor,
                   'w': Qt.CursorShape.SizeHorCursor}
        self.setCursor(cursors.get(hit, Qt.CursorShape.CrossCursor))

    def mousePressEvent(self, event):
        hit = self.hit(event.pos())
        if event.button() != Qt.MouseButton.LeftButton or not hit:
            event.ignore()
            return
        self.gesture = (hit, event.scenePos(), self.pos(), self.w, self.h)
        self.setFocus()
        event.accept()

    def resize_box(self, width, height):
        self.prepareGeometryChange()
        self.w, self.h = width, height
        self.valid = False
        self.pixmap = None
        self.update()

    def mouseMoveEvent(self, event):
        if not self.gesture:
            return
        kind, start, position, width, height = self.gesture
        delta = event.scenePos() - start
        x, y = position.x(), position.y()
        right, bottom = x + width, y + height
        bounds = self.editor.page_rect
        if kind == 'move':
            x, y = x + delta.x(), y + delta.y()
            if self.snap_enabled and self.editor.snap.isChecked() and not event.modifiers() & Qt.KeyboardModifier.AltModifier:
                x, y, guides = snap_box(x, y, width, height, self.offset, self.editor.spans, 7 / self.editor.view.zoom)
                self.editor.draw_guides(guides)
            else:
                self.editor.draw_guides([])
            x, y = max(0, min(x, bounds.width() - width)), max(0, min(y, bounds.height() - height))
            self.setPos(x, y)
        else:
            if 'w' in kind:
                x = max(0, min(x + delta.x(), right - self.minimum_size))
            if 'e' in kind:
                right = min(bounds.width(), max(x + self.minimum_size, right + delta.x()))
            if 'n' in kind:
                y = max(0, min(y + delta.y(), bottom - self.minimum_size))
            if 's' in kind:
                bottom = min(bounds.height(), max(y + self.minimum_size, bottom + delta.y()))
            self.setPos(x, y)
            self.resize_box(right - x, bottom - y)
        self.changed.emit(kind != 'move')
        event.accept()

    def mouseReleaseEvent(self, event):
        if self.gesture:
            self.mouseMoveEvent(event)
            self.gesture = None
            self.changed.emit(False)
        event.accept()

    def mouseDoubleClickEvent(self, event):
        self.editor.text_input.setFocus()
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and not self.editor.busy:
            self.editor.cancel()
            self.editor.statusBar().showMessage('已删除待添加的文字框。', 4000)
            event.accept()
            return
        directions = {Qt.Key.Key_Left: (-1, 0), Qt.Key.Key_Right: (1, 0), Qt.Key.Key_Up: (0, -1), Qt.Key.Key_Down: (0, 1)}
        if event.key() in directions:
            step = 10 if event.modifiers() & Qt.KeyboardModifier.ShiftModifier else 1
            dx, dy = directions[event.key()]
            x = max(0, min(self.x() + dx * step, self.editor.page_rect.width() - self.w))
            y = max(0, min(self.y() + dy * step, self.editor.page_rect.height() - self.h))
            self.setPos(x, y)
            self.editor.draw_guides([])
            self.changed.emit(False)
            event.accept()
        else:
            super().keyPressEvent(event)


class EraseSelection(Draft):
    """Adjustable region only; never edits the PDF until explicitly confirmed."""
    def __init__(self, editor, width, height):
        super().__init__(editor, width, height)
        self.snap_enabled = False
        self.minimum_size = 3

    def paint(self, painter, option, widget=None):
        pen = QPen(QColor('#d83b01'), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        painter.setPen(pen)
        painter.setBrush(QColor(216, 59, 1, 45))
        painter.drawRect(QRectF(0, 0, self.w, self.h))
        painter.setBrush(Qt.GlobalColor.white)
        radius = 4 / self.editor.view.zoom
        for x, y in self.handles().values():
            painter.drawRect(QRectF(x-radius, y-radius, radius*2, radius*2))

    def mouseDoubleClickEvent(self, event):
        event.accept()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.editor.confirm_image_erase()
            event.accept()
        elif event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.editor.cancel()
            event.accept()
        else:
            super().keyPressEvent(event)


class PdfView(QGraphicsView):
    viewport_changed = Signal()

    def __init__(self, editor):
        super().__init__()
        self.editor = editor
        self.zoom = 1.0
        self.pan = None
        self.selection_start = None
        self.selection = None
        self.erase_hover = None
        self.precise_items = []
        self.selected_chars = []
        self.setMouseTracking(True)
        self.setScene(QGraphicsScene(self))
        self.setBackgroundBrush(QColor('#d9dfe7'))
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        self.setViewportUpdateMode(self.ViewportUpdateMode.MinimalViewportUpdate)
        self.setTransformationAnchor(self.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(self.ViewportAnchor.AnchorViewCenter)
        self.setAcceptDrops(True)
        self.horizontalScrollBar().valueChanged.connect(self.viewport_changed)
        self.verticalScrollBar().valueChanged.connect(self.viewport_changed)

    def set_zoom(self, value, anchor=None):
        if not self.editor.path:
            return
        value = max(0.2, min(6, value))
        point = anchor or self.viewport().rect().center()
        before = self.mapToScene(point)
        self.scale(value / self.zoom, value / self.zoom)
        self.zoom = value
        after = self.mapToScene(point)
        delta = after - before
        self.translate(delta.x(), delta.y())
        self.editor.zoom_label.setText(f'{value:.0%}')
        if self.editor.draft:
            self.editor.draft.update()
        self.viewport_changed.emit()

    def wheelEvent(self, event):
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - event.angleDelta().y())
        else:
            delta = event.angleDelta().y() or event.pixelDelta().y() * 3
            self.set_zoom(self.zoom * 1.12 ** (max(-480, min(480, delta)) / 120), event.position().toPoint())
        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.viewport_changed.emit()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.MiddleButton:
            self.pan = event.position()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        point = self.mapToScene(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and self.editor.picking_background and not self.editor.busy:
            if self.editor.page_rect.contains(point):
                self.editor.request_background(point)
            event.accept()
            return
        draft = self.editor.draft or self.editor.erase_selection
        if event.button() == Qt.MouseButton.LeftButton and draft and draft.hit(draft.mapFromScene(point)):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and not self.editor.busy and self.editor.page_rect.contains(point):
            mode = self.editor.mode.currentData()
            if mode == 'sample':
                self.editor.sample(point)
            elif mode == 'cell':
                self.editor.place_cell(point)
            elif mode == 'edit':
                self.editor.edit_at(point)
            elif mode == 'add':
                self.editor.place(point)
            elif mode == 'erase':
                span = nearest_span(point.x(), point.y(), self.editor.spans, 3 / self.zoom)
                if span:
                    x0, y0, x1, y1 = span['bbox']
                    self.editor.delete_selection(QRectF(x0, y0, x1 - x0, y1 - y0))
                else:
                    self.editor.statusBar().showMessage('此处没有可删除的文字；扫描件请切换“擦除图片区域”。', 5000)
            elif mode in ('delete', 'precise', 'erase_image', 'ocr'):
                self.selection_start = point
                pen = QPen(QColor('#d83b01'), 1, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self.selection = self.scene().addRect(QRectF(point, point), pen)
                self.selection.setZValue(30)
            elif mode == 'pan':
                self.pan = event.position()
                self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def clear_erase_hover(self):
        if self.erase_hover is not None:
            self.scene().removeItem(self.erase_hover)
            self.erase_hover = None

    def mouseMoveEvent(self, event):
        if self.pan is not None:
            delta = event.position() - self.pan
            self.pan = event.position()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - round(delta.x()))
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - round(delta.y()))
            return
        if self.editor.mode.currentData() in ('erase', 'precise') and not self.editor.busy and self.selection_start is None:
            point = self.mapToScene(event.position().toPoint())
            targets = self.editor.characters if self.editor.mode.currentData() == 'precise' else self.editor.spans
            span = nearest_span(point.x(), point.y(), targets, 0 if self.editor.mode.currentData() == 'precise' else 3 / self.zoom)
            self.clear_erase_hover()
            if span:
                x0, y0, x1, y1 = span['bbox']
                pen = QPen(QColor('#d83b01'), 1, Qt.PenStyle.DashLine)
                pen.setCosmetic(True)
                self.erase_hover = self.scene().addRect(QRectF(x0, y0, x1 - x0, y1 - y0), pen, QColor(216, 59, 1, 25))
                self.erase_hover.setZValue(15)
                self.erase_hover.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            return
        if self.selection_start is not None:
            point = self.mapToScene(event.position().toPoint())
            self.selection.setRect(QRectF(self.selection_start, point).normalized().intersected(self.editor.page_rect))
            if self.editor.mode.currentData() == 'precise':
                self.select_characters(self.selection.rect(), point)
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if self.pan is not None:
            self.pan = None
            self.unsetCursor()
            return
        if self.selection_start is not None:
            rect = self.selection.rect()
            self.scene().removeItem(self.selection)
            self.selection, self.selection_start = None, None
            if self.editor.mode.currentData() == 'precise':
                self.select_characters(rect, self.mapToScene(event.position().toPoint()))
            elif rect.width() > 2 and rect.height() > 2:
                self.editor.delete_selection(rect)
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if self.editor.mode.currentData() == 'precise' and not self.editor.busy and event.button() == Qt.MouseButton.LeftButton:
            if self.selection is not None:
                self.scene().removeItem(self.selection)
                self.selection, self.selection_start = None, None
            point = self.mapToScene(event.position().toPoint())
            self.show_character_selection(word_at(point.x(), point.y(), self.editor.characters))
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def clear_character_selection(self):
        for item in self.precise_items:
            self.scene().removeItem(item)
        self.precise_items = []
        self.selected_chars = []
        if hasattr(self.editor, 'delete_chars_action'):
            self.editor.delete_chars_action.setEnabled(False)

    def select_characters(self, rect, point):
        if rect.width() < 2 and rect.height() < 2:
            char = nearest_span(point.x(), point.y(), self.editor.characters, 0)
            chars = [char] if char else []
        else:
            chars = [c for c in self.editor.characters if rect.contains(
                QPointF((c['bbox'][0] + c['bbox'][2]) / 2, (c['bbox'][1] + c['bbox'][3]) / 2))]
        self.show_character_selection(chars)

    def show_character_selection(self, chars):
        ids = [c['id'] for c in chars]
        if ids == self.selected_chars:
            return
        self.clear_character_selection()
        self.selected_chars = ids
        pen = QPen(QColor('#d83b01'), 1)
        pen.setCosmetic(True)
        path = QPainterPath()
        for char in chars:
            x0, y0, x1, y1 = char['bbox']
            path.addRect(QRectF(x0, y0, x1 - x0, y1 - y0))
        if chars:
            item = self.scene().addPath(path, pen, QColor(216, 59, 1, 55))
            item.setZValue(16)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.precise_items.append(item)
        self.editor.delete_chars_action.setEnabled(bool(ids) and not self.editor.busy)
        text = ''.join(c['text'] for c in chars)[:80]
        self.editor.statusBar().showMessage(f'已选 {len(ids)} 个字符：{text}  — 点击“删除所选”或按 Delete；Esc 取消。')

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace) and self.selected_chars:
            self.editor.delete_characters()
            event.accept()
            return
        super().keyPressEvent(event)

    def leaveEvent(self, event):
        self.clear_erase_hover()
        super().leaveEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        paths = [url.toLocalFile() for url in event.mimeData().urls()]
        if len(paths) == 1 and Path(paths[0]).suffix.lower() in ('.pdf', '.lpdf'):
            self.editor.open_pdf(paths[0])
            event.acceptProposedAction()
        else:
            self.editor.statusBar().showMessage('请每次拖入一个 PDF 文件。', 5000)


class Editor(QMainWindow):
    FALLBACK_TILE_LIMIT = 16 * 1024 * 1024

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'轻简 PDF {__version__} · Qt 版 · 自用')
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1280, available.width() - 60), min(860, available.height() - 60))
        self.setMinimumSize(min(900, max(480, available.width() - 60)),
                            min(640, max(360, available.height() - 60)))
        self.ocr_dialog = None
        self.path = None
        self.last_saved_path = None
        self.index = 0
        self.count = 0
        self.revision = 0
        self.epoch = 0
        self.busy = False
        self.dirty = False
        self.spans = []
        self.characters = []
        self.objects = []
        self.ruling_lines = []
        self.editing_id = None
        self.can_undo = False
        self.can_redo = False
        self.page_rect = QRectF()
        self.draft = None
        self.erase_selection = None
        self.erase_color = (1.0, 1.0, 1.0)
        self.erase_auto_color = True
        self.erase_color_ready = False
        self.background_version = 0
        self.picking_background = False
        self.background_timer = QTimer(self)
        self.background_timer.setSingleShot(True)
        self.background_timer.setInterval(150)
        self.background_timer.timeout.connect(self.request_background)
        self.guides = []
        self.color = (0.0, 0.0, 0.0)
        self.fonts = windows_fonts()
        if not any(name in self.fonts for name in ('微软雅黑', '宋体', '黑体', '楷体', '仿宋')):
            self.fonts = {'内置中文字体': None, **self.fonts}
        else:
            self.fonts['内置中文字体'] = None
        self.preview_version = 0
        self.tile_cache = OrderedDict()
        self.cache_bytes = 0
        self.tile_items = {}
        self.fallback_tiles = []
        self.wanted = set()
        self.tile_group = None
        self.view = PdfView(self)
        self.setCentralWidget(self.view)
        self.tile_timer = QTimer(self)
        self.tile_timer.setSingleShot(True)
        self.tile_timer.setInterval(80)
        self.tile_timer.timeout.connect(self.schedule_tiles)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(100)
        self.preview_timer.timeout.connect(self.request_preview)
        self.view.viewport_changed.connect(self.viewport_updated)
        self.recovery_path = None
        self.recovery_pending = False
        self.recovery_stamp = None
        self.pending_recovery_draft = None
        self.recovery_timer = QTimer(self)
        self.recovery_timer.setInterval(30000)
        self.recovery_timer.timeout.connect(self.autosave)
        self.build_toolbar()
        self.build_panel()
        self.build_navigation()
        self.client = PdfClient(self)
        self.client.result.connect(self.on_result)
        self.client.failed.connect(self.worker_failed)
        self.restart_action.setEnabled(True)
        self.statusBar().showMessage('拖入 PDF 开始。滚轮缩放，中键拖动平移；原文基线吸附已开启。')
        welcome = self.view.scene().addText('拖入 PDF，开始编辑\n\n原文基线吸附 · 样式取样 · 独立进程渲染')
        welcome.setDefaultTextColor(QColor('#526174'))
        welcome.setPos(60, 70)

    def action(self, toolbar, title, slot, shortcut=None):
        action = QAction(title, self)
        action.triggered.connect(slot)
        if shortcut:
            action.setShortcut(shortcut)
        toolbar.addAction(action)
        return action

    def build_toolbar(self):
        bar = QToolBar('文件与页面', self)
        bar.setMovable(False)
        self.addToolBar(bar)
        self.open_action = self.action(bar, '打开文件', lambda: self.open_pdf(), 'Ctrl+O')
        self.save_action = self.action(bar, '另存为', self.save, 'Ctrl+S')
        self.project_action = self.action(bar, '保存工程', self.save_project, 'Ctrl+Shift+S')
        self.recover_action = self.action(bar, '打开恢复副本', self.open_recovery)
        self.restart_action = self.action(bar, '重启处理进程', self.restart_worker)
        self.restart_action.setEnabled(False)
        self.undo_action = self.action(bar, '撤销', self.undo, 'Ctrl+Z')
        self.redo_action = self.action(bar, '重做', self.redo, 'Ctrl+Y')
        self.redo_action.setShortcuts(['Ctrl+Y', 'Ctrl+Shift+Z'])
        self.undo_action.setEnabled(False)
        self.redo_action.setEnabled(False)
        bar.addSeparator()
        self.prev_action = self.action(bar, '上一页', lambda: self.turn(-1))
        self.page_label = QLabel('  尚未打开  ')
        bar.addWidget(self.page_label)
        self.next_action = self.action(bar, '下一页', lambda: self.turn(1))
        self.action(bar, '跳转页码', self.prompt_page, 'Ctrl+G')
        self.action(bar, '适合页面', self.fit_page, 'Ctrl+0')
        self.action(bar, '−', lambda: self.view.set_zoom(self.view.zoom / 1.2))
        self.zoom_label = QLabel('100%')
        bar.addWidget(self.zoom_label)
        self.action(bar, '+', lambda: self.view.set_zoom(self.view.zoom * 1.2))
        self.addToolBarBreak()
        editing = QToolBar('编辑工具', self)
        editing.setMovable(False)
        self.addToolBar(editing)
        editing.addWidget(QLabel('工具  '))
        self.mode = PropertyComboBox()
        for label, value in [('添加文字', 'add'), ('表格单元格填字', 'cell'), ('编辑新增文字', 'edit'), ('精细删除（按字符）', 'precise'), ('框选删除', 'delete'), ('擦除图片区域', 'erase_image'), ('OCR 转为文字', 'ocr'), ('点选删除文字', 'erase'), ('取样原文样式', 'sample'), ('平移页面', 'pan')]:
            self.mode.addItem(label, value)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        editing.addWidget(self.mode)
        self.action(editing, '编辑新增文字', lambda: self.mode.setCurrentIndex(self.mode.findData('edit')))
        self.action(editing, '精细删除', lambda: self.mode.setCurrentIndex(self.mode.findData('precise')))
        self.delete_chars_action = self.action(editing, '删除所选', self.delete_characters)
        self.delete_chars_action.setEnabled(False)
        self.delete_chars_action.setToolTip('预览红色字符选区后点击删除；在页面上也可按 Delete，Esc 取消。')
        self.action(editing, '框选删除', lambda: self.mode.setCurrentIndex(self.mode.findData('delete')))
        self.action(editing, '图片擦除 / 填底色', lambda: self.mode.setCurrentIndex(self.mode.findData('erase_image')))
        self.action(editing, '点选删除', lambda: self.mode.setCurrentIndex(self.mode.findData('erase')))
        self.snap = QCheckBox('吸附原文基线 / 边缘（Alt 暂停）')
        self.snap.setChecked(True)
        editing.addWidget(self.snap)
        editing.addSeparator()
        self.view.setToolTip('滚轮缩放 · 中键平移 · Shift+滚轮滚动')

    def build_navigation(self):
        self.thumbnail_identity = None
        self.thumbnail_start = 0
        self.thumbnail_generation = 0
        self.thumbnail_timer = QTimer(self)
        self.thumbnail_timer.setSingleShot(True)
        self.thumbnail_timer.setInterval(160)
        self.thumbnail_timer.timeout.connect(self.schedule_thumbnails)
        self.pages_dock = QDockWidget('页面导航', self)
        self.pages_dock.setMinimumWidth(170)
        body = QWidget()
        layout = QVBoxLayout(body)
        row = QHBoxLayout()
        self.page_input = QSpinBox()
        self.page_input.setRange(1, 1)
        self.page_input.setPrefix('第 ')
        self.page_input.setSuffix(' 页')
        go = QPushButton('跳转')
        go.clicked.connect(lambda: self.go_to_page(self.page_input.value() - 1))
        row.addWidget(self.page_input)
        row.addWidget(go)
        layout.addLayout(row)
        self.page_list = QListWidget()
        self.page_list.setIconSize(QSize(130, 170))
        self.page_list.setUniformItemSizes(True)
        self.page_list.viewport().installEventFilter(self)
        self.page_list.itemClicked.connect(lambda item: self.go_to_page(item.data(Qt.ItemDataRole.UserRole)))
        self.page_list.verticalScrollBar().valueChanged.connect(lambda _: self.thumbnail_timer.start())
        layout.addWidget(self.page_list)
        groups = QHBoxLayout()
        self.previous_group = QPushButton('前 20 页')
        self.next_group = QPushButton('后 20 页')
        self.previous_group.clicked.connect(lambda: self.show_thumbnail_group(self.thumbnail_start - 20))
        self.next_group.clicked.connect(lambda: self.show_thumbnail_group(self.thumbnail_start + 20))
        groups.addWidget(self.previous_group)
        groups.addWidget(self.next_group)
        layout.addLayout(groups)
        self.pages_dock.setWidget(body)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.pages_dock)
        self.pages_dock.hide()
        self.pages_dock.visibilityChanged.connect(self.navigation_visibility)
        self.findChildren(QToolBar)[0].addAction(self.pages_dock.toggleViewAction())

    def eventFilter(self, watched, event):
        if hasattr(self, "page_list") and watched is self.page_list.viewport() and event.type() == QEvent.Type.Resize:
            self.thumbnail_timer.start()
        return super().eventFilter(watched, event)

    def navigation_visibility(self, visible):
        if visible:
            self.thumbnail_timer.start()
        elif hasattr(self, 'client'):
            self.client.thumbnails = []

    def prompt_page(self):
        if self.busy or not self.path:
            return
        number, ok = QInputDialog.getInt(self, '跳转页码', f'页码（1–{self.count}）', self.index + 1, 1, self.count)
        if ok:
            self.go_to_page(number - 1)

    def show_thumbnail_group(self, start):
        if not self.count or not 0 <= start < self.count:
            return
        self.thumbnail_start = start // 20 * 20
        self.thumbnail_generation += 1
        self.client.thumbnails = []
        self.page_list.clear()
        for index in range(self.thumbnail_start, min(self.thumbnail_start + 20, self.count)):
            item = QListWidgetItem(f'第 {index + 1} 页')
            item.setData(Qt.ItemDataRole.UserRole, index)
            item.setSizeHint(QSize(145, 185))
            self.page_list.addItem(item)
            if index == self.index:
                self.page_list.setCurrentItem(item)
        self.previous_group.setEnabled(self.thumbnail_start > 0)
        self.next_group.setEnabled(self.thumbnail_start + 20 < self.count)
        self.thumbnail_timer.start()

    def refresh_navigation(self):
        identity = (str(self.path), self.revision, self.count)
        if identity != self.thumbnail_identity or not self.thumbnail_start <= self.index < self.thumbnail_start + 20:
            self.thumbnail_identity = identity
            self.show_thumbnail_group(self.index // 20 * 20)
        self.page_input.setRange(1, max(1, self.count))
        self.page_input.setValue(self.index + 1)
        if self.page_list.count():
            self.page_list.setCurrentRow(self.index - self.thumbnail_start)
            self.page_list.scrollToItem(self.page_list.currentItem())
        self.thumbnail_timer.start()

    def schedule_thumbnails(self):
        if not self.path or self.busy or not self.pages_dock.isVisible() or self.client.dead:
            self.client.thumbnails = []
            return
        requests = []
        for row in range(self.page_list.count()):
            item = self.page_list.item(row)
            if not item.icon().isNull() or item.data(Qt.ItemDataRole.UserRole + 1):
                continue
            if not self.page_list.visualItemRect(item).intersects(self.page_list.viewport().rect()):
                continue
            request = dict(kind='thumbnail', epoch=self.epoch, revision=self.revision,
                           index=item.data(Qt.ItemDataRole.UserRole), generation=self.thumbnail_generation)
            active = self.client.active
            if not active or any(active.get(key) != value for key, value in request.items()):
                requests.append(request)
        self.client.thumbnails = requests
        self.client.dispatch()

    def receive_thumbnail(self, response):
        request = response['request']
        if request.get('generation') != self.thumbnail_generation or request.get('revision') != self.revision:
            return
        row = request['index'] - self.thumbnail_start
        if not 0 <= row < self.page_list.count():
            return
        item = self.page_list.item(row)
        if 'error' in response:
            item.setToolTip('缩略图未能生成：' + response['error'])
            item.setData(Qt.ItemDataRole.UserRole + 1, True)
        elif not response['data'].get('stale'):
            item.setIcon(QIcon(decode_pixmap(response['data']['image'])))
        self.thumbnail_timer.start()

    def build_panel(self):
        dock = QDockWidget('文字属性', self)
        dock.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)
        dock.setMinimumWidth(310)
        body = QWidget()
        layout = QVBoxLayout(body)
        self.text_input = QPlainTextEdit()
        self.text_input.setPlaceholderText('输入文字，再点击页面定位。\n也可先用“取样原文样式”。')
        self.text_input.setMaximumHeight(145)
        self.text_input.textChanged.connect(self.content_changed)
        layout.addWidget(self.text_input)
        form = QFormLayout()
        self.font_combo = PropertyComboBox()
        self.font_combo.addItems(list(self.fonts))
        self.font_combo.currentTextChanged.connect(self.content_changed)
        form.addRow('字体', self.font_combo)
        import_button = QPushButton('选择字体文件…')
        import_button.clicked.connect(self.import_font)
        form.addRow('', import_button)
        self.size = PropertySpinBox()
        self.size.setRange(6, 96)
        self.size.setValue(14)
        self.size.setSuffix(' pt')
        self.size.valueChanged.connect(self.content_changed)
        form.addRow('字号', self.size)
        self.line_spacing = PropertySpinBox()
        self.line_spacing.setRange(0, 1000)
        self.line_spacing.setDecimals(2)
        self.line_spacing.setSuffix(' pt')
        self.line_spacing.setSpecialValueText('自动')
        self.line_spacing.setToolTip('相邻行基线之间的距离；0 为字体默认行距。取样时尝试读取同列相邻行。')
        self.line_spacing.valueChanged.connect(self.content_changed)
        form.addRow('行距', self.line_spacing)
        self.text_align = PropertyComboBox()
        for label, value in [('左对齐', 0), ('居中', 1), ('右对齐', 2)]:
            self.text_align.addItem(label, value)
        self.text_align.currentIndexChanged.connect(self.content_changed)
        self.text_align.setToolTip('对齐文字框内的各行，不移动文字框；取样原文样式后默认左对齐。')
        form.addRow('框内对齐', self.text_align)
        self.bold = QCheckBox('加粗')
        self.bold.toggled.connect(self.content_changed)
        form.addRow('', self.bold)
        self.color_button = QPushButton('文字颜色  ■')
        self.color_button.clicked.connect(self.choose_color)
        form.addRow('颜色', self.color_button)
        self.coords = {}
        for key, label, value in [('x', '文字框左侧 X', 40), ('baseline', '首行基线 Y', 60), ('width', '文字框宽', 260), ('height', '文字框高', 90)]:
            field = PropertySpinBox()
            field.setRange(0 if key in ('x', 'baseline') else 12, 20000)
            field.setDecimals(2)
            field.setValue(value)
            field.setSuffix(' pt')
            field.valueChanged.connect(lambda value, name=key: self.geometry_changed(name))
            self.coords[key] = field
            form.addRow(label, field)
        layout.addLayout(form)
        self.sample_label = QLabel('取样会读取原文字号、颜色、粗细和字体名称。')
        self.sample_label.setWordWrap(True)
        layout.addWidget(self.sample_label)
        layout.addStretch()
        self.recovery_toggle = QCheckBox('自动恢复副本（约 30 秒）')
        self.recovery_toggle.setToolTip('选择本地目录，保存当前文档和已放置的草稿；保留原有 PDF 加密。每次打开文件后需重新启用。')
        self.recovery_toggle.toggled.connect(self.toggle_recovery)
        layout.addWidget(self.recovery_toggle)
        self.recovery_label = QLabel('尚未启用自动恢复副本。')
        self.recovery_label.setWordWrap(True)
        layout.addWidget(self.recovery_label)
        hint = QLabel('框内拖动，边角调整大小。\n方向键微调，Shift+方向键移动 10 pt。\n虚线标示首行文字基线，不是文字框顶边。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        self.properties_scroll = scroll
        panel = QWidget()
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        panel_layout.addWidget(scroll, 1)
        footer_widget = QWidget()
        footer_layout = QVBoxLayout(footer_widget)
        self.background_controls = QWidget()
        color_layout = QHBoxLayout(self.background_controls)
        color_layout.setContentsMargins(0,0,0,0)
        self.background_auto = QPushButton('自动底色')
        self.background_auto.clicked.connect(self.use_auto_background)
        self.background_pick = QPushButton('页面取色')
        self.background_pick.clicked.connect(self.begin_background_pick)
        self.background_color = QPushButton('底色…')
        self.background_color.clicked.connect(self.choose_background_color)
        for button in (self.background_auto,self.background_pick,self.background_color):
            color_layout.addWidget(button)
        self.background_controls.hide()
        footer_layout.addWidget(self.background_controls)
        self.preview_label = QLabel('点击页面放置文字；对齐时出现蓝色参考线。')
        self.preview_label.setWordWrap(True)
        self.preview_label.setMaximumHeight(64)
        footer_layout.addWidget(self.preview_label)
        self.apply_button = QPushButton('应用文字  Ctrl+Enter')
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        footer_layout.addWidget(self.apply_button)
        self.cancel_button = QPushButton('取消预览  Esc')
        self.cancel_button.clicked.connect(self.cancel)
        footer_layout.addWidget(self.cancel_button)
        panel_layout.addWidget(footer_widget)
        dock.setWidget(panel)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, dock)
        apply_action = QAction(self)
        apply_action.setShortcut('Ctrl+Return')
        apply_action.triggered.connect(self.apply)
        self.addAction(apply_action)
        cancel_action = QAction(self)
        cancel_action.setShortcut('Esc')
        cancel_action.triggered.connect(self.cancel)
        self.addAction(cancel_action)
        bold_action = QAction(self)
        bold_action.setShortcut('Ctrl+B')
        bold_action.triggered.connect(lambda: self.bold.setChecked(not self.bold.isChecked()))
        self.addAction(bold_action)

    def set_busy(self, value):
        self.busy = value
        for control in (self.open_action, self.save_action, self.project_action, self.recover_action, self.undo_action, self.redo_action, self.prev_action, self.next_action):
            control.setEnabled(not value)
        self.undo_action.setEnabled(not value and self.can_undo)
        self.redo_action.setEnabled(not value and self.can_redo)
        self.delete_chars_action.setEnabled(not value and bool(self.view.selected_chars))
        self.pages_dock.widget().setEnabled(not value and bool(self.path))
        self.prev_action.setEnabled(not value and self.index > 0)
        self.next_action.setEnabled(not value and self.index + 1 < self.count)
        self.mode.setEnabled(not value)
        self.background_controls.setEnabled(not value)
        self.recovery_toggle.setEnabled(not value)
        self.apply_button.setEnabled(not value and (self.erase_selection is not None and self.erase_color_ready or self.draft is not None and self.draft.valid))
        if self.erase_selection:
            self.erase_selection.setEnabled(not value)
        if self.draft:
            self.draft.setEnabled(not value)
        for control in (self.text_input, self.font_combo, self.size, self.line_spacing, self.text_align, self.bold, *self.coords.values()):
            control.setEnabled(not value)

    def discard(self):
        if self.busy and not self.client.dead:
            self.statusBar().showMessage('正在处理文件，请稍后。', 5000)
            return False
        if self.dirty or self.draft or self.erase_selection:
            return QMessageBox.question(self, '未保存的修改', '是否放弃当前未保存的修改和待确认预览？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        return True

    def open_pdf(self, path=None):
        if not self.discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, '打开 PDF 或编辑工程', '', 'PDF / 编辑工程 (*.pdf *.lpdf);;PDF (*.pdf);;编辑工程 (*.lpdf)')
        if not path:
            return
        if self.client.dead:
            self.reset_worker()
        self.epoch += 1
        self.set_busy(True)
        self.statusBar().showMessage('正在后台打开 PDF…')
        self.client.command('open', path=str(path), epoch=self.epoch)

    def worker_failed(self, message):
        if self.ocr_dialog is not None:
            self.ocr_dialog.reject()
        self.stop_recovery()
        self.pending_recovery_draft = None
        self.tile_timer.stop()
        self.preview_timer.stop()
        self.epoch += 1
        self.set_busy(True)
        self.open_action.setEnabled(True)
        self.recover_action.setEnabled(True)
        self.restart_action.setEnabled(True)
        self.text_input.setEnabled(True)
        self.text_input.setReadOnly(True)
        note = message + '\n可点击“重启处理进程”重新打开最近另存的文件或原稿。未保存的修改无法恢复；右侧文字仍可复制。若已启用恢复副本，可打开最近一次成功保存的副本。保存请求可能已经写出，请另行核对输出文件。'
        self.statusBar().showMessage(note.replace('\n', ' '))
        QMessageBox.critical(self, 'PDF 处理进程已停止', note)

    def reset_worker(self):
        self.stop_recovery()
        self.pending_recovery_draft = None
        self.tile_timer.stop()
        self.preview_timer.stop()
        old = self.client
        old.result.disconnect(self.on_result)
        old.failed.disconnect(self.worker_failed)
        old.close()
        old.deleteLater()
        self.epoch += 1
        self.cancel(local=True)
        self.view.clear_erase_hover()
        self.view.scene().clear()
        self.path = None
        self.last_saved_path = None
        self.page_rect = QRectF()
        self.spans, self.characters, self.objects = [], [], []
        self.ruling_lines = []
        self.tile_cache.clear()
        self.tile_items, self.wanted = {}, set()
        self.fallback_tiles = []
        self.tile_group = None
        self.cache_bytes = 0
        self.can_undo = self.can_redo = self.dirty = False
        self.index = self.count = self.revision = 0
        self.thumbnail_timer.stop()
        self.thumbnail_generation += 1
        self.thumbnail_identity = None
        self.page_list.clear()
        self.client = PdfClient(self)
        self.client.result.connect(self.on_result)
        self.client.failed.connect(self.worker_failed)
        self.restart_action.setEnabled(True)
        self.text_input.setReadOnly(False)
        self.restart_action.setEnabled(True)
        self.set_busy(False)
        self.page_label.setText('  尚未打开  ')
        self.update_title()

    def restart_worker(self):
        if not self.client.dead:
            answer = QMessageBox.question(self, '停止并重启处理进程',
                '这会中断当前操作并放弃未保存修改和草稿。保存请求可能已经写出，请另行核对输出文件。\n'
                '将重新打开最近另存的文件或原稿；也可取消后打开恢复副本。是否继续？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                return
            self.client.failure('用户手动停止并重启工作进程。', notify=False)
        elif not self.discard():
            return
        target = self.last_saved_path or self.path
        self.reset_worker()
        if target:
            self.open_pdf(str(target))
        else:
            self.statusBar().showMessage('处理进程已重启，请打开 PDF。')

    def on_result(self, response):
        request = response['request']
        kind = request['kind']
        if self.client.dead:
            return
        if kind == 'autosave':
            self.on_autosave(response)
            return
        if request.get('epoch') != self.epoch:
            return
        if kind == 'ocr_preview':
            if self.ocr_dialog is not None:
                self.ocr_dialog.receive_preview(response)
            return
        if kind == 'ocr_snapshot':
            self.set_busy(False)
            if 'error' in response:
                QMessageBox.warning(self, 'OCR 未开始', response['error'])
            else:
                self.review_ocr(response['data'])
            return
        if kind == 'thumbnail':
            self.receive_thumbnail(response)
            return
        if kind == 'open' and 'error' not in response and not response.get('data', {}).get('password_required'):
            self.thumbnail_identity = None
            self.last_saved_path = None
            self.stop_recovery()
            self.pending_recovery_draft = None
        if kind == 'sample_background':
            if request.get('version') != self.background_version or self.erase_selection is None:
                return
            if 'error' in response:
                self.erase_color_ready = False
                self.apply_button.setEnabled(False)
                self.preview_label.setText(response['error'])
            else:
                self.erase_color = tuple(response['data']['color'])
                self.erase_color_ready = True
                self.refresh_background_label()
            return
        if 'error' in response:
            if kind == 'preview':
                if request.get('version') == self.preview_version and self.draft:
                    self.draft.valid = False
                    self.draft.pixmap = None
                    self.draft.update()
                    self.apply_button.setEnabled(False)
                    self.preview_label.setText(response['error'])
                    self.preview_label.setToolTip(response['error'])
            elif kind == 'tile':
                self.statusBar().showMessage('该区域渲染失败：' + response['error'], 6000)
            else:
                self.set_busy(False)
                QMessageBox.warning(self, '操作未完成', response['error'])
                if self.path and kind in ('insert', 'delete', 'delete_chars', 'erase_image', 'undo', 'redo', 'open', 'ocr_convert'):
                    self.client.command('page', index=self.index, epoch=self.epoch)
            return
        data = response['data']
        if data.get('password_required'):
            password, ok = QInputDialog.getText(self, '加密 PDF', '请输入密码：', QLineEdit.EchoMode.Password)
            if ok:
                self.client.command('open', path=request['path'], password=password, epoch=self.epoch)
            else:
                self.set_busy(False)
            return
        if kind == 'begin_edit':
            self.load_page(data)
            pending, self.pending_recovery_draft = self.pending_recovery_draft, None
            self.restore_object_draft(dict(id=pending['editing_id'], spec=pending['spec'], offset=pending['offset']) if pending else data['edit_object'])
            if pending:
                self.statusBar().showMessage('已恢复重新编辑中的草稿；应用替换，Esc 保留原文字。', 10000)
        elif kind in ('open', 'page', 'insert', 'delete', 'delete_chars', 'erase_image', 'undo', 'redo', 'update_object', 'cancel_edit', 'ocr_convert'):
            retired_objects = kind in ('delete', 'delete_chars', 'erase_image') and bool({o['id'] for o in self.objects} - {o['id'] for o in data.get('objects', [])})
            self.load_page(data, fit=kind in ('open', 'page'))
            if kind == 'open' and data.get('recovery'):
                self.restore_recovery(data.get('recovery_draft'))
            if retired_objects:
                self.statusBar().showMessage('已删除文字。与删除范围相交或连锁重叠的文字框已转为普通文字；未受影响的文字框仍可编辑。撤销可恢复。', 10000)
        elif kind == 'preview':
            if self.draft and request['version'] == self.preview_version:
                baseline = self.draft.y() + (data['baseline_offset'] if getattr(self.draft, 'anchor_top', False) else self.draft.offset)
                self.draft.anchor_top = False
                self.draft.offset = data['baseline_offset']
                self.draft.setY(max(0, min(baseline - self.draft.offset, self.page_rect.height() - self.draft.h)))
                self.draft.pixmap = decode_pixmap(data['image'])
                self.draft.valid = True
                self.draft.update()
                self.sync_geometry()
                self.apply_button.setEnabled(not self.busy)
                self.preview_label.setText('实际 PDF 排版预览。蓝色虚线是首行基线。')
                self.preview_label.setToolTip('')
        elif kind == 'tile' and not data.get('stale'):
            key = tuple(request['key'])
            pixmap = decode_pixmap(data['image'])
            data = {k: v for k, v in data.items() if k != 'image'}
            cost = pixmap.width() * pixmap.height() * 4
            if key in self.tile_cache:
                self.cache_bytes -= self.tile_cache.pop(key)[2]
            self.tile_cache[key] = (pixmap, data, cost)
            self.cache_bytes += cost
            while self.cache_bytes > 64 * 1024 * 1024 and len(self.tile_cache) > 1:
                _, (_, _, removed) = self.tile_cache.popitem(last=False)
                self.cache_bytes -= removed
            if key in self.wanted:
                self.show_tile(key, pixmap, data)
                self.finish_tile_transition()
        elif kind in ('save', 'save_project'):
            self.last_saved_path = Path(data['saved'])
            self.dirty = False
            self.set_busy(False)
            self.update_title()
            self.statusBar().showMessage('已保存：' + data['saved'], 10000)
            self.tile_timer.start()

    def load_page(self, data, fit=False):
        self.view.clear_erase_hover()
        self.cancel(local=True)
        self.path = Path(data['path'])
        self.index, self.count, self.revision = data['index'], data['count'], data['revision']
        self.dirty = data['dirty']
        self.spans = data['spans']
        self.characters = data.get('characters', [])
        self.objects = data.get('objects', [])
        self.ruling_lines = data.get('ruling_lines', [])
        self.can_undo, self.can_redo = data['can_undo'], data.get('can_redo', False)
        self.page_rect = QRectF(0, 0, data['width'], data['height'])
        scene = self.view.scene()
        scene.clear()
        self.guides = []
        self.tile_items = {}
        self.fallback_tiles = []
        self.wanted = set()
        self.tile_cache.clear()
        self.cache_bytes = 0
        self.tile_group = None
        scene.addRect(self.page_rect, QPen(Qt.PenStyle.NoPen), QColor('white')).setZValue(-2)
        thumbnail = scene.addPixmap(decode_pixmap(data['thumbnail']))
        thumbnail.setScale(1 / data['scale'])
        thumbnail.setZValue(-1)
        thumbnail.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        scene.setSceneRect(self.page_rect.adjusted(-30, -30, 30, 30))
        self.page_label.setText(f'  {self.index + 1} / {self.count} 页  ')
        self.refresh_navigation()
        self.set_busy(False)
        self.undo_action.setEnabled(data['can_undo'])
        self.update_title()
        if fit:
            self.fit_page()
        self.tile_timer.start()
        message = '滚轮缩放，中键平移；点击原文附近可吸附到同一基线。'
        if not self.spans:
            message = '本页没有可提取文字（可能为扫描件）；可添加文字，无法吸附，擦除请选“擦除图片区域”。'
        self.statusBar().showMessage(message)

    def update_title(self):
        self.setWindowTitle(f'{"* " if self.dirty else ""}{self.path.name if self.path else "轻简 PDF"} · {__version__} · Qt 版 · 自用')

    def viewport_updated(self):
        # A debounce must not keep dispatching queued work for the old viewport.
        if hasattr(self, 'client'):
            self.client.tiles = []
        self.wanted = set()
        self.tile_timer.start()

    def clear_fallback_tiles(self):
        for item in self.fallback_tiles:
            self.view.scene().removeItem(item)
        self.fallback_tiles = []

    def finish_tile_transition(self):
        if self.wanted and self.wanted.issubset(self.tile_items):
            self.clear_fallback_tiles()

    def schedule_tiles(self):
        if not self.path or self.busy:
            return
        scale = math.ceil(self.view.zoom * self.view.devicePixelRatioF() * 4) / 4
        scale = min(10, max(0.25, scale))
        group = (self.epoch, self.revision, self.index, scale)
        if group != self.tile_group:
            # Keep at most one bounded previous layer until the new view is sharp.
            cost = sum(item.pixmap().width() * item.pixmap().height() * 4 for item in self.tile_items.values())
            retain = not self.fallback_tiles and cost <= self.FALLBACK_TILE_LIMIT
            for item in self.tile_items.values():
                if retain:
                    item.setZValue(-0.5)
                    self.fallback_tiles.append(item)
                else:
                    self.view.scene().removeItem(item)
            self.tile_items = {}
            self.tile_group = group
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect().intersected(self.page_rect)
        if visible.isEmpty():
            self.wanted = set()
            self.client.replace_tiles([])
            self.clear_fallback_tiles()
            return
        step = 512 / scale
        requests = []
        self.wanted = set()
        for row in range(max(0, math.floor(visible.top() / step)), math.ceil(visible.bottom() / step)):
            for col in range(max(0, math.floor(visible.left() / step)), math.ceil(visible.right() / step)):
                key = group + (col, row)
                self.wanted.add(key)
                if key in self.tile_items:
                    continue
                if key in self.tile_cache:
                    pixmap, data, _ = self.tile_cache[key]
                    self.tile_cache.move_to_end(key)
                    self.show_tile(key, pixmap, data)
                else:
                    clip = [col * step, row * step, min((col + 1) * step, self.page_rect.width()),
                            min((row + 1) * step, self.page_rect.height())]
                    requests.append(dict(kind='tile', epoch=self.epoch, revision=self.revision, index=self.index,
                                         scale=scale, clip=clip, key=key))
        for key in list(self.tile_items):
            if key not in self.wanted:
                self.view.scene().removeItem(self.tile_items.pop(key))
        center = visible.center()
        requests.sort(key=lambda r: (r['clip'][0] - center.x()) ** 2 + (r['clip'][1] - center.y()) ** 2)
        self.client.replace_tiles(requests)
        self.finish_tile_transition()

    def show_tile(self, key, pixmap, data):
        if key in self.tile_items:
            return
        item = self.view.scene().addPixmap(pixmap)
        item.setScale(1 / data['scale'])
        item.setPos(data['x'] / data['scale'], data['y'] / data['scale'])
        item.setZValue(0)
        item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.tile_items[key] = item

    def fit_page(self):
        if self.path:
            self.view.resetTransform()
            self.view.zoom = 1
            self.view.set_zoom(min((self.view.viewport().width() - 60) / self.page_rect.width(),
                                   (self.view.viewport().height() - 60) / self.page_rect.height()))
            self.view.centerOn(self.page_rect.center())

    def mode_changed(self):
        if hasattr(self, 'background_controls'):
            self.background_controls.setVisible(self.mode.currentData() == 'erase_image')
        self.view.clear_erase_hover()
        self.view.clear_character_selection()
        if hasattr(self, 'text_input') and (self.erase_selection is not None or self.editing_id is not None or self.mode.currentData() in ('delete', 'erase', 'precise', 'edit', 'cell', 'erase_image')):
            self.cancel()
        self.draw_guides([])
        if self.mode.currentData() == 'cell':
            self.statusBar().showMessage('表格填字：输入文字后点击有完整直线边框的单元格，自动留出 4 pt 内边距。扫描表格不支持。')
        elif self.mode.currentData() == 'edit':
            self.statusBar().showMessage('点击新增或工程中恢复的文字框，重新修改或移动；应用更新，Esc 取消。')
        elif self.mode.currentData() == 'precise':
            self.statusBar().showMessage('精细删除：单击选字，双击选词段，拖动多选；预览后按 Delete 删除，Esc 取消。')
        elif self.mode.currentData() == 'erase':
            self.statusBar().showMessage('点选删除：红框标出将删除的文字段；点击删除，Ctrl+Z 撤销。')
        elif self.mode.currentData() == 'erase_image':
            self.statusBar().showMessage('擦除图片区域：拖框预览，可移动 / 拉边角调整；点击“确认擦除”后才修改。Esc 取消。')
        elif self.mode.currentData() == 'ocr':
            self.statusBar().showMessage('OCR：框选纯色背景上的横排扫描文字，校对并预览后转为可编辑文字框。')
        elif self.mode.currentData() == 'delete':
            self.statusBar().showMessage('框选删除：拖动框选文字，松开后删除；Ctrl+Z 撤销。')

    def edit_at(self, point):
        if self.busy or not self.path:
            return
        if self.draft:
            self.statusBar().showMessage('请先应用或取消当前文字预览。', 5000)
            return
        candidates = [o for o in reversed(self.objects) if
            QRectF(o['bbox'][0], o['bbox'][1], o['bbox'][2] - o['bbox'][0],
                   o['bbox'][3] - o['bbox'][1]).contains(point)]
        if not candidates:
            self.statusBar().showMessage('此处没有可重新编辑的新增文字。仅支持新增或工程恢复、且未受文字删除影响的文字框。', 7000)
            return
        target = candidates[0]
        if len(candidates) > 1:
            labels = [f"{i + 1}. {o['spec']['text'].replace(chr(10), ' ')[:48]}  (X={o['spec']['x']:.1f}, Y={o['spec']['y']:.1f})"
                      for i, o in enumerate(candidates)]
            label, accepted = QInputDialog.getItem(self, '选择重叠文字框', '此处有多个文字框，请选择要编辑的文字：', labels, 0, False)
            if not accepted:
                return
            target = candidates[labels.index(label)]
        self.epoch += 1
        self.set_busy(True)
        self.client.command('begin_edit', epoch=self.epoch, index=self.index,
                            revision=self.revision, object_id=target['id'])

    def restore_object_draft(self, obj):
        spec = obj['spec']
        self.editing_id = obj['id']
        fontfile = spec.get('fontfile')
        label = next((name for name, path in self.fonts.items() if path == fontfile), None)
        if label is None:
            label = Path(fontfile).name if fontfile else '内置中文字体'
            self.fonts[label] = fontfile
            if self.font_combo.findText(label) < 0:
                self.font_combo.addItem(label)
        self.font_combo.setCurrentText(label)
        self.text_input.setPlainText(spec['text'])
        self.size.setValue(spec['size'])
        self.line_spacing.setValue(spec.get('line_spacing') or 0)
        self.text_align.setCurrentIndex(self.text_align.findData(spec.get('align', 0)))
        self.bold.setChecked(spec.get('bold', False))
        self.color = tuple(spec['color'])
        self.color_button.setStyleSheet('color: ' + QColor.fromRgbF(*self.color).name())
        self.draft = Draft(self, spec['width'], spec['height'])
        self.draft.offset = obj['offset']
        self.draft.setPos(spec['x'], spec['y'])
        self.view.scene().addItem(self.draft)
        self.draft.changed.connect(self.draft_changed)
        self.sync_geometry()
        self.apply_button.setText('应用修改  Ctrl+Enter')
        self.content_changed()
        self.statusBar().showMessage('正在编辑新增文字。旧文字已从底图预览隐藏；应用后替换，Esc 恢复。')

    def spec(self):
        draft = self.draft
        return dict(x=draft.x(), y=draft.y(), width=draft.w, height=draft.h,
                    text=self.text_input.toPlainText(), size=self.size.value(), color=self.color,
                    fontfile=self.fonts.get(self.font_combo.currentText()), bold=self.bold.isChecked(),
                    line_spacing=self.line_spacing.value() or None, align=self.text_align.currentData())

    def place_cell(self, point):
        if self.busy or not self.path:
            return
        bounds = containing_cell(point.x(), point.y(), self.ruling_lines)
        if bounds is None:
            self.statusBar().showMessage('没有找到完整的矢量单元格边框；请用“添加文字”手动定位。', 6000)
            return
        left, top, right, bottom = bounds
        if not self.page_rect.contains(QRectF(left, top, right-left, bottom-top)):
            self.statusBar().showMessage('单元格边框超出可见页面，请手动定位。', 5000)
            return
        if right - left < 20 or bottom - top < 20:
            self.statusBar().showMessage('单元格过小，请手动设置文字框或减小字号。', 5000)
            return
        self.cancel(local=True)
        self.draft = Draft(self, right - left - 8, bottom - top - 8)
        self.draft.setPos(left + 4, top + 4)
        self.draft.anchor_top = True
        self.view.scene().addItem(self.draft)
        self.draft.changed.connect(self.draft_changed)
        self.sync_geometry()
        self.content_changed()
        self.text_input.setFocus()
        self.statusBar().showMessage('已按单元格放置文字框。可修改行距、字号或拉伸；应用前检查预览。')

    def place(self, point):
        if not self.path or self.busy:
            return
        if not self.draft:
            self.draft = Draft(self, min(self.coords['width'].value(), self.page_rect.width()),
                               min(self.coords['height'].value(), self.page_rect.height()))
            self.view.scene().addItem(self.draft)
            self.draft.changed.connect(self.draft_changed)
        draft = self.draft
        x, y = point.x(), point.y() - draft.offset
        guides = []
        if self.snap.isChecked() and not QApplication.keyboardModifiers() & Qt.KeyboardModifier.AltModifier:
            x, y, guides = snap_box(x, y, draft.w, draft.h, draft.offset, self.spans, 9 / self.view.zoom)
        draft.setPos(max(0, min(x, self.page_rect.width() - draft.w)),
                     max(0, min(y, self.page_rect.height() - draft.h)))
        self.draw_guides(guides)
        self.sync_geometry()
        if draft.pixmap is None:
            self.content_changed()
        self.text_input.setFocus()

    def sample(self, point):
        span = nearest_span(point.x(), point.y(), self.spans, 8 / self.view.zoom)
        if not span:
            self.statusBar().showMessage('附近没有可提取的文字。', 5000)
            return
        family = match_font(span['font'], self.fonts)
        if family:
            self.font_combo.setCurrentText(family)
        self.size.setValue(span['size'])
        spacing = sample_line_spacing(span, self.spans)
        self.line_spacing.setValue(spacing or 0)
        self.text_align.setCurrentIndex(0)
        self.bold.setChecked(span['bold'])
        color = span['color']
        self.color = (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)
        self.color_button.setStyleSheet(f'color: #{color:06x}')
        note = f'原字体：{span["font"]}，{span["size"]:.2f} pt。'
        if not family:
            note += f'本机未找到对应字体，使用 {self.font_combo.currentText()}。'
        else:
            note += f'使用本机 {family}。'
        note += f' 估计行距 {spacing:.2f} pt。' if spacing else ' 未检测到同列相邻行，行距使用自动。'
        self.sample_label.setText(note)
        self.mode.setCurrentIndex(0)
        self.content_changed()
        self.draw_guides([('h', span['baseline']), ('v', span['bbox'][0])] if span['horizontal'] else [])
        self.statusBar().showMessage('已取样。点击要添加的位置；靠近原文基线即可吸附。', 7000)

    def content_changed(self, *args):
        if not self.draft:
            return
        self.preview_version += 1
        self.draft.valid = False
        self.draft.pixmap = None
        self.draft.update()
        self.apply_button.setEnabled(False)
        self.preview_label.setText('正在生成文字排版预览…')
        self.preview_timer.start()

    def request_preview(self):
        if self.draft and not self.busy:
            self.client.request_preview(epoch=self.epoch, version=self.preview_version, spec=self.spec(),
                                        scale=max(2, min(4, self.view.zoom * self.view.devicePixelRatioF())))

    def draft_changed(self, resized):
        self.sync_geometry()
        if resized:
            self.content_changed()

    def sync_geometry(self):
        if not self.draft:
            return
        values = dict(x=self.draft.x(), baseline=self.draft.y() + self.draft.offset,
                      width=self.draft.w, height=self.draft.h)
        for key, value in values.items():
            self.coords[key].blockSignals(True)
            self.coords[key].setValue(value)
            self.coords[key].blockSignals(False)

    def geometry_changed(self, key):
        if not self.draft:
            return
        draft = self.draft
        if key in ('width', 'height'):
            width = min(self.coords['width'].value(), self.page_rect.width())
            height = min(self.coords['height'].value(), self.page_rect.height())
            draft.resize_box(width, height)
            self.content_changed()
        draft.setPos(max(0, min(self.coords['x'].value(), self.page_rect.width() - draft.w)),
                     max(0, min(self.coords['baseline'].value() - draft.offset, self.page_rect.height() - draft.h)))
        self.sync_geometry()
        self.draw_guides([])

    def draw_guides(self, guides):
        for item in self.guides:
            self.view.scene().removeItem(item)
        self.guides = []
        pen = QPen(QColor('#078bdf'), 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        for kind, value in guides:
            if kind == 'h':
                item = self.view.scene().addLine(0, value, self.page_rect.width(), value, pen)
            else:
                item = self.view.scene().addLine(value, 0, value, self.page_rect.height(), pen)
            item.setZValue(10)
            item.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            self.guides.append(item)

    def cancel(self, local=False):
        if self.busy and not local:
            return
        if self.erase_selection:
            self.view.scene().removeItem(self.erase_selection)
            self.erase_selection = None
        self.background_timer.stop()
        self.background_version += 1
        self.picking_background = False
        editing_id = self.editing_id
        self.editing_id = None
        self.view.clear_character_selection()
        if self.view.selection is not None:
            self.view.scene().removeItem(self.view.selection)
            self.view.selection, self.view.selection_start = None, None
        self.preview_timer.stop()
        self.client.preview = None
        self.preview_version += 1
        if self.draft:
            self.view.scene().removeItem(self.draft)
            self.draft = None
        self.draw_guides([])
        self.apply_button.setEnabled(False)
        self.preview_label.setToolTip('')
        self.preview_label.setText('点击页面放置文字；虚线是首行基线。')
        self.apply_button.setText('确认擦除  Ctrl+Enter' if self.mode.currentData() == 'erase_image' else '应用文字  Ctrl+Enter')
        if self.mode.currentData() == 'erase_image':
            self.preview_label.setText('拖框预览擦除区域，调整后确认；尚未修改 PDF。')
        if editing_id is not None and not local:
            self.epoch += 1
            self.set_busy(True)
            self.client.command('cancel_edit', epoch=self.epoch, index=self.index)

    def apply(self):
        if self.erase_selection is not None:
            self.confirm_image_erase()
            return
        if self.busy or not self.draft or not self.draft.valid:
            return
        spec = self.spec()
        self.epoch += 1
        self.set_busy(True)
        if self.editing_id is not None:
            self.client.command('update_object', epoch=self.epoch, index=self.index, spec=spec,
                                object_id=self.editing_id, revision=self.revision)
        else:
            self.client.command('insert', epoch=self.epoch, index=self.index, spec=spec)
        self.statusBar().showMessage('正在后台写入文字…')

    def delete_selection(self, rect):
        if self.busy:
            return
        if self.mode.currentData() == 'ocr':
            self.start_ocr(rect)
            return
        if self.mode.currentData() == 'erase_image':
            self.preview_image_erase(rect)
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('delete', epoch=self.epoch, index=self.index, revision=self.revision,
                            rect=[rect.left(), rect.top(), rect.right(), rect.bottom()])

    def start_ocr(self, rect):
        if self.busy or not self.path:
            return
        if self.draft is not None or self.editing_id is not None or self.erase_selection is not None:
            QMessageBox.information(self, '请先完成当前操作', '请先应用或取消当前文字 / 擦除草稿，再进行 OCR。')
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('ocr_snapshot', epoch=self.epoch, index=self.index, revision=self.revision,
                            rect=[rect.left(),rect.top(),rect.right(),rect.bottom()])
        self.statusBar().showMessage('正在准备 OCR 选区…')

    def review_ocr(self, snapshot):
        dialog = OcrDialog(snapshot, self.fonts, self)
        self.ocr_dialog = dialog
        context = dict(epoch=self.epoch, index=self.index, revision=self.revision)
        def preview(fields):
            if not self.client.dead:
                self.client.preview = dict(kind='ocr_preview', **context, **fields)
                self.client.dispatch()
        dialog.preview_requested.connect(preview)
        accepted = dialog.exec()
        self.ocr_dialog = None
        if self.client.preview and self.client.preview.get('kind') == 'ocr_preview':
            self.client.preview = None
        if accepted and not self.client.dead and context == dict(epoch=self.epoch,index=self.index,revision=self.revision):
            self.epoch += 1
            self.set_busy(True)
            self.client.command('ocr_convert', epoch=self.epoch, index=self.index, revision=self.revision, **dialog.payload)
        dialog.deleteLater()

    def preview_image_erase(self, rect):
        rect = rect.normalized().intersected(self.page_rect)
        if self.busy or not self.path or rect.width() <= 2 or rect.height() <= 2:
            return
        self.cancel()
        self.erase_selection = EraseSelection(self, rect.width(), rect.height())
        self.erase_selection.setPos(rect.topLeft())
        self.view.scene().addItem(self.erase_selection)
        self.erase_selection.changed.connect(self.update_erase_preview)
        self.erase_selection.setFocus()
        self.update_erase_preview()

    def update_erase_preview(self, *_):
        if self.erase_selection is None:
            return
        self.picking_background = False
        if self.erase_auto_color:
            self.background_version += 1
            self.erase_color_ready = False
            self.background_timer.start()
        self.refresh_background_label()

    def refresh_background_label(self):
        box = self.erase_selection
        if box is None:
            return
        color = QColor.fromRgbF(*self.erase_color)
        self.background_color.setText(color.name()+'…')
        self.background_color.setStyleSheet('border: 3px solid '+color.name())
        self.apply_button.setText('确认擦除 / 填底色')
        self.apply_button.setEnabled(not self.busy and self.erase_color_ready)
        status = color.name() if self.erase_color_ready else '正在取样…'
        self.preview_label.setText(f'待擦除 {box.w:.1f} × {box.h:.1f} pt；底色 {status}。可取色或选色后确认。')
        self.preview_label.setToolTip('真实清除选区图片像素及文字层，再填充选定底色；纯色填充不重建渐变或纹理。')

    def request_background(self, point=None):
        box = self.erase_selection
        if box is None or self.busy:
            return
        self.background_timer.stop()
        self.background_version += 1
        self.picking_background = False
        self.erase_color_ready = False
        fields = dict(kind='sample_background', epoch=self.epoch, index=self.index,
                      revision=self.revision, version=self.background_version)
        if point is not None:
            self.erase_auto_color = False
            fields['point'] = [point.x(), point.y()]
        else:
            fields['rect'] = [box.x(),box.y(),box.x()+box.w,box.y()+box.h]
        self.client.preview = fields
        self.client.dispatch()
        self.refresh_background_label()

    def use_auto_background(self):
        self.erase_auto_color = True
        self.update_erase_preview()

    def begin_background_pick(self):
        if self.busy or self.erase_selection is None:
            self.statusBar().showMessage('请先框选待擦除区域。',4000)
            return
        self.background_timer.stop()
        self.background_version += 1
        self.picking_background = True
        self.erase_color_ready = False
        self.apply_button.setEnabled(False)
        self.preview_label.setText('请点击页面上的干净背景取色；Esc 取消预览。')

    def set_background_color(self, color):
        self.background_timer.stop()
        self.background_version += 1
        self.erase_auto_color = False
        self.picking_background = False
        self.erase_color = (color.redF(),color.greenF(),color.blueF())
        self.erase_color_ready = True
        self.refresh_background_label()

    def choose_background_color(self):
        color = QColorDialog.getColor(QColor.fromRgbF(*self.erase_color),self,'擦除后填充的底色')
        if color.isValid():
            self.set_background_color(color)

    def confirm_image_erase(self):
        box = self.erase_selection
        if self.busy or box is None or not self.erase_color_ready or self.mode.currentData() != 'erase_image':
            return
        rect = [box.x(), box.y(), box.x()+box.w, box.y()+box.h]
        self.epoch += 1
        self.set_busy(True)
        self.client.command('erase_image', epoch=self.epoch, index=self.index,
                            revision=self.revision, rect=rect, fill_color=self.erase_color)
        self.statusBar().showMessage('正在擦除选中图片区域…')

    def delete_characters(self):
        if self.busy or not self.path or not self.view.selected_chars:
            return
        ids = list(self.view.selected_chars)
        self.epoch += 1
        self.set_busy(True)
        self.client.command('delete_chars', epoch=self.epoch, index=self.index,
                            revision=self.revision, ids=ids)
        self.statusBar().showMessage('正在删除所选字符并检查相邻文字…')

    def redo(self):
        if self.busy or not self.path or not self.can_redo:
            return
        if self.draft or self.erase_selection:
            self.statusBar().showMessage('请先应用或取消预览，再重做。', 4000)
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('redo', epoch=self.epoch, index=self.index)

    def undo(self):
        if self.busy:
            return
        if self.draft or self.erase_selection:
            self.cancel()
        elif self.path:
            self.epoch += 1
            self.set_busy(True)
            self.client.command('undo', epoch=self.epoch, index=self.index)

    def turn(self, delta):
        self.go_to_page(self.index + delta)

    def go_to_page(self, index):
        if self.busy or not self.path or not 0 <= index < self.count or index == self.index:
            return
        if self.draft or self.erase_selection:
            self.page_input.setValue(self.index + 1)
            self.page_list.setCurrentRow(self.index - self.thumbnail_start if self.thumbnail_start <= self.index < self.thumbnail_start + 20 else -1)
            QMessageBox.information(self, '预览尚未确认', '请先应用或取消预览。')
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('page', epoch=self.epoch, index=index)

    def stop_recovery(self):
        self.recovery_timer.stop()
        self.recovery_pending = False
        self.recovery_stamp = None
        self.recovery_toggle.blockSignals(True)
        self.recovery_toggle.setChecked(False)
        self.recovery_toggle.blockSignals(False)
        self.recovery_label.setText('自动恢复已关闭；已有副本保留在所选目录。' if self.recovery_path else '尚未启用自动恢复副本。')

    def toggle_recovery(self, enabled):
        if not enabled:
            self.stop_recovery()
            return
        if not self.path or self.busy or self.client.dead:
            self.stop_recovery()
            return
        folder = QFileDialog.getExistingDirectory(self, '选择自动恢复副本保存目录', str(self.path.parent))
        if not folder:
            self.stop_recovery()
            return
        name = self.path.stem + '_恢复_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '_' + uuid4().hex[:8] + '.lpdf'
        self.recovery_path = Path(folder) / name
        self.recovery_stamp = None
        self.recovery_label.setText('等待保存恢复副本：' + str(self.recovery_path))
        self.recovery_timer.start()
        self.autosave()

    def autosave(self):
        if not self.recovery_toggle.isChecked() or not self.recovery_path or not self.path:
            return
        if self.busy or self.client.dead or self.recovery_pending or self.client.commands:
            return
        draft = dict(spec=self.spec(), offset=self.draft.offset, index=self.index,
                     editing_id=self.editing_id) if self.draft else None
        stamp = json.dumps([self.revision, self.index, draft], sort_keys=True, ensure_ascii=False)
        if stamp == self.recovery_stamp:
            return
        self.recovery_pending = True
        # Background snapshots must not discard queued previews or tiles.
        self.client.commands.append(dict(kind='autosave', path=str(self.recovery_path),
            index=self.index, draft=draft, epoch=self.epoch, stamp=stamp))
        self.client.dispatch()

    def on_autosave(self, response):
        request = response['request']
        if self.recovery_path is None or request['path'] != str(self.recovery_path):
            return
        self.recovery_pending = False
        if request.get('epoch') != self.epoch or not self.recovery_toggle.isChecked():
            return
        if 'error' in response:
            self.stop_recovery()
            self.recovery_label.setText('自动恢复副本保存失败，已暂停：' + response['error'])
            return
        self.recovery_stamp = request['stamp']
        self.recovery_label.setText('恢复副本已保存 ' + datetime.now().strftime('%H:%M:%S') + '\n' + str(self.recovery_path))

    def open_recovery(self):
        if self.busy and not self.client.dead:
            return
        folder = str(self.recovery_path.parent if self.recovery_path else (self.path.parent if self.path else Path.home()))
        target, _ = QFileDialog.getOpenFileName(self, '打开恢复副本', folder, '恢复副本 / 工程 (*.lpdf)')
        if target:
            self.open_pdf(target)

    def restore_recovery(self, draft):
        self.statusBar().showMessage('已打开恢复副本。请检查内容，再另存 PDF 或工程；自动恢复需要重新启用。', 10000)
        if not draft:
            return
        if draft['editing_id'] is not None:
            self.pending_recovery_draft = draft
            self.mode.setCurrentIndex(self.mode.findData('edit'))
            self.set_busy(True)
            self.client.command('begin_edit', epoch=self.epoch, index=self.index,
                                revision=self.revision, object_id=draft['editing_id'])
        else:
            self.mode.setCurrentIndex(self.mode.findData('add'))
            self.restore_object_draft(dict(id=None, spec=draft['spec'], offset=draft['offset']))
            self.apply_button.setText('应用文字  Ctrl+Enter')
            self.statusBar().showMessage('已恢复未应用的文字草稿；检查预览后应用，Esc 取消。', 10000)

    def save_project(self):
        if self.busy or not self.path:
            return
        if self.draft or self.erase_selection:
            self.statusBar().showMessage('请先应用或取消预览，再保存工程。', 5000)
            return
        target, _ = QFileDialog.getSaveFileName(self, '保存编辑工程',
            str(self.path.with_name(self.path.stem + '_工程.lpdf')), '编辑工程 (*.lpdf)')
        if not target:
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('save_project', path=target, index=self.index, epoch=self.epoch)
        self.statusBar().showMessage('正在保存文档快照及可编辑文字框…')

    def save(self):
        if self.busy or not self.path:
            return
        if self.draft or self.erase_selection:
            QMessageBox.information(self, '预览尚未确认', '请先应用或取消预览，再保存。')
            return
        target, _ = QFileDialog.getSaveFileName(self, '另存为', str(self.path.with_name(self.path.stem + '_已修改.pdf')), 'PDF (*.pdf)')
        if target:
            self.set_busy(True)
            self.client.command('save', epoch=self.epoch, path=target)
            self.statusBar().showMessage('正在后台保存 PDF…')

    def choose_color(self):
        color = QColorDialog.getColor(QColor.fromRgbF(*self.color), self)
        if color.isValid():
            self.color = (color.redF(), color.greenF(), color.blueF())
            self.color_button.setStyleSheet('color: ' + color.name())
            self.content_changed()

    def import_font(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择字体文件', '', '字体 (*.ttf *.otf *.ttc)')
        if path:
            name = Path(path).name
            self.fonts[name] = path
            if self.font_combo.findText(name) < 0:
                self.font_combo.addItem(name)
            self.font_combo.setCurrentText(name)

    def closeEvent(self, event):
        if not self.discard():
            event.ignore()
            return
        self.recovery_timer.stop()
        self.preview_timer.stop()
        self.tile_timer.stop()
        self.thumbnail_timer.stop()
        self.background_timer.stop()
        self.client.close()
        event.accept()


def main():
    app = QApplication(sys.argv)
    app.setApplicationName('轻简 PDF')
    if 'windowsvista' in QStyleFactory.keys():
        app.setStyle('windowsvista')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    editor = Editor()
    editor.show()
    if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test':
        from portable_smoke import run
        return run(editor, sys.argv[2])
    if len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: editor.open_pdf(sys.argv[1]))
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
