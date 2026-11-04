# 归档 Python 原生桌面版

面向团委、学生会办公室的 Windows 档案格式助手，使用 **Python + PySide6 Qt Widgets**。界面、文件拖拽、段落识别和导出对话框均为原生桌面控件。没有网页前端、本地 HTTP 服务、浏览器、WebView 或 QtWebEngine 依赖。

项目原创代码及原创说明文档采用 [MIT License](LICENSE) 开源。[GitHub 仓库](https://github.com/JeffWang-12/office-archive-studio)仅公开程序源码，字体、规范 PDF/Word 原件及包含它们的旧安装包不公开。第三方依赖保留各自许可，详见 [第三方说明](THIRD_PARTY_NOTICES.md)。

## 开源代码版 v2.1.0

公开版本只提供源码及源码压缩包，不附带字体或规范原件。没有这些文件也可运行、检查、修正和导出 DOCX；需要的排版字体由使用者自行在本机安装。

“档案规范”中的原件查看按钮会让使用者选择本机文件，仅在本机打开。字体、原始规范和生成模板资源目录均有 Git 忽略规则，公开源码打包也会排除这些本机资源。开源版可以通过“档案生成”导入自己的模板资源，或添加包含 `{{ 占位符 }}` 的 DOCX 模板。

## 从 Python 源码运行

建议 Windows 10/11 x64，Python 3.10–3.13 x64。在项目目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe main.py
```

也可双击 `运行源码.cmd`；已建虚拟环境时优先使用 `.venv`。

## 打包发布

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-build.txt -c requirements-lock.txt
powershell -ExecutionPolicy Bypass -File scripts/build.ps1 -Python .\.venv\Scripts\python.exe
```

默认生成适合分发的目录版、Windows 原生桌面压缩包和干净的 Python 源码压缩包，均位于 `release-native`。如需单文件，可增加 `-OneFile`；单文件首次运行需要解压 Qt 运行时。构建步骤不发布到互联网。

仅生成不含本机字体和规范原件的源码包：`python scripts/package_release.py --format source`。自行构建的安装包仅供本机使用或按自己的资源授权范围分发，本项目的公开发行页不上传这些安装包。

## 功能

- 批量导入 DOCX，以及通过本机 Word/WPS 转换旧版 DOC/WPS。
- 检查、修正字体、字号、固定行距、缩进、页边距和标准页码。
- 原生段落结构预览，可人工指定标题、正文、副标题、落款等类型。
- 原始文档保留，输出规范 DOCX、检查清单和 ZIP；通过本机 Office 生成 PDF。
- 本机字体环境检测、规范原件查阅、历史记录管理。
- 历史记录可勾选、Ctrl / Shift 多选、全选当前搜索结果并批量删除。
- 自定义文本格式规范：分别设置主标题、各级标题、正文、落款等的字体、字号、固定行距、缩进、对齐及纸张、页边距；支持 JSON 导入导出，记录保存规范快照。
- 原生档案生成页：年度 / 月份封皮、计划、总结、文化导航申报表七类模板；动态任务、目录和活动明细编辑、2–3 张照片排版、草稿自动保存和备份恢复、自定义模板识别。
- 按需嵌入允许嵌入的字体，遵循 OOXML 字体密钥字节序，缺失或禁止嵌入的字体会给出提示；保留模板字体名称。
- 后台线程处理，关闭窗口退出；同一数据目录使用文件锁避免重复实例。

DOCX 修正不依赖 Office。旧版转换和 PDF 导出需要可用的 Word/WPS 自动化组件。复杂页脚、附件、印章及内容质量需人工核对。WPS 暂未实机验证。

## 代码结构

| 文件 | 用途 |
| --- | --- |
| `main.py` | Python 桌面程序入口 |
| `app/desktop.py` | PySide6 原生窗口、对话框、后台任务 |
| `app/theme.py` | Qt 控件样式 |
| `app/storage.py` | 本机记录、导入、修正和导出 |
| `app/engine.py` | 真实 DOCX 格式检查、修正和内容校验 |
| `app/profiles.py`、`app/profile_ui.py` | 自定义文本规范与原生编辑器 |
| `app/generation.py`、`app/generation_ui.py`、`app/generator/` | 本机资源库、草稿、原生生成表单和 DOCX 生成 |
| `app/platform.py`、`scripts/office.ps1` | 字体检测、Office 转换 |
| `scripts/build.ps1` | Windows 打包入口 |
| `scripts/package_release.py` | 发行目录、源码包、依赖许可 |

验证：安装开发依赖后运行 `python -m unittest discover -s tests -v`。应用内原生流程测试使用 `python main.py --data-dir .build/qa-records --smoke-test .build/qa/result.json`；可设置 `QT_QPA_PLATFORM=offscreen` 在无桌面环境下运行。

规则、操作步骤和验证边界见 `docs`。打包参考 [Qt 官方部署说明](https://doc.qt.io/qtforpython-6/deployment/deployment-pyinstaller.html)；依赖声明见 `THIRD_PARTY_NOTICES.md`。
