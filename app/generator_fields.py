"""Native form editors matching the source generator's point/task model."""
from datetime import date
import re
from PySide6.QtCore import Qt, Signal, QRegularExpression
from PySide6.QtGui import QRegularExpressionValidator, QPainter, QPen, QColor
from PySide6.QtWidgets import (QWidget, QFrame, QLabel, QPushButton, QVBoxLayout,
    QHBoxLayout, QLineEdit, QTextEdit, QComboBox)


def action(text, callback, primary=False):
    button = QPushButton(text)
    button.setProperty('primary', primary)
    if callback:
        button.clicked.connect(callback)
    return button


def visible_length(value):
    if isinstance(value, dict):
        return sum(visible_length(item) for item in value.values())
    if isinstance(value, list):
        return sum(visible_length(item) for item in value)
    return len(re.sub(r'\s+', '', str(value)))


class FormTextEdit(QTextEdit):
    def __init__(self, rows=3):
        super().__init__()
        self.setAcceptRichText(False)
        self.setFixedHeight(max(74, min(rows, 12) * 23 + 30))
        self.setTabChangesFocus(True)

    def wheelEvent(self, event):
        if self.verticalScrollBar().maximum() == 0:
            event.ignore()
        else:
            super().wheelEvent(event)


class FormComboBox(QComboBox):
    def __init__(self):
        super().__init__()
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor('#6b8160' if self.isEnabled() else '#afb8a8'), 1.5))
        x, y = self.width() - 17, self.height() // 2
        painter.drawLine(x - 4, y - 2, x, y + 2)
        painter.drawLine(x, y + 2, x + 4, y - 2)

    def wheelEvent(self, event):
        # Scrolling the form must not silently change a document setting.
        event.ignore()


class NumberEntry(QLineEdit):
    def __init__(self, value='', amount=False, digits=None):
        super().__init__(str(value))
        self.amount = amount
        self.setValidator(QRegularExpressionValidator(QRegularExpression('[0-9,]*' if amount else '[0-9]*'), self))
        if digits:
            self.setMaxLength(int(digits))
        self.editingFinished.connect(self.format_amount)

    def format_amount(self):
        value = self.text().replace(',', '').strip()
        if self.amount and value.isdigit():
            self.setText(f'{int(value):,}')


class DateEntry(QWidget):
    changed = Signal()

    def __init__(self, value=''):
        super().__init__()
        row = QHBoxLayout(self)
        row.setContentsMargins(0, 0, 0, 0)
        self.input = QLineEdit(str(value))
        self.input.setPlaceholderText('YYYY-MM-DD，例如 2026-11-04')
        self.input.setMaxLength(10)
        self.input.textChanged.connect(self.changed)
        row.addWidget(self.input, 1)
        self.today_button = action('今天', lambda: self.input.setText(date.today().isoformat()))
        row.addWidget(self.today_button)
        self.setFocusProxy(self.input)

    def value(self):
        return self.input.text()

    def set_value(self, value):
        self.input.setText(str(value))


class PointsEditor(QWidget):
    changed = Signal()

    def __init__(self, maximum=20):
        super().__init__()
        self.maximum = maximum
        self.entries = []
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.rows.setSpacing(8)
        self.add_button = action('＋ 添加一条', self.add)
        self.count = QLabel()
        self.count.setObjectName('muted')
        bottom = QHBoxLayout()
        bottom.addWidget(self.add_button)
        bottom.addWidget(self.count)
        bottom.addStretch()
        self.rows.addLayout(bottom)
        self.add()

    def add(self, checked=False, value='', restoring=False):
        if len(self.entries) >= self.maximum and not restoring:
            return
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        number = QLabel()
        number.setObjectName('muted')
        number.setFixedWidth(48)
        layout.addWidget(number, 0, Qt.AlignmentFlag.AlignTop)
        entry = FormTextEdit(2)
        entry.setPlaceholderText('填写这一条内容，编号会自动生成')
        entry.setPlainText(str(value))
        layout.addWidget(entry, 1)
        remove = action('删除', lambda: self.remove(row))
        layout.addWidget(remove, 0, Qt.AlignmentFlag.AlignTop)
        self.entries.append((row, number, entry))
        self.rows.insertWidget(self.rows.count() - 1, row)
        entry.textChanged.connect(self.changed)
        self.renumber()
        self.changed.emit()

    def remove(self, row):
        if len(self.entries) == 1:
            self.entries[0][2].clear()
            return
        self.entries = [entry for entry in self.entries if entry[0] is not row]
        row.hide()
        self.rows.removeWidget(row)
        row.deleteLater()
        self.renumber()
        self.changed.emit()

    def renumber(self):
        for i, (_, number, entry) in enumerate(self.entries, 1):
            number.setText(f'第 {i} 条')
            entry.setAccessibleName(f'第 {i} 条内容')
        self.add_button.setEnabled(len(self.entries) < self.maximum)
        self.count.setText(f'{len(self.entries)} / {self.maximum} 条')

    def value(self):
        # Each editor is one point; embedded newlines remain part of that point.
        return [entry.toPlainText().strip() for _, _, entry in self.entries]

    def set_value(self, values):
        values = values if isinstance(values, list) else ([str(values)] if values else [])
        for row, _, _ in self.entries:
            row.hide()
            self.rows.removeWidget(row)
            row.deleteLater()
        self.entries = []
        for value in values or ['']:
            self.add(value=value, restoring=True)


