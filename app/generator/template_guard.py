"""Check shipped templates against the reviewed 2026—2027 release."""
import hashlib
import os
import shutil
import zipfile
import xml.etree.ElementTree as ET
from datetime import date
from pathlib import Path

from docxtpl import DocxTemplate

VERSION = "2026—2027 学年版"
VALID_THROUGH = date(2027, 7, 31)
HASHES = {
    "年度档案封皮.docx": "C0CCC2AE75136C595FA631C0189516AD56703AE7D4633527CBE63278ED90BB02",
    "年度工作计划.docx": "24AE88DD58DD4AD7BD6A563D98D95CC69E1FC1BA2477FE50443F697AE6AD0CDD",
    "年度工作总结.docx": "8237A98512D3D98131AB07DD045228231358E49E47D0E88AAA2C1C2E23B41875",
    "文化导航申报表.docx": "A54A88D62A86CB004095BD2B6002ABDC36F1CBB932535C1E7BAAC1826852933B",
    "月份档案封皮.docx": "D7940914B57425A2DCF9181168220485CCF5B511609FC20D1E86FCCF83AEA9D8",
    "月份工作计划.docx": "23D3B104D6D5171BE53159F29913FAB3191705B23F813CFBBD4513DF21F4E993",
    "月份工作总结.docx": "8C9844ECC9045F289879AD728CB5C4EEA5B43ADAC3767D2737BA4718A68AF0BF",
}


def version_is_outdated(today: date | None = None) -> bool:
    return (today or date.today()) > VALID_THROUGH


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest().upper()


def check_template(root: Path, path: Path) -> None:
    if not path.exists():
        raise ValueError(f"未找到模板“{path.name}”。标准模板可点击“恢复标准模板”。")
    if path.parent.resolve() == (root / "templates").resolve() and path.name in HASHES:
        if file_hash(path) != HASHES[path.name]:
            raise ValueError(f"标准模板“{path.name}”与{VERSION}不一致，请点击“恢复标准模板”。自定义样式请放入根目录“模板.docx”。")
    try:
        with zipfile.ZipFile(path) as archive:
            if archive.testzip() is not None or "word/document.xml" not in archive.namelist():
                raise ValueError("压缩结构损坏")
            for name in archive.namelist():
                if name.startswith("word/") and name.endswith(".xml"):
                    data = archive.read(name)
                    if b"txbxContent" in data:
                        for node in ET.fromstring(data).iter():
                            if node.tag.endswith("}txbxContent"):
                                content = "".join(child.text or "" for child in node.iter() if child.tag.endswith("}t"))
                                if "{{" in content or "{%" in content:
                                    raise ValueError("文本框中的占位符暂不支持，请把占位符放到正文、表格或页眉页脚")
        DocxTemplate(path).get_undeclared_template_variables()
    except Exception as exc:
        raise ValueError(f"模板“{path.name}”损坏或占位符格式不正确：{exc}") from exc


def restore_standard_templates(root: Path) -> int:
    source_dir = root / "默认模板"
    target_dir = root / "templates"
    target_dir.mkdir(parents=True, exist_ok=True)
    for name, expected in HASHES.items():
        source = source_dir / name
        if not source.exists() or file_hash(source) != expected:
            raise ValueError(f"恢复资源“{name}”缺失或损坏，请重新解压完整程序包。")
    for name in HASHES:
        source = source_dir / name
        target = target_dir / name
        temporary = target.with_name(target.name + ".restore.tmp")
        shutil.copyfile(source, temporary)
        os.replace(temporary, target)
    return len(HASHES)
