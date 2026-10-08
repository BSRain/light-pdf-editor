"""Review OCR text and an actual PDF conversion preview before committing."""
from pathlib import Path
import base64
import sys
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QPixmap, QColor
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QPlainTextEdit, QComboBox, QDoubleSpinBox, QFormLayout, QScrollArea, QWidget, QColorDialog)
from pdf_client import PdfClient


class OcrDialog(QDialog):
    preview_requested = Signal(dict)

    def __init__(self, snapshot, fonts, parent=None):
        super().__init__(parent)
        self.snapshot = snapshot
        self.fonts = fonts
        self.client = None
        self.version = 0
        self.payload = None
        self.validated = None
        self.recognizing = False
        self.fill_color = snapshot['fill_color']
        self.text_color = [0,0,0]
        self.preview_pixmap = None
        self.original = QPixmap()
        self.original.loadFromData(base64.b64decode(snapshot['image']))
        self.setWindowTitle('OCR → 可编辑文字 · 校对与预览')
        screen = self.screen().availableGeometry()
        self.resize(min(850,screen.width()-60),min(790,screen.height()-60))
        layout = QVBoxLayout(self)
        scroll = QScrollArea();scroll.setWidgetResizable(True)
        body = QWidget();contents = QVBoxLayout(body);scroll.setWidget(body);layout.addWidget(scroll)
        info = QLabel('框选区域内的图片内容会被纯色填充，再写入一个可编辑文字框。\n请避开图片、扫描表格线和复杂背景；先校对，再确认。关闭窗口不修改 PDF。')
        if snapshot.get('background_warning'):
            info.setText(info.text()+'\n'+snapshot['background_warning'])
        info.setWordWrap(True);contents.addWidget(info)
        row = QHBoxLayout()
        self.language=QComboBox();self.language.addItem('简体中文＋英文','chi_sim+eng');self.language.addItem('英文','eng')
        row.addWidget(self.language)
        self.recognize_button=QPushButton('重新识别');self.recognize_button.clicked.connect(self.recognize);row.addWidget(self.recognize_button)
        self.stop_button=QPushButton('取消识别');self.stop_button.clicked.connect(self.stop_recognition);row.addWidget(self.stop_button)
        contents.addLayout(row)
        self.text=QPlainTextEdit();self.text.setPlaceholderText('正在识别…识别后请检查错字。');self.text.setMinimumHeight(90);self.text.setMaximumHeight(160)
        contents.addWidget(self.text)
        form=QFormLayout();self.font=QComboBox()
        for name,path in fonts.items(): self.font.addItem(name,path)
        self.size=QDoubleSpinBox();self.size.setRange(4,144);self.size.setValue(14);self.size.setSuffix(' pt')
        self.left=QDoubleSpinBox();self.top=QDoubleSpinBox()
        x0,y0,x1,y1=snapshot['rect']
        self.left.setRange(0,max(0,x1-x0-3));self.top.setRange(0,max(0,y1-y0-3))
        for spin in (self.left,self.top): spin.setSuffix(' pt')
        self.fill_button=QPushButton();self.fill_button.clicked.connect(lambda: self.pick_color(True))
        self.ink_button=QPushButton();self.ink_button.clicked.connect(lambda: self.pick_color(False))
        for label,control in [('字体',self.font),('字号',self.size),('左侧留白',self.left),('顶部留白',self.top),('填充底色',self.fill_button),('文字颜色',self.ink_button)]: form.addRow(label,control)
        contents.addLayout(form);self.update_colors()
        self.compare=QComboBox();self.compare.addItems(['原图选区','转换预览']);self.compare.currentIndexChanged.connect(self.show_image)
        contents.addWidget(self.compare)
        self.image=QLabel();self.image.setMinimumSize(160,100);self.image.setMaximumHeight(220);self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        contents.addWidget(self.image)
        self.status=QLabel(f"识别分辨率 {snapshot['dpi']} DPI；预览通过后可确认转换。")
        self.status.setWordWrap(True);contents.addWidget(self.status)
        buttons=QHBoxLayout();buttons.addStretch()
        cancel=QPushButton('取消');cancel.clicked.connect(self.reject);buttons.addWidget(cancel)
        self.confirm=QPushButton('确认转换（可撤销）');self.confirm.setEnabled(False);self.confirm.clicked.connect(self.accept);buttons.addWidget(self.confirm)
        layout.addLayout(buttons)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(250);self.timer.timeout.connect(self.request_preview)
        self.text.textChanged.connect(self.changed);self.font.currentIndexChanged.connect(self.changed)
        for spin in (self.size,self.left,self.top): spin.valueChanged.connect(self.changed)
        self.show_image()
        QTimer.singleShot(0,self.recognize)

    def update_colors(self):
        for button,color in ((self.fill_button,self.fill_color),(self.ink_button,self.text_color)):
            c=QColor.fromRgbF(*color);button.setText(c.name());button.setStyleSheet('border: 3px solid '+c.name())

    def pick_color(self, background):
        color=QColorDialog.getColor(QColor.fromRgbF(*(self.fill_color if background else self.text_color)),self,'选择颜色')
        if color.isValid():
            value=[color.redF(),color.greenF(),color.blueF()]
            if background: self.fill_color=value
            else: self.text_color=value
            self.update_colors();self.changed()

    def recognize(self):
        if not self.isVisible(): return
        self.stop_recognition()
        self.recognizing=True;self.changed()
        self.text.setEnabled(False);self.recognize_button.setEnabled(False);self.stop_button.setEnabled(True)
        self.status.setText('正在离线识别，可取消；原 PDF 尚未改变。')
        if getattr(sys,'frozen',False):
            command=[str(Path(sys.executable).with_name('PdfWorker.exe')),'--ocr']
        else:
            command=[sys.executable,'-u',str(Path(__file__).with_name('worker_entry.py')),'--ocr']
        self.client=PdfClient(self,worker_command=command,timeout_ms=120000)
        self.client.result.connect(self.recognized);self.client.failed.connect(self.failed)
        self.client.command('ocr_recognize',snapshot=self.snapshot,language=self.language.currentData())

    def stop_recognition(self):
        if self.client:
            self.client.close();self.client.deleteLater();self.client=None
        self.recognizing=False;self.text.setEnabled(True);self.recognize_button.setEnabled(True);self.stop_button.setEnabled(False)
        self.status.setText('识别已停止，原 PDF 未改变。可重新识别。')
        self.changed()

    def failed(self,message):
        self.stop_recognition();self.status.setText(message)

    def recognized(self,response):
        self.stop_recognition()
        if 'error' in response:
            self.status.setText(response['error']);return
        result=response['data']
        self.text.setPlainText(result['text'])
        self.size.setValue(round(result['size'],1))
        self.left.setValue(max(0,min(line['bbox'][0] for line in result['lines'])-self.snapshot['rect'][0]))
        self.top.setValue(max(0,min(line['bbox'][1] for line in result['lines'])-self.snapshot['rect'][1]))
        self.changed()

    def changed(self,*_):
        self.version+=1;self.validated=None;self.confirm.setEnabled(False);self.preview_pixmap=None
        self.show_image()
        self.timer.stop()
        if not self.recognizing and self.text.toPlainText().strip(): self.timer.start()

    def request_preview(self):
        if not self.isVisible() or self.recognizing: return
        x0,y0,x1,y1=self.snapshot['rect']
        x,y=x0+self.left.value(),y0+self.top.value()
        self.payload=dict(rect=self.snapshot['rect'],fill_color=list(self.fill_color),
            spec=dict(x=x,y=y,width=x1-x,height=y1-y,text=self.text.toPlainText(),size=self.size.value(),
                      color=list(self.text_color),fontfile=self.font.currentData(),bold=False,align=0))
        self.status.setText('正在生成实际 PDF 转换预览…')
        self.preview_requested.emit(dict(**self.payload,version=self.version))

    def receive_preview(self,response):
        if response['request']['version']!=self.version or not self.isVisible(): return
        if 'error' in response:
            self.status.setText(response['error']+' 可减小字号或留白后重试。');return
        self.preview_pixmap=QPixmap();self.preview_pixmap.loadFromData(base64.b64decode(response['data']['image']))
        self.validated=self.version;self.confirm.setEnabled(True);self.compare.setCurrentIndex(1);self.show_image()
        self.status.setText('请检查内容和外观。确认会清除选区原图内容并写入文字，可一次撤销。')

    def show_image(self,*_):
        if not hasattr(self,'image'): return
        pix=self.original if self.compare.currentIndex()==0 else self.preview_pixmap
        self.image.setPixmap(pix.scaled(max(160,self.width()-70),200,Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation) if pix else QPixmap())

    def resizeEvent(self,event):
        super().resizeEvent(event);self.show_image()

    def accept(self):
        if self.validated==self.version and self.payload is not None: super().accept()

    def done(self,result):
        self.timer.stop()
        if self.client:
            self.client.close();self.client.deleteLater();self.client=None
        super().done(result)
