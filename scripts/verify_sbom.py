#!/usr/bin/env python3
"""Scan the pinned validation dependency inventory with Trivy; fail on incomplete evidence."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import unquote
import uuid

ROOT = Path(__file__).resolve().parents[1]
SCANNER = 'aquasec/trivy:0.76.1@sha256:790fd66d1697395d8693d1acaa1ea702406a20f109b6fc7bac8db623eca6c06c'
CACHE = 'codex-skills-trivy-cache'


def normalize(name: str) -> str:
    return re.sub(r'[-_.]+', '-', name).lower()


def requirements(path: Path) -> dict[str, str]:
    result = {}
    for raw in path.read_text(encoding='utf-8-sig').splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        match = re.fullmatch(r'([A-Za-z0-9_.-]+)==([^\s;]+)', line)
        if not match or normalize(match[1]) in result:
            raise ValueError(f'Expected unique exact package pins, got: {line}')
        result[normalize(match[1])] = match[2]
    if not result:
        raise ValueError('Empty dependency inventory')
    return result


def validate_reports(expected: dict, bom: dict, scan: dict) -> dict:
    if bom.get('bomFormat') != 'CycloneDX' or not isinstance(bom.get('components'), list):
        raise ValueError('Missing CycloneDX components')
    observed = {}
    for component in bom['components']:
        purl = component.get('purl', '')
        if purl.startswith('pkg:pypi/'):
            name, version = unquote(purl[len('pkg:pypi/'):]).split('?', 1)[0].rsplit('@', 1)
            observed[normalize(name)] = version
    if observed != expected:
        raise ValueError('SBOM packages do not exactly cover the pinned inventory')
    if scan.get('SchemaVersion') != 2 or not isinstance(scan.get('Results'), list) or not scan['Results']:
        raise ValueError('Missing vulnerability scan results')
    if not any(result.get('Class') == 'lang-pkgs' for result in scan['Results']):
        raise ValueError('Dependency ecosystem was not scanned')
    findings = [v for result in scan['Results'] for v in result.get('Vulnerabilities', [])
                if v.get('Severity') in {'HIGH', 'CRITICAL'}]
    if findings:
        raise ValueError(f'Found {len(findings)} HIGH/CRITICAL vulnerabilities')
    return {'packages': len(observed), 'highCritical': 0, 'coverage': 'exact pinned inventory'}


def run_scan(inventory: Path, report: Path) -> dict:
    expected = requirements(inventory)
    report.mkdir(parents=True, exist_ok=False)
    inputs = report / 'inputs'
    inputs.mkdir()
    shutil.copy2(inventory, inputs / 'requirements.txt')
    digest = hashlib.sha256(inventory.read_bytes()).hexdigest()
    summary = {'status': 'incomplete', 'startedAt': datetime.now(timezone.utc).isoformat(),
               'scanner': SCANNER, 'requirementsSha256': digest, 'threshold': ['HIGH', 'CRITICAL'],
               'exclusions': [], 'scope': 'Pinned isolated validation environment including MarkItDown DOCX/PDF dependencies and validator tooling',
               'notScanned': 'Host OS, Python executable/stdlib, Git, PowerShell, Codex bundled runtimes, Mac native environment, scanner image and unrelated task-specific SBOM targets'}

    def run(name: str, args: list[str]):
        with (report / f'{name}.log').open('w', encoding='utf-8') as log:
            subprocess.run(args, check=True, stdout=log, stderr=subprocess.STDOUT)

    try:
        common = ['docker', 'run', '--rm', '--mount', f'type=bind,source={inputs},target=/inputs,readonly',
                  '--mount', f'type=bind,source={report},target=/reports',
                  '--mount', f'type=volume,source={CACHE},target=/root/.cache/trivy', SCANNER]
        run('generate', common + ['fs', '--format', 'cyclonedx', '--output', '/reports/dependencies.cdx.json', '/inputs'])
        run('scan', common + ['sbom', '--scanners', 'vuln', '--severity', 'HIGH,CRITICAL', '--exit-code', '1',
                             '--ignorefile', '/dev/null', '--format', 'json', '--output', '/reports/vulnerabilities.json',
                             '/reports/dependencies.cdx.json'])
        run('database', ['docker', 'run', '--rm', '--mount', f'type=volume,source={CACHE},target=/root/.cache/trivy,readonly',
                         '--entrypoint', 'cat', SCANNER, '/root/.cache/trivy/db/metadata.json'])
        summary['database'] = json.loads((report / 'database.log').read_text(encoding='utf-8'))
        bom = json.loads((report / 'dependencies.cdx.json').read_text(encoding='utf-8'))
        scan = json.loads((report / 'vulnerabilities.json').read_text(encoding='utf-8'))
        summary['coverage'] = validate_reports(expected, bom, scan)
        if hashlib.sha256(inventory.read_bytes()).hexdigest() != digest:
            raise ValueError('Dependency inventory changed during verification')
        summary['status'] = 'passed'
        return summary
    except Exception as exc:
        summary.update(status='failed', error=str(exc))
        raise
    finally:
        summary['finishedAt'] = datetime.now(timezone.utc).isoformat()
        (report / 'summary.json').write_text(json.dumps(summary, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--requirements', type=Path, default=ROOT / 'security/requirements-validation.txt')
    args = parser.parse_args()
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ') + '-' + uuid.uuid4().hex[:8]
    report = ROOT / '.work/security' / stamp
    try:
        summary = run_scan(args.requirements.resolve(), report)
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0
    except (OSError, ValueError, subprocess.CalledProcessError) as exc:
        print(f'SBOM failed: {exc}', file=sys.stderr)
        return 1
    finally:
        print(f'SBOM report: {report}')


if __name__ == '__main__':
    raise SystemExit(main())
