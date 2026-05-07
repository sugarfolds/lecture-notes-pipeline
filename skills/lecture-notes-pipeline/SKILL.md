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
2. If videos must be fetched from Canvas and the repo script is present, use:
   - `download_canvas_videos.py`
3. If transcription is needed, use:
   - `process_lecture.py`
   - `run_course_pipeline.py` for batch runs
4. Build slide context with:
   - `build_slide_index.py`
   - `scan_ppt_hits.py`
5. If the user wants a reading version rather than only editable notes, export:
   - `export_notes_pdf.py`
6. Determine boundaries by content and slide deck, not by session number.
7. For noisy transcript fragments:
   - first check slide PDFs
   - then check any reference notes
   - only correct text when there is supporting evidence
   - otherwise omit the fragment from formal notes and record the uncertainty
8. Maintain queue and uncertainty records when the workspace already uses them.

## Note style

- Write in compact study-note form.
- Do not write in classroom narration voice.
- Remove process markers such as “老师说”, “这节课”, “转写显示”.
- Prefer ordered knowledge blocks over conversational explanation.
- Merge slide structure and transcript content into a single note.
- Expand any case that is materially discussed in class.
- Prefer `Markdown` as the editable source of truth and `PDF` as the final reading/export format.

## Case handling

When a case is actually developed in the lecture, capture at least:

- basic facts
- dispute / issue
- rule or method being illustrated
- conclusion or competing positions

If the lecture uses the case to compare multiple legal methods, preserve that contrast explicitly.

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
