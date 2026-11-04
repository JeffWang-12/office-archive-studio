"""Create plans with a variable number of points in each section."""
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.shared import Pt

from .layout import BODY_FONT, add_h1, add_h2, add_para, add_title

CN_NUMBERS = ("一", "二", "三", "四", "五", "六", "七", "八", "九", "十", "十一", "十二")


def build_plan(template_path: Path, output_path: Path, values: dict, monthly: bool) -> None:
    document = Document(template_path)
    body = document._body._body
    for child in list(body):
        if child.tag != qn("w:sectPr"):
            body.remove(child)

    if monthly:
        toc = str(values.get("toc", "")).strip()
        if toc:
            add_para(document, "目录", first_indent=False, align=WD_ALIGN_PARAGRAPH.CENTER, size=22, line=33)
            for line in toc.splitlines():
                name, _, page = line.partition("|")
                add_para(document, f"{name.strip()}　　　　　　　　　{page.strip()}", first_indent=False)
        add_title(document, values["department_name"], f'{values["year"]}年{values["month"]}月工作计划')
        if toc:
            document.paragraphs[-2].paragraph_format.page_break_before = True
    else:
        add_title(document, f'{values["college_name"]}学院学生会', f'{values["year"]}年工作计划')

    for title, name in (
        ("一、总体工作思路", "overall_idea"),
        ("二、需要全面推进的工作", "comprehensive_work"),
        ("三、需要重点推进的工作和创新性工作（重点阐述）", "priority_work"),
    ):
        add_h1(document, title)
        items = values.get(name, [])
        if isinstance(items, str):
            items = [line.strip() for line in items.splitlines() if line.strip()]
        if name == "overall_idea":
            for index, item in enumerate(items, 1):
                prefix = f"{index}. " if len(items) > 1 else ""
                add_para(document, prefix + str(item).replace("\n", " "), font=BODY_FONT, size=16)
            continue
        for index, task in enumerate(items):
            task_start = len(document.paragraphs)
            number = CN_NUMBERS[index]
            add_h2(document, f"（{number}）任务之{number}：{task['description']}")
            for goal_index, goal in enumerate(task["goals"], 1):
                add_para(document, f"{goal_index}. 目标：{goal}", font=BODY_FONT, size=16)
            if task["measures"]:
                add_para(document, "具体措施：", font=BODY_FONT, size=16)
                for measure_index, measure in enumerate(task["measures"], 1):
                    add_para(document, f"（{measure_index}）{measure}", font=BODY_FONT, size=16)
            if name == "priority_work" and index == len(items) - 1:
                task_chars = len(task["description"]) + sum(len(value) for value in task["goals"] + task["measures"])
                if task_chars < 350:
                    for paragraph in document.paragraphs[task_start:]:
                        paragraph.paragraph_format.keep_with_next = True

    signature = add_para(document, values["signature_unit"], align=WD_ALIGN_PARAGRAPH.RIGHT, first_indent=False, before=84)
    signature.paragraph_format.right_indent = Pt(64)
    signature.paragraph_format.keep_with_next = True
    date_line = add_para(document, values["date_cn"], align=WD_ALIGN_PARAGRAPH.RIGHT, first_indent=False)
    date_line.paragraph_format.right_indent = Pt(64)
    document.save(output_path)
