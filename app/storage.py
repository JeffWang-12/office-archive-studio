"""Local document records shared by native desktop widgets and background workers."""
from __future__ import annotations

from datetime import datetime
import io
import json
import os
from pathlib import Path
import shutil
import threading
import uuid
import zipfile

from .engine import Package, DocumentError
from .platform import office_convert

MAX_UPLOAD = 25 * 1024 * 1024
OFFICE_LOCK = threading.Lock()


def safe_name(name):
    value = name.replace('\\', '/').split('/')[-1]
    value = ''.join(c for c in value if ord(c) >= 32 and c not in '<>:"/\\|?*').strip(' .')[:180]
    return value or '未命名.docx'


class Store:
    def __init__(self, root):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs = {}
        path = self.root / 'history.json'
        if path.exists():
            try:
                for job in json.loads(path.read_text(encoding='utf-8')):
                    if isinstance(job.get('id'), str) and len(job['id']) == 32 and all(c in '0123456789abcdef' for c in job['id']) and (self.root / job['id'] / 'original.docx').is_file():
                        self.jobs[job['id']] = job
            except (ValueError, KeyError, OSError):
                pass

    def save(self):
        with self.lock:
            path = self.root / 'history.tmp'
            path.write_text(json.dumps(list(self.jobs.values()), ensure_ascii=False), encoding='utf-8')
            path.replace(self.root / 'history.json')

    def folder(self, key):
        if key not in self.jobs:
            raise DocumentError('此记录不存在或已删除，请重新导入。')
        return self.root / key

    def create(self, name, data, options=None, demo=False):
        options = options or {}
        if len(data) > MAX_UPLOAD:
            raise DocumentError('单个文件不能超过 25 MB。')
        name = safe_name(name)
        key = uuid.uuid4().hex
        folder = self.root / key
        folder.mkdir()
        original_suffix = Path(name).suffix.lower()
        converted_with = None
        try:
            if original_suffix in ('.doc', '.wps'):
                source = folder / ('source' + original_suffix)
                source.write_bytes(data)
                with OFFICE_LOCK:
                    result = office_convert(source, folder / 'original.docx')
                data = (folder / 'original.docx').read_bytes()
                converted_with = result['application']
                name = Path(name).stem + '.docx'
            elif original_suffix != '.docx':
                raise DocumentError('请选择 DOCX、DOC 或 WPS 文字文件。PDF 和 Excel 暂不支持格式纠正。')
            report = Package(data, name).inspect(options)
            (folder / 'original.docx').write_bytes(data)
            job = {'id': key, 'name': name, 'created': datetime.now().astimezone().isoformat(timespec='seconds'),
                   'size': len(data), 'status': 'checked', 'demo': demo, 'options': options,
                   'report': report, 'convertedWith': converted_with, 'fixedAt': None}
            with self.lock:
                self.jobs[key] = job
                self.save()
            return job
        except Exception:
            shutil.rmtree(folder, ignore_errors=True)
            raise

    def analyze(self, key, options):
        with self.lock:
            job = self.jobs[key]
            folder = self.folder(key)
            # Reanalysis uses the immutable imported source and invalidates stale exports.
            report = Package((folder / 'original.docx').read_bytes(), job['name']).inspect(options)
            job.update(options=options, report=report, status='checked', fixedAt=None)
            job.pop('after', None)
            for name in ('corrected.docx', 'corrected.pdf'):
                (folder / name).unlink(missing_ok=True)
            self.save()
            return job

    def fix(self, key):
        with self.lock:
            job = self.jobs[key]
            folder = self.folder(key)
            data, before, after = Package((folder / 'original.docx').read_bytes(), job['name']).repair(job['options'])
            (folder / 'corrected.docx').write_bytes(data)
            (folder / 'corrected.pdf').unlink(missing_ok=True)
            job.update(status='fixed', report=before, after=after,
                       fixedAt=datetime.now().astimezone().isoformat(timespec='seconds'))
            self.save()
            return job

    def report(self, key):
        job = self.jobs[key]
        lines = ['归档 · 格式检查与修正记录', '=' * 38, f"文件：{job['name']}", f"检查时间：{job['created']}",
                 '依据：共青团文件格式规范（2025年12月17日）；学院学生会工作档案考核方案',
                 '本报告仅覆盖格式检查，不是正式考核得分。内容真实性、完整性、逻辑、创新及印章需人工审阅。',
                 '段落预览为结构预览，不代表 Word / WPS 的最终分页。', '']
        if job.get('convertedWith'):
            lines.append('旧版文件已通过 ' + job['convertedWith'] + ' 转换；请核对转换后的图表与分页。')
        if job['status'] == 'fixed':
            lines += [f"修正时间：{job['fixedAt']}", f"修正前可自动处理：{job['report']['autoCount']} 处", f"复检剩余可自动问题：{job['after']['autoCount']} 处", '原文件保留；文字内容完整性已逐段核对。', '']
        for issue in job['report']['issues']:
            state = '格式修正' if issue['auto'] else '人工核对'
            lines += [f"[{state}] {issue['location']} / {issue['label']}", f"  检测：{issue['actual']}", f"  要求：{issue['expected']}"]
        lines += ['', '修正后仍需核对：'] if job['status'] == 'fixed' else []
        for issue in job.get('after', {}).get('issues', []):
            lines.append(f"- {issue['location']} / {issue['label']}：{issue['expected']}")
        return '\n'.join(lines).encode('utf-8-sig')

    def import_file(self, path, options=None):
        source = Path(path).resolve()
        if source.stat().st_size > MAX_UPLOAD:
            raise DocumentError('单个文件不能超过 25 MB。')
        job = self.create(source.name, source.read_bytes(), options)
        job['sourcePath'] = str(source)
        self.save()
        return job

    def export_file(self, key, destination, kind='docx'):
        folder = self.folder(key)
        target = Path(destination).resolve()
        job = self.jobs[key]
        if job.get('sourcePath') and target == Path(job['sourcePath']).resolve():
            raise DocumentError('请选择新的导出文件名，不能覆盖导入的原始文件。')
        if target.is_relative_to(self.root.resolve()):
            raise DocumentError('请将文件导出到应用记录目录以外的位置。')
        if kind == 'report':
            data = self.report(key)
        elif kind in ('docx', 'pdf'):
            source = folder / ('corrected.' + kind)
            if not source.is_file():
                raise DocumentError('请先完成格式修正；PDF 还需生成打印版。')
            data = source.read_bytes()
        else:
            raise DocumentError('不支持的导出格式。')
        target.write_bytes(data)
        return str(target)

    def export_bundle(self, keys, destination):
        if not keys:
            raise DocumentError('请选择至少一份已修正文件。')
        stream = io.BytesIO()
        used = set()
        with zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
            for key in keys:
                folder = self.folder(key)
                if not (folder / 'corrected.docx').is_file():
                    raise DocumentError('请先修正所选文件。')
                stem = safe_name(Path(self.jobs[key]['name']).stem + '-已规范')
                name, n = stem, 2
                while name in used:
                    name, n = f'{stem}-{n}', n + 1
                used.add(name)
                z.writestr(name + '.docx', (folder / 'corrected.docx').read_bytes())
                z.writestr(name + '-检查报告.txt', self.report(key))
        target = Path(destination).resolve()
        if target.is_relative_to(self.root.resolve()):
            raise DocumentError('请选择应用记录目录以外的导出位置。')
        for job in self.jobs.values():
            if job.get('sourcePath') and target == Path(job['sourcePath']).resolve():
                raise DocumentError('不能覆盖导入的原始文件。')
        target.write_bytes(stream.getvalue())
        return str(target)

    def generate_pdf(self, key, application=None):
        folder = self.folder(key)
        if not (folder / 'corrected.docx').is_file():
            raise DocumentError('请先修正格式，再生成 PDF 打印版。')
        with OFFICE_LOCK:
            result = office_convert(folder / 'corrected.docx', folder / 'corrected.pdf', 'pdf', application)
        return result

    def remove(self, key):
        with self.lock:
            folder = self.folder(key)
            del self.jobs[key]
            self.save()
            shutil.rmtree(folder)
