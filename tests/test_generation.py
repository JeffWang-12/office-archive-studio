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
import json


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

    def test_auto_save_privacy_memory_and_selective_clear(self):
        library = GeneratorLibrary(self.root / 'records')
        library.save_draft('甲', {'content': '甲的内容'})
        library.save_draft('乙', {'content': '乙的内容'})
        library.clear_drafts('甲')
        restored = GeneratorLibrary(self.root / 'records')
        self.assertNotIn('甲', restored.drafts)
        self.assertIn('乙', restored.drafts)
        self.assertFalse(library.draft_path.with_suffix('.bak').exists())
        library.set_auto_save(False)
        library.save_draft('甲', {'content': '仅在内存中'})
        self.assertEqual(library.drafts['甲']['content'], '仅在内存中')
        self.assertFalse(library.draft_path.exists())
        self.assertFalse(library.draft_path.with_suffix('.bak').exists())
        self.assertFalse(GeneratorLibrary(self.root / 'records').auto_save)
        self.assertEqual(GeneratorLibrary(self.root / 'records').drafts, {})
        library.set_auto_save(True)
        self.assertIn('甲', GeneratorLibrary(self.root / 'records').drafts)
        library.clear_drafts()
        self.assertEqual(GeneratorLibrary(self.root / 'records').drafts, {})

    def test_upgrade_fills_missing_resources_and_keeps_user_template(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with patch('app.generation.resource_root', return_value=empty):
            library = GeneratorLibrary(self.root / 'records')
        (library.root / '.initialized').write_text('1', encoding='utf-8')
        bundle = self.root / 'bundle'
        folder = bundle / 'assets/generator/templates'
        folder.mkdir(parents=True)
        doc = Document()
        doc.add_paragraph('{{ content }}')
        source = folder / '自有模板.docx'
        doc.save(source)
        with patch('app.generation.resource_root', return_value=bundle):
            upgraded = GeneratorLibrary(self.root / 'records')
        self.assertEqual(len(upgraded.catalog()), 1)
        target = upgraded.root / 'templates/自有模板.docx'
        doc.add_paragraph('用户自己的修改')
        doc.save(target)
        original = target.read_bytes()
        with patch('app.generation.resource_root', return_value=bundle):
            GeneratorLibrary(self.root / 'records')
        self.assertEqual(target.read_bytes(), original)

    def test_one_click_output_preferences_and_custom_template_replacement(self):
        empty = self.root / 'empty'
        empty.mkdir()
        with patch('app.generation.resource_root', return_value=empty):
            library = GeneratorLibrary(self.root / 'records')
        template = self.root / 'first.docx'
        doc = Document()
        doc.add_paragraph('{{ content }}')
        doc.save(template)
        library.replace_custom_template(template)
        name = next(iter(library.catalog()))
        library.remember(defaultTemplate=name, outputDirectory=str(self.root / 'output'))
        values = dict(project_name='同名/项目:*', content='保持内容')
        first = library.generate(name, values)
        second = library.generate(name, values)
        self.assertNotEqual(first.output_path, second.output_path)
        self.assertTrue(first.output_path.is_file())
        self.assertEqual(first.output_path.parent, self.root / 'output')
        self.assertNotIn('/', first.output_path.name)
        self.assertEqual(GeneratorLibrary(self.root / 'records').preferences['defaultTemplate'], name)
        old = (library.root / '模板.docx').read_bytes()
        doc.add_paragraph('{{ extra }}')
        doc.save(template)
        library.replace_custom_template(template)
        self.assertEqual((library.root / '自定义模板备份.docx').read_bytes(), old)
        self.assertIn('extra', {f['name'] for f in library.catalog()[name]['fields']})

    def test_legacy_draft_import_and_explicit_plain_text_backup(self):
        library = GeneratorLibrary(self.root / 'records')
        path = self.root / '填写草稿.json'
        old = {'年度档案封皮': {'college_name': '测试学院', 'school_year_start': '2026'}}
        path.write_text(json.dumps(old, ensure_ascii=False), encoding='utf-8-sig')
        library.import_drafts(library.read_drafts(path))
        self.assertEqual(library.drafts['年度档案封皮']['college_name'], '测试学院')
        destination = self.root / 'backup.json'
        library.export_drafts(destination)
        self.assertEqual(library.read_drafts(destination), old)
        path.write_text('[]', encoding='utf-8')
        with self.assertRaises(ValueError):
            library.read_drafts(path)
