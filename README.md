# lecture-notes-pipeline

> Download Canvas course materials, recordings, and local Whisper transcripts.
> Optional Codex / Claude Code skill for PPT-aligned study notes.

This repository is useful in two modes:

1. Without an agent: download Canvas course files, download lecture recordings, and transcribe videos locally with Whisper.
2. With an agent: align slides and transcripts, judge lecture boundaries, clean low-confidence fragments, and write compact study notes.

The command-line pipeline covers the mechanical work:

```text
materials/   Canvas course files, PPTs, module files, assignment attachments
downloads/   Canvas lecture recordings
audio/       extracted audio
transcripts/ local Whisper transcripts
```

The bundled skill covers the judgment-heavy work after those assets exist.

## Preview

Exported lecture note sample:

![PDF note sample](examples/assets/lesson_sample_page1.png)

## What this repo does

- Downloads Canvas course materials when a local logged-in browser session is available.
- Downloads Canvas-hosted recordings from SJTU's video platform.
- Extracts audio with `ffmpeg`.
- Transcribes Chinese lectures with `mlx-whisper`.
- Builds a quick slide text index from PDF decks.
- Runs rough PPT keyword scans over transcripts.
- Supports fuzzy lookup against slides and reference notes for low-confidence fragments.

## Repository layout

- `download_canvas_videos.py`: download Canvas recordings with the smallest available stream.
- `download_canvas_materials.py`: download Canvas course files, module files, assignment pages, and assignment attachments.
- `process_lecture.py`: extract audio and transcribe one or more lecture videos.
- `run_course_pipeline.py`: unified wrapper for materials, video downloads, and transcription.
- `build_slide_index.py`: extract a quick text preview from PPT PDFs.
- `scan_ppt_hits.py`: rough transcript-to-PPT keyword scan.
- `fuzzy_lookup.py`: fuzzy lookup over slide PDFs and reference notes.
- `clean_transcript.py`: remove obvious noise fragments from transcript text.
- `export_notes_pdf.py`: export Markdown notes into per-note PDFs and one combined PDF.
- `examples/`: sample note source and preview assets for the README.
- `skills/lecture-notes-pipeline/`: Codex skill for running the workflow with stable note-writing rules.

## Requirements

Python packages:

- `requests`
- `mlx-whisper`
- `reportlab`
- `pypdf`
- `python-pptx`
- `browser-cookie3`

System tools:

- `ffmpeg`
- `pdftotext` (Poppler)

Install Python dependencies:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Quick start

Refresh your browser login at `oc.sjtu.edu.cn`, then create a local course root:

```bash
mkdir -p /path/to/course-root
```

Sync Canvas materials and recording metadata without downloading:

```bash
python3 run_course_pipeline.py \
  --course-id 123456 \
  --from-chrome \
  --steps materials,videos \
  --course-root /path/to/course-root
```

Download a small bounded batch:

```bash
python3 run_course_pipeline.py \
  --course-id 123456 \
  --from-chrome \
  --steps materials,videos \
  --start 1 \
  --end 3 \
  --download \
  --max-count 3 \
  --course-root /path/to/course-root
```

Transcribe downloaded videos:

```bash
python3 run_course_pipeline.py \
  --course-id 123456 \
  --steps transcribe \
  --start 1 \
  --end 3 \
  --course-root /path/to/course-root
```

You can also run each layer directly:

```bash
python3 download_canvas_materials.py --course-id 123456 --from-chrome --download --output-dir /path/to/course-root/materials
python3 download_canvas_videos.py --source sjtu-lti --course-id 123456 --canvas-cookie-file /path/to/cookies.txt 1 2 --download --output-dir /path/to/course-root/downloads
python3 process_lecture.py /path/to/course-root/downloads/*.mp4 --audio-dir /path/to/course-root/audio --transcript-dir /path/to/course-root/transcripts
```

Build a slide index after materials are in place:

```bash
python3 build_slide_index.py --ppt-dir /path/to/course-root/materials --output /path/to/course-root/slides_index.md
```

Fuzzy lookup for noisy fragments:

```bash
python3 fuzzy_lookup.py "无知之幕" --notes-pdf /path/to/reference-notes.pdf --ppt-dir /path/to/ppt
```

Export notes to PDF:

```bash
python3 export_notes_pdf.py --notes-dir /path/to/notes --output-dir /path/to/exports
```

This generates:

- one PDF per Markdown note
- one combined PDF volume by default

Try the included sample:

```bash
python3 export_notes_pdf.py --notes-dir examples/sample_notes --output-dir examples/rendered
```

## Canvas download configuration

`download_canvas_videos.py` reads an authenticated Canvas token from a local Chrome session storage file.

You can override the defaults with:

- `CANVAS_BASE_URL`
- `CANVAS_SESSION_STORAGE`

By default the script looks at the Chrome `Session Storage/` directory and picks the newest `.log` file.

Or by passing:

```bash
python3 download_canvas_videos.py 4 5 6 --session-storage "/path/to/Session Storage"
```

For SJTU Canvas, the downloader can also reuse an already authenticated `oc.sjtu.edu.cn` cookie and follow the LTI3 handoff to `v.sjtu.edu.cn`:

```bash
python3 download_canvas_videos.py \
  --source sjtu-lti \
  --course-id 123456 \
  --canvas-cookie-file /path/to/cookies.txt \
  --sync-details \
  --output-dir /path/to/course-root/downloads
```

Then download a bounded batch:

```bash
python3 download_canvas_videos.py \
  --source sjtu-lti \
  --course-id 123456 \
  --canvas-cookie-file /path/to/cookies.txt \
  1 2 \
  --download \
  --resume \
  --max-count 2 \
  --output-dir /path/to/course-root/downloads
```

