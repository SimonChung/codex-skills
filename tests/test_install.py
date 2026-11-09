import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

PROJECT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('manage_skills', PROJECT / 'scripts' / 'manage_skills.py')
manager = importlib.util.module_from_spec(spec)
spec.loader.exec_module(manager)


class InstallationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='codex skills test ')
        self.base = Path(self.tmp.name).resolve()
        self.repo = self.base / 'repository'
        self.dest = self.base / 'user' / 'skills'
        source = self.repo / 'skills' / 'demo-skill'
        source.mkdir(parents=True)
        (source / 'SKILL.md').write_text('---\nname: demo-skill\ndescription: Example\n---\nOriginal\n', encoding='utf-8')
        (self.repo / 'skills.json').write_text(json.dumps({'schemaVersion': 1, 'skills': ['demo-skill']}))
        (self.repo / 'scripts').mkdir()
        shutil.copy2(PROJECT / 'scripts' / 'new-junction.ps1', self.repo / 'scripts')

    def tearDown(self):
        # Remove only the installed link itself; never traverse into its source.
        target = self.dest / 'demo-skill'
        if manager.linked(target):
            if target.is_symlink():
                target.unlink()
            else:
                os.rmdir(target)
        self.tmp.cleanup()

    def test_install_is_idempotent_and_edits_reach_source(self):
        first = manager.install(self.repo, self.dest)
        self.assertEqual(first['skills'][0]['state'], 'linked')
        (self.dest / 'demo-skill' / 'SKILL.md').write_text('edited', encoding='utf-8')
        self.assertEqual((self.repo / 'skills/demo-skill/SKILL.md').read_text(), 'edited')
        self.assertEqual(manager.install(self.repo, self.dest)['backups'], [])

    def test_equal_existing_copy_is_backed_up_with_cache(self):
        target = self.dest / 'demo-skill'
        shutil.copytree(self.repo / 'skills/demo-skill', target)
        cache = target / '__pycache__'
        cache.mkdir()
        (cache / 'old.pyc').write_bytes(b'keep me')
        original = (target / 'SKILL.md').read_bytes().replace(b'\r\n', b'\n').replace(b'\n', b'\r\n')
        (target / 'SKILL.md').write_bytes(original)
        result = manager.install(self.repo, self.dest)
        backup = Path(result['backups'][0]['backup'])
        self.assertEqual((backup / 'SKILL.md').read_bytes(), original)
        self.assertEqual((backup / '__pycache__/old.pyc').read_bytes(), b'keep me')
        self.assertFalse(manager.within(backup, self.dest))

    def test_different_copy_is_not_overwritten(self):
        target = self.dest / 'demo-skill'
        target.mkdir(parents=True)
        (target / 'SKILL.md').write_text('my local edits')
        with self.assertRaisesRegex(ValueError, 'differs'):
            manager.install(self.repo, self.dest)
        self.assertEqual((target / 'SKILL.md').read_text(), 'my local edits')
        self.assertFalse((self.dest.parent / 'skill-backups').exists())

    def test_overlap_is_rejected(self):
        with self.assertRaisesRegex(ValueError, 'overlap'):
            manager.install(self.repo, self.repo / 'skills')

    def test_failed_link_restores_original_directory(self):
        from unittest.mock import patch
        target = self.dest / 'demo-skill'
        shutil.copytree(self.repo / 'skills/demo-skill', target)
        with patch.object(manager, 'create_link', side_effect=OSError('link failed')):
            with self.assertRaises(OSError):
                manager.install(self.repo, self.dest)
        self.assertFalse(manager.linked(target))
        self.assertEqual(manager.snapshot(target), manager.snapshot(self.repo / 'skills/demo-skill'))

    def test_all_skills_are_checked_before_migration(self):
        second = self.repo / 'skills/second-skill'
        second.mkdir()
        (second / 'SKILL.md').write_text('Second skill')
        (self.repo / 'skills.json').write_text(json.dumps({'schemaVersion': 1, 'skills': ['demo-skill', 'second-skill']}))
        shutil.copytree(self.repo / 'skills/demo-skill', self.dest / 'demo-skill')
        (self.dest / 'second-skill').mkdir()
        (self.dest / 'second-skill/SKILL.md').write_text('Local changes')
        with self.assertRaisesRegex(ValueError, 'differs'):
            manager.install(self.repo, self.dest)
        self.assertFalse(manager.linked(self.dest / 'demo-skill'))
        self.assertFalse((self.dest.parent / 'skill-backups').exists())

    @unittest.skipUnless(shutil.which('git'), 'Git is required for the two-checkout integration test')
    def test_git_sync_updates_installed_link_and_refuses_local_changes(self):
        def git(path, *args):
            return subprocess.run(['git', '-C', str(path), *args], check=True, capture_output=True, text=True).stdout.strip()
        git(self.repo, 'init', '-b', 'main')
        git(self.repo, 'config', 'user.name', 'Fixture')
        git(self.repo, 'config', 'user.email', 'fixture@example.invalid')
        git(self.repo, 'add', '.')
        git(self.repo, 'commit', '-m', 'Initial fixture')
        remote = self.base / 'remote.git'
        subprocess.run(['git', 'clone', '--bare', str(self.repo), str(remote)], check=True, capture_output=True)
        git(self.repo, 'remote', 'add', 'origin', str(remote))
        git(self.repo, 'push', '-u', 'origin', 'main')
        other = self.base / 'other'
        subprocess.run(['git', 'clone', str(remote), str(other)], check=True, capture_output=True)
        git(other, 'config', 'user.name', 'Fixture')
        git(other, 'config', 'user.email', 'fixture@example.invalid')
        manager.install(self.repo, self.dest)
        (other / 'skills/demo-skill/SKILL.md').write_text('Remote update\n')
        git(other, 'commit', '-am', 'Remote update')
        git(other, 'push')
        manager.sync(self.repo, self.dest)
        self.assertEqual((self.dest / 'demo-skill/SKILL.md').read_text(), 'Remote update\n')
        (self.dest / 'demo-skill/SKILL.md').write_text('Unsaved local edit\n')
        with self.assertRaisesRegex(ValueError, 'local changes'):
            manager.sync(self.repo, self.dest)
        self.assertEqual((self.dest / 'demo-skill/SKILL.md').read_text(), 'Unsaved local edit\n')


if __name__ == '__main__':
    unittest.main()
