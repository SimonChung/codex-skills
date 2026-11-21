#!/usr/bin/env python3
"""Scan one resolved Pub, SwiftPM or CocoaPods dependency inventory."""
import argparse
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
import tempfile
from urllib.parse import unquote, urlsplit

from trivy_reports import run_trivy


KINDS = {'pubspec.lock': 'pub', 'Package.resolved': 'swift', 'Podfile.lock': 'cocoapods'}
MANIFESTS = {'pubspec.yaml': 'pubspec.lock', 'Package.swift': 'Package.resolved', 'Podfile': 'Podfile.lock'}


def find_lock(source: Path) -> Path | None:
    if source.name in KINDS:
        if not source.is_file():
            raise ValueError(f'Missing resolved dependency lockfile: {source}')
        return source
    if not source.is_dir():
        if not source.is_file():
            raise ValueError(f'Input does not exist: {source}')
        lock = source.with_name(MANIFESTS.get(source.name, source.name))
        if lock.name not in KINDS or not lock.is_file():
            raise ValueError(f'Expected a resolved dependency lockfile: {lock}')
        return lock
    candidates = {source / name for name in KINDS if (source / name).exists()}
    candidates.update(source / lock for name, lock in MANIFESTS.items() if (source / name).is_file())
    workspaces = list(source.glob('*.xcworkspace'))
    projects = list(source.glob('*.xcodeproj'))
    if source.suffix == '.xcworkspace':
        workspaces.append(source)
    elif source.suffix == '.xcodeproj':
        projects.append(source)
    relative = Path('xcshareddata/swiftpm/Package.resolved')
    workspace_locks = {w / relative for w in workspaces if (w / relative).is_file()}
    candidates.update(workspace_locks)
    for project in projects:
        lock = project / 'project.xcworkspace' / relative
        if lock.exists():
            candidates.add(lock)
        elif not workspace_locks:
            model = (project / 'project.pbxproj').read_text(encoding='utf-8')
            if 'XCRemoteSwiftPackageReference' in model:
                raise ValueError('Xcode declares Swift packages; supply its resolved workspace lockfile')
            if 'XCLocalSwiftPackageReference' in model:
                raise ValueError('Verify the local Swift packages and their resolved dependencies')
    if not candidates:
        if source.suffix == '.xcworkspace':
            raise ValueError('No SwiftPM lock in this workspace; check the selected schemes and package references')
        return None
    if len(candidates) != 1:
        raise ValueError('Check each applicable lock separately: ' + ', '.join(map(str, sorted(candidates))))
    return find_lock(candidates.pop())


@dataclass
class Inventory:
    packages: dict[str, str] = field(default_factory=dict)
    sdk: list[str] = field(default_factory=list)
    gaps: dict[str, str] = field(default_factory=dict)
    revisions: dict[str, str] = field(default_factory=dict)


def read_yaml(content: bytes) -> dict:
    try:
        import yaml
    except ImportError as exc:
        raise ValueError('Pub and CocoaPods inventories require PyYAML in the scanner Python environment') from exc

    class LockLoader(yaml.BaseLoader):
        # Lock identifiers and versions are strings, including names like "on".
        def construct_mapping(self, node, deep=False):
            mapping = super().construct_mapping(node, deep)
            if len(mapping) != len(node.value):
                raise ValueError('Duplicate YAML lockfile key')
            return mapping

    try:
        return yaml.load(content, Loader=LockLoader)
    except yaml.YAMLError as exc:
        raise ValueError('Malformed YAML lockfile') from exc


def pub_inventory(data: dict) -> Inventory:
    found = Inventory()
    for name, entry in data['packages'].items():
        found.packages[name] = entry['version']
        source = entry['source']
        if source == 'sdk':
            found.sdk.append(name)
        elif source == 'hosted':
            description = entry['description']
            public = {'https://pub.dev', 'https://pub.dartlang.org'}
            if not isinstance(description, dict) or description.get('url', '').rstrip('/') not in public:
                found.gaps[name] = 'Unverified hosted package origin'
            elif description.get('name', name) != name:
                found.gaps[name] = 'Hosted package name differs from lock entry'
        else:
            found.gaps[name] = f'Pub {source} dependency; verify the actual source'
            if source == 'git' and entry['description'].get('resolved-ref'):
                found.revisions[name] = entry['description']['resolved-ref']
    return found


