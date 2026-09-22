# 性能测量 / Performance measurements — v0.3.3

2026-09-22，本机生成文档、每组 5 次、每次新建处理进程。仅作可复现基线，不代表任意工作 PDF 的性能保证。
Generated fixtures, five runs each with a fresh worker. A reproducible local baseline, not a guarantee for arbitrary PDFs.

## 测量范围 / Scope

- 通过实际 JSON 管道测量往返墙钟耗时，包括 PDF 操作、元数据、缩略图 / PNG 编码和传输；不含 GUI 绘制。启动单独计时，打开统计到首屏元数据返回。 / Real worker-pipe wall time includes operations, metadata, thumbnails/PNG and transport, excluding GUI paint. Startup is separate; opening ends at first-page metadata.
- 六个图块对应 200% 下至多 1536 × 1024 像素视口，页面边缘裁切；这不是完整缩放交互或整页渲染时间。原有 Qt 缩放基准仍由 benchmark_editor.py 提供。 / Six clipped tiles at 200% cover up to 1536 × 1024 viewport pixels; not total zoom interaction/full-page rendering.
- P50 为中位数，P95 使用最近秩；5 个样本时 P95 就是最大样本，不能视作充分的尾延迟估计。系统文件缓存未清空。 / P50 is median; nearest-rank P95 equals the maximum of five samples and is not a robust tail estimate. OS file caches are not flushed.
- 内存是 Windows 后台处理进程生命周期峰值工作集，含共享页，不含 GUI / 基准进程，也不等于私有提交内存。 / Memory is the Windows worker lifetime peak working set, including shared pages, excluding GUI/benchmark; not private committed memory. [Microsoft definition](https://learn.microsoft.com/en-us/windows/win32/api/psapi/ns-psapi-process_memory_counters).

环境 / Environment: Windows-11-10.0.26200-SP0; Python 3.12.9; PyMuPDF 1.26.7.

## 优化后 / After optimization

耗时单位 ms，每格 P50 / P95。内存 MiB。 / Times in ms, P50 / P95; memory in MiB.

| 用例 / Fixture | 页数 / Pages | 文件 MiB | 打开 / Open | 六图块 / Tiles | 添加 / Insert | 保存 / Save | 最大工作集 / Peak |
| --- | --- | --- | --- | --- | --- | --- | --- |
| many_pages | 80 | 0.631 | 50.2 / 61.13 | 50.11 / 52.88 | 178.52 / 189.96 | 127.79 / 133.59 | 59.52 |
| large_page | 1 | 0.031 | 173.04 / 179.14 | 58.81 / 60.17 | 180.76 / 194.62 | 10.94 / 13.69 | 67.77 |
| large_images | 3 | 30.936 | 95.88 / 104.13 | 196.64 / 201.76 | 162.24 / 163.4 | 118.85 / 129.08 | 200.81 |

many_pages：80 页，每页 35 行文字；large_page：2400 × 3200 pt 单页、140 行；large_images：3 页，各含 1800 × 2000 随机像素图。随机种子固定，图片用例用于测试低压缩率文件，不模拟真实扫描内容。
Fixtures: 80 pages × 35 lines; one 2400 × 3200 pt page × 140 lines; three pages with distinct seeded 1800 × 2000 noise images. Noise stresses low-compression files rather than realistic scans.

## 保存优化 / Save optimization

| 用例 / Fixture | 优化前 P50 / P95 ms | 优化后 P50 / P95 ms |
| --- | --- | --- |
| many_pages | 4069.89 / 4469.83 | 127.79 / 133.59 |
| large_page | 17.26 / 27.05 | 10.94 / 13.69 |
| large_images | 156.51 / 197.77 | 118.85 / 129.08 |

导出由 garbage=4 改为 garbage=2：仍清理未引用对象、压缩和整理编号，跳过重复对象与内容流的比较合并。取舍是某些文件可能稍大。原文件保护、删除导出、加密与再编辑由回归测试验证。
Export switches garbage=4 to garbage=2: unused objects are removed and xrefs compacted, while duplicate-object/stream comparisons are skipped. Some outputs may be larger. Regressions verify source protection, deletion export, encryption and re-editing.

## 复现 / Reproduce

```powershell
.\.venv\Scripts\python.exe benchmark_workflows.py --runs 5
.\.venv\Scripts\python.exe benchmark_editor.py
```

[全部原始样本 / Raw samples](benchmarks/v0.3.3.json) 包含启动、再次编辑、撤销、重做和逐次内存数据。生成 PDF 与本地运行报告不进入版本控制。 / Includes startup, re-edit, undo/redo and per-run memory. Generated PDFs/local run reports are not committed.
