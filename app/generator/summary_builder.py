"""Build variable-length summaries while retaining the approved page/header design."""
import re
import unicodedata
from pathlib import Path

from docx import Document
from docx.enum.table import WD_CELL_VERTICAL_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.image.image import Image as DocxImage
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt
from fontTools.ttLib import TTFont

from .layout import BODY_FONT, add_h1, add_h2, add_para, add_title

PHOTO_MARKER = re.compile(r"^\[\[照片([1-3]?)\]\]$")


def build_summary(template_path: Path, output_path: Path, values: dict, monthly: bool) -> None:
    document = Document(template_path)
    body = document._body._body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)

    photos = values.get("photo_paths", [])
    used_photos = set()
    layout = values.get("photo_layout", "横向两列")
    position = values.get("photo_position", "活动总结后")
    font_path = template_path.parent.parent / "fonts" / "仿宋_GB2312.ttf"

    def fits_one_line(text: str) -> bool:
        section = document.sections[0]
        available_pt = (section.page_width - section.left_margin - section.right_margin - Pt(32)) / 12700
        if font_path.exists():
            font = TTFont(font_path, lazy=True)
            try:
                cmap = font.getBestCmap()
                metrics = font["hmtx"].metrics
                units = font["head"].unitsPerEm
                width_pt = sum(metrics.get(cmap.get(ord(char), ".notdef"), (units, 0))[0] * 16 / units for char in text)
            finally:
                font.close()
            return width_pt <= available_pt - 2
        cells = sum(2 if unicodedata.east_asian_width(char) in "FW" else 1 for char in text)
        return cells <= 48

    def add_photo(index: int):
        if index > len(photos) or index in used_photos:
            return
        path = photos[index - 1]
        img = DocxImage.from_file(path)
        ratio = min(Cm(4) / img.width, Cm(5.34) / img.height)
        paragraph = document.add_paragraph()
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.keep_together = True
        paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
        paragraph.paragraph_format.line_spacing = 1
        paragraph.add_run().add_picture(path, width=int(img.width * ratio), height=int(img.height * ratio))
        used_photos.add(index)

    def add_all_photos():
        pending = [i for i in range(1, len(photos) + 1) if i not in used_photos]
        if not pending:
            return
        photo_heading = add_h2(document, "活动照片")
        photo_heading.paragraph_format.page_break_before = values.get("photo_page", "照片单独成页") == "照片单独成页"
        columns = {"竖向单列": 1, "横向两列": 2, "横向三列": 3}.get(layout, 2)
        if columns == 1:
            for i in pending:
                add_photo(i)
            if values.get("photo_page", "照片单独成页") == "照片单独成页":
                document.add_page_break()
            return
        table = document.add_table(rows=1, cols=columns)
        table.autofit = False
        table.rows[0]._tr.get_or_add_trPr().append(OxmlElement("w:cantSplit"))
        for cell, i in zip(table.rows[0].cells, pending):
            img = DocxImage.from_file(photos[i - 1])
            ratio = min(Cm(4) / img.width, Cm(5.34) / img.height)
            cell.vertical_alignment = WD_CELL_VERTICAL_ALIGNMENT.CENTER
            paragraph = cell.paragraphs[0]
            paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
            paragraph.paragraph_format.line_spacing_rule = WD_LINE_SPACING.SINGLE
            paragraph.paragraph_format.line_spacing = 1
            paragraph.add_run().add_picture(photos[i - 1], width=int(img.width * ratio), height=int(img.height * ratio))
            used_photos.add(i)
        for i in pending[columns:]:
            add_photo(i)
        if values.get("photo_page", "照片单独成页") == "照片单独成页":
            document.add_page_break()

    def add_text(text: str):
        for line in re.split(r"\r?\n", str(text)):
            line = line.strip()
            if not line:
                continue
            match = PHOTO_MARKER.fullmatch(line)
            if match:
                if match.group(1):
                    add_photo(int(match.group(1)))
                else:
                    add_all_photos()
            else:
                add_para(document, line, font=BODY_FONT, size=16)

    def add_points(items):
        if isinstance(items, str):
            items = [line for line in items.splitlines() if line.strip()]
        items = [re.sub(r"\s+", " ", str(item)).strip() for item in items if str(item).strip()]
        for index, item in enumerate(items, 1):
            prefix = f"{index}. " if len(items) > 1 else ""
            add_para(document, prefix + item, font=BODY_FONT, size=16)

    def add_detail(label: str, value: str):
        if isinstance(value, list):
            if value:
                add_para(document, label, font=BODY_FONT, size=16)
                add_points(value)
            return
        value = str(value or "").strip()
        if not value:
            return
        if "\n" not in value and fits_one_line(label + value):
            add_para(document, label + value, font=BODY_FONT, size=16)
            return
        add_para(document, label, font=BODY_FONT, size=16)
        lines = value.splitlines()
        for index in range(len(lines) - 1, -1, -1):
            if lines[index].strip() and not PHOTO_MARKER.fullmatch(lines[index].strip()):
                if lines[index].rstrip()[-1] not in "。！？.!?；;":
                    lines[index] = lines[index].rstrip() + "。"
                break
        add_text("\n".join(lines))

    if monthly:
        toc = str(values.get("toc", "")).strip()
        if toc:
            add_para(document, "目录", first_indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, size=22, line=33)
            for line in toc.splitlines():
                name, _, page = line.partition("|")
                add_para(document, f"{name.strip()}　　　　　　　　　{page.strip()}", first_indent=False)
        title = add_title(document, values["department_name"], f'{values["year"]}年{values["month"]}月工作总结')
        if toc:
            document.paragraphs[-2].paragraph_format.page_break_before = True
    else:
        add_title(document, f'{values["college_name"]}学院学生会', f'{values["year"]}年工作总结')

    add_h1(document, "一、总结部分（简明扼要）")
    add_points(values.get("summary_main", []))
    add_h1(document, "二、创新性或特色工作（简况、主要作法、具体成效）")
    for number in (1, 2):
        prefix = f"activity{number}_"
        name = values.get(prefix + "name", "")
        if not name:
            continue
        add_h2(document, f"{number}. {name}")
        for key, label in (
            ("purpose", "活动目的："), ("time", "活动时间："),
            ("location", "活动地点："), ("publicity", "活动宣传方式："),
            ("preparation", "活动准备："), ("scope", "活动覆盖范围："),
            ("participants", "活动参与人数："), ("process", "活动过程："),
            ("impact", "活动影响力："), ("summary", "活动总结："),
        ):
            add_detail(label, values.get(prefix + key, ""))
            if number == 1 and key == "process" and position == "活动过程后":
                add_all_photos()
    if position == "活动总结后":
        add_all_photos()
    if position == "困难建议前":
        add_all_photos()
    suggestions = values.get("suggestions", [])
    add_h1(document, "三、存在的困难和问题及相应建议" if suggestions else "三、存在的困难和问题")
    if suggestions:
        add_h2(document, "1. 存在的困难")
    add_points(values.get("problems", []))
    if suggestions:
        add_h2(document, "2. 相应建议")
        add_points(suggestions)
    def add_signature():
        signature = add_para(document, values["signature_unit"], align=WD_ALIGN_PARAGRAPH.RIGHT, first_indent=False, before=84)
        signature.paragraph_format.right_indent = Pt(64)
        signature.paragraph_format.keep_with_next = True
        date_line = add_para(document, values["date_cn"], align=WD_ALIGN_PARAGRAPH.RIGHT, first_indent=False)
        date_line.paragraph_format.right_indent = Pt(64)

    if position == "文末":
        add_signature()
        add_all_photos()
    else:
        if position == "自定义标记":
            add_all_photos()
        add_signature()
    document.save(output_path)
