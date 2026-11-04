"""Local resource library, draft persistence and native generator service."""
from copy import deepcopy
import json
from pathlib import Path
import shutil
import uuid

from .engine import Package, DocumentError
from .generator.generator_core import load_template_catalog, load_config, generate_document, AUTO_FONT
from .generator.template_guard import restore_standard_templates, version_is_outdated
from .platform import resource_root


class GeneratorLibrary:
    def __init__(self, data_root):
        self.root = Path(data_root) / 'generator'
        self.root.mkdir(parents=True, exist_ok=True)
        self.draft_path = self.root / 'drafts.json'
        self.drafts = {}
        self.auto_save = True
        self.draft_warning = ''
        if not (self.root / '.initialized').exists():
            bundled = resource_root() / 'assets/generator'
            if (bundled / 'templates').is_dir():
                self.import_resources(bundled)
            (self.root / '.initialized').write_text('1', encoding='utf-8')
        for path in (self.draft_path, self.draft_path.with_suffix('.bak')):
            if not path.is_file():
                continue
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if not isinstance(data.get('drafts'), dict):
                    raise ValueError('草稿格式错误')
                self.drafts = data['drafts']
                self.auto_save = bool(data.get('autoSave', True))
                if path != self.draft_path:
                    self.draft_warning = '草稿文件损坏，已从备份恢复'
                break
            except (OSError, ValueError, AttributeError):
                self.draft_warning = '草稿文件无法读取，原文件已保留'

    def import_resources(self, source):
        source = Path(source).resolve()
        if not (source / 'templates').is_dir():
            nested = source / '试用版V3'
            if (nested / 'templates').is_dir():
                source = nested
            else:
                raise DocumentError('请选择包含 templates 文件夹的模板资源目录')
        # Copy only resources. Never run imported Python/EXE or import personal drafts.
        for folder, extensions in [('templates', {'.docx'}), ('默认模板', {'.docx'}), ('fonts', {'.ttf', '.otf'})]:
            target = self.root / folder
            target.mkdir(exist_ok=True)
            for path in (source / folder).glob('*'):
                if path.is_file() and path.suffix.lower() in extensions:
                    if path.suffix.lower() == '.docx':
                        Package(path.read_bytes(), path.name)
                    if path.stat().st_size > 30 * 1024 * 1024:
                        raise DocumentError('资源文件过大：' + path.name)
                    dest = target / path.name
                    if not dest.exists():
                        shutil.copyfile(path, dest)
        for name in ('templates.json', '模板.docx'):
            path = source / name
            if path.is_file() and not (self.root / name).exists():
                if name.endswith('.json'):
                    self._validate_manifest(json.loads(path.read_text(encoding='utf-8-sig')))
                else:
                    Package(path.read_bytes(), path.name)
                shutil.copyfile(path, self.root / name)

    @staticmethod
    def _validate_manifest(raw):
        if not isinstance(raw, dict) or len(raw) > 100:
            raise DocumentError('模板清单格式无效')
        for name, spec in raw.items():
            filename = str(spec.get('file', ''))
            if not filename or Path(filename).name != filename or '/' in filename or '\\' in filename or not filename.lower().endswith('.docx'):
                raise DocumentError('模板清单包含无效文件名')
            if not isinstance(spec.get('fields', []), list) or len(spec.get('fields', [])) > 100:
                raise DocumentError('模板字段数量无效')

    def catalog(self):
        manifest = self.root / 'templates.json'
        if manifest.exists():
            self._validate_manifest(json.loads(manifest.read_text(encoding='utf-8-sig')))
        return load_template_catalog(self.root)

    def add_template(self, path):
        path = Path(path)
        Package(path.read_bytes(), path.name)
        folder = self.root / 'templates'
        folder.mkdir(exist_ok=True)
        target = folder / path.name
        if target.exists():
            target = folder / (path.stem + '-' + uuid.uuid4().hex[:6] + '.docx')
        shutil.copyfile(path, target)
        return target

    def restore(self):
        return restore_standard_templates(self.root)

    def save_draft(self, name, values):
        if self.auto_save:
            self.drafts[name] = deepcopy(values)
            self.persist()

    def persist(self):
        payload = json.dumps({'autoSave': self.auto_save, 'drafts': self.drafts}, ensure_ascii=False, indent=2)
        json.loads(payload)
        temp = self.draft_path.with_suffix('.tmp')
        temp.write_text(payload, encoding='utf-8')
        if self.draft_path.is_file():
            try:
                json.loads(self.draft_path.read_text(encoding='utf-8'))
                shutil.copyfile(self.draft_path, self.draft_path.with_suffix('.bak'))
            except (OSError, ValueError):
                pass
        temp.replace(self.draft_path)

    def generate(self, name, values, destination, embed=False):
        spec = self.catalog().get(name)
        if not spec:
            raise DocumentError('模板不存在，请刷新模板库')
        destination = Path(destination).resolve()
        inputs = {Path(spec['path']).resolve(), *[Path(p).resolve() for p in values.get('photo_paths', [])]}
        if destination in inputs or destination.is_relative_to(self.root.resolve()):
            raise DocumentError('请选择模板库以外的保存位置，不能覆盖模板或照片')
        config = load_config(self.root)
        config['general']['embed_fonts'] = 'true' if embed else 'false'
        result = generate_document(self.root, spec, deepcopy(values), AUTO_FONT, config)
        temporary = destination.with_name('.' + destination.name + '.' + uuid.uuid4().hex + '.tmp')
        try:
            # Validate the package before publishing the requested output.
            Package(result.output_path.read_bytes(), destination.name)
            shutil.copyfile(result.output_path, temporary)
            temporary.replace(destination)
        finally:
            temporary.unlink(missing_ok=True)
            result.output_path.unlink(missing_ok=True)
        result.output_path = destination
        if version_is_outdated():
            result.warnings.append('当前模板适用于 2026–2027 学年，请核对是否有新版规范')
        return result
