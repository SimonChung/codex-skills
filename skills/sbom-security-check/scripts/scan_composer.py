#!/usr/bin/env python3
"""Scan one project's locked Composer packages with Trivy, including development dependencies."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import unquote


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding='utf-8-sig'))


def inventory(lock: dict) -> set[str]:
    expected = set()
    for group in ('packages', 'packages-dev'):
        if not isinstance(lock.get(group), list):
            raise ValueError(f'Missing or invalid composer.lock section: {group}')
        for package in lock[group]:
            expected.add(package['name'] + '@' + package['version'])
    return expected


def check_coverage(expected: set[str], report: dict, bom: dict) -> list[dict]:
    composer = [r for r in report['Results']
                if r.get('Class') == 'lang-pkgs' and r.get('Type') == 'composer'
                and r.get('Target') == 'composer.lock']
    if report.get('SchemaVersion') != 2 or len(composer) != 1:
        raise ValueError('Missing Composer vulnerability report for composer.lock')
    scanned = {p['Name'] + '@' + p['Version'] for p in composer[0]['Packages']}
    components = set()
    for component in bom['components']:
        purl = component.get('purl', '')
        if purl.startswith('pkg:composer/'):
            value = purl.removeprefix('pkg:composer/').split('?', 1)[0].split('#', 1)[0]
            components.add(unquote(value))
    if bom.get('bomFormat') != 'CycloneDX' or components != expected or scanned != expected:
        raise ValueError('Composer names or versions differ between lock, scan and SBOM')
    findings = composer[0].get('Vulnerabilities', [])
    if not isinstance(findings, list):
        raise ValueError('Invalid Composer vulnerabilities')
    return findings


def run_trivy(inputs: Path, reports: Path, severity: str, image: str | None) -> dict:
    trivy = ['trivy']
    output = str(reports)
    if image:
        trivy = ['docker', 'run', '--rm', '--workdir', '/inputs',
                 '--volume', f'{inputs}:/inputs:ro', '--volume', f'{reports}:/reports',
                 '--volume', 'codex-skills-trivy-cache:/root/.cache/trivy', image]
        output = '/reports'
    (inputs / '.trivyignore').touch()
    scan_path = f'{output}/vulnerabilities.json'
    bom_path = f'{output}/dependencies.cdx.json'
    subprocess.run([*trivy, 'fs', '--scanners', 'vuln', '--include-dev-deps',
                    '--list-all-pkgs', '--severity', severity, '--ignorefile', '.trivyignore', '--ignore-unfixed=false',
                    '--exit-code', '0', '--format', 'json', '--output', scan_path, '.'],
                   cwd=inputs, check=True)
    subprocess.run([*trivy, 'convert', '--format', 'cyclonedx', '--output', bom_path, scan_path],
                   cwd=inputs, check=True)
    version = subprocess.check_output([*trivy, 'version', '--format', 'json'], cwd=inputs)
    metadata = json.loads(version)
    if not metadata.get('Version') or not metadata.get('VulnerabilityDB', {}).get('UpdatedAt'):
        raise ValueError('Missing Trivy version or vulnerability database timestamp')
    return metadata


def scan(module: Path, reports: Path, severity: str, image: str | None = None) -> int:
    if not module.is_dir():
        raise ValueError(f'Project directory does not exist: {module}')
    files = [module / name for name in ('composer.json', 'composer.lock')
             if (module / name).exists() or (module / name).is_symlink()]
    if not files:
        print('Skipped: no Composer manifest or lockfile in this module')
        return 0

    reports.mkdir(parents=True, exist_ok=False)
    summary = {'module': str(module), 'severity': severity, 'status': 'incomplete', 'sha256': {}}
    try:
        with tempfile.TemporaryDirectory() as temp:
            inputs = Path(temp)
            for path in files:
                content = path.read_bytes()
                (inputs / path.name).write_bytes(content)
                summary['sha256'][path.name] = hashlib.sha256(content).hexdigest()
            if not (inputs / 'composer.lock').is_file():
                raise ValueError('No composer.lock for this module; resolved versions are unknown')
            expected = inventory(read_json(inputs / 'composer.lock'))
            manifest = inputs / 'composer.json'
            data = read_json(manifest) if manifest.exists() else {}
            if not isinstance(data, dict):
                raise ValueError('Invalid Composer manifest')

            if expected:
                summary['trivy'] = run_trivy(inputs, reports, severity, image)
                findings = check_coverage(expected, read_json(reports / 'vulnerabilities.json'),
                                          read_json(reports / 'dependencies.cdx.json'))
                summary.update(status='findings' if findings else 'passed', findings=len(findings))
            else:
                if any('/' in name for group in ('require', 'require-dev') for name in data.get(group, {})):
                    raise ValueError('Empty lockfile despite Composer requirements in the manifest')
                summary['status'] = 'no-locked-packages'
            summary['packages'] = len(expected)
            for name, digest in summary['sha256'].items():
                if hashlib.sha256((module / name).read_bytes()).hexdigest() != digest:
                    raise ValueError(f'{name} changed during verification')
        return 1 if summary['status'] == 'findings' else 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        summary.update(status='incomplete', error=str(exc))
        return 2
    finally:
        (reports / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('module', type=Path, help='One in-scope Composer project directory')
    parser.add_argument('reports', type=Path, help='New report directory for this run')
    parser.add_argument('--severity', default='HIGH,CRITICAL', help='Comma-separated Trivy severities')
    parser.add_argument('--trivy-image', help='Use Docker with this approved Trivy image pinned by digest')
    args = parser.parse_args()
    levels = args.severity.upper().split(',')
    if not set(levels) <= {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}:
        parser.error('Invalid Trivy severity list')
    if args.trivy_image and (args.trivy_image.startswith('-') or '@sha256:' not in args.trivy_image):
        parser.error('Supply a Trivy image reference pinned by digest')
    try:
        return scan(args.module.resolve(), args.reports.resolve(), ','.join(levels), args.trivy_image)
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
