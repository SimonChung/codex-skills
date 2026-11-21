import argparse
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'skills/sbom-security-check/scripts'))
import scan_java as gate


class JavaTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.args = argparse.Namespace(project=self.root, reports=self.root / 'reports',
                                       severity='HIGH,CRITICAL', trivy_image=None, maven_arg=[])

    def test_non_java_project_skips_all_tools(self):
        vendor = self.root / 'node_modules' / 'example'
        vendor.mkdir(parents=True)
        (vendor / 'pom.xml').touch()
        with patch.object(gate.subprocess, 'run') as tool, contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.scan(self.args), 0)
            tool.assert_not_called()
        self.assertFalse(self.args.reports.exists())

    def test_gradle_build_without_resolved_versions_is_incomplete(self):
        (self.root / 'build.gradle.kts').touch()
        with self.assertRaisesRegex(ValueError, 'without a lockfile'):
            gate.source_file(self.root)

    def test_multiple_inputs_require_individual_scans(self):
        for name in ['pom.xml', 'gradle.lockfile', 'buildscript-gradle.lockfile']:
            (self.root / name).touch()
        with self.assertRaisesRegex(ValueError, 'each input'):
            gate.source_file(self.root)

    def test_gradle_inventory_distinguishes_test_and_unresolved_inputs(self):
        expected = {('org.example', 'test-lib', '2')}
        self.assertEqual(gate.gradle_inventory(b'org.example:test-lib:2=testRuntimeClasspath\nempty=\n'), expected)
        self.assertEqual(gate.gradle_inventory(b'empty=runtimeClasspath\n'), set())
        for data in (b'', b'empty=\n', b'org.example:test-lib=testRuntimeClasspath\n'):
            with self.subTest(data=data), self.assertRaises(ValueError):
                gate.gradle_inventory(data)

    def test_maven_tree_includes_transitive_and_test_scopes(self):
        folder = self.root / 'org.example/app/1'
        folder.mkdir(parents=True)
        root = {'groupId': 'org.example', 'artifactId': 'app', 'version': '1'}
        leaf = {**root, 'artifactId': 'indirect'}
        child = {**root, 'artifactId': 'testing', 'scope': 'test', 'children': [leaf]}
        (folder / 'tree.json').write_text(json.dumps({**root, 'children': [child]}))
        (folder / 'dependencies.cdx.json').write_text(json.dumps({
            'metadata': {'component': {'purl': 'pkg:maven/org.example/app@1?type=jar'}}}))
        expected, project = gate.maven_inventory(folder)
        self.assertEqual(project, ('org.example', 'app', '1'))
        self.assertEqual(expected, {('org.example', 'testing', '1'), ('org.example', 'indirect', '1')})
        with self.assertRaisesRegex(ValueError, 'SBOM differs'):
            gate.check_bom({'bomFormat': 'CycloneDX', 'components': []}, expected)

    def test_partial_or_wrong_ecosystem_scan_cannot_pass(self):
        item = {'Identifier': {'PURL': 'pkg:maven/org.example/lib@1?type=jar'}}
        result = {'Class': 'lang-pkgs', 'Type': 'jar', 'Packages': [item], 'Vulnerabilities': [{}]}
        report = {'SchemaVersion': 2, 'Results': [result]}
        expected = {('org.example', 'lib', '1')}
        self.assertEqual(gate.check_report(report, expected, None, 'jar'), 1)
        with self.assertRaisesRegex(ValueError, 'Missing Java'):
            gate.check_report(report, expected, None, 'gradle')
        result['Vulnerabilities'] = {}
        with self.assertRaisesRegex(ValueError, 'Invalid Java'):
            gate.check_report(report, expected, None, 'jar')
        result['Packages'] = []
        with self.assertRaisesRegex(ValueError, 'Scan differs'):
            gate.check_report(report, expected, None, 'jar')

    def test_successful_maven_exit_with_missing_module_is_incomplete(self):
        pom = self.root / 'pom.xml'
        pom.touch()
        parent = self.args.reports / 'maven/example/parent/1'
        parent.mkdir(parents=True)
        (parent / 'tree.json').touch()
        (parent / 'dependencies.cdx.json').touch()

        def partial_build(command, **kwargs):
            kwargs['stdout'].write('[INFO] Building parent 1 [1/2]\n[INFO] Building child 1 [2/2]\n')

        with patch.object(gate.subprocess, 'run', side_effect=partial_build):
            with self.assertRaisesRegex(ValueError, 'Missing Maven module'):
                gate.resolve_maven(pom, self.args.reports, [])

    def test_scanner_failure_is_distinct_from_findings(self):
        (self.root / 'gradle.lockfile').write_text('org.example:lib:1=testClasspath\n')
        with patch.object(gate, 'run_trivy', side_effect=FileNotFoundError('trivy')), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(gate.scan(self.args), 2)
        self.assertEqual(gate.read_json(self.args.reports / 'summary.json')['status'], 'incomplete')
