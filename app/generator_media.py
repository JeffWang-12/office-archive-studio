"""Native directory/activity grids and photo selection controls."""
from pathlib import Path
from PySide6.QtCore import Qt, Signal, QSize
from PySide6.QtGui import QPixmap, QImageReader
from PySide6.QtWidgets import (QWidget, QLabel, QVBoxLayout, QHBoxLayout, QListWidget,
    QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QFileDialog, QMessageBox)
from .generator_fields import action
from .generator.photo_guard import validate_photos

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
        self.table.setRowCount(1)

    def add(self):
        if self.table.rowCount() < self.maximum:
            self.table.insertRow(self.table.rowCount())
            self.changed.emit()

    def remove(self):
        for row in sorted({i.row() for i in self.table.selectionModel().selectedRows()}, reverse=True):
            self.table.removeRow(row)
        if not self.table.rowCount():
            self.table.setRowCount(1)
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
        if not self.table.rowCount():
            self.table.setRowCount(1)

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
        slots = QHBoxLayout()
        for index in range(3):
            slots.addWidget(action(f'照片 {index + 1}…', lambda _, i=index: self.choose_slot(i)))
        v.addLayout(slots)
        self.hint = QLabel('2–3 张不同照片 · 短边至少 300 像素 · 每张不超过 25 MB')
        self.hint.setWordWrap(True)
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

    def choose_slot(self, index):
        path, _ = QFileDialog.getOpenFileName(self, f'选择照片 {index + 1}', '', '图片 (*.png *.jpg *.jpeg *.bmp *.tif *.tiff *.webp *.gif)')
        if not path:
            return
        paths = self.value()
        if index < len(paths):
            paths[index] = path
        else:
            paths.append(path)
        try:
            validate_photos(paths)
            self.set_value(paths)
            self.list.setCurrentRow(min(index, len(paths) - 1))
            self.changed.emit()
        except ValueError as exc:
            QMessageBox.warning(self, '请检查照片', str(exc))

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
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.width() * size.height() > 50_000_000:
            self.preview.setText('图片过大，请更换')
            return
        reader.setScaledSize(size.scaled(QSize(320, 260), Qt.AspectRatioMode.KeepAspectRatio))
        pixmap = QPixmap.fromImage(reader.read())
        self.preview.setPixmap(pixmap.scaled(160, 130, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