class TaskGroups(QWidget):
    changed = Signal()

    def __init__(self, maximum=12):
        super().__init__()
        self.maximum = maximum
        self.groups = []
        self.rows = QVBoxLayout(self)
        self.rows.setContentsMargins(0, 0, 0, 0)
        self.add_button = action('＋ 添加一个任务', self.add)
        self.count = QLabel()
        self.count.setObjectName('muted')
        bottom = QHBoxLayout()
        bottom.addWidget(self.add_button)
        bottom.addWidget(self.count)
        bottom.addStretch()
        self.rows.addLayout(bottom)
        self.add()

    def add(self, checked=False, value=None, restoring=False):
        if len(self.groups) >= self.maximum and not restoring:
            return
        frame = QFrame()
        frame.setObjectName('taskCard')
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(16, 16, 16, 16)
        header = QHBoxLayout()
        title = QLabel()
        title.setObjectName('section')
        header.addWidget(title)
        header.addStretch()
        header.addWidget(action('删除此任务', lambda: self.remove(frame)))
        layout.addLayout(header)
        description = FormTextEdit(2)
        description.setPlaceholderText('任务内容')
        layout.addWidget(QLabel('任务内容'))
        layout.addWidget(description)
        goals, measures = PointsEditor(12), PointsEditor(20)
        layout.addWidget(QLabel('目标（按需添加）'))
        layout.addWidget(goals)
        layout.addWidget(QLabel('具体措施（按需添加）'))
        layout.addWidget(measures)
        self.groups.append((frame, title, description, goals, measures))
        self.rows.insertWidget(self.rows.count() - 1, frame)
        if value:
            description.setPlainText(str(value.get('description', '')))
            goals.set_value(value.get('goals', []))
            measures.set_value(value.get('measures', []))
        description.textChanged.connect(self.changed)
        goals.changed.connect(self.changed)
        measures.changed.connect(self.changed)
        self.renumber()
        self.changed.emit()

    def remove(self, frame):
        if len(self.groups) == 1:
            _, _, description, goals, measures = self.groups[0]
            description.clear()
            goals.set_value([])
            measures.set_value([])
            self.changed.emit()
            return
        self.groups = [group for group in self.groups if group[0] is not frame]
        frame.hide()
        self.rows.removeWidget(frame)
        frame.deleteLater()
        self.renumber()
        self.changed.emit()

    def renumber(self):
        for i, (_, title, _, _, _) in enumerate(self.groups, 1):
            title.setText(f'任务 {i}')
        self.add_button.setEnabled(len(self.groups) < self.maximum)
        self.count.setText(f'{len(self.groups)} / {self.maximum} 个任务')

    def value(self):
        return [dict(description=d.toPlainText(), goals=g.value(), measures=m.value()) for _, _, d, g, m in self.groups]

    def set_value(self, values):
        for frame, *_ in self.groups:
            frame.hide()
            self.rows.removeWidget(frame)
            frame.deleteLater()
        self.groups = []
        values = values if isinstance(values, list) else []
        for value in values or [{}]:
            self.add(value=value if isinstance(value, dict) else dict(description=str(value)), restoring=True)
