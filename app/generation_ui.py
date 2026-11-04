"""Complete native generator: selector, one scrolling form, fixed action footer."""
from pathlib import Path
from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QGridLayout,
    QFormLayout, QLineEdit, QTextEdit, QScrollArea, QFrame, QFileDialog,
    QMessageBox, QCheckBox, QMenu, QDialog, QLayout)
from .generation import GeneratorLibrary
from .generator.generator_core import default_value, validate_values, AUTO_FONT
from .generator.template_guard import VERSION, version_is_outdated
from .generator_fields import (action, TaskGroups, PointsEditor, FormTextEdit,
                               FormComboBox, NumberEntry, DateEntry, visible_length)
from .generator_media import GridField, PhotosField

DESCRIPTIONS = {
    '年度档案封皮': '单页年度档案封皮 · 填写学院、学年和文档类别',
    '月份档案封皮': '单页月份档案封皮 · 填写学院、年份、月份和文档类别',
    '年度工作计划': '按顺序填写总体思路、全面推进任务、重点及创新任务，目标和措施可逐条增减',
    '月份工作计划': '填写目录和月度工作安排，每个任务分别填写内容、目标与具体措施',
    '年度工作总结': '填写总结、特色活动、2–3 张照片、困难和建议，可选择照片位置与排版方式',
    '月份工作总结': '填写目录、月度总结、活动信息、2–3 张照片和问题建议',
    '文化导航申报表': '最多 7 项活动，无活动也可生成空表 · 纸质件需核对盖章和签字',
}


class GeneratedDialog(QDialog):
    def __init__(self, result, host):
        super().__init__(host)
        self.setWindowTitle('文档已生成 · 提交前核对')
        self.resize(620, 560)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 24, 26, 24)
        layout.setSpacing(14)
        heading = QLabel('文档已生成')
        heading.setObjectName('section')
        layout.addWidget(heading)
        path = QLabel(str(result.output_path))
        path.setTextFormat(Qt.TextFormat.PlainText)
        path.setWordWrap(True)
        path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        layout.addWidget(path)
        embedded = '、'.join(item['font'] for item in result.font_report.get('embedded', [])) or '未嵌入字体'
        text = QLabel('执行规范：' + VERSION + '\n已封装字体：' + embedded)
        text.setTextFormat(Qt.TextFormat.PlainText)
        text.setWordWrap(True)
        text.setObjectName('muted')
        layout.addWidget(text)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        body = QWidget()
        body.setObjectName('generatorForm')
        checks = QVBoxLayout(body)
        checks.setContentsMargins(0, 3, 6, 3)
        self.checklist = []
        for caption in ['标题与正文字体是否正确', '日期、落款和附件位置', '照片内容、方向和清晰度',
                        '内容与数据真实性', '公章、签字与纸质件要求', '最终 PDF 页码与装订']:
            check = QCheckBox(caption)
            self.checklist.append(check)
            checks.addWidget(check)
        note = QLabel('生成成功表示文件已输出，以上事项仍需人工审核')
        note.setObjectName('muted')
        note.setWordWrap(True)
        checks.addWidget(note)
        if result.warnings:
            warning = QLabel('提示\n' + '\n'.join('• ' + str(item).rstrip('。') for item in result.warnings))
            warning.setTextFormat(Qt.TextFormat.PlainText)
            warning.setWordWrap(True)
            warning.setObjectName('warning')
            checks.addWidget(warning)
        checks.addStretch()
        scroll.setWidget(body)
        layout.addWidget(scroll, 1)
        row = QHBoxLayout()
        row.addWidget(action('打开文档', lambda: host.open_path(result.output_path)))
        row.addWidget(action('打开输出文件夹', lambda: host.open_path(result.output_path.parent)))
        row.addStretch()
        row.addWidget(action('完成', self.accept, True))
        layout.addLayout(row)


