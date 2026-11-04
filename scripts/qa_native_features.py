"""Exercise the app's native widgets with synthetic records and templates."""
import json
from pathlib import Path
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QLabel
from app.desktop import MainWindow, SettingsDialog
from app.engine import make_sample
from app.storage import Store
from app.profile_ui import StandardEditor
from app.profiles import default_standard
from app.theme import STYLE


def main():
    root = Path('.build/qa-native-features-v210').resolve()
    root.mkdir(parents=True, exist_ok=True)
    app = QApplication([])
    app.setStyle('Fusion')
    QFontDatabase.addApplicationFont('C:/Windows/Fonts/msyh.ttc')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)
    store = Store(root / 'records')
    if store.jobs:
        store.remove_many(list(store.jobs))
    window = MainWindow(store)
    window.show()
    errors = []
    window.error = errors.append

    def wait():
        deadline = time.monotonic() + 30
        while window.busy and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(.02)
        app.processEvents()
        assert not window.busy, 'worker timeout'
        assert not errors, errors

    for name in ('批量测试甲.docx', '批量测试乙.docx', '保留这份.docx'):
        store.create(name, make_sample())
    window.refresh()
    window.navigate(3)
    window.search.setText('批量测试')
    window.select_all_history()
    assert len(window.selected_history_ids()) == 2
    assert window.history_selected_label.text() == '已选择 2 份'
    window.grab().save(str(root / 'history-multi-select.png'))
    original_question = QMessageBox.question
    QMessageBox.question = lambda *args, **kwargs: QMessageBox.StandardButton.Yes
    try:
        window.remove_history()
        wait()
    finally:
        QMessageBox.question = original_question
    assert [j['name'] for j in store.jobs.values()] == ['保留这份.docx']
    window.search.clear()
    window.clear_history_selection()

    editor = StandardEditor(parent=window)
    editor.name.setText('办公室自定格式')
    editor.fields['body'][0].setText('宋体')
    editor.fields['body'][1].setValue(14)
    editor.fields['body'][2].setValue(25)
    editor.show()
    app.processEvents()
    editor.grab().save(str(root / 'custom-standard-editor.png'))
    editor.save()
    assert editor.result()
    key = window.profiles.save(editor.standard)
    window.refresh_profiles(key)
    assert window.profile.currentData() == key
    old = next(iter(store.jobs.values()))
    settings = SettingsDialog(old['options'], window)
    settings.profile.setCurrentIndex(settings.profile.findData(key))
    assert settings.result_options()['standard']['roles']['body']['size'] == 14
    window.active_id = old['id']
    window.reanalyze(old, settings.result_options())
    wait()
    window.fix_current()
    wait()
    assert window.job()['after']['autoCount'] == 0

    page = window.generation
    window.navigate(4)
    page.templates.setCurrentText('年度工作计划')
    _, tasks = page.fields['comprehensive_work']
    tasks.set_value([dict(description='整理档案', goals=['提高效率'], measures=['统一归档'])])
    assert tasks.value()[0]['description'] == '整理档案'
    page.save_draft()
    page.templates.setCurrentText('月份档案封皮')
    page.templates.setCurrentText('年度工作计划')
    assert page.fields['comprehensive_work'][1].value()[0]['description'] == '整理档案'
    page.tabs.setCurrentIndex(1)
    app.processEvents()
    window.grab().save(str(root / 'generator-tasks.png'))

    page.templates.setCurrentText('月份档案封皮')
    page.fields['college_name'][1].setText('信息工程')
    destination = root / '原生界面生成封皮.docx'
    original_save = QFileDialog.getSaveFileName
    QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(destination), 'Word 文档 (*.docx)')
    try:
        page.generate()
        wait()
    finally:
        QFileDialog.getSaveFileName = original_save
    assert destination.is_file()
    assert page.open_button.isEnabled()
    assert len(store.jobs) == 2
    app.processEvents()
    window.grab().save(str(root / 'generator-cover.png'))
    for entry in window.findChildren(QLabel):
        if entry.objectName() in ('headline', 'section'):
            assert not entry.text().endswith('。'), entry.text()
    window.navigate(0)
    window.grab().save(str(root / 'workspace.png'))
    page.save_draft()
    window.close()
    (root / 'result.json').write_text(json.dumps({'ok': True, 'checks': ['Filtered batch deletion through native controls', 'Custom standard editor and repair', 'Task group editor and draft restore', 'Generator worker, save action and history import', 'Native headings omit full stops']}, indent=2), encoding='utf-8')
    print('Native feature checks passed')


if __name__ == '__main__':
    main()
