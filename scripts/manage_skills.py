#!/usr/bin/env python3
"""Install linked personal skills; update a clean Git checkout without overwriting edits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import stat
import subprocess
import sys
import uuid

ROOT = Path(__file__).resolve().parent.parent
TEXT_SUFFIXES = {'.md', '.yaml', '.yml', '.json', '.py', '.ps1', '.sh', '.txt'}


def linked(path: Path) -> bool:
    if path.is_symlink():
        return True
    try:
        return bool(getattr(path.lstat(), 'st_file_attributes', 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT)
    except FileNotFoundError:
        return False


def exists(path: Path) -> bool:
    return os.path.lexists(path)


def within(path: Path, root: Path) -> bool:
    return path == root or root in path.parents


def skill_sources(root: Path) -> dict[str, Path]:
    manifest = json.loads((root / 'skills.json').read_text(encoding='utf-8'))
    names = manifest.get('skills')
    if manifest.get('schemaVersion') != 1 or not isinstance(names, list) or not names:
        raise ValueError('Invalid skills.json')
    result = {}
    source_root = (root / 'skills').resolve()
    for name in names:
        if not isinstance(name, str) or not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', name):
            raise ValueError('Invalid skill name')
        if name in result:
            raise ValueError(f'Duplicate skill: {name}')
        source = root / 'skills' / name
        if linked(source) or not within(source.resolve(), source_root) or not (source / 'SKILL.md').is_file():
            raise ValueError(f'Invalid skill source: {source}')
        snapshot(source)  # Reject nested links and special files before touching destinations.
        result[name] = source.resolve()
    return result


def snapshot(root: Path) -> dict[str, str]:
    """Compare source files, allowing only line-ending and Python cache differences."""
    if linked(root) or not root.is_dir():
        raise ValueError(f'Expected an ordinary skill directory: {root}')
    result = {}
    for base, directories, files in os.walk(root, followlinks=False):
        for name in list(directories):
            path = Path(base) / name
            if linked(path):
                raise ValueError(f'Nested directory link is not supported: {path}')
            if name == '__pycache__':
                directories.remove(name)
        for name in files:
            path = Path(base) / name
            if linked(path) or not path.is_file():
                raise ValueError(f'Unsupported skill entry: {path}')
            if path.suffix in {'.pyc', '.pyo'}:
                continue
            data = path.read_bytes()
            if path.suffix.lower() in TEXT_SUFFIXES:
                data = data.replace(b'\r\n', b'\n')
            result[path.relative_to(root).as_posix()] = hashlib.sha256(data).hexdigest()
    return result


def default_destination() -> Path:
    return Path(os.environ.get('CODEX_HOME', str(Path.home() / '.codex'))).expanduser() / 'skills'


def create_link(destination: Path, source: Path, root: Path) -> None:
    if os.name == 'nt':
        shell = shutil.which('pwsh') or shutil.which('powershell')
        if not shell:
            raise ValueError('PowerShell is required to create Windows directory junctions')
        subprocess.run([shell, '-NoProfile', '-NonInteractive', '-File', str(root / 'scripts' / 'new-junction.ps1'),
                        '-Destination', str(destination), '-Source', str(source)], check=True)
    else:
        destination.symlink_to(source, target_is_directory=True)


def inspect(root: Path, destination: Path) -> list[dict]:
    destination = destination.expanduser().resolve()
    rows = []
    for name, source in skill_sources(root).items():
        target = destination / name
        if linked(target):
            state = 'linked' if target.resolve() == source and target.is_dir() else 'other-link'
        else:
            state = 'directory-copy' if target.is_dir() else ('occupied' if exists(target) else 'missing')
        rows.append({'skill': name, 'state': state, 'destination': str(target), 'source': str(source)})
    return rows


def install(root: Path, destination: Path) -> dict:
    root = root.resolve()
    destination = destination.expanduser().resolve()
    sources = skill_sources(root)
    source_root = (root / 'skills').resolve()
    if within(destination, source_root) or within(source_root, destination):
        raise ValueError('Install destination must not overlap repository skill sources')
    # Preflight every skill before backing up or linking any of them.
    pending = []
    for name, source in sources.items():
        target = destination / name
        if linked(target):
            if target.resolve() != source or not target.is_dir():
                raise ValueError(f'Existing link points elsewhere; preserve and review: {target}')
            continue
        if exists(target) and (not target.is_dir() or snapshot(target) != snapshot(source)):
            raise ValueError(f'Existing skill differs; preserve and merge into the repository first: {target}')
        pending.append((name, source, target))
    if os.name == 'nt' and not (shutil.which('pwsh') or shutil.which('powershell')):
        raise ValueError('PowerShell is required on Windows')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    backup_root = (destination.parent / 'skill-backups' / 'codex-skills' / stamp).resolve()
    if within(backup_root, destination) or within(backup_root, source_root):
        raise ValueError('Backup directory must be outside discovery and source directories')
    destination.mkdir(parents=True, exist_ok=True)
    backups = []
    for name, source, target in pending:
        backup = None
        if exists(target):
            # Resolve and check both endpoints immediately before a recursive-directory move.
            if linked(target) or target.resolve().parent != destination:
                raise ValueError(f'Unsafe migration source: {target}')
            backup = backup_root / name
            if backup.resolve().parent != backup_root or exists(backup):
                raise ValueError(f'Unsafe migration destination: {backup}')
            backup_root.mkdir(parents=True, exist_ok=True)
            target.rename(backup)
        try:
            create_link(target, source, root)
            if not linked(target) or target.resolve() != source:
                raise ValueError(f'Link verification failed: {target}')
        except Exception:
            if backup is not None and not exists(target):
                backup.rename(target)
            raise
        if backup is not None:
            backups.append({'skill': name, 'backup': str(backup)})
    result = {'status': 'installed', 'skills': inspect(root, destination), 'backups': backups}
    if backups:
        (backup_root / 'migration.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    return result


def git(root: Path, *args: str) -> str:
    return subprocess.run(['git', '-C', str(root), *args], check=True, text=True,
                          encoding='utf-8', stdout=subprocess.PIPE).stdout.strip()


def sync(root: Path, destination: Path) -> dict:
    if git(root, 'status', '--porcelain'):
        raise ValueError('Repository has local changes; review, commit and push them before sync')
    branch = git(root, 'symbolic-ref', '--quiet', '--short', 'HEAD')
    if branch != 'main':
        raise ValueError(f'Sync expects main; finish the current work on {branch} first')
    upstream = git(root, 'rev-parse', '--abbrev-ref', '--symbolic-full-name', '@{upstream}')
    if upstream != 'origin/main':
        raise ValueError(f'Expected upstream origin/main, got {upstream}')
    git(root, 'fetch', 'origin')
    ahead, _behind = map(int, git(root, 'rev-list', '--left-right', '--count', 'HEAD...@{upstream}').split())
    if ahead:
        raise ValueError('Local commits are unpublished or diverged; review and push/merge before sync')
    git(root, 'merge', '--ff-only', '@{upstream}')
    result = install(root, destination)
    result.update(status='synced', commit=git(root, 'rev-parse', 'HEAD'))
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['install', 'status', 'sync'])
    parser.add_argument('--dest', type=Path, default=default_destination(), help='Personal skill directory; default: $CODEX_HOME/skills or ~/.codex/skills')
    args = parser.parse_args()
    try:
        if args.action == 'status':
            rows = inspect(ROOT, args.dest)
            print(json.dumps(rows, ensure_ascii=False, indent=2))
            return 0 if all(row['state'] == 'linked' for row in rows) else 1
        result = install(ROOT, args.dest) if args.action == 'install' else sync(ROOT, args.dest)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'Error: {exc}', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
