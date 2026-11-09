#!/usr/bin/env python3
"""Convert a local Word DOCX file to Markdown with Microsoft MarkItDown."""

from __future__ import annotations

import argparse
import os
import shutil
import zipfile
from pathlib import Path


def load_markitdown():
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError(
            "MarkItDown is not installed in this Python runtime. "
            "Install it with: python -m pip install 'markitdown[docx]'"
        ) from exc
    return MarkItDown(enable_plugins=False)


def extract_media(source: Path, asset_dir: Path) -> list[Path]:
    """Extract DOCX embedded media without interpreting pixels or OCR text."""
    with zipfile.ZipFile(source) as archive:
        names = [
            name for name in archive.namelist()
            if name.startswith("word/media/") and not name.endswith("/")
        ]
        if not names:
            return []
        asset_dir.mkdir(parents=True, exist_ok=True)
        outputs: list[Path] = []
        for name in names:
            target = asset_dir / Path(name).name
            with archive.open(name) as source_stream, target.open("wb") as target_stream:
                shutil.copyfileobj(source_stream, target_stream)
            outputs.append(target)
        return outputs


def relative_link(from_file: Path, target: Path) -> str:
    return Path(os.path.relpath(target, from_file.parent)).as_posix()


def convert(
    source: Path,
    output: Path,
    asset_dir: Path | None,
    include_images: bool,
) -> None:
    source = source.resolve()
    output = output.resolve()
    if source.suffix.casefold() != ".docx":
        raise ValueError("Only .docx input is supported. Convert legacy .doc files to .docx first.")
    if source == output:
        raise ValueError("Output Markdown must not overwrite the source DOCX.")

    converter = load_markitdown()
    result = converter.convert_local(str(source))
    markdown = result.markdown
    if not isinstance(markdown, str) or not markdown.strip():
        raise RuntimeError("MarkItDown produced no Markdown text.")

    media: list[Path] = []
    if include_images:
        media = extract_media(
            source,
            asset_dir.resolve() if asset_dir else output.with_name(output.stem + "_assets"),
        )

    lines = markdown.rstrip().splitlines()
    if media:
        lines.extend(["", "## Embedded images", ""])
        for image in media:
            lines.append(f"![{image.name}]({relative_link(output, image)})")
            lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines).rstrip() + "\n", encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path, help="Local Word .docx file")
    parser.add_argument("--output", type=Path, help="Markdown path; defaults to the input stem with .md")
    parser.add_argument("--asset-dir", type=Path, help="Directory for extracted embedded media")
    parser.add_argument("--no-images", action="store_true", help="Do not extract or link embedded media")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    source = args.input.expanduser().resolve()
    output = (args.output or source.with_suffix(".md")).expanduser().resolve()
    try:
        convert(source, output, args.asset_dir, not args.no_images)
    except Exception as exc:
        print(f"Conversion failed: {exc}")
        return 1
    print(f"Wrote {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
