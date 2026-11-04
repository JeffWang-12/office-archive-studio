"""Windows integration. Office is optional; DOCX formatting needs no Office."""
from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import subprocess
import sys


# Names and aliases are metadata, independent of privately supplied font files.
FONT_REQUIREMENTS = [
    ('仿宋_GB2312', ['FangSong_GB2312', '仿宋_GB2312'], True),
    ('方正公文楷体', ['FZDocKai', '方正公文楷体'], False),
    ('方正小标宋简体', ['FZXiaoBiaoSong-B05S', 'FZXBSJW--GB1-0', '方正小标宋简体'], True),
    ('楷体_GB2312', ['KaiTi_GB2312', '楷体_GB2312'], True),
    ('黑体', ['SimHei', '黑体'], True),
    ('宋体', ['SimSun', '宋体'], True),
    ('Times New Roman', ['Times New Roman'], True),
]


def font_catalog(font_directory, installed):
    """Detect all required fonts even in a source-only checkout with no TTFs."""
    def key(name):
        return name.lower().replace('_', '').replace(' ', '').replace('-', '')
    haystack = '\n'.join(key(name) for name in installed)
    supplied = []
    for path in sorted(Path(font_directory).glob('*.ttf')):
        metadata = font_metadata(path)
        supplied.append((path, metadata))
    fonts = []
    for name, aliases, required in FONT_REQUIREMENTS:
        matching = next(((path, meta) for path, meta in supplied
                         if any(key(alias) == key(value) for alias in aliases for value in meta['names'])), None)
        fonts.append({'name': name, 'names': aliases, 'required': required,
                      'installed': any(key(alias) in haystack for alias in aliases),
                      'file': matching[0].name if matching else None,
                      'embeddingFlags': matching[1]['embeddingFlags'] if matching else None})
    return fonts


def resource_root():
    return Path(getattr(sys, '_MEIPASS', Path(__file__).resolve().parent.parent))


def font_metadata(path):
    data = Path(path).read_bytes()
    count = struct.unpack_from('>H', data, 4)[0]
    tables = {}
    for i in range(count):
        off = 12 + 16 * i
        name, _, offset, length = struct.unpack_from('>4sIII', data, off)
        tables[name] = (offset, length)
    off = tables[b'name'][0]
    _, count, strings = struct.unpack_from('>HHH', data, off)
    names = []
    for i in range(count):
        platform, encoding, language, name_id, length, offset = struct.unpack_from('>HHHHHH', data, off + 6 + i * 12)
        if name_id not in (1, 4, 6):
            continue
        raw = data[off + strings + offset:off + strings + offset + length]
        try:
            name = raw.decode('utf-16-be' if platform in (0, 3) else 'mac-roman')
            if name not in names:
                names.append(name)
        except UnicodeError:
            pass
    embed = struct.unpack_from('>H', data, tables[b'OS/2'][0] + 8)[0] if b'OS/2' in tables else None
    return {'names': names, 'embeddingFlags': embed}


def environment():
    installed = set()
    office = []
    if os.name == 'nt':
        import winreg
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            try:
                with winreg.OpenKey(hive, r'SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts') as k:
                    n = 0
                    while True:
                        try:
                            name, file, _ = winreg.EnumValue(k, n)
                            installed.add(name.lower())
                            installed.add(str(file).lower())
                            n += 1
                        except OSError:
                            break
            except OSError:
                pass
        for key, label in [('Word.Application', 'Microsoft Word'), ('KWPS.Application', 'WPS 文字')]:
            try:
                with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, key + r'\CLSID'):
                    office.append({'id': key, 'name': label})
            except OSError:
                pass
    font_list = font_catalog(resource_root() / 'assets' / 'fonts', installed)
    return {'os': 'Windows' if os.name == 'nt' else sys.platform, 'office': office,
            'fonts': font_list, 'local': True, 'version': '2.2.0', 'canConvert': bool(office)}


def office_convert(source, output, mode='docx', application=None):
    if os.name != 'nt':
        raise ValueError('旧版文件转换和 PDF 导出需要 Windows 上的 Word 或 WPS。')
    env = environment()
    if not env['office']:
        raise ValueError('未检测到可用的 Word / WPS 自动化组件。请先将文档另存为 DOCX。')
    valid = [x['id'] for x in env['office']]
    app = application if application in valid else valid[0]
    powershell = Path(os.environ.get('SystemRoot', r'C:\Windows')) / 'System32' / 'WindowsPowerShell' / 'v1.0' / 'powershell.exe'
    request = json.dumps({'source': str(Path(source).resolve()), 'output': str(Path(output).resolve()),
                          'mode': mode, 'application': app}, ensure_ascii=False)
    result = subprocess.run([str(powershell), '-NoProfile', '-NonInteractive', '-ExecutionPolicy', 'Bypass',
                             '-File', str(resource_root() / 'scripts' / 'office.ps1')],
                            input=request, encoding='utf-8', capture_output=True, timeout=120,
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
    try:
        data = json.loads(result.stdout.strip().lstrip('\ufeff'))
    except (ValueError, TypeError):
        raise ValueError('Office 转换未完成。请关闭文件的密码或修复提示，在原软件中重新另存后再试。')
    if not data.get('ok') or not Path(output).is_file():
        raise ValueError('Office 转换失败：' + data.get('error', '未生成文件'))
    return data
