#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


PPT_DIR = Path("ppt")
OUT_PATH = Path("slides_index.md")


def extract_lines(pdf: Path) -> list[str]:
    result = subprocess.run(
        ["pdftotext", str(pdf), "-"],
        check=True,
        capture_output=True,
        text=True,
    )
    raw_lines = result.stdout.replace("\f", "\n").splitlines()
    lines: list[str] = []
    seen: set[str] = set()
    for raw in raw_lines:
        line = re.sub(r"\s+", " ", raw).strip()
        if not line or line in seen:
            continue
        seen.add(line)
        lines.append(line)
    return lines


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--ppt-dir", type=Path, default=PPT_DIR)
    parser.add_argument("--output", type=Path, default=OUT_PATH)
    args = parser.parse_args()

    rows = ["# 法理学课件索引", ""]
    for pdf in sorted(args.ppt_dir.glob("*.pdf")):
        lines = extract_lines(pdf)
        preview = lines[:10]
        rows.append(f"## {pdf.name}")
        rows.append("")
        for line in preview:
            rows.append(f"- {line}")
        rows.append("")
    args.output.write_text("\n".join(rows), encoding="utf-8")


if __name__ == "__main__":
    main()
