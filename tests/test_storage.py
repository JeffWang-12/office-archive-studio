import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from app.engine import Package, DocumentError, make_sample
from app.storage import Store, safe_name


class StorageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.store = Store(self.root / 'records')

    def tearDown(self):
        self.temp.cleanup()

    def test_import_fix_export_report_bundle_and_persistence(self):
        source = self.root / '工作总结.docx'
        original = make_sample()
        source.write_bytes(original)
        j = self.store.import_file(source)
        key = j['id']
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((self.store.folder(key) / 'original.docx').read_bytes(), original)
        fixed = self.store.fix(key)
        self.assertEqual(fixed['after']['autoCount'], 0)
        target = self.root / '工作总结-已规范.docx'
        self.store.export_file(key, target)
        self.assertEqual(Package(target.read_bytes(), target.name).inspect()['autoCount'], 0)
        report = self.root / '检查报告.txt'
        self.store.export_file(key, report, 'report')
        self.assertIn('复检剩余可自动问题：0', report.read_text(encoding='utf-8-sig'))
        archive = self.root / '档案.zip'
        self.store.export_bundle([key], archive)
        with zipfile.ZipFile(archive) as z:
            self.assertEqual(len(z.namelist()), 2)
        restored = Store(self.root / 'records')
        self.assertEqual(restored.jobs[key]['status'], 'fixed')
        self.assertEqual(source.read_bytes(), original)

    def test_original_cannot_be_overwritten(self):
        source = self.root / '原始文件.docx'
        original = make_sample()
        source.write_bytes(original)
        j = self.store.import_file(source)
        self.store.fix(j['id'])
        with self.assertRaises(DocumentError):
            self.store.export_file(j['id'], source)
        with self.assertRaises(DocumentError):
            self.store.export_file(j['id'], self.store.folder(j['id']) / 'original.docx')
        with self.assertRaises(DocumentError):
            self.store.export_bundle([j['id']], source)
        self.assertEqual(source.read_bytes(), original)

    def test_reanalysis_invalidates_stale_exports(self):
        j = self.store.create('测试.docx', make_sample())
        self.store.fix(j['id'])
        checked = self.store.analyze(j['id'], {'profile': 'summary', 'titleLine': 34})
        self.assertEqual(checked['status'], 'checked')
        self.assertFalse((self.store.folder(j['id']) / 'corrected.docx').exists())
        with self.assertRaises(DocumentError):
            self.store.export_file(j['id'], self.root / 'stale.docx')

    def test_duplicate_names_in_bundle_are_retained(self):
        keys = []
        for _ in range(2):
            j = self.store.create('同名.docx', make_sample())
            self.store.fix(j['id'])
            keys.append(j['id'])
        dest = self.root / 'all.zip'
        self.store.export_bundle(keys, dest)
        with zipfile.ZipFile(dest) as z:
            self.assertEqual(len(set(z.namelist())), 4)
        self.store.remove(keys[0])
        self.assertNotIn(keys[0], self.store.jobs)
        self.assertFalse((self.store.root / keys[0]).exists())

    def test_filename_and_type_validation(self):
        self.assertEqual(safe_name('../../test.docx'), 'test.docx')
        with self.assertRaises(DocumentError):
            self.store.create('test.pdf', b'not supported')
        with self.assertRaises(DocumentError):
            self.store.create('large.docx', b'x' * (25 * 1024 * 1024 + 1))


if __name__ == '__main__':
    unittest.main()
