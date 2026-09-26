# 后续版本计划 / Roadmap

> 自用 / Personal use。以下是计划，不代表已实现；按实际使用反馈调整优先级，不预设发布日期。
> Planned work, not released features. Priorities follow personal-use feedback; no release dates are promised.

## 当前版本 / Current: v0.5.0-rc.3

Qt 界面、独立 PDF 处理进程、可见区域分块渲染、原文基线与边缘吸附、字体样式取样、增删文字、字符 / 词段选择与删除预览、本次会话新增文字再次编辑、重叠框选择、删除后保留独立文字框、相邻文字保护、加粗、撤销 / 重做、拖放、加密文件保存。

Qt UI, isolated PDF worker, viewport tiles, baseline/edge snapping, style sampling, text insertion/deletion, character/token selection with deletion preview, session-created text re-editing, overlapping-box picker, independent boxes preserved across deletion, neighboring-text checks, bold, undo/redo, drag-and-drop, encrypted export.

当前候选版补充了紧凑文字框高度判断、单字符宽度保护和模拟加粗修复；并已修正旋转文字选择框，新增框内居中 / 右对齐。 / The current candidate fixes compact text fitting, glyph-width overflow, synthetic bold and rotated selection geometry, and adds centered/right-aligned text boxes.

## 分阶段计划 / Next versions

按下列顺序推进；每阶段先完成测试再发布。版本是工作批次，不代表承诺的交付日期。
Work proceeds in this order, with tests before each release. Versions identify work batches, not promised delivery dates.

| 顺序 / Order | 版本 / Version | 计划内容 / Planned work | 验收标准 / Acceptance |
| --- | --- | --- | --- |
| 已发布 / Released | v0.4.0 对齐排版 / Alignment | 优先解决表格 / 多栏定位、行距取样、字体家族和粗细匹配；吸附优先考虑附近同列文字。 / Table/column alignment, line-spacing sampling, font-family/weight matching and local-column snap priority. | 中英文表格、多栏、旋转页面的添加位置可复现；替代字体有提示；拖动不因吸附跨列跳动。 / Reproducible placement across mixed-language tables, columns and rotations; explicit fallback; no cross-column snap jumps. |
| 已发布 / Released | v0.4.1 编辑工程 / Editable projects | 独立快照和文字框往返；保留加密。 / Standalone snapshot and editable-box roundtrips with encryption. | 四种旋转、源文件移除、损坏拒绝、加密与界面往返已验证。 / Validated rotations, missing source, corruption rejection, encryption and UI roundtrip. |
| 已发布 / Released | v0.4.2 自动恢复 / Recovery | 可选自动保存、未应用草稿恢复。 / Optional autosave and unapplied draft recovery. | 恢复不覆盖原稿；加密文档不明文保存密码或解密副本；失败不阻塞编辑。 / Preserve originals and encryption, never persist passwords; failure must not block editing. |
| 3 | v0.5.0 Windows 交付 / Windows delivery | 便携 EXE、依赖打包、高 DPI / 多显示器适配、无 Python 环境验证。 / Portable EXE, bundled dependencies, high-DPI/multi-monitor support, clean-machine validation. | 无 Python 的 Windows 测试环境可打开、拖放、编辑、撤销并导出；提供安装包哈希与已知限制。 / Open/drop/edit/undo/export on Windows without Python; published package hashes and limitations. |

## 本轮进展 / Current: v0.5.0-rc.3

- Windows x64 便携候选版、共享依赖的无控制台界面 / 工作进程、构建脚本、对应源码与许可证、SHA-256 校验值。 / Portable Windows x64 candidate, windowless GUI/worker with shared libraries, build scripts, matching source/licenses and SHA-256 checksums.
- 已完成本机移位 / 中文空格路径验证；全新无 Python 系统和物理多显示器仍待验证，因此尚不标为 v0.5.0 正式版。 / Relocated Unicode/space-path local validation; clean Windows without Python and physical multi-monitor checks remain pending, so v0.5.0 is not yet final.

### v0.4.2 已完成 / Previously completed

- 可选自动恢复副本，恢复已应用修改和未应用草稿；后台异常恢复、失败降级和加密验证。 / Optional snapshots recover committed changes and unapplied drafts; worker-exit recovery, graceful save failures and encryption verified.

### v0.4.1 已完成 / Previously completed

- 工程快照与文字框保存 / 重开，保留加密、独立于源文件；普通 PDF 导出不携带工程记录。 / Encrypted, source-independent project snapshots and editable boxes; regular exports omit project metadata.

### v0.4.0 已完成 / Previously completed

- 同列基线优先、显式基线行距及取样估计、导入字体家族匹配、完整矢量单元格点击填字。 / Local-column baseline priority, explicit/sampled baseline pitch, imported font-family matching and bordered vector-cell placement.
- 四种旋转、中文与加粗字体、导出重新编辑和界面点击流程回归。 / Regressions cover four rotations, Chinese/bold fonts, export/re-edit and UI clicks.

### v0.3.3 已完成 / Previously completed

- 进程异常退出后可重启并重新打开已保存文件，明确提示未保存内容无法恢复。 / Restart after worker exit and reopen saved files, with explicit unsaved-work limits.
- 大文件工作流 P50/P95、后台峰值工作集及保存优化已验证，见 [性能报告 / benchmarks](BENCHMARKS.md)。 / Workflow P50/P95, worker peak working set and save optimization are measured.

### v0.3.2 已完成 / Previously completed

- 重叠文字框通过文字摘要和坐标选择，支持取消。 / Pick overlapping boxes by text and coordinates; cancellation supported.
- 删除后保留不受影响的独立文字框，保留字体资源；相交或连锁重叠的框保守转为普通文字，撤销恢复。 / Preserve independent boxes and font resources after deletion; retire affected/overlapping clusters conservatively, with undo.
- 回归覆盖中文像素一致性、精细删除字符编号重映射、四种旋转与加密导出。 / Regressions cover Chinese pixel preservation, precise-selection ID remapping, rotations and encrypted export.

## 迭代方法 / Iteration process

每轮限定一至两个可验证问题：添加脱敏或生成的复现用例 → 实现 → 核心与 Qt 回归 → 更新中英文说明和日志 → Git 提交与版本标签。真实工作 PDF 仅在用户提供并同意使用后作为本地验证材料，不自动加入仓库。
Each iteration targets one or two verifiable problems: sanitized/generated fixture, implementation, core/Qt regression, bilingual documentation, commit and tag. Real work PDFs require user-provided authorization for local validation and are never automatically committed.

## 暂不纳入 / Outside current scope

OCR、扫描图片内容擦除、整篇自动重排、云端上传处理、协作编辑、数字签名修复。

OCR, scanned-image erasure, document-wide reflow, cloud processing, collaborative editing, signature repair.

## 版本规则 / Versioning

- `main`：已完成本地回归验证的版本；发布提交使用 `vX.Y.Z` 标签。 / Tested main branch, releases tagged `vX.Y.Z`.
- `0.x` 阶段允许交互与内部架构调整；补丁号用于兼容修复及小范围功能迭代。 / During 0.x, UI/architecture may evolve; patch versions cover compatible fixes and small feature iterations.
- 每次发布更新 `version.py`、`CHANGELOG.md` 和中英文说明，运行回归测试，推送提交及标签。 / Update version, changelog and bilingual docs; test, commit and tag.
- 用户文档、字体、虚拟环境和授权凭据不进入仓库。 / Do not commit user PDFs, fonts, environments or credentials.
- 不以重写历史的方式替换已发布标签。 / Never replace published tags by rewriting history.
