---
name: lecture-notes-pipeline
description: Use when the task is to turn recorded course sessions, lecture videos, or local LMS/Canvas recordings into PPT-aligned study notes with transcripts, low-confidence cleanup, and compact review-oriented output. Triggers on requests like transcribe this lecture, align notes to slides, process course recordings, build study notes from class videos, Canvas course note workflow, or lecture-to-notes pipeline.
---

# Lecture Notes Pipeline

Use this skill for course-recording workflows where the output is not just a transcript, but a stable note set aligned to slide content.

## Core workflow

1. Locate the working root and identify:
   - `ppt/`
   - `notes/`
   - `transcripts/`
   - `downloads/`
   - `audio/`
2. Resolve the video source before doing any transcript work:
   - first prefer existing local `downloads/` files
   - if the workspace uses a symlinked `downloads/` directory, treat that as valid local input
   - if the workspace keeps a manifest or stable local source path, use that instead of depending on an open browser tab
   - do not assume a Canvas page, login state, or browser context is still available in a new thread
3. If videos must be fetched from Canvas and the repo script is present, use:
   - `download_canvas_videos.py`
   - prefer its status, resume, verify, and bounded-batch modes when available
4. If transcription is needed, use:
   - `process_lecture.py`
   - `run_course_pipeline.py` for batch runs
5. Build slide context with:
   - `build_slide_index.py`
   - `scan_ppt_hits.py`
6. If the user wants a reading version rather than only editable notes, export:
   - `export_notes_pdf.py`
7. Determine boundaries by content and slide deck, not by session number.
8. For noisy transcript fragments:
   - first check slide PDFs
   - then check any reference notes
   - only correct text when there is supporting evidence
   - otherwise omit the fragment from formal notes and record the uncertainty
9. Maintain queue and uncertainty records when the workspace already uses them.
10. Keep process lifecycle operationally tight:
   - prefer small download batches over one long detached semester-wide job
   - long download or transcription work must leave a status file, log, and verification result
   - automation should advance one bounded, verifiable step; it should not be treated as the downloader itself
   - after each batch, verify expected files and process status
   - if downloader `python` or child `curl` processes are finished, stalled, or no longer needed, clean them up promptly
   - if transcription `python` processes are finished, stalled, or no longer needed, clean them up promptly as well
   - after every completed download or transcription batch, explicitly check for residual processes instead of assuming they exited cleanly
   - do not leave heavy background download or transcription jobs running unattended on the user's machine
11. If the local project does not contain the next required video, record that as a concrete project status gap instead of pretending the web source is still available.
12. If slides are missing for a transcript range, create a gap list and preparatory checklist; do not force a formal lecture note before the slide boundary is stable.
13. If slides exist and have been checked but no stable transcript or recording segment matches them, create a slide-only materials note instead of leaving the material unusable:
   - name it clearly, such as `*_slide_materials_note.md` or the local equivalent
   - mark at the top that it is based on slides only and has no stable transcript-backed lecture expansion yet
   - do not label it as a formal integrated lecture note
   - upgrade it later if a matching transcript or recording is found

## Download state

For LMS/Canvas downloads, prefer a resumable queue over one-off scripts.

- Keep a manifest of lesson labels, source URLs, expected target paths, and view selection.
- Keep a status file with `pending`, `downloading`, `downloaded`, `verified`, and `failed` states.
- Verify downloads by file existence, reasonable size, and duration when a media probe is available.
- Preserve failed or partial evidence in logs; clean misleading tiny files or stale `.part` files only after recording the failure.
- If authentication depends on browser cookies or session storage, record that dependency and fail clearly when the login state expires.

## Transcription QC

Before using a transcript in formal notes:

- Check detected language, duration coverage, segment count, repeated noise, and obvious wrong-language output.
- For Chinese lectures, force `zh` on retry when auto-detection fails.
- Preserve bad transcripts as `.bad_<reason>.json/.txt` before replacing them with corrected output.
- Treat corrected transcripts as new inputs for boundary judgment; do not silently mix bad and corrected text.

## Note style

- Write in compact study-note form.
- The target artifact is a revision note, not a lecture retelling or explanatory recap.
- Do not write in classroom narration voice.
- Remove lecture-retelling markers such as “老师说”, “课堂讲到”, “课堂提醒”, “这节课”, “转写显示”.
- Prefer ordered knowledge blocks over conversational explanation.
- Headings should land directly on concepts, structures, rules, tests, or judgments; avoid meta headings like “课堂补充”, “方法意义”, or “本讲定位” in the main body.
- Merge slide structure and transcript content into a single note; do not produce a “slide outline plus later supplements” shape.
- Keep boundary/process notes minimal inside formal notes; move most cut-point, noise, and transcript-repair detail into queue/status/uncertainty files when the workspace has them.
- For slide-only materials notes, keep the same compact study-note style but preserve provenance: the note must say it is slide-derived only, and it must not imply the instructor actually covered the material in class.
- Expand any case that is materially discussed in class.
- Prefer `Markdown` as the editable source of truth and `PDF` as the final reading/export format.

## Case handling

When a case is actually developed in the lecture, capture at least:

- basic facts
- dispute / issue
- rule or method being illustrated
- conclusion or competing positions

If the lecture uses the case to compare multiple legal methods, institutional models, or constitutional structures, preserve that contrast explicitly inside the case note rather than treating it as a passing example.

## Low-confidence fragments

Treat low-confidence fragments conservatively.

- Use fuzzy lookup only to confirm, not to invent.
- If slide or reference-note evidence is weak, leave the fragment out of the formal notes.
- Keep a separate uncertainty record when the workspace already uses one.

## Repo-specific helpers

If this repo is present, prefer these scripts over ad hoc rewrites:

- `download_canvas_videos.py`
- `process_lecture.py`
- `run_course_pipeline.py`
- `cleanup_download_jobs.py`
- `cleanup_course_jobs.py`
- `build_slide_index.py`
- `scan_ppt_hits.py`
- `fuzzy_lookup.py`
- `clean_transcript.py`
- `export_notes_pdf.py`

## Recommended output structure

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