`--canvas-cookie-file` accepts Netscape cookie exports and simple `name=value; name2=value2` cookie header text. You can also pass the header directly with `--canvas-cookie`. This mode does not store account passwords or perform jAccount login; refresh the cookie from your own browser session when it expires.

SJTU note: `findVodVideoList` expects a JSON request body, and the `canvasCourseId` value should be `encodeURIComponent(courId)`. If you pass the raw `courId`, the platform may return an empty list or a decrypt failure even when the current browser page can play the recording.

This script is intentionally local-first. It is designed for workflows where the user is already logged into Canvas in Chrome on the same machine.

For resumable course runs, use the downloader as a small stateful job rather than a long detached process:

```bash
python3 download_canvas_videos.py 4 5 6 --sync-details --output-dir /path/to/course-root/downloads
python3 download_canvas_videos.py 4 5 6 --download --resume --max-count 2 --output-dir /path/to/course-root/downloads
python3 download_canvas_videos.py --verify-only --output-dir /path/to/course-root/downloads
python3 download_canvas_videos.py --status --output-dir /path/to/course-root/downloads
```

The downloader writes:

- `canvas_download_manifest.json`: selected recordings, streams, output paths, and source URLs
- `download_status.json`: per-lecture `pending / downloading / verified / failed` state
- `download_runs/*.jsonl`: run logs for download and verification events

If Canvas exposes multiple recording views and you know the desired `cdviViewNum`, pass `--view-num`. Otherwise the downloader keeps the previous behavior and chooses the smallest downloadable stream.

## Canvas material download

`download_canvas_materials.py` downloads course materials from Canvas itself, separate from lecture recordings. It can discover:

- course files
- files linked from modules
- assignment pages
- files linked from assignment descriptions

For SJTU Canvas, first refresh your browser login at `oc.sjtu.edu.cn`, then run:

```bash
python3 download_canvas_materials.py \
  --course-id 123456 \
  --from-chrome \
  --sync-details \
  --output-dir /path/to/course-root/materials
```

Or pass a cookie file explicitly:

```bash
python3 download_canvas_materials.py \
  --course-id 123456 \
  --canvas-cookie-file /path/to/cookies.txt \
  --download \
  --resume \
  --max-count 10 \
  --output-dir /path/to/course-root/materials
```

The material downloader writes:

- `canvas_materials_manifest.json`: discovered material entries and target paths
- `canvas_materials_status.json`: per-entry `pending / downloading / verified / failed / skipped` state
- `material_runs/*.jsonl`: run logs

Use `--include files`, `--include modules`, or `--include assignments` to limit discovery. Keep large material pulls bounded with `--max-count`, especially when assignment attachments are numerous.

## Download process hygiene

Do not leave large download jobs hanging in the background.

- Prefer small batches such as `1 2` or `1 2 3`, not the whole semester in one detached process.
- Prefer `--max-count` when automation is driving the work.
- After each batch, verify the expected files landed completely before starting transcription.
- Use `--verify-only` and `--status` before deciding whether more download work is needed.
- If a download job finishes or stalls, clean up the matching `python3 download_canvas_videos.py` and child `curl` processes promptly.
- If you want an explicit cleanup pass, use:

```bash
python3 cleanup_download_jobs.py --list
python3 cleanup_download_jobs.py --kill
```

The cleanup helper only targets downloader jobs from this repo. It does not kill unrelated Python or curl processes.

## Download source stability

For unattended project work, do not make the pipeline depend on an open browser tab.

- Prefer a stable local `downloads/` directory first.
- A symlinked `downloads/` directory is acceptable if the real files live elsewhere.
- If the next lecture video is missing locally, record that as a project gap instead of assuming Canvas is still open in the current thread.
- Treat browser session state as opportunistic input, not as the primary long-term source of truth.
- For SJTU Canvas, prefer `--source sjtu-lti` with a fresh authenticated cookie when Chrome Session Storage does not contain the video-platform token.
- For Canvas course materials, use `download_canvas_materials.py`; keep materials under `materials/` and recordings under `downloads/`.
- Platform captions are not part of the default workflow. Use local Whisper transcription through `process_lecture.py` for formal note inputs.

## Transcription process hygiene

The same cleanup rule applies to transcription jobs.

- Run one lecture or one small batch at a time.
- After each transcription finishes, verify the expected `.txt` and `.json` files landed.
- Explicitly check for residual `process_lecture.py` processes instead of assuming they exited cleanly.
- If a transcription process is stalled or no longer needed, terminate it before starting new heavy work.

Use:

```bash
python3 cleanup_course_jobs.py --list
python3 cleanup_course_jobs.py --kill
```

## Output conventions

Recommended output structure:

```text
course-root/
  ppt/
  notes/
  transcripts/
  downloads/
  audio/
  slides_index.md
  ppt_processing_queue.md
  uncertain_fragments.md
```

## Note-writing rules

The bundled Codex skill encodes the preferred note style:

- align by PPT/content boundary first, not by session number
- write compact study notes, not classroom narration
- remove teacher/process voice
- expand any case that is actually discussed in class
- only correct low-confidence transcript text when slide or note evidence supports it

If you want Codex to follow those rules consistently, install or reuse the included skill:

- `skills/lecture-notes-pipeline/`

## Publish checklist

Before making the repo public:

- remove any local-only outputs or preview artifacts you do not want to ship
- confirm the Canvas downloader behavior matches what you want to expose publicly
- choose and add a `LICENSE`
- add a few example inputs or screenshots if you want the README to be self-explanatory
