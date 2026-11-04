"""Deterministic, package-preserving WordprocessingML inspection and repair.

Only formatting parts are rewritten. Text, relationships, media, tables, fields,
bookmarks and comments are retained. No document is opened as executable code.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass
from lxml import etree as E

W = 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'
R = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'
REL = 'http://schemas.openxmlformats.org/package/2006/relationships'
CT = 'http://schemas.openxmlformats.org/package/2006/content-types'
NS = {'w': W, 'r': R}
FONTS = {'title': '方正小标宋简体', 'subtitle': '楷体_GB2312', 'h1': '黑体',
         'h2': '楷体_GB2312', 'h3': '仿宋_GB2312', 'h4': '仿宋_GB2312',
         'body': '仿宋_GB2312', 'date': '仿宋_GB2312', 'signature': '仿宋_GB2312',
         'attachment': '黑体'}
LABELS = {'title': '主标题', 'subtitle': '副标题 / 单位', 'h1': '一级标题', 'h2': '二级标题',
          'h3': '三级标题', 'h4': '四级标题', 'body': '正文', 'date': '成文日期',
          'signature': '发文机关署名', 'attachment': '附件标识', 'table': '表格内容（保留）',
          'object': '文本框内容（保留）', 'blank': '空行'}
RULES = [
    {'group': '版面', 'name': '纸张与页边距', 'value': 'A4 · 上 3.7 / 下 3.5 / 左 2.8 / 右 2.6 cm', 'source': '格式规范第 1 页 · 一、二', 'auto': True},
    {'group': '字体', 'name': '主标题', 'value': '方正小标宋 · 二号 22 pt · 居中 · 行距 33–36 pt', 'source': '格式规范第 1、2 页 · 三、六', 'auto': True},
    {'group': '字体', 'name': '正文与前言', 'value': '仿宋_GB2312 · 三号 16 pt · 固定行距 28 pt', 'source': '格式规范第 1、3 页 · 三、六', 'auto': True},
    {'group': '字体', 'name': '各级标题', 'value': '一级黑体 / 二级楷体_GB2312 / 三四级仿宋_GB2312 · 三号', 'source': '格式规范第 1 页 · 三', 'auto': True},
    {'group': '段落', 'name': '缩进与间距', 'value': '正文及各级标题首行 2 字符 · 段前段后 0 · 默认字距', 'source': '格式规范第 1、3 页 · 二、六', 'auto': True},
    {'group': '页码', 'name': '页眉页脚', 'value': '首页无页码 · 居中 —页码— · 四号宋体 · 页眉 1.5 / 页脚 2.5 cm', 'source': '格式规范第 2 页 · 五', 'auto': True},
    {'group': '结构', 'name': '标题层级', 'value': '四层：一、 / （一） / 1. / （1）；两层、三层按原规范变体', 'source': '格式规范第 2 页 · 四', 'auto': False},
    {'group': '落款', 'name': '署名与日期', 'value': '日期用完整阿拉伯数字，无虚位；右空 4 字格，署名与日期居中对齐', 'source': '格式规范第 3 页 · 七', 'auto': False},
    {'group': '附件', 'name': '附件编排', 'value': '附件说明正文下空一行；附件另面，标识左上顶格，标题第三行居中', 'source': '格式规范第 2、3 页 · 四、八', 'auto': False},
    {'group': '归档', 'name': '文件命名', 'value': '一般：文档名-处理人-年月日；工作总结：学院名称-工作总结-时间范围', 'source': '格式规范第 4 页 · 九；考核方案 · 考核流程', 'auto': False},
    {'group': '打印', 'name': '提交与打印', 'value': '建议双面、左侧装订；转为 PDF 打印；工作总结纸质版需盖章', 'source': '格式规范第 1、3 页；考核方案 · 考核流程', 'auto': False},
]


class DocumentError(ValueError):
    pass


def tag(name):
    return '{' + W + '}' + name


def node(parent, name, **attrs):
    child = parent.find(tag(name))
    if child is None:
        child = E.SubElement(parent, tag(name))
    for key, value in attrs.items():
        child.set(tag(key), str(value))
    return child


def val(parent, path, attr='val', default=None):
    if parent is None:
        return default
    child = parent.find('/'.join(tag(x) for x in path.split('/')))
    return child.get(tag(attr), default) if child is not None else default


def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise DocumentError('文档含不受支持的 XML 声明，请在 Word 或 WPS 中另存为 DOCX。')
    return E.fromstring(data, parser=E.XMLParser(resolve_entities=False, no_network=True))


def dump(root):
    return E.tostring(root, encoding='UTF-8', xml_declaration=True, standalone=True)


def text_of(p):
    if p.tag == tag('p'):
        return ''.join(t.text or '' for t in p.iter(tag('t'))
                       if next(t.iterancestors(tag('p')), None) is p)
    return ''.join(p.xpath('.//w:t/text()', namespaces=NS))


def runs_of(p):
    return [r for r in p.iter(tag('r')) if next(r.iterancestors(tag('p')), None) is p]


# ECMA-376 child sequence. Keeping these orders matters to Word's strict reader.
ORDERS = {
    'pPr': 'pStyle keepNext keepLines pageBreakBefore framePr widowControl numPr suppressLineNumbers pBdr shd tabs suppressAutoHyphens kinsoku wordWrap overflowPunct topLinePunct autoSpaceDE autoSpaceDN bidi adjustRightInd snapToGrid spacing ind contextualSpacing mirrorIndents suppressOverlap jc textDirection textAlignment textboxTightWrap outlineLvl divId cnfStyle rPr sectPr pPrChange',
    'rPr': 'rStyle rFonts b bCs i iCs caps smallCaps strike dstrike outline shadow emboss imprint noProof snapToGrid vanish webHidden color spacing w kern position sz szCs highlight u effect bdr shd fitText vertAlign rtl cs em lang eastAsianLayout specVanish oMath rPrChange',
    'sectPr': 'headerReference footerReference footnotePr endnotePr type pgSz pgMar paperSrc pgBorders lnNumType pgNumType cols formProt vAlign noEndnote titlePg textDirection bidi rtlGutter docGrid printerSettings sectPrChange',
}


def order_properties(root):
    for kind, sequence in ORDERS.items():
        order = {tag(name): i for i, name in enumerate(sequence.split())}
        for parent in root.iter(tag(kind)):
            # Python's sort is stable, so repeated references retain their order.
            parent[:] = sorted(parent, key=lambda child: order.get(child.tag, len(order)))


def normalize_font(name):
    return (name or '').replace(' ', '').replace('_', '').replace('-', '').lower()


@dataclass
class Package:
    data: bytes
    name: str

    def __post_init__(self):
        try:
            z = zipfile.ZipFile(io.BytesIO(self.data))
            infos = z.infolist()
            if len(infos) > 3500 or sum(x.file_size for x in infos) > 120 * 1024 * 1024:
                raise DocumentError('文档解压后过大（上限 120 MB / 3500 个部件）。')
            if len({x.filename for x in infos}) != len(infos):
                raise DocumentError('文档包有重复部件，请重新另存。')
            if any(x.flag_bits & 1 for x in infos):
                raise DocumentError('暂不支持加密文档，请先解除密码。')
            if any('vbaproject' in x.filename.lower() for x in infos):
                raise DocumentError('请先将含宏文档另存为不含宏的 DOCX。')
            self.parts = {x.filename: z.read(x) for x in infos}
            self.document = xml(self.parts['word/document.xml'])
            self.types = xml(self.parts['[Content_Types].xml'])
            self.styles = xml(self.parts['word/styles.xml']) if 'word/styles.xml' in self.parts else E.Element(tag('styles'))
            self.settings = xml(self.parts['word/settings.xml']) if 'word/settings.xml' in self.parts else E.Element(tag('settings'), nsmap={'w': W})
            self.rels = xml(self.parts['word/_rels/document.xml.rels']) if 'word/_rels/document.xml.rels' in self.parts else E.Element('{' + REL + '}Relationships', nsmap={None: REL})
        except DocumentError:
            raise
        except (zipfile.BadZipFile, KeyError, E.XMLSyntaxError, RuntimeError, NotImplementedError) as exc:
            raise DocumentError('无法读取 DOCX。文件可能已损坏、已加密，或实际是旧版 DOC。') from exc
        if 'wordprocessingml.document.main+xml' not in self.parts['[Content_Types].xml'].decode('utf-8', errors='replace'):
            raise DocumentError('当前仅支持标准 DOCX 文档，请先在 Word / WPS 中另存。')
        self.paragraphs = self.document.xpath('.//w:body//w:p', namespaces=NS)
        self.style_map = {s.get(tag('styleId')): s for s in self.styles.findall(tag('style'))}

    def style_chain(self, p):
        chain, seen = [], set()
        current = val(p, 'pPr/pStyle', default='Normal')
        while current in self.style_map and current not in seen:
            seen.add(current)
            style = self.style_map[current]
            chain.append(style)
            current = val(style, 'basedOn')
        return chain

    def effective(self, p, path, attr='val', run=None):
        if run is not None:
            value = val(run, path, attr)
            if value is not None:
                return value
            rstyle = self.style_map.get(val(run, 'rPr/rStyle'))
            if rstyle is not None:
                value = val(rstyle, path, attr)
                if value is not None:
                    return value
        for parent in [p] + self.style_chain(p):
            value = val(parent, path, attr)
            if value is not None:
                return value
        return val(self.styles, 'docDefaults/' + ('rPrDefault/' if path.startswith('rPr') else 'pPrDefault/') + path, attr)

    def roles(self, overrides=None):
        overrides = overrides or {}
        roles, used_title = [], False
        explicit_title = any(value == 'title' for value in overrides.values())
        has_kai = any(re.match(r'^[（(][一二三四五六七八九十百]+[）)]', text_of(p).strip()) for p in self.paragraphs)
        date_indices = [i for i, p in enumerate(self.paragraphs) if re.fullmatch(r'\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日', text_of(p).strip())]
        for i, p in enumerate(self.paragraphs):
            t = text_of(p).strip()
            style = (val(p, 'pPr/pStyle', default='') or '').lower()
            outline = self.effective(p, 'pPr/outlineLvl')
            if any(a.tag == tag('tc') for a in p.iterancestors()):
                role = 'table'
            elif any(a.tag == tag('txbxContent') for a in p.iterancestors()):
                role = 'object'
            elif not t:
                role = 'blank'
            elif re.match(r'^附件\s*\d*\s*$', t):
                role = 'attachment'
            elif re.fullmatch(r'\d{4}\s*年\s*\d{1,2}\s*月\s*\d{1,2}\s*日', t):
                role = 'date'
            elif i + 1 in date_indices and len(t) < 45:
                role = 'signature'
            elif style in ('subtitle', '副标题'):
                role = 'subtitle'
            elif style in ('title', '标题') or (not explicit_title and not used_title and len(t) <= 85 and not re.match(r'^(附件[：:]|[一二三四五六七八九十]+、|[（(]|\d+[.．、])', t)):
                role, used_title = 'title', True
            elif re.match(r'^[一二三四五六七八九十百]+、', t):
                role = 'h1'
            elif re.match(r'^[（(][一二三四五六七八九十百]+[）)]', t):
                role = 'h2'
            elif len(t) <= 85 and re.match(r'^\d+[.．、]', t):
                role = 'h3' if has_kai else 'h2'
            elif len(t) <= 85 and re.match(r'^[（(]\d+[）)]', t):
                role = 'h4' if has_kai else 'h3'
            elif outline is not None and str(outline).isdigit() and int(outline) < 4:
                role = 'h' + str(int(outline) + 1)
            elif re.search(r'(heading|标题)\s*[1-4]$', style):
                role = 'h' + style[-1]
            else:
                role = 'body'
            override = overrides.get(str(i))
            if override in LABELS and role not in ('table', 'blank', 'object') and override not in ('table', 'blank', 'object'):
                role = override
                if role == 'title':
                    used_title = True
            roles.append(role)
        return roles

    def restricted(self):
        p = self.settings.find(tag('documentProtection'))
        return p is not None and p.get(tag('enforcement')) in ('1', 'true', 'on')

    def complex_footer(self):
        for name, data in self.parts.items():
            if re.fullmatch(r'word/footer\d+\.xml', name):
                root = xml(data)
                content = ''.join(root.xpath('.//w:t/text()', namespaces=NS))
                if root.xpath('.//w:drawing | .//w:pict | .//w:tbl', namespaces=NS) or re.sub(r'[\d\s—–\-第页共/]', '', content):
                    return True
        return False

    def inspect(self, options=None):
        options = options or {}
        roles = self.roles(options.get('roles'))
        issues = []

        def issue(code, label, actual, expected, location='文档', paragraph=None, auto=True, source='格式规范'):
            issues.append({'id': str(len(issues)), 'code': code, 'label': label, 'actual': str(actual),
                           'expected': str(expected), 'location': location, 'paragraph': paragraph,
                           'auto': auto, 'source': source})

        for n, s in enumerate(self.document.xpath('.//w:sectPr', namespaces=NS)):
            loc = f'第 {n + 1} 节'
            landscape = val(s, 'pgSz', 'orient') == 'landscape'
            expected_size = ('16838', '11906') if landscape else ('11906', '16838')
            if (val(s, 'pgSz', 'w'), val(s, 'pgSz', 'h')) != expected_size:
                issue('paper', '纸张规格', f"{val(s, 'pgSz', 'w', '?')} × {val(s, 'pgSz', 'h', '?')} twip", 'A4' + (' 横向（保留方向）' if landscape else ' 纵向'), loc)
            for key, mm in [('top', 37), ('bottom', 35), ('left', 28), ('right', 26), ('header', 15), ('footer', 25)]:
                v = val(s, 'pgMar', key)
                target = round(mm / 25.4 * 1440)
                if v is None or not v.isdigit() or abs(int(v) - target) > 2:
                    issue('margin', {'top': '上页边距', 'bottom': '下页边距', 'left': '左页边距', 'right': '右页边距', 'header': '页眉距边界', 'footer': '页脚距边界'}[key], f'{round(int(v) / 1440 * 2.54, 2)} cm' if v and v.isdigit() else '未明确设置', f'{mm / 10:g} cm', loc)
            if n == 0 and s.find(tag('titlePg')) is None:
                issue('first-page', '首页页码', '未启用首页不同', '首页不显示页码', loc, auto=not self.complex_footer())
        title_line = int(options.get('titleLine', 35))
        if not 33 <= title_line <= 36:
            raise DocumentError('标题行距须在 33–36 磅之间。')
        preview = []
        for i, (p, role) in enumerate(zip(self.paragraphs, roles)):
            t = text_of(p)
            preview.append({'index': i, 'text': t, 'role': role, 'label': LABELS[role]})
            if role in ('blank', 'table', 'object'):
                continue
            loc = f'第 {i + 1} 段 · {LABELS[role]}'
            font, size = FONTS[role], (44 if role == 'title' else 32)
            runs = [r for r in runs_of(p) if r.find(tag('t')) is not None]
            bad_fonts, bad_sizes, bad_latin = set(), set(), False
            for r in runs:
                rt = text_of(r)
                rf = self.effective(p, 'rPr/rFonts', 'eastAsia', r)
                if not rf:
                    rf = self.effective(p, 'rPr/rFonts', 'ascii', r)
                rs = self.effective(p, 'rPr/sz', run=r)
                if re.search(r'[\u3400-\u9fff]', rt) and normalize_font(rf) != normalize_font(font):
                    bad_fonts.add(rf or '主题字体 / 未明确')
                if rs != str(size):
                    bad_sizes.add(f'{int(rs) / 2:g} pt' if rs and rs.isdigit() else '未明确设置')
                if role.startswith('h') and re.search(r'\d', rt) and self.effective(p, 'rPr/rFonts', 'ascii', r) != 'Times New Roman':
                    bad_latin = True
            if bad_fonts:
                issue('font', '中文字体', '、'.join(sorted(bad_fonts)), font, loc, i)
            if bad_sizes:
                issue('size', '字号', '、'.join(sorted(bad_sizes)), f'{size / 2:g} pt（' + ('二号' if role == 'title' else '三号') + '）', loc, i)
            if bad_latin:
                issue('latin-font', '标题数字字体', '非 Times New Roman', 'Times New Roman', loc, i)
            line = self.effective(p, 'pPr/spacing', 'line')
            rule = self.effective(p, 'pPr/spacing', 'lineRule')
            expected_line = title_line if role == 'title' else 28
            if line != str(expected_line * 20) or rule != 'exact':
                issue('line', '固定行距', f'{line or "继承"} / {rule or "自动"}', f'固定值 {expected_line} pt', loc, i)
            indent = self.effective(p, 'pPr/ind', 'firstLineChars')
            first = self.effective(p, 'pPr/ind', 'firstLine')
            expected_indent = '0' if role in ('title', 'subtitle', 'date', 'signature', 'attachment') else '200'
            if indent != expected_indent and not (expected_indent == '0' and (indent in (None, '0')) and first in (None, '0')):
                issue('indent', '首行缩进', f'{int(indent) / 100:g} 字符' if indent and indent.isdigit() else '非明确字符缩进', '2 字符' if expected_indent == '200' else '0 字符', loc, i)
            if any(self.effective(p, 'pPr/spacing', x) not in (None, '0') for x in ('before', 'after', 'beforeLines', 'afterLines', 'beforeAutospacing', 'afterAutospacing')):
                issue('spacing', '段前段后', '存在段落间距', '均为 0', loc, i)
            align = self.effective(p, 'pPr/jc')
            target_align = 'center' if role in ('title', 'subtitle') else ('right' if role in ('date', 'signature') else None)
            if target_align and align != target_align:
                issue('alignment', '段落对齐', align or '默认', '居中' if target_align == 'center' else '右侧落款区', loc, i)
            if role.startswith('h') and re.search(r'[：:。；;，,、！？!?]$', t.strip()):
                issue('heading-punctuation', '标题末尾标点', t.strip()[-1], '分行标题末尾不加标点，请确认后修改文字', loc, i, False, '格式规范第 1 页 · 四')
            if role == 'date' and re.search(r'年\s*0\d|月\s*0\d', t):
                issue('date', '日期虚位', t, '例如 2026年1月4日；请确认日期后修改文字', loc, i, False, '格式规范第 3 页 · 七')
            if role.startswith('h') and len(t) > 85:
                issue('mixed-heading', '标题与正文可能同行', t[:45] + '…', '请人工确认标题边界', loc, i, False)
            if p.xpath('.//w:numPr', namespaces=NS) or (self.effective(p, 'pPr/numPr/numId') is not None):
                issue('numbering', '自动编号', '包含自动编号', '保留编号定义；请在 Word / WPS 核对层级和序号', loc, i, False)
        if not any(r == 'title' for r in roles):
            issue('title', '主标题识别', '未识别到主标题', '请在段落预览中指定主标题', auto=False)
        footer_ok = self.footer_valid()
        if not footer_ok:
            issue('footer', '页码样式', '未检测到完整规范页码', '居中宋体四号 —PAGE— 动态页码', auto=not self.complex_footer())
        if self.complex_footer():
            issue('complex-footer', '原有页脚内容', '页脚含文字、图片或表格', '保留原页脚，请在 Word / WPS 中人工处理页码', auto=False)
        if self.document.xpath('.//w:ins | .//w:del | .//w:moveFrom | .//w:moveTo', namespaces=NS):
            issue('revisions', '文档修订', '存在未处理的修订', '先在原软件中审阅、接受或拒绝修订，再重新导入', auto=False)
        if self.restricted():
            issue('protected', '限制编辑', '文档启用了编辑保护', '请先在原软件中解除编辑保护', auto=False)
        if any(x.startswith('_xmlsignatures/') for x in self.parts):
            issue('signed', '数字签名', '文档已数字签名', '修改会使签名失效；请使用未签名副本', auto=False)
        if self.document.xpath('.//w:drawing | .//w:pict | .//w:tbl', namespaces=NS):
            issue('objects', '图表与图片', '含图片、表格或浮动对象', '对象及表格格式保留；请核对跨页、文字环绕与打印效果', auto=False)
        if any(r in ('attachment', 'signature', 'date') for r in roles):
            issue('signoff-review', '落款与附件位置', '已检测到落款或附件', '核对落款空行、署名与日期中心、印章及附件另页位置', auto=False, source='格式规范第 2、3 页')
        if options.get('profile') == 'summary':
            valid_name = bool(re.fullmatch(r'.+-工作总结-.+', self.name.rsplit('.', 1)[0]))
            if not valid_name:
                issue('filename', '工作总结文件命名', self.name, '学院名称-工作总结-时间范围.docx', auto=False, source='考核方案 · 考核流程')
        elif not re.fullmatch(r'.+-.+-\d{8}', self.name.rsplit('.', 1)[0]):
            issue('filename', '归档文件命名', self.name, '文档名-处理人-年月日.docx；可在导出时设置', auto=False, source='格式规范第 4 页 · 九')
        auto_count = sum(i['auto'] for i in issues)
        return {'name': self.name, 'paragraphs': preview, 'issues': issues, 'autoCount': auto_count,
                'manualCount': len(issues) - auto_count, 'paragraphCount': sum(bool(x['text']) for x in preview),
                'sectionCount': len(self.document.xpath('.//w:sectPr', namespaces=NS)),
                'imageCount': len([k for k in self.parts if k.startswith('word/media/')]),
                'tableCount': len(self.document.xpath('.//w:tbl', namespaces=NS)),
                'canFix': not self.restricted() and not any(i['code'] in ('revisions', 'signed') for i in issues)}

    def footer_valid(self):
        sections = self.document.xpath('.//w:sectPr', namespaces=NS)
        relmap = {r.get('Id'): r.get('Target') for r in self.rels}
        inherited = None
        for s in sections:
            refs = s.findall(tag('footerReference'))
            for ref in refs:
                if ref.get(tag('type')) == 'default':
                    inherited = relmap.get(ref.get('{' + R + '}id'))
            if not inherited:
                return False
            part = 'word/' + inherited.lstrip('/') if not inherited.startswith('/word/') else inherited[1:]
            if part not in self.parts:
                return False
            f = xml(self.parts[part])
            ps = f.findall(tag('p'))
            if len(ps) != 1 or val(ps[0], 'pPr/jc') != 'center':
                return False
            codes = ''.join(f.xpath('.//w:instrText/text() | .//w:fldSimple/@w:instr', namespaces=NS))
            if not re.search(r'\bPAGE\b', codes) or text_of(f).count('—') < 2:
                return False
            for run in f.xpath('.//w:r[w:t]', namespaces=NS):
                if val(run, 'rPr/sz') != '28' or val(run, 'rPr/rFonts', 'eastAsia') != '宋体':
                    return False
        return bool(sections)

    def repair(self, options=None):
        options = options or {}
        before = self.inspect(options)
        if not before['canFix']:
            raise DocumentError('请先处理编辑保护、数字签名或未完成的修订，再修正格式。')
        before_text = [text_of(p) for p in self.paragraphs]
        roles = self.roles(options.get('roles'))
        for i, (p, role) in enumerate(zip(self.paragraphs, roles)):
            if role in ('blank', 'table', 'object'):
                continue
            pp = p.find(tag('pPr'))
            if pp is None:
                pp = E.Element(tag('pPr'))
                p.insert(0, pp)
            sp = node(pp, 'spacing', before=0, after=0, beforeLines=0, afterLines=0,
                      beforeAutospacing=0, afterAutospacing=0,
                      line=(int(options.get('titleLine', 35)) if role == 'title' else 28) * 20, lineRule='exact')
            ind = node(pp, 'ind', firstLineChars=0 if role in ('title', 'subtitle', 'date', 'signature', 'attachment') else 200,
                       firstLine=0, left=0, right=0)
            for attr in ('hanging', 'hangingChars', 'leftChars', 'rightChars', 'start', 'end', 'startChars', 'endChars'):
                ind.attrib.pop(tag(attr), None)
            if role in ('title', 'subtitle'):
                node(pp, 'jc', val='center')
            elif role in ('date', 'signature'):
                node(pp, 'jc', val='right')
                node(pp, 'ind', rightChars=400, right=0)
            elif role == 'attachment':
                node(pp, 'jc', val='left')
            else:
                # Existing left/justified alignment is kept; stray center/right is corrected.
                if self.effective(p, 'pPr/jc') not in ('left', 'both', 'distribute'):
                    node(pp, 'jc', val='both')
            node(pp, 'snapToGrid', val=0)
            node(pp, 'contextualSpacing', val=0)
            node(pp, 'bidi', val=0)
            if role in ('title', 'subtitle', 'h1', 'h2', 'h3', 'h4'):
                node(pp, 'keepNext', val=1)
                node(pp, 'keepLines', val=1)
            for run in runs_of(p):
                if run.find(tag('t')) is None:
                    continue
                rp = run.find(tag('rPr'))
                if rp is None:
                    rp = E.Element(tag('rPr'))
                    run.insert(0, rp)
                rf = node(rp, 'rFonts', eastAsia=FONTS[role], ascii='Times New Roman', hAnsi='Times New Roman', cs='Times New Roman', hint='eastAsia')
                for a in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
                    rf.attrib.pop(tag(a), None)
                node(rp, 'sz', val=44 if role == 'title' else 32)
                node(rp, 'szCs', val=44 if role == 'title' else 32)
                node(rp, 'spacing', val=0)
                node(rp, 'w', val=100)
                node(rp, 'position', val=0)
                # These are document formatting, never rewrite textual content.
        sections = self.document.xpath('.//w:sectPr', namespaces=NS)
        complex_footer = self.complex_footer()
        for n, s in enumerate(sections):
            landscape = val(s, 'pgSz', 'orient') == 'landscape'
            node(s, 'pgSz', w=16838 if landscape else 11906, h=11906 if landscape else 16838)
            node(s, 'pgMar', **{k: round(v / 25.4 * 1440) for k, v in [('top', 37), ('bottom', 35), ('left', 28), ('right', 26), ('header', 15), ('footer', 25)]})
            node(s, 'textDirection', val='lrTb')
            # Disable document-grid snapping per paragraph; preserve other CJK settings.
            if not complex_footer and n == 0:
                node(s, 'titlePg', val=1)
        if not complex_footer:
            self.add_footers(sections)
        compat = node(self.settings, 'compat')
        for c in list(compat):
            if c.get(tag('name')) == 'compatibilityMode':
                compat.remove(c)
        E.SubElement(compat, tag('compatSetting'), {tag('name'): 'compatibilityMode', tag('uri'): 'http://schemas.microsoft.com/office/word', tag('val'): '15'})
        # PAGE fields refresh with pagination; never request blanket updates to
        # LINK / INCLUDETEXT / DDE fields when a recipient opens the document.
        node(self.settings, 'updateFields', val=0)
        self.ensure_part('word/settings.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml', 'settings')
        if 'word/styles.xml' not in self.parts:
            # Minimal packages must not inherit the recipient's Normal.dotm.
            defaults = E.SubElement(self.styles, tag('docDefaults'))
            rp = E.SubElement(E.SubElement(defaults, tag('rPrDefault')), tag('rPr'))
            node(rp, 'rFonts', eastAsia='仿宋_GB2312', ascii='Times New Roman', hAnsi='Times New Roman')
            node(rp, 'sz', val=32)
            for sid in ('Normal', 'Header', 'Footer'):
                st = E.SubElement(self.styles, tag('style'), {tag('type'): 'paragraph', tag('styleId'): sid})
                if sid == 'Normal':
                    st.set(tag('default'), '1')
                node(st, 'name', val=sid)
                node(E.SubElement(st, tag('pPr')), 'pBdr')
            self.ensure_part('word/styles.xml', 'application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml', 'styles')
            self.parts['word/styles.xml'] = dump(self.styles)
        self.parts['word/settings.xml'] = dump(self.settings)
        order_properties(self.document)
        self.parts['word/document.xml'] = dump(self.document)
        self.parts['word/_rels/document.xml.rels'] = dump(self.rels)
        self.parts['[Content_Types].xml'] = dump(self.types)
        if before_text != [text_of(p) for p in self.paragraphs]:
            raise DocumentError('内容完整性校验失败，已停止导出。')
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
            for name, data in self.parts.items():
                z.writestr(name, data)
        result = stream.getvalue()
        after = Package(result, self.name).inspect(options)
        return result, before, after

    def ensure_part(self, path, content_type, relation):
        if not any(t.get('PartName') == '/' + path for t in self.types):
            E.SubElement(self.types, '{' + CT + '}Override', PartName='/' + path, ContentType=content_type)
        target = path.removeprefix('word/')
        for rel in self.rels:
            if rel.get('Target') == target:
                return rel.get('Id')
        ids = {r.get('Id') for r in self.rels}
        n = 1
        while f'rIdArchive{n}' in ids:
            n += 1
        rid = f'rIdArchive{n}'
        E.SubElement(self.rels, '{' + REL + '}Relationship', Id=rid, Type=R + '/' + relation, Target=target)
        return rid

    def add_footers(self, sections):
        # New part names prevent overwriting a footer part linked by a header or other part.
        n = 1
        while f'word/footerArchive{n}.xml' in self.parts or f'word/footerArchive{n + 1}.xml' in self.parts:
            n += 1
        paths = [f'word/footerArchive{n}.xml', f'word/footerArchive{n + 1}.xml']
        f = E.Element(tag('ftr'), nsmap={'w': W})
        p = E.SubElement(f, tag('p'))
        pp = E.SubElement(p, tag('pPr'))
        node(pp, 'jc', val='center')
        node(pp, 'spacing', before=0, after=0, line=280, lineRule='exact')

        def footer_run(parent, content):
            r = E.SubElement(parent, tag('r'))
            rp = E.SubElement(r, tag('rPr'))
            node(rp, 'rFonts', eastAsia='宋体', ascii='宋体', hAnsi='宋体')
            node(rp, 'sz', val=28)
            E.SubElement(r, tag('t')).text = content

        footer_run(p, '—')
        field = E.SubElement(p, tag('fldSimple'), {tag('instr'): ' PAGE ', tag('dirty'): 'true'})
        footer_run(field, '2')
        footer_run(p, '—')
        self.parts[paths[0]] = dump(f)
        blank = E.Element(tag('ftr'), nsmap={'w': W})
        E.SubElement(blank, tag('p'))
        self.parts[paths[1]] = dump(blank)
        rels = [self.ensure_part(p, 'application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml', 'footer') for p in paths]
        for i, s in enumerate(sections):
            has_title = s.find(tag('titlePg')) is not None
            for old in list(s.findall(tag('footerReference'))):
                s.remove(old)
            refs = [('default', rels[0]), ('even', rels[0])]
            if i == 0 or has_title:
                refs.append(('first', rels[1] if i == 0 else rels[0]))
            for kind, rid in reversed(refs):
                s.insert(0, E.Element(tag('footerReference'), {tag('type'): kind, '{' + R + '}id': rid}))


def make_sample():
    """Small intentionally misformatted fixture, generated without external services."""
    root = E.Element(tag('document'), nsmap={'w': W, 'r': R})
    body = E.SubElement(root, tag('body'))
    lines = ['学生会办公室十月工作总结', '一、工作开展情况',
             '本月，办公室围绕档案归集、会议统筹与部门协作开展工作，持续完善材料收集与审核流程。',
             '1. 档案整理与归集', '完成各部门活动材料的分类整理，核对工作计划、活动记录与总结材料，建立档案目录。',
             '2. 日常事务与协作', '做好例会安排与会议记录，及时跟进各部门材料提交进度。',
             '二、存在问题与下一步计划', '部分材料的字体与页边距不一致。下一阶段将统一档案标准，完善提交前的检查流程。',
             '学院学生会办公室', '2026年11月4日']
    for i, t in enumerate(lines):
        p = E.SubElement(body, tag('p'))
        pp = E.SubElement(p, tag('pPr'))
        node(pp, 'spacing', after=160, line=360, lineRule='auto')
        r = E.SubElement(p, tag('r'))
        rp = E.SubElement(r, tag('rPr'))
        node(rp, 'rFonts', eastAsia='微软雅黑', ascii='Calibri')
        node(rp, 'sz', val=36 if i == 0 else 24)
        E.SubElement(r, tag('t')).text = t
    sect = E.SubElement(body, tag('sectPr'))
    node(sect, 'pgSz', w=11906, h=16838)
    node(sect, 'pgMar', top=1440, bottom=1440, left=1440, right=1440)
    types = f'''<?xml version="1.0" encoding="UTF-8"?><Types xmlns="{CT}"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/></Types>'''
    rels = f'''<Relationships xmlns="{REL}"><Relationship Id="rId1" Type="{R}/officeDocument" Target="word/document.xml"/></Relationships>'''
    out = io.BytesIO()
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', types)
        z.writestr('_rels/.rels', rels)
        z.writestr('word/document.xml', dump(root))
    return out.getvalue()