def swift_name(location: str) -> str:
    # Canonicalize the repository, retaining its owner; Swift identities alone can collide.
    scp = re.fullmatch(r'git@([^:]+):(.+)', location)
    if scp:
        location = 'ssh://git@' + scp[1] + '/' + scp[2]
    url = urlsplit(location if '://' in location else '//' + location)
    host = url.hostname or ''
    path = unquote(url.path).strip('/').removesuffix('.git')
    if not host or not path:
        raise ValueError('Swift package lacks a repository host or path')
    if url.port and url.port != {'https': 443, 'ssh': 22, 'http': 80}.get(url.scheme):
        host += ':' + str(url.port)
    return host + '/' + (path.lower() if host == 'github.com' else path)


def swift_inventory(data: dict) -> Inventory:
    schema = data['version']
    if schema not in (1, 2, 3):
        raise ValueError(f'Unsupported Package.resolved version: {schema}')
    pins = (data['object'] if schema == 1 else data)['pins']
    if not isinstance(pins, list):
        raise ValueError('Invalid SwiftPM pins')
    found = Inventory()
    for pin in pins:
        state = pin['state']
        identity = pin['package'] if schema == 1 else pin['identity']
        location = pin['repositoryURL'] if schema == 1 else pin.get('location', '')
        kind = pin.get('kind', 'remoteSourceControl')
        if kind != 'remoteSourceControl' or location.startswith(('/', './', '../', 'file:')):
            name = identity
            found.gaps[name] = f'Unverified Swift package origin ({kind})'
        else:
            name = swift_name(location)
        if name in found.packages:
            raise ValueError(f'Duplicate Swift package: {name}')
        version = state.get('version')
        if not version:
            found.gaps[name] = 'Branch or revision without a release version'
            if state.get('revision'):
                found.revisions[name] = state['revision']
        found.packages[name] = version or state.get('revision') or state['branch']
    return found


def pods_inventory(data: dict) -> Inventory:
    found = Inventory()
    public_repos = {'trunk', 'https://cdn.cocoapods.org', 'https://github.com/cocoapods/specs',
                    'https://github.com/cocoapods/specs.git'}
    public = {name for repo, names in data.get('SPEC REPOS', {}).items()
              if repo.lower().rstrip('/') in public_repos for name in names}
    entries = data['PODS']
    if not isinstance(entries, list):
        raise ValueError('Invalid CocoaPods PODS section')
    if not entries and data.get('DEPENDENCIES'):
        raise ValueError('Empty PODS section despite declared dependencies')
    for pod in entries:
        if isinstance(pod, dict):
            pod, = pod.keys()
        match = re.fullmatch(r'([^\s()]+) \(([^\s()]+)\)', pod)
        if not match:
            raise ValueError('Invalid CocoaPods package name or resolved version')
        name, version = match.groups()
        if name in found.packages:
            raise ValueError(f'Duplicate CocoaPods entry: {name}')
        found.packages[name] = version
        base = name.split('/', 1)[0]
        if base in data.get('EXTERNAL SOURCES', {}) or base not in public:
            found.gaps[name] = 'External, local or unverified pod origin'
            commit = data.get('CHECKOUT OPTIONS', {}).get(base, {}).get(':commit')
            if commit:
                found.revisions[name] = commit
    return found


def coordinate(purl: str, kind: str) -> tuple[str, str]:
    prefix = 'pkg:' + kind + '/'
    if not purl.startswith(prefix):
        raise ValueError(f'Expected a {kind} package URL')
    path, _, subpath = purl[len(prefix):].partition('#')
    name, version = path.split('?', 1)[0].rsplit('@', 1)
    name, version = unquote(name), unquote(version)
    if kind == 'swift':
        name = swift_name(name)
    if subpath:
        name += '/' + unquote(subpath)
    return name, version


