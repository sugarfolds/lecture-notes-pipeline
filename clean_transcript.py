#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path


NOISE_PATTERNS = [
    "请保留法律师",
    "请不吝点赞",
    "订阅",
    "转发",
    "打赏支持",
]


def is_noise(text: str) -> bool:
    if not text.strip():
        return True
    if any(item in text for item in NOISE_PATTERNS):
        return True
    compact = re.sub(r"\s+", "", text)
    if compact and len(set(compact)) == 1 and len(compact) <= 8:
        return True
    return False


def clean_lines(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    for line in lines:
        match = re.match(r"^\[(.*?)\]\s*(.*)$", line)
        if not match:
            continue
        text = match.group(2).strip()
        if is_noise(text):
            continue
        cleaned.append(line)
    return cleaned


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("path", type=Path)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    source = args.path
    target = args.output or source.with_name(source.stem + "_cleaned.txt")
    lines = source.read_text(encoding="utf-8").splitlines()
    target.write_text("\n".join(clean_lines(lines)), encoding="utf-8")
    print(target)


if __name__ == "__main__":
    main()
