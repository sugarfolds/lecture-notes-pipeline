#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
from pathlib import Path


def run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True)


def extract_audio(video: Path, audio_dir: Path) -> Path:
    audio_dir.mkdir(parents=True, exist_ok=True)
    out = audio_dir / f"{video.stem}.m4a"
    if out.exists() and out.stat().st_size > 1024 * 1024:
        return out
    run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-b:a",
            "64k",
            str(out),
        ]
    )
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--audio-dir", type=Path, default=Path("audio"))
    args = parser.parse_args()

    for video in args.videos:
        audio = extract_audio(video, args.audio_dir)
        print(audio)


if __name__ == "__main__":
    main()
