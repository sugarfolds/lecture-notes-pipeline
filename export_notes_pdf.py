#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
from pathlib import Path

from pypdf import PdfWriter
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer


PAGE_SIZE = A4
FONT_NAME = "LectureNotesFont"
FONT_CANDIDATES = [
    Path(os.environ.get("LECTURE_NOTES_FONT", "")) if os.environ.get("LECTURE_NOTES_FONT") else None,
    Path("/Library/Fonts/Arial Unicode.ttf"),
    Path("/System/Library/Fonts/Supplemental/Arial Unicode.ttf"),
]


def register_fonts() -> None:
    for path in FONT_CANDIDATES:
        if not path:
            continue
        if not path.exists():
            continue
        registerFont(TTFont(FONT_NAME, str(path)))
        return
    raise RuntimeError("未找到可用于中英混排的 TrueType 字体。可通过 LECTURE_NOTES_FONT 指定字体文件路径。")


def natural_key(path: Path) -> tuple:
    parts = re.split(r"(\d+)", path.stem)
    return tuple(int(part) if part.isdigit() else part for part in parts)


def normalize_visual_text(text: str) -> str:
    text = re.sub(r"(\d{4})-(\d{2})-(\d{2})", r"\1年\2月\3日", text)
    text = re.sub(r"(\d{2}:\d{2})-(\d{2}:\d{2})", r"\1 至 \2", text)
    return text


def paragraph_text(text: str) -> str:
    text = normalize_visual_text(text)
    text = text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return text.replace("\n", "<br/>")


def build_styles():
    styles = getSampleStyleSheet()
    base = ParagraphStyle(
        "BaseCN",
        parent=styles["BodyText"],
        fontName=FONT_NAME,
        fontSize=11,
        leading=16,
        alignment=TA_LEFT,
        spaceAfter=4,
    )
    return {
        "title": ParagraphStyle(
            "TitleCN",
            parent=base,
            fontSize=18,
            leading=24,
            spaceAfter=10,
        ),
        "h1": ParagraphStyle(
            "H1CN",
            parent=base,
            fontSize=15,
            leading=20,
            spaceBefore=8,
            spaceAfter=6,
        ),
        "h2": ParagraphStyle(
            "H2CN",
            parent=base,
            fontSize=13,
            leading=18,
            spaceBefore=6,
            spaceAfter=4,
        ),
        "body": base,
        "bullet": ParagraphStyle(
            "BulletCN",
            parent=base,
            leftIndent=12,
            firstLineIndent=-8,
        ),
        "quote": ParagraphStyle(
            "QuoteCN",
            parent=base,
            leftIndent=14,
            textColor="#444444",
        ),
    }


def markdown_to_story(md_path: Path, styles: dict) -> list:
    story = []
    lines = md_path.read_text(encoding="utf-8").splitlines()
    saw_title = False

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            story.append(Spacer(1, 5))
            continue

        if line.startswith("# "):
            style = styles["title"] if not saw_title else styles["h1"]
            story.append(Paragraph(paragraph_text(line[2:].strip()), style))
            saw_title = True
            continue
        if line.startswith("## "):
            story.append(Paragraph(paragraph_text(line[3:].strip()), styles["h2"]))
            continue
        if line.startswith("### "):
            story.append(Paragraph(paragraph_text(line[4:].strip()), styles["h2"]))
            continue
        if line.startswith("- "):
            story.append(Paragraph(paragraph_text(f"• {line[2:].strip()}"), styles["bullet"]))
            continue
        if re.match(r"^\d+\.\s+", line):
            story.append(Paragraph(paragraph_text(line), styles["bullet"]))
            continue
        if line.startswith("> "):
            story.append(Paragraph(paragraph_text(line[2:].strip()), styles["quote"]))
            continue

        story.append(Paragraph(paragraph_text(line), styles["body"]))

    if not saw_title:
        story.insert(0, Paragraph(paragraph_text(md_path.stem.replace("_", " ")), styles["title"]))
        story.insert(1, Spacer(1, 4))

    return story


def export_one(md_path: Path, pdf_path: Path, styles: dict) -> None:
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=PAGE_SIZE,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=18 * mm,
        bottomMargin=18 * mm,
        title=md_path.stem,
    )
    doc.build(markdown_to_story(md_path, styles))


def combine_pdfs(pdf_paths: list[Path], out_path: Path) -> None:
    writer = PdfWriter()
    for pdf in pdf_paths:
        writer.append(str(pdf))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("wb") as f:
        writer.write(f)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--notes-dir", type=Path, default=Path("notes"))
    parser.add_argument("--output-dir", type=Path, default=Path("exports"))
    parser.add_argument("--combine-name", default="法理学_整合笔记汇编.pdf")
    parser.add_argument("--pattern", default="*.md")
    parser.add_argument("--single-only", action="store_true")
    args = parser.parse_args()

    register_fonts()
    styles = build_styles()
    notes = sorted(args.notes_dir.glob(args.pattern), key=natural_key)
    if not notes:
        raise RuntimeError(f"未在 {args.notes_dir} 下找到 {args.pattern}")

    output_dir = args.output_dir
    single_paths: list[Path] = []
    for note in notes:
        out = output_dir / f"{note.stem}.pdf"
        export_one(note, out, styles)
        single_paths.append(out)
        print(out)

    if not args.single_only:
        combined = output_dir / args.combine_name
        combine_pdfs(single_paths, combined)
        print(combined)


if __name__ == "__main__":
    main()
