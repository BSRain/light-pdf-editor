# v0.5.0 本机稳定性验收 / Local stability acceptance

自用 / Personal use。当前交付 v0.5.0-rc.9；未标记正式版。
Personal-use v0.5.0-rc.9; not the final release.

## 范围 / Scope

- 本机 Windows 11、已有 Python、单显示器原生缩放 125%。 / Local Windows 11 with Python installed, one monitor at native 125% scale.
- 清空便携子进程 Python 路径，移位到中文 / 空格目录。 / Relocate to Unicode/space paths and remove Python from the child PATH.
- 三种 QT_SCALE_FACTOR（1、1.5、2）检查窗口边界、按钮、鼠标缩放锚点、Qt 拖放事件和编辑导出。 / Three QT_SCALE_FACTOR values test bounds, controls, zoom anchoring, Qt drop events and editing/export.
- 实际后台 EXE 异常退出后，核对警告并重新打开未应用草稿的恢复副本。 / Crash the actual worker, verify its warning, and reopen a recovery snapshot with an unapplied draft.
- 移除工作进程或 Windows 平台插件时必须有明确启动错误，不应静默退出或停在无响应界面。 / Missing worker/platform-plugin faults must produce clear diagnostics.

## 尚待完成 / Pending

独立无 Python Windows；从资源管理器实际拖放；不同 DPI 的物理显示器之间移动窗口。暂时没有对应设备，按用户选择先完成本机验收。模拟缩放、Qt 事件注入及清空 PATH 均不能替代这些实测。
Independent Windows without Python, real Explorer drag/drop and physical monitor transitions at different DPI remain pending because the devices are unavailable. Simulated scaling/events and sanitized PATH do not replace them.

## 复现 / Reproduce

参照 [构建与矩阵命令](BUILD_WINDOWS.md)。报告位于每次验证新建目录中的 `结果/smoke-report.json`，故障场景另有 `fault-*/smoke-report.json`。只使用生成 PDF，不需要真实工作文件。
See [build/matrix commands](BUILD_WINDOWS.md). Each run retains `结果/smoke-report.json` and separate `fault-*/smoke-report.json` files, using generated PDFs only.
