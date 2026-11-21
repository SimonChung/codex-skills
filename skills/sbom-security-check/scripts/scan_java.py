#!/usr/bin/env python3
"""Check a Maven reactor or Gradle lockfile against its SBOM and Trivy findings."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
from urllib.parse import unquote

from trivy_reports import run_trivy


def read_json(path: Path) -> dict:
    return json.loads(path.read_bytes())


def source_file(project: Path) -> Path | None:
    if project.is_file():
        if project.name == 'pom.xml' or project.name.endswith('gradle.lockfile'):
            return project
        raise ValueError('Expected pom.xml or a *gradle.lockfile')
    entries = list(project.iterdir())
    sources = [p for p in entries if p.name == 'pom.xml' or p.name.endswith('gradle.lockfile')]
    if len(sources) > 1:
        raise ValueError('Scan each input individually: ' + ', '.join(sorted(p.name for p in sources)))
    if sources:
        return sources[0]
    if any(p.name in {'build.gradle', 'build.gradle.kts', 'settings.gradle', 'settings.gradle.kts'} for p in entries):
        raise ValueError('Gradle project without a lockfile; obtain the resolved build inventory')
    return None


def gradle_inventory(content: bytes) -> set[tuple]:
    packages = set()
    empty_marker = False
    for line in content.decode('utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        coordinate, separator, configs = line.partition('=')
        if separator and coordinate == 'empty':
            empty_marker = bool(configs.strip()) or empty_marker
            continue
        parts = coordinate.split(':')
        if not configs or len(parts) != 3 or not all(parts):
            raise ValueError(f'Invalid Gradle lock entry: {line}')
        packages.add(tuple(parts))
    if not packages and not empty_marker:
        raise ValueError('Empty or incomplete Gradle lockfile')
    return packages


def purl_coordinate(purl: str) -> tuple:
    if not purl.startswith('pkg:maven/'):
        raise ValueError(f'Expected a Maven package URL: {purl}')
    gav = purl.removeprefix('pkg:maven/').split('?', 1)[0].split('#', 1)[0]
    name, version = gav.rsplit('@', 1)
    group, artifact = name.split('/', 1)
    if not group or not artifact or not version:
        raise ValueError(f'Incomplete Maven package URL: {purl}')
    return unquote(group), unquote(artifact), unquote(version)


def resolve_maven(pom: Path, reports: Path, arguments: list[str]) -> list[Path]:
    # Maven interpolates this path separately for each active reactor project.
    output = reports / 'maven' / '${project.groupId}' / '${project.artifactId}' / '${project.version}'
    wrapper = pom.parent / ('mvnw.cmd' if os.name == 'nt' else 'mvnw')
    mvn = str(wrapper) if wrapper.is_file() else shutil.which('mvn') or 'mvn'
    command = [mvn, '-B', '-ntp', '-f', str(pom), *arguments,
               'org.apache.maven.plugins:maven-dependency-plugin:3.11.0:tree',
               '-DoutputType=json', f'-DoutputFile={output / "tree.json"}',
               'org.cyclonedx:cyclonedx-maven-plugin:2.9.3:makeBom', '-DincludeTestScope=true',
               '-DoutputFormat=json', '-DoutputName=dependencies.cdx', f'-DoutputDirectory={output}']
    log_path = reports / 'maven.log'
    with log_path.open('w', encoding='utf-8') as log:
        subprocess.run(command, cwd=pom.parent, stdout=log, stderr=subprocess.STDOUT, check=True)
    log = log_path.read_text(encoding='utf-8', errors='replace')
    missing = r'no dependency information available|transitive dependencies .*not be available|failed to (?:read artifact descriptor|collect dependencies)'
    if re.search(missing, log, re.I):
        raise ValueError('Maven could not resolve dependency metadata; see maven.log')
    modules = sorted(p.parent for p in (reports / 'maven').glob('*/*/*/tree.json'))
    boms = {p.parent for p in (reports / 'maven').glob('*/*/*/dependencies.cdx.json')}
    counts = re.findall(r'^\[INFO\] Building .*\[\d+/(\d+)\]\s*$', log, re.M)
    if not modules or set(modules) != boms or (counts and len(modules) != max(map(int, counts))):
        raise ValueError('Missing Maven module tree or SBOM; see maven.log')
    return modules


def maven_inventory(directory: Path) -> tuple:
    tree = read_json(directory / 'tree.json')
    root = (tree['groupId'], tree['artifactId'], tree['version'])
    bom = read_json(directory / 'dependencies.cdx.json')
    if purl_coordinate(bom['metadata']['component']['purl']) != root or root != directory.parts[-3:]:
        raise ValueError('SBOM and dependency tree identify different Maven projects')
    expected = set()
    nodes = list(tree.get('children', []))
    while nodes:
        node = nodes.pop()
        expected.add((node['groupId'], node['artifactId'], node['version']))
        nodes.extend(node.get('children', []))
    return expected, root


def check_bom(bom: dict, expected: set) -> None:
    components = set()
    for component in bom.get('components', []):
        if component.get('type') == 'application' and 'purl' not in component:
            continue  # Trivy adds a wrapper component for the Gradle lockfile.
        components.add(purl_coordinate(component['purl']))
    if bom.get('bomFormat') != 'CycloneDX' or components != expected:
        raise ValueError(f'SBOM differs from resolved dependencies: missing={expected-components}, extra={components-expected}')


def check_report(report: dict, expected: set, root: tuple | None, kind: str) -> int:
    results = [r for r in report['Results'] if r.get('Class') == 'lang-pkgs' and r.get('Type') == kind]
    if report.get('SchemaVersion') != 2 or not results:
        raise ValueError('Missing Java vulnerability scan results')
    scanned = {purl_coordinate(p['Identifier']['PURL']) for r in results for p in r['Packages']}
    if root:
        scanned.discard(root)
    if scanned != expected:
        raise ValueError(f'Scan differs from resolved dependencies: missing={expected-scanned}, extra={scanned-expected}')
    count = 0
    for result in results:
        findings = result.get('Vulnerabilities', [])
        if not isinstance(findings, list):
            raise ValueError('Invalid Java vulnerability list')
        count += len(findings)
    return count


def scan_inventory(directory: Path, expected: set, args: argparse.Namespace, *,
                   root: tuple | None = None, lock: bytes | None = None, lock_name: str = '') -> dict:
    maven = root is not None
    if maven:
        check_bom(read_json(directory / 'dependencies.cdx.json'), expected)
    if not expected:
        return {'status': 'no-external-dependencies', 'packages': 0, 'findings': 0}
    with tempfile.TemporaryDirectory() as temp:
        inputs = Path(temp)
        if lock is not None:
            (inputs / lock_name).write_bytes(lock)
        trivy = run_trivy(inputs, directory, args.severity, args.trivy_image, scan_bom=maven)
    if not maven:
        check_bom(read_json(directory / 'dependencies.cdx.json'), expected)
    count = check_report(read_json(directory / 'vulnerabilities.json'), expected, root, 'jar' if maven else 'gradle')
    return {'status': 'findings' if count else 'passed', 'packages': len(expected),
            'findings': count, 'trivy': trivy}


def scan(args: argparse.Namespace) -> int:
    source = source_file(args.project.resolve())
    if source is None:
        print('Skipped: no Maven or Gradle project in this directory')
        return 0
    reports = args.reports.resolve()
    reports.mkdir(parents=True, exist_ok=False)
    summary = {'source': str(source), 'status': 'incomplete', 'severity': args.severity, 'results': {}}
    results = summary['results']
    try:
        content = source.read_bytes()
        summary['sha256'] = hashlib.sha256(content).hexdigest()
        if source.name == 'pom.xml':
            for directory in resolve_maven(source, reports, args.maven_arg):
                expected, root = maven_inventory(directory)
                results[':'.join(root)] = scan_inventory(directory, expected, args, root=root)
        else:
            if args.maven_arg:
                raise ValueError('--maven-arg requires pom.xml')
            expected = gradle_inventory(content)
            results[source.name] = scan_inventory(reports, expected, args, lock=content, lock_name=source.name)
        if source.read_bytes() != content:
            raise ValueError('Dependency input changed during the scan')
        if any(r['findings'] for r in results.values()):
            summary['status'] = 'findings'
            return 1
        summary['status'] = 'passed' if any(r['packages'] for r in results.values()) else 'no-external-dependencies'
        return 0
    except (OSError, ValueError, KeyError, TypeError, AttributeError, subprocess.SubprocessError) as exc:
        summary.update(status='incomplete', error=str(exc))
        return 2
    finally:
        (reports / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('project', type=Path, help='One module directory or explicit pom.xml / Gradle lockfile')
    parser.add_argument('reports', type=Path, help='New output directory for this scan')
    parser.add_argument('--maven-arg', action='append', default=[], help='Build selection, e.g. --maven-arg=-Pprod')
    parser.add_argument('--severity', default='HIGH,CRITICAL')
    parser.add_argument('--trivy-image', help='Use Docker with an approved Trivy image pinned by digest')
    args = parser.parse_args()
    args.severity = args.severity.upper()
    if not set(args.severity.split(',')) <= {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}:
        parser.error('Invalid Trivy severity list')
    if args.trivy_image and (args.trivy_image.startswith('-') or '@sha256:' not in args.trivy_image):
        parser.error('Supply a Trivy image reference pinned by digest')
    try:
        return scan(args)
    except (OSError, ValueError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
