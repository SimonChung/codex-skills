import importlib.util
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'tests/fixtures/conversion'


@unittest.skipUnless(importlib.util.find_spec('markitdown'), 'Install the validation environment for real conversions')
class ConversionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory(prefix='轉檔 測試 ')
        self.addCleanup(temp.cleanup)
        self.directory = Path(temp.name)

    def convert(self, skill, script, *args):
        subprocess.run([sys.executable, ROOT / 'skills' / skill / 'scripts' / script, *args],
                       check=True, stdout=subprocess.PIPE)

    def test_pdf_pages_and_existing_output(self):
        source = self.directory / '路線.pdf'
        shutil.copyfile(FIXTURES / 'checklist.pdf', source)
        self.convert('pdf-to-markdown', 'pdf_to_markdown.py', source)
        output = source.with_suffix('.md')
        lines = [line for line in output.read_text(encoding='utf-8').splitlines() if line]
        self.assertEqual(lines, ['Page 1 - Arrival', '入口報到', 'Desk A - 09:00',
                                 'Page 2 - Departure', '完成簽退', 'Contact: desk@example.invalid'])
        output.write_bytes(b'keep existing\n')
        self.convert('pdf-to-markdown', 'pdf_to_markdown.py', self.directory, '--recursive', '--skip-existing')
        self.assertEqual(output.read_bytes(), b'keep existing\n')
        self.assertEqual(source.read_bytes(), (FIXTURES / 'checklist.pdf').read_bytes())

    def test_docx_structure_and_image_modes(self):
        source = self.directory / 'notes v1.docx'
        shutil.copyfile(FIXTURES / 'checklist.docx', source)
        self.convert('word-to-markdown', 'docx_to_markdown.py', source)
        markdown = source.with_suffix('.md').read_text(encoding='utf-8')
        self.assertNotIn('data:image/', markdown)
        with ZipFile(source) as docx:
            for name, alt in [('image1.png', '入口標示'), ('image2.png', '出口標示')]:
                self.assertIn(f'![{alt}](notes%20v1_assets/{name})', markdown)
                self.assertIn(f'![{name}](notes%20v1_assets/{name})', markdown)
                self.assertEqual((self.directory / 'notes v1_assets' / name).read_bytes(),
                                 docx.read(f'word/media/{name}'))

        output = self.directory / '純文字.md'
        self.convert('word-to-markdown', 'docx_to_markdown.py', source, '--no-images', '--output', output)
        text_only = output.read_text(encoding='utf-8')
        self.assertNotIn('![', text_only)
        self.assertFalse((self.directory / '純文字_assets').exists())
        for text in (markdown, text_only):
            for part in ('# 驗收清單', '第一段核對內容。', '* 確認入口', '| 站點 | 時間 |',
                         '| 入口 | 09:00 |', '[操作指南](https://example.invalid/guide)'):
                self.assertIn(part, text)
        self.assertEqual(source.read_bytes(), (FIXTURES / 'checklist.docx').read_bytes())


if __name__ == '__main__':
    unittest.main()
