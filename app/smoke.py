"""Deterministic smoke test of the application's own native widgets.

Runs inside the Qt event loop, including worker signals and native rendering.
No browser automation or desktop input injection is involved.
"""
import json
from pathlib import Path
import sys
import traceback

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication, QComboBox, QFileDialog

from .desktop import ParagraphDialog
from .engine import Package


def run_smoke_test(window, result_path):
    result_path = result_path.resolve()
    result_path.parent.mkdir(parents=True, exist_ok=True)
    state = {'checks': [], 'version': QApplication.applicationVersion(), 'native': True}
    before_count = len(window.store.jobs)

    def finish(error=None):
        if error:
            state['error'] = str(error)
        state['ok'] = error is None
        result_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
        QApplication.exit(1 if error else 0)

    def guard(fn):
        def wrapped():
            try:
                fn()
            except Exception:
                finish(traceback.format_exc())
        return wrapped

    def after_task(fn, tries=0):
        if tries > 400:
            finish('Native worker timed out')
        elif window.busy:
            QTimer.singleShot(50, lambda: after_task(fn, tries + 1))
        else:
            guard(fn)()

    window.error = lambda message: finish(message)
    state['checks'].append('QMainWindow with Qt Widgets')
    assert 'http.server' not in sys.modules
    assert not any('QtWebEngine' in name for name in sys.modules)
    state['checks'].append('No HTTP server or QtWebEngine loaded')

    def imported():
        assert len(window.store.jobs) == before_count + 1
        job = window.job()
        assert job['report']['autoCount'] > 0
        assert window.queue.rowCount() == before_count + 1
        state['before'] = job['report']['autoCount']
        state['checks'].append('Native demo import and background worker signal')
        dialog = ParagraphDialog(job, window)
        dialog.show()
        QApplication.processEvents()
        # Select through the actual combo-box signal and verify the state used
        # by the save operation, rather than mirroring the implementation.
        combo = dialog.rows.cellWidget(3, 1)
        assert isinstance(combo, QComboBox)
        combo.setCurrentIndex(combo.findData('h3'))
        assert dialog.roles['3'] == 'h3'
        assert '学生会办公室' in dialog.paper.toPlainText()
        dialog.grab().save(str(result_path.parent / 'native-paragraphs.png'))
        roles = dict(dialog.roles)
        dialog.close()
        state['checks'].append('Native paragraph role change and QTextDocument preview')
        window.reanalyze(job, {**job['options'], 'roles': roles})
        after_task(checked)

    def checked():
        assert window.job()['options']['roles']['3'] == 'h3'
        window.fix_current()
        after_task(fixed)

    def fixed():
        job = window.job()
        assert job['status'] == 'fixed'
        assert job['after']['autoCount'] == 0
        state['after'] = 0
        state['checks'].append('Native reanalysis and background formatting repair')
        destination = result_path.parent / 'native-export.docx'
        original_dialog = QFileDialog.getSaveFileName
        QFileDialog.getSaveFileName = lambda *args, **kwargs: (str(destination), 'Word 文档 (*.docx)')
        try:
            window.export_current()
        finally:
            QFileDialog.getSaveFileName = original_dialog
        after_task(exported)

    def exported():
        destination = result_path.parent / 'native-export.docx'
        assert Package(destination.read_bytes(), destination.name).inspect(window.job()['options'])['autoCount'] == 0
        state['checks'].append('Native save workflow exports a real compliant DOCX')
        state['export'] = str(destination)
        window.store.export_file(window.active_id, result_path.parent / 'native-report.txt', 'report')
        window.store.export_bundle([window.active_id], result_path.parent / 'native-bundle.zip')
        state['checks'].append('Report and bundle exported without HTTP')
        window.navigate(3)
        window.search.setText('no-such-document-12345')
        assert all(window.history.isRowHidden(i) for i in range(window.history.rowCount()))
        window.search.clear()
        assert window.history.rowCount() == before_count + 1
        window.navigate(2)
        assert window.fonts.rowCount() >= 7
        QApplication.processEvents()
        window.grab().save(str(result_path.parent / 'native-fonts.png'))
        state['checks'].append('Native history search and font environment page')
        window.navigate(0)
        window.resize(1440, 960)
        QApplication.processEvents()
        window.grab().save(str(result_path.parent / 'native-workspace.png'))
        state['screenshot'] = str(result_path.parent / 'native-workspace.png')
        finish()

    guard(window.demo)()
    after_task(imported)
