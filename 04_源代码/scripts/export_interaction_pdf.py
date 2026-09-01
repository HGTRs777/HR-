from __future__ import annotations

import html
import re
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    HRFlowable,
    ListFlowable,
    ListItem,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "03_人机交互对话" / "人机交互对话.md"
OUTPUT = ROOT / "03_人机交互对话" / "人机交互对话.pdf"


def inline_markup(value: str) -> str:
    rendered = html.escape(value.strip())
    rendered = re.sub(r"`([^`]+)`", r'<font name="DengMono">\1</font>', rendered)
    rendered = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", rendered)
    return rendered


def page_footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#D9DEE7"))
    canvas.line(20 * mm, 14 * mm, A4[0] - 20 * mm, 14 * mm)
    canvas.setFont("Deng", 8)
    canvas.setFillColor(colors.HexColor("#667085"))
    canvas.drawString(20 * mm, 9 * mm, "公司 HR 制度智能问答 · 人机交互对话记录")
    canvas.drawRightString(A4[0] - 20 * mm, 9 * mm, f"第 {doc.page} 页")
    canvas.restoreState()


def build_styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle(
            "ChineseTitle",
            parent=base["Title"],
            fontName="DengBold",
            fontSize=21,
            leading=29,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#172B4D"),
            spaceAfter=16,
        ),
        "h2": ParagraphStyle(
            "ChineseH2",
            parent=base["Heading2"],
            fontName="DengBold",
            fontSize=15,
            leading=21,
            textColor=colors.HexColor("#174EA6"),
            spaceBefore=13,
            spaceAfter=7,
            keepWithNext=True,
        ),
        "h3": ParagraphStyle(
            "ChineseH3",
            parent=base["Heading3"],
            fontName="DengBold",
            fontSize=12,
            leading=18,
            textColor=colors.HexColor("#22314D"),
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
        ),
        "body": ParagraphStyle(
            "ChineseBody",
            parent=base["BodyText"],
            fontName="Deng",
            fontSize=9.5,
            leading=16,
            textColor=colors.HexColor("#242B36"),
            spaceAfter=5,
        ),
        "quote": ParagraphStyle(
            "ChineseQuote",
            parent=base["BodyText"],
            fontName="Deng",
            fontSize=8.8,
            leading=14,
            leftIndent=9,
            borderColor=colors.HexColor("#7BAAF7"),
            borderWidth=1.5,
            borderPadding=(5, 7, 5, 8),
            backColor=colors.HexColor("#F5F8FE"),
            textColor=colors.HexColor("#475467"),
            spaceAfter=7,
        ),
        "table": ParagraphStyle(
            "ChineseTable",
            parent=base["BodyText"],
            fontName="Deng",
            fontSize=7.2,
            leading=10.5,
            textColor=colors.HexColor("#242B36"),
        ),
        "table_header": ParagraphStyle(
            "ChineseTableHeader",
            parent=base["BodyText"],
            fontName="DengBold",
            fontSize=7.3,
            leading=10.5,
            textColor=colors.white,
        ),
    }


def parse_table(lines: list[str], styles: dict[str, ParagraphStyle], width: float) -> Table:
    rows = [[cell.strip() for cell in line.strip().strip("|").split("|")] for line in lines]
    rows = [rows[0], *rows[2:]]
    column_count = max(len(row) for row in rows)
    data = []
    for row_index, row in enumerate(rows):
        row += [""] * (column_count - len(row))
        style = styles["table_header"] if row_index == 0 else styles["table"]
        data.append([Paragraph(inline_markup(cell), style) for cell in row])
    first_width = 16 * mm if column_count >= 4 else width / column_count
    col_widths = [first_width] + [(width - first_width) / (column_count - 1)] * (column_count - 1)
    table = Table(data, colWidths=col_widths, repeatRows=1, hAlign="LEFT")
    table.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#315B96")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#CCD3DE")),
                ("BACKGROUND", (0, 1), (-1, -1), colors.white),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F9FC")]),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]
        )
    )
    return table


def build_story(text: str, styles: dict[str, ParagraphStyle], width: float):
    story = []
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        line = lines[index].rstrip()
        if not line:
            story.append(Spacer(1, 2.5 * mm))
            index += 1
            continue
        if line == "---":
            story.append(HRFlowable(width="100%", color=colors.HexColor("#D9DEE7"), thickness=0.6, spaceBefore=4, spaceAfter=7))
            index += 1
            continue
        if line.startswith("# "):
            story.append(Paragraph(inline_markup(line[2:]), styles["title"]))
            index += 1
            continue
        if line.startswith("## "):
            story.append(Paragraph(inline_markup(line[3:]), styles["h2"]))
            index += 1
            continue
        if line.startswith("### "):
            story.append(Paragraph(inline_markup(line[4:]), styles["h3"]))
            index += 1
            continue
        if line.startswith("> "):
            quote_lines = []
            while index < len(lines) and lines[index].startswith("> "):
                quote_lines.append(lines[index][2:].rstrip("  "))
                index += 1
            story.append(Paragraph("<br/>".join(inline_markup(item) for item in quote_lines), styles["quote"]))
            continue
        if line.startswith("| ") and index + 1 < len(lines) and re.match(r"^\|[ :|-]+\|$", lines[index + 1]):
            table_lines = [line, lines[index + 1]]
            index += 2
            while index < len(lines) and lines[index].startswith("|"):
                table_lines.append(lines[index])
                index += 1
            story.extend([parse_table(table_lines, styles, width), Spacer(1, 3 * mm)])
            continue
        if line.startswith("- "):
            items = []
            while index < len(lines) and lines[index].startswith("- "):
                items.append(ListItem(Paragraph(inline_markup(lines[index][2:]), styles["body"]), leftIndent=8))
                index += 1
            story.append(ListFlowable(items, bulletType="bullet", start="circle", leftIndent=15, bulletFontName="Deng"))
            story.append(Spacer(1, 2 * mm))
            continue
        paragraph_lines = [line]
        index += 1
        while index < len(lines) and lines[index].strip() and not re.match(r"^(#|>|- |\| |---$)", lines[index]):
            paragraph_lines.append(lines[index].strip())
            index += 1
        story.append(Paragraph(inline_markup(" ".join(paragraph_lines)), styles["body"]))
    return story


def main() -> None:
    source = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else SOURCE
    output = Path(sys.argv[2]).resolve() if len(sys.argv) > 2 else OUTPUT
    pdfmetrics.registerFont(TTFont("Deng", r"C:\Windows\Fonts\Deng.ttf"))
    pdfmetrics.registerFont(TTFont("DengBold", r"C:\Windows\Fonts\Dengb.ttf"))
    pdfmetrics.registerFont(TTFont("DengMono", r"C:\Windows\Fonts\Deng.ttf"))
    pdfmetrics.registerFontFamily("Deng", normal="Deng", bold="DengBold")

    left = right = 20 * mm
    top = 18 * mm
    bottom = 18 * mm
    frame = Frame(left, bottom, A4[0] - left - right, A4[1] - top - bottom, id="normal")
    document = BaseDocTemplate(
        str(output),
        pagesize=A4,
        leftMargin=left,
        rightMargin=right,
        topMargin=top,
        bottomMargin=bottom,
        title="公司 HR 制度智能问答项目：人机交互对话提炼",
        author="项目组",
    )
    document.addPageTemplates(PageTemplate(id="content", frames=[frame], onPage=page_footer))
    styles = build_styles()
    story = build_story(source.read_text(encoding="utf-8"), styles, A4[0] - left - right)
    document.build(story)
    print(f"Exported {output}")


if __name__ == "__main__":
    main()
