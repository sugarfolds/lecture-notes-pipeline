#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import requests


BASE_URL = os.environ.get("CANVAS_BASE_URL", "https://v.sjtu.edu.cn/jy-application-canvas-sjtu")
SESSION_STORAGE = Path(
    os.environ.get(
        "CANVAS_SESSION_STORAGE",
        "~/Library/Application Support/Google/Chrome/Default/Session Storage",
    )
).expanduser()
DEFAULT_OUTPUT_DIR = Path("downloads")
DEFAULT_MIN_BYTES = 50 * 1024 * 1024
DEFAULT_MIN_DURATION = 600


@dataclass
class SessionState:
    token: str
    cour_id: str | None = None
    lti_course_id: str | None = None
    client_id: str | None = None


@dataclass
class StreamChoice:
    url: str
    view_num: int
    channel_num: int
    content_length: int
    raw: dict[str, Any]


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text())


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def append_run_log(runs_dir: Path, event: str, payload: dict[str, Any]) -> None:
    runs_dir.mkdir(parents=True, exist_ok=True)
    log_path = runs_dir / f"{datetime.now().strftime('%Y%m%d')}.jsonl"
    row = {"time": now_iso(), "event": event, **payload}
    with log_path.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def utf16_field(text: str, field: str) -> str | None:
    match = re.search(fr'"{field}":"([^"]+)"', text)
    return match.group(1) if match else None


def resolve_session_storage(path: Path) -> Path:
    if path.is_file():
        return path
    if not path.exists():
        raise RuntimeError(f"Session Storage 路径不存在: {path}")
    candidates = sorted(path.glob("*.log"), key=lambda item: item.stat().st_mtime, reverse=True)
    if not candidates:
        raise RuntimeError(f"未在 {path} 下找到任何 .log 会话文件")
    return candidates[0]


def load_session_state(path: Path = SESSION_STORAGE) -> SessionState:
    resolved = resolve_session_storage(path)
    blob = resolved.read_bytes()
    token_state: SessionState | None = None
    metadata_state: SessionState | None = None

    for match in re.finditer(rb"map-\d+-Canvas_UserState", blob):
        snippet = blob[match.start() : match.start() + 20000].decode("utf-16le", "ignore")
        token = utf16_field(snippet, "token")
        cour_id = utf16_field(snippet, "courId")
        lti_course_id = utf16_field(snippet, "ltiCourseId")
        client_id = utf16_field(snippet, "clientId")
        if token:
            token_state = SessionState(token=token)
        if token and cour_id and lti_course_id:
            metadata_state = SessionState(
                token=token,
                cour_id=cour_id,
                lti_course_id=lti_course_id,
                client_id=client_id,
            )

    if not token_state:
        raise RuntimeError(f"无法从 {resolved} 读取 Canvas token")
    if not metadata_state:
        raise RuntimeError(f"无法从 {resolved} 读取课程参数")
    return SessionState(
        token=token_state.token,
        cour_id=metadata_state.cour_id,
        lti_course_id=metadata_state.lti_course_id,
        client_id=metadata_state.client_id,
    )


