"""按校内实训报告模板生成合并版 Word 报告。

模板结构：封面（校徽 / 小组名单 / 实践信息）→ 实践计划 → 实践记录。
实践记录原来是一个 1×1 的大表格，单元格里预先写好了「任务一 / 任务二
+ 五章标题」。Word 的表格单元格里不能插入分页符，所以这里把占位表格
换成「每章一个表格框」，章与章之间用显式分页符分开 —— 外观与模板的
记录框一致，同时保证每章从新页开始。

两份 Markdown 报告分别填进「任务一」「任务二」，输出到仓库根目录
`校内实训报告.docx`。

用法：
    py tools/build_template_report.py            # 生成 docx
    py tools/build_template_report.py --finalize # 再用 Word 导出 PDF 预览
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH, WD_BREAK
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt

sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_word_reports import (  # noqa: E402
    add_code_block, add_image_block, add_run, add_table_block,
    chapter_number, inline_runs, latex_to_text, para_format, parse_markdown,
)

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "tools" / "template.docx"   # 由老师给的 .doc 模板转出
OUT = ROOT / "校内实训报告.docx"
REPORTS = [
    (ROOT / "第一部分/选题一_城市交通路径导航系统/docs/实验报告.md", "任务一"),
    (ROOT / "第二部分/选题二_任务调度模拟器/docs/实验报告.md", "任务二"),
]
CELL_WIDTH_CM = 16.3
FIGURE_WIDTH = 14.6


def set_cell_width(cell, cm: float = CELL_WIDTH_CM) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    tcw = tcpr.find(qn("w:tcW"))
    if tcw is None:
        tcw = OxmlElement("w:tcW")
        tcpr.insert(0, tcw)
    tcw.set(qn("w:w"), str(int(cm * 567)))
    tcw.set(qn("w:type"), "dxa")


def create_chapter_table(doc):
    """一个带边框的 1×1 表格，用来装一章内容。"""
    table = doc.add_table(rows=1, cols=1)
    try:
        table.style = "Table Grid"
    except KeyError:
        table.style = "Normal Table"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    tblpr = table._tbl.tblPr
    tblw = tblpr.find(qn("w:tblW"))
    if tblw is None:
        tblw = OxmlElement("w:tblW")
        tblpr.append(tblw)
    tblw.set(qn("w:w"), str(int(CELL_WIDTH_CM * 567)))
    tblw.set(qn("w:type"), "dxa")
    cell = table.rows[0].cells[0]
    set_cell_width(cell)
    # 新表格的单元格自带一个空段落，先清掉，免得每章标题前多一行
    for paragraph in list(cell.paragraphs):
        paragraph._element.getparent().remove(paragraph._element)
    return table, cell


def insert_page_break(doc, anchor):
    """在 anchor 元素之后插入一个分页符段落，返回新元素。"""
    p = doc.add_paragraph()
    para_format(p, line=1.0, after=0)
    p.add_run().add_break(WD_BREAK.PAGE)
    anchor.addnext(p._p)
    return p._p


def insert_spacer(doc, anchor, size_pt: float = 6):
    p = doc.add_paragraph()
    para_format(p, line=1.0, before=0, after=0)
    p.add_run("").font.size = Pt(size_pt)
    anchor.addnext(p._p)
    return p._p


def chapter_heading(heading: str) -> str:
    """模板的章标题写作「第一章：需求分析与问题建模」。"""
    m = re.match(r"^(第[一二三四五六七八九十]+章)\s*(.*)$", heading)
    if m:
        return f"{m.group(1)}：{m.group(2)}"
    return heading


def split_chapters(body: list) -> list[list]:
    chapters: list[list] = []
    current: list = []
    for block in body:
        if block[0] == "h2":
            if current:
                chapters.append(current)
            current = [block]
        else:
            current.append(block)
    if current:
        chapters.append(current)
    return chapters


def write_task_title(cell, title: str) -> None:
    p = cell.add_paragraph(style="Heading 3")
    para_format(p, line=1.5, before=6, after=12,
                align=WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, title, 20, bold=True, east="宋体")


def render_chapter(cell, blocks: list, md_dir: Path) -> None:
    heading = blocks[0][1]
    chapter = chapter_number(heading)
    fig_count = 0

    p = cell.add_paragraph(style="Heading 3")
    add_run(p, chapter_heading(heading), 13.5, bold=True, east="宋体")

    for block in blocks[1:]:
        kind = block[0]
        if kind == "h3":
            p = cell.add_paragraph()
            para_format(p, line=1.5, before=10, after=4)
            add_run(p, block[1], 12, bold=True, east="黑体")
        elif kind == "p":
            p = cell.add_paragraph()
            para_format(p, line=1.5)
            inline_runs(p, block[1])
        elif kind == "bullets":
            for item in block[1]:
                p = cell.add_paragraph()
                para_format(p, line=1.5, hanging=0.74)
                add_run(p, "•  ")
                inline_runs(p, item)
        elif kind == "numbers":
            for num, item in block[1]:
                p = cell.add_paragraph()
                para_format(p, line=1.5, hanging=0.74)
                add_run(p, f"{num}.  ")
                inline_runs(p, item)
        elif kind == "quote":
            from build_word_reports import border_paragraph, shade_paragraph
            p = cell.add_paragraph()
            para_format(p, line=1.5, left=0.6, right=0.3, before=6, after=6)
            shade_paragraph(p, "F6F8FA")
            border_paragraph(p, "left")
            inline_runs(p, block[1], 10.5, color="595959")
        elif kind == "code":
            add_code_block(cell, block[1])
        elif kind == "math":
            p = cell.add_paragraph()
            para_format(p, line=1.5, before=6, after=6,
                        align=WD_ALIGN_PARAGRAPH.CENTER)
            add_run(p, latex_to_text(block[1]), 12,
                    ascii_font="Cambria Math", east="Cambria Math")
        elif kind == "table":
            add_table_block(cell, block[1])
        elif kind == "image":
            alt, rel = block[1]
            fig_count += 1
            add_image_block(cell, alt, rel, md_dir,
                            f"{chapter}-{fig_count}", width_cm=FIGURE_WIDTH)


def main() -> None:
    if not TEMPLATE.exists():
        raise SystemExit("缺少 _template.docx（由 .doc 模板另存而来）")

    doc = Document(str(TEMPLATE))
    placeholder = doc.tables[3]._tbl
    anchor = placeholder

    for task_index, (md_path, task_title) in enumerate(REPORTS):
        blocks = parse_markdown(md_path.read_text(encoding="utf-8"))
        start = next((i for i, b in enumerate(blocks)
                      if b[0] == "h2" and "第一章" in b[1]), 0)
        chapters = split_chapters(blocks[start:])

        for chapter_index, chapter in enumerate(chapters):
            if task_index and chapter_index == 0:
                anchor = insert_page_break(doc, anchor)
            elif chapter_index:
                anchor = insert_spacer(doc, anchor)

            table, cell = create_chapter_table(doc)
            anchor.addnext(table._tbl)
            anchor = table._tbl

            if chapter_index == 0:
                write_task_title(cell, task_title)
            render_chapter(cell, chapter, md_path.parent)

    # 成绩评定另起一页
    insert_page_break(doc, anchor)
    # 移走模板里的占位表格
    placeholder.getparent().remove(placeholder)

    doc.core_properties.title = "学生实践报告 —— 数据结构编程实践"
    doc.core_properties.author = ""
    doc.save(OUT)
    print(f"写出 {OUT}（{OUT.stat().st_size // 1024} KB）")

    if "--finalize" in sys.argv:
        finalize(OUT)


def finalize(path: Path) -> None:
    import win32com.client as win32
    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        doc = word.Documents.Open(str(path))
        doc.Fields.Update()
        doc.Save()
        pdf = path.with_suffix(".pdf")
        doc.SaveAs2(str(pdf), FileFormat=17)
        doc.Close(False)
        print(f"已导出预览 {pdf}")
    finally:
        word.Quit()


if __name__ == "__main__":
    main()
