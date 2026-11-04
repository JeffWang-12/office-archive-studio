import base64
import io
from pathlib import Path
import tempfile
import unittest
import zipfile

from lxml import etree as E
from docx import Document
from docx.shared import Inches

from app.engine import Package, DocumentError, make_sample, tag, NS, R, REL, CT, xml, dump, text_of, node, val, ORDERS


def mutate(data, callback):
    parts = {}
    with zipfile.ZipFile(io.BytesIO(data)) as z:
        parts = {n: z.read(n) for n in z.namelist()}
    callback(parts)
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        for n, v in parts.items():
            z.writestr(n, v)
    return out.getvalue()


class EngineTests(unittest.TestCase):
    def test_repair_rechecks_clean_and_preserves_text(self):
        source = make_sample()
        p = Package(source, '工作总结.docx')
        corrected, before, after = p.repair()
        self.assertGreater(before['autoCount'], 40)
        self.assertEqual(after['autoCount'], 0)
        q = Package(corrected, '工作总结.docx')
        self.assertEqual([text_of(x) for x in p.paragraphs], [text_of(x) for x in q.paragraphs])
        self.assertGreater(after['manualCount'], 0)
        self.assertEqual(q.repair()[2]['autoCount'], 0)

    def test_package_parts_media_comments_numbering_and_tables_preserved(self):
        d = Document()
        d.add_heading('办公室年度工作总结', 0)
        d.add_heading('一、部门工作', 1)
        d.add_paragraph('成员培训和档案归集工作。')
        d.add_paragraph('自动编号条目', style='List Number')
        table = d.add_table(rows=2, cols=2)
        table.cell(0, 0).text = '项目'
        table.cell(0, 1).text = '人数'
        table.cell(1, 0).text = '例会'
        table.cell(1, 1).text = '25'
        image = io.BytesIO(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+aX1sAAAAASUVORK5CYII='))
        d.add_picture(image, width=Inches(.2))
        comment = d.add_comment(d.paragraphs[2].runs, text='请核对内容', author='办公室')
        out = io.BytesIO()
        d.save(out)
        source = out.getvalue()
        p = Package(source, '工作总结.docx')
        original_table = E.tostring(p.document.find('.//' + tag('tbl')))
        fixed, _, after = p.repair()
        q = Package(fixed, '工作总结.docx')
        self.assertEqual(E.tostring(q.document.find('.//' + tag('tbl'))), original_table)
        for name, data in p.parts.items():
            if name not in ('word/document.xml', 'word/settings.xml', 'word/_rels/document.xml.rels', '[Content_Types].xml'):
                self.assertEqual(q.parts[name], data, name)
        self.assertEqual(after['autoCount'], 0)
        self.assertTrue(any(i['code'] == 'objects' for i in after['issues']))
        self.assertTrue(any('comments' in n for n in q.parts))
        self.assertTrue(any(n.startswith('word/media/') for n in q.parts))
        reopened = Document(io.BytesIO(fixed))
        self.assertEqual(len(reopened.tables), 1)

    def test_four_and_three_level_heading_conventions(self):
        def replace(parts):
            root = xml(parts['word/document.xml'])
            ts = root.xpath('.//w:t', namespaces=NS)
            for t, value in zip(ts, ['标题', '一、一级', '（一）二级', '1. 三级', '（1）四级']):
                t.text = value
            parts['word/document.xml'] = dump(root)
        p = Package(mutate(make_sample(), replace), '测试.docx')
        self.assertEqual(p.roles()[:5], ['title', 'h1', 'h2', 'h3', 'h4'])
        self.assertEqual(Package(make_sample(), '测试.docx').roles()[3], 'h2')

    def test_textboxes_are_not_flattened_or_reformatted(self):
        def textbox(parts):
            root = xml(parts['word/document.xml'])
            p = root.find('.//' + tag('p'))
            box = E.SubElement(E.SubElement(E.SubElement(p, tag('r')), tag('pict')), tag('txbxContent'))
            inner = E.SubElement(box, tag('p'))
            rp = E.SubElement(E.SubElement(inner, tag('r')), tag('rPr'))
            node(rp, 'sz', val=18)
            E.SubElement(rp.getparent(), tag('t')).text = '独立文本框'
            parts['word/document.xml'] = dump(root)
        p = Package(mutate(make_sample(), textbox), '测试.docx')
        self.assertNotIn('独立文本框', text_of(p.paragraphs[0]))
        before = E.tostring(p.document.find('.//' + tag('txbxContent')))
        data, _, _ = p.repair()
        q = Package(data, '测试.docx')
        self.assertEqual(E.tostring(q.document.find('.//' + tag('txbxContent'))), before)
        self.assertIn('object', q.roles())

    def test_paragraph_override_is_honored(self):
        p = Package(make_sample(), '测试.docx')
        roles = p.roles({'0': 'body', '1': 'title'})
        self.assertEqual(roles[:2], ['body', 'title'])
        fixed, _, after = p.repair({'roles': {'0': 'body', '1': 'title'}, 'titleLine': 33})
        q = Package(fixed, '测试.docx')
        self.assertEqual(val(q.paragraphs[1], 'pPr/spacing', 'line'), '660')
        self.assertEqual(after['autoCount'], 0)

    def test_complex_footer_is_kept(self):
        d = Document(io.BytesIO(make_sample()))
        d.sections[0].footer.paragraphs[0].text = '办公室内部资料'
        out = io.BytesIO()
        d.save(out)
        p = Package(out.getvalue(), '测试.docx')
        fixed, _, after = p.repair()
        q = Package(fixed, '测试.docx')
        for name in p.parts:
            if 'footer' in name:
                self.assertEqual(p.parts[name], q.parts[name])
        self.assertTrue(any(i['code'] == 'complex-footer' and not i['auto'] for i in after['issues']))

    def test_revisions_and_protection_are_not_bypassed(self):
        def revisions(parts):
            root = xml(parts['word/document.xml'])
            E.SubElement(root.find('.//' + tag('p')), tag('ins'))
            parts['word/document.xml'] = dump(root)
        p = Package(mutate(make_sample(), revisions), '测试.docx')
        self.assertFalse(p.inspect()['canFix'])
        with self.assertRaises(DocumentError):
            p.repair()
        d = Document(io.BytesIO(make_sample()))
        node(d.settings.element, 'documentProtection', edit='readOnly', enforcement=1)
        out = io.BytesIO(); d.save(out)
        with self.assertRaises(DocumentError):
            Package(out.getvalue(), '测试.docx').repair()

    def test_corrupt_macro_and_entity_packages_rejected(self):
        with self.assertRaises(DocumentError):
            Package(b'not a zip file', '测试.docx')
        with self.assertRaises(DocumentError):
            Package(mutate(make_sample(), lambda p: p.update({'word/vbaProject.bin': b'x'})), '测试.docx')
        def entity(parts):
            parts['word/document.xml'] = b'<!DOCTYPE x [<!ENTITY a SYSTEM "file:///test">]><x/>'
        with self.assertRaises(DocumentError):
            Package(mutate(make_sample(), entity), '测试.docx')

    def test_property_order_and_first_page_dynamic_footer(self):
        data, _, _ = Package(make_sample(), '测试.docx').repair()
        p = Package(data, '测试.docx')
        for kind, sequence in ORDERS.items():
            order = {tag(n): i for i, n in enumerate(sequence.split())}
            for parent in p.document.iter(tag(kind)):
                indexes = [order.get(c.tag, len(order)) for c in parent]
                self.assertEqual(indexes, sorted(indexes))
        self.assertEqual(val(p.settings, 'updateFields'), '0')
        sect = p.document.find('.//' + tag('sectPr'))
        self.assertIsNotNone(sect.find(tag('titlePg')))
        relmap = {r.get('Id'): r.get('Target') for r in p.rels}
        first = next(r for r in sect.findall(tag('footerReference')) if r.get(tag('type')) == 'first')
        root = xml(p.parts['word/' + relmap[first.get('{' + R + '}id')]])
        self.assertEqual(text_of(root), '')
        self.assertTrue(p.footer_valid())

    def test_generated_assessment_document_preserves_table(self):
        document = Document()
        document.add_paragraph('附件：')
        document.add_paragraph('档案格式测试方案')
        document.add_paragraph('一、检查方式')
        document.add_paragraph('这是一份程序生成的测试材料。')
        grid = document.add_table(rows=2, cols=2)
        grid.cell(0, 0).text = '检查项目'
        grid.cell(0, 1).text = '处理结果'
        grid.cell(1, 0).text = '文档格式'
        grid.cell(1, 1).text = '待核对'
        stream = io.BytesIO()
        document.save(stream)
        source = stream.getvalue()
        p = Package(source, '档案格式测试方案.docx')
        table = E.tostring(p.document.find('.//' + tag('tbl')))
        data, _, after = p.repair({'roles': {'0': 'body', '1': 'title'}})
        q = Package(data, '档案格式测试方案.docx')
        self.assertEqual(table, E.tostring(q.document.find('.//' + tag('tbl'))))
        self.assertEqual(after['autoCount'], 0)


if __name__ == '__main__':
    unittest.main()
