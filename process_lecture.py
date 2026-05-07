#!/usr/bin/env python3
import argparse
import json
import subprocess
from pathlib import Path

import mlx_whisper


MODEL = "mlx-community/whisper-large-v3-turbo"
PROMPT = (
    "中文法理学研究生课程。关键词：法理学、习近平法治思想、法律思维、法律方法、"
    "判例、利益衡量、司法改革、商事合规、计算法学、中国特色社会主义法治体系、"
    "案例、制度名称、法律术语。"
)


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


def transcribe(audio: Path, transcript_dir: Path) -> Path:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    base = transcript_dir / audio.stem
    txt_path = base.with_suffix(".txt")
    json_path = base.with_suffix(".json")
    if txt_path.exists() and json_path.exists():
        return txt_path

    result = mlx_whisper.transcribe(
        str(audio),
        path_or_hf_repo=MODEL,
        language="zh",
        task="transcribe",
        verbose=True,
        word_timestamps=False,
        initial_prompt=PROMPT,
    )
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    lines = []
    for seg in result.get("segments", []):
        start = seg["start"] / 60
        end = seg["end"] / 60
        text = seg["text"].strip()
        lines.append(f"[{start:05.2f}-{end:05.2f}] {text}")
    txt_path.write_text("\n".join(lines), encoding="utf-8")
    return txt_path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("videos", nargs="+", type=Path)
    parser.add_argument("--audio-dir", type=Path, default=Path("audio"))
    parser.add_argument("--transcript-dir", type=Path, default=Path("transcripts"))
    args = parser.parse_args()

    for video in args.videos:
        audio = extract_audio(video, args.audio_dir)
        transcript = transcribe(audio, args.transcript_dir)
        print(transcript)


if __name__ == "__main__":
    main()
