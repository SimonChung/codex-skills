---
name: word-to-markdown
description: Convert Word DOCX files to Markdown with Microsoft MarkItDown, preserving document structure and optional embedded media links.
---

# Word To Markdown

Use this skill when the user asks to convert a Word `.docx` file to Markdown. Microsoft MarkItDown is the conversion engine; do not use the previous custom OOXML parser as a fallback. Legacy `.doc` files must be converted to `.docx` first by an explicit local conversion step, then passed to MarkItDown.

## Workflow

1. Resolve the bundled Python runtime with `load_workspace_dependencies`. Do not use a system Python or install packages into the project.
2. Ensure MarkItDown is available in that runtime. The official package is `markitdown`; for Word conversion install `markitdown[docx]` in the intended environment. If it is missing, stop and report the install command.
3. Run [`scripts/docx_to_markdown.py`](scripts/docx_to_markdown.py). The script calls `MarkItDown(enable_plugins=False).convert_local(...)` and writes UTF-8 Markdown beside the source by default.
4. Keep extracted media only when requested with the default image behavior. The wrapper extracts embedded DOCX media into a sibling `<stem>_assets` directory and appends relative image links; it does not invent captions or transcribe image text.
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
