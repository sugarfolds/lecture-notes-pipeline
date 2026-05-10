#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os
import re
import subprocess
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent
MATERIALS_SCRIPT = ROOT / "download_canvas_materials.py"
DOWNLOAD_SCRIPT = ROOT / "download_canvas_videos.py"
PROCESS_SCRIPT = ROOT / "process_lecture.py"


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, cwd=ROOT, check=True)


def lecture_number(path: Path) -> int:
    match = re.search(r"第(\d+)课时", path.name)
    if not match:
        raise RuntimeError(f"无法解析课时号: {path}")
    return int(match.group(1))


def parse_steps(raw: str) -> list[str]:
    if raw == "all":
        return ["materials", "videos", "transcribe"]
    steps = [item.strip() for item in raw.split(",") if item.strip()]
    allowed = {"materials", "videos", "transcribe"}
    unknown = sorted(set(steps) - allowed)
    if unknown:
        raise RuntimeError(f"未知 steps: {unknown}")
    return steps


def lecture_args(start: int | None, end: int | None) -> list[str]:
    if start is None and end is None:
        return []
    if start is None or end is None:
        raise RuntimeError("--start 和 --end 需要同时提供")
    if start > end:
        raise RuntimeError("start 不能大于 end")
    return [str(item) for item in range(start, end + 1)]


def existing_videos(download_dir: Path, start: int | None, end: int | None) -> list[Path]:
    videos = sorted(download_dir.glob("*.mp4"))
    if start is None and end is None:
        return videos
    selected: list[Path] = []
    for path in videos:
        try:
            idx = lecture_number(path)
        except RuntimeError:
            continue
        if start is not None and end is not None and start <= idx <= end:
            selected.append(path)
    return selected


def chrome_cookie_file(domain: str) -> tempfile.NamedTemporaryFile[str]:
    try:
        import browser_cookie3
    except ImportError as exc:
        raise RuntimeError("--from-chrome requires browser-cookie3") from exc

    jar = browser_cookie3.chrome(domain_name=domain)
    parts = [f"{cookie.name}={cookie.value}" for cookie in jar if cookie.name and cookie.value]
    if not parts:
        raise RuntimeError(f"Chrome 中没有找到 {domain} 的可用 cookie")
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", prefix="lecture-notes-cookies-", suffix=".txt", delete=False)
    handle.write("; ".join(parts))
    handle.flush()
    handle.close()
    os.chmod(handle.name, 0o600)
    return handle


def materials_command(args: argparse.Namespace) -> list[str]:
    cmd = [
        "python3",
        str(MATERIALS_SCRIPT),
        "--course-id",
        args.course_id,
        "--output-dir",
        str(args.course_root / "materials"),
    ]
    if args.from_chrome:
        cmd.append("--from-chrome")
        cmd.extend(["--cookie-domain", args.cookie_domain])
    if args.canvas_cookie_file:
        cmd.extend(["--canvas-cookie-file", str(args.canvas_cookie_file)])
    if args.canvas_cookie:
        cmd.extend(["--canvas-cookie", args.canvas_cookie])
    if args.download:
        cmd.extend(["--download", "--resume", "--max-count", str(args.max_count)])
    else:
        cmd.append("--sync-details")
    return cmd


def videos_command(args: argparse.Namespace, cookie_file: Path | None) -> list[str]:
    cmd = [
        "python3",
        str(DOWNLOAD_SCRIPT),
        "--source",
        "sjtu-lti",
        "--course-id",
        args.course_id,
        "--output-dir",
        str(args.course_root / "downloads"),
        *lecture_args(args.start, args.end),
    ]
    if cookie_file is not None:
        cmd.extend(["--canvas-cookie-file", str(cookie_file)])
    elif args.canvas_cookie_file:
        cmd.extend(["--canvas-cookie-file", str(args.canvas_cookie_file)])
    elif args.canvas_cookie:
        cmd.extend(["--canvas-cookie", args.canvas_cookie])
    else:
        raise RuntimeError("videos step needs --from-chrome, --canvas-cookie-file, or --canvas-cookie")
    if args.download:
        cmd.extend(["--download", "--resume", "--max-count", str(args.max_count)])
    else:
        cmd.append("--sync-details")
    return cmd


def transcribe_command(args: argparse.Namespace) -> list[str]:
    targets = existing_videos(args.course_root / "downloads", args.start, args.end)
    if not targets:
        raise RuntimeError(f"未找到可转写视频: {args.course_root / 'downloads'}")
    return [
        "python3",
        str(PROCESS_SCRIPT),
        *[str(path) for path in targets],
        "--audio-dir",
        str(args.course_root / "audio"),
        "--transcript-dir",
        str(args.course_root / "transcripts"),
    ]


def run_modern(args: argparse.Namespace) -> None:
    if not args.course_id:
        raise RuntimeError("new pipeline mode needs --course-id")
    args.course_root.mkdir(parents=True, exist_ok=True)
    steps = parse_steps(args.steps)

    temp_cookie: tempfile.NamedTemporaryFile[str] | None = None
    try:
        if args.from_chrome and "videos" in steps:
            temp_cookie = chrome_cookie_file(args.cookie_domain)
        for step in steps:
            if step == "materials":
                run(materials_command(args))
            elif step == "videos":
                run(videos_command(args, Path(temp_cookie.name) if temp_cookie else None))
            elif step == "transcribe":
                run(transcribe_command(args))
    finally:
        if temp_cookie is not None:
            try:
                Path(temp_cookie.name).unlink()
            except FileNotFoundError:
                pass


def run_legacy(args: argparse.Namespace) -> None:
    if args.start is None or args.end is None:
        raise RuntimeError("legacy mode needs --start and --end")
    if args.start > args.end:
        raise RuntimeError("start 不能大于 end")
    course_root = ROOT
    if args.step in {"download", "all"}:
        run(
            [
                "python3",
                str(DOWNLOAD_SCRIPT),
                *lecture_args(args.start, args.end),
                "--download",
                "--resume",
            ]
        )
    if args.step in {"transcribe", "all"}:
        targets = existing_videos(course_root / "downloads", args.start, args.end)
        if not targets:
            raise RuntimeError(f"未找到第 {args.start}-{args.end} 课时视频")
        run(["python3", str(PROCESS_SCRIPT), *[str(path) for path in targets]])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", help="Canvas course id for modern materials/videos pipeline")
    parser.add_argument("--course-root", type=Path, default=Path("."))
    parser.add_argument("--steps", help="Comma-separated modern steps: materials,videos,transcribe, or all")
    parser.add_argument("--download", action="store_true", help="Download materials/videos; default is sync-details only")
    parser.add_argument("--max-count", type=int, default=3, help="Max material/video entries to download per run")
    parser.add_argument("--from-chrome", action="store_true", help="Load Canvas cookies from local Chrome")
    parser.add_argument("--cookie-domain", default=".sjtu.edu.cn")
    parser.add_argument("--canvas-cookie-file", type=Path)
    parser.add_argument("--canvas-cookie")
    parser.add_argument("--start", type=int)
    parser.add_argument("--end", type=int)
    parser.add_argument(
        "--step",
        choices=["download", "transcribe", "all"],
        default="all",
        help="Legacy video-only step; use --steps for the modern pipeline",
    )
    args = parser.parse_args()

    if args.steps:
        run_modern(args)
    else:
        run_legacy(args)


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as exc:
        print(f"[error] {exc}")
        raise SystemExit(1)
