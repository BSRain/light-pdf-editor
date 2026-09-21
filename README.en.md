# Light PDF Editor · Personal Use

English | [简体中文](README.md)

> **Personal use / 自用**: a small desktop utility for everyday personal PDF text edits. The scope is intentionally limited. Commercial support and ongoing maintenance are not promised.

![Editor preview](ui_preview.png)

A local Windows PDF text editor with a Chinese interface. Add or remove text, choose fonts and bold formatting, drag and resize text boxes, and zoom with the mouse wheel. PDF content stays on your computer.

## Quick start

1. Install Python 3.10 or newer on Windows, with **Add Python to PATH** enabled.
2. Clone this repository, or download and extract its ZIP archive.
3. Double-click **start.bat**. On the first run, it creates a `.venv` and installs the pinned dependencies. Internet access is required for this initial setup.
4. Drop one PDF into the window, edit it, and save a new copy.

Close the old application window before restarting after an update. Run normally rather than as Administrator: Windows may block file drops from a non-elevated File Explorer into an elevated application.

## Features

- Open PDFs through a file dialog or drag and drop; Chinese characters and spaces in paths are supported.
- Add Chinese or English text, including multiple lines, with font, size, color, and bold controls.
- Use installed Windows fonts, or select a TTF, OTF, or TTC font file.
- Preview actual PDF text layout before applying an edit.
- Drag inside a text box to move it. Drag any of its eight handles to resize it. Resizing reflows the text without changing its font size.
- Fine-tune X, Y, width, and height in points (72 pt = 1 inch).
- Remove actual PDF text within a selection while keeping images and vector graphics.
- Undo edits, switch pages, fit the page, and save a separate PDF copy.
- Open password-protected PDFs by entering the password.

## Editing workflow

1. Click **添加文字** (Add text).
2. Enter text in the right panel. Choose a font, size, and color; enable **B 加粗** for bold.
3. Click the page to place the text box. Move or resize it until the preview looks right.
4. Click **应用** (Apply), or press **Ctrl+Enter**. Press **Esc** to cancel the pending preview.
5. Choose **框选删除** (Select to delete) and drag a rectangle to remove text. Characters intersecting the selection are removed.
6. Click **另存为** (Save as) to export a new file. The opened original cannot be overwritten through this tool.

After text is applied, undo it before repositioning it. Undo history is limited to 20 steps, with fewer steps retained for large documents.

## Mouse and keyboard

| Action | Control |
| --- | --- |
| Open PDF | Ctrl+O |
| Save as | Ctrl+S |
| Apply pending text | Ctrl+Enter |
| Cancel pending text | Esc |
| Undo | Ctrl+Z |
| Move the pending box | Drag inside the box |
| Resize the box | Drag a corner or edge handle |
| Nudge the box, with page focused | Arrow keys: 1 pt; Shift+Arrow: 10 pt |
| Zoom around the pointer | Mouse wheel over the PDF view |
| Scroll vertically | Shift+Mouse wheel, or scrollbar |

The properties panel keeps its own scrolling behavior. Zoom anchoring is constrained by the page's scrollable bounds.

## Fonts and rendering

Bold uses the installed bold variants of Microsoft YaHei, Arial, Times New Roman, and Consolas when available. Other fonts use stroke-based synthetic bold. The resulting appearance is saved into the PDF. Fonts used for inserted text are embedded in the output; font files are not included in this repository.

Zoom reuses a cached page display list and scales only the visible area during wheel input. Approximately 150 ms after scrolling stops, the page is rendered sharply. A temporary soft preview does not affect exported PDF quality. Only one sharp page image is cached.

## Limitations

- No OCR: text contained in scans or converted to outlines cannot be removed as editable text.
- No direct editing of existing text, automatic matching of original fonts, or document-wide layout reflow.
- Editing a digitally signed document can invalidate its signature.
- This is an editing utility, not a sensitive-data sanitization tool. Metadata and attachments are not cleared.
- The UI is currently Chinese; these instructions provide an English reference.

## Development and tests

The launcher sets up the environment automatically. To do it manually in PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe pdf_editor.py
```

Run the test suite in a Windows desktop session:

```powershell
.\.venv\Scripts\python.exe -m unittest -v test_editor.py
```

Tests cover text insertion/removal, page rotations, font embedding, bold export, preview/export consistency, undo, file-drop callbacks, resizing, pointer-centered zoom, and cache invalidation. The full physical drag gesture from File Explorer is not automatically tested.

## Project files

- `pdf_editor.py`: desktop application.
- `start.bat`: Windows launcher.
- `requirements.txt`: pinned dependencies.
- `test_editor.py`: regression tests.
- `README.md`: Chinese documentation.

Virtual environments, personal PDFs, and temporary files are excluded from version control.

## Personal-use notice

This project is maintained for personal learning and everyday use, not as a commercial PDF product. No separate open-source license is included. This personal-use notice does not replace the licenses of third-party dependencies or installed fonts.

Implementation references: [PyMuPDF page editing](https://pymupdf.readthedocs.io/en/latest/page.html) and [TkinterDnD2](https://github.com/pmgagne/tkinterdnd2).
