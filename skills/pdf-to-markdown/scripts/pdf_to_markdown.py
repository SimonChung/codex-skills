#!/usr/bin/env python3
"""Convert local PDF files or directories to Markdown with Microsoft MarkItDown."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path


def load_markitdown(use_plugins: bool):
    try:
        from markitdown import MarkItDown
    except ImportError as exc:
        raise RuntimeError(
            "MarkItDown is not installed in this Python runtime. "
            "Install it with: python -m pip install 'markitdown[pdf]'"
        ) from exc
    return MarkItDown(enable_plugins=use_plugins)


def discover_pdfs(inputs: list[Path], recursive: bool) -> tuple[list[Path], list[str]]:
    found: list[Path] = []
    errors: list[str] = []
    for item in inputs:
        path = item.expanduser()
        if not path.exists():
            errors.append(f"Input not found: {path}")
        elif path.is_dir():
            iterator = path.rglob("*") if recursive else path.iterdir()
            found.extend(
                candidate for candidate in iterator
                if candidate.is_file() and candidate.suffix.casefold() == ".pdf"
            )
        elif path.is_file() and path.suffix.casefold() == ".pdf":
            found.append(path)
        else:
            errors.append(f"Expected a PDF file or folder: {path}")

    unique: dict[str, Path] = {}
    for path in found:
        resolved = path.resolve()
        unique.setdefault(str(resolved).casefold(), resolved)
    return sorted(unique.values(), key=lambda path: str(path).casefold()), errors


def convert_one(source: Path, output: Path, use_plugins: bool) -> None:
    converter = load_markitdown(use_plugins)
    result = converter.convert_local(str(source.resolve()))
    markdown = result.markdown
    if not isinstance(markdown, str) or not markdown.strip():
        raise RuntimeError("MarkItDown produced no Markdown text.")
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(markdown.rstrip() + "\n", encoding="utf-8", newline="\n")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("inputs", nargs="+", type=Path, help="PDF file(s) or folder(s)")
    parser.add_argument("-r", "--recursive", action="store_true", help="Scan folders recursively")
    parser.add_argument("-o", "--output", type=Path, help="Markdown destination (single PDF only)")
    parser.add_argument("--use-plugins", action="store_true", help="Enable explicitly installed MarkItDown plugins")
    parser.add_argument("--overwrite", action="store_true", help="Replace existing Markdown outputs")
    parser.add_argument("--skip-existing", action="store_true", help="Skip existing Markdown outputs")
    parser.add_argument("--verbose", action="store_true", help="Show per-file conversion messages")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.overwrite and args.skip_existing:
        parser.error("--overwrite and --skip-existing are mutually exclusive")

    sources, errors = discover_pdfs(args.inputs, args.recursive)
    for error in errors:
        print(error, file=sys.stderr)
    if not sources:
        print("No PDF files found.", file=sys.stderr)
        return 2
    if args.output and len(sources) != 1:
        parser.error("--output can be used only when the inputs resolve to one PDF")

    converted = skipped = failed = 0
    for source in sources:
        output = (args.output.expanduser() if args.output else source.with_suffix(".md")).resolve()
        if output.suffix.casefold() != ".md":
            parser.error(f"Output must use the .md extension: {output}")
        if output == source.resolve():
            parser.error(f"Output path must not be the source PDF: {source}")
        if output.exists() and args.skip_existing:
            print(f"skipped existing output: {output}")
            skipped += 1
            continue
        if output.exists() and not args.overwrite:
            print(f"failed: output exists; use --overwrite or --skip-existing: {output}", file=sys.stderr)
            failed += 1
            continue

        if args.verbose:
            print(f"converting: {source}", flush=True)
        try:
            convert_one(source, output, args.use_plugins)
        except Exception as exc:
            print(f"failed: {source}: {exc}", file=sys.stderr)
            failed += 1
            continue
        print(f"wrote: {output}")
        converted += 1

    print(f"Summary: converted={converted}, skipped={skipped}, failed={failed}")
    return 1 if failed or errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
