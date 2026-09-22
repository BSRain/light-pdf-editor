# 更新日志 / Changelog

自用 / Personal use。版本标签对应可回溯的代码快照。
Version tags identify reproducible source snapshots.

## v0.2.0 — 2026-09-22

### 新增 / Added

- Qt / PySide6 桌面界面，独立 PDF 进程，512 像素可见区域图块及缓存。
  Qt interface, isolated PDF process, visible 512-pixel tiles and caching.
- 原文基线 / 边缘吸附、参考线、字体大小 / 颜色 / 粗细取样，以及明确的字体替代提示。
  Baseline/edge snapping, guides, style sampling and explicit font fallback.
- 工具栏框选删除和点选删除入口。点选时红框预览整个文字段，点击后真正移除文字，可撤销。
  Dedicated box/click deletion tools. Hover highlights the text span; clicking removes its text and supports undo.
- 定位框获得焦点时，Delete / Backspace 删除待添加文字框；不删除原 PDF 内容。
  Delete/Backspace removes a focused draft without modifying the original PDF content.
- 版本号、双语路线图、可复现交互基准测试。
  Version metadata, bilingual roadmap and reproducible interaction benchmark.

### 保留与改进 / Preserved and improved

- 中文 / 英文、多行、字体、加粗、颜色、拖动拉伸、拖放、多页、撤销、另存为。
  Chinese/English text, multiline layout, fonts, bold, color, box manipulation, file drops, pages, undo and save-as.
- 加密 PDF 在撤销与导出后保留加密；修复任意尺寸文字框的浮点边界误判。
  Encryption preserved through undo/export; fixed fractional text-box boundary checks.
- 移动文字框不重排整页；滚轮只变换 Qt 图像；过期后台结果不会覆盖当前内容。
  Moving text no longer reprocesses the page; zoom transforms Qt graphics; stale worker results are ignored.

### 验证 / Validation

15 项本地回归测试通过，覆盖核心编辑、加密、旋转页面基线、Qt 拖放、移动 / 拉伸、删除 / 撤销 / 导出、缩放与独立进程。已检查界面及 pythonw 启动路径。
15 local regression tests cover editing, encryption, rotated baselines, Qt drops, movement/resizing, deletion/undo/export, zoom and process isolation. UI and pythonw startup were checked.

### 已知限制 / Known limitations

扫描件与轮廓文字不支持文字删除或基线吸附；点选删除按 PDF 文字段进行，不是按单字。没有本机对应字体时无法保证字形完全一致。更精细编辑见 [路线图 / roadmap](ROADMAP.md)。
Scanned/outlined text is unsupported for text removal/snapping. Click deletion operates on PDF text spans, not individual characters. Exact font matching requires a suitable local font.

## v0.1.0 — Historical baseline / 历史基线

首个 Tkinter 版本，提交 `e80a4e9`：基础增删文字、拖放、加粗、定位框、缩放和中英文自用说明。
Initial Tkinter version at `e80a4e9`: text insertion/removal, drag-and-drop, bold, positioning, zoom and bilingual personal-use documentation.
