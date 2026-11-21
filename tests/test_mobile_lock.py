import contextlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/sbom-security-check/scripts'))
import scan_mobile_lock as gate


class MobileLockTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_unrelated_dependency_copy_skips_all_tools(self):
        vendor = self.root / 'node_modules/sample'
        vendor.mkdir(parents=True)
        (vendor / 'pubspec.lock').touch()
        with patch.object(gate, 'run_trivy') as scanner, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.scan(self.root, self.root / 'reports', 'HIGH,CRITICAL', None), 0)
            scanner.assert_not_called()
        self.assertFalse((self.root / 'reports').exists())

    def test_mixed_project_requires_each_input(self):
        (self.root / 'Podfile.lock').touch()
        (self.root / 'pubspec.yaml').touch()
        with self.assertRaisesRegex(ValueError, 'each applicable lock'):
            gate.find_lock(self.root)
        with self.assertRaisesRegex(ValueError, 'lockfile'):
            gate.find_lock(self.root / 'pubspec.yaml')

    def test_xcode_workspace_and_missing_package_resolution(self):
        project = self.root / 'App.xcodeproj'
        project.mkdir()
        (project / 'project.pbxproj').write_text('isa = XCRemoteSwiftPackageReference;')
        (self.root / 'Podfile.lock').touch()
        with self.assertRaisesRegex(ValueError, 'Xcode declares'):
            gate.find_lock(self.root)
        workspace = self.root / 'App.xcworkspace'
        lock = workspace / 'xcshareddata/swiftpm/Package.resolved'
        lock.parent.mkdir(parents=True)
        lock.touch()
        self.assertEqual(gate.find_lock(workspace), lock)

    def test_pub_sdk_git_and_private_origins(self):
        data = {'packages': {
            'archive': {'version': '3', 'source': 'hosted', 'description': {'url': 'https://pub.dev'}},
            'fork': {'version': '2', 'source': 'hosted', 'description': {'url': 'https://registry.example'}},
            'flutter': {'version': '0.0.0', 'source': 'sdk'},
            'gitpkg': {'version': '1', 'source': 'git', 'description': {'resolved-ref': 'abc'}}}}
        inv = gate.pub_inventory(data)
        self.assertEqual(set(inv.gaps), {'fork', 'gitpkg'})
        self.assertEqual(inv.revisions, {'gitpkg': 'abc'})
        self.assertEqual(inv.sdk, ['flutter'])

    @unittest.skipUnless(importlib.util.find_spec('yaml'), 'Pub/Pods parser requires the validation environment')
    def test_yaml_preserves_package_identifiers_and_rejects_duplicates(self):
        self.assertEqual(gate.read_yaml(b'packages:\n  on: 1.0\n'), {'packages': {'on': '1.0'}})
        with self.assertRaisesRegex(ValueError, 'Duplicate'):
            gate.read_yaml(b'packages: {}\npackages: {}\n')

    def test_swift_schemas_owner_and_revision(self):
        url = 'https://github.com/A/Library.git'
        state = {'version': '1.2.3'}
        v1 = {'version': 1, 'object': {'pins': [{'package': 'Library', 'repositoryURL': url, 'state': state}]}}
        self.assertEqual(gate.swift_inventory(v1).packages, {'github.com/a/library': '1.2.3'})
        for schema in (2, 3):
            data = {'version': schema, 'pins': [
                {'identity': 'library', 'location': url, 'state': state},
                {'identity': 'fork', 'location': 'git@github.com:B/library.git', 'state': {'revision': 'abc'}},
                {'identity': 'example.other', 'kind': 'registry', 'state': state}]}
            inv = gate.swift_inventory(data)
            self.assertEqual(set(inv.gaps), {'github.com/b/library', 'example.other'})
            self.assertEqual(inv.revisions['github.com/b/library'], 'abc')
        with self.assertRaisesRegex(ValueError, 'Unsupported'):
            gate.swift_inventory({'version': 4, 'pins': []})

    def test_pods_preserve_subspec_and_local_sources(self):
        data = {'PODS': [{'Net/Core (2.0)': ['Other']}, 'Other (1.0)'],
                'SPEC REPOS': {'trunk': ['Net']}, 'EXTERNAL SOURCES': {'Other': {':path': '../Other'}}}
        inv = gate.pods_inventory(data)
        self.assertEqual(inv.packages, {'Net/Core': '2.0', 'Other': '1.0'})
        self.assertEqual(set(inv.gaps), {'Other'})
        self.assertEqual(gate.coordinate('pkg:cocoapods/Net@2.0#Core', 'cocoapods'), ('Net/Core', '2.0'))

    def test_both_reports_must_cover_exact_versions_and_keep_confirmed_findings(self):
        purl = 'pkg:pub/archive@3.3.5'
        inv = gate.Inventory(packages={'archive': '3.3.5', 'fork': '1'}, gaps={'fork': 'Private origin'})
        bom = {'bomFormat': 'CycloneDX', 'components': [{'purl': purl}]}
        result = {'Type': 'pub', 'Class': 'lang-pkgs', 'Packages': [{'Identifier': {'PURL': purl}}],
                  'Vulnerabilities': [{'PkgName': 'archive', 'InstalledVersion': '3.3.5'},
                                      {'PkgName': 'fork', 'InstalledVersion': '1'}]}
        scan = {'SchemaVersion': 2, 'Results': [result]}
        self.assertEqual(gate.check_reports(inv, 'pub', scan, bom), (1, 1))
        with self.assertRaisesRegex(ValueError, 'CycloneDX differs'):
            gate.check_reports(inv, 'pub', scan, {**bom, 'components': [{'purl': 'pkg:pub/archive@3.4.0'}]})
        result['Packages'] = []
        with self.assertRaisesRegex(ValueError, 'Trivy differs'):
            gate.check_reports(inv, 'pub', scan, bom)

    def test_partial_swift_scan_preserves_finding_and_revision(self):
        repo = 'https://github.com/Example/'
        pins = [{'identity': 'lib', 'location': repo + 'Lib.git', 'state': {'version': '1'}},
                {'identity': 'fork', 'location': repo + 'Fork.git', 'state': {'revision': 'abc'}}]
        lock = self.root / 'Package.resolved'
        lock.write_text(json.dumps({'version': 3, 'pins': pins}))
        purl = 'pkg:swift/github.com/example/lib@1'

        def scan_snapshot(inputs, reports, severity, image):
            self.assertEqual((inputs / lock.name).read_bytes(), lock.read_bytes())
            package = {'Identifier': {'PURL': purl}}
            result = {'Class': 'lang-pkgs', 'Type': 'swift', 'Packages': [package],
                      'Vulnerabilities': [{'PkgName': 'github.com/Example/Lib', 'InstalledVersion': '1'}]}
            (reports / 'vulnerabilities.json').write_text(json.dumps({'SchemaVersion': 2, 'Results': [result]}))
            (reports / 'dependencies.cdx.json').write_text(json.dumps({
                'bomFormat': 'CycloneDX', 'components': [{'purl': purl}]}))
            return {}

        reports = self.root / 'reports'
        with patch.object(gate, 'run_trivy', side_effect=scan_snapshot), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.scan(lock, reports, 'HIGH,CRITICAL', None), 2)
        summary = json.loads((reports / 'summary.json').read_bytes())
        self.assertEqual(summary['status'], 'incomplete')
        self.assertEqual(summary['findings'], 1)
        self.assertEqual(summary['revisions'], {'github.com/example/fork': 'abc'})
