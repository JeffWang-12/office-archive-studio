# Third party components

归档原生桌面版使用以下运行时组件。发行包 `licenses` 目录保留可用的原始许可文本，组件源代码与许可证以各上游项目为准。

项目原创代码和原创说明文档以根目录 `LICENSE` 的 MIT License 开源。公开仓库及源码包不包含用户提供的字体、规范原件或包含这些资源的安装包。此许可不改变使用者自行配置的外部文件的许可或权利状态。

- **Python 3.12** — Python Software Foundation License。<https://www.python.org/>。发行包使用 PyInstaller 附带 Python 运行时。
- **Qt for Python / PySide6 Essentials / Shiboken6** — 安装包元数据声明 `LGPL-3.0-only OR GPL-2.0-only OR GPL-3.0-only`。<https://code.qt.io/pyside/pyside-setup>。Qt 库以发行目录内独立 DLL 形式提供，可在兼容条件下替换。
- **Qt 6** — Qt 各模块使用上游公布的许可。<https://code.qt.io/qt/>，<https://doc.qt.io/qt-6/licenses-used-in-qt.html>。本应用使用 Qt Core、Gui、Widgets，不使用 WebEngine。
- **lxml / libxml2 / libxslt** — lxml 为 BSD 许可，底层库许可见随附文本及 <https://lxml.de/>。
- **PyInstaller** — GPL-2.0-or-later with bootloader exception。<https://pyinstaller.org/>。仅用于打包和程序启动引导。

字体名称、格式参数和检测逻辑保留在程序中，字体文件和规范原件由使用者自行在本机配置。程序不自动安装字体，也不自动嵌入导出的 DOCX。方正公文楷体为可选字体，不替代规范要求的楷体_GB2312。

本项目源码及打包脚本与二进制包一并交付；源码不包含开发测试记录、用户导入的档案、Python 环境或网页界面。