class GenerationPage(QWidget):
    def __init__(self, host):
        super().__init__()
        self.host = host
        self.library = GeneratorLibrary(host.store.root)
        self.fields = {}
        self.field_rows = {}
        self.current_name = None
        self.loading = False
        self.last_output = None
        self.success_dialog = None
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.setInterval(650)
        self.timer.timeout.connect(self.save_draft)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 23, 28, 20)
        layout.setSpacing(15)
        title = QLabel('标准化档案文档生成')
        title.setObjectName('headline')
        layout.addWidget(title)
        self.version_label = QLabel(f'当前规范：{VERSION} · 团内格式规范优先 · 一键生成 Word')
        self.version_label.setObjectName('muted')
        layout.addWidget(self.version_label)
        self.version_warning = QLabel('当前学年规范可能已过期，请核对最新要求后再提交材料')
        self.version_warning.setObjectName('warning')
        self.version_warning.setWordWrap(True)
        self.version_warning.setVisible(version_is_outdated())
        layout.addWidget(self.version_warning)

        selector = QFrame()
        selector.setObjectName('card')
        grid = QGridLayout(selector)
        grid.setContentsMargins(20, 16, 20, 16)
        grid.setHorizontalSpacing(14)
        grid.addWidget(QLabel('文档类型'), 0, 0)
        self.templates = host.add_control(FormComboBox())
        self.templates.setAccessibleName('生成文档类型')
        self.templates.setMaxVisibleItems(14)
        self.templates.currentTextChanged.connect(self.select_template)
        grid.addWidget(self.templates, 0, 1)
        grid.addWidget(QLabel('执行规范'), 0, 2)
        self.standard = FormComboBox()
        self.standard.addItem(AUTO_FONT)
        self.standard.setToolTip('七类标准模板按团内规范生成；自定义模板保留其原版式，进一步调整可在格式工作台选用自己的规范')
        grid.addWidget(self.standard, 0, 3)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        self.description = QLabel()
        self.description.setTextFormat(Qt.TextFormat.PlainText)
        self.description.setWordWrap(True)
        self.description.setObjectName('muted')
        grid.addWidget(self.description, 1, 0, 1, 4)
        layout.addWidget(selector)

        form_card = QFrame()
        form_card.setObjectName('card')
        card_layout = QVBoxLayout(form_card)
        card_layout.setContentsMargins(4, 5, 4, 5)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setAccessibleName('完整档案填写表单')
        card_layout.addWidget(self.scroll)
        layout.addWidget(form_card, 1)

        output = QHBoxLayout()
        output.addWidget(QLabel('输出目录'))
        self.output_path = QLineEdit(str(self.library.output_directory))
        self.output_path.setReadOnly(True)
        self.output_path.setAccessibleName('生成文件输出目录')
        output.addWidget(self.output_path, 1)
        output.addWidget(host.add_control(action('选择目录…', self.choose_output)))
        output.addWidget(action('打开目录', self.open_output_directory))
        more = host.add_control(action('更多操作', None))
        self.more_menu = QMenu(more)
        for caption, callback in [('另存为 DOCX…', self.generate_as), ('添加外部模板…', self.add_template),
                                  ('替换自定义模板…', self.replace_custom_template), ('导入模板资源…', self.import_library),
                                  ('导入旧版 / 备份草稿…', self.import_drafts), ('导出草稿备份…', self.export_drafts),
                                  ('刷新文档类型', self.refresh_catalog), ('打开模板资源目录', lambda: host.open_path(self.library.root)),
                                  ('只清空当前文档草稿', lambda: self.clear_draft(False))]:
            self.more_menu.addAction(caption, callback)
        more.setMenu(self.more_menu)
        output.addWidget(more)
        layout.addLayout(output)

        bottom = QHBoxLayout()
        self.draft_state = QLabel(self.library.draft_warning or '就绪')
        self.draft_state.setTextFormat(Qt.TextFormat.PlainText)
        self.draft_state.setObjectName('muted')
        self.draft_state.setWordWrap(True)
        self.draft_state.setMinimumWidth(110)
        bottom.addWidget(self.draft_state, 1)
        self.autosave = QCheckBox('自动保存草稿（明文）')
        self.autosave.setChecked(self.library.auto_save)
        self.autosave.setToolTip('草稿仅保存在本机；关闭时可删除磁盘草稿，当前窗口仍保留填写内容')
        self.autosave.toggled.connect(self.toggle_autosave)
        bottom.addWidget(self.autosave)
        self.embed = QCheckBox('嵌入可授权字体')
        self.embed.setChecked(bool(self.library.preferences.get('embedFonts', True)))
        self.embed.toggled.connect(lambda checked: self.remember(embedFonts=checked))
        self.embed.setToolTip('禁止嵌入和仅允许位图嵌入的字体会跳过，不会绕过字体嵌入标志')
        bottom.addWidget(self.embed)
        bottom.addWidget(host.add_control(action('清空草稿', lambda: self.clear_draft(True))))
        bottom.addWidget(host.add_control(action('恢复标准模板', self.restore)))
        self.generate_button = host.add_control(action('一键生成文档', self.generate, True))
        self.generate_button.setMinimumHeight(45)
        bottom.addWidget(self.generate_button)
        layout.addLayout(bottom)
        self.result = QLabel('按原表单顺序填写，标 * 为必填项')
        self.result.setObjectName('muted')
        layout.addWidget(self.result)
        self.refresh_catalog(self.library.preferences.get('defaultTemplate'))

    def remember(self, **settings):
        try:
            self.library.remember(**settings)
        except OSError as exc:
            self.draft_state.setText('设置未保存：' + str(exc))

    def refresh_catalog(self, selected=None):
        if isinstance(selected, bool):
            selected = None
        selected = selected or self.current_name
        self.save_draft()
        error = None
        try:
            self.catalog = self.library.catalog()
        except Exception as exc:
            self.catalog = {}
            error = '模板库无法读取：' + str(exc)
        self.templates.blockSignals(True)
        self.templates.clear()
        self.templates.addItems(list(self.catalog))
        if selected in self.catalog:
            self.templates.setCurrentText(selected)
        self.templates.blockSignals(False)
        self.select_template(self.templates.currentText())
        if error:
            self.description.setText(error)

    def collect(self):
        values = {}
        for key, (_, widget) in self.fields.items():
            if hasattr(widget, 'value'):
                values[key] = widget.value()
            elif isinstance(widget, FormComboBox):
                values[key] = widget.currentText()
            elif isinstance(widget, QTextEdit):
                values[key] = widget.toPlainText()
            else:
                values[key] = widget.text()
        return values

    def select_template(self, name):
        self.save_draft()
        self.timer.stop()
        self.loading = True
        self.current_name = name or None
        self.fields, self.field_rows = {}, {}
        old = self.scroll.takeWidget()
        if old:
            old.hide()
            old.deleteLater()
        container = QWidget()
        container.setObjectName('generatorForm')
        self.form_content = container
        outer = QVBoxLayout(container)
        outer.setSizeConstraint(QLayout.SizeConstraint.SetMinAndMaxSize)
        outer.setContentsMargins(20, 16, 20, 20)
        self.form = QFormLayout()
        self.form.setHorizontalSpacing(20)
        self.form.setVerticalSpacing(17)
        self.form.setLabelAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        outer.addLayout(self.form)
        outer.addStretch()
        self.scroll.setWidget(container)
        spec = self.catalog.get(name)
        if not spec:
            self.description.setText('在“更多操作”中导入模板资源，或添加含 {{ 占位符 }} 的 DOCX 模板')
            self.draft_state.setText('未选择文档类型')
            self.loading = False
            return
        self.description.setText(DESCRIPTIONS.get(name, str(spec.get('description', '')).rstrip('。')))
        saved_values = self.library.drafts.get(name, {})
        for field in spec.get('fields', []):
            key, kind = field['name'], field.get('type', 'text')
            saved = saved_values.get(key, default_value(field)) if isinstance(saved_values, dict) else default_value(field)
            if kind == 'task_groups':
                widget = TaskGroups(int(field.get('max_tasks', 12)))
                widget.set_value(saved)
            elif kind == 'points':
                widget = PointsEditor(int(field.get('max_items', 20)))
                widget.set_value(saved)
            elif kind == 'photos':
                widget = PhotosField()
                widget.set_value(saved)
            elif kind in ('events', 'toc'):
                widget = GridField(kind, int(field.get('max_rows', 7 if kind == 'events' else 6)))
                widget.set_value(saved)
            elif kind == 'choice':
                widget = FormComboBox()
                widget.addItems(field.get('choices', []))
                widget.setCurrentText(str(saved))
            elif kind == 'multiline':
                widget = FormTextEdit(int(field.get('rows', 5)))
                widget.setPlainText(str(saved))
            elif kind == 'date':
                widget = DateEntry(saved)
            elif kind == 'number':
                amount = '金额' in field.get('label', '') or any(word in key.lower() for word in ('amount', 'money'))
                widget = NumberEntry(saved, amount, field.get('digits'))
            else:
                widget = QLineEdit(str(saved))
                widget.setMaxLength(int(field.get('max_chars', 4000)))
            self.fields[key] = kind, widget
            widget.setAccessibleName(field.get('label', key))
            row = QWidget()
            row_layout = QVBoxLayout(row)
            row_layout.setContentsMargins(0, 0, 0, 0)
            row_layout.setSpacing(5)
            row_layout.addWidget(widget)
            if field.get('hint'):
                hint = QLabel(str(field['hint']).rstrip('。'))
                hint.setTextFormat(Qt.TextFormat.PlainText)
                hint.setWordWrap(True)
                hint.setObjectName('muted')
                row_layout.addWidget(hint)
            maximum = field.get('max_chars')
            count = None
            if maximum and kind in ('multiline', 'points', 'task_groups'):
                count = QLabel()
                count.setObjectName('muted')
                row_layout.addWidget(count)
            def changed(*_, w=widget, counter=count, limit=maximum):
                if counter is not None:
                    value = w.value() if hasattr(w, 'value') else w.toPlainText()
                    length = visible_length(value)
                    counter.setText(f'{length} / {limit} 字（不计空白）')
                self.schedule_draft()
            if hasattr(widget, 'changed'):
                widget.changed.connect(changed)
            elif isinstance(widget, FormComboBox):
                widget.currentTextChanged.connect(changed)
            else:
                widget.textChanged.connect(changed)
            changed()
            caption = QWidget()
            label_row = QHBoxLayout(caption)
            label_row.setContentsMargins(0, 8, 0, 0)
            label_row.setSpacing(4)
            title = QLabel(str(field.get('label', key)).rstrip('。'))
            title.setTextFormat(Qt.TextFormat.PlainText)
            title.setWordWrap(True)
            label_row.addWidget(title, 1)
            if field.get('required'):
                required = QLabel('*')
                required.setObjectName('required')
                label_row.addWidget(required, 0, Qt.AlignmentFlag.AlignTop)
            caption.setFixedWidth(220)
            self.form.addRow(caption, row)
            self.field_rows[key] = row
        self.loading = False
        self.draft_state.setText('已选择：' + name)
        self.remember(defaultTemplate=name)
        self.scroll.verticalScrollBar().setValue(0)

    def schedule_draft(self, *_):
        if not self.loading:
            self.draft_state.setText('正在编辑' if self.library.auto_save else '本次填写仅留在当前窗口')
            if self.library.auto_save:
                self.timer.start()

    def save_draft(self):
        if self.current_name and not self.loading:
            try:
                self.library.save_draft(self.current_name, self.collect())
                self.draft_state.setText('草稿已保存' if self.library.auto_save else '本次填写仅留在当前窗口')
            except (OSError, ValueError) as exc:
                self.draft_state.setText('草稿未保存：' + str(exc))
                return False
        return True

    def toggle_autosave(self, checked):
        if not checked:
            answer = QMessageBox.question(self, '关闭草稿自动保存', '关闭后删除本机已保存的草稿及备份\n当前窗口的填写内容仍会保留，退出后不再恢复\n\n是否关闭？', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
            if answer != QMessageBox.StandardButton.Yes:
                self.autosave.blockSignals(True)
                self.autosave.setChecked(True)
                self.autosave.blockSignals(False)
                return
        self.timer.stop()
        try:
            self.library.set_auto_save(checked)
            self.save_draft()
        except OSError as exc:
            self.autosave.blockSignals(True)
            self.autosave.setChecked(self.library.auto_save)
            self.autosave.blockSignals(False)
            self.host.error(str(exc))

    def clear_draft(self, all_templates=False):
        if not self.current_name:
            return
        caption = '全部文档类型的草稿' if all_templates else '当前文档类型的草稿'
        if QMessageBox.question(self, '清空草稿', '清空' + caption + '？\n已生成文件会保留，草稿及对应备份将清理', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.timer.stop()
        try:
            name = self.current_name
            self.library.clear_drafts(None if all_templates else name)
            self.current_name = None
            self.select_template(name)
            self.draft_state.setText('全部草稿已清空' if all_templates else '当前草稿已清空')
        except OSError as exc:
            self.host.error(str(exc))

    def choose_output(self):
        path = QFileDialog.getExistingDirectory(self, '选择文档输出目录', str(self.library.output_directory))
        if path:
            self.remember(outputDirectory=str(Path(path).resolve()))
            self.output_path.setText(str(self.library.output_directory))

    def import_drafts(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择旧版填写草稿或备份', '', '草稿文件 (*.json *.bak)')
        if not path:
            return
        try:
            values = self.library.read_drafts(path)
            if QMessageBox.question(self, '导入草稿', f'导入 {len(values)} 类文档的草稿？\n同名文档类型的现有草稿会被替换', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.save_draft()
            self.timer.stop()
            self.library.import_drafts(values)
            name, self.current_name = self.current_name, None
            self.select_template(name or self.templates.currentText())
            self.draft_state.setText(f'已导入 {len(values)} 类草稿' + ('，仅在当前会话保留' if not self.library.auto_save else ''))
        except (OSError, ValueError) as exc:
            self.host.error(str(exc))

    def export_drafts(self):
        self.save_draft()
        path, _ = QFileDialog.getSaveFileName(self, '导出填写草稿备份（明文 JSON）', '填写草稿备份.json', '草稿文件 (*.json)')
        if path:
            try:
                self.library.export_drafts(path if path.lower().endswith('.json') else path + '.json')
                self.draft_state.setText('草稿备份已导出')
            except OSError as exc:
                self.host.error(str(exc))

    def open_output_directory(self):
        try:
            self.library.output_directory.mkdir(parents=True, exist_ok=True)
            self.host.open_path(self.library.output_directory)
        except OSError as exc:
            self.host.error(str(exc))

    def import_library(self):
        path = QFileDialog.getExistingDirectory(self, '选择本机模板资源文件夹')
        if path:
            self.host.run_task('正在导入模板资源', lambda: self.library.import_resources(path), lambda _: self.refresh_catalog())

    def add_template(self):
        path, _ = QFileDialog.getOpenFileName(self, '添加含 {{ 占位符 }} 的 DOCX 模板', '', 'Word 模板 (*.docx)')
        if path:
            def completed(target):
                self.refresh_catalog()
                selected = next((name for name, spec in self.catalog.items() if Path(spec['path']) == target), None)
                if selected:
                    self.templates.setCurrentText(selected)
            self.host.run_task('正在导入自定义模板', lambda: self.library.add_template(path), completed)

    def replace_custom_template(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择新的根目录自定义模板', '', 'Word 模板 (*.docx)')
        if path:
            self.host.run_task('正在更新自定义模板', lambda: self.library.replace_custom_template(path), lambda _: self.refresh_catalog('自定义模板（根目录模板.docx）'))

    def restore(self):
        if QMessageBox.question(self, '恢复标准模板', '恢复七份标准模板？\n自定义模板、草稿和已生成文件会保留', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            def complete(count):
                self.refresh_catalog()
                self.draft_state.setText(f'已恢复 {count} 份标准模板')
            self.host.run_task('正在恢复标准模板', self.library.restore, complete)

    def focus_error(self, message):
        key = next((f['name'] for f in self.catalog[self.current_name].get('fields', []) if f.get('label') and f['label'] in message), None)
        if not key and '照片' in message:
            key = 'photo_paths'
        if key in self.fields:
            widget = self.fields[key][1]
            self.scroll.ensureWidgetVisible(widget, 12, 25)
            widget.setFocus(Qt.FocusReason.OtherFocusReason)

    def generate_as(self):
        self.generate(save_as=True)

    def generate(self, checked=False, save_as=False):
        if self.host.busy or not self.current_name:
            return
        name, values, embed = self.current_name, self.collect(), self.embed.isChecked()
        spec = self.catalog[name]
        try:
            validate_values(spec, values)
        except ValueError as exc:
            self.focus_error(str(exc))
            self.host.error(str(exc))
            return
        destination = None
        if save_as:
            path, _ = QFileDialog.getSaveFileName(self, '生成档案并另存', str(self.library.output_directory / (name + '.docx')), 'Word 文档 (*.docx)')
            if not path:
                return
            destination = path if path.lower().endswith('.docx') else path + '.docx'
        self.save_draft()
        self.remember(defaultTemplate=name, embedFonts=embed)
        def work():
            result = self.library.generate(name, values, destination, embed)
            try:
                job = self.host.store.import_file(result.output_path, {'profile': 'summary' if spec.get('summary') else 'general', 'titleLine': 35})
            except Exception as exc:
                job = None
                result.warnings.append('文件已保存，但加入工作台失败：' + str(exc))
            return result, job
        def complete(payload):
            result, job = payload
            self.last_output = result.output_path
            if job:
                self.host.active_id = job['id']
                self.host.refresh()
            self.result.setText('已生成：' + result.output_path.name)
            self.result.setToolTip(str(result.output_path))
            self.draft_state.setText('生成成功')
            self.host.statusBar().showMessage('档案已生成：' + str(result.output_path))
            if self.success_dialog:
                self.success_dialog.close()
            self.success_dialog = GeneratedDialog(result, self.host)
            self.success_dialog.open()
        self.host.run_task('正在生成并校验档案', work, complete)

    def open_output(self):
        if self.last_output:
            self.host.open_path(self.last_output)
