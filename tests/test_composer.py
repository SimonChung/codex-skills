import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/sbom-security-check/scripts'))
import scan_composer as gate


class ComposerTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        self.report = self.root / 'report'
        self.lock = self.root / 'composer.lock'
        self.prod = {'name': 'psr/log', 'version': '3.0.2'}
        self.dev = {'name': 'guzzlehttp/psr7', 'version': '1.8.4'}

    def run_gate(self):
        with contextlib.redirect_stdout(io.StringIO()):
            return gate.scan(self.root, self.report, 'HIGH,CRITICAL')

    def test_no_project_composer_files_skips_scanner(self):
        vendor = self.root / 'node_modules' / 'sample'
        vendor.mkdir(parents=True)
        (vendor / 'composer.json').write_text('{}')
        with patch.object(gate, 'run_trivy') as scanner:
            self.assertEqual(self.run_gate(), 0)
            self.assertFalse(self.report.exists())
            scanner.assert_not_called()

    def test_manifest_without_lock_is_incomplete(self):
        (self.root / 'composer.json').write_text('{"require":{"psr/log":"^3"}}')
        with patch.object(gate, 'run_trivy') as scanner:
            self.assertEqual(self.run_gate(), 2)
            self.assertEqual(gate.read_json(self.report / 'summary.json')['status'], 'incomplete')
            scanner.assert_not_called()

    def test_empty_locked_inventory_skips_scanner(self):
        self.lock.write_text('{"packages":[],"packages-dev":[]}')
        with patch.object(gate, 'run_trivy') as scanner:
            self.assertEqual(self.run_gate(), 0)
            self.assertEqual(gate.read_json(self.report / 'summary.json')['status'], 'no-locked-packages')
            scanner.assert_not_called()

    def test_scanner_error_is_incomplete(self):
        self.lock.write_text(json.dumps({'packages': [], 'packages-dev': [self.dev]}))
        with patch.object(gate, 'run_trivy', side_effect=FileNotFoundError('trivy')):
            self.assertEqual(self.run_gate(), 2)
            self.assertEqual(gate.read_json(self.report / 'summary.json')['status'], 'incomplete')

    def test_both_reports_must_cover_locked_versions_including_dev(self):
        expected = gate.inventory({'packages': [self.prod], 'packages-dev': [self.dev]})
        self.assertEqual(expected, {'psr/log@3.0.2', 'guzzlehttp/psr7@1.8.4'})
        packages = [{'Name': p['name'], 'Version': p['version']} for p in [self.prod, self.dev]]
        finding = {'PkgName': self.dev['name'], 'Severity': 'HIGH'}
        result = {'Target': 'composer.lock', 'Class': 'lang-pkgs', 'Type': 'composer',
                  'Packages': packages, 'Vulnerabilities': [finding]}
        scan = {'SchemaVersion': 2, 'Results': [result]}
        bom = {'bomFormat': 'CycloneDX', 'components': [{'purl': 'pkg:composer/' + p} for p in expected]}
        self.assertEqual(gate.check_coverage(expected, scan, bom), [finding])
        with self.assertRaises(ValueError):
            gate.check_coverage(expected, scan, {**bom, 'components': []})
        with self.assertRaises(ValueError):
            gate.check_coverage(expected, {**scan, 'Results': []}, bom)
        packages[1]['Version'] = '2.0.0'
        with self.assertRaises(ValueError):
            gate.check_coverage(expected, scan, bom)
