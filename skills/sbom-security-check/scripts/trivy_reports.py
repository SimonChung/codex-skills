"""Generate local Trivy reports from isolated inputs or an existing CycloneDX SBOM."""
import json
from pathlib import Path
import subprocess


def run_trivy(inputs: Path, reports: Path, severity: str, image: str | None, *,
              scan_bom: bool = False) -> dict:
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
    options = ['--scanners', 'vuln', '--list-all-pkgs', '--severity', severity,
               '--ignorefile', '.trivyignore', '--ignore-unfixed=false',
               '--exit-code', '0', '--format', 'json', '--output', scan_path]
    if scan_bom:
        subprocess.run([*trivy, 'sbom', *options, bom_path], cwd=inputs, check=True)
    else:
        subprocess.run([*trivy, 'fs', '--include-dev-deps', *options, '.'], cwd=inputs, check=True)
        subprocess.run([*trivy, 'convert', '--format', 'cyclonedx', '--output', bom_path, scan_path],
                       cwd=inputs, check=True)
    version = subprocess.check_output([*trivy, 'version', '--format', 'json'], cwd=inputs)
    metadata = json.loads(version)
    if not metadata.get('Version') or not metadata.get('VulnerabilityDB', {}).get('UpdatedAt'):
        raise ValueError('Missing Trivy version or vulnerability database timestamp')
    return metadata
