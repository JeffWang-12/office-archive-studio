"""Qt Widgets styling. No browser, HTML renderer or web engine is used."""
STYLE = '''
QWidget { color: #34453c; font-family: "Microsoft YaHei UI", "Segoe UI"; font-size: 12px; }
QMainWindow, QDialog { background: #f5f7f3; }
QWidget#generatorForm { background: white; }
QFrame#sidebar { background: #fcfdfb; border-right: 1px solid #e0e6dc; }
QLabel#brand { color: #294d3e; font-size: 30px; font-weight: 650; }
QLabel#brandSub, QLabel#eyebrow { color: #8b956f; font-size: 10px; letter-spacing: 2px; }
QLabel#headline { color: #2b4134; font-size: 27px; font-weight: 600; }
QLabel#muted { color: #75836e; font-size: 11px; }
QLabel#section { font-size: 14px; font-weight: 600; color: #41573e; }
QLabel#statNumber { font-size: 28px; color: #3c6047; font-weight: 500; }
QLabel#amberNumber { font-size: 28px; color: #a08045; font-weight: 500; }
QLabel#status { color: #638056; padding: 8px 10px; background: #edf3e7; border-radius: 5px; }
QFrame#card { background: white; border: 1px solid #e0e6dc; border-radius: 9px; }
QFrame#statCard { background: white; border: 1px solid #e0e6dc; border-radius: 8px; }
QFrame#dropArea { background: #eff4e9; border: 1px dashed #adbe9c; border-radius: 8px; }
QFrame#dropArea[dragging="true"] { background: #e0ecd7; border: 2px dashed #668c53; }
QFrame#toolbar { background: #fbfcf9; border-bottom: 1px solid #e0e6dc; }
QPushButton { background: white; border: 1px solid #d6dfcf; border-radius: 5px; padding: 8px 14px; color: #58704b; }
QPushButton:hover { background: #eef4e7; border-color: #a9bd98; }
QPushButton:pressed { background: #e2ecd9; }
QPushButton:disabled { color: #adb6a5; background: #f0f2ed; border-color: #e4e8df; }
QPushButton[primary="true"] { background: #315746; color: #fff; border-color: #315746; font-weight: 600; }
QPushButton[primary="true"]:hover { background: #436b58; }
QPushButton[primary="true"]:disabled { background: #9daea0; border-color: #9daea0; color: #e9eee7; }
QPushButton#nav { text-align: left; padding: 13px 17px; background: transparent; border: 0; color: #6f8067; font-size: 13px; }
QPushButton#nav:checked { background: #315746; color: white; }
QPushButton#nav:hover:!checked { background: #edf2e8; }
QPushButton#link { color: #6c8659; background: transparent; border: 0; padding: 5px 2px; text-align: left; }
QPushButton[danger="true"] { color: #a65747; }
QComboBox, QLineEdit, QSpinBox, QDoubleSpinBox { background: white; border: 1px solid #d9e1d2; border-radius: 5px; padding: 7px 10px; selection-background-color: #d4e3c6; min-height: 16px; }
QComboBox:focus, QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { border-color: #8ba774; }
QComboBox::drop-down { border: 0; width: 24px; }
QComboBox QAbstractItemView { background: white; selection-background-color: #e4eddb; color: #34453c; }
QTableWidget, QTreeWidget, QListWidget { border: 0; background: white; alternate-background-color: #f9fbf6; selection-background-color: #e6efde; selection-color: #345131; outline: none; gridline-color: #edf0e8; }
QTableWidget::item, QTreeWidget::item { padding: 8px; border-bottom: 1px solid #eef1e9; }
QHeaderView::section { background: #f6f8f2; color: #7b8b6e; padding: 10px 8px; border: 0; border-bottom: 1px solid #e4e9dd; font-weight: 400; }
QTableCornerButton::section { background: #f6f8f2; border: 0; }
QTabWidget::pane { border: 1px solid #e2e7dc; border-radius: 6px; background: white; }
QTabBar::tab { padding: 10px 15px; color: #839376; background: #f1f4ec; border: 0; }
QTabBar::tab:selected { color: #426537; background: white; border-bottom: 2px solid #6c8d55; }
QTextEdit, QPlainTextEdit { background: white; border: 1px solid #e0e7d8; border-radius: 6px; padding: 15px; selection-background-color: #d9e6ce; }
QScrollArea { border: 0; background: transparent; }
QScrollBar:vertical { background: transparent; width: 8px; margin: 0; }
QScrollBar::handle:vertical { background: #ccd7c1; border-radius: 4px; min-height: 25px; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
QSplitter::handle { background: transparent; width: 12px; height: 12px; }
QSplitter::handle:hover { background: #e3ebdb; }
QProgressBar { border: 0; background: #e5ecdd; border-radius: 3px; height: 5px; text-align: center; }
QProgressBar::chunk { background: #72925d; border-radius: 3px; }
QStatusBar { background: #edf2e7; color: #6b7f5c; border-top: 1px solid #dfe7d7; }
QStatusBar::item { border: 0; }
QToolTip { background: #315746; color: white; border: 0; padding: 7px; }
QCheckBox { spacing: 7px; color: #748668; }
'''
