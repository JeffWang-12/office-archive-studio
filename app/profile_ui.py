"""Native editors for user-defined formatting standards."""
import json
from copy import deepcopy
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QLineEdit, QComboBox, QDoubleSpinBox, QTableWidget, QHeaderView,
    QPushButton, QLabel, QDialogButtonBox, QFileDialog, QMessageBox, QListWidget,
    QTabWidget, QWidget, QAbstractItemView)
from .profiles import ROLE_NAMES, default_standard, validate_standard


def spin(value, low, high, step=.5, suffix=''):
    w = QDoubleSpinBox()
    w.setRange(low, high)
    w.setSingleStep(step)
    w.setDecimals(1)
    w.setValue(value)
    w.setSuffix(suffix)
    return w


class StandardEditor(QDialog):
    def __init__(self, standard=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑文本格式规范')
        self.resize(1000, 700)
        self.standard = deepcopy(standard or default_standard())
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 22)
        form = QFormLayout()
        self.name = QLineEdit(self.standard['name'])
        self.name.setMaxLength(50)
        form.addRow('规范名称', self.name)
        v.addLayout(form)
        tabs = QTabWidget()
        self.rows = QTableWidget(len(ROLE_NAMES), 6)
        self.rows.setHorizontalHeaderLabels(['段落类型', '中文字体', '字号 / 磅', '固定行距 / 磅', '首行 / 字符', '对齐'])
        self.rows.verticalHeader().hide()
        self.rows.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.rows.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.rows.setColumnWidth(0, 135)
        self.rows.setColumnWidth(3, 130)
        self.rows.setColumnWidth(4, 125)
        self.fields = {}
        for row, (key, name) in enumerate(ROLE_NAMES.items()):
            rule = self.standard['roles'][key]
            self.rows.setCellWidget(row, 0, QLabel('  ' + name))
            font = QLineEdit(rule['font'])
            font.setMaxLength(100)
            size = spin(rule['size'], 5, 96)
            line = spin(rule['line'], 5, 200)
            indent = spin(rule['indent'], 0, 10)
            align = QComboBox()
            for code, label in [('left', '左对齐'), ('center', '居中'), ('right', '右对齐'), ('both', '两端对齐')]:
                align.addItem(label, code)
            align.setCurrentIndex(align.findData(rule['align']))
            self.fields[key] = (font, size, line, indent, align)
            for col, field in enumerate(self.fields[key], 1):
                self.rows.setCellWidget(row, col, field)
            self.rows.setRowHeight(row, 45)
        tabs.addTab(self.rows, '文本格式')
        page = QWidget()
        layout = QFormLayout(page)
        layout.setContentsMargins(25, 25, 25, 25)
        self.paper = QComboBox()
        self.paper.addItems(['A4', 'A5', 'Letter'])
        self.paper.setCurrentText(self.standard['paper'])
        layout.addRow('纸张（保留原方向）', self.paper)
        self.margins = {}
        for key, title in [('top', '上页边距'), ('bottom', '下页边距'), ('left', '左页边距'), ('right', '右页边距'), ('header', '页眉距边界'), ('footer', '页脚距边界')]:
            self.margins[key] = spin(self.standard['margins'][key], 0, 80, .1, ' mm')
            layout.addRow(title, self.margins[key])
        tabs.addTab(page, '版面')
        v.addWidget(tabs)
        note = QLabel('只调整格式，保留原文、图片和表格 · 段前段后归零 · 页码沿用团内规范\n字体名称应与 Windows 中安装的字体一致，应用不会代为安装字体')
        note.setWordWrap(True)
        note.setObjectName('muted')
        v.addWidget(note)
        controls = QDialogButtonBox(QDialogButtonBox.StandardButton.Cancel | QDialogButtonBox.StandardButton.Save)
        controls.button(QDialogButtonBox.StandardButton.Cancel).setText('取消')
        controls.button(QDialogButtonBox.StandardButton.Save).setText('保存规范')
        controls.accepted.connect(self.save)
        controls.rejected.connect(self.reject)
        v.addWidget(controls)

    def value(self):
        raw = {'name': self.name.text(), 'paper': self.paper.currentText(),
               'margins': {k: w.value() for k, w in self.margins.items()}, 'roles': {}}
        for key, (font, size, line, indent, align) in self.fields.items():
            raw['roles'][key] = dict(font=font.text(), size=size.value(), line=line.value(),
                                    indent=indent.value(), align=align.currentData())
        return validate_standard(raw)

    def save(self):
        try:
            self.standard = self.value()
        except ValueError as exc:
            QMessageBox.warning(self, '请检查规范', str(exc))
            return
        self.accept()


