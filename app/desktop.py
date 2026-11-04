"""Native Python desktop client built exclusively with PySide6 Qt Widgets.

No HTTP service, browser, WebView, QtWebEngine or HTML interface is started.
All document work runs in background threads and uses the local Python engine.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import logging
import os
from pathlib import Path
import shutil
import sys
import traceback

from PySide6.QtCore import Qt, QObject, Signal, QRunnable, QThreadPool, QTimer, QUrl, QLockFile
from PySide6.QtGui import QIcon, QFont, QFontDatabase, QDesktopServices, QTextCursor, QTextBlockFormat, QTextCharFormat, QColor
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QGridLayout, QStackedWidget, QSplitter, QComboBox, QTableWidget,
    QTableWidgetItem, QHeaderView, QAbstractItemView, QTextEdit, QTabWidget,
    QFileDialog, QMessageBox, QDialog, QDialogButtonBox, QFormLayout, QSpinBox,
    QLineEdit, QProgressBar, QScrollArea, QSizePolicy,
)

from .engine import RULES, LABELS, FONTS, make_sample, DocumentError
from .storage import Store
from .platform import environment, resource_root
from .theme import STYLE
from .profiles import ProfileStore, standard_for
from .profile_ui import StandardsDialog
from .generation_ui import GenerationPage

VERSION = '2.2.0'
ROLE_CHOICES = {k: v for k, v in LABELS.items() if k not in ('blank', 'table', 'object')}


def label(text, name=None, wrap=False):
    w = QLabel(text)
    w.setTextFormat(Qt.TextFormat.PlainText)
    w.setWordWrap(wrap)
    if name:
        w.setObjectName(name)
    return w


def button(text, callback=None, primary=False, name=None):
    w = QPushButton(text)
    w.setCursor(Qt.CursorShape.PointingHandCursor)
    w.setProperty('primary', primary)
    if name:
        w.setObjectName(name)
    if callback:
        w.clicked.connect(callback)
    return w


def card():
    w = QFrame()
    w.setObjectName('card')
    layout = QVBoxLayout(w)
    layout.setContentsMargins(20, 18, 20, 18)
    layout.setSpacing(13)
    return w, layout


def table(headers):
    w = QTableWidget(0, len(headers))
    w.setHorizontalHeaderLabels(headers)
    w.verticalHeader().hide()
    w.setShowGrid(False)
    w.setAlternatingRowColors(True)
    w.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    w.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    w.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    w.horizontalHeader().setStretchLastSection(True)
    w.verticalHeader().setDefaultSectionSize(49)
    return w


def item(text, key=None):
    i = QTableWidgetItem(str(text))
    if key is not None:
        i.setData(Qt.ItemDataRole.UserRole, key)
    i.setToolTip(str(text))
    return i


class WorkerSignals(QObject):
    done = Signal(object)
    failed = Signal(str)
    finished = Signal()


class Worker(QRunnable):
    def __init__(self, fn):
        super().__init__()
        self.fn = fn
        self.signals = WorkerSignals()

    def run(self):
        try:
            self.signals.done.emit(self.fn())
        except Exception as exc:
            logging.exception('Document operation failed')
            self.signals.failed.emit(str(exc) or '操作未完成，请重试。')
        finally:
            self.signals.finished.emit()


class DropArea(QFrame):
    filesDropped = Signal(list)
    clicked = Signal()

    def __init__(self):
        super().__init__()
        self.setObjectName('dropArea')
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMinimumHeight(116)
        self.setMaximumHeight(142)
        self.setAccessibleName('拖入文件或点击添加档案')
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 20, 18, 20)
        main = label('＋  拖入档案，开始整理', 'section')
        sub = label('或点击选择文件  ·  支持 DOCX / DOC / WPS  ·  单份不超过 25 MB', 'muted')
        for w in (main, sub):
            w.setAlignment(Qt.AlignmentFlag.AlignCenter)
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            v.addWidget(w)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit()

    def keyPressEvent(self, event):
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Space):
            self.clicked.emit()
        else:
            super().keyPressEvent(event)

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls() and all(u.isLocalFile() for u in event.mimeData().urls()):
            event.acceptProposedAction()
            self.setProperty('dragging', True)
            self.style().unpolish(self)
            self.style().polish(self)

    def dragLeaveEvent(self, event):
        self.setProperty('dragging', False)
        self.style().unpolish(self)
        self.style().polish(self)

    def dropEvent(self, event):
        self.dragLeaveEvent(event)
        self.filesDropped.emit([u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()])
        event.acceptProposedAction()


class SettingsDialog(QDialog):
    def __init__(self, options, parent):
        super().__init__(parent)
        self.setWindowTitle('档案检查设置')
        self.resize(460, 280)
        self.options = dict(options)
        v = QVBoxLayout(self)
        v.setContentsMargins(25, 23, 25, 23)
        v.setSpacing(18)
        form = QFormLayout()
        self.profile = QComboBox()
        self.profiles = parent.profiles
        for key, name in self.profiles.choices().items():
            self.profile.addItem(name, key)
        if options.get('standard') and options.get('profile') not in self.profiles.choices():
            self.profile.addItem(options['standard']['name'] + '（记录快照）', options['profile'])
        self.profile.setCurrentIndex(max(0, self.profile.findData(options.get('profile', 'general'))))
        self.line = QSpinBox()
        self.line.setRange(33, 36)
        self.line.setValue(options.get('titleLine', 35))
        self.line.setSuffix(' 磅')
        self.profile.currentIndexChanged.connect(lambda: self.line.setEnabled(self.profile.currentData() in ('general', 'summary')))
        self.line.setEnabled(self.profile.currentData() in ('general', 'summary'))
        form.addRow('适用规范', self.profile)
        form.addRow('主标题固定行距', self.line)
        v.addLayout(form)
        v.addWidget(label('内置规范标题行距 33–36 磅；自定义规范采用其保存的文本与版面参数。保存后从原始副本重新检查，需再次修正以生成最新导出文件。', 'muted', True))
        buttons = QDialogButtonBox()
        buttons.addButton('取消', QDialogButtonBox.ButtonRole.RejectRole)
        buttons.addButton('保存并重新检查', QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def result_options(self):
        key = self.profile.currentData()
        if key not in self.profiles.choices() and self.options.get('standard'):
            return dict(self.options)
        result = self.profiles.options(key, self.line.value())
        if 'roles' in self.options:
            result['roles'] = self.options['roles']
        return result


class ParagraphDialog(QDialog):
    def __init__(self, job, parent):
        super().__init__(parent)
        self.setWindowTitle('段落识别与结构预览')
        self.resize(1080, 730)
        self.job = job
        self.roles = dict(job['options'].get('roles', {}))
        v = QVBoxLayout(self)
        v.setContentsMargins(22, 20, 22, 20)
        v.setSpacing(15)
        v.addWidget(label('逐段确认标题、正文与落款类型', 'section'))
        v.addWidget(label('这是原生文字与结构预览，图片、表格及最终分页请在 Word / WPS 中核对。', 'muted', True))
        splitter = QSplitter(Qt.Orientation.Horizontal)
        self.rows = table(['段', '类型', '原始文字'])
        self.rows.setColumnWidth(0, 42)
        self.rows.setColumnWidth(1, 150)
        self.rows.setMinimumWidth(390)
        paragraphs = job['report']['paragraphs']
        self.rows.setRowCount(len(paragraphs))
        for row, p in enumerate(paragraphs):
            self.rows.setItem(row, 0, item(p['index'] + 1))
            self.rows.setItem(row, 2, item(p['text']))
            if p['role'] in ('blank', 'table', 'object'):
                self.rows.setItem(row, 1, item(p['label']))
            else:
                combo = QComboBox()
                combo.setAccessibleName(f"第 {p['index'] + 1} 段类型")
                for key, title in ROLE_CHOICES.items():
                    combo.addItem(title, key)
                chosen = self.roles.get(str(p['index']), p['role'])
                combo.setCurrentIndex(combo.findData(chosen))
                combo.currentIndexChanged.connect(lambda _, c=combo, index=p['index']: self.change_role(index, c.currentData()))
                self.rows.setCellWidget(row, 1, combo)
        self.paper = QTextEdit()
        self.paper.setReadOnly(True)
        self.paper.setAccessibleName('段落结构示意')
        self.paper.document().setDocumentMargin(35)
        splitter.addWidget(self.rows)
        splitter.addWidget(self.paper)
        splitter.setSizes([480, 520])
        v.addWidget(splitter, 1)
        self.rows.currentCellChanged.connect(lambda row, *_: self.highlight_preview(row))
        controls = QDialogButtonBox()
        controls.addButton('关闭', QDialogButtonBox.ButtonRole.RejectRole)
        controls.addButton('保存识别并重新检查', QDialogButtonBox.ButtonRole.AcceptRole)
        controls.accepted.connect(self.accept)
        controls.rejected.connect(self.reject)
        v.addWidget(controls)
        self.render_paper()

    def change_role(self, index, role):
        self.roles[str(index)] = role
        self.render_paper()

    def render_paper(self):
        self.paper.clear()
        cursor = self.paper.textCursor()
        standard = standard_for(self.job['options'])
        for i, p in enumerate(self.job['report']['paragraphs']):
            if i:
                cursor.insertBlock()
            role = self.roles.get(str(p['index']), p['role'])
            block = QTextBlockFormat()
            block.setTopMargin(0)
            block.setBottomMargin(9)
            block.setLineHeight(150, QTextBlockFormat.LineHeightTypes.ProportionalHeight.value)
            target = standard['roles'].get(role)
            font = QFont(target['font'] if target else 'Microsoft YaHei UI')
            font.setPointSizeF(target['size'] if target else 11)
            if target:
                block.setTextIndent(target['size'] * target['indent'])
                block.setAlignment({'center': Qt.AlignmentFlag.AlignHCenter, 'right': Qt.AlignmentFlag.AlignRight, 'left': Qt.AlignmentFlag.AlignLeft, 'both': Qt.AlignmentFlag.AlignJustify}[target['align']])
            elif role in ('title', 'subtitle'):
                block.setAlignment(Qt.AlignmentFlag.AlignHCenter)
            elif role in ('signature', 'date'):
                block.setAlignment(Qt.AlignmentFlag.AlignRight)
                block.setRightMargin(40)
            cursor.setBlockFormat(block)
            char = QTextCharFormat()
            char.setFont(font)
            char.setForeground(QColor('#26382b' if role not in ('table', 'object') else '#87927d'))
            cursor.setCharFormat(char)
            cursor.insertText(p['text'] or ' ')
        self.paper.moveCursor(QTextCursor.MoveOperation.Start)

    def highlight_preview(self, row):
        if row < 0:
            return
        block = self.paper.document().findBlockByNumber(row)
        if block.isValid():
            cursor = QTextCursor(block)
            self.paper.setTextCursor(cursor)
            self.paper.ensureCursorVisible()


class MainWindow(QMainWindow):
    def __init__(self, store):
        super().__init__()
        self.store = store
        self.profiles = ProfileStore(store.root)
        self.env = environment()
        self.active_id = None
        self.busy = False
        self._restoring_page = True
        self.pool = QThreadPool(self)
        self.pool.setMaxThreadCount(1)
        self.workers = []
        self.setWindowTitle('归档 · 档案格式助手')
        self.setWindowIcon(QIcon(str(resource_root() / 'assets' / 'app.ico')))
        self.resize(1320, 880)
        self.setMinimumSize(1050, 710)
        self.controls = []
        root = QWidget()
        self.setCentralWidget(root)
        h = QHBoxLayout(root)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(0)
        h.addWidget(self.build_sidebar())
        shell = QWidget()
        v = QVBoxLayout(shell)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        v.addWidget(self.build_toolbar())
        self.pages = QStackedWidget()
        self.pages.addWidget(self.build_workspace())
        self.pages.addWidget(self.build_rules())
        self.pages.addWidget(self.build_environment())
        self.pages.addWidget(self.build_history())
        self.generation = GenerationPage(self)
        self.pages.addWidget(self.generation)
        preferred_page = self.generation.library.preferences.get('lastPage', 4 if self.generation.catalog else 0)
        v.addWidget(self.pages, 1)
        h.addWidget(shell, 1)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)
        self.progress.setMaximumWidth(170)
        self.progress.setMaximumHeight(6)
        self.progress.hide()
        self.statusBar().addPermanentWidget(self.progress)
        self.statusBar().showMessage('本机处理 · 原始文件保留 · Python 原生桌面版')
        self.refresh()
        self.refresh_environment()
        self._restoring_page = False
        self.navigate(preferred_page if isinstance(preferred_page, int) and 0 <= preferred_page < self.pages.count() else 0)

    def add_control(self, control):
        self.controls.append(control)
        return control

    def build_sidebar(self):
        side = QFrame()
        side.setObjectName('sidebar')
        side.setFixedWidth(208)
        v = QVBoxLayout(side)
        v.setContentsMargins(20, 32, 20, 24)
        v.setSpacing(9)
        v.addWidget(label('▰ 归档', 'brand'))
        v.addWidget(label('ARCHIVE STUDIO', 'brandSub'))
        v.addSpacing(30)
        v.addWidget(label('办公室工作空间', 'muted'))
        v.addSpacing(8)
        self.nav = []
        for index, title in enumerate(['格式工作台', '档案规范', '兼容与字体', '处理记录', '档案生成']):
            b = button(title, lambda _, i=index: self.navigate(i), name='nav')
            b.setCheckable(True)
            self.nav.append(b)
            v.addWidget(b)
        v.addStretch()
        v.addWidget(label('专注内容\n让格式回归秩序', 'section', True))
        v.addSpacing(13)
        v.addWidget(label('为团委 · 学生会办公室而作', 'muted', True))
        v.addSpacing(28)
        v.addWidget(label('●  原生桌面 · 本机处理', 'muted'))
        v.addWidget(label('Python / PySide6', 'brandSub'))
        return side

    def build_toolbar(self):
        frame = QFrame()
        frame.setObjectName('toolbar')
        h = QHBoxLayout(frame)
        h.setContentsMargins(27, 15, 27, 15)
        self.crumb = label('工作空间  /  格式工作台', 'muted')
        h.addWidget(self.crumb)
        h.addStretch()
        h.addWidget(label('DESKTOP ' + VERSION, 'eyebrow'))
        h.addSpacing(12)
        h.addWidget(button('档案生成', lambda: self.navigate(4), name='link'))
        h.addSpacing(12)
        h.addWidget(button('使用指南', self.guide, name='link'))
        return frame

    def page(self, headline, description):
        w = QWidget()
        v = QVBoxLayout(w)
        v.setContentsMargins(28, 23, 28, 23)
        v.setSpacing(16)
        v.addWidget(label(headline, 'headline'))
        v.addWidget(label(description, 'muted', True))
        return w, v

    def build_workspace(self):
        w, v = self.page('好格式，从这里开始', '依据团委与学生会档案规范，直接检查并修正本机文档')
        stats = QHBoxLayout()
        stats.setSpacing(13)
        self.stat_numbers = []
        for i, title in enumerate(['待处理文件', '可自动修正', '需要人工核对']):
            c, cv = card()
            c.setObjectName('statCard')
            cv.setContentsMargins(19, 12, 19, 12)
            cv.setSpacing(2)
            cv.addWidget(label(title, 'muted'))
            n = label('00', 'amberNumber' if i == 2 else 'statNumber')
            self.stat_numbers.append(n)
            cv.addWidget(n)
            stats.addWidget(c)
        v.addLayout(stats)
        toolbar = QHBoxLayout()
        self.profile = QComboBox()
        self.profile.setAccessibleName('档案规范类型')
        self.refresh_profiles()
        self.profile.setMinimumWidth(220)
        toolbar.addWidget(self.profile)
        toolbar.addWidget(self.add_control(button('管理规范…', self.manage_profiles)))
        toolbar.addStretch()
        self.demo_button = self.add_control(button('体验示例', self.demo))
        toolbar.addWidget(self.demo_button)
        toolbar.addWidget(self.add_control(button('添加文件…', self.choose_files, True)))
        v.addLayout(toolbar)
        self.drop = DropArea()
        self.drop.clicked.connect(self.choose_files)
        self.drop.filesDropped.connect(self.import_files)
        v.addWidget(self.drop)
        split = QSplitter(Qt.Orientation.Horizontal)
        left, lv = card()
        lv.setContentsMargins(15, 15, 15, 13)
        header = QHBoxLayout()
        header.addWidget(label('档案处理清单', 'section'))
        header.addStretch()
        self.queue_count = label('0 份', 'muted')
        header.addWidget(self.queue_count)
        lv.addLayout(header)
        self.queue = table(['档案名称', '格式问题', '状态'])
        self.queue.setAccessibleName('档案处理清单')
        self.queue.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.queue.setColumnWidth(1, 78)
        self.queue.setColumnWidth(2, 110)
        self.queue.itemSelectionChanged.connect(self.select_queue)
        self.queue.itemDoubleClicked.connect(lambda _: self.paragraphs())
        lv.addWidget(self.queue, 1)
        bottom = QHBoxLayout()
        bottom.addWidget(self.add_control(button('批量修正', self.fix_all)))
        bottom.addWidget(self.add_control(button('打包导出…', self.export_bundle)))
        bottom.addStretch()
        lv.addLayout(bottom)
        split.addWidget(left)
        right, rv = card()
        right.setMinimumWidth(350)
        rv.setContentsMargins(16, 15, 16, 15)
        self.detail_name = label('选择一份档案查看检查结果', 'section', True)
        rv.addWidget(self.detail_name)
        self.detail_meta = label('字体、段落、版面与归档提示', 'muted', True)
        rv.addWidget(self.detail_meta)
        self.fix_button = self.add_control(button('一键修正格式', self.fix_current, True))
        rv.addWidget(self.fix_button)
        row = QHBoxLayout()
        row.addWidget(self.add_control(button('段落识别', self.paragraphs)))
        row.addWidget(self.add_control(button('检查设置', self.settings)))
        rv.addLayout(row)
        self.issue_tabs = QTabWidget()
        self.auto_issues = self.issue_table()
        self.manual_issues = self.issue_table()
        self.issue_tabs.addTab(self.auto_issues, '格式问题')
        self.issue_tabs.addTab(self.manual_issues, '人工核对')
        rv.addWidget(self.issue_tabs, 1)
        actions = QGridLayout()
        actions.addWidget(self.add_control(button('导出 DOCX…', self.export_current)), 0, 0)
        actions.addWidget(self.add_control(button('生成 PDF…', self.export_pdf)), 0, 1)
        actions.addWidget(self.add_control(button('检查报告…', self.export_report)), 1, 0)
        actions.addWidget(self.add_control(button('打开原始副本', self.open_original)), 1, 1)
        rv.addLayout(actions)
        split.addWidget(right)
        split.setSizes([520, 450])
        v.addWidget(split, 1)
        v.addWidget(label('原文件保留，修正结果另存为 DOCX。内容、附件、落款、印章及最终分页需人工核对。', 'muted', True))
        return w

    def issue_table(self):
        w = table(['检查项目', '规范要求'])
        w.setWordWrap(True)
        w.setColumnWidth(0, 120)
        w.verticalHeader().setDefaultSectionSize(67)
        return w

    def build_rules(self):
        w, v = self.page('规范，有据可循', '查看内置要求，或添加适合自己的文本格式规范')
        row = QHBoxLayout()
        row.addWidget(button('查看本机格式规范…', lambda: self.open_reference('rules.pdf')))
        row.addWidget(button('查看本机考核方案…', lambda: self.open_reference('assessment.docx')))
        row.addWidget(self.add_control(button('我的格式规范…', self.manage_profiles, True)))
        row.addStretch()
        v.addLayout(row)
        c, cv = card()
        t = table(['规则项目', '格式要求', '处理方式'])
        t.setWordWrap(True)
        t.setRowCount(len(RULES))
        t.setColumnWidth(0, 155)
        t.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        t.setColumnWidth(2, 140)
        for r, rule in enumerate(RULES):
            t.setItem(r, 0, item(rule['name'] + '\n' + rule['group']))
            t.setItem(r, 1, item(rule['value'] + '\n依据：' + rule['source']))
            t.setItem(r, 2, item('自动检查与修正' if rule['auto'] else '人工核对'))
        t.verticalHeader().setDefaultSectionSize(76)
        cv.addWidget(t)
        v.addWidget(c, 1)
        v.addWidget(label('考核构成：内容完整性 30 分 · 数据真实与分析 25 分 · 材料格式 15 分 · 逻辑结构 10 分 · 创新与特色 20 分。\n应用不自动评定正式考核得分；“可自动问题归零”不代表全部档案要求均已满足。', 'muted', True))
        return w

    def build_environment(self):
        w, v = self.page('在 Word，也在 WPS', '检查本机排版组件与规范字体，减少跨软件打开时的格式差异')
        self.office_state = label('', 'status', True)
        v.addWidget(self.office_state)
        v.addWidget(label('DOCX 检查与修正不依赖 Office。旧版 DOC / WPS 转换、PDF 导出需本机可用的 Office 自动化组件。', 'muted', True))
        c, cv = card()
        self.fonts = table(['字体名称', '应用内预览', 'Windows 安装状态'])
        self.fonts.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.fonts.setColumnWidth(1, 265)
        self.fonts.setColumnWidth(2, 160)
        self.fonts.verticalHeader().setDefaultSectionSize(65)
        cv.addWidget(self.fonts)
        v.addWidget(c, 1)
        row = QHBoxLayout()
        row.addWidget(self.add_control(button('重新检测', self.detect_environment)))
        row.addWidget(button('另存选中的字体…', self.save_font))
        row.addWidget(button('打开字体文件', self.open_font))
        row.addStretch()
        v.addLayout(row)
        v.addWidget(label('开源版不随附字体。请使用你已取得使用权限的本机字体；安装后重启 Word / WPS 并重新检测。\n格式纠正保留字体名称；档案生成可选择嵌入允许嵌入的字体。不同软件及版本仍可能造成分页差异。', 'muted', True))
        return w

    def build_history(self):
        w, v = self.page('留存每一次整理', '文档副本、检查结果与修正记录保存在本机，可继续处理和导出')
        self.search = QLineEdit()
        self.search.setPlaceholderText('搜索档案名称…')
        self.search.textChanged.connect(self.filter_history)
        v.addWidget(self.search)
        c, cv = card()
        self.history = table(['档案名称', '处理时间', '状态', '格式问题', '人工核对'])
        self.history.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.history.itemChanged.connect(self.update_history_selection)
        self.history.itemSelectionChanged.connect(self.update_history_selection)
        self.history.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for i, width in [(1, 145), (2, 100), (3, 80), (4, 80)]:
            self.history.setColumnWidth(i, width)
        self.history.itemDoubleClicked.connect(lambda _: self.continue_history())
        cv.addWidget(self.history)
        v.addWidget(c, 1)
        row = QHBoxLayout()
        row.addWidget(self.add_control(button('继续处理', self.continue_history, True)))
        row.addWidget(self.add_control(button('全选当前结果', self.select_all_history)))
        row.addWidget(self.add_control(button('取消选择', self.clear_history_selection)))
        self.delete_history_button = self.add_control(button('删除所选记录', self.remove_history))
        self.delete_history_button.setProperty('danger', True)
        row.addWidget(self.delete_history_button)
        row.addWidget(button('打开记录目录', lambda: self.open_path(self.store.root)))
        row.addStretch()
        self.history_selected_label = label('已选择 0 份', 'muted')
        row.addWidget(self.history_selected_label)
        v.addLayout(row)
        v.addWidget(label('勾选记录，或用 Ctrl / Shift 多选 · 全选仅作用于当前搜索结果\n删除只清理应用内的副本与记录，原始文件及已导出文件保留', 'muted', True))
        return w

    def refresh_profiles(self, key=None):
        selected = key or self.profile.currentData()
        self.profile.clear()
        for code, title in self.profiles.choices().items():
            self.profile.addItem(title, code)
        self.profile.setCurrentIndex(max(0, self.profile.findData(selected)))

    def manage_profiles(self):
        if not self.busy:
            dialog = StandardsDialog(self.profiles, self)
            dialog.exec()
            self.refresh_profiles(dialog.key())

    def navigate(self, index):
        self.pages.setCurrentIndex(index)
        for i, b in enumerate(self.nav):
            b.setChecked(i == index)
        self.crumb.setText('工作空间  /  ' + self.nav[index].text())
        if not self._restoring_page and hasattr(self, 'generation'):
            self.generation.remember(lastPage=index)

    def job(self):
        return self.store.jobs.get(self.active_id)

    def selected_history_id(self):
        row = self.history.currentRow()
        return self.history.item(row, 0).data(Qt.ItemDataRole.UserRole) if row >= 0 and self.history.item(row, 0) else None

    def refresh(self):
        jobs = list(reversed(list(self.store.jobs.values())))
        pending = sum(j['status'] != 'fixed' for j in jobs)
        reports = [j.get('after', j['report']) if j['status'] == 'fixed' else j['report'] for j in jobs]
        for widget, count in zip(self.stat_numbers, [pending, sum(r['autoCount'] for r in reports), sum(r['manualCount'] for r in reports)]):
            widget.setText(f'{count:02d}')
        self.queue_count.setText(f'{len(jobs)} 份')
        selected = self.active_id
        self.queue.blockSignals(True)
        checked = set(self.selected_history_ids())
        self.history.blockSignals(True)
        self.queue.setRowCount(len(jobs))
        self.history.setRowCount(len(jobs))
        for row, j in enumerate(jobs):
            report = j.get('after', j['report']) if j['status'] == 'fixed' else j['report']
            status = '格式已修正' if j['status'] == 'fixed' else '待修正'
            self.queue.setItem(row, 0, item(j['name'], j['id']))
            self.queue.setItem(row, 1, item(report['autoCount']))
            self.queue.setItem(row, 2, item(status))
            if j['id'] == selected:
                self.queue.selectRow(row)
            date = datetime.fromisoformat(j.get('fixedAt') or j['created']).strftime('%m-%d %H:%M')
            values = [j['name'], date, status, report['autoCount'], report['manualCount']]
            for col, value in enumerate(values):
                self.history.setItem(row, col, item(value, j['id'] if col == 0 else None))
            entry = self.history.item(row, 0)
            entry.setFlags(entry.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            entry.setCheckState(Qt.CheckState.Checked if j['id'] in checked else Qt.CheckState.Unchecked)
        self.queue.blockSignals(False)
        self.history.blockSignals(False)
        self.filter_history()
        self.refresh_detail()
        self.navigate(self.pages.currentIndex())

    def select_queue(self):
        row = self.queue.currentRow()
        if row >= 0 and self.queue.item(row, 0):
            self.active_id = self.queue.item(row, 0).data(Qt.ItemDataRole.UserRole)
            self.refresh_detail()

    def refresh_detail(self):
        j = self.job()
        for t in (self.auto_issues, self.manual_issues):
            t.setRowCount(0)
        if not j:
            self.detail_name.setText('选择一份档案查看检查结果')
            self.detail_meta.setText('支持真实 DOCX 文档检查与修正')
            self.fix_button.setEnabled(False)
            self.issue_tabs.setTabText(0, '格式问题')
            self.issue_tabs.setTabText(1, '人工核对')
            return
        report = j.get('after', j['report']) if j['status'] == 'fixed' else j['report']
        self.detail_name.setText(j['name'])
        self.detail_meta.setText(f"{report['paragraphCount']} 段文字 · {report['sectionCount']} 个节 · {report['tableCount']} 个表格" + ('\n已生成规范副本，原文校验通过。' if j['status'] == 'fixed' else ''))
        self.fix_button.setText('重新生成规范副本' if j['status'] == 'fixed' else '一键修正格式')
        self.fix_button.setEnabled(report['canFix'] and not self.busy)
        for auto, t in [(True, self.auto_issues), (False, self.manual_issues)]:
            issues = [i for i in report['issues'] if i['auto'] == auto]
            t.setRowCount(len(issues))
            for row, issue in enumerate(issues):
                t.setItem(row, 0, item(issue['label'] + '\n' + issue['location']))
                cell = item(issue['expected'])
                cell.setToolTip('检测：' + issue['actual'] + '\n要求：' + issue['expected'] + '\n依据：' + issue['source'])
                t.setItem(row, 1, cell)
        self.issue_tabs.setTabText(0, f"格式问题 {report['autoCount']}")
        self.issue_tabs.setTabText(1, f"人工核对 {report['manualCount']}")

    def run_task(self, title, fn, success=None):
        if self.busy:
            return
        self.busy = True
        self.progress.show()
        self.statusBar().showMessage(title + '…')
        for control in self.controls:
            control.setEnabled(False)
        self.drop.setEnabled(False)
        worker = Worker(fn)
        self.workers.append(worker)
        if success:
            worker.signals.done.connect(success)
        worker.signals.failed.connect(self.error)
        worker.signals.finished.connect(lambda w=worker: self.task_finished(w))
        self.pool.start(worker)

    def task_finished(self, worker):
        if worker in self.workers:
            self.workers.remove(worker)
        self.busy = False
        self.progress.hide()
        for control in self.controls:
            control.setEnabled(True)
        self.drop.setEnabled(True)
        self.refresh_detail()

    def error(self, message):
        self.statusBar().showMessage('处理未完成，原始文件保留。')
        QMessageBox.warning(self, '处理提示', message)

    def need_job(self, fixed=False):
        if self.busy:
            return None
        j = self.job()
        if not j:
            self.statusBar().showMessage('请先选择一份档案。')
            return None
        if fixed and j['status'] != 'fixed':
            QMessageBox.information(self, '请先修正格式', '完成格式修正后，即可导出规范副本或 PDF。')
            return None
        return j

    def choose_files(self):
        if self.busy:
            return
        files, _ = QFileDialog.getOpenFileNames(self, '添加待整理的档案', '', '文字文档 (*.docx *.doc *.wps)')
        if files:
            self.import_files(files)

    def import_files(self, files):
        if self.busy or not files:
            return
        options = self.profiles.options(self.profile.currentData())
        def work():
            jobs, errors = [], []
            for file in files:
                try:
                    if not Path(file).is_file():
                        raise DocumentError('请选择文件，暂不支持文件夹导入。')
                    jobs.append(self.store.import_file(file, options.copy()))
                except Exception as exc:
                    errors.append(Path(file).name + '：' + str(exc))
            return jobs, errors
        def complete(result):
            jobs, errors = result
            if jobs:
                self.active_id = jobs[-1]['id']
            self.navigate(0)
            self.refresh()
            self.statusBar().showMessage(f'已检查 {len(jobs)} 份档案。')
            if errors:
                self.error('\n\n'.join(errors))
        self.run_task('正在导入并检查档案', work, complete)

    def demo(self):
        options = self.profiles.options(self.profile.currentData())
        def complete(j):
            self.active_id = j['id']
            self.refresh()
            self.statusBar().showMessage('示例已载入，可以体验段落识别、格式修正和文件导出。')
        self.run_task('正在准备体验示例', lambda: self.store.create('办公室工作总结-示例.docx', make_sample(), options, True), complete)

    def fix_current(self):
        j = self.need_job()
        if not j:
            return
        def complete(_):
            self.refresh()
            self.issue_tabs.setCurrentIndex(1)
            self.statusBar().showMessage('规范副本已生成，原文完整性校验通过。')
        self.run_task('正在修正档案格式', lambda: self.store.fix(j['id']), complete)

    def fix_all(self):
        jobs = [j for j in self.store.jobs.values() if j['status'] != 'fixed']
        if not jobs:
            self.statusBar().showMessage('没有待修正文件，可导出已规范的档案。')
            return
        def work():
            errors = []
            count = 0
            for j in jobs:
                try:
                    self.store.fix(j['id'])
                    count += 1
                except Exception as exc:
                    errors.append(j['name'] + '：' + str(exc))
            return count, errors
        def complete(result):
            count, errors = result
            self.refresh()
            self.statusBar().showMessage(f'已修正 {count} 份档案。')
            if errors:
                self.error('\n\n'.join(errors))
        self.run_task('正在批量修正档案', work, complete)

    def settings(self):
        j = self.need_job()
        if not j:
            return
        dialog = SettingsDialog(j['options'], self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reanalyze(j, dialog.result_options())

    def paragraphs(self):
        j = self.need_job()
        if not j:
            return
        dialog = ParagraphDialog(j, self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self.reanalyze(j, {**j['options'], 'roles': dialog.roles})

    def reanalyze(self, j, options):
        def complete(_):
            self.refresh()
            self.issue_tabs.setCurrentIndex(0)
            self.statusBar().showMessage('识别与设置已更新，请重新修正以生成最新规范副本。')
        self.run_task('正在重新检查档案', lambda: self.store.analyze(j['id'], options), complete)

    def default_export(self, j, suffix):
        return str(Path.home() / 'Desktop' / (Path(j['name']).stem + '-已规范' + suffix))

    def export_current(self):
        j = self.need_job(True)
        if not j:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出规范 DOCX（保留原始文件）', self.default_export(j, '.docx'), 'Word 文档 (*.docx)')
        if path:
            self.export_to(j['id'], path if path.lower().endswith('.docx') else path + '.docx', 'docx')

    def export_report(self):
        j = self.need_job()
        if not j:
            return
        path, _ = QFileDialog.getSaveFileName(self, '导出检查与修改清单', self.default_export(j, '-检查报告.txt'), '文本文件 (*.txt)')
        if path:
            self.export_to(j['id'], path if path.lower().endswith('.txt') else path + '.txt', 'report')

    def export_to(self, key, path, kind):
        self.run_task('正在导出文件', lambda: self.store.export_file(key, path, kind), lambda result: self.statusBar().showMessage('已导出：' + result))

    def export_bundle(self):
        keys = [j['id'] for j in self.store.jobs.values() if j['status'] == 'fixed']
        if not keys:
            self.statusBar().showMessage('请先修正至少一份档案。')
            return
        path, _ = QFileDialog.getSaveFileName(self, '打包导出规范文件与报告', str(Path.home() / 'Desktop' / '归档-规范文件与报告.zip'), 'ZIP 压缩文件 (*.zip)')
        if path:
            path = path if path.lower().endswith('.zip') else path + '.zip'
            self.run_task('正在打包导出', lambda: self.store.export_bundle(keys, path), lambda result: self.statusBar().showMessage('已导出：' + result))

    def export_pdf(self):
        j = self.need_job(True)
        if not j:
            return
        if not self.env['office']:
            QMessageBox.information(self, '需要本机 Office 组件', 'PDF 导出需要可用的 Word 或 WPS 自动化组件。也可先导出 DOCX，在原软件中另存为 PDF。')
            return
        dialog = QDialog(self)
        dialog.setWindowTitle('生成 PDF 打印版')
        dialog.resize(460, 270)
        v = QVBoxLayout(dialog)
        v.setContentsMargins(24, 22, 24, 22)
        v.setSpacing(16)
        v.addWidget(label('选择本机排版引擎', 'section'))
        combo = QComboBox()
        for office in self.env['office']:
            combo.addItem(office['name'], office['id'])
        v.addWidget(combo)
        text = 'PDF 从已修正的 DOCX 生成。导出后请核对字体、图片、印章与分页。'
        if any(f.get('required') and not f['installed'] for f in self.env['fonts']):
            text += '\n\n当前检测到规范字体缺失，建议先补齐字体。'
        v.addWidget(label(text, 'muted', True))
        controls = QDialogButtonBox()
        controls.addButton('取消', QDialogButtonBox.ButtonRole.RejectRole)
        controls.addButton('选择位置并生成', QDialogButtonBox.ButtonRole.AcceptRole)
        controls.accepted.connect(dialog.accept)
        controls.rejected.connect(dialog.reject)
        v.addWidget(controls)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        path, _ = QFileDialog.getSaveFileName(self, '保存 PDF 打印版', self.default_export(j, '.pdf'), 'PDF 文件 (*.pdf)')
        if not path:
            return
        path = path if path.lower().endswith('.pdf') else path + '.pdf'
        application = combo.currentData()
        def work():
            self.store.generate_pdf(j['id'], application)
            return self.store.export_file(j['id'], path, 'pdf')
        self.run_task('正在调用本机 Office 生成 PDF', work, lambda result: self.statusBar().showMessage('PDF 已导出：' + result))

    def open_path(self, path):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).resolve()))):
            self.error('无法打开文件，请检查本机的默认文件关联。')

    def open_reference(self, name):
        path = resource_root() / 'assets/reference' / name
        if not path.is_file():
            types = 'PDF 文件 (*.pdf)' if name.endswith('.pdf') else 'Word 文档 (*.docx *.doc)'
            chosen, _ = QFileDialog.getOpenFileName(self, '选择你本机的规范原件（仅本机打开）', '', types)
            if not chosen:
                return
            path = Path(chosen)
        self.open_path(path)

    def open_original(self):
        j = self.need_job()
        if j:
            self.open_path(self.store.folder(j['id']) / 'original.docx')

    def refresh_environment(self):
        detected = [o['name'] for o in self.env['office']]
        self.office_state.setText('已检测到：' + (' / '.join(detected) if detected else '未检测到 Word / WPS 自动化组件') + '\n检测结果以实际转换是否成功为准。')
        self.fonts.setRowCount(len(self.env['fonts']))
        for row, f in enumerate(self.env['fonts']):
            title = f['name'] + ('（可选）' if not f.get('required') else '')
            self.fonts.setItem(row, 0, item(title))
            sample = item('档案 · 规范留存')
            sample.setFont(QFont(f['name'], 17))
            self.fonts.setItem(row, 1, sample)
            status = item('已安装' if f['installed'] else '未检测到')
            status.setForeground(QColor('#5b824b' if f['installed'] else '#ac874d'))
            self.fonts.setItem(row, 2, status)

    def detect_environment(self):
        def complete(result):
            self.env = result
            self.refresh_environment()
            self.statusBar().showMessage('本机 Office 与字体检测已更新。')
        self.run_task('正在检测本机环境', environment, complete)

    def selected_font(self):
        row = self.fonts.currentRow()
        if row < 0:
            self.statusBar().showMessage('请先选中需要的字体。')
            return None
        f = self.env['fonts'][row]
        if not f.get('file'):
            QMessageBox.information(self, '字体未随附', '开源版不分发字体。请从你已有的本机字体或有权使用的来源安装所需字体，再重新检测。')
            return None
        return f

    def save_font(self):
        f = self.selected_font()
        if not f:
            return
        path, _ = QFileDialog.getSaveFileName(self, '另存规范字体', str(Path.home() / 'Desktop' / (f['name'] + '.ttf')), 'TrueType 字体 (*.ttf)')
        if path:
            try:
                shutil.copyfile(resource_root() / 'assets/fonts' / f['file'], path)
                self.statusBar().showMessage('字体已另存。双击字体文件安装后，请重启 Word / WPS。')
            except OSError as exc:
                self.error(str(exc))

    def open_font(self):
        f = self.selected_font()
        if f:
            self.open_path(resource_root() / 'assets/fonts' / f['file'])

    def filter_history(self):
        text = self.search.text().strip().lower()
        for row in range(self.history.rowCount()):
            i = self.history.item(row, 0)
            self.history.setRowHidden(row, bool(text and i and text not in i.text().lower()))
        self.update_history_selection()

    def selected_history_ids(self):
        checked, selected = [], []
        rows = {i.row() for i in self.history.selectionModel().selectedRows()}
        for row in range(self.history.rowCount()):
            entry = self.history.item(row, 0)
            if not entry or self.history.isRowHidden(row):
                continue
            key = entry.data(Qt.ItemDataRole.UserRole)
            if entry.checkState() == Qt.CheckState.Checked:
                checked.append(key)
            if row in rows:
                selected.append(key)
        return checked or selected

    def update_history_selection(self, *_):
        if hasattr(self, 'history_selected_label'):
            self.history_selected_label.setText(f'已选择 {len(self.selected_history_ids())} 份')

    def select_all_history(self):
        self.history.blockSignals(True)
        for row in range(self.history.rowCount()):
            self.history.item(row, 0).setCheckState(Qt.CheckState.Unchecked if self.history.isRowHidden(row) else Qt.CheckState.Checked)
        self.history.blockSignals(False)
        self.update_history_selection()

    def clear_history_selection(self):
        self.history.clearSelection()
        self.history.blockSignals(True)
        for row in range(self.history.rowCount()):
            self.history.item(row, 0).setCheckState(Qt.CheckState.Unchecked)
        self.history.blockSignals(False)
        self.update_history_selection()

    def continue_history(self):
        key = self.selected_history_id()
        if key:
            self.active_id = key
            self.navigate(0)
            self.refresh()

    def remove_history(self):
        keys = self.selected_history_ids()
        if self.busy:
            return
        if not keys:
            self.statusBar().showMessage('请先勾选或选中要删除的记录')
            return
        result = QMessageBox.question(self, '批量删除本机记录', f'删除所选 {len(keys)} 份档案在本应用中的副本与记录？\n\n原始文件与已导出文件保留', QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if result == QMessageBox.StandardButton.Yes:
            def complete(_):
                if self.active_id in keys:
                    self.active_id = None
                self.refresh()
                pending = self.store.pending_deletions
                self.statusBar().showMessage(f'已删除 {len(keys)} 份本机记录' + (f'，{pending} 份副本被占用，将在下次启动时重试清理' if pending else ''))
            self.run_task('正在清理本机记录', lambda: self.store.remove_many(keys), complete)

    def guide(self):
        QMessageBox.information(self, '归档 · 原生 Python 桌面版', '1. 添加或拖入 DOCX / DOC / WPS 文件。\n\n2. 在“段落识别”中核对主标题、层级、正文与落款。\n\n3. 一键修正格式，导出规范 DOCX 与完整检查报告。\n\n4. 补齐规范字体后，可通过本机 Word / WPS 生成 PDF。\n\n文档始终在本机处理，不覆盖原始文件。\n关闭窗口即可退出程序，无后台网页服务。')

    def closeEvent(self, event):
        if self.busy:
            QMessageBox.information(self, '正在处理文件', '后台正在处理档案，请等待当前操作完成后关闭。')
            event.ignore()
        else:
            if not self.generation.save_draft():
                self.error('本机草稿未保存，请检查磁盘空间或目录权限后重试关闭')
                event.ignore()
                return
            event.accept()


def main():
    parser = argparse.ArgumentParser(description='归档 · 原生 Python 档案格式助手')
    parser.add_argument('--data-dir', help='自定义本机记录目录')
    parser.add_argument('--smoke-test', metavar='JSON', help=argparse.SUPPRESS)
    args = parser.parse_args()
    app = QApplication([sys.argv[0]])
    # Some headless/offscreen Windows environments expose no system fonts.
    # Load the existing Windows UI font privately without installing anything.
    if os.name == 'nt' and 'Microsoft YaHei UI' not in QFontDatabase.families():
        ui_font = Path(os.environ.get('WINDIR', 'C:/Windows')) / 'Fonts/msyh.ttc'
        if ui_font.is_file():
            QFontDatabase.addApplicationFont(str(ui_font))
    app.setApplicationName('归档')
    app.setOrganizationName('ArchiveStudio')
    app.setApplicationVersion(VERSION)
    app.setStyle('Fusion')
    app.setFont(QFont('Microsoft YaHei UI', 10))
    app.setStyleSheet(STYLE)
    root = Path(args.data_dir) if args.data_dir else (Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'ArchiveStudio/records' if getattr(sys, 'frozen', False) else resource_root() / '.local_data')
    root.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=root / 'application.log', encoding='utf-8', level=logging.WARNING)
    lock = QLockFile(str(root / 'desktop.lock'))
    lock.setStaleLockTime(30000)
    if not lock.tryLock(100):
        QMessageBox.information(None, '归档已在运行', '此记录目录已有归档窗口在运行，请切换到已打开的窗口。')
        return 0
    for font in (resource_root() / 'assets/fonts').glob('*.ttf'):
        QFontDatabase.addApplicationFont(str(font))
    window = MainWindow(Store(root))
    window.show()
    if args.smoke_test:
        from .smoke import run_smoke_test
        QTimer.singleShot(100, lambda: run_smoke_test(window, Path(args.smoke_test)))
    code = app.exec()
    lock.unlock()
    return code
