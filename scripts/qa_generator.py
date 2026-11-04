"""Exercise all locally supplied templates without publishing the resources."""
import argparse
import json
import logging
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PIL import Image, ImageDraw
from app.generation import GeneratorLibrary
from app.generator.generator_core import default_value
from app.engine import Package, text_of


def main():
    logging.basicConfig(level=logging.ERROR)
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', default='.build/qa-generator-v210')
    args = parser.parse_args()
    root = Path(args.output).resolve()
    root.mkdir(parents=True, exist_ok=True)
    photos = []
    for i, color in enumerate(('#8eae98', '#c9b286', '#98aac3')):
        path = root / f'测试照片{i+1}.jpg'
        picture = Image.new('RGB', (900, 600), color)
        ImageDraw.Draw(picture).text((50, 50), f'ARCHIVE TEST {i+1}', fill='white')
        picture.save(path)
        photos.append(str(path))
    library = GeneratorLibrary(root / 'data')
    catalog = library.catalog()
    results = []
    for name, spec in catalog.items():
        if name.startswith(('外部模板', '自定义模板')):
            continue
        values = {}
        for field in spec.get('fields', []):
            key, kind = field['name'], field.get('type', 'text')
            value = default_value(field)
            if kind == 'photos':
                value = photos[:2]
            elif kind == 'points':
                value = ['围绕学生需求开展服务，完善工作流程。', '汇总活动反馈，落实后续改进。']
            elif kind == 'task_groups':
                value = [dict(description='完善档案工作', goals=['提升整理效率'], measures=['开展培训', '定期检查'])]
            elif kind == 'toc':
                value = '工作内容|2\n重点工作|3'
            elif kind == 'events':
                value = '主题交流|11月4日|活动中心|学生会|指导教师'
            elif kind == 'choice':
                value = field.get('default') or field['choices'][0]
            elif kind == 'number' and not value:
                value = str(max(30, field.get('min', 1)))
            elif not value and field.get('required'):
                value = '信息工程' if key == 'college_name' else ('学生会办公室' if key == 'department_name' else '组织学生参加交流活动，记录反馈并完善后续服务。')
            values[key] = value
        # Generate both a standard document and alternative photo layouts.
        variants = [('标准', {})]
        if spec.get('summary'):
            variants += [('三列照片', dict(photo_paths=photos, photo_layout='横向三列', photo_position='文末', photo_page='紧接正文')),
                         ('单列照片', dict(photo_layout='竖向单列', photo_position='活动过程后'))]
        for suffix, overrides in variants:
            destination = root / (name + '-' + suffix + '.docx')
            result = library.generate(name, {**values, **overrides}, destination, embed=suffix == '三列照片')
            package = Package(destination.read_bytes(), destination.name)
            all_text = ''.join(text_of(p) for p in package.paragraphs)
            assert '{{' not in all_text and '{%' not in all_text, name
            if spec.get('summary'):
                media = [p for p in package.parts if p.startswith('word/media/')]
                assert len(media) >= len(overrides.get('photo_paths', values['photo_paths'])), name
            results.append(dict(name=name, variant=suffix, path=str(destination), warnings=result.warnings,
                                embedded=result.font_report.get('embedded', [])))
    assert len({r['name'] for r in results}) == 7
    (root / 'result.json').write_text(json.dumps({'ok': True, 'generated': results}, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'Validated {len(results)} DOCX outputs across seven template types')


if __name__ == '__main__':
    main()
