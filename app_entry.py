"""Small launcher: diagnose incomplete bundles before importing Qt."""
from datetime import datetime
import json
import os
from pathlib import Path
import sys
import tempfile
import traceback
from uuid import uuid4


class IncompleteBundle(RuntimeError):
    pass


def validate_bundle(root):
    required = ('PdfWorker.exe', '_internal/PySide6/Qt6Core.dll',
                '_internal/PySide6/plugins/platforms/qwindows.dll')
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise IncompleteBundle('程序包不完整 / Incomplete application bundle: ' + ', '.join(missing)
                               + '\n请完整解压 ZIP 到新目录，不要只复制主 EXE。'
                               + '\nExtract the complete ZIP into a new folder; keep all bundled files together.')


def write_startup_log(details):
    for base in (Path(os.environ.get('LOCALAPPDATA', tempfile.gettempdir())) / 'LightPDFEditor' / 'logs',
                 Path(tempfile.gettempdir()) / 'LightPDFEditor-logs'):
        try:
            base.mkdir(parents=True, exist_ok=True)
            path = base / ('startup-' + datetime.now().strftime('%Y%m%d-%H%M%S') + '-' + uuid4().hex[:8] + '.log')
            path.write_text(details, encoding='utf-8')
            return path
        except OSError:
            continue
    return None


def report_failure(exc, details, smoke_output=None):
    log = write_startup_log(details)
    message = '轻简 PDF 无法启动 / Light PDF Editor could not start.\n\n' + str(exc)
    message += '\n\n请重新完整解压下载包。 / Re-extract the full download. '
    if log:
        message += '\n本地诊断日志 / Local diagnostic log: ' + str(log)
    if smoke_output is not None:
        output = Path(smoke_output)
        output.mkdir(parents=True, exist_ok=True)
        (output / 'smoke-report.json').write_text(json.dumps(dict(ok=False, startup_failure=True,
            frozen=bool(getattr(sys, 'frozen', False)), error=message), ensure_ascii=False, indent=2), encoding='utf-8')
    elif os.name == 'nt':
        import ctypes
        ctypes.windll.user32.MessageBoxW(None, message, '轻简 PDF · 启动失败', 0x10)
    elif sys.stderr:
        print(message, file=sys.stderr)


def main():
    try:
        if getattr(sys, 'frozen', False):
            validate_bundle(Path(sys.executable).resolve().parent)
        from pdf_editor import main as editor_main
        return editor_main()
    except Exception as exc:
        smoke_output = sys.argv[2] if len(sys.argv) == 3 and sys.argv[1] == '--smoke-test' else None
        report_failure(exc, traceback.format_exc(), smoke_output)
        return 1


if __name__ == '__main__':
    sys.exit(main())
