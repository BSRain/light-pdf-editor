# Light PDF Editor v0.2.0 · Qt Edition · Personal Use

English | [简体中文](README.md) | [Roadmap](ROADMAP.md) | [Changelog](CHANGELOG.md)

> **Personal use / 自用**: a small utility for everyday PDF text edits. Commercial support and ongoing maintenance are not promised.

![Qt editor with baseline snapping](ui_preview.png)

A Windows desktop PDF text editor with a Chinese interface. This version replaces the Tkinter implementation with **PySide6 / Qt and a separate PDF worker process**. Files are processed locally.

## Start

1. Install Python 3.10 or newer on Windows with **Add Python to PATH** enabled.
2. Clone or extract this repository and double-click **start.bat**.
3. The launcher creates `.venv` and installs dependencies on first use. Existing installations automatically install Qt if missing.
4. Close the old application before restarting. Drop one PDF into the editing view or choose **打开 PDF** (Open PDF).

The initial Qt download is larger than the old version; subsequent use can be offline. Run normally, not as Administrator, to avoid Windows file-drop privilege restrictions. The repository contains no personal PDFs, virtual environments, or font files.

## Align new text with existing text

1. Select **取样原文样式** (Sample original style) and click the reference text.
2. The properties panel shows the detected font, size, color, and weight. If no matching local font is available, the selected fallback is explicitly identified.
3. Enter the new text and click its intended position. The clicked height represents the first text **baseline**, rather than the top of a box.
4. Nearby original baselines and text edges act as snap targets. Blue guides show the alignment. Hold **Alt** while dragging to disable snapping temporarily.
5. Drag inside the box to move it, or drag any of the eight handles to resize it. The side panel provides exact X, first-baseline Y, width, and height values in PDF points.
6. Review the PDF engine's text preview, then click **应用文字** (Apply) or press **Ctrl+Enter**. Press **Esc** to cancel the draft.

Changing font or size preserves the first baseline where page bounds permit. Baseline snapping currently supports extractable text that is horizontal on screen. Scans, outlined glyphs, and vertical text do not provide supported baseline targets.

## Editing and saving

- Chinese and English text, multiline layout, font size, color, bold, and local TTF / OTF / TTC fonts.
- Native bold font variants when available, with synthetic stroke bold otherwise. Inserted fonts are embedded in the output.
- **框选删除** (Box delete): drag a rectangle to remove intersecting characters.
- **点选删除** (Click delete): hover over original text to highlight the PDF text span in red, then click to remove that entire span. Use box deletion for smaller regions.
- Original-text deletion supports Ctrl+Z undo and preserves images and vector graphics. Scanned-image text is unsupported.
- Click a draft box to focus it, then press **Delete / Backspace** to discard that draft without changing the source document.
- Undo retains up to 20 steps, with fewer steps for large documents. Undo applied text before repositioning it.
- Save as exports a separate file and refuses to overwrite the opened original. Apply or cancel the pending draft first.
- Password-protected PDFs can be opened by entering their password; undo and export preserve encryption.

## Controls

| Action | Input |
| --- | --- |
| Open / Save as | Ctrl+O / Ctrl+S |
| Apply / Cancel draft | Ctrl+Enter / Esc |
| Undo / Bold | Ctrl+Z / Ctrl+B |
| Delete focused draft | Delete / Backspace |
| Zoom around pointer | Mouse wheel |
| Pan | Middle-button drag, or Pan tool |
| Scroll vertically | Shift+Mouse wheel or scrollbar |
| Fit page | Ctrl+0 |
| Nudge focused draft | Arrows: 1 pt; Shift+Arrows: 10 pt |
| Temporarily disable snapping | Alt while dragging |

72 pt equals one inch. Zoom range: 20%–600%.

## Rendering architecture

- Qt transforms existing graphics immediately; wheel handlers do not parse or rasterize the PDF.
- Opening, text extraction, editing, previews, saving, and rasterization run in a separate process.
- After approximately 80 ms without viewport changes, the UI requests only visible 512-pixel tiles. A low-resolution page thumbnail remains underneath while sharp tiles arrive.
- The tile cache has a 64 MiB budget, in addition to visible graphics, the thumbnail, and the PDF engine's own memory. Pending viewport requests are replaced by the latest batch, and stale document results are ignored.
- Draft text is a separate transparent layer. Moving it does not clone or render the underlying page. Text, style, or box-size changes request a new text layout.

On this machine, generated text, 1,600-line vector, and large-image fixtures produced median wheel-dispatch-plus-GUI-processing times of about 4.5–4.7 ms. **This is not complete PDF render latency or a frame-rate guarantee**, and it is not directly comparable with older benchmarks that measured different operations. The benchmark is included for reproduction.

## Development and verification

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pdf_editor.py
.\.venv\Scripts\python.exe -m unittest -v test_editor.py
.\.venv\Scripts\python.exe benchmark_editor.py
```

Tests cover actual text removal, graphic preservation, Chinese bold embedding, baseline/export agreement for four page rotations, encrypted undo/export, overflow rollback, tile bounds, Qt file-drop events, Qt mouse dragging/resizing, pointer-centered zoom, style sampling, stale responses, and process isolation. Qt tests require an available desktop session. The physical File Explorer drag gesture is not automatically tested.

| File | Purpose |
| --- | --- |
| `pdf_editor.py` | Qt interface, interaction, scheduling, tile cache |
| `pdf_worker.py` | Isolated PDF owner and JSON pipe protocol |
| `pdf_core.py` | Fonts, insertion/deletion, text geometry extraction |
| `alignment.py` | Baseline/edge snapping and local font matching |
| `test_editor.py` | Core and Qt integration tests |
| `benchmark_editor.py` | Generated-page interaction benchmark |
| `start.bat` | Windows launcher |
| `version.py` / `CHANGELOG.md` | Version metadata and release history |
| `ROADMAP.md` | Bilingual future-version plan |

## Limitations and personal-use notice

No OCR, direct rewriting of existing text, or document-wide reflow. Exact glyph matching is not guaranteed when the original font is unavailable. Editing signed PDFs can invalidate their signatures. Metadata and attachments are not sanitized.

This project is for personal learning and everyday use. No separate open-source license is included. This notice does not replace the licenses of Qt, PyMuPDF, other dependencies, or installed fonts.

References: [Qt Graphics View](https://doc.qt.io/qtforpython-6.8/overviews/qtwidgets-graphicsview.html), [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/page.html), [PyMuPDF multiprocessing](https://pymupdf.readthedocs.io/en/latest/recipes-multiprocessing.html).
