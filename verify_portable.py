"""Verify a relocated portable ZIP with Python removed from the child PATH."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import uuid
import zipfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('archive', type=Path)
    parser.add_argument('--scale', default='1')
    parser.add_argument('--fault-checks', action='store_true', help='Check readable errors for missing bundled components')
    args = parser.parse_args()
    root = Path(__file__).resolve().parent
    target = (root/'tmp'/('便携验证 空格_'+uuid.uuid4().hex[:8])).resolve()
    if not target.is_relative_to(root/'tmp'):
        raise RuntimeError('Verification path escaped workspace.')
    target.mkdir(parents=True)
    with zipfile.ZipFile(args.archive) as bundle:
        for name in bundle.namelist():
            if not (target/name).resolve().is_relative_to(target):
                raise RuntimeError('Archive contains an unsafe path.')
        bundle.extractall(target)
    application = target/'LightPDFEditor'/'LightPDFEditor.exe'
    output = target/'结果'
    environment = {k:v for k,v in os.environ.items() if k.upper() not in
                   ('PYTHONPATH', 'PYTHONHOME', 'VIRTUAL_ENV', 'QT_PLUGIN_PATH', 'QT_QPA_PLATFORM_PLUGIN_PATH')}
    environment['PATH'] = str(Path(os.environ['SystemRoot'])/'System32')
    environment['QT_SCALE_FACTOR'] = args.scale
    result = subprocess.run([str(application), '--smoke-test', str(output)], cwd=target,
                            env=environment, capture_output=True, timeout=120)
    report_path = output/'smoke-report.json'
    if not report_path.exists():
        raise RuntimeError(f'No smoke report. Exit {result.returncode}: {result.stderr!r}')
    report = json.loads(report_path.read_text(encoding='utf-8'))
    print(json.dumps(dict(report=report, report_path=str(report_path), scale=args.scale), ensure_ascii=False, indent=2))
    if result.returncode or not report['ok'] or not report['frozen']:
        raise SystemExit(1)
    if args.fault_checks:
        environment['LOCALAPPDATA'] = str(target / 'local-appdata')
        for name in ('PdfWorker.exe', '_internal/PySide6/plugins/platforms/qwindows.dll'):
            component = application.parent / name
            disabled = component.with_name(component.name + '.test-disabled')
            if not component.resolve().is_relative_to(target) or disabled.exists():
                raise RuntimeError('Unsafe fault-check path')
            component.rename(disabled)
            try:
                failure_output = target / ('fault-' + component.stem)
                failed = subprocess.run([str(application), '--smoke-test', str(failure_output)], cwd=target,
                                        env=environment, capture_output=True, timeout=30)
                failure = json.loads((failure_output/'smoke-report.json').read_text(encoding='utf-8'))
                if not failed.returncode or not failure.get('startup_failure') or name not in failure['error']:
                    raise RuntimeError('Missing component did not produce expected startup diagnostic: ' + name)
                print('Startup fault check passed: ' + name, flush=True)
            finally:
                disabled.rename(component)



if __name__ == '__main__':
    main()
