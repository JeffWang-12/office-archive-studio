from copy import deepcopy
from pathlib import Path
import tempfile
import unittest

from app.engine import Package, make_sample, text_of, NS, val, DocumentError
from app.profiles import ProfileStore, default_standard, validate_standard
from app.storage import Store


class ProfileTests(unittest.TestCase):
    def test_custom_format_round_trip_and_immutable_job_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            profiles = ProfileStore(directory)
            standard = default_standard()
            standard['name'] = '部门自己的规范'
            standard['paper'] = 'A5'
            standard['margins'].update(top=20, bottom=20, left=18, right=18)
            standard['roles']['title'].update(font='宋体', size=20, line=30, align='left')
            standard['roles']['body'].update(font='黑体', size=12.5, line=22.5, indent=1.5, align='left')
            key = profiles.save(standard)
            options = profiles.options(key)
            store = Store(Path(directory) / 'records')
            job = store.create('测试.docx', make_sample(), options)
            options['standard']['roles']['body']['font'] = '不应影响记录'
            standard['roles']['body']['font'] = '楷体'
            profiles.save(standard, key)
            result = store.fix(job['id'])
            self.assertEqual(result['after']['autoCount'], 0)
            self.assertEqual(result['after']['standardName'], '部门自己的规范')
            fixed = Package((store.folder(job['id']) / 'corrected.docx').read_bytes(), '测试.docx')
            self.assertEqual([text_of(p) for p in fixed.paragraphs], [text_of(p) for p in Package(make_sample(), '测试.docx').paragraphs])
            body = next(p for p, role in zip(fixed.paragraphs, fixed.roles()) if role == 'body')
            self.assertEqual(val(body, 'pPr/spacing', 'line'), '450')
            self.assertEqual(val(body, 'pPr/ind', 'firstLineChars'), '150')
            self.assertEqual(body.xpath('.//w:rFonts/@w:eastAsia', namespaces=NS)[0], '黑体')
            self.assertEqual(body.xpath('.//w:sz/@w:val', namespaces=NS)[0], '25')
            self.assertEqual(fixed.document.xpath('.//w:pgSz/@w:w', namespaces=NS), ['8391'])
            self.assertEqual(ProfileStore(directory).profiles[key]['roles']['body']['font'], '楷体')
            self.assertIn('部门自己的规范', store.report(job['id']).decode('utf-8-sig'))
            profiles.remove(key)
            # Removing a preset must not invalidate existing records.
            self.assertEqual(Store(store.root).fix(job['id'])['after']['autoCount'], 0)

    def test_invalid_numbers_and_impossible_pages_rejected(self):
        for value in (float('nan'), float('inf'), -1, 500, True):
            standard = default_standard()
            standard['roles']['body']['line'] = value
            with self.assertRaises(ValueError):
                validate_standard(standard)
        standard = default_standard()
        standard['paper'] = 'A5'
        standard['margins'].update(left=80, right=80)
        with self.assertRaises(ValueError):
            validate_standard(standard)
        with self.assertRaises(DocumentError):
            Package(make_sample(), '测试.docx').inspect({'titleLine': 100})
