from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_LINE_SPACING
from docx.oxml.ns import qn
from docx.shared import Pt

BODY_FONT="仿宋_GB2312"
SECOND_FONT="楷体_GB2312"
TITLE_FONT="方正小标宋简体"
BLACK_FONT="黑体"
LATIN_FONT="Times New Roman"

def set_run(run, east_asia=BODY_FONT, size=16, bold=False):
    run.font.name = LATIN_FONT
    run.font.size = Pt(size)
    run.font.bold = bold
    r_pr = run._element.get_or_add_rPr()
    r_fonts = r_pr.get_or_add_rFonts()
    r_fonts.set(qn("w:ascii"), LATIN_FONT)
    r_fonts.set(qn("w:hAnsi"), LATIN_FONT)
    r_fonts.set(qn("w:eastAsia"), east_asia)
    r_fonts.set(qn("w:cs"), LATIN_FONT)
    return run

def add_para(
    document,
    text="",
    *,
    font=BODY_FONT,
    size=16,
    bold=False,
    align=WD_ALIGN_PARAGRAPH.JUSTIFY,
    first_indent=True,
    before=0,
    after=0,
    line=28,
    keep=False,
    page_break=False,
):
    paragraph = document.add_paragraph()
    paragraph.alignment = align
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing_rule = WD_LINE_SPACING.EXACTLY
    fmt.line_spacing = Pt(line)
    fmt.first_line_indent = Pt(size * 2) if first_indent else Pt(0)
    fmt.keep_together = keep
    fmt.keep_with_next = keep
    fmt.page_break_before = page_break
    set_run(paragraph.add_run(text), east_asia=font, size=size, bold=bold)
    return paragraph

def add_title(document, line1, line2=None):
    add_para(
        document,
        line1,
        font=TITLE_FONT,
        size=22,
        align=WD_ALIGN_PARAGRAPH.CENTER,
        first_indent=False,
        after=0,
        line=33,
        keep=True,
    )
    if line2:
        add_para(
            document,
            line2,
            font=TITLE_FONT,
            size=22,
            align=WD_ALIGN_PARAGRAPH.CENTER,
            first_indent=False,
            after=12,
            line=33,
            keep=True,
        )

def add_h1(document, text, *, page_break=False):
    return add_para(
        document,
        text,
        font=BLACK_FONT,
        size=16,
        bold=False,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        first_indent=True,
        before=4,
        line=28,
        keep=True,
        page_break=page_break,
    )

def add_h2(document, text):
    return add_para(
        document,
        text,
        font=SECOND_FONT,
        size=16,
        align=WD_ALIGN_PARAGRAPH.LEFT,
        first_indent=True,
        keep=True,
    )
