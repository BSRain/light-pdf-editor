# 更新日志 / Changelog

自用 / Personal use。版本标签对应可回溯的代码快照。
Version tags identify reproducible source snapshots.

## v0.6.0-rc.1 — 2026-10-02

- 95 项源码回归通过。 / 95 source regressions pass.

- 新增 Ctrl+G 页码跳转、可收起的缩略图导航；每组最多 20 页，只渲染可见缩略图。 / Add Ctrl+G page jumps and collapsible lazy thumbnails, bounded to 20 items per group.
- 缩略图请求低于编辑、文字预览和页面分块优先级；不替换当前页显示列表缓存，过期结果不会写入新文档或新分组。 / Prioritize editing, text previews and tiles over thumbnails; preserve the active display cache and reject obsolete results.
- 保留文字草稿 / 图片擦除预览的翻页保护，增加导航回归及便携包导航往返自检。 / Preserve pending-preview guards, add navigation regressions and packaged navigation checks.
- 提供多页、大尺寸文字、图片文档的后台页面响应基准；不将其描述为完整界面延迟或优化幅度。 / Publish worker page-response baselines without claiming full UI latency or an unmeasured speedup.

## v0.5.0-rc.9 — 2026-10-02

- 89 项源码回归通过。 / 89 source regressions pass.

- 增加独立启动入口，检查工作进程和 Windows 界面组件缺失；启动异常提供双语说明和本地诊断日志。
  Add a launcher that detects missing worker/Windows UI components and reports startup exceptions with bilingual guidance and local logs.
- 便携自检扩展为拖放事件、缩放锚点、实际工作进程崩溃及未应用草稿恢复；预期提示框核对后自动关闭，其他弹窗判为失败。
  Extend packaged checks to drop events, pointer-anchored zoom, real worker crashes and draft recovery; verify/dismiss expected dialogs and fail on unexpected ones.
- 增加缺失工作进程 / 平台插件的实际 EXE 故障注入。独立无 Python Windows 与物理多显示器验收尚未完成，继续以候选版交付。
  Add actual-EXE missing-worker/platform-plugin fault injection. Clean Windows without Python and physical multi-monitor acceptance remain pending; this remains a candidate.

## v0.5.0-rc.8 — 2026-10-01

- 85 项回归通过。 / 85 regressions pass.

- 图片擦除增加自动底色、页面取色和自选颜色，先清除像素 / OCR 再填底色；取色完成前禁止确认，旧响应不会覆盖新颜色。
  Add automatic background sampling, page picking and custom fill; remove pixels/OCR before filling, wait for sampling before confirmation and ignore stale responses.
- 增加工具栏“图片擦除 / 填底色”入口；验证彩色底图、四种旋转和导出图片中原像素已清除。
  Add a direct image-erasure/fill toolbar entry; validate colored scans, rotations and removed source pixels in exported images.

## v0.5.0-rc.7 — 2026-10-01

- 82 项回归通过，覆盖真实鼠标移动 / 缩放、取消、保存保护、连续擦除导出。 / 82 regressions pass, including mouse move/resize, cancellation, save guards and consecutive-erasure exports.

- 图片擦除改为范围预览：松开鼠标不修改 PDF，支持拖动、八个调整手柄和方向键微调；按钮 / Ctrl+Enter 确认，Esc 取消。
  Image erasure now previews an adjustable region without editing on release; move, resize with eight handles or nudge, then confirm with the button/Ctrl+Enter or cancel with Esc.
- 确认后继续框选，支持连续擦除、逐次撤销；待确认选区阻止保存 / 翻页，Ctrl+Z 优先取消当前选区。
  Continue selecting after confirmation, with per-operation undo; pending regions block save/page changes and Ctrl+Z first cancels the pending region.

## v0.5.0-rc.6 — 2026-10-01

- 新增“擦除图片区域”：拖框松开后清除当前页图片的相交像素及文字层，保留矢量线条；支持撤销、重做和加密导出。
  Add image-region erasure: drag/release to blank intersecting pixels and remove text on the current page, preserving vectors; supports undo/redo and encrypted export.
- 验证四种页面旋转、像素清除、OCR 删除、导出原图清理、共享图片其他页不变、加密工程及鼠标框选。
  Validate four rotations, pixel/OCR removal, unused-original cleanup on export, shared-image page isolation, encrypted projects and mouse selection.

