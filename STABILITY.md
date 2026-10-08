# 本机稳定性验收 / Local stability acceptance

当前交付 v0.7.0 自用版，验收范围限于下面列出的本机环境；外部验收未因此标记通过。
Current delivery: v0.7.0 for personal use, validated only in the local environment below; external acceptance is not claimed.

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

## v0.6 继承验收 / Continued acceptance

v0.6.0-rc.1 继续使用上述本机矩阵，增加可见缩略图、页码往返和打开导航栏后的窗口边界检查。每个版本的实际结果随 Release 附带的 stability JSON 发布；v0.5 的外部设备验收仍待完成。
v0.6.0-rc.1 extends the same local matrix with visible thumbnails, page-jump roundtrips and window bounds with navigation open. Actual results ship in the release stability JSON; external-device acceptance from v0.5 remains pending.

v0.6.0-rc.2 额外检查删除后翻页再返回，防止命中旧缓存；源码回归覆盖字节预算、保存状态、回滚、加密换文档及四种旋转裁剪坐标。
v0.6.0-rc.2 additionally revisits a page after deletion to detect stale cache results; source tests cover byte budgets, save state, rollback, encrypted document switches and four rotations with cropping.

v0.6.0-rc.3 在实际 EXE 中增加清晰预览过渡检查：新分块到齐前保留旧层，到齐后必须清理；继续执行三档模拟缩放和缺失组件检查。
v0.6.0-rc.3 adds an actual-EXE sharp-preview transition check: retain the previous layer until new tiles arrive, then remove it; keep the three-scale and missing-component checks.

v0.6.1 增加源码故障注入：真实挂起进程、超长通信输出、协议错配、日志写入失败、忙碌时确认 / 取消重启和矩形删除异常回滚。便携自检新增正常进程手动重启确认及文件重开。
v0.6.1 adds source fault injection for hung workers, oversized output, protocol mismatch, log failures, busy restart confirmation/cancellation and unsafe rectangle rollback. Packaged checks additionally verify live-worker restart confirmation and reopening.

v0.7.0 增加真实中英 OCR、选区坐标、像素上限、语言包缺失、取消 / 超时隔离、预览与提交像素一致、转换整体回滚、四种旋转下裁切加密工程重开编辑及撤销。便携自检增加离线识别、校对、确认转换、撤销重做及导出。
v0.7.0 adds real Chinese/English OCR, coordinates, pixel bounds, missing-model handling, cancellation/timeout isolation, preview/commit pixel equality, rollback and rotated/cropped encrypted project editing. Packaged checks cover recognition, correction, confirmation, undo/redo and export.
