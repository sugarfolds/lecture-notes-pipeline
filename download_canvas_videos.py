#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable

import requests


BASE_URL = os.environ.get("CANVAS_BASE_URL", "https://v.sjtu.edu.cn/jy-application-canvas-sjtu")
SESSION_STORAGE = Path(
    os.environ.get(
        "CANVAS_SESSION_STORAGE",
        "~/Library/Application Support/Google/Chrome/Default/Session Storage",
    )
).expanduser()
DEFAULT_OUTPUT_DIR = Path("downloads")


@dataclass
class SessionState:
    token: str
    cour_id: str | None = None
    lti_course_id: str | None = None
    client_id: str | None = None


@dataclass
class StreamChoice:
    url: str
    channel_num: int
    content_length: int


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
        raise RuntimeError(f"无法从 {path} 读取 Canvas token")
    if not metadata_state:
        raise RuntimeError(f"无法从 {path} 读取课程参数")
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
    json_body: dict | None = None,
    form_body: dict | None = None,
) -> dict:
    headers = {"token": token}
    if json_body is not None:
        headers["Content-Type"] = "application/json"
        response = session.post(f"{BASE_URL}{path}", headers=headers, json=json_body, timeout=30)
    else:
        response = session.post(f"{BASE_URL}{path}", headers=headers, data=form_body, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "0":
        raise RuntimeError(f"{path} 返回失败: {payload}")
    return payload


def fetch_video_list(session: requests.Session, state: SessionState) -> list[dict]:
    payload = api_post(
        session,
        "/directOnDemandPlay/findVodVideoList",
        token=state.token,
        json_body={"canvasCourseId": state.cour_id},
    )
    return payload["data"]["records"]


def fetch_streams(session: requests.Session, state: SessionState, video_id: str) -> list[dict]:
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


def choose_smallest_stream(session: requests.Session, streams: list[dict]) -> StreamChoice:
    candidates: list[StreamChoice] = []
    for stream in streams:
        url = stream.get("rtmpUrlHdv")
        if not url:
            continue
        size = probe_stream(session, url)
        candidates.append(
            StreamChoice(
                url=url,
                channel_num=int(stream.get("cdviChannelNum") or 0),
                content_length=size,
            )
        )
    if not candidates:
        raise RuntimeError("没有可下载的视频流")
    return min(candidates, key=lambda item: (item.content_length or 10**18, item.channel_num))


def lecture_index(record: dict) -> int:
    match = re.search(r"第(\d+)讲", record["videoName"])
    if not match:
        raise RuntimeError(f"无法从标题解析课时序号: {record['videoName']}")
    return int(match.group(1))


def output_name(record: dict) -> str:
    index = lecture_index(record)
    start = datetime.strptime(record["courseBeginTime"], "%Y-%m-%d %H:%M:%S")
    return f"法理学研_第{index:02d}课时_{start:%Y-%m-%d_%H%M}.mp4"


def is_complete_file(out: Path, expected_size: int) -> bool:
    if not out.exists():
        return False
    if expected_size <= 0:
        return out.stat().st_size > 100 * 1024 * 1024
    actual_size = out.stat().st_size
    return abs(actual_size - expected_size) <= max(1024 * 1024, expected_size // 100)


def download(url: str, out: Path, expected_size: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    if is_complete_file(out, expected_size):
        return
    if out.exists():
        out.unlink()
    subprocess.run(
        [
            "curl",
            "-L",
            "--fail",
            "--retry",
            "3",
            "--output",
            str(out),
            url,
        ],
        check=True,
    )


def parse_targets(records: Iterable[dict], numbers: list[int] | None) -> list[dict]:
    if not numbers:
        return list(records)
    wanted = set(numbers)
    selected = [record for record in records if lecture_index(record) in wanted]
    missing = sorted(wanted - {lecture_index(record) for record in selected})
    if missing:
        raise RuntimeError(f"未找到这些课时: {missing}")
    return selected


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("lectures", nargs="*", type=int, help="要下载的课时编号，例如 4 5 6")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--session-storage", type=Path, default=SESSION_STORAGE)
    parser.add_argument("--list-only", action="store_true")
    args = parser.parse_args()

    state = load_session_state(args.session_storage.expanduser())
    with requests.Session() as session:
        records = fetch_video_list(session, state)
        targets = parse_targets(records, args.lectures)
        summary = []
        for record in targets:
            idx = lecture_index(record)
            streams = fetch_streams(session, state, record["videoId"])
            choice = choose_smallest_stream(session, streams)
            out = args.output_dir / output_name(record)
            summary.append(
                {
                    "lecture": idx,
                    "videoName": record["videoName"],
                    "beginTime": record["courseBeginTime"],
                    "channel": choice.channel_num,
                    "sizeBytes": choice.content_length,
                    "output": str(out),
                }
            )
            if not args.list_only:
                download(choice.url, out, choice.content_length)
        print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
