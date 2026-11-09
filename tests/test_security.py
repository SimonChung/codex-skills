import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('verify_sbom', Path(__file__).resolve().parents[1] / 'scripts/verify_sbom.py')
gate = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gate)


class SecurityGateTests(unittest.TestCase):
    def setUp(self):
        self.expected = {'urllib3': '1.26.5'}
        self.bom = {'bomFormat': 'CycloneDX', 'components': [{'purl': 'pkg:pypi/urllib3@1.26.5'}]}
        self.scan = {'SchemaVersion': 2, 'Results': [{'Class': 'lang-pkgs', 'Vulnerabilities': []}]}

    def test_complete_reports_pass(self):
        self.assertEqual(gate.validate_reports(self.expected, self.bom, self.scan)['packages'], 1)

    def test_high_finding_blocks(self):
        self.scan['Results'][0]['Vulnerabilities'] = [{'VulnerabilityID': 'CVE-2023-43804', 'Severity': 'HIGH'}]
        with self.assertRaisesRegex(ValueError, 'HIGH/CRITICAL'):
            gate.validate_reports(self.expected, self.bom, self.scan)

    def test_incomplete_inventory_blocks(self):
        self.bom['components'] = []
        with self.assertRaisesRegex(ValueError, 'cover'):
            gate.validate_reports(self.expected, self.bom, self.scan)

    def test_missing_scan_blocks(self):
        with self.assertRaisesRegex(ValueError, 'scan results'):
            gate.validate_reports(self.expected, self.bom, {})

    def test_scanner_failure_records_failure(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            inventory = base / 'requirements.txt'
            inventory.write_text('urllib3==1.26.5\n')
            report = base / 'report'
            with patch.object(gate.subprocess, 'run', side_effect=subprocess.CalledProcessError(2, 'docker')):
                with self.assertRaises(subprocess.CalledProcessError):
                    gate.run_scan(inventory, report)
            self.assertEqual(json.loads((report / 'summary.json').read_text())['status'], 'failed')


if __name__ == '__main__':
    unittest.main()
