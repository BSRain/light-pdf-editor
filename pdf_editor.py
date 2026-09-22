"""Qt UI; PDF parsing, editing and rendering run in pdf_worker.py."""
from collections import OrderedDict, deque
import base64
import json
import math
from pathlib import Path
import sys
from PySide6.QtCore import Qt, QObject, Signal, QProcess, QTimer, QPointF, QRectF
from PySide6.QtGui import QAction, QColor, QPainter, QPen, QPixmap, QImage, QFont, QPainterPath
from PySide6.QtWidgets import (QApplication, QMainWindow, QWidget, QGraphicsView, QGraphicsScene,
    QGraphicsObject, QVBoxLayout, QFormLayout, QLabel, QPushButton, QToolBar, QComboBox,
    QDoubleSpinBox, QCheckBox, QPlainTextEdit, QDockWidget, QFileDialog, QMessageBox,
    QColorDialog, QInputDialog, QLineEdit, QScrollArea, QStyleFactory)
from pdf_core import windows_fonts
from alignment import snap_box, nearest_span, match_font
from version import __version__


class PdfClient(QObject):
    result = Signal(dict)
    failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.commands = deque()
        self.preview = None
        self.tiles = []
        self.active = None
        self.serial = 0
        self.buffer = bytearray()
        self.stopping = False
        self.dead = False
        self.stderr = ''
        self.process = QProcess(self)
        self.process.setProgram(sys.executable)
        self.process.setArguments(['-u', str(Path(__file__).with_name('pdf_worker.py'))])
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.started.connect(self.dispatch)
        self.process.errorOccurred.connect(lambda error: self.failure(self.process.errorString()))
        self.process.finished.connect(lambda code, status: self.failure('PDF 处理进程已停止，请重新启动编辑器。'))
        self.process.start()

    def read_error(self):
        self.stderr = (self.stderr + bytes(self.process.readAllStandardError()).decode('utf-8', 'replace'))[-4000:]

    def failure(self, message):
        if not self.stopping and not self.dead:
            self.dead = True
            self.failed.emit(message)

    def command(self, kind, **fields):
        self.tiles = []
        self.preview = None
        self.commands.append(dict(kind=kind, **fields))
        self.dispatch()

    def request_preview(self, **fields):
        self.preview = dict(kind='preview', **fields)
        self.dispatch()

    def replace_tiles(self, requests):
        self.tiles = [r for r in requests if not self.active or r.get('key') != self.active.get('key')]
        self.dispatch()

    def dispatch(self):
        if self.stopping or self.dead or self.active is not None or self.process.state() != QProcess.ProcessState.Running:
            return
        if self.commands:
            request = self.commands.popleft()
        elif self.preview is not None:
            request, self.preview = self.preview, None
        elif self.tiles:
            request = self.tiles.pop(0)
        else:
            return
        self.serial += 1
        request['id'] = self.serial
        self.active = request
        self.process.write((json.dumps(request, ensure_ascii=False) + '\n').encode('utf-8'))

    def read(self):
        self.buffer.extend(bytes(self.process.readAllStandardOutput()))
        while b'\n' in self.buffer:
            line, _, rest = self.buffer.partition(b'\n')
            self.buffer = bytearray(rest)
            try:
                response = json.loads(line)
            except ValueError:
                self.failure('PDF 进程返回了无效数据。')
                continue
            request, self.active = self.active, None
            if not self.stopping and request and response.get('id') == request['id']:
                response['request'] = request
                self.result.emit(response)
            self.dispatch()

    def close(self):
        self.stopping = True
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(400):
            self.process.kill()
            self.process.waitForFinished(1000)


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
            if self.editor.snap.isChecked() and not event.modifiers() & Qt.KeyboardModifier.AltModifier:
                x, y, guides = snap_box(x, y, width, height, self.offset, self.editor.spans, 7 / self.editor.view.zoom)
                self.editor.draw_guides(guides)
            else:
                self.editor.draw_guides([])
            x, y = max(0, min(x, bounds.width() - width)), max(0, min(y, bounds.height() - height))
            self.setPos(x, y)
        else:
            if 'w' in kind:
                x = max(0, min(x + delta.x(), right - 12))
            if 'e' in kind:
                right = min(bounds.width(), max(x + 12, right + delta.x()))
            if 'n' in kind:
                y = max(0, min(y + delta.y(), bottom - 12))
            if 's' in kind:
                bottom = min(bounds.height(), max(y + 12, bottom + delta.y()))
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
        draft = self.editor.draft
        if event.button() == Qt.MouseButton.LeftButton and draft and draft.hit(draft.mapFromScene(point)):
            super().mousePressEvent(event)
            return
        if event.button() == Qt.MouseButton.LeftButton and not self.editor.busy and self.editor.page_rect.contains(point):
            mode = self.editor.mode.currentData()
            if mode == 'sample':
                self.editor.sample(point)
            elif mode == 'add':
                self.editor.place(point)
            elif mode == 'erase':
                span = nearest_span(point.x(), point.y(), self.editor.spans, 3 / self.zoom)
                if span:
                    x0, y0, x1, y1 = span['bbox']
                    self.editor.delete_selection(QRectF(x0, y0, x1 - x0, y1 - y0))
                else:
                    self.editor.statusBar().showMessage('此处没有可删除的文字；扫描件中的图片文字不支持直接删除。', 5000)
            elif mode in ('delete', 'precise'):
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
        if len(paths) == 1 and Path(paths[0]).suffix.lower() == '.pdf':
            self.editor.open_pdf(paths[0])
            event.acceptProposedAction()
        else:
            self.editor.statusBar().showMessage('请每次拖入一个 PDF 文件。', 5000)


