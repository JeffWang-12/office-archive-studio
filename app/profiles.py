"""Validated, portable formatting standards; jobs keep their own immutable snapshot."""
from copy import deepcopy
import json
import math
from pathlib import Path
import uuid

ROLE_NAMES = {'title': '主标题', 'subtitle': '副标题 / 单位', 'h1': '一级标题',
              'h2': '二级标题', 'h3': '三级标题', 'h4': '四级标题', 'body': '正文',
              'date': '成文日期', 'signature': '署名', 'attachment': '附件标识'}
BASE_FONTS = dict(zip(ROLE_NAMES, ['方正小标宋简体', '楷体_GB2312', '黑体', '楷体_GB2312',
                                '仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312', '仿宋_GB2312',
                                '仿宋_GB2312', '黑体']))
BUILTINS = {'general': '团内文件 · 通用规范', 'summary': '学院工作总结 · 考核规范'}


def default_standard():
    return {'name': '我的格式规范', 'paper': 'A4',
            'margins': dict(top=37, bottom=35, left=28, right=26, header=15, footer=25),
            'roles': {k: {'font': BASE_FONTS[k], 'size': 22 if k == 'title' else 16,
                          'line': 35 if k == 'title' else 28,
                          'indent': 0 if k in ('title', 'subtitle', 'date', 'signature', 'attachment') else 2,
                          'align': 'center' if k in ('title', 'subtitle') else ('right' if k in ('date', 'signature') else 'both')}
                      for k in ROLE_NAMES}}


def number(value, low, high, label, step=1):
    if isinstance(value, bool):
        raise ValueError(label + '须为有效数值')
    try:
        v = float(value)
    except (ValueError, TypeError) as exc:
        raise ValueError(label + '须为有效数值') from exc
    if not math.isfinite(v) or not low <= v <= high or abs(v / step - round(v / step)) > 0.00001:
        raise ValueError(f'{label}须在 {low}–{high} 之间，步长 {step}')
    return int(v) if v.is_integer() else v


def validate_standard(raw):
    if not isinstance(raw, dict):
        raise ValueError('格式规范必须为 JSON 对象')
    base = default_standard()
    name = str(raw.get('name', '')).strip()
    if not name or len(name) > 50:
        raise ValueError('请填写 1–50 字的规范名称')
    base['name'] = name
    base['paper'] = raw.get('paper', 'A4')
    if base['paper'] not in ('A4', 'A5', 'Letter'):
        raise ValueError('纸张支持 A4、A5 或 Letter')
    margins = raw.get('margins', {})
    if not isinstance(margins, dict) or not isinstance(raw.get('roles', {}), dict):
        raise ValueError('页边距和段落类型必须为 JSON 对象')
    for k in base['margins']:
        base['margins'][k] = number(margins.get(k, base['margins'][k]), 0, 80, '页边距', .1)
    width, height = {'A4': (210, 297), 'A5': (148, 210), 'Letter': (215.9, 279.4)}[base['paper']]
    if base['margins']['left'] + base['margins']['right'] >= width - 30 or base['margins']['top'] + base['margins']['bottom'] >= height - 30:
        raise ValueError('页边距过大，请至少保留 30 mm 的正文区域')
    for k, target in base['roles'].items():
        row = raw.get('roles', {}).get(k, {})
        if not isinstance(row, dict):
            raise ValueError('段落格式必须为 JSON 对象')
        font = str(row.get('font', target['font'])).strip()
        if not font or len(font) > 100 or any(ord(c) < 32 for c in font):
            raise ValueError(ROLE_NAMES[k] + '字体名称无效')
        target.update(font=font, size=number(row.get('size', target['size']), 5, 96, '字号', .5),
                      line=number(row.get('line', target['line']), 5, 200, '固定行距', .5),
                      indent=number(row.get('indent', target['indent']), 0, 10, '首行缩进', .5),
                      align=row.get('align', target['align']))
        if target['align'] not in ('left', 'center', 'right', 'both'):
            raise ValueError('不支持的对齐方式')
    return base


def standard_for(options):
    if options.get('standard'):
        return validate_standard(options['standard'])
    base = default_standard()
    line = number(options.get('titleLine', 35), 33, 36, '标题行距')
    base['roles']['title']['line'] = line
    base['name'] = BUILTINS.get(options.get('profile'), BUILTINS['general'])
    return base


def paper_twips(standard):
    return {'A4': (11906, 16838), 'A5': (8391, 11906), 'Letter': (12240, 15840)}[standard['paper']]


class ProfileStore:
    def __init__(self, folder):
        self.path = Path(folder) / 'standards.json'
        self.profiles = {}
        self.warning = ''
        if self.path.is_file():
            try:
                raw = json.loads(self.path.read_text(encoding='utf-8-sig'))
                if not isinstance(raw, dict):
                    raise ValueError('规范库格式不正确')
                for key, value in raw.items():
                    self.profiles[key] = validate_standard(value)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                self.warning = '部分自定义规范未能读取：' + str(exc)

    def save(self, standard, key=None):
        standard = validate_standard(standard)
        key = key or 'custom-' + uuid.uuid4().hex
        updated = {**self.profiles, key: standard}
        self._write(updated)
        return key

    def remove(self, key):
        updated = dict(self.profiles)
        del updated[key]
        self._write(updated)

    def _write(self, values):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix('.tmp')
        temp.write_text(json.dumps(values, ensure_ascii=False, indent=2), encoding='utf-8')
        temp.replace(self.path)
        self.profiles = values

    def choices(self):
        return {**BUILTINS, **{k: v['name'] for k, v in self.profiles.items()}}

    def options(self, key, title_line=35):
        if key in self.profiles:
            return {'profile': key, 'standard': deepcopy(self.profiles[key])}
        return {'profile': key if key in BUILTINS else 'general', 'titleLine': title_line}
