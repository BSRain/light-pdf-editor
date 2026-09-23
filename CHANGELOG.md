# 更新日志 / Changelog

自用 / Personal use。版本标签对应可回溯的代码快照。
Version tags identify reproducible source snapshots.

## v0.5.0-rc.1 — 2026-09-23

- 新增 Windows x64 便携构建、GUI / PDF 工作进程分离的无控制台 EXE、Windows 文件版本信息和 SHA-256 校验文件。
  Add Windows x64 portable builds, separate windowless GUI/PDF worker executables, Windows version resources and SHA-256 checksums.
- 打包附带对应源码、使用说明和依赖许可证；工作进程适配打包目录与继承管道，不依赖系统 Python 命令。
  Bundle matching source, documentation and dependency licenses; adapt worker discovery and inherited pipes without relying on a system Python command.
- 本机移位、中文空格路径、删除、填字、工程往返和加密导出自检；全新无 Python 系统和物理多显示器验证尚未完成，作为候选版发布。
  Local relocated Unicode/space-path checks exercise deletion, insertion, project roundtrips and encrypted export. Clean Windows without Python and physical multi-monitor tests remain pending; this is a release candidate.

## v0.4.2 — 2026-09-23

- 可选自动恢复副本：选择目录后首次保存，约每 30 秒检查，跳过未变化内容，后台保存不丢弃预览与渲染请求。
  Optional recovery snapshots save initially and check about every 30 seconds, skipping unchanged content without discarding preview/render requests.
- 恢复新增草稿和重新编辑草稿；保留应用 / 取消语义、PDF 加密、未保存标记和撤销历史。空草稿及尚未排下的草稿也能保存。
  Restore new and re-edit drafts while retaining apply/cancel semantics, encryption, dirty state and undo history. Empty and overflowing drafts can be snapshotted.
- 保存失败暂停备份并显示原因；原子更新保留上次成功副本。每次启用独立文件，避免多个窗口互相覆盖。
  Failures pause backups with a visible explanation; atomic replacement preserves the last successful copy. Each activation uses a unique file to avoid cross-window collisions.
- 61 项回归，包含真实终止进程后的草稿恢复、重新编辑取消还原、加密草稿、写入失败与状态保护。
  61 regressions include actual worker termination and draft recovery, canceling recovered re-edits, encrypted drafts, write failures and state preservation.

## v0.4.1 — 2026-09-23

- 新增 `.lpdf` 独立工程保存及打开、拖放。当前 PDF 快照和已应用文字框一起保存，重开恢复位置、字体设置、行距和编辑能力。
  Save/open/drop standalone .lpdf projects containing a PDF snapshot and applied editable boxes, restoring position, font settings, spacing and editing.
- 验证工程版本、页面内容 / 几何签名和文字流标识；损坏工程不会替换当前文档。保存采用同目录临时文件及原子替换。
  Validate format versions, page content/geometry signatures and object streams; reject invalid projects without replacing the active document. Save through same-directory temporary files and atomic replacement.
- 加密工程保留 PDF 密码保护；普通 PDF 导出移除工程编辑记录。工程不依赖原稿路径，不携带撤销历史、草稿或字体文件。
  Retain PDF encryption; strip project editing metadata from regular exports. Projects are source-independent and omit undo history, drafts and font files.
- 自动保存与崩溃草稿恢复拆分到 v0.4.2，先交付可验证的手动工程往返流程。
  Autosave and crash-draft recovery move to v0.4.2; this release delivers the manually saved project roundtrip.

## v0.4.0 — 2026-09-23

- 多栏吸附优先附近文本；取样估计同列相邻基线距离，新增可编辑行距，重新编辑和撤销保留设置。
  Prefer nearby column text when snapping; sample adjacent baseline pitch, edit line spacing and retain it through re-editing and undo.
- 完整矢量边框单元格点击填字，自动设置 4 pt 内边距，支持旋转页面；不完整边框提示手动定位。
  Click fully bordered vector cells for placement with 4 pt padding, including rotated pages; incomplete borders require manual placement.
- 改进导入字体家族匹配，避免窄体误匹配；修正底层字体上升部造成的行距偏差，提交前检查文字高度。
  Improve imported font-family matching and narrow-font fallback; compensate font-ascender line-pitch differences and check height before committing text.
- 新增排版和 Qt 回归，覆盖中英文字体、加粗、四种旋转、行距导出、重编辑、表格点击及溢出无修改。
  Layout and Qt regressions cover Chinese/English fonts, bold, four rotations, exported pitch, re-editing, cell clicks and non-mutating overflow rejection.

## v0.3.3 — 2026-09-23

- 处理进程异常退出后禁用编辑，提供重启及重新打开最近导出 / 原稿入口；未保存内容需确认放弃，右侧文字可复制。丢弃旧命令和过期结果。
  Worker-exit recovery disables editing, offers restart/reopen of the last export or source, confirms discarding unsaved work, preserves copyable input text, and rejects stale commands/results.
