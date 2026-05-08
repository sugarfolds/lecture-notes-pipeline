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
    f"{ROOT}/download_canvas_videos.py",
]


def list_processes() -> list[tuple[int, int, str]]:
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
        if any(pattern in command for pattern in PATTERNS):
            rows.append((int(pid_str), int(ppid_str), command))
    return rows


def child_curls(parent_pids: set[int]) -> list[tuple[int, int, str]]:
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
        pid = int(pid_str)
        ppid = int(ppid_str)
        if ppid in parent_pids and "curl -L --fail --retry 3 --output" in command:
            rows.append((pid, ppid, command))
    return rows


def kill_rows(rows: list[tuple[int, int, str]]) -> None:
    for pid, _, _ in rows:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            pass


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--list", action="store_true", help="列出匹配的下载进程")
    parser.add_argument("--kill", action="store_true", help="终止匹配的下载进程")
    args = parser.parse_args()

    parents = list_processes()
    curls = child_curls({pid for pid, _, _ in parents})
    rows = parents + curls

    if not rows:
        print("没有找到下载进程。")
        return

    for pid, ppid, command in rows:
        print(f"{pid}\t{ppid}\t{command}")

    if args.kill:
        kill_rows(curls)
        kill_rows(parents)


if __name__ == "__main__":
    main()
