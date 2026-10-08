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

## rc.5 精细删除 / Precise deletion

同机生成 Courier 字体 60 行 × 60 字符页面，删除每行前 10 字符；每次新启工作进程，计时包含删除保护、缩略图、元数据及管道返回，并验证撤销恢复全部字符。三次运行中位数：rc.4 **7,106.42 ms** → 本轮空间筛选 **2,747.87 ms**（约减少 61%）。不是滚轮帧率，也不代表所有 PDF。

A generated 60-row × 60-character Courier page deletes the first 10 glyphs per row. Each run uses a fresh worker; timing includes protection checks, thumbnail, metadata and pipe response, with complete character restoration checked after undo. Three-run medians: rc.4 **7,106.42 ms** → spatial filtering **2,747.87 ms**, approximately 61% lower. This measures neither wheel frame rate nor every PDF workload.

原始记录 / Raw data: [deletion-rc5.json](benchmarks/deletion-rc5.json). 优化后测量发生在版本号更新前，记录明确标注工作区变体。The after measurement precedes the version bump and explicitly identifies the working-tree variant.

复现 / Reproduce: `.venv\Scripts\python.exe benchmark_deletion.py --output tmp/deletion.json --runs 3`

## v0.6.0-rc.1 页面导航基线 / Navigation baseline

2026-10-02，本机实际工作进程 JSON 管道请求到响应，每类 12 次；仅生成 PDF。命令：`.venv\Scripts\python.exe benchmark_navigation.py`。原始数据见 [navigation-v0.6.0-rc.1.json](benchmarks/navigation-v0.6.0-rc.1.json)。
Measured worker request-to-response latency through the JSON pipe, 12 samples per generated fixture. Excludes UI painting and is not a before/after optimization comparison. The single large page is repeatedly requested; it is not a multi-page turn test.

| 用例 / Fixture | 页面响应 P50 / P95 ms | 缩略图 P50 / P95 ms |
| --- | --- | --- |
| 80 页 / pages | 37.34 / 40.90 | 2.77 / 4.00 |
| 大尺寸文字页 / large text page | 145.87 / 165.78 | 7.88 / 9.74 |
| 3 页图片，30.94 MB / image pages | 54.06 / 79.32 | 5.84 / 7.14 |

缩略图队列优先级低于主页面分块，但已开始的单次渲染不能抢占；复杂页面仍可能延迟后续操作。当前内存中最多保留 20 张 130×170 边界内的缩略图；打开整个文档不会预先生成所有缩略图。
Queued thumbnails have lower priority than main-view tiles, but an already active render is non-preemptible. Complex pages can still delay subsequent work. At most 20 thumbnails within 130×170 bounds are retained; document opening does not render every thumbnail.

## v0.6.0-rc.2 页面缓存 / Page content cache

2026-10-02，同一台机器、同一生成脚本和请求顺序，比较 rc.1 与 rc.2；每类循环重访 24 次。实际工作进程 JSON 管道请求到响应，不含界面绘制或之后的高清分块渲染。首次访问不等于系统冷缓存；单页用例测重复请求，不是跨页导航。原始记录：[优化前](benchmarks/page-cache-before-rc2.json)、[优化后](benchmarks/page-cache-after-rc2.json)。
Same host, generated fixtures and request order; 24 revisits per case, rc.1 vs rc.2. Worker JSON request/response only, excluding UI painting and later high-resolution tiles. First visits are not OS cold-cache measurements; the single-page case measures repeated requests rather than navigation.

| 用例 / Fixture | 优化前 P50 / P95 ms | 优化后 P50 / P95 ms | P50 降低 / reduction |
| --- | --- | --- | --- |
| 80 页文档中循环访问 4 页 / four-page working set | 42.40 / 45.47 | 16.58 / 16.88 | 60.9% |
| 大尺寸文字页重复请求 / large text page | 160.54 / 174.73 | 65.29 / 67.07 | 59.3% |
| 3 页图片文档 / three image pages | 61.21 / 70.33 | 21.17 / 24.05 | 65.4% |

