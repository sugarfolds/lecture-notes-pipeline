#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path

import mlx_whisper


MODEL = "mlx-community/whisper-large-v3-turbo"
PROMPT = (
    "中文法学研究生课程。关键词：宪法学、法理学、民法、司法制度、基本权利、"
    "公共权力、司法权、案例、制度名称、法律术语。"
)

def resolve_model_path(model_ref: str) -> str:
    if Path(model_ref).exists():
        return model_ref
    if "/" not in model_ref:
        return model_ref

    owner, name = model_ref.split("/", 1)
    hub_root = Path(os.environ.get("HF_HUB_CACHE", Path.home() / ".cache" / "huggingface" / "hub"))
    model_root = hub_root / f"models--{owner}--{name}"
    snapshots_dir = model_root / "snapshots"
    if snapshots_dir.exists():
        snapshots = sorted(p for p in snapshots_dir.iterdir() if p.is_dir())
        if snapshots:
            return str(snapshots[-1])
    return model_ref


def resolve_audio_input(path: Path, audio_dir: Path) -> Path:
    if path.suffix.lower() in {".m4a", ".mp3", ".wav", ".flac", ".aac"}:
        return path

    candidate = audio_dir / f"{path.stem}.m4a"
    if candidate.exists() and candidate.stat().st_size > 1024 * 1024:
        return candidate

    raise RuntimeError(
        f"未找到与视频对应的音频文件: {candidate}。"
        "请先运行 extract_audio.py，或直接传入 audio/*.m4a。"
    )


def transcribe(audio: Path, transcript_dir: Path, verbose: bool = False) -> Path:
    transcript_dir.mkdir(parents=True, exist_ok=True)
    base = transcript_dir / audio.stem
    txt_path = base.with_suffix(".txt")
    json_path = base.with_suffix(".json")
    if txt_path.exists() and json_path.exists():
        return txt_path

    model_path = resolve_model_path(MODEL)
    result = mlx_whisper.transcribe(
        str(audio),
        path_or_hf_repo=model_path,
        language="zh",
        task="transcribe",
        verbose=verbose,
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
    parser.add_argument("inputs", nargs="+", type=Path)
    parser.add_argument("--audio-dir", type=Path, default=Path("audio"))
    parser.add_argument("--transcript-dir", type=Path, default=Path("transcripts"))
    parser.add_argument("--verbose-transcript", action="store_true")
    args = parser.parse_args()

    for input_path in args.inputs:
        audio = resolve_audio_input(input_path, args.audio_dir)
        transcript = transcribe(audio, args.transcript_dir, verbose=args.verbose_transcript)
        print(transcript)


if __name__ == "__main__":
    main()
