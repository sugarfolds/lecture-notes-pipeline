#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import signal
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PATTERNS = [
    "download_canvas_videos.py",
    "process_lecture.py",
    f"{ROOT}/download_canvas_videos.py",
    f"{ROOT}/process_lecture.py",
]


def ps_rows() -> list[tuple[int, int, str]]:
    result = subprocess.run(
        ["ps", "-axo", "pid=,ppid=,command="],
        check=True,
        capture_output=True,
        text=True,
    )
    rows: list[tuple[int, int, str]] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        pid_str, ppid_str, command = line.split(None, 2)
        rows.append((int(pid_str), int(ppid_str), command))
    return rows


def matching_parent_rows(rows: list[tuple[int, int, str]]) -> list[tuple[int, int, str]]:
    return [row for row in rows if any(pattern in row[2] for pattern in PATTERNS)]


def matching_child_rows(rows: list[tuple[int, int, str]], parent_pids: set[int]) -> list[tuple[int, int, str]]:
    matches: list[tuple[int, int, str]] = []
    for pid, ppid, command in rows:
        if ppid not in parent_pids:
            continue
        if "curl -L --fail --retry 3 --output" in command:
            matches.append((pid, ppid, command))
        elif "ffmpeg" in command:
            matches.append((pid, ppid, command))
    return matches


def kill_rows(rows: list[tuple[int, int, str]]) -> None:
    for pid, _, _ in rows:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="列出匹配的课程处理进程")
    parser.add_argument("--kill", action="store_true", help="终止匹配的课程处理进程")
    args = parser.parse_args()

    rows = ps_rows()
    parents = matching_parent_rows(rows)
    children = matching_child_rows(rows, {pid for pid, _, _ in parents})
    matches = parents + children

    if not matches:
        print("没有找到课程处理进程。")
        return

    for pid, ppid, command in matches:
        print(f"{pid}\t{ppid}\t{command}")

    if args.kill:
        kill_rows(children)
        kill_rows(parents)


if __name__ == "__main__":
    main()
