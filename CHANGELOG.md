# 更新日志 / Changelog

自用 / Personal use。版本标签对应可回溯的代码快照。
Version tags identify reproducible source snapshots.

## v0.3.0 — 2026-09-22

### 新增与修复 / Added and fixed

- 精细删除：单击选择字符，或框选字符中心；红色预览、选中字数、Delete 提交、Esc 取消。
  Precise deletion: click a character or box-select character centers, review red highlights and counts, Delete to apply, Esc to cancel.
- 删除前寻找不与未选文字相交的区域，删除后核对未选字符的内容和位置；失败时恢复原文。
  Exclusive redaction regions protect neighboring glyphs; post-edit text/geometry validation rolls back unsupported layouts.
- 重做 Ctrl+Y / Ctrl+Shift+Z，支持跨页和加密文件；失败编辑保留重做分支，新编辑清空分支。
  Redo supports pages and encrypted files. Failed edits preserve the redo branch; new edits clear it.
- 撤销 / 重做共享历史预算；修复删除模式下中键平移被悬停逻辑截获。
  Shared undo/redo history budget; middle-button panning now works in deletion modes.
- 字符高亮合并成一个图形路径，避免每个字符创建一个场景对象。
  Character highlights share one graphics path instead of one scene object per character.

### 验证 / Validation

23 项本地回归测试：包含四种旋转下中英文字符删除与导出、紧邻两行保护、重叠字符拒绝与回滚、裁切斜体页面、跨页与加密撤销 / 重做，以及 Qt 选择、取消、删除和快捷键。运行生成文档缩放基准并检查界面截图。
23 local tests include mixed-text deletion/export at four rotations, close-line protection, overlap rejection and rollback, cropped italic pages, multi-page/encrypted undo/redo, and Qt selection/cancel/delete/shortcuts. Generated-document zoom benchmarks and UI screenshots were checked.

### 仍在计划中 / Still planned

自动按词选择、重新选中已应用文字后移动和修改，继续放在 v0.3.x。扫描图片及轮廓文字仍不支持删除；完全重叠的字符须一并选择；删除不自动重排文字。
Automatic word selection and re-editing applied text remain planned for v0.3.x. Scanned/outlined text is unsupported; fully overlapping characters must be selected together; deletion does not reflow text.

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
