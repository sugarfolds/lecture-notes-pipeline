# lecture-notes-pipeline

Pipeline for turning recorded course sessions into PPT-aligned study notes.

The repository is built around a pragmatic workflow:

1. Download or collect lecture videos.
2. Extract audio and run Whisper transcription.
3. Align transcript content to PPT boundaries instead of hard-cutting by session.
4. Resolve noisy transcript fragments against slides or reference notes when there is evidence.
5. Produce compact, review-oriented notes.

## What this repo does

- Downloads Canvas-hosted recordings when a local logged-in browser session is available.
- Extracts audio with `ffmpeg`.
- Transcribes Chinese lectures with `mlx-whisper`.
- Builds a quick slide text index from PDF decks.
- Runs rough PPT keyword scans over transcripts.
- Supports fuzzy lookup against slides and reference notes for low-confidence fragments.

## Repository layout

- `download_canvas_videos.py`: download Canvas recordings with the smallest available stream.
- `process_lecture.py`: extract audio and transcribe one or more lecture videos.
- `run_course_pipeline.py`: batch wrapper around download and transcription.
- `build_slide_index.py`: extract a quick text preview from PPT PDFs.
- `scan_ppt_hits.py`: rough transcript-to-PPT keyword scan.
- `fuzzy_lookup.py`: fuzzy lookup over slide PDFs and reference notes.
- `clean_transcript.py`: remove obvious noise fragments from transcript text.
- `export_notes_pdf.py`: export Markdown notes into per-note PDFs and one combined PDF.
- `skills/lecture-notes-pipeline/`: Codex skill for running the workflow with stable note-writing rules.

## Requirements

Python packages:

- `requests`
- `mlx-whisper`
- `reportlab`
- `pypdf`

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

Build a slide index:

```bash
python3 build_slide_index.py --ppt-dir /path/to/ppt --output slides_index.md
```

Transcribe local videos:

```bash
python3 process_lecture.py /path/to/video1.mp4 /path/to/video2.mp4
```

Batch download and transcribe:

```bash
python3 run_course_pipeline.py --start 1 --end 6 --step all
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

This script is intentionally local-first. It is designed for workflows where the user is already logged into Canvas in Chrome on the same machine.

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
