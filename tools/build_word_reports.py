"""把两个选题的 Markdown 实验报告排版成 Word 文档。

用法：
    py tools/build_word_reports.py            # 生成两份 .docx
    py tools/build_word_reports.py --finalize # 生成后用 Word 更新目录并导出 PDF 预览

排版约定（中文课程实验报告的常见格式）：
    A4，页边距 2.54 cm；正文宋体小四、1.5 倍行距、首行缩进 2 字符；
    一/二/三级标题黑体三号/四号/小四；封面单独一节、不编页码；
    目录为 Word 目录域，正文节页码从 1 开始。
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

from docx import Document
from docx.enum.section import WD_SECTION
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parents[1]
REPORTS = [
    (ROOT / "第一部分/选题一_城市交通路径导航系统/docs/实验报告.md",
     ROOT / "第一部分/选题一_城市交通路径导航系统/docs/实验报告.docx"),
    (ROOT / "第二部分/选题二_任务调度模拟器/docs/实验报告.md",
     ROOT / "第二部分/选题二_任务调度模拟器/docs/实验报告.docx"),
]

BODY_SIZE = 12.0        # 小四
TABLE_SIZE = 10.5       # 五号
CODE_SIZE = 9.0
CAPTION_SIZE = 10.5
TEXT_COLOR = "1F2328"
MUTED_COLOR = "595959"
PAGE_WIDTH_CM = 15.4    # A4 去掉左右 2.54cm 边距后的正文宽度

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
          "六": 6, "七": 7, "八": 8, "九": 9, "十": 10}


# ----------------------------------------------------------------------
# 低层工具
# ----------------------------------------------------------------------
def _ensure_rfonts(rpr) -> None:
    if rpr.find(qn("w:rFonts")) is None:
        rpr.append(OxmlElement("w:rFonts"))


def style_font(style, size: float, bold: bool = False,
               ascii_font: str = "Times New Roman", east: str = "宋体") -> None:
    style.font.name = ascii_font
    style.font.size = Pt(size)
    style.font.bold = bold
    style.font.color.rgb = RGBColor.from_string(TEXT_COLOR)
    rpr = style.element.get_or_add_rPr()
    _ensure_rfonts(rpr)
    rfonts = rpr.find(qn("w:rFonts"))
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)
    rfonts.set(qn("w:eastAsia"), east)


def add_run(p, text: str, size: float = BODY_SIZE, bold: bool = False,
            color: str | None = TEXT_COLOR, *, italic: bool = False,
            underline: bool = False, ascii_font: str = "Times New Roman",
            east: str = "宋体", shade: str | None = None):
    run = p.add_run()
    run.text = text.replace("\ue000", "*")
    for node in run._r.findall(qn("w:t")):
        node.set(qn("xml:space"), "preserve")
    run.font.name = ascii_font
    run.font.size = Pt(size)
    run.font.bold = bold
    run.font.italic = italic
    run.font.underline = underline
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    rpr = run._r.get_or_add_rPr()
    _ensure_rfonts(rpr)
    rfonts = rpr.find(qn("w:rFonts"))
    rfonts.set(qn("w:ascii"), ascii_font)
    rfonts.set(qn("w:hAnsi"), ascii_font)
    rfonts.set(qn("w:eastAsia"), east)
    if shade:
        shd = OxmlElement("w:shd")
        shd.set(qn("w:val"), "clear")
        shd.set(qn("w:color"), "auto")
        shd.set(qn("w:fill"), shade)
        rpr.append(shd)
    return run


def para_format(p, *, first_indent: float = 0, left: float = 0,
                right: float = 0, before: float = 0, after: float = 0,
                line: float = 1.5, align=None, hanging: float = 0,
                keep_next: bool = False) -> None:
    pf = p.paragraph_format
    pf.first_line_indent = Pt(first_indent) if not hanging else Cm(-hanging)
    pf.left_indent = Cm(left) if left else (Cm(hanging) if hanging else Pt(0))
    pf.right_indent = Cm(right) if right else Pt(0)
    pf.space_before = Pt(before)
    pf.space_after = Pt(after)
    pf.line_spacing = line
    pf.keep_with_next = keep_next
    if align is not None:
        p.alignment = align


def shade_paragraph(p, fill: str) -> None:
    ppr = p._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    ppr.insert_element_before(
        shd, "w:tabs", "w:suppressAutoHyphens", "w:kinsoku", "w:wordWrap",
        "w:overflowPunct", "w:topLinePunct", "w:autoSpaceDE", "w:autoSpaceDN",
        "w:bidi", "w:adjustRightInd", "w:snapToGrid", "w:spacing", "w:ind",
        "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
        "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
        "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr",
        "w:pPrChange")


def border_paragraph(p, side: str = "left", color: str = "D0D7DE",
                     space: str = "6") -> None:
    ppr = p._p.get_or_add_pPr()
    pbdr = OxmlElement("w:pBdr")
    edge = OxmlElement(f"w:{side}")
    edge.set(qn("w:val"), "single")
    edge.set(qn("w:sz"), "8")
    edge.set(qn("w:space"), space)
    edge.set(qn("w:color"), color)
    pbdr.append(edge)
    ppr.insert_element_before(
        pbdr, "w:shd", "w:tabs", "w:suppressAutoHyphens", "w:spacing", "w:ind",
        "w:contextualSpacing", "w:mirrorIndents", "w:suppressOverlap", "w:jc",
        "w:textDirection", "w:textAlignment", "w:textboxTightWrap",
        "w:outlineLvl", "w:divId", "w:cnfStyle", "w:rPr", "w:sectPr",
        "w:pPrChange")


def shade_cell(cell, fill: str) -> None:
    tcpr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcpr.append(shd)


def set_repeat_header(row) -> None:
    trpr = row._tr.get_or_add_trPr()
    header = OxmlElement("w:tblHeader")
    header.set(qn("w:val"), "true")
    trpr.append(header)


def underline_cell(cell) -> None:
    """给单元格加一条下边框，用作封面的待填横线。"""
    tcpr = cell._tc.get_or_add_tcPr()
    borders = OxmlElement("w:tcBorders")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "8")
    bottom.set(qn("w:space"), "0")
    bottom.set(qn("w:color"), "1F2328")
    borders.append(bottom)
    tcpr.insert_element_before(
        borders, "w:shd", "w:noWrap", "w:tcMar", "w:textDirection",
        "w:tcFitText", "w:vAlign", "w:hideMark", "w:headers", "w:cellIns",
        "w:cellDel", "w:cellMerge", "w:tcPrChange")


# ----------------------------------------------------------------------
# 行内格式
# ----------------------------------------------------------------------
INLINE_RE = re.compile(
    r"(\*\*.+?\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\)|\$[^$\n]+\$|\*[^*\n]+\*)")


def latex_to_text(src: str) -> str:
    """把报告里用到的少量 LaTeX 片段转成可读的 Unicode 文本。"""
    s = src.strip()
    s = re.sub(r"\\sqrt\{([^{}]*)\}", r"√(\1)", s)
    s = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", s)
    s = s.replace("\\bar{L}", "L̄").replace("\\bar", "")
    s = s.replace("\\big(", "(").replace("\\big)", ")")
    s = s.replace("\\left", "").replace("\\right", "")
    s = s.replace("\\log", "log").replace("\\sum", "Σ")
    s = s.replace("\\leq", "≤").replace("\\le", "≤")
    s = s.replace("\\geq", "≥").replace("\\ge", "≥")
    s = s.replace("\\times", "×").replace("\\cdot", "·")
    s = s.replace("\\infty", "∞").replace("\\Theta", "Θ").replace("\\Omega", "Ω")
    s = s.replace("^2", "²")
    subs = {"n": "ₙ", "t": "ₜ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ",
            "0": "₀", "1": "₁", "2": "₂", "S": "ₛ", "s": "ₛ"}
    s = re.sub(r"([A-Za-z0-9])_([A-Za-z0-9])",
               lambda m: m.group(1) + subs.get(m.group(2), m.group(2)), s)
    s = s.replace("{", "").replace("}", "").replace("\\", "")
    return s


def inline_runs(p, text: str, size: float = BODY_SIZE, bold: bool = False,
                color: str | None = TEXT_COLOR) -> None:
    text = text.replace("\\*", "\ue000")
    pos = 0
    for match in INLINE_RE.finditer(text):
        if match.start() > pos:
            add_run(p, text[pos:match.start()], size, bold, color)
        token = match.group(0)
        if token.startswith("**"):
            add_run(p, token[2:-2], size, True, color)
        elif token.startswith("`"):
            add_run(p, token[1:-1], size, bold, color,
                    ascii_font="Consolas", east="新宋体", shade="F2F2F2")
        elif token.startswith("["):
            label = re.match(r"\[([^\]]+)\]", token).group(1)
            add_run(p, label, size, bold, color, underline=True)
        elif token.startswith("$"):
            add_run(p, latex_to_text(token[1:-1]), size, bold, color,
                    ascii_font="Cambria Math", east="Cambria Math")
        elif token.startswith("*"):
            add_run(p, token[1:-1], size, bold, color, italic=True)
        pos = match.end()
    if pos < len(text):
        add_run(p, text[pos:], size, bold, color)


# ----------------------------------------------------------------------
# Markdown 解析
# ----------------------------------------------------------------------
def join_lines(lines: list[str]) -> str:
    out = lines[0]
    for nxt in lines[1:]:
        prev = out[-1] if out else ""
        head = nxt[0] if nxt else ""
        if prev.isascii() and prev.isalnum() and head.isascii() and head.isalnum():
            out += " " + nxt
        else:
            out += nxt
    return out


def parse_markdown(text: str):
    lines = text.splitlines()
    blocks = []
    i = 0
    while i < len(lines):
        raw = lines[i]
        s = raw.strip()
        if not s:
            i += 1
            continue
        if s.startswith("```"):
            i += 1
            buf = []
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i])
                i += 1
            i += 1
            blocks.append(("code", "\n".join(buf)))
        elif s.startswith("### "):
            blocks.append(("h3", s[4:].strip()))
            i += 1
        elif s.startswith("## "):
            blocks.append(("h2", s[3:].strip()))
            i += 1
        elif s.startswith("# "):
            blocks.append(("h1", s[2:].strip()))
            i += 1
        elif s.startswith("|"):
            rows = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                rows.append(lines[i].strip())
                i += 1
            blocks.append(("table", rows))
        elif s.startswith("!["):
            m = re.match(r"!\[([^\]]*)\]\(([^)]+)\)", s)
            if m:
                blocks.append(("image", (m.group(1), m.group(2))))
            i += 1
        elif s.startswith("> "):
            buf = []
            while i < len(lines) and lines[i].startswith(">"):
                buf.append(lines[i][1:].strip())
                i += 1
            blocks.append(("quote", join_lines(buf)))
        elif re.match(r"^\s*[-*+]\s+", raw):
            items = []
            while i < len(lines) and re.match(r"^\s*[-*+]\s+", lines[i]):
                items.append(re.sub(r"^\s*[-*+]\s+", "", lines[i]).strip())
                i += 1
            blocks.append(("bullets", items))
        elif re.match(r"^\s*\d+\.\s+", raw):
            items = []
            while i < len(lines) and re.match(r"^\s*\d+\.\s+", lines[i]):
                m = re.match(r"^\s*(\d+)\.\s+(.*)", lines[i])
                items.append((m.group(1), m.group(2).strip()))
                i += 1
            blocks.append(("numbers", items))
        elif re.match(r"^\$\$.+\$\$$", s):
            blocks.append(("math", s[2:-2].strip()))
            i += 1
        elif s in ("---", "***", "___"):
            i += 1
        else:
            buf = [s]
            i += 1
            while i < len(lines):
                nxt = lines[i]
                ns = nxt.strip()
                if (not ns or ns.startswith(("#", "```", "|", "![", ">", "$$"))
                        or ns in ("---", "***", "___")
                        or re.match(r"^\s*([-*+]|\d+\.)\s", nxt)):
                    break
                buf.append(ns)
                i += 1
            blocks.append(("p", join_lines(buf)))
    return blocks


def split_table_row(row: str) -> list[str]:
    row = row.strip()
    if row.startswith("|"):
        row = row[1:]
    if row.endswith("|"):
        row = row[:-1]
    return [c.strip() for c in row.split("|")]


# ----------------------------------------------------------------------
# 文档构建
# ----------------------------------------------------------------------
def setup_page(section) -> None:
    section.page_width = Cm(21.0)
    section.page_height = Cm(29.7)
    section.top_margin = Cm(2.54)
    section.bottom_margin = Cm(2.54)
    section.left_margin = Cm(2.54)
    section.right_margin = Cm(2.54)
    section.header_distance = Cm(1.5)
    section.footer_distance = Cm(1.5)


def add_field(paragraph, instr: str, placeholder: str = "") -> None:
    run = paragraph.add_run()
    begin = OxmlElement("w:fldChar")
    begin.set(qn("w:fldCharType"), "begin")
    begin.set(qn("w:dirty"), "true")
    run._r.append(begin)

    run2 = paragraph.add_run()
    text = OxmlElement("w:instrText")
    text.set(qn("xml:space"), "preserve")
    text.text = instr
    run2._r.append(text)

    run3 = paragraph.add_run()
    sep = OxmlElement("w:fldChar")
    sep.set(qn("w:fldCharType"), "separate")
    run3._r.append(sep)

    if placeholder:
        add_run(paragraph, placeholder, 10.5, color=MUTED_COLOR)

    run4 = paragraph.add_run()
    end = OxmlElement("w:fldChar")
    end.set(qn("w:fldCharType"), "end")
    run4._r.append(end)


def add_header_footer(section, title: str) -> None:
    section.header.is_linked_to_previous = False
    hp = section.header.paragraphs[0]
    hp.text = ""
    para_format(hp, line=1.0, align=WD_ALIGN_PARAGRAPH.RIGHT)
    add_run(hp, f"《数据结构实践》实验报告 · {title}", 9, color="8C959F")

    section.footer.is_linked_to_previous = False
    fp = section.footer.paragraphs[0]
    fp.text = ""
    para_format(fp, line=1.0, align=WD_ALIGN_PARAGRAPH.CENTER)
    run = fp.add_run("— ")
    run.font.size = Pt(9)
    add_field(fp, " PAGE ")
    run = fp.add_run(" —")
    run.font.size = Pt(9)


def start_page_numbering(section, start: int = 1) -> None:
    sectpr = section._sectPr
    pg = sectpr.find(qn("w:pgNumType"))
    if pg is None:
        pg = OxmlElement("w:pgNumType")
        sectpr.append(pg)
    pg.set(qn("w:start"), str(start))


def clear_header_footer(section) -> None:
    section.header.is_linked_to_previous = False
    section.footer.is_linked_to_previous = False
    for part in (section.header, section.footer):
        for p in part.paragraphs:
            p.text = ""


def add_cover(doc, title: str, info: dict[str, str]) -> None:
    for _ in range(3):
        p = doc.add_paragraph()
        para_format(p, line=1.5)

    p = doc.add_paragraph()
    para_format(p, line=1.5, after=24, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, "《数据结构实践》课程实验报告", 18, bold=True, east="黑体")

    p = doc.add_paragraph()
    para_format(p, line=1.5, after=72, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, title, 26, bold=True, east="黑体")

    rows = [
        ("实验选题", info.get("实验选题", "")),
        ("实现语言", info.get("实现语言", "")),
        ("姓名", ""),
        ("学号", ""),
        ("班级", ""),
        ("日期", ""),
    ]
    table = doc.add_table(rows=len(rows), cols=2)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for i, (key, value) in enumerate(rows):
        row = table.rows[i]
        row.cells[0].width = Cm(4.2)
        row.cells[1].width = Cm(9.0)
        left = row.cells[0].paragraphs[0]
        para_format(left, line=1.5, after=6, align=WD_ALIGN_PARAGRAPH.RIGHT)
        add_run(left, key + "：", 14, bold=True, east="黑体")
        right = row.cells[1].paragraphs[0]
        para_format(right, line=1.5, after=6, align=WD_ALIGN_PARAGRAPH.LEFT)
        if value:
            add_run(right, value, 14)
        else:
            # 段落末尾的空格下划线在 Word 里不渲染，改用段落下边框做横线
            add_run(right, "　" * 12, 14)
            border_paragraph(right, "bottom", color="1F2328", space="2")


def add_toc(doc) -> None:
    p = doc.add_paragraph()
    para_format(p, line=1.5, after=18, align=WD_ALIGN_PARAGRAPH.CENTER)
    add_run(p, "目　录", 16, bold=True, east="黑体")

    p = doc.add_paragraph()
    para_format(p, line=1.5)
    add_field(p, ' TOC \\o "1-3" \\h \\z \\u ',
              "（目录将在打开文档时自动生成；若未显示，请右键此处选择“更新域”）")


def chapter_number(heading: str):
    m = re.search(r"第([一二三四五六七八九十]+)章", heading)
    if m:
        return CN_NUM.get(m.group(1), m.group(1))
    if "附录" in heading:
        return "附"
    return ""


def add_table_block(doc, rows: list[str]) -> None:
    if not rows:
        return
    header = split_table_row(rows[0])
    data = [split_table_row(r) for r in rows[2:]] if len(rows) > 2 else []
    ncols = max([len(header)] + [len(r) for r in data]) if data else len(header)
    table = doc.add_table(rows=1 + len(data), cols=ncols)
    table.style = "Table Grid"
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = True
    set_repeat_header(table.rows[0])

    def fill(cell, text: str, bold: bool) -> None:
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        p = cell.paragraphs[0]
        para_format(p, line=1.25, before=2, after=2,
                    align=WD_ALIGN_PARAGRAPH.LEFT)
        inline_runs(p, text, TABLE_SIZE, bold)

    for j, text in enumerate(header):
        cell = table.rows[0].cells[j]
        shade_cell(cell, "F2F2F2")
        fill(cell, text, True)
    for i, row in enumerate(data, start=1):
        for j in range(ncols):
            fill(table.rows[i].cells[j], row[j] if j < len(row) else "", False)

    spacer = doc.add_paragraph()
    para_format(spacer, line=1.0, after=0)
    spacer.paragraph_format.space_before = Pt(0)
    spacer_run = spacer.add_run("")
    spacer_run.font.size = Pt(6)


def add_image_block(doc, alt: str, rel_path: str, base: Path,
                    fig_no: str, width_cm: float = PAGE_WIDTH_CM) -> None:
    img = (base / rel_path).resolve()
    p = doc.add_paragraph()
    para_format(p, line=1.0, before=6, after=3,
                align=WD_ALIGN_PARAGRAPH.CENTER)
    if img.exists():
        p.add_run().add_picture(str(img), width=Cm(width_cm))
    else:
        add_run(p, f"[图片缺失：{rel_path}]", 9, color="CF222E")

    cap = doc.add_paragraph()
    para_format(cap, line=1.25, before=0, after=10,
                align=WD_ALIGN_PARAGRAPH.CENTER)
    text = f"图 {fig_no}" + (f"　{alt}" if alt else "")
    add_run(cap, text, CAPTION_SIZE, color=MUTED_COLOR)


def add_code_block(doc, code: str) -> None:
    p = doc.add_paragraph()
    para_format(p, line=1.0, left=0.35, right=0.35, before=6, after=6)
    shade_paragraph(p, "F6F8FA")
    lines = code.split("\n")
    for i, line in enumerate(lines):
        run = add_run(p, line if line else " ", CODE_SIZE,
                      ascii_font="Consolas", east="新宋体")
        if i < len(lines) - 1:
            run.add_break()


def build_report(md_path: Path, out_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")
    blocks = parse_markdown(text)

    title = next((b[1] for b in blocks if b[0] == "h1"), md_path.stem)
    cover_rows = next((b[1] for b in blocks if b[0] == "table"), [])
    info = {}
    if cover_rows:
        for row in cover_rows[2:]:
            cells = split_table_row(row)
            if len(cells) >= 2:
                info[cells[0]] = cells[1]

    start = next((i for i, b in enumerate(blocks)
                  if b[0] == "h2" and "第一章" in b[1]), 0)
    body = blocks[start:]

    doc = Document()

    # ---- 基础样式 ----
    normal = doc.styles["Normal"]
    style_font(normal, BODY_SIZE)
    pf = normal.paragraph_format
    pf.line_spacing = 1.5
    pf.space_before = Pt(0)
    pf.space_after = Pt(0)
    pf.first_line_indent = Pt(24)

    for name, size, before, after in (
            ("Heading 1", 16, 24, 12),
            ("Heading 2", 14, 12, 6),
            ("Heading 3", 12, 6, 3)):
        st = doc.styles[name]
        style_font(st, size, bold=True, east="黑体")
        spf = st.paragraph_format
        spf.first_line_indent = Pt(0)
        spf.line_spacing = 1.5
        spf.space_before = Pt(before)
        spf.space_after = Pt(after)
        spf.keep_with_next = True

    # ---- 第 1 节：封面 ----
    setup_page(doc.sections[0])
    clear_header_footer(doc.sections[0])
    add_cover(doc, title, info)

    # ---- 第 2 节：目录 ----
    sec_toc = doc.add_section(WD_SECTION.NEW_PAGE)
    setup_page(sec_toc)
    clear_header_footer(sec_toc)
    add_toc(doc)

    # ---- 第 3 节：正文 ----
    sec_body = doc.add_section(WD_SECTION.NEW_PAGE)
    setup_page(sec_body)
    add_header_footer(sec_body, title)
    start_page_numbering(sec_body, 1)

    chapter = ""
    fig_count = 0
    first_heading = True

    for block in body:
        kind = block[0]
        if kind == "h2":
            heading = block[1]
            chapter = chapter_number(heading)
            fig_count = 0
            p = doc.add_paragraph(style="Heading 1")
            p.paragraph_format.page_break_before = not first_heading
            first_heading = False
            add_run(p, heading, 16, bold=True, east="黑体")
        elif kind == "h3":
            p = doc.add_paragraph(style="Heading 2")
            add_run(p, block[1], 14, bold=True, east="黑体")
        elif kind == "p":
            p = doc.add_paragraph()
            para_format(p, line=1.5)
            inline_runs(p, block[1])
        elif kind == "bullets":
            for item in block[1]:
                p = doc.add_paragraph()
                para_format(p, line=1.5, hanging=0.74)
                add_run(p, "•  ")
                inline_runs(p, item)
        elif kind == "numbers":
            for num, item in block[1]:
                p = doc.add_paragraph()
                para_format(p, line=1.5, hanging=0.74)
                add_run(p, f"{num}.  ")
                inline_runs(p, item)
        elif kind == "quote":
            p = doc.add_paragraph()
            para_format(p, line=1.5, left=0.9, right=0.5, before=6, after=6)
            shade_paragraph(p, "F6F8FA")
            border_paragraph(p, "left")
            inline_runs(p, block[1], 10.5, color=MUTED_COLOR)
        elif kind == "code":
            add_code_block(doc, block[1])
        elif kind == "math":
            p = doc.add_paragraph()
            para_format(p, line=1.5, before=6, after=6,
                        align=WD_ALIGN_PARAGRAPH.CENTER)
            add_run(p, latex_to_text(block[1]), 12,
                    ascii_font="Cambria Math", east="Cambria Math")
        elif kind == "table":
            add_table_block(doc, block[1])
        elif kind == "image":
            alt, rel = block[1]
            fig_count += 1
            add_image_block(doc, alt, rel, md_path.parent,
                            f"{chapter}-{fig_count}")

    doc.core_properties.title = title
    doc.core_properties.subject = "《数据结构实践》课程实验报告"
    doc.core_properties.author = ""

    # 打开时自动更新域（目录页码）
    settings = doc.settings.element
    update = OxmlElement("w:updateFields")
    update.set(qn("w:val"), "true")
    settings.append(update)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    doc.save(out_path)
    print(f"写出 {out_path}（{out_path.stat().st_size // 1024} KB）")


def finalize_with_word() -> None:
    """用 Word 更新目录域并导出 PDF 预览。"""
    try:
        import win32com.client as win32
    except ImportError:
        print("未安装 pywin32，跳过目录更新")
        return

    word = win32.DispatchEx("Word.Application")
    word.Visible = False
    word.DisplayAlerts = 0
    try:
        for _, docx_path in REPORTS:
            doc = word.Documents.Open(str(docx_path))
            for toc in doc.TablesOfContents:
                toc.Update()
            doc.Fields.Update()
            # 目录条目用 11pt、单倍行距，一页就能放下全部条目
            for name in ("TOC 1", "TOC 2", "TOC 3"):
                try:
                    st = doc.Styles(name)
                    st.Font.Size = 11
                    st.ParagraphFormat.LineSpacingRule = 0   # 单倍行距
                    st.ParagraphFormat.SpaceBefore = 0
                    st.ParagraphFormat.SpaceAfter = 3
                except Exception:
                    pass
            for toc in doc.TablesOfContents:
                toc.Update()
            doc.Save()
            pdf_path = docx_path.with_suffix(".pdf")
            doc.SaveAs2(str(pdf_path), FileFormat=17)
            doc.Close(False)
            print(f"已更新目录并导出预览 {pdf_path}")
    finally:
        word.Quit()


def main() -> None:
    for md_path, docx_path in REPORTS:
        if not md_path.exists():
            print(f"缺少报告 {md_path}")
            continue
        build_report(md_path, docx_path)
    if "--finalize" in sys.argv:
        finalize_with_word()


if __name__ == "__main__":
    main()
