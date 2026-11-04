"""Schema-driven Qt forms in the same native desktop window."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (QWidget, QLabel, QPushButton, QVBoxLayout, QHBoxLayout,
    QFormLayout, QLineEdit, QTextEdit, QComboBox, QTabWidget, QScrollArea,
    QFrame, QFileDialog, QMessageBox, QCheckBox, QListWidget, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView)
from .generation import GeneratorLibrary
from .generator.generator_core import default_value
from .generator.photo_guard import validate_photos


def action(text, callback, primary=False):
    b = QPushButton(text)
    b.setProperty('primary', primary)
    b.clicked.connect(callback)
    return b


class TaskGroups(QWidget):
    changed = Signal()

    def __init__(self, maximum=12):
        super().__init__()
        self.maximum = maximum
        self.groups = []
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        self.add_button = action('＋ 添加工作任务', self.add)
        self.layout.addWidget(self.add_button)

    def add(self, checked=False, value=None):
        if len(self.groups) >= self.maximum:
            return
        frame = QFrame()
        frame.setObjectName('card')
        form = QFormLayout(frame)
        description = QLineEdit()
        description.setPlaceholderText('任务内容')
        goals, measures = QTextEdit(), QTextEdit()
        for w, title in [(goals, '每行一条目标'), (measures, '每行一条具体措施')]:
            w.setAcceptRichText(False)
            w.setPlaceholderText(title)
            w.setFixedHeight(100)
        form.addRow('任务内容', description)
        form.addRow('目标', goals)
        form.addRow('具体措施', measures)
        group = (frame, description, goals, measures)
        remove = action('移除此任务', lambda: self.remove(group))
        form.addRow('', remove)
        self.groups.append(group)
        self.layout.insertWidget(self.layout.count() - 1, frame)
        for w in (description, goals, measures):
            w.textChanged.connect(self.changed)
        if value:
            description.setText(str(value.get('description', '')))
            goals.setPlainText('\n'.join(value.get('goals', [])))
            measures.setPlainText('\n'.join(value.get('measures', [])))
        self.add_button.setEnabled(len(self.groups) < self.maximum)
        self.changed.emit()

    def remove(self, group):
        self.groups.remove(group)
        group[0].deleteLater()
        self.add_button.setEnabled(True)
        self.changed.emit()

    def value(self):
        return [dict(description=d.text(), goals=g.toPlainText().splitlines(), measures=m.toPlainText().splitlines()) for _, d, g, m in self.groups]

    def set_value(self, values):
        for group in list(self.groups):
            self.remove(group)
        for value in values if isinstance(values, list) else []:
            if isinstance(value, dict):
                self.add(value=value)


class GridField(QWidget):
    changed = Signal()

    def __init__(self, kind, maximum):
        super().__init__()
        self.maximum = maximum
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        headers = ['名称', '页码'] if kind == 'toc' else ['活动名称', '时间', '地点', '组织单位', '邀请出席人']
        self.table = QTableWidget(0, len(headers))
        self.table.setHorizontalHeaderLabels(headers)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setMinimumHeight(190)
        self.table.itemChanged.connect(self.changed)
        v.addWidget(self.table)
        h = QHBoxLayout()
        h.addWidget(action('＋ 添加一行', self.add))
        h.addWidget(action('移除所选行', self.remove))
        h.addStretch()
        v.addLayout(h)

    def add(self):
        if self.table.rowCount() < self.maximum:
            self.table.insertRow(self.table.rowCount())
            self.changed.emit()

    def remove(self):
        for row in sorted({i.row() for i in self.table.selectionModel().selectedRows()}, reverse=True):
            self.table.removeRow(row)
        self.changed.emit()

    def value(self):
        rows = []
        for row in range(self.table.rowCount()):
            values = [self.table.item(row, col).text().strip() if self.table.item(row, col) else '' for col in range(self.table.columnCount())]
            if any(values):
                rows.append('|'.join(values))
        return '\n'.join(rows)

    def set_value(self, value):
        self.table.setRowCount(0)
        for line in str(value).splitlines()[:self.maximum]:
            if not line.strip():
                continue
            row = self.table.rowCount()
            self.table.insertRow(row)
            for col, text in enumerate(line.split('|')[:self.table.columnCount()]):
                self.table.setItem(row, col, QTableWidgetItem(text))


class PhotosField(QWidget):
    changed = Signal()

    def __init__(self):
        super().__init__()
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        h = QHBoxLayout()
        self.list = QListWidget()
        self.list.setFixedHeight(130)
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.preview = QLabel('照片预览')
        self.preview.setFixedSize(160, 130)
        self.preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.list.currentRowChanged.connect(self.show_preview)
        h.addWidget(self.list, 1)
        h.addWidget(self.preview)
        v.addLayout(h)
        row = QHBoxLayout()
        row.addWidget(action('选择照片…', self.browse))
        row.addWidget(action('移除所选照片', self.remove))
        row.addStretch()
        v.addLayout(row)
        self.hint = QLabel('2–3 张不同照片 · 短边至少 300 像素 · 每张不超过 25 MB')
        self.hint.setObjectName('muted')
        v.addWidget(self.hint)

    def browse(self):
        paths, _ = QFileDialog.getOpenFileNames(self, '选择活动照片', '', '图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif)')
        if paths:
            combined = list(dict.fromkeys(self.value() + paths))
            try:
                if len(combined) > 3:
                    raise ValueError('最多选择 3 张照片，请先移除不需要的照片')
                validate_photos(combined)
                self.set_value(combined)
                self.changed.emit()
            except ValueError as exc:
                QMessageBox.warning(self, '请检查照片', str(exc))

    def remove(self):
        for entry in self.list.selectedItems():
            self.list.takeItem(self.list.row(entry))
        self.show_preview(self.list.currentRow())
        self.changed.emit()

    def value(self):
        return [self.list.item(row).data(Qt.ItemDataRole.UserRole) for row in range(self.list.count())]

    def set_value(self, values):
        self.list.clear()
        for path in values if isinstance(values, list) else []:
            self.list.addItem(Path(path).name)
            self.list.item(self.list.count() - 1).setData(Qt.ItemDataRole.UserRole, str(path))
            self.list.item(self.list.count() - 1).setToolTip(str(path))
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.preview.setPixmap(QPixmap())
            self.preview.setText('照片预览')

    def show_preview(self, row):
        if row < 0:
            self.preview.clear()
            return
        path = self.list.item(row).data(Qt.ItemDataRole.UserRole)
        pixmap = QPixmap(path)
        self.preview.setPixmap(pixmap.scaled(160, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))


class GenerationPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.library = GeneratorLibrary(host.store.root)
        self.fields = {}
        self.current_name = None
        self.loading = False
        self.last_output = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(650)
        self.timer.timeout.connect(self.save_draft)
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 23, 28, 23)
        v.setSpacing(16)
        title = QLabel('从内容，到完整档案')
        title.setObjectName('headline')
        v.addWidget(title)
        sub = QLabel('封皮、计划、总结与文化导航申报 · 本机生成 DOCX')
        sub.setObjectName('muted')
        v.addWidget(sub)
        row = QHBoxLayout()
        self.templates = QComboBox()
        self.templates.setMinimumWidth(280)
        self.templates.currentTextChanged.connect(self.select_template)
        row.addWidget(self.templates, 1)
        for text, callback in [('导入资源…', self.import_library), ('添加模板…', self.add_template), ('恢复标准模板', self.restore)]:
            row.addWidget(host.add_control(action(text, callback)))
        v.addLayout(row)
        self.description = QLabel()
        self.description.setWordWrap(True)
        self.description.setObjectName('muted')
        v.addWidget(self.description)
        self.tabs = QTabWidget()
        v.addWidget(self.tabs, 1)
        options = QHBoxLayout()
        self.autosave = QCheckBox('自动保存本机草稿')
        self.autosave.setChecked(self.library.auto_save)
        self.autosave.toggled.connect(self.toggle_autosave)
        options.addWidget(self.autosave)
        self.embed = QCheckBox('嵌入可授权字体')
        self.embed.setToolTip('读取字体的嵌入许可标志，禁止嵌入的字体会跳过；接收方仍可能需要安装缺失字体')
        options.addWidget(self.embed)
        options.addWidget(action('清空当前草稿', self.clear_draft))
        options.addStretch()
        self.draft_state = QLabel(self.library.draft_warning or '草稿保存在本机')
        self.draft_state.setObjectName('muted')
        options.addWidget(self.draft_state)
        v.addLayout(options)
        row = QHBoxLayout()
        self.generate_button = host.add_control(action('生成并另存 DOCX…', self.generate, True))
        row.addWidget(self.generate_button)
        self.open_button = action('打开生成文件', self.open_output)
        self.open_button.setEnabled(False)
        row.addWidget(self.open_button)
        row.addWidget(action('打开模板库', lambda: host.open_path(self.library.root)))
        row.addStretch()
        v.addLayout(row)
        self.result = QLabel('生成后可直接用 Word / WPS 打开，也会加入格式工作台供进一步检查')
        self.result.setWordWrap(True)
        self.result.setObjectName('muted')
        v.addWidget(self.result)
        self.refresh_catalog()

    def refresh_catalog(self, selected=None):
        self.save_draft()
        try:
            self.catalog = self.library.catalog()
        except Exception as exc:
            self.catalog = {}
            self.description.setText('模板库无法读取：' + str(exc))
        self.templates.blockSignals(True)
        self.templates.clear()
        self.templates.addItems(list(self.catalog))
        if selected in self.catalog:
            self.templates.setCurrentText(selected)
        self.templates.blockSignals(False)
        self.select_template(self.templates.currentText())

    def collect(self):
        result = {}
        for name, (kind, widget) in self.fields.items():
            if hasattr(widget, 'value'):
                value = widget.value()
            elif isinstance(widget, QComboBox):
                value = widget.currentText()
            elif isinstance(widget, QTextEdit):
                value = widget.toPlainText().splitlines() if kind == 'points' else widget.toPlainText()
            else:
                value = widget.text()
            result[name] = value
        return result

    def select_template(self, name):
        self.save_draft()
        self.timer.stop()
        self.loading = True
        self.current_name = name or None
        self.fields = {}
        while self.tabs.count():
            page = self.tabs.widget(0)
            self.tabs.removeTab(0)
            page.deleteLater()
        spec = self.catalog.get(name)
        if not spec:
            self.description.setText('导入本机模板资源，或添加含 {{ 占位符 }} 的 DOCX 模板')
            self.loading = False
            return
        self.description.setText(str(spec.get('description', '')).rstrip('。'))
        layouts = {}
        for group, caption in [('basic', '基本信息'), ('body', '主要内容'), ('activity', '活动与照片'), ('signature', '落款')]:
            container = QWidget()
            container.setObjectName('generatorForm')
            form = QFormLayout(container)
            form.setContentsMargins(24, 22, 24, 22)
            form.setSpacing(15)
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            scroll.setWidget(container)
            layouts[group] = (form, scroll, caption)
        drafts = self.library.drafts.get(name, {})
        for field in spec.get('fields', []):
            key, kind = field['name'], field.get('type', 'text')
            saved = drafts.get(key, default_value(field)) if isinstance(drafts, dict) else default_value(field)
            if kind == 'task_groups':
                widget = TaskGroups(int(field.get('max_tasks', 12)))
                widget.set_value(saved)
            elif kind == 'photos':
                widget = PhotosField()
                widget.set_value(saved)
            elif kind in ('events', 'toc'):
                widget = GridField(kind, int(field.get('max_rows', 7 if kind == 'events' else 6)))
                widget.set_value(saved)
            elif kind == 'choice':
                widget = QComboBox()
                widget.addItems(field.get('choices', []))
                widget.setCurrentText(str(saved))
            elif kind in ('multiline', 'points'):
                widget = QTextEdit()
                widget.setAcceptRichText(False)
                widget.setFixedHeight(130)
                widget.setPlaceholderText('每行填写一条内容，编号会自动生成' if kind == 'points' else '填写内容')
                widget.setPlainText('\n'.join(saved) if isinstance(saved, list) else str(saved))
            else:
                widget = QLineEdit(str(saved))
                widget.setMaxLength(int(field.get('max_chars', 4000)))
                if kind == 'date':
                    widget.setPlaceholderText('YYYY-MM-DD')
            self.fields[key] = kind, widget
            widget.setAccessibleName(field.get('label', key))
            if hasattr(widget, 'changed'):
                widget.changed.connect(self.schedule_draft)
            elif isinstance(widget, QComboBox):
                widget.currentTextChanged.connect(self.schedule_draft)
            else:
                widget.textChanged.connect(self.schedule_draft)
            group = 'activity' if key.startswith(('activity', 'photo')) else ('signature' if key in ('signature_unit', 'date') else ('body' if kind in ('points', 'task_groups', 'events', 'toc') else 'basic'))
            caption = str(field.get('label', key)).rstrip('。') + (' *' if field.get('required') else '')
            title = QLabel(caption)
            title.setWordWrap(True)
            title.setFixedWidth(180)
            layouts[group][0].addRow(title, widget)
        for form, scroll, caption in layouts.values():
            if form.rowCount():
                self.tabs.addTab(scroll, caption)
            else:
                scroll.deleteLater()
        self.loading = False

    def schedule_draft(self, *_):
        if not self.loading and self.library.auto_save:
            self.draft_state.setText('正在编辑')
            self.timer.start()

    def save_draft(self):
        if self.current_name and not self.loading and self.library.auto_save:
            try:
                self.library.save_draft(self.current_name, self.collect())
                self.draft_state.setText('草稿已保存')
                return True
            except (OSError, ValueError) as exc:
                self.draft_state.setText('草稿未保存：' + str(exc))
                return False
        return True

    def toggle_autosave(self, checked):
        self.library.auto_save = checked
        self.timer.stop()
        try:
            self.library.persist()
            self.draft_state.setText('草稿保存在本机' if checked else '自动保存已关闭')
        except OSError as exc:
            self.host.error(str(exc))
        if checked:
            self.save_draft()

    def clear_draft(self):
        if self.current_name and QMessageBox.question(self, '清空当前草稿', '清空当前模板的填写内容？其他模板草稿和已生成文件会保留', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.timer.stop()
            self.library.drafts.pop(self.current_name, None)
            try:
                self.library.persist()
                # Prevent the old form from being saved again while rebuilding it.
                name, self.current_name = self.current_name, None
                self.select_template(name)
                self.draft_state.setText('当前草稿已清空')
            except OSError as exc:
                self.host.error(str(exc))

    def import_library(self):
        path = QFileDialog.getExistingDirectory(self, '选择本机模板资源文件夹')
        if path:
            self.host.run_task('正在导入模板资源', lambda: self.library.import_resources(path), lambda _: self.refresh_catalog())

    def add_template(self):
        path, _ = QFileDialog.getOpenFileName(self, '添加含 {{ 占位符 }} 的 DOCX 模板', '', 'Word 模板 (*.docx)')
        if path:
            self.host.run_task('正在导入自定义模板', lambda: self.library.add_template(path), lambda _: self.refresh_catalog())

    def restore(self):
        if QMessageBox.question(self, '恢复标准模板', '恢复七份标准模板？自定义模板、草稿和已生成文件会保留', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.host.run_task('正在恢复标准模板', self.library.restore, lambda _: self.refresh_catalog())

    def generate(self):
        if self.host.busy or not self.current_name:
            return
        name, values, embed = self.current_name, self.collect(), self.embed.isChecked()
        from .generator.generator_core import validate_values
        try:
            validate_values(self.catalog[name], values)
        except ValueError as exc:
            self.host.error(str(exc))
            return
        path, _ = QFileDialog.getSaveFileName(self, '生成档案并另存', str(Path.home() / 'Desktop' / (name + '.docx')), 'Word 文档 (*.docx)')
        if not path:
            return
        path = path if path.lower().endswith('.docx') else path + '.docx'
        self.save_draft()
        def work():
            result = self.library.generate(name, values, path, embed)
            job = self.host.store.import_file(result.output_path, {'profile': 'summary' if self.catalog[name].get('summary') else 'general', 'titleLine': 35})
            return result, job
        def complete(payload):
            result, job = payload
            self.last_output = result.output_path
            self.open_button.setEnabled(True)
            self.host.active_id = job['id']
            self.host.refresh()
            warning = '；'.join(result.warnings)
            self.result.setText('已生成：' + str(result.output_path) + ('\n字体提示：' + warning if warning else ''))
            self.host.statusBar().showMessage('档案已生成，并已加入格式工作台')
        self.host.run_task('正在生成完整档案', work, complete)

    def open_output(self):
        if self.last_output:
            self.host.open_path(self.last_output)
