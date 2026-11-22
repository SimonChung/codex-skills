---
name: word-to-markdown
description: Convert Word DOCX files to Markdown with Microsoft MarkItDown, preserving document structure and optional embedded media links.
---

# Word To Markdown

Use this skill when the user asks to convert a Word `.docx` file to Markdown. Microsoft MarkItDown is the conversion engine; do not use the previous custom OOXML parser as a fallback. Legacy `.doc` files must be converted to `.docx` first by an explicit local conversion step, then passed to MarkItDown.

## Workflow

1. Resolve the bundled Python runtime with `load_workspace_dependencies`. On macOS, if the bundle lacks the converter, also check `~/.local/share/codex-skills/markitdown/bin/python` for a virtual environment based on that bundled Python. Keep conversion dependencies outside the document project.
2. Ensure the selected runtime has `markitdown[docx]`. If it is missing, report the install command `python -m pip install 'markitdown[docx]'` for the intended environment.
3. Run [`scripts/docx_to_markdown.py`](scripts/docx_to_markdown.py). The script calls `MarkItDown(enable_plugins=False).convert_local(...)` and writes UTF-8 Markdown beside the source by default.
4. With the default image behavior, the wrapper extracts embedded DOCX media into a sibling `<stem>_assets` directory. Inline images link to the extracted files and retain their source alt text. The Markdown also lists the extracted files. Preserve any captions from the source without inventing captions or transcribing image text.
5. Verify the output exists and preserves MarkItDown's headings, lists, tables, links, and source order. Do not silently summarize or “correct” source content.
6. If the document is image-only or its important content is inside screenshots, report that MarkItDown did not produce searchable text for those pixels. OCR requires an explicitly configured MarkItDown plugin or another user-requested OCR workflow.

## Conversion details

- MarkItDown is designed for structure-preserving Markdown for text analysis, not pixel-perfect document reproduction.
- Use the narrow local-file API `convert_local` rather than permissive URL or remote-resource conversion.
- Plugins remain disabled by default. Enable them only when the user explicitly requests a configured plugin workflow.
- Use `--output` or `--asset-dir` when the user requests a different destination. Use `--no-images` only for an explicitly text-only result.

Official project: <https://github.com/microsoft/markitdown>

## Command

```powershell
& "<bundled-python>" "<skill-folder>\scripts\docx_to_markdown.py" input.docx
```
