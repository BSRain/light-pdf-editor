# Windows 便携版构建 / Portable Windows builds

当前候选版：v0.5.0-rc.9。自用 / Personal use。

## 使用 / Run

从 GitHub 版本页面下载 Windows x64 ZIP，完整解压后双击 `LightPDFEditor.exe`。`PdfWorker.exe` 与 `_internal` 必须保留在同一目录；无需手工安装项目的 Python 依赖。使用说明及对应源代码在 `source/`，依赖许可证在 `licenses/`。

Download the Windows x64 ZIP from the GitHub release, extract everything and run `LightPDFEditor.exe`. Keep `PdfWorker.exe` and `_internal` beside it. Project Python dependencies are bundled. Matching source/documentation live in `source/`; dependency licenses live in `licenses/`.

候选版尚未完成「未安装 Python 的全新 Windows」及物理多显示器验证。清空子进程 PATH 的本机测试不能代替干净机器测试。没有代码签名证书，软件包不宣称已经通过 SmartScreen 信誉验证。

Clean Windows without Python and physical multi-monitor validation are pending. A local test with Python removed from the child PATH does not replace clean-machine testing. The package is not code-signed and does not claim SmartScreen reputation validation.

## 复现构建 / Reproduce

在 Windows x64、Python 3.12 环境中： / On Windows x64 with Python 3.12:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements-build.txt
.venv\Scripts\python.exe -m unittest discover -q
.venv\Scripts\python.exe build_windows.py
.venv\Scripts\python.exe verify_portable.py releases\LightPDFEditor-0.5.0-rc.9-windows-x64.zip
```

构建脚本验证输出目录位于仓库内，再调用 PyInstaller；只替换 `dist/LightPDFEditor` 构建产物。ZIP 与 SHA-256 文件位于 `releases/`，不会加入 Git 源代码历史。版本代码使用 Git 标签管理，ZIP 作为对应 GitHub Release 附件。

The builder validates repository-contained output paths before PyInstaller replaces its output directory. ZIP and SHA-256 files are written under `releases/` and excluded from Git source history. Code uses version tags; binaries are attached to the matching GitHub release.

验证器把 ZIP 解压到独立的中文 / 空格目录，并让 EXE 在只含 Windows System32 的 PATH 下运行。程序自己的显式 `--smoke-test <directory>` 模式生成示例 PDF，检查渲染、填字、撤销 / 重做、工程重开及导出，并写出报告和截图。该模式只在明确传入参数时运行。

The verifier extracts into a separate Unicode/space-containing path and launches the EXE with only Windows System32 on PATH. The application's explicit `--smoke-test <directory>` mode generates a synthetic PDF and checks rendering, insertion, undo/redo, project reopen and export, then writes a report and screenshot. This mode runs only when explicitly requested on the command line.

## 实现参考 / Implementation references

界面与 PDF 工作进程分别打包为无控制台 EXE，共用动态库。打包后通过 EXE 所在目录定位工作进程；窗口模式下使用继承的 Windows 管道句柄恢复标准输入输出。

The UI and PDF worker are separate windowless executables sharing bundled libraries. The worker is located beside the GUI executable; inherited Windows pipe handles provide standard I/O in windowless mode.

- [PyInstaller runtime paths](https://pyinstaller.org/en/stable/runtime-information.html)
- [PyInstaller windowless standard I/O behavior](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html)
- [Microsoft GetStdHandle](https://learn.microsoft.com/en-us/windows/console/getstdhandle)
- [Microsoft _open_osfhandle ownership](https://learn.microsoft.com/en-us/cpp/c-runtime-library/reference/open-osfhandle?view=msvc-170)

## 本机稳定性矩阵 / Local stability matrix

```powershell
.venv\Scripts\python.exe verify_portable.py releases\LightPDFEditor-0.5.0-rc.9-windows-x64.zip --scale 1 --fault-checks
.venv\Scripts\python.exe verify_portable.py releases\LightPDFEditor-0.5.0-rc.9-windows-x64.zip --scale 1.5
.venv\Scripts\python.exe verify_portable.py releases\LightPDFEditor-0.5.0-rc.9-windows-x64.zip --scale 2
```

故障检查仅重命名验证器新解压目录中的两个组件，验证可读错误后恢复；不修改源程序包或用户文档。模拟缩放和 Qt 拖放事件不能替代跨物理显示器移动和资源管理器真实拖放验收。
Fault checks temporarily rename two components only in the verifier's freshly extracted directory and restore them afterwards. Simulated scale/drop events do not replace physical monitor transitions or Explorer drag/drop acceptance.
