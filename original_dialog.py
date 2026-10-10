"""Review original-font replacement without editing the document until acceptance."""
import base64
from PySide6.QtCore import Signal,QTimer,Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QDialog,QVBoxLayout,QHBoxLayout,QLabel,QLineEdit,QPushButton


class OriginalTextDialog(QDialog):
    preview_requested=Signal(dict)

    def __init__(self,info,parent=None):
        super().__init__(parent)
        self.info=info;self.version=0;self.validated=None;self.pixmap=None
        self.setWindowTitle('原位修改原有文字')
        available=self.screen().availableGeometry()
        self.resize(min(760,available.width()-60),min(420,available.height()-60))
        layout=QVBoxLayout(self)
        label=QLabel(f"沿用原字体：{info['font']} · {info['size']:.2f} pt\n保持原位置、颜色和字距，不自动移动相邻内容。清空输入会删除本段文字。")
        label.setWordWrap(True);layout.addWidget(label)
        self.text=QLineEdit(info['text']);self.text.setMaxLength(2000);layout.addWidget(self.text)
        self.image=QLabel();self.image.setAlignment(Qt.AlignmentFlag.AlignCenter);self.image.setMinimumSize(120,80);layout.addWidget(self.image,1)
        self.status=QLabel('正在生成预览…');self.status.setWordWrap(True);layout.addWidget(self.status)
        row=QHBoxLayout();row.addStretch()
        cancel=QPushButton('取消');cancel.clicked.connect(self.reject);row.addWidget(cancel)
        self.confirm=QPushButton('应用修改（可撤销）');self.confirm.setEnabled(False);self.confirm.clicked.connect(self.accept);row.addWidget(self.confirm)
        layout.addLayout(row)
        self.timer=QTimer(self);self.timer.setSingleShot(True);self.timer.setInterval(180);self.timer.timeout.connect(self.request_preview)
        self.text.textChanged.connect(self.changed)
        QTimer.singleShot(0,self.changed)

    def changed(self,*_):
        self.version+=1;self.validated=None;self.confirm.setEnabled(False)
        self.status.setText('正在生成实际 PDF 预览…')
        self.timer.start()

    def request_preview(self):
        if self.isVisible():self.preview_requested.emit(dict(target=self.info['target'],text=self.text.text(),version=self.version))

    def receive_preview(self,response):
        if response['request']['version']!=self.version or not self.isVisible():return
        if 'error' in response:
            self.status.setText(response['error']);return
        self.pixmap=QPixmap();self.pixmap.loadFromData(base64.b64decode(response['data']['image']))
        self.show_image();self.validated=self.version
        self.confirm.setEnabled(self.text.text()!=self.info['text'])
        self.status.setText('请检查预览；应用后可一次撤销。')

    def show_image(self):
        if self.pixmap:
            self.image.setPixmap(self.pixmap.scaled(max(120,self.width()-40),max(80,min(220,self.height()-170)),Qt.AspectRatioMode.KeepAspectRatio,Qt.TransformationMode.SmoothTransformation))

    def resizeEvent(self,event):
        super().resizeEvent(event)
        if hasattr(self,'image'):self.show_image()

    def accept(self):
        if self.validated==self.version and self.confirm.isEnabled():super().accept()

    def done(self,result):
        self.timer.stop();super().done(result)
