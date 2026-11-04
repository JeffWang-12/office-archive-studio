"""Render generated fixtures through installed Word or WPS for visual review."""
from pathlib import Path
import json
import sys
from pypdf import PdfReader

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.platform import office_convert

root = Path(sys.argv[1] if len(sys.argv) > 1 else '.build/qa-generator-v210').resolve()
results = []
for source in sorted(root.glob('*.docx')):
    output = source.with_suffix('.pdf')
    conversion = office_convert(source, output, 'pdf', 'Word.Application')
    reader = PdfReader(output)
    text = '\n'.join(page.extract_text() or '' for page in reader.pages)
    assert len(reader.pages) > 0 and text.strip(), source.name
    results.append(dict(name=source.name, pages=len(reader.pages), conversion=conversion))
    print(source.name, len(reader.pages), 'pages', flush=True)
(root / 'office-result.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
