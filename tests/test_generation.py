from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from docx import Document
from PIL import Image

from app.engine import Package, text_of
from app.generation import GeneratorLibrary
from app.generator.generator_core import validate_values
from app.generator.photo_guard import validate_photos
from app.generator.font_embedder import _obfuscate, FontInfo
import uuid


class GenerationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)

    def tearDown(self):
        self.temp.cleanup()

    def test_source_only_custom_template_escaping_and_draft_recovery(self):
        empty = self.root / 'no-resources'
        empty.mkdir()
        with patch('app.generation.resource_root', return_value=empty):
            library = GeneratorLibrary(self.root / 'records')
        self.assertEqual(library.catalog(), {})
        template = self.root / '自用.docx'
        doc = Document()
        doc.add_paragraph('{{ project_name }}')
        doc.add_paragraph('{{ content }}')
        doc.save(template)
        library.add_template(template)
        name = next(iter(library.catalog()))
        values = {'project_name': '内容标题', 'content': '保留 <符号> & 原文\n下一段'}
        library.save_draft(name, values)
        library.save_draft(name, {**values, 'project_name': '更新草稿'})
        library.draft_path.write_text('broken', encoding='utf-8')
        restored = GeneratorLibrary(self.root / 'records')
        self.assertEqual(restored.drafts[name]['project_name'], '内容标题')
        output = self.root / '生成.docx'
        restored.generate(name, values, output)
        content = '\n'.join(text_of(p) for p in Package(output.read_bytes(), output.name).paragraphs)
        self.assertIn('保留 <符号> & 原文', content)
        self.assertIn('下一段', content)
        self.assertNotIn('{{', content)
        self.assertEqual(template.read_bytes(), (library.root / 'templates' / template.name).read_bytes())
        self.assertIn('草稿文件损坏', restored.draft_warning)

    def test_photos_numbers_dates_and_choices_are_validated(self):
        photos = []
        for i, color in enumerate(('red', 'blue')):
            path = self.root / f'{i}.png'
            Image.new('RGB', (400, 600), color).save(path)
            photos.append(str(path))
        validate_photos(photos)
        with self.assertRaises(ValueError):
            validate_photos([photos[0], photos[0]])
        tiny = self.root / 'tiny.png'
        Image.new('RGB', (100, 100), 'black').save(tiny)
        with self.assertRaises(ValueError):
            validate_photos([str(tiny)])
        spec = {'fields': [dict(name='month', label='月份', type='number', required=True, min=1, max=12),
                           dict(name='date', label='日期', type='date', required=True),
                           dict(name='choice', label='选项', type='choice', choices=['甲', '乙'], required=True)]}
        base = dict(month='11', date='2026-11-04', choice='甲')
        self.assertEqual(validate_values(spec, base)['month'], '11')
        for update in [dict(month='13'), dict(date='2026-02-30'), dict(choice='丙')]:
            with self.assertRaises(ValueError):
                validate_values(spec, {**base, **update})

    def test_font_key_uses_ooxml_byte_order_and_restricted_fonts_are_skipped(self):
        key = uuid.UUID('1DF903E3-2F14-4575-8028-881FEBABF2AB')
        # Vector uses the UUID's hexadecimal octets in reverse order (17.8.1).
        expected = bytes.fromhex('abf2abeb1f8828807545142fe303f91d') * 2
        self.assertEqual(_obfuscate(bytes(40), key), expected + bytes(8))
        self.assertTrue(FontInfo(Path('font.ttf'), 'font', (), 0x200).restricted)
        self.assertTrue(FontInfo(Path('font.ttf'), 'font', (), 2).restricted)
        self.assertFalse(FontInfo(Path('font.ttf'), 'font', (), 0).restricted)
