# v0.9.0 交付说明 / Handoff

自用 / Personal use。按需求加入局部 OCR 转换，保留实际问题修复；仓库未归档。软件在本机处理文件，不上传工作 PDF。
Region OCR conversion is available; actual-use fixes remain possible. The repository is not archived. Documents are processed locally.

## 安装与更新 / Install and update

从 [v0.9.0 Release](https://github.com/BSRain/light-pdf-editor/releases/tag/v0.9.0) 下载 Windows x64 ZIP，解压到新目录，运行 `LightPDFEditor.exe`。保留同目录的 `PdfWorker.exe`、`_internal`、`ocr_data`。关闭旧程序再启动新版本；自己的 PDF、`.lpdf` 工程及恢复副本保留在原有位置，不要覆盖到程序目录。需要回退时，关闭新版后运行之前版本。
Download the Windows x64 ZIP from the release, extract into a new directory and run `LightPDFEditor.exe`. Keep `PdfWorker.exe`, `_internal` and `ocr_data`. Close the old application first; keep your PDFs, `.lpdf` projects and recovery copies separately. To roll back, close this version and run a previous release.

ZIP 旁提供 SHA-256 校验文件。PowerShell 命令：`Get-FileHash .\LightPDFEditor-0.9.0-windows-x64.zip -Algorithm SHA256`，对照附件中的值。依赖许可证位于 `licenses/`，对应源码与文档位于 `source/`。
Compare the PowerShell hash with the release checksum. Dependency licenses are in `licenses/`; matching source and docs are in `source/`.

## 常用操作 / Daily workflows

| 任务 / Task | 操作 / Workflow |
| --- | --- |
| 添加并对齐文字 / Add aligned text | 先取样原文样式，再输入文字、点击定位；拖动 / 边角缩放，应用。 / Sample nearby text, type, place, drag/resize and apply. |
| 删除可提取文字 / Delete extractable text | 精细删除工具选择字符，核对红色预览后删除。 / Select characters with precise deletion, review the red selection, then delete. |
| 删除扫描图片文字 / Erase raster text | 图片擦除 / 填底色 → 拖框 → 调整范围 → 自动底色、页面取色或自选颜色 → 确认擦除。 / Image erase/fill → draw/adjust a box → auto/sample/custom background → confirm. |
| 保留可编辑框 / Keep editable boxes | 保存为 `.lpdf` 工程；普通 PDF 重开不会恢复这些框。 / Save an `.lpdf` project; regular PDF reopening does not restore editable boxes. |
| 导出 / Export | 应用或取消待确认预览，再“另存为”新 PDF；重新打开核对结果。 / Apply/cancel pending previews, save a new PDF, then reopen to check. |
| 自动恢复 / Recovery | 每次打开文件后按需启用自动恢复副本，选择本地目录；崩溃后打开最近成功副本。 / Enable recovery for each opened document and choose a local folder; reopen the latest successful copy after a crash. |
| 导航与缩放 / Navigation and zoom | Ctrl+G 跳页；页面导航显示缩略图；滚轮缩放，中键平移，Shift+滚轮滚动。 / Ctrl+G jumps, navigation shows thumbnails, wheel zooms, middle button pans, Shift+wheel scrolls. |
| 撤销 / 取消 / Undo and cancel | Ctrl+Z 撤销已应用操作；Esc 取消当前预览；Ctrl+Enter 应用。 / Ctrl+Z undoes applied changes; Esc cancels a preview; Ctrl+Enter applies. |

## 已知范围 / Known limits

- 正式交付范围是本机 Windows 自用。独立未安装 Python 的 Windows、资源管理器真实拖放、物理不同 DPI 显示器间移动尚未验证；模拟缩放、Qt 拖放事件与清空 PATH 不能替代它们。软件未签名。 / Release scope is locally validated Windows personal use. Clean Windows without Python, real Explorer drops and physical mixed-DPI transitions remain unverified; simulations are not substitutes. The app is unsigned.
- 支持受限单段原文修改，不支持任意原文重排。扫描件可局部 OCR 转为可编辑文字；未转换区域仍是图片。 / Supported single-span edits, without arbitrary original-text reflow; scanned regions can be converted with OCR, while unconverted regions remain images.
- 图片擦除填纯色，不重建渐变、纹理或照片细节；保存后检查效果。 / Image erasure fills solid color, not reconstructed gradients, textures or photo detail; inspect the saved result.
- 删除操作不清除原始文件、旧导出、工程或恢复副本中的历史内容；撤销历史有容量限制。 / Erasure does not clear original files, older exports, projects or recovery copies; undo history is bounded.
- 缺少原字体时需要替代字体；字体文件不随工程打包。 / Missing fonts require substitution; projects do not bundle external font files.
- 不能在保留当前会话的前提下中断单次渲染；可确认停止并重启整个工作进程，复杂文件也有请求超时保护。缓存改善主要针对重访页面；缩放减少排队工作可能增加停止后的补清晰时间。 / A render cannot be interrupted while retaining the current session; confirmed worker restart and request deadlines provide an escape. Complex files may wait; caches primarily benefit revisits, and less queued zoom work may increase settling time.

## 遇到问题 / Troubleshooting

记录版本、Windows 缩放比例、操作步骤、错误文字、能否稳定复现。优先提供生成或脱敏样例；不要直接上传真实工作文件。启动诊断日志通常位于 `%LOCALAPPDATA%\LightPDFEditor\logs`，可能含本地路径，分享前自行检查。工作进程退出时可重启或打开恢复副本；未保存且未备份的操作不能保证恢复。
Record version, Windows scale, steps, exact error and reproducibility. Prefer generated or sanitized examples; do not directly upload work documents. Startup logs usually live under `%LOCALAPPDATA%\LightPDFEditor\logs` and may contain local paths; review before sharing. Restart or open a recovery copy after a worker exit; unsaved changes without a successful backup are not guaranteed recoverable.

## 交付与后续 / Delivery and next steps

Release 提供 ZIP、SHA-256 和本机稳定性 JSON；复现命令见 [构建说明](BUILD_WINDOWS.md)，测试边界见 [稳定性说明](STABILITY.md)，性能收益与取舍见 [性能报告](BENCHMARKS.md)。本次新增局部 OCR 转换。建议实际稳定使用 1～2 周后再决定是否归档；有问题优先修复当前版本。
The release includes ZIP, SHA-256 and local stability JSON. See build commands, acceptance scope and benchmark tradeoffs in the linked documents. Further features depend on actual needs. Consider archiving after 1–2 weeks of stable actual use; prioritize fixes to the current version.

## v0.9.0 卡住时的处理 / Unresponsive worker

可直接点击“重启处理进程”，默认选择取消；确认会放弃未保存修改并中止工作进程。若有恢复副本，可重新打开最近成功的副本。请求到达 120 秒（打开 / 编辑 / 保存等为 300 秒）会自动停止并提示。保存是否已经完成需要核对输出文件。错误提示中的本地 worker 日志可能含路径及 stderr 中的文档信息，不要未经检查直接分享。
Use “重启处理进程” to stop/restart; cancellation is the default. Confirmation abandons unsaved changes. Reopen a successful recovery copy if available. Requests automatically stop after 120 seconds (300 for open/edit/save and similar operations). Check output files to determine whether saving completed. Review local worker logs for paths/document details before sharing.

OCR 使用步骤及限制见 [中文说明](README.md#ocr扫描图片转为可编辑文字v080) / [English](README.en.md)。

OCR 默认逐行生成独立文字框，校对时选择行，可分别调整位置、字号和颜色。仍保留整块模式。整个选区会填纯色，请避开扫描表格线和图标；本次未增加表格线保护。 / OCR now defaults to independent line boxes with per-line position, size and color controls; whole-block mode remains. The whole selection is filled, so avoid raster rules/icons; table-line protection was not added.

## v0.9.0 新操作 / New workflows

选择“修改原有文字”后点击原文，在实际 PDF 预览中确认修改；复用受支持的原字体，缺字或复杂绘制会拒绝。工具栏左右旋转按钮处理当前页并保存到 PDF。旋转后的新增文字框需旋回创建方向后再拖动编辑；格式 4 工程需新版打开。 / Click original text in the new tool, review and apply using its supported original font. Missing glyphs or unsupported rendering are refused. Toolbar rotation affects and saves the current page. Restore a box’s creation orientation before editing it; format 4 projects require the new version.
