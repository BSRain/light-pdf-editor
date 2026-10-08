"""Qt worker transport and lifecycle, independent of the editor UI."""
from collections import deque
import json
from pathlib import Path
import sys
from PySide6.QtCore import QObject, Signal, QProcess, QTimer
from worker_diagnostics import write_worker_log

class PdfClient(QObject):
    MAX_FRAME_BYTES = 64 * 1024 * 1024
    STARTUP_TIMEOUT_MS = 30000
    REQUEST_TIMEOUT_MS = 120000
    LONG_TIMEOUT_MS = 300000

    result = Signal(dict)
    failed = Signal(str)

    def __init__(self, parent=None, *, worker_command=None, timeout_ms=None):
        super().__init__(parent)
        self.commands = deque()
        self.preview = None
        self.thumbnails = []
        self.tiles = []
        self.active = None
        self.serial = 0
        self.buffer = bytearray()
        self.stopping = False
        self.dead = False
        self.stderr = ''
        self.timeout_override = timeout_ms
        self.watchdog = QTimer(self)
        self.watchdog.setSingleShot(True)
        self.watchdog.timeout.connect(self.timed_out)
        self.process = QProcess(self)
        if worker_command is not None:
            self.process.setProgram(worker_command[0])
            self.process.setArguments(worker_command[1:])
        elif getattr(sys, 'frozen', False):
            self.process.setProgram(str(Path(sys.executable).with_name('PdfWorker.exe')))
            self.process.setArguments([])
        else:
            self.process.setProgram(sys.executable)
            self.process.setArguments(['-u', str(Path(__file__).with_name('worker_entry.py'))])
        self.process.readyReadStandardOutput.connect(self.read)
        self.process.readyReadStandardError.connect(self.read_error)
        self.process.started.connect(self.dispatch)
        self.process.errorOccurred.connect(lambda error: self.failure(self.process.errorString()))
        self.process.finished.connect(lambda code, status: self.failure('PDF 处理进程已停止。'))
        self.watchdog.start(self.STARTUP_TIMEOUT_MS)
        self.process.start()

    def read_error(self):
        self.stderr = (self.stderr + bytes(self.process.readAllStandardError()).decode('utf-8', 'replace'))[-4000:]

    def timeout_for(self, request):
        if self.timeout_override is not None:
            return self.timeout_override
        return self.LONG_TIMEOUT_MS if request['kind'] in (
            'open', 'insert', 'update_object', 'delete', 'delete_chars', 'erase_image',
            'undo', 'redo', 'begin_edit', 'save', 'save_project', 'autosave', 'ocr_convert', 'ocr_preview', 'ocr_recognize') else self.REQUEST_TIMEOUT_MS

    def timed_out(self):
        self.failure('PDF 处理请求超时，已停止工作进程。')

    def failure(self, message, *, notify=True):
        if not self.stopping and not self.dead:
            self.dead = True
            self.watchdog.stop()
            self.read_error()
            log = write_worker_log(message, self.active, self.stderr)
            self.commands.clear()
            self.preview = None
            self.tiles = []
            self.thumbnails = []
            self.active = None
            self.buffer.clear()
            self.process.kill()
            if log:
                message += '\n本地诊断日志：' + str(log)
            else:
                message += '\n诊断日志无法写入；请记录本次错误提示。'
            if notify:
                self.failed.emit(message)

    def command(self, kind, **fields):
        if self.dead or self.stopping:
            return
        self.tiles = []
        self.thumbnails = []
        self.preview = None
        self.commands.append(dict(kind=kind, **fields))
        self.dispatch()

    def request_preview(self, **fields):
        if self.dead or self.stopping:
            return
        self.preview = dict(kind='preview', **fields)
        self.dispatch()

    def replace_tiles(self, requests):
        if self.dead or self.stopping:
            return
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
        elif self.thumbnails:
            request = self.thumbnails.pop(0)
        else:
            self.watchdog.stop()
            return
        self.watchdog.stop()
        self.serial += 1
        request['id'] = self.serial
        self.active = request
        payload = (json.dumps(request, ensure_ascii=False) + '\n').encode('utf-8')
        if len(payload) > self.MAX_FRAME_BYTES:
            self.failure('PDF 请求超过通信大小上限，已停止工作进程。')
            return
        self.watchdog.start(self.timeout_for(request))
        self.process.write(payload)

    def read(self):
        if self.dead or self.stopping:
            return
        while self.process.bytesAvailable() and not self.dead and not self.stopping:
            # Read bounded chunks; reserve one byte to detect an overlong frame.
            room = self.MAX_FRAME_BYTES + 1 - len(self.buffer)
            self.buffer.extend(bytes(self.process.read(min(65536, room))))
            while b'\n' in self.buffer:
                line, _, rest = self.buffer.partition(b'\n')
                self.buffer = bytearray(rest)
                if len(line) + 1 > self.MAX_FRAME_BYTES:
                    self.failure('PDF 响应超过通信大小上限，已停止工作进程。')
                    return
                try:
                    response = json.loads(line)
                except (ValueError, RecursionError):
                    self.failure('PDF 进程返回了无效数据。')
                    return
                if (not isinstance(response, dict) or not self.active or
                    type(response.get('id')) is not int or response['id'] != self.active['id'] or
                    (('data' in response) == ('error' in response)) or
                    ('data' in response and not isinstance(response['data'], dict)) or
                    ('error' in response and not isinstance(response['error'], str))):
                    self.failure('PDF 进程返回的数据与当前操作不匹配。')
                    return
                self.watchdog.stop()
                request, self.active = self.active, None
                response['request'] = request
                self.result.emit(response)
                if self.dead or self.stopping:
                    return
                self.dispatch()
            if len(self.buffer) >= self.MAX_FRAME_BYTES:
                self.failure('PDF 响应超过通信大小上限，已停止工作进程。')
                return

    def close(self):
        self.stopping = True
        self.watchdog.stop()
        self.process.closeWriteChannel()
        if not self.process.waitForFinished(400):
            self.process.kill()
            self.process.waitForFinished(1000)

