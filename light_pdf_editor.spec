# Build both windowless executables into one directory, sharing bundled libraries.
from pathlib import Path
from version import __version__
from PyInstaller.utils.win32.versioninfo import VSVersionInfo, FixedFileInfo, StringFileInfo, StringTable, StringStruct, VarFileInfo, VarStruct
root = Path(SPECPATH)
core_version = tuple(int(n) for n in __version__.split('-')[0].split('.')) + (0,)
info = VSVersionInfo(ffi=FixedFileInfo(filevers=core_version, prodvers=core_version,
    mask=0x3f, flags=2 if '-' in __version__ else 0, OS=0x40004, fileType=1, subtype=0, date=(0,0)),
    kids=[StringFileInfo([StringTable('040904B0', [
        StringStruct('FileDescription', 'Light PDF Editor - Personal Use'),
        StringStruct('FileVersion', __version__), StringStruct('ProductName', 'Light PDF Editor'),
        StringStruct('ProductVersion', __version__)])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])])

gui = Analysis([str(root / 'app_entry.py')], pathex=[str(root)],
               binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=[])
worker = Analysis([str(root / 'worker_entry.py')], pathex=[str(root)],
                  binaries=[], datas=[], hiddenimports=[], hookspath=[], runtime_hooks=[], excludes=['PySide6'])
gui_pyz = PYZ(gui.pure)
worker_pyz = PYZ(worker.pure)
gui_exe = EXE(gui_pyz, gui.scripts, [], exclude_binaries=True, name='LightPDFEditor',
              debug=False, strip=False, upx=False, console=False, version=info)
worker_exe = EXE(worker_pyz, worker.scripts, [], exclude_binaries=True, name='PdfWorker',
                 debug=False, strip=False, upx=False, console=False, version=info)
collection = COLLECT(gui_exe, worker_exe, gui.binaries, gui.datas, worker.binaries, worker.datas,
                     strip=False, upx=False, name='LightPDFEditor')