def api_post(
    session: requests.Session,
    path: str,
    *,
    token: str,
    json_body: dict[str, Any] | None = None,
    form_body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"token": token}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        response = session.post(f"{BASE_URL}{path}", headers=headers, json=json_body, timeout=30)
    else:
        response = session.post(f"{BASE_URL}{path}", headers=headers, data=form_body, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if str(payload.get("code")) != "0":
        raise RuntimeError(f"{path} 返回失败: {payload}")
    return payload


def fetch_video_list(session: requests.Session, state: SessionState) -> list[dict[str, Any]]:
    payload = api_post(
        session,
        "/directOnDemandPlay/findVodVideoList",
        token=state.token,
        json_body={"canvasCourseId": state.cour_id},
    )
    return payload["data"]["records"]


def fetch_streams(session: requests.Session, state: SessionState, video_id: str) -> list[dict[str, Any]]:
    payload = api_post(
        session,
        "/directOnDemandPlay/getVodVideoInfos",
        token=state.token,
        form_body={"id": video_id, "playTypeHls": "true", "isAudit": "true"},
    )
    return payload["data"]["videoPlayResponseVoList"]


def probe_stream(session: requests.Session, url: str) -> int:
    response = session.head(url, allow_redirects=True, timeout=30)
    response.raise_for_status()
    return int(response.headers.get("Content-Length") or 0)


def choose_stream(session: requests.Session, streams: list[dict[str, Any]], view_num: int | None = None) -> StreamChoice:
    candidates: list[StreamChoice] = []
    for stream in streams:
        url = stream.get("rtmpUrlHdv")
        if not url:
            continue
        current_view = int(stream.get("cdviViewNum") or stream.get("cdviChannelNum") or 0)
        if view_num is not None and current_view != view_num:
            continue
        size = probe_stream(session, url)
        candidates.append(
            StreamChoice(
                url=url,
                view_num=current_view,
                channel_num=int(stream.get("cdviChannelNum") or 0),
                content_length=size,
                raw=stream,
            )
        )
    if not candidates:
        raise RuntimeError("没有可下载的视频流")
    return min(candidates, key=lambda item: (item.content_length or 10**18, item.channel_num))


def lecture_index(record: dict[str, Any]) -> int:
    match = re.search(r"第(\d+)讲", record["videoName"])
    if not match:
        raise RuntimeError(f"无法从标题解析课时序号: {record['videoName']}")
    return int(match.group(1))


def course_slug(record: dict[str, Any]) -> str:
    raw = record["videoName"]
    label = re.sub(r"\(第\d+讲\)", "", raw).strip()
    label = re.sub(r"[^\w\u4e00-\u9fff]+", "", label)
    return label or "课程"


def output_name(record: dict[str, Any]) -> str:
    index = lecture_index(record)
    start = datetime.strptime(record["courseBeginTime"], "%Y-%m-%d %H:%M:%S")
    return f"{course_slug(record)}_第{index:02d}课时_{start:%Y-%m-%d_%H%M}.mp4"


def parse_targets(records: Iterable[dict[str, Any]], numbers: list[int] | None) -> list[dict[str, Any]]:
    if not numbers:
        return list(records)
    wanted = set(numbers)
    selected = [record for record in records if lecture_index(record) in wanted]
    missing = sorted(wanted - {lecture_index(record) for record in selected})
    if missing:
        raise RuntimeError(f"未找到这些课时: {missing}")
    return selected


def default_manifest_path(output_dir: Path) -> Path:
    return output_dir / "canvas_download_manifest.json"


def default_status_path(output_dir: Path) -> Path:
    return output_dir / "download_status.json"


def default_runs_dir(output_dir: Path) -> Path:
    return output_dir / "download_runs"


def load_status(path: Path) -> dict[str, Any]:
    return read_json(path, {"schema_version": 1, "updated_at": None, "items": {}})


def save_status(path: Path, status: dict[str, Any]) -> None:
    status["updated_at"] = now_iso()
    write_json(path, status)


def set_status(
    status: dict[str, Any],
    label: str,
    state: str,
    *,
    entry: dict[str, Any] | None = None,
    error: str | None = None,
    verification: dict[str, Any] | None = None,
) -> None:
    item = status.setdefault("items", {}).setdefault(label, {})
    item["state"] = state
    item["updated_at"] = now_iso()
    if entry:
        item.update(
            {
                "lecture": entry.get("lecture"),
                "videoName": entry.get("videoName"),
                "beginTime": entry.get("beginTime"),
                "channel": entry.get("channel"),
                "view": entry.get("view"),
                "sizeBytes": entry.get("sizeBytes"),
                "output": entry.get("output"),
            }
        )
    if error:
        item["error"] = error
    else:
        item.pop("error", None)
    if verification:
        item["verification"] = verification


def probe_duration(path: Path) -> float | None:
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v",
                "error",
                "-show_entries",
                "format=duration",
                "-of",
                "default=noprint_wrappers=1:nokey=1",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if result.returncode != 0:
        return None
    try:
        return float(result.stdout.strip())
    except ValueError:
        return None


def verify_video(path: Path, min_bytes: int, min_duration: int) -> dict[str, Any]:
    errors: list[str] = []
    size = path.stat().st_size if path.exists() else 0
    duration = probe_duration(path) if path.exists() else None
    if not path.exists():
        errors.append("missing")
    elif size < min_bytes:
        errors.append(f"too_small:{size}")
    if duration is not None and duration < min_duration:
        errors.append(f"too_short:{duration:.1f}")
    return {
        "ok": not errors,
        "path": str(path),
        "size": size,
        "duration": duration,
        "errors": errors,
        "checked_at": now_iso(),
    }


def download(url: str, out: Path, expected_size: int, *, resume: bool) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    part = out.with_suffix(out.suffix + ".part")
    command = [
        "curl",
        "-L",
        "--fail",
        "--retry",
        "3",
        "--output",
        str(part),
    ]
    if resume and part.exists():
        command[1:1] = ["-C", "-"]
    command.append(url)
    subprocess.run(command, check=True)
    if expected_size > 0 and abs(part.stat().st_size - expected_size) > max(1024 * 1024, expected_size // 100):
        raise RuntimeError(f"downloaded size mismatch: got {part.stat().st_size}, expected {expected_size}")
    part.replace(out)


def manifest_entry(record: dict[str, Any], choice: StreamChoice, out: Path) -> dict[str, Any]:
    return {
        "lecture": lecture_index(record),
        "label": f"第{lecture_index(record):02d}课时",
        "videoName": record["videoName"],
        "beginTime": record["courseBeginTime"],
        "videoId": record["videoId"],
        "channel": choice.channel_num,
        "view": choice.view_num,
        "sizeBytes": choice.content_length,
        "output": str(out),
        "url": choice.url,
    }


def print_status(status_path: Path, status: dict[str, Any]) -> None:
    items = status.get("items") or {}
    if not items:
        print(f"{status_path}: no status records")
        return
    counts: dict[str, int] = {}
    for item in items.values():
        state = item.get("state", "unknown")
        counts[state] = counts.get(state, 0) + 1
    print(f"status_file: {status_path}")
    print(f"updated_at: {status.get('updated_at')}")
    print("summary:")
    for state, count in sorted(counts.items()):
        print(f"  {state}: {count}")
    print("items:")
    for label in sorted(items):
        item = items[label]
        suffix = ""
        if item.get("error"):
            suffix = f" error={item['error']}"
        verification = item.get("verification") or {}
        if verification.get("ok"):
            suffix += f" size={verification.get('size')} duration={verification.get('duration')}"
        print(f"  {label}: {item.get('state')}{suffix}")


def verify_manifest_entries(
    manifest: list[dict[str, Any]],
    status: dict[str, Any],
    *,
    min_bytes: int,
    min_duration: int,
) -> int:
    failures = 0
    for entry in manifest:
        label = entry["label"]
        path = Path(entry["output"])
        verification = verify_video(path, min_bytes, min_duration)
        state = "verified" if verification["ok"] else "failed"
        error = None if verification["ok"] else ",".join(verification["errors"])
        set_status(status, label, state, entry=entry, error=error, verification=verification)
        print(f"[{state}] {label} {path.name}")
        if not verification["ok"]:
            failures += 1
    return failures


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("lectures", nargs="*", type=int, help="要下载的课时编号，例如 4 5 6")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--session-storage", type=Path, default=SESSION_STORAGE)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--list-only", action="store_true", help="兼容旧参数：列出目标并写 manifest，不下载")
    parser.add_argument("--sync-details", action="store_true", help="刷新列表与 manifest，不下载")
    parser.add_argument("--download", action="store_true", help="刷新 manifest 后下载目标课时")
    parser.add_argument("--resume", action="store_true", help="续用已有 .part 文件")
    parser.add_argument("--retry-failed", action="store_true", help="只重试状态为 failed 的条目")
    parser.add_argument("--verify-only", action="store_true", help="只按 manifest 校验本地视频")
    parser.add_argument("--status", action="store_true", help="打印状态文件")
    parser.add_argument("--max-count", type=int, help="本轮最多下载多少个条目")
    parser.add_argument("--view-num", type=int, help="指定 cdviViewNum；不指定时选择最小可下载流")
    parser.add_argument("--min-bytes", type=int, default=DEFAULT_MIN_BYTES)
    parser.add_argument("--min-duration", type=int, default=DEFAULT_MIN_DURATION)
    args = parser.parse_args()

    output_dir = args.output_dir
    manifest_path = args.manifest or default_manifest_path(output_dir)
    status_path = args.status_file or default_status_path(output_dir)
    runs_dir = args.runs_dir or default_runs_dir(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    status = load_status(status_path)

    if args.status:
        print_status(status_path, status)
        return 0

    if args.verify_only:
        if not manifest_path.exists():
            raise RuntimeError(f"manifest 不存在，先运行 --sync-details: {manifest_path}")
        manifest = read_json(manifest_path, [])
        if not isinstance(manifest, list):
            raise RuntimeError(f"manifest 格式不是列表: {manifest_path}")
        failures = verify_manifest_entries(
            manifest,
            status,
            min_bytes=args.min_bytes,
            min_duration=args.min_duration,
        )
        save_status(status_path, status)
        append_run_log(runs_dir, "verify_only", {"manifest": str(manifest_path), "failures": failures})
        return 1 if failures else 0

    should_download = args.download or not (args.sync_details or args.list_only)
    if args.retry_failed:
        should_download = True

    state = load_session_state(args.session_storage.expanduser())
    downloaded_count = 0
    manifest: list[dict[str, Any]] = []
    with requests.Session() as session:
        records = fetch_video_list(session, state)
        targets = parse_targets(records, args.lectures)
        for record in targets:
            idx = lecture_index(record)
            streams = fetch_streams(session, state, record["videoId"])
            choice = choose_stream(session, streams, view_num=args.view_num)
            out = args.output_dir / output_name(record)
            entry = manifest_entry(record, choice, out)
            manifest.append(entry)

            label = entry["label"]
            current_state = (status.get("items") or {}).get(label, {}).get("state")
            if not should_download:
                set_status(status, label, "pending", entry=entry)
                continue
            if args.retry_failed and current_state != "failed":
                print(f"[skip] {label} 当前状态不是 failed")
                set_status(status, label, current_state or "pending", entry=entry)
                continue
            if args.max_count is not None and downloaded_count >= args.max_count:
                print(f"[pending] {label} 达到 --max-count，留待下轮")
                set_status(status, label, current_state or "pending", entry=entry)
                continue

            precheck = verify_video(out, args.min_bytes, args.min_duration)
            if precheck["ok"]:
                print(f"[verified] {label} 已存在 {out}")
                set_status(status, label, "verified", entry=entry, verification=precheck)
                continue

            set_status(status, label, "downloading", entry=entry)
            save_status(status_path, status)
            append_run_log(runs_dir, "download_start", {"label": label, "output": str(out)})
            try:
                download(choice.url, out, choice.content_length, resume=args.resume)
                verification = verify_video(out, args.min_bytes, args.min_duration)
                if verification["ok"]:
                    print(f"[verified] {label} {out}")
                    set_status(status, label, "verified", entry=entry, verification=verification)
                    append_run_log(runs_dir, "download_verified", {"label": label, "verification": verification})
                else:
                    error = ",".join(verification["errors"])
                    print(f"[failed] {label} {error}", file=sys.stderr)
                    set_status(status, label, "failed", entry=entry, error=error, verification=verification)
                    append_run_log(runs_dir, "download_failed", {"label": label, "error": error})
            except Exception as exc:
                print(f"[error] {label} {exc}", file=sys.stderr)
                set_status(status, label, "failed", entry=entry, error=str(exc))
                append_run_log(runs_dir, "download_error", {"label": label, "error": str(exc)})
            finally:
                save_status(status_path, status)
            downloaded_count += 1

    write_json(manifest_path, manifest)
    save_status(status_path, status)
    append_run_log(
        runs_dir,
        "run_complete",
        {
            "manifest": str(manifest_path),
            "downloaded_count": downloaded_count,
            "should_download": should_download,
        },
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    print(f"[manifest] {manifest_path}")
    print(f"[status] {status_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
