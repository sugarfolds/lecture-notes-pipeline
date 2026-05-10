#!/usr/bin/env python3
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

import requests


OC_BASE_URL = "https://oc.sjtu.edu.cn"
CANVAS_API_ROOT = f"{OC_BASE_URL}/api/v1"
DEFAULT_OUTPUT_DIR = Path("materials")
ASSIGNMENT_API_ENDPOINT_PATTERN = re.compile(r'data-api-endpoint="([^"]*?/api/v1/(?:courses/\d+/)?files/\d+)"')
ASSIGNMENT_COURSE_FILE_PATTERN = re.compile(r"/courses/(\d+)/files/(\d+)")
ASSIGNMENT_GLOBAL_FILE_PATTERN = re.compile(r"/files/(\d+)(?:/download)?")
INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))


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


def sanitize_name(name: Any, fallback: str = "unnamed") -> str:
    cleaned = INVALID_CHARS.sub("_", str(name or "")).strip().rstrip(".")
    cleaned = WHITESPACE.sub(" ", cleaned)
    return cleaned or fallback


def load_cookie_file(path: Path) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if "\t" in line:
            parts = line.split("\t")
            if len(parts) >= 7:
                cookies[parts[5]] = parts[6]
            continue
        for part in line.split(";"):
            if "=" not in part:
                continue
            name, value = part.strip().split("=", 1)
            if name:
                cookies[name] = value
    if not cookies:
        raise RuntimeError(f"未能从 cookie 文件读取任何 cookie: {path}")
    return cookies


def parse_cookie_header(value: str) -> dict[str, str]:
    cookies: dict[str, str] = {}
    for part in value.split(";"):
        if "=" not in part:
            continue
        name, cookie_value = part.strip().split("=", 1)
        if name:
            cookies[name] = cookie_value
    if not cookies:
        raise RuntimeError("--canvas-cookie 没有包含可识别的 name=value")
    return cookies


def update_session_cookies(
    session: requests.Session,
    *,
    cookie_file: Path | None,
    cookie_header: str | None,
    from_chrome: bool,
    cookie_domain: str,
) -> None:
    if cookie_file is None and not cookie_header and not from_chrome:
        raise RuntimeError("需要 --canvas-cookie-file、--canvas-cookie 或 --from-chrome")
    if cookie_file is not None:
        session.cookies.update(load_cookie_file(cookie_file.expanduser()))
    if cookie_header:
        session.cookies.update(parse_cookie_header(cookie_header))
    if from_chrome:
        try:
            import browser_cookie3
        except ImportError as exc:
            raise RuntimeError("使用 --from-chrome 需要安装 browser-cookie3") from exc
        jar = browser_cookie3.chrome(domain_name=cookie_domain)
        count = 0
        for cookie in jar:
            if cookie.name and cookie.value:
                session.cookies.set_cookie(cookie)
                count += 1
        if count == 0:
            raise RuntimeError(f"Chrome 中没有找到 {cookie_domain} 的可用 cookie")


