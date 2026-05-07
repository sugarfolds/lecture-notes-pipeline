#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path


DEFAULT_NOTES_PDF = Path("法理学笔记.pdf")
DEFAULT_PPT_DIR = Path("ppt")


@dataclass
class Hit:
    score: float
    source: str
    text: str


def pdf_text(path: Path) -> str:
    return subprocess.run(
        ["pdftotext", str(path), "-"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout


def normalize(text: str) -> str:
    text = re.sub(r"\s+", "", text)
    return re.sub(r"[^\w\u4e00-\u9fff]", "", text)


def char_ngrams(text: str, n: int = 2) -> set[str]:
    normalized = normalize(text)
    if len(normalized) <= n:
        return {normalized} if normalized else set()
    return {normalized[i : i + n] for i in range(len(normalized) - n + 1)}


def score(query: str, candidate: str) -> float:
    q = char_ngrams(query)
    c = char_ngrams(candidate)
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    return overlap / max(len(q), 1) + overlap / max(len(c), 1) * 0.25


def chunks(text: str, window: int = 180) -> list[str]:
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.replace("\f", "\n").splitlines()]
    lines = [line for line in lines if line]
    output: list[str] = []
    current = ""
    for line in lines:
        if len(current) + len(line) <= window:
            current = f"{current} {line}".strip()
        else:
            if current:
                output.append(current)
            current = line
    if current:
        output.append(current)
    return output


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("query")
    parser.add_argument("-n", "--limit", type=int, default=8)
    parser.add_argument("--notes-pdf", type=Path, default=DEFAULT_NOTES_PDF)
    parser.add_argument("--ppt-dir", type=Path, default=DEFAULT_PPT_DIR)
    parser.add_argument(
        "--source",
        type=Path,
        action="append",
        default=[],
        help="额外纳入模糊检索的 PDF 文件，可重复传入",
    )
    args = parser.parse_args()

    sources = []
    if args.notes_pdf.exists():
        sources.append(args.notes_pdf)
    if args.ppt_dir.exists():
        sources.extend(sorted(args.ppt_dir.glob("*.pdf")))
    sources.extend(path for path in args.source if path.exists())

    hits: list[Hit] = []
    for source in sources:
        if not source.exists() or source.name.startswith("."):
            continue
        for chunk in chunks(pdf_text(source)):
            hits.append(Hit(score(args.query, chunk), source.name, chunk))

    for hit in sorted(hits, key=lambda item: item.score, reverse=True)[: args.limit]:
        print(f"{hit.score:.3f}\t{hit.source}\t{hit.text}")


if __name__ == "__main__":
    main()
