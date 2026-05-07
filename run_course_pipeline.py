#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DOWNLOAD_SCRIPT = ROOT / "download_canvas_videos.py"
PROCESS_SCRIPT = ROOT / "process_lecture.py"
DOWNLOAD_DIR = ROOT / "downloads"


def lecture_number(path: Path) -> int:
    match = re.search(r"第(\d+)课时", path.name)
    if not match:
        raise RuntimeError(f"无法解析课时号: {path}")
    return int(match.group(1))


def existing_videos() -> dict[int, Path]:
    videos: dict[int, Path] = {}
    for path in sorted(DOWNLOAD_DIR.glob("*.mp4")):
        videos[lecture_number(path)] = path
    return videos


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def download_lectures(start: int, end: int) -> None:
    wanted = list(range(start, end + 1))
    args = ["python3", str(DOWNLOAD_SCRIPT), *[str(item) for item in wanted]]
    run(args)


def transcribe_lectures(start: int, end: int) -> None:
    videos = existing_videos()
    targets = [videos[idx] for idx in range(start, end + 1) if idx in videos]
    if not targets:
        raise RuntimeError(f"未找到第 {start}-{end} 课时视频")
    run(["python3", str(PROCESS_SCRIPT), *[str(path) for path in targets]])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--start", type=int, required=True)
    parser.add_argument("--end", type=int, required=True)
    parser.add_argument(
        "--step",
        choices=["download", "transcribe", "all"],
        default="all",
    )
    args = parser.parse_args()

    if args.start > args.end:
        raise RuntimeError("start 不能大于 end")

    if args.step in {"download", "all"}:
        download_lectures(args.start, args.end)
    if args.step in {"transcribe", "all"}:
        transcribe_lectures(args.start, args.end)


if __name__ == "__main__":
    main()