class Editor(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle(f'轻简 PDF {__version__} · Qt 版 · 自用')
        available = QApplication.primaryScreen().availableGeometry()
        self.resize(min(1280, available.width() - 60), min(860, available.height() - 60))
        self.setMinimumSize(900, 640)
        self.path = None
        self.index = 0
        self.count = 0
        self.revision = 0
        self.epoch = 0
        self.busy = False
        self.dirty = False
        self.spans = []
        self.characters = []
        self.can_undo = False
        self.can_redo = False
        self.page_rect = QRectF()
        self.draft = None
        self.guides = []
        self.color = (0.0, 0.0, 0.0)
        self.fonts = windows_fonts()
        self.preview_version = 0
        self.tile_cache = OrderedDict()
        self.cache_bytes = 0
        self.tile_items = {}
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
        self.view.viewport_changed.connect(self.tile_timer.start)
        self.build_toolbar()
        self.build_panel()
        self.client = PdfClient(self)
        self.client.result.connect(self.on_result)
        self.client.failed.connect(self.worker_failed)
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
        self.open_action = self.action(bar, '打开 PDF', lambda: self.open_pdf(), 'Ctrl+O')
        self.save_action = self.action(bar, '另存为', self.save, 'Ctrl+S')
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
        self.mode = QComboBox()
        for label, value in [('添加文字', 'add'), ('精细删除（按字符）', 'precise'), ('框选删除', 'delete'), ('点选删除文字', 'erase'), ('取样原文样式', 'sample'), ('平移页面', 'pan')]:
            self.mode.addItem(label, value)
        self.mode.currentIndexChanged.connect(self.mode_changed)
        editing.addWidget(self.mode)
        self.action(editing, '精细删除', lambda: self.mode.setCurrentIndex(self.mode.findData('precise')))
        self.delete_chars_action = self.action(editing, '删除所选', self.delete_characters)
        self.delete_chars_action.setEnabled(False)
        self.delete_chars_action.setToolTip('预览红色字符选区后点击删除；在页面上也可按 Delete，Esc 取消。')
        self.action(editing, '框选删除', lambda: self.mode.setCurrentIndex(self.mode.findData('delete')))
        self.action(editing, '点选删除', lambda: self.mode.setCurrentIndex(self.mode.findData('erase')))
        self.snap = QCheckBox('吸附原文基线 / 边缘（Alt 暂停）')
        self.snap.setChecked(True)
        editing.addWidget(self.snap)
        editing.addSeparator()
        self.view.setToolTip('滚轮缩放 · 中键平移 · Shift+滚轮滚动')

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
        self.font_combo = QComboBox()
        self.font_combo.addItems(list(self.fonts) or ['内置宋体'])
        self.font_combo.currentTextChanged.connect(self.content_changed)
        form.addRow('字体', self.font_combo)
        import_button = QPushButton('选择字体文件…')
        import_button.clicked.connect(self.import_font)
        form.addRow('', import_button)
        self.size = QDoubleSpinBox()
        self.size.setRange(6, 96)
        self.size.setValue(14)
        self.size.setSuffix(' pt')
        self.size.valueChanged.connect(self.content_changed)
        form.addRow('字号', self.size)
        self.bold = QCheckBox('加粗')
        self.bold.toggled.connect(self.content_changed)
        form.addRow('', self.bold)
        self.color_button = QPushButton('文字颜色  ■')
        self.color_button.clicked.connect(self.choose_color)
        form.addRow('颜色', self.color_button)
        self.coords = {}
        for key, label, value in [('x', '左侧 X', 40), ('baseline', '首行基线 Y', 60), ('width', '文字框宽', 260), ('height', '文字框高', 90)]:
            field = QDoubleSpinBox()
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
        self.preview_label = QLabel('点击页面放置文字；对齐时出现蓝色参考线。')
        self.preview_label.setWordWrap(True)
        layout.addWidget(self.preview_label)
        self.apply_button = QPushButton('应用文字  Ctrl+Enter')
        self.apply_button.setEnabled(False)
        self.apply_button.clicked.connect(self.apply)
        layout.addWidget(self.apply_button)
        cancel = QPushButton('取消预览  Esc')
        cancel.clicked.connect(self.cancel)
        layout.addWidget(cancel)
        hint = QLabel('框内拖动，边角调整大小。\n方向键微调，Shift+方向键移动 10 pt。\n虚线标示首行文字基线，不是文字框顶边。')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setWidget(body)
        dock.setWidget(scroll)
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
        for control in (self.open_action, self.save_action, self.undo_action, self.redo_action, self.prev_action, self.next_action):
            control.setEnabled(not value)
        self.undo_action.setEnabled(not value and self.can_undo)
        self.redo_action.setEnabled(not value and self.can_redo)
        self.delete_chars_action.setEnabled(not value and bool(self.view.selected_chars))
        self.mode.setEnabled(not value)
        self.apply_button.setEnabled(not value and self.draft is not None and self.draft.valid)
        if self.draft:
            self.draft.setEnabled(not value)
        for control in (self.text_input, self.font_combo, self.size, self.bold, *self.coords.values()):
            control.setEnabled(not value)

    def discard(self):
        if self.busy:
            self.statusBar().showMessage('正在处理文件，请稍后。', 5000)
            return False
        if self.dirty or self.draft:
            return QMessageBox.question(self, '未保存的修改', '是否放弃当前未保存的修改和文字预览？',
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes
        return True

    def open_pdf(self, path=None):
        if not self.discard():
            return
        if not path:
            path, _ = QFileDialog.getOpenFileName(self, '打开 PDF', '', 'PDF (*.pdf)')
        if not path:
            return
        self.epoch += 1
        self.set_busy(True)
        self.statusBar().showMessage('正在后台打开 PDF…')
        self.client.command('open', path=str(path), epoch=self.epoch)

    def worker_failed(self, message):
        self.set_busy(False)
        self.statusBar().showMessage(message)
        self.apply_button.setEnabled(False)
        QMessageBox.critical(self, 'PDF 进程错误', message)

    def on_result(self, response):
        request = response['request']
        kind = request['kind']
        if request.get('epoch') != self.epoch:
            return
        if 'error' in response:
            if kind == 'preview':
                if request.get('version') == self.preview_version and self.draft:
                    self.draft.valid = False
                    self.draft.pixmap = None
                    self.draft.update()
                    self.apply_button.setEnabled(False)
                    self.preview_label.setText(response['error'])
            elif kind == 'tile':
                self.statusBar().showMessage('该区域渲染失败：' + response['error'], 6000)
            else:
                self.set_busy(False)
                QMessageBox.warning(self, '操作未完成', response['error'])
                if self.path and kind in ('insert', 'delete', 'delete_chars', 'undo', 'redo', 'open'):
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
        if kind in ('open', 'page', 'insert', 'delete', 'delete_chars', 'undo', 'redo'):
            self.load_page(data, fit=kind in ('open', 'page'))
        elif kind == 'preview':
            if self.draft and request['version'] == self.preview_version:
                baseline = self.draft.y() + self.draft.offset
                self.draft.offset = data['baseline_offset']
                self.draft.setY(max(0, min(baseline - self.draft.offset, self.page_rect.height() - self.draft.h)))
                self.draft.pixmap = decode_pixmap(data['image'])
                self.draft.valid = True
                self.draft.update()
                self.sync_geometry()
                self.apply_button.setEnabled(not self.busy)
                self.preview_label.setText('实际 PDF 排版预览。蓝色虚线是首行基线。')
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
        elif kind == 'save':
            self.dirty = False
            self.set_busy(False)
            self.update_title()
            self.statusBar().showMessage('已保存：' + data['saved'], 10000)
            self.tile_timer.start()

    def load_page(self, data, fit=False):
        self.view.clear_erase_hover()
        self.cancel()
        self.path = Path(data['path'])
        self.index, self.count, self.revision = data['index'], data['count'], data['revision']
        self.dirty = data['dirty']
        self.spans = data['spans']
        self.characters = data.get('characters', [])
        self.can_undo, self.can_redo = data['can_undo'], data.get('can_redo', False)
        self.page_rect = QRectF(0, 0, data['width'], data['height'])
        scene = self.view.scene()
        scene.clear()
        self.guides = []
        self.tile_items = {}
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
        self.set_busy(False)
        self.undo_action.setEnabled(data['can_undo'])
        self.update_title()
        if fit:
            self.fit_page()
        self.tile_timer.start()
        message = '滚轮缩放，中键平移；点击原文附近可吸附到同一基线。'
        if not self.spans:
            message = '本页没有可提取文字（可能为扫描件）；可添加文字，但无法吸附或删除图片内文字。'
        self.statusBar().showMessage(message)

    def update_title(self):
        self.setWindowTitle(f'{"* " if self.dirty else ""}{self.path.name if self.path else "轻简 PDF"} · {__version__} · Qt 版 · 自用')

    def schedule_tiles(self):
        if not self.path or self.busy:
            return
        scale = math.ceil(self.view.zoom * self.view.devicePixelRatioF() * 4) / 4
        scale = min(10, max(0.25, scale))
        group = (self.epoch, self.revision, self.index, scale)
        if group != self.tile_group:
            for item in self.tile_items.values():
                self.view.scene().removeItem(item)
            self.tile_items = {}
            self.tile_group = group
        visible = self.view.mapToScene(self.view.viewport().rect()).boundingRect().intersected(self.page_rect)
        if visible.isEmpty():
            self.wanted = set()
            self.client.replace_tiles([])
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
        self.view.clear_erase_hover()
        self.view.clear_character_selection()
        if hasattr(self, 'text_input') and self.mode.currentData() in ('delete', 'erase', 'precise'):
            self.cancel()
        self.draw_guides([])
        if self.mode.currentData() == 'precise':
            self.statusBar().showMessage('精细删除：单击选一个字符，拖动选择字符中心落在框内的文字；预览后按 Delete 删除，Esc 取消。')
        elif self.mode.currentData() == 'erase':
            self.statusBar().showMessage('点选删除：红框标出将删除的文字段；点击删除，Ctrl+Z 撤销。')
        elif self.mode.currentData() == 'delete':
            self.statusBar().showMessage('框选删除：拖动框选文字，松开后删除；Ctrl+Z 撤销。')

    def spec(self):
        draft = self.draft
        return dict(x=draft.x(), y=draft.y(), width=draft.w, height=draft.h,
                    text=self.text_input.toPlainText(), size=self.size.value(), color=self.color,
                    fontfile=self.fonts.get(self.font_combo.currentText()), bold=self.bold.isChecked())

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
        self.bold.setChecked(span['bold'])
        color = span['color']
        self.color = (((color >> 16) & 255) / 255, ((color >> 8) & 255) / 255, (color & 255) / 255)
        self.color_button.setStyleSheet(f'color: #{color:06x}')
        note = f'原字体：{span["font"]}，{span["size"]:.2f} pt。'
        if not family:
            note += f'本机未找到对应字体，使用 {self.font_combo.currentText()}。'
        else:
            note += f'使用本机 {family}。'
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

    def cancel(self):
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
        self.preview_label.setText('点击页面放置文字；虚线是首行基线。')

    def apply(self):
        if self.busy or not self.draft or not self.draft.valid:
            return
        spec = self.spec()
        self.epoch += 1
        self.set_busy(True)
        self.client.command('insert', epoch=self.epoch, index=self.index, spec=spec)
        self.statusBar().showMessage('正在后台写入文字…')

    def delete_selection(self, rect):
        if self.busy:
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('delete', epoch=self.epoch, index=self.index,
                            rect=[rect.left(), rect.top(), rect.right(), rect.bottom()])

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
        if self.draft:
            self.statusBar().showMessage('请先应用或取消文字预览，再重做。', 4000)
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('redo', epoch=self.epoch, index=self.index)

    def undo(self):
        if self.busy:
            return
        if self.draft:
            self.cancel()
        elif self.path:
            self.epoch += 1
            self.set_busy(True)
            self.client.command('undo', epoch=self.epoch, index=self.index)

    def turn(self, delta):
        if self.busy or not self.path or not 0 <= self.index + delta < self.count:
            return
        if self.draft:
            QMessageBox.information(self, '文字尚未应用', '请先应用或取消文字预览。')
            return
        self.epoch += 1
        self.set_busy(True)
        self.client.command('page', epoch=self.epoch, index=self.index + delta)

    def save(self):
        if self.busy or not self.path:
            return
        if self.draft:
            QMessageBox.information(self, '文字尚未应用', '请先应用或取消文字预览，再保存。')
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
        self.preview_timer.stop()
        self.tile_timer.stop()
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
    if len(sys.argv) > 1:
        QTimer.singleShot(0, lambda: editor.open_pdf(sys.argv[1]))
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
