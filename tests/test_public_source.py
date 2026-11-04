from pathlib import Path
import tempfile
import unittest

from app.platform import font_catalog
from scripts.package_release import source_files


class PublicSourceTests(unittest.TestCase):
    def test_font_detection_does_not_require_bundled_fonts(self):
        with tempfile.TemporaryDirectory() as directory:
            fonts = font_catalog(directory, {'仿宋_GB2312 (TrueType)', 'simsun.ttc'})
        self.assertEqual(len(fonts), 7)
        self.assertTrue(next(f for f in fonts if f['name'] == '仿宋_GB2312')['installed'])
        self.assertTrue(next(f for f in fonts if f['name'] == '宋体')['installed'])
        self.assertFalse(next(f for f in fonts if f['name'] == '楷体_GB2312')['installed'])
        self.assertTrue(all(f['file'] is None for f in fonts))

    def test_public_source_excludes_private_resource_files(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for name in ('app', 'assets/fonts', 'assets/reference', 'scripts', 'tests', 'docs'):
                (root / name).mkdir(parents=True, exist_ok=True)
            for name in ('assets/fonts/font.ttf', 'assets/reference/rules.pdf', 'assets/reference/assessment.docx',
                         'assets/fonts/README.md', 'assets/reference/README.md', 'app/test.py'):
                (root / name).write_text('test', encoding='utf-8')
            paths = [str(p.relative_to(root)).replace('\\', '/') for p, _ in source_files(root)]
        self.assertNotIn('assets/fonts/font.ttf', paths)
        self.assertNotIn('assets/reference/rules.pdf', paths)
        self.assertNotIn('assets/reference/assessment.docx', paths)
        self.assertIn('assets/fonts/README.md', paths)
        self.assertIn('assets/reference/README.md', paths)
        self.assertIn('app/test.py', paths)


if __name__ == '__main__':
    unittest.main()