## v0.5.0-rc.5 — 2026-09-26

- 74 项回归通过；便携包补齐性能原始记录。 / 74 regressions pass; include raw benchmark records in the portable source bundle.

- 精细删除按纵向位置筛选可能重叠的保护字符，避免每个选中字符都遍历全页；超大或异常字符框回退完整扫描。
  Filter protected glyphs by vertical bands during precise deletion; oversized or abnormal boxes fall back to a full scan.
- 保留原始字符顺序、重叠区域保护、删除后内容 / 坐标验证及失败回滚。
  Preserve source order, overlap protection, post-deletion text/geometry validation and failure rollback.
- 生成的 3,600 字符页面删除 600 字符，工作进程响应三次中位耗时从 7,106.42 ms 降到 2,747.87 ms；结果含保护检查和缩略图，不代表所有文档。见 BENCHMARKS.md。
  On a synthetic 3,600-character page deleting 600 glyphs, median worker response falls from 7,106.42 to 2,747.87 ms over three runs, including safety checks and thumbnail generation. This is not a universal guarantee; see BENCHMARKS.md.

## v0.5.0-rc.4 — 2026-09-26

- 应用 / 取消按钮固定在属性面板底部，小窗口与高 DPI 下无需滚到底部才能操作。
  Keep Apply/Cancel below the scrollable properties in small/high-DPI windows.
- 始终提供内置中文字体；没有受支持的中文系统字体时默认选中。修正原“内置宋体”的不准确命名。
  Always offer the built-in Chinese font and default to it without supported Chinese system fonts; correct the misleading “built-in SimSun” label.
- 字体、字号、坐标、工具等控件只有获得焦点时才响应滚轮，避免滚动经过时误改值。
  Require keyboard focus before wheel changes to font, size, position or tool controls.
- 72 项回归通过，增加小窗口按钮可见与点击、仅英文系统字体下中文添加 / 重编辑、滚轮焦点保护；便携验证使用内置字体。
  72 regressions pass, including small-window visibility/click, Chinese insertion/re-edit with Latin-only font inventory and wheel focus; exercise the built-in font in packaged checks.

## v0.5.0-rc.3 — 2026-09-23

- 新增框内左 / 中 / 右对齐，多行文字按同一文字框对齐；预览、重编辑、工程与恢复保留设置。
  Add left/center/right alignment within text boxes, retained through previews, re-editing, projects and recovery.
- 使用精确字体度量修正旋转宋体的字符框偏移；按实际页面位置点击、逐字删除及相邻行保护已验证。
  Use accurate font metrics to fix displaced rotated SimSun boxes; verified visual-position clicks, per-character deletion and neighboring-row preservation.
- 新对齐字段采用工程格式版本 3，旧工程仍兼容；旧软件会拒绝新格式，避免忽略对齐设置。
  Alignment uses project schema version 3 while retaining legacy readers; older app versions reject the new schema rather than silently lose alignment.
- 69 项回归，覆盖中英文字体、四种旋转下的多行对齐、工程往返和旋转中文字形点击。
  69 regressions cover Chinese/English fonts, multiline alignment across four rotations, project roundtrips and visual clicks on rotated Chinese text.

## v0.5.0-rc.2 — 2026-09-23

- 复用 PDF 引擎的换行结果，按实际首 / 末行基线与字体下降部判断文字高度；修正大行距下单行文字误报溢出。字符宽度超过框宽时拒绝写入。
  Reuse PDF word wrapping and check actual first/last baselines plus font descent. Fix false single-line overflow with large spacing; reject boxes narrower than a glyph advance.
- 修正模拟加粗笔画宽度重复乘字号，防止宋体等字体粗成实心；已有原生粗体继续使用粗体字体文件。
  Remove duplicate font-size scaling in synthetic bold strokes, preventing over-thick SimSun and similar fonts; native bold variants remain preferred.
- 64 项回归，新增四种旋转下紧凑单行框的实际渲染检查、精确高度与水平溢出保护、三种字号的加粗像素覆盖率检查。
  64 regressions add rendered tight-box checks across four rotations, exact-height/horizontal-overflow protection and synthetic-bold ink coverage at three sizes.
- 固定便携构建使用的 Pillow 和打包工具依赖版本，使首次构建包含完整依赖与许可证。
  Pin Pillow and packaging dependencies for complete first-time builds and license collection.

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