def api_get(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    headers = {
        "Accept": "application/json, text/plain, */*",
        "X-Requested-With": "XMLHttpRequest",
        **kwargs.pop("headers", {}),
    }
    response = session.get(url, headers=headers, timeout=60, **kwargs)
    if response.status_code == 401:
        raise RuntimeError(f"Canvas API 未授权，请刷新 cookie: {url}")
    response.raise_for_status()
    return response


def paginate(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Iterator[Any]:
    next_url = url
    next_params = params or {}
    while next_url:
        response = api_get(session, next_url, params=next_params)
        payload = response.json()
        if isinstance(payload, list):
            yield from payload
        else:
            yield payload
        next_url = response.links.get("next", {}).get("url")
        next_params = {}


def course_info(session: requests.Session, course_id: str) -> dict[str, Any]:
    payload = api_get(session, f"{CANVAS_API_ROOT}/courses/{course_id}", params={"include[]": ["term", "teachers"]}).json()
    if not isinstance(payload, dict) or not payload.get("id"):
        raise RuntimeError(f"课程信息返回异常: {payload}")
    return payload


def normalize_file_record(raw: dict[str, Any], source: str, module_name: str | None = None, assignment_name: str | None = None) -> dict[str, Any]:
    file_id = raw.get("id")
    return {
        "kind": "file",
        "id": str(file_id) if file_id is not None else None,
        "source": source,
        "display_name": raw.get("display_name") or raw.get("filename") or f"file-{file_id}",
        "filename": raw.get("filename") or raw.get("display_name") or f"file-{file_id}",
        "size": raw.get("size"),
        "url": raw.get("url") or raw.get("download_url") or raw.get("html_url"),
        "folder_full_name": raw.get("folder_full_name"),
        "content_type": raw.get("content-type") or raw.get("content_type"),
        "updated_at": raw.get("updated_at") or raw.get("modified_at"),
        "locked_for_user": raw.get("locked_for_user"),
        "lock_explanation": raw.get("lock_explanation"),
        "module_name": module_name,
        "assignment_name": assignment_name,
    }


def normalize_assignment(raw: dict[str, Any]) -> dict[str, Any]:
    assignment_id = raw.get("id")
    return {
        "kind": "assignment_page",
        "id": str(assignment_id) if assignment_id is not None else None,
        "source": "assignments",
        "name": raw.get("name") or f"assignment-{assignment_id}",
        "description": raw.get("description") or "",
        "html_url": raw.get("html_url") or "",
        "due_at": raw.get("due_at"),
        "unlock_at": raw.get("unlock_at"),
        "lock_at": raw.get("lock_at"),
        "points_possible": raw.get("points_possible"),
        "submission_types": raw.get("submission_types") or [],
        "published": raw.get("published"),
        "locked_for_user": raw.get("locked_for_user"),
        "lock_explanation": raw.get("lock_explanation"),
    }


def course_files(session: requests.Session, course_id: str) -> list[dict[str, Any]]:
    return [
        normalize_file_record(item, "files")
        for item in paginate(session, f"{CANVAS_API_ROOT}/courses/{course_id}/files", params={"per_page": 100})
        if isinstance(item, dict)
    ]


def module_files(session: requests.Session, course_id: str) -> list[dict[str, Any]]:
    modules = [
        item
        for item in paginate(session, f"{CANVAS_API_ROOT}/courses/{course_id}/modules", params={"per_page": 100})
        if isinstance(item, dict)
    ]
    records: list[dict[str, Any]] = []
    for module in modules:
        module_id = module.get("id")
        module_name = str(module.get("name") or f"module-{module_id}")
        if not module_id:
            continue
        items = paginate(
            session,
            f"{CANVAS_API_ROOT}/courses/{course_id}/modules/{module_id}/items",
            params={"per_page": 100},
        )
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "File" or not item.get("content_id"):
                continue
            try:
                payload = api_get(session, f"{CANVAS_API_ROOT}/files/{item['content_id']}").json()
            except requests.RequestException:
                continue
            if isinstance(payload, dict):
                records.append(normalize_file_record(payload, "modules", module_name=module_name))
    return records


def assignments(session: requests.Session, course_id: str) -> list[dict[str, Any]]:
    return [
        normalize_assignment(item)
        for item in paginate(session, f"{CANVAS_API_ROOT}/courses/{course_id}/assignments", params={"per_page": 100})
        if isinstance(item, dict) and item.get("id")
    ]


def assignment_file_api_urls(course_id: str, description_html: str) -> list[str]:
    urls: set[str] = set()
    if not description_html:
        return []
    for url in ASSIGNMENT_API_ENDPOINT_PATTERN.findall(description_html):
        if url.startswith("/"):
            url = f"{OC_BASE_URL.rstrip('/')}{url}"
        urls.add(url)
    for matched_course_id, file_id in ASSIGNMENT_COURSE_FILE_PATTERN.findall(description_html):
        urls.add(f"{CANVAS_API_ROOT}/courses/{matched_course_id}/files/{file_id}")
    for file_id in ASSIGNMENT_GLOBAL_FILE_PATTERN.findall(description_html):
        urls.add(f"{CANVAS_API_ROOT}/files/{file_id}")
    if not urls and "/files/" in description_html:
        for file_id in re.findall(r"/files/(\d+)", description_html):
            urls.add(f"{CANVAS_API_ROOT}/courses/{course_id}/files/{file_id}")
    return sorted(urls)


def assignment_attachments(session: requests.Session, course_id: str, assignment: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen: set[str] = set()
    for url in assignment_file_api_urls(course_id, str(assignment.get("description") or "")):
        try:
            payload = api_get(session, url).json()
        except requests.RequestException:
            continue
        if not isinstance(payload, dict) or not payload.get("id"):
            continue
        file_id = str(payload["id"])
        if file_id in seen:
            continue
        seen.add(file_id)
        records.append(normalize_file_record(payload, "assignment_attachments", assignment_name=str(assignment["name"])))
    return records


def target_for_file(output_dir: Path, record: dict[str, Any]) -> Path:
    filename = sanitize_name(record.get("display_name") or record.get("filename"))
    source = record.get("source")
    if source == "modules":
        return output_dir / "modules" / sanitize_name(record.get("module_name") or "module") / filename
    if source == "assignment_attachments":
        return output_dir / "assignments" / sanitize_name(record.get("assignment_name") or "assignment") / "attachments" / filename

    target_dir = output_dir / "files"
    folder_full_name = str(record.get("folder_full_name") or "").strip()
    if folder_full_name:
        for segment in folder_full_name.split("/"):
            segment = segment.strip()
            if segment and segment.lower() != "course files":
                target_dir /= sanitize_name(segment)
    return target_dir / filename


def assignment_page_target(output_dir: Path, assignment: dict[str, Any]) -> Path:
    return output_dir / "assignments" / sanitize_name(assignment.get("name") or "assignment") / "assignment.html"


def render_assignment_html(course: dict[str, Any], assignment: dict[str, Any]) -> str:
    metadata = [
        f"<li><strong>Course</strong>: {html.escape(str(course.get('name') or course.get('id')))}</li>",
        f"<li><strong>Assignment ID</strong>: {html.escape(str(assignment.get('id') or ''))}</li>",
        f"<li><strong>Due</strong>: {html.escape(str(assignment.get('due_at') or ''))}</li>",
        f"<li><strong>Unlock</strong>: {html.escape(str(assignment.get('unlock_at') or ''))}</li>",
        f"<li><strong>Lock</strong>: {html.escape(str(assignment.get('lock_at') or ''))}</li>",
        f"<li><strong>Points</strong>: {html.escape(str(assignment.get('points_possible') or ''))}</li>",
        f"<li><strong>Submission types</strong>: {html.escape(', '.join(assignment.get('submission_types') or []))}</li>",
        f"<li><strong>URL</strong>: <a href=\"{html.escape(str(assignment.get('html_url') or ''))}\">{html.escape(str(assignment.get('html_url') or ''))}</a></li>",
    ]
    description = assignment.get("description") or "<p>(No description)</p>"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head><meta charset=\"utf-8\">\n"
        f"<title>{html.escape(str(assignment.get('name') or 'assignment'))}</title></head>\n"
        "<body>\n"
        f"<h1>{html.escape(str(assignment.get('name') or 'assignment'))}</h1>\n"
        f"<ul>{''.join(metadata)}</ul>\n"
        "<hr>\n"
        f"<div>{description}</div>\n"
        "</body>\n"
        "</html>\n"
    )


def default_manifest_path(output_dir: Path) -> Path:
    return output_dir / "canvas_materials_manifest.json"


def default_status_path(output_dir: Path) -> Path:
    return output_dir / "canvas_materials_status.json"


def default_runs_dir(output_dir: Path) -> Path:
    return output_dir / "material_runs"


def load_status(path: Path) -> dict[str, Any]:
    return read_json(path, {"schema_version": 1, "updated_at": None, "items": {}})


def save_status(path: Path, status: dict[str, Any]) -> None:
    status["updated_at"] = now_iso()
    write_json(path, status)


def status_key(entry: dict[str, Any]) -> str:
    return f"{entry.get('kind')}:{entry.get('source')}:{entry.get('id') or entry.get('path')}"


def set_status(
    status: dict[str, Any],
    entry: dict[str, Any],
    state: str,
    *,
    error: str | None = None,
    verification: dict[str, Any] | None = None,
) -> None:
    item = status.setdefault("items", {}).setdefault(status_key(entry), {})
    item.update(
        {
            "state": state,
            "updated_at": now_iso(),
            "kind": entry.get("kind"),
            "source": entry.get("source"),
            "name": entry.get("display_name") or entry.get("name"),
            "path": entry.get("path"),
            "size": entry.get("size"),
        }
    )
    if error:
        item["error"] = error
    else:
        item.pop("error", None)
    if verification:
        item["verification"] = verification


def build_manifest(session: requests.Session, course_id: str, output_dir: Path, include: set[str]) -> dict[str, Any]:
    course = course_info(session, course_id)
    entries: list[dict[str, Any]] = []
    if "files" in include:
        for record in course_files(session, course_id):
            entries.append({**record, "path": str(target_for_file(output_dir, record))})
    if "modules" in include:
        for record in module_files(session, course_id):
            entries.append({**record, "path": str(target_for_file(output_dir, record))})
    if "assignments" in include:
        for assignment in assignments(session, course_id):
            entries.append(
                {
                    **assignment,
                    "path": str(assignment_page_target(output_dir, assignment)),
                }
            )
            for record in assignment_attachments(session, course_id, assignment):
                entries.append({**record, "path": str(target_for_file(output_dir, record))})

    return {
        "schema_version": 1,
        "generated_at": now_iso(),
        "course": {
            "id": course.get("id"),
            "name": course.get("name"),
            "course_code": course.get("course_code"),
            "workflow_state": course.get("workflow_state"),
        },
        "include": sorted(include),
        "entries": dedupe_entries(entries),
    }


def dedupe_entries(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str, str]] = set()
    result: list[dict[str, Any]] = []
    for entry in entries:
        key = (str(entry.get("kind")), str(entry.get("source")), str(entry.get("id") or entry.get("path")))
        if key in seen:
            continue
        seen.add(key)
        result.append(entry)
    return result


def verify_entry(entry: dict[str, Any]) -> dict[str, Any]:
    path = Path(str(entry["path"]))
    size = path.stat().st_size if path.exists() else 0
    expected = entry.get("size")
    if isinstance(expected, str) and expected.isdigit():
        expected = int(expected)
    errors: list[str] = []
    if not path.exists():
        errors.append("missing")
    elif expected is not None and size != expected:
        errors.append(f"size_mismatch:{size}!={expected}")
    return {"ok": not errors, "path": str(path), "size": size, "expected_size": expected, "errors": errors, "checked_at": now_iso()}


def download_file(session: requests.Session, entry: dict[str, Any], *, resume: bool) -> dict[str, Any]:
    target = Path(str(entry["path"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    expected = entry.get("size")
    if isinstance(expected, str) and expected.isdigit():
        expected = int(expected)
    precheck = verify_entry(entry)
    if precheck["ok"]:
        return {"status": "verified", "verification": precheck}
    if entry.get("locked_for_user") or entry.get("lock_explanation"):
        return {"status": "skipped", "error": str(entry.get("lock_explanation") or "locked_for_user"), "verification": precheck}
    url = entry.get("url")
    if not url:
        return {"status": "failed", "error": "missing_download_url", "verification": precheck}

    part = target.with_suffix(target.suffix + ".part")
    headers = {"Accept": "*/*", "Referer": OC_BASE_URL}
    request_headers = dict(headers)
    if resume and part.exists():
        request_headers["Range"] = f"bytes={part.stat().st_size}-"
    response = session.get(str(url), headers=request_headers, stream=True, timeout=(30, 300))
    response.raise_for_status()
    mode = "ab" if request_headers.get("Range") and response.status_code == 206 else "wb"
    with part.open(mode) as handle:
        for chunk in response.iter_content(chunk_size=1024 * 256):
            if chunk:
                handle.write(chunk)
    part.replace(target)
    verification = verify_entry(entry)
    return {"status": "verified" if verification["ok"] else "failed", "verification": verification}


def write_assignment_page(entry: dict[str, Any], course: dict[str, Any]) -> dict[str, Any]:
    target = Path(str(entry["path"]))
    target.parent.mkdir(parents=True, exist_ok=True)
    content = render_assignment_html(course, {**entry, "description": ""})
    if target.exists() and target.read_text(encoding="utf-8") == content:
        return {"status": "verified", "verification": verify_entry(entry)}
    target.write_text(content, encoding="utf-8")
    return {"status": "verified", "verification": verify_entry(entry)}


def download_entries(
    session: requests.Session,
    manifest: dict[str, Any],
    status: dict[str, Any],
    *,
    status_path: Path,
    runs_dir: Path,
    resume: bool,
    max_count: int | None,
    retry_failed: bool,
) -> int:
    processed = 0
    course = manifest.get("course") or {}
    for entry in manifest.get("entries") or []:
        if max_count is not None and processed >= max_count:
            set_status(status, entry, "pending")
            continue
        current_state = (status.get("items") or {}).get(status_key(entry), {}).get("state")
        if retry_failed and current_state != "failed":
            set_status(status, entry, current_state or "pending")
            continue
        set_status(status, entry, "downloading")
        save_status(status_path, status)
        append_run_log(runs_dir, "download_start", {"path": entry.get("path"), "source": entry.get("source")})
        try:
            if entry.get("kind") == "assignment_page":
                result = write_assignment_page(entry, course)
            else:
                result = download_file(session, entry, resume=resume)
            set_status(status, entry, result["status"], error=result.get("error"), verification=result.get("verification"))
            append_run_log(runs_dir, "download_complete", {"path": entry.get("path"), "status": result["status"]})
        except Exception as exc:
            set_status(status, entry, "failed", error=str(exc))
            append_run_log(runs_dir, "download_error", {"path": entry.get("path"), "error": str(exc)})
        finally:
            save_status(status_path, status)
        processed += 1
    return processed


def print_status(status_path: Path, status: dict[str, Any]) -> None:
    items = status.get("items") or {}
    counts: dict[str, int] = {}
    for item in items.values():
        state = item.get("state", "unknown")
        counts[state] = counts.get(state, 0) + 1
    print(f"status_file: {status_path}")
    print(f"updated_at: {status.get('updated_at')}")
    print("summary:")
    for state, count in sorted(counts.items()):
        print(f"  {state}: {count}")


def parse_include(values: list[str]) -> set[str]:
    include: set[str] = set()
    for value in values:
        for item in value.split(","):
            item = item.strip()
            if item:
                include.add(item)
    allowed = {"files", "modules", "assignments"}
    unknown = include - allowed
    if unknown:
        raise RuntimeError(f"未知 include 类型: {sorted(unknown)}")
    return include or allowed


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--course-id", required=True, help="Canvas course id, for example the number in /courses/<id>")
    parser.add_argument("--canvas-cookie-file", type=Path, help="Canvas cookie file in Netscape or name=value format")
    parser.add_argument("--canvas-cookie", help="Canvas Cookie header, for example 'JAAuthCookie=...'")
    parser.add_argument("--from-chrome", action="store_true", help="Load Canvas cookies from local Chrome with browser-cookie3")
    parser.add_argument("--cookie-domain", default=".sjtu.edu.cn", help="Chrome cookie domain for --from-chrome; default: .sjtu.edu.cn")
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--status-file", type=Path)
    parser.add_argument("--runs-dir", type=Path)
    parser.add_argument("--include", action="append", help="Comma-separated subset: files,modules,assignments")
    parser.add_argument("--sync-details", action="store_true", help="Refresh manifest/status without downloading files")
    parser.add_argument("--download", action="store_true", help="Refresh manifest and download entries")
    parser.add_argument("--resume", action="store_true", help="Resume .part files when the server supports ranges")
    parser.add_argument("--retry-failed", action="store_true", help="Only retry entries currently marked failed")
    parser.add_argument("--verify-only", action="store_true", help="Verify local files against an existing manifest")
    parser.add_argument("--status", action="store_true", help="Print status summary")
    parser.add_argument("--max-count", type=int, help="Maximum entries to download this run")
    args = parser.parse_args()

    output_dir = args.output_dir
    manifest_path = args.manifest or default_manifest_path(output_dir)
    status_path = args.status_file or default_status_path(output_dir)
    runs_dir = args.runs_dir or default_runs_dir(output_dir)
    status = load_status(status_path)

    if args.status:
        print_status(status_path, status)
        return 0

    if args.verify_only:
        manifest = read_json(manifest_path, None)
        if not isinstance(manifest, dict):
            raise RuntimeError(f"manifest 不存在或格式错误: {manifest_path}")
        failures = 0
        for entry in manifest.get("entries") or []:
            verification = verify_entry(entry)
            state = "verified" if verification["ok"] else "failed"
            set_status(status, entry, state, error=None if verification["ok"] else ",".join(verification["errors"]), verification=verification)
            if not verification["ok"]:
                failures += 1
        save_status(status_path, status)
        append_run_log(runs_dir, "verify_only", {"failures": failures})
        return 1 if failures else 0

    include = parse_include(args.include)
    should_download = args.download or not args.sync_details
    if args.retry_failed:
        should_download = True

    with requests.Session() as session:
        update_session_cookies(
            session,
            cookie_file=args.canvas_cookie_file,
            cookie_header=args.canvas_cookie,
            from_chrome=args.from_chrome,
            cookie_domain=args.cookie_domain,
        )
        manifest = build_manifest(session, args.course_id, output_dir, include)
        write_json(manifest_path, manifest)
        for entry in manifest.get("entries") or []:
            set_status(status, entry, "pending")
        save_status(status_path, status)
        append_run_log(runs_dir, "sync_details", {"manifest": str(manifest_path), "entries": len(manifest.get("entries") or [])})

        if should_download:
            processed = download_entries(
                session,
                manifest,
                status,
                status_path=status_path,
                runs_dir=runs_dir,
                resume=args.resume,
                max_count=args.max_count,
                retry_failed=args.retry_failed,
            )
            append_run_log(runs_dir, "run_complete", {"processed": processed, "download": True})

    print(f"[manifest] {manifest_path}")
    print(f"[status] {status_path}")
    print(f"[entries] {len(manifest.get('entries') or [])}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except RuntimeError as exc:
        print(f"[error] {exc}", file=sys.stderr)
        raise SystemExit(1)