class StandardsDialog(QDialog):
    def __init__(self, store, parent=None):
        super().__init__(parent)
        self.store = store
        self.setWindowTitle('我的格式规范')
        self.resize(650, 470)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 22)
        note = QLabel('新建规范后，可在工作台导入文件或“检查设置”中选用\n旧记录保留原来的规范快照，重新检查后才会应用修改')
        note.setWordWrap(True)
        v.addWidget(note)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(self.edit)
        v.addWidget(self.list, 1)
        row = QHBoxLayout()
        for text, callback in [('新建', self.create), ('编辑', self.edit), ('删除', self.remove), ('导入 JSON…', self.load), ('导出 JSON…', self.export)]:
            b = QPushButton(text)
            b.clicked.connect(callback)
            row.addWidget(b)
        v.addLayout(row)
        close = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        close.button(QDialogButtonBox.StandardButton.Close).setText('完成')
        close.rejected.connect(self.accept)
        v.addWidget(close)
        self.refresh()

    def key(self):
        row = self.list.currentRow()
        return list(self.store.profiles)[row] if row >= 0 else None

    def refresh(self, selected=None):
        self.list.clear()
        for key, profile in self.store.profiles.items():
            self.list.addItem(profile['name'] + '  ·  ' + profile['paper'])
            if key == selected:
                self.list.setCurrentRow(self.list.count() - 1)

    def create(self):
        dialog = StandardEditor(parent=self)
        if dialog.exec():
            self.persist(dialog.standard)

    def edit(self, *_):
        key = self.key()
        if key:
            dialog = StandardEditor(self.store.profiles[key], self)
            if dialog.exec():
                self.persist(dialog.standard, key)

    def persist(self, standard, key=None):
        try:
            self.refresh(self.store.save(standard, key))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, '未能保存规范', str(exc))

    def remove(self):
        key = self.key()
        if key and QMessageBox.question(self, '删除规范', '删除这个自定义规范？已处理档案的规范快照会保留', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            try:
                self.store.remove(key)
                self.refresh()
            except OSError as exc:
                QMessageBox.warning(self, '未能删除规范', str(exc))

    def load(self):
        path, _ = QFileDialog.getOpenFileName(self, '导入格式规范', '', '格式规范 (*.json)')
        if path:
            try:
                from pathlib import Path
                if Path(path).stat().st_size > 256 * 1024:
                    raise ValueError('规范文件不能超过 256 KB')
                standard = validate_standard(json.loads(Path(path).read_text(encoding='utf-8-sig')))
                dialog = StandardEditor(standard, self)
                if dialog.exec():
                    self.persist(dialog.standard)
            except (OSError, ValueError, TypeError, AttributeError) as exc:
                QMessageBox.warning(self, '无法导入规范', str(exc))

    def export(self):
        key = self.key()
        if not key:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出格式规范', '格式规范.json', '格式规范 (*.json)')
        if path:
            try:
                from pathlib import Path
                Path(path if path.lower().endswith('.json') else path + '.json').write_text(json.dumps(self.store.profiles[key], ensure_ascii=False, indent=2), encoding='utf-8')
            except OSError as exc:
                QMessageBox.warning(self, '无法导出规范', str(exc))
