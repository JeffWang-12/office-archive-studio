"""Optional real Office integration checks; run on an interactive Windows account."""
from pathlib import Path
import json
import sys
import argparse

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.engine import Package, make_sample
from app.platform import office_convert

parser = argparse.ArgumentParser(description='Optional local Word/WPS integration checks')
parser.add_argument('--templates', type=Path, help='Directory containing your own DOC templates')
parser.add_argument('--output', type=Path, default=Path('.build/office-qa'))
args = parser.parse_args()
out = args.output.resolve()
out.mkdir(parents=True, exist_ok=True)
data, before, after = Package(make_sample(), '示例.docx').repair()
(out / 'sample-fixed.docx').write_bytes(data)
pdf = office_convert(out / 'sample-fixed.docx', out / 'sample-fixed.pdf', 'pdf')
results = [{'case': 'sample PDF', 'result': pdf, 'before': before['autoCount'], 'after': after['autoCount']}]
source = args.templates
for name in (['年度工作总结正文模板.doc', '月份工作总结正文模板.doc'] if source else []):
    target = out / (Path(name).stem + '.docx')
    conversion = office_convert(source / name, target, 'docx')
    p = Package(target.read_bytes(), target.name)
    data, b, a = p.repair()
    corrected = out / (target.stem + '-已规范.docx')
    corrected.write_bytes(data)
    pdf = office_convert(corrected, corrected.with_suffix('.pdf'), 'pdf')
    results.append({'case': name, 'conversion': conversion, 'pdf': pdf, 'paragraphs': b['paragraphCount'], 'before': b['autoCount'], 'after': a['autoCount']})
(out / 'results.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
print(json.dumps(results, ensure_ascii=False, indent=2))