def check_reports(inv: Inventory, kind: str, scan: dict, bom: dict) -> tuple[int, int]:
    excluded = set(inv.sdk) | inv.gaps.keys()
    expected = {(n, v) for n, v in inv.packages.items() if n not in excluded}
    components = {coordinate(c['purl'], kind) for c in bom['components'] if 'purl' in c}
    results = [r for r in scan['Results'] if r.get('Class') == 'lang-pkgs' and r.get('Type') == kind]
    if bom.get('bomFormat') != 'CycloneDX' or scan.get('SchemaVersion') != 2 or len(results) != 1:
        raise ValueError('Missing SBOM or vulnerability result for the selected ecosystem')
    result = results[0]
    scanned = {coordinate(p['Identifier']['PURL'], kind) for p in result['Packages']}
    for label, observed in (('CycloneDX', components), ('Trivy', scanned)):
        covered = {(n, v) for n, v in observed if n not in excluded}
        if covered != expected:
            raise ValueError(f'{label} differs from lock: missing={expected - covered}, extra={covered - expected}')
    confirmed = 0
    unverified = 0
    findings = result.get('Vulnerabilities', [])
    if not isinstance(findings, list):
        raise ValueError('Invalid vulnerability result')
    for v in findings:
        name = swift_name(v['PkgName']) if kind == 'swift' else v['PkgName']
        if (name, v['InstalledVersion']) in expected:
            confirmed += 1
        elif name in excluded:
            unverified += 1
        else:
            raise ValueError('Finding refers to an unrecognized package or version')
    return confirmed, unverified


def scan(source: Path, reports: Path, severity: str, image: str | None) -> int:
    lock = find_lock(source)
    if lock is None:
        print('Skipped: no Pub, SwiftPM or CocoaPods inputs in this module')
        return 0
    reports.mkdir(parents=True, exist_ok=False)
    summary = {'source': str(lock), 'severity': severity, 'status': 'incomplete'}
    try:
        content = lock.read_bytes()
        kind = KINDS[lock.name]
        summary['sha256'] = hashlib.sha256(content).hexdigest()
        data = json.loads(content) if kind == 'swift' else read_yaml(content)
        inv = {'pub': pub_inventory, 'swift': swift_inventory, 'cocoapods': pods_inventory}[kind](data)
        summary.update(locked=len(inv.packages), sdkPackages=inv.sdk, gaps=inv.gaps, revisions=inv.revisions)
        if inv.packages:
            with tempfile.TemporaryDirectory() as temp:
                inputs = Path(temp)
                (inputs / lock.name).write_bytes(content)
                summary['trivy'] = run_trivy(inputs, reports, severity, image)
            findings, unverified = check_reports(inv, kind, json.loads((reports / 'vulnerabilities.json').read_bytes()),
                                                json.loads((reports / 'dependencies.cdx.json').read_bytes()))
            summary.update(findings=findings, unverifiedFindings=unverified)
        summary['verifiedPackageVersions'] = len(inv.packages) - len(inv.sdk) - len(inv.gaps)
        if lock.read_bytes() != content:
            raise ValueError('Lockfile changed during verification')
        if inv.gaps:
            return 2
        if summary.get('findings'):
            summary['status'] = 'findings'
            return 1
        summary['status'] = 'passed' if len(inv.packages) > len(inv.sdk) else 'no-locked-external-packages'
        return 0
    except (OSError, ValueError, TypeError, KeyError, AttributeError, subprocess.SubprocessError) as exc:
        summary['error'] = str(exc)
        return 2
    finally:
        (reports / 'summary.json').write_text(json.dumps(summary, indent=2) + '\n', encoding='utf-8')
        print(json.dumps(summary, ensure_ascii=False))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Explicit lockfile, manifest or single module directory')
    parser.add_argument('reports', type=Path, help='New report directory for this lockfile')
    parser.add_argument('--severity', default='HIGH,CRITICAL')
    parser.add_argument('--trivy-image', help='Approved Trivy image pinned by digest')
    args = parser.parse_args()
    severity = args.severity.upper()
    if not set(severity.split(',')) <= {'UNKNOWN', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'}:
        parser.error('Invalid Trivy severity list')
    if args.trivy_image and (args.trivy_image.startswith('-') or '@sha256:' not in args.trivy_image):
        parser.error('Supply a Trivy image reference pinned by digest')
    try:
        return scan(args.source.resolve(), args.reports.resolve(), severity, args.trivy_image)
    except (ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