分析定位到逐字符坐标变换是大文字页的主要 CPU 热点；未旋转页面现在跳过恒等变换。缓存保存页面文字、坐标和低清预览，命中时避免再次提取 / 渲染。最多 4 页、16 MiB 序列化数据；这不是整个进程的内存上限，解析对象、显示列表、撤销历史仍占用其他内存。缓存仅存在内存中，编辑或切换文档后失效。
Profiling identified per-character transforms as a major CPU cost; unrotated pages now skip identity transforms. Hits reuse text, geometry and low-resolution previews. The four-page/16 MiB limit covers serialized cache payload, not total process memory (parsed objects, display lists and undo history remain separate). Cache is memory-only and invalidates after edits/document changes.

只宣称已测重访场景的改善；首次打开、超出容量连续翻页和高清渲染不保证同样收益。打开耗时的单次记录含进程启动，会有波动。复现：`python benchmark_page_cache.py --output result.json`；在相应版本运行同一脚本。
Improvement claims apply to measured revisits only; first open, cache-thrashing sequential visits and high-resolution rendering may behave differently. One-shot open timings include process startup and fluctuate. Reproduce with the same script on each revision: `python benchmark_page_cache.py --output result.json`.

## v0.6.0-rc.3 连续缩放 / Continuous zoom

2026-10-02：同一脚本在 rc.2 / rc.3 运行，生成文字、矢量、图片 PDF。每类一次三段缩放，段首显式提交分块，随后每 16 ms 调整比例，共 30 次；用于复现旧队列问题，不代表所有滚轮操作。记录真实 Qt / 工作进程响应。脚本：`python benchmark_zoom_queue.py --output result.json`。原始：[之前](benchmarks/zoom-before-rc3.json)、[之后](benchmarks/zoom-after-rc3.json)。
Matched rc.2/rc.3 script, one three-part burst per generated fixture, explicit tile scheduling at each start followed by 30 total zoom changes spaced 16 ms apart. Reproduces queued-work behavior, not a general wheel benchmark. Actual Qt/worker responses; single runs are not statistical guarantees.

| 用例 / Fixture | 过期比例响应数 前→后 | 缩放调用+事件处理 P50 ms 前→后 | 最后输入后停稳 ms 前→后 |
| --- | --- | --- | --- |
| text | 26 → 3 | 6.53 → 5.27 | 64.64 → 190.09 |
| vector | 26 → 3 | 6.22 → 1.1 | 64.62 → 205.55 |
| image | 26 → 3 | 5.88 → 0.94 | 66.74 → 235.54 |

“过期”表示响应时比例已不匹配当前视图，不表示它以后不能被缓存复用。本例旧实现提前生成的分块恰好能在最终比例复用，因此停稳更快；新实现减少了交互期间的工作，但停稳后需要补绘更多分块。新实现保留上一层清晰预览直到补绘完成，避免期间直接退回低清底图。表中的事件耗时不等于高清 PDF 完整渲染延迟。
An obsolete response has a scale mismatching the view at reply time; it may still be reusable later. Here the old implementation's speculative tiles happened to match the final scale, shortening settling. The new implementation does less work during interaction but renders more after stopping; it retains the previous sharp preview during that transition. Event timings are not full high-resolution PDF render latency.

旧层最多一层、像素数据 16 MiB；这是对已有分块缓存之外持有的显示引用的约束，不是进程总内存上限。已有分块缓存仍为 64 MiB；正在执行的工作进程请求不能抢占。
At most one fallback layer with 16 MiB of pixel data is retained; this bounds display references, not total process memory. Existing tile cache remains 64 MiB. Active worker requests are non-preemptible.

## v0.7.0 OCR

运行 `.venv\Scripts\python.exe benchmark_ocr.py`；生成的中英混排小选区结果见 `benchmarks/ocr-v0.7.0.json`。仅测引擎调用，排除 GUI 和进程通信；三次结果不代表所有扫描件性能，首版不承诺通用耗时或准确率。
Run the generated OCR benchmark; results cover direct engine calls only, excluding GUI/IPC and do not generalize to all scans.
