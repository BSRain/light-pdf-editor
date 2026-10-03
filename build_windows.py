"""Build a Windows x64 portable directory and ZIP using the pinned build tools."""
import hashlib
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import zipfile
from version import __version__

ROOT = Path(__file__).resolve().parent


def safe_build_path(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ROOT) or path == ROOT:
        raise RuntimeError('Build output must remain inside the repository workspace.')
    return path


def main():
    if sys.platform != 'win32':
        raise SystemExit('Build this package on Windows.')
    # PyInstaller may replace its COLLECT directory; validate before invoking it.
    output = safe_build_path('dist/LightPDFEditor')
    dist = safe_build_path('dist')
    work = safe_build_path('build')
    release = safe_build_path('releases')
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--distpath', str(dist),
                    '--workpath', str(work), str(ROOT/'light_pdf_editor.spec')], cwd=ROOT, check=True)
    source = output / 'source'
    source.mkdir(exist_ok=True)
    selected = [p for p in ROOT.iterdir() if p.is_file() and (
        p.suffix in ('.py', '.md', '.spec') or p.name.startswith('requirements') or
        p.name == 'start.bat' or p.name.startswith('ui_') and p.suffix == '.png')]
    for path in selected:
        shutil.copy2(path, source / path.name)
    benchmark_source = source / 'benchmarks'
    benchmark_source.mkdir(exist_ok=True)
    for path in (ROOT / 'benchmarks').glob('*.json'):
        shutil.copy2(path, benchmark_source / path.name)
    packages = ('PyMuPDF', 'PySide6', 'PySide6_Essentials', 'PySide6_Addons', 'shiboken6', 'Pillow', 'PyInstaller')
    notices = []
    for package in packages:
        distribution = metadata.distribution(package)
        notices.append(f'{package} {distribution.version}')
        for item in distribution.files or []:
            parts = Path(str(item)).parts
            if '..' in parts:
                continue
            if not any('license' in part.lower() or part.lower().startswith(('copying', 'notice')) for part in parts):
                continue
            path = Path(distribution.locate_file(item))
            if path.is_file():
                target = output / 'licenses' / package / Path(str(item))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
    python_license = Path(sys.base_prefix) / 'LICENSE.txt'
    if python_license.exists():
        target = output/'licenses'/'Python-LICENSE.txt'
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(python_license, target)
    (output/'THIRD_PARTY_NOTICES.txt').write_text('\n'.join(notices)+'\n\nLicense texts are included under licenses/.\n', encoding='utf-8')
    (output/'START_HERE.txt').write_text(
        '轻简 PDF / Light PDF Editor '+__version__+' — 自用 / Personal use\n\n'
        '完整解压后双击 LightPDFEditor.exe；保留 _internal 和 PdfWorker.exe。\n'
        'Extract the entire ZIP, then run LightPDFEditor.exe. Keep _internal and PdfWorker.exe beside it.\n'
        '使用说明和本版本源代码位于 source/。 / Documentation and matching source are in source/.\n'
        '验收范围：本机自用；无 Python 的全新 Windows 环境及物理多显示器尚未验证。\n'
        'Validated for local personal use; clean Windows without Python and physical multi-monitor checks remain pending.\n', encoding='utf-8')
    release.mkdir(exist_ok=True)
    archive = release / f'LightPDFEditor-{__version__}-windows-x64.zip'
    with zipfile.ZipFile(archive, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
        for path in sorted(output.rglob('*')):
            if path.is_file():
                bundle.write(path, Path('LightPDFEditor') / path.relative_to(output))
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    checksum = archive.with_suffix('.zip.sha256')
    checksum.write_text(f'{digest}  {archive.name}\n',encoding='utf-8')
    print(json.dumps(dict(archive=str(archive), sha256=digest, size_mb=round(archive.stat().st_size/1024**2,2))))


if __name__ == '__main__':
    main()
