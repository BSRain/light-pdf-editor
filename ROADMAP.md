# 后续版本计划 / Roadmap

> 自用 / Personal use。以下是计划，不代表已实现；按实际使用反馈调整优先级，不预设发布日期。
> Planned work, not released features. Priorities follow personal-use feedback; no release dates are promised.

## 当前版本 / Current: v0.2.0

Qt 界面、独立 PDF 处理进程、可见区域分块渲染、原文基线与边缘吸附、字体样式取样、增删文字、加粗、撤销、拖放、加密文件保存。

Qt UI, isolated PDF worker, viewport tiles, baseline/edge snapping, style sampling, text insertion/deletion, bold, undo, drag-and-drop, encrypted export.

## 分阶段计划 / Next versions

| 版本 / Version | 重点 / Focus | 计划内容 / Planned work | 验收标准 / Acceptance |
| --- | --- | --- | --- |
| v0.2.x | 稳定性 / Stability | 收集经脱敏的实际工作 PDF 用例；修复文字误删、边缘裁切、缩放卡顿和进程异常；完善错误提示。 / Add sanitized real-world fixtures; fix deletion, clipping, zoom stalls and worker errors. | 每个修复有可复现用例；既有保存、加密和对齐测试全部通过。 / Reproducible cases and passing regression tests. |
| v0.3.0 | 精细编辑 / Precise editing | 按字或词选择删除；删除前显示范围；重做；本次会话新增文字可再次选中移动和修改。 / Character/word deletion, selection preview, redo, reselect and edit session-created text. | 混合中英文与多行文档中不误删相邻字符；撤销/重做后内容一致。 / No neighboring-character loss; reversible edits. |
| v0.4.0 | 排版对齐 / Alignment | 更准确的字体家族和粗细匹配；多行行距取样；对齐到列、表格单元格和最近文本行；优化吸附优先级。 / Better font matching, line-spacing sampling, columns/table alignment and snap priorities. | 多栏与表格用例可稳定对齐；字体替代有明确提示。 / Stable alignment on multi-column/table fixtures, explicit font fallback. |
| v0.5.0 | 桌面交付 / Desktop delivery | Windows 便携 EXE；崩溃恢复草稿；大文档缓存调优；高 DPI 与多显示器验证。 / Portable Windows EXE, draft recovery, large-file tuning, high-DPI/multi-monitor checks. | 无 Python 环境可运行；恢复草稿不覆盖原稿；明确缓存上限并实测交互延迟。 / Runs without Python; recovery preserves originals; measured cache/latency limits. |

## 暂不纳入 / Outside current scope

OCR、扫描图片内容擦除、整篇自动重排、云端上传处理、协作编辑、数字签名修复。

OCR, scanned-image erasure, document-wide reflow, cloud processing, collaborative editing, signature repair.

## 版本规则 / Versioning

- `main`：已完成本地回归验证的版本；发布提交使用 `vX.Y.Z` 标签。 / Tested main branch, releases tagged `vX.Y.Z`.
- `0.x` 阶段允许交互与内部架构调整；补丁号用于兼容修复。 / During 0.x, UI/architecture may evolve; patch versions are compatible fixes.
- 每次发布更新 `version.py`、`CHANGELOG.md` 和中英文说明，运行回归测试，推送提交及标签。 / Update version, changelog and bilingual docs; test, commit and tag.
- 用户文档、字体、虚拟环境和授权凭据不进入仓库。 / Do not commit user PDFs, fonts, environments or credentials.
- 不以重写历史的方式替换已发布标签。 / Never replace published tags by rewriting history.
