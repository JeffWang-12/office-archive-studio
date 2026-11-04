"""Native UI parity checks against all locally configured generator schemas."""
from datetime import date
import json
import logging
from pathlib import Path
import sys
import time
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt, QPoint
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox
from app.desktop import MainWindow
from app.storage import Store
from app.theme import STYLE
from app.generation import GeneratorLibrary
from app.generator_fields import PointsEditor, TaskGroups, NumberEntry, DateEntry
from app.engine import Package
from app.generator.generator_core import default_value
from PIL import Image


def main():
    logging.basicConfig(level=logging.ERROR)
    root = Path('.build/qa-generator-parity-v220').resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)
    window = MainWindow(Store(root / 'records'))
    window.show()
    window.navigate(4)
    page = window.generation
    failures = []
    window.error = failures.append
    checks = []

    def settle():
        for _ in range(5):
            app.processEvents()

    def wait():
        deadline = time.monotonic() + 40
        while window.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        settle()
        assert not window.busy and not failures, failures

    assert page.templates.count() >= 8
    for name, spec in page.catalog.items():
        page.templates.setCurrentText(name)
        settle()
        assert list(page.fields) == [field['name'] for field in spec.get('fields', [])], name
        assert page.form.rowCount() == len(spec.get('fields', [])), name
        for key, (kind, widget) in page.fields.items():
            assert widget.isVisible(), (name, key)
            if kind == 'points':
                assert isinstance(widget, PointsEditor)
            if kind == 'task_groups':
                assert isinstance(widget, TaskGroups)
            assert widget.height() >= widget.minimumSizeHint().height(), (name, key, 'clipped')
    checks.append('All fields of seven standard types and the root custom template share one complete scrolling form')

    page.templates.setCurrentText('年度工作计划')
    points = page.fields['overall_idea'][1]
    points.set_value(['第一项'])
    points.add_button.click()
    points.entries[1][2].setPlainText('第二项\n同一条的补充')
    assert len(points.value()) == 2 and '\n' in points.value()[1]
    points.remove(points.entries[0][0])
    assert points.entries[0][1].text() == '第 1 条'
    tasks = page.fields['comprehensive_work'][1]
    tasks.set_value([dict(description='任务内容', goals=['目标甲'], measures=['措施甲'])])
    tasks.groups[0][3].add_button.click()
    tasks.groups[0][3].entries[1][2].setPlainText('目标乙')
    tasks.groups[0][4].add_button.click()
    tasks.groups[0][4].entries[1][2].setPlainText('措施乙')
    assert tasks.value()[0]['goals'] == ['目标甲', '目标乙']
    assert tasks.value()[0]['measures'] == ['措施甲', '措施乙']
    tasks.add_button.click()
    assert len(tasks.groups) == 2
    tasks.remove(tasks.groups[1][0])
    settle()
    page.scroll.verticalScrollBar().setValue(tasks.mapTo(page.form_content, QPoint(0, 0)).y() - 12)
    settle()
    window.grab().save(str(root / 'plan-points-and-tasks.png'))
    checks.append('Independent point, task, goal and measure add/remove controls preserve their own values')

    entry = page.fields['year'][1]
    assert isinstance(entry, NumberEntry)
    entry.clear()
    QTest.keyClicks(entry, 'a20b26')
    assert entry.text() == '2026'
    amount = NumberEntry('', True)
    QTest.keyClicks(amount, '1234567')
    amount.format_amount()
    assert amount.text() == '1,234,567'
    date_entry = page.fields['date'][1]
    assert isinstance(date_entry, DateEntry)
    date_entry.set_value('2000-01-01')
    date_entry.today_button.click()
    assert date_entry.value() == date.today().isoformat()
    checks.append('Numeric input filtering, amount separators and Today action work through native controls')

    page.save_draft()
    with patch.object(QMessageBox, 'question', return_value=QMessageBox.StandardButton.Yes):
        page.autosave.setChecked(False)
    assert not page.library.draft_path.exists()
    points.set_value(['不保存到磁盘的内容'])
    page.templates.setCurrentText('月份档案封皮')
    page.templates.setCurrentText('年度工作计划')
    assert page.fields['overall_idea'][1].value() == ['不保存到磁盘的内容']
    assert not page.library.draft_path.exists()
    page.autosave.setChecked(True)
    page.save_draft()
    assert page.library.draft_path.is_file()
    checks.append('Disabling saved drafts removes disk copies while switching templates retains the current session')

    page.templates.setCurrentText('月份档案封皮')
    page.fields['college_name'][1].setText('信息工程')
    page.fields['project_name'][1].setText('一键生成测试')
    page.library.remember(outputDirectory=str(root / 'output'))
    page.output_path.setText(str(page.library.output_directory))
    with patch.object(QFileDialog, 'getSaveFileName', side_effect=AssertionError('One-click generation must not show a save dialog')):
        page.generate_button.click()
        wait()
    output = page.last_output
    assert output.is_file() and output.parent == root / 'output'
    assert '一键生成测试' in output.name
    Package(output.read_bytes(), output.name)
    assert len(page.success_dialog.checklist) == 6
    page.success_dialog.grab().save(str(root / 'generated-review-dialog.png'))
    page.success_dialog.close()
    page.generate_button.click()
    wait()
    assert page.last_output != output and output.is_file()
    page.success_dialog.close()
    checks.append('One-click generation uses a unique timestamp/project filename and shows the complete review checklist')

    photos = []
    for index, color in enumerate(('#8caf96', '#c8b085')):
        path = root / f'photo-{index + 1}.jpg'
        Image.new('RGB', (900, 600), color).save(path)
        photos.append(str(path))
    generated = []
    for name, spec in page.catalog.items():
        if name.startswith(('自定义模板', '外部模板')):
            continue
        page.templates.setCurrentText(name)
        for field in spec['fields']:
            key, kind = field['name'], field.get('type', 'text')
            widget = page.fields[key][1]
            value = default_value(field)
            if kind == 'points':
                widget.set_value(['开展服务，收集反馈并完善工作。', '落实档案整理，提高协作效率。'])
            elif kind == 'task_groups':
                widget.set_value([dict(description='完成档案工作', goals=['统一材料格式', '提升整理效率'], measures=['组织培训', '定期核对'])])
            elif kind == 'photos':
                widget.set_value(photos)
            elif kind in ('toc', 'events'):
                widget.set_value('工作安排|2' if kind == 'toc' else '主题交流|11月4日|活动中心|学生会|指导教师')
            elif kind == 'choice':
                widget.setCurrentText(value or field['choices'][0])
            elif kind == 'date':
                widget.set_value(value)
            elif kind == 'number':
                widget.setText(value or str(max(30, field.get('min', 1))))
            else:
                value = value or ('信息工程' if key == 'college_name' else ('学生会办公室' if key == 'department_name' else ('组织交流活动，记录结果并落实改进。' if field.get('required') else '')))
                if hasattr(widget, 'setPlainText'):
                    widget.setPlainText(value)
                else:
                    widget.setText(value)
        page.generate_button.click()
        wait()
        assert page.last_output.is_file()
        package = Package(page.last_output.read_bytes(), page.last_output.name)
        assert not any('{{' in p['text'] for p in package.inspect()['paragraphs'])
        generated.append({'name': name, 'path': str(page.last_output)})
        page.success_dialog.close()
    assert len(generated) == 7
    checks.append('Seven document types generate valid DOCX files from the actual native form collectors')

    page.templates.setCurrentText('年度档案封皮')
    page.fields['college_name'][1].setText('信息工程')
    for width, height in [(1320, 880), (1050, 710)]:
        window.resize(width, height)
        settle()
        point = page.generate_button.mapTo(page, page.generate_button.rect().topLeft())
        assert point.x() >= 0 and point.x() + page.generate_button.width() <= page.width(), 'footer clipped'
        window.grab().save(str(root / f'complete-form-{width}.png'))
    page.save_draft()
    restored = GeneratorLibrary(window.store.root)
    assert restored.preferences['defaultTemplate'] == '年度档案封皮'
    assert restored.drafts['年度档案封皮']['college_name'] == '信息工程'
    checks.append('Last document type, output location and drafts persist; footer fits regular and minimum window sizes')
    window.close()
    (root / 'result.json').write_text(json.dumps({'ok': True, 'checks': checks, 'generated': generated}, ensure_ascii=False, indent=2), encoding='utf-8')
    print('Generator UI parity checks passed:', len(checks))


if __name__ == '__main__':
    main()