- 工作流基准覆盖生成的 80 页 PDF、大尺寸页面、约 31 MiB 图片 PDF；报告 P50/P95、原始样本和后台峰值工作集。
  Workflow benchmarks cover 80-page, large-page and approximately 31 MiB image PDFs, with P50/P95, raw samples and worker peak working set.
- 导出跳过重复流比较，保留未引用对象清理和编号整理。80 页用例保存 P50 从 4069.89 ms 降到 127.79 ms（各 5 次，本机生成用例；部分文件可能更大）。
  Export skips duplicate-stream comparisons while retaining unused-object cleanup and xref compaction. The generated 80-page fixture save P50 fell from 4069.89 to 127.79 ms across five local runs; some outputs may be larger.
- 42 项回归测试，包含真实终止后台进程、编辑中断、重启取消、保存文件不变与重启后继续编辑。详情见 [性能报告 / benchmarks](BENCHMARKS.md)。
  42 regressions include actual worker termination, interrupted edits, canceled restart, unchanged saved files and post-restart editing.

自动恢复未保存修改尚未实现；此次提供重新打开已保存文件的恢复入口。
Automatic recovery of unsaved changes is not implemented; this release reopens saved files.

## v0.3.2 — 2026-09-22

- 删除文字后保留远离删除区域的独立文字框；精细选区重新映射字符编号。相交及连锁重叠的文字框保守转为普通 PDF 文字，撤销恢复。
  Preserve independent text boxes across deletion and remap precise character IDs. Affected/overlapping clusters become ordinary PDF text, reversible with undo.
- 保留文字框重新挂接时恢复所需字体资源，修复中文乱码；保持独立文字框的绘制顺序。
  Restore required font resources when reattaching preserved boxes, fixing Chinese corruption; preserve relative box paint order.
- 点击重叠框时可按文字摘要和坐标选择目标，取消不改变文档。
  Select overlapping boxes by text excerpts and coordinates; cancellation leaves the document unchanged.
- 路线图明确四个后续阶段：稳定性与性能、对齐排版、编辑工程与恢复、Windows 便携交付。
  Roadmap defines stability/performance, alignment, editable projects/recovery and portable Windows delivery.

38 项回归测试覆盖删除后继续编辑、中文字体与像素保留、加密 / 旋转导出、重叠框选择、撤销 / 重做及既有功能。
38 regression tests cover continued editing after deletion, Chinese font/pixel preservation, encrypted/rotated export, overlapping-box selection, history and existing behavior.

## v0.3.1 — 2026-09-22

### 新增与改进 / Added and improved

- “编辑新增文字”：重新选择本次会话新增的文字，移动、拉伸、改字及调整样式；旧文字从预览隐藏，应用后替换，取消恢复。修改支持撤销 / 重做。
  Re-edit session-created text: move, resize, change text/style, preview without the old text, apply replacement or cancel. Updates support undo/redo.
- 精细删除模式双击选择词段，按空白 / 标点分界；中文选择连续汉字段，不做语义分词。
  Double-click token selection in precise deletion, using whitespace/punctuation boundaries; contiguous CJK runs, without semantic segmentation.
- 替换新增文字通过移除对应页面内容引用完成，不涂除覆盖区域，因此保留下方原文。另存为使用副本整理，保存后仍能继续编辑当前会话。
  Replacements detach the inserted content references instead of redacting the area, preserving underlying text. Export compacts a copy and retains active session references.
- 加密文档、旋转页面及失败编辑恢复纳入回归；文字删除后明确提示该页已有文字框的编辑限制。
  Encryption, rotated pages and failed-edit recovery are covered by regressions; page deletion reports its impact on existing text-box editing.

### 验证 / Validation

33 项回归测试通过，含 Qt 重新选中 / 拖动 / 改字 / 取消 / 双击选词、跨页撤销重做、重叠原文保护、四种旋转的加密导出、保存后继续编辑。已运行缩放基准并检查重新编辑界面截图。
33 passing tests include Qt reselect/drag/update/cancel/token selection, cross-page history, overlapping-original protection, encrypted export at four rotations, and continued editing after save. Zoom benchmarks and re-edit UI screenshots were checked.

### 限制 / Limits

重新编辑仅跟踪本次打开后新增的文字，关闭 / 重开后不恢复文字框。删除文字会使该页先前新增的文字框失去编辑记录，撤销可恢复；其他页不受影响。重叠框优先选择后添加的框。
Re-editing tracks text inserted during the current open-document session only. Reopening does not restore boxes. Redaction retires existing boxes on that page; undo restores them, and other pages are unaffected. Overlaps select the most recently inserted box.

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
