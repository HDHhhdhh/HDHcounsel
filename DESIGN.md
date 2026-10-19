# Connect Log Layout

## Scope

Preserve the existing Streamlit operational interface. Changes here concern the
recording uploader, recent log history, processing status, and ADMIN save feedback.
No marketing content, new theme, animations, or decorative media.

## Existing Primitives

- Streamlit headings, inputs, uploaders, buttons, expanders and columns.
- Main columns retain the existing 0.9 / 1.45 / 1.0 proportions and large gaps.
- History strips use a 6px radius, 1px rgba(128,128,128,0.28) border,
  rgba(128,128,128,0.035) surface, 8px row gap and 8px / 12px padding.
- History dates and states use 0.9rem, weight 650; time and counts use 0.84rem.
- Letter spacing stays zero. Long content wraps instead of overflowing.
- Keep existing button names, disabled states and uploader callbacks.

## Recording and History

- Keep the recording heading at the top of the center column.
- Place the uploader in a track capped at 300px and its generate/copy action
  directly below, outside the gray box. The shared upload label sits above both tracks,
  so the gray upload surface and the first history strip start at the same height.
- Preserve Streamlit's native uploader surface and the action's natural width.
- Keep both controls in stable, separate containers with the normal vertical gap.
- Give the adjacent history track all remaining width, separated by 16px.
- Hide the native file-size/type hint only in the recording uploader. Preserve
  file-type and size validation, selected files, upload errors and the CSV uploader.
- At a center-container width of 640px or less, stack the two tracks.
- Uploaded filenames remain within the uploader. History strips may wrap on
  narrow screens. Do not shrink text or hide dates, states, times or counts.
- Batch progress, summary editing and CSV processing retain the full center width.
- Keep dynamic audio details and CSV processing in separate, unconditional sibling
  containers. Their positions must not change when uploads or summaries change;
  otherwise Streamlit can briefly retain duplicate CSV expanders during reruns.

## Status Column

- Processing status starts at the same height as the other column headings.
- Today's summary records remain immediately below processing status.
- Updating CSV history changes only the history placeholder in the center column.

## ADMIN Save Feedback

- Save interactions rerender only the ADMIN fragment, not the full page.
- Do not force-scroll to the save controls or add smooth-scroll scripts.
- Keep target information above the button and save feedback below it.
- Preserve the current button label, validation and duplicate-save protection.
- Hide the single-save action once its exact summary is already confirmed saved.
- One `5A ADMIN 일괄 적용` action saves all generated batch summaries to their own
  confirmed ADMIN targets and counseling dates. Show generated counts separately
  from unique saved students; generation alone is not storage completion.
- Keep unsaved summaries and unacknowledged batch results across new sessions.
  Retry stored summaries without retranscription. Ambiguous targets stay pending
  until selected in the batch summary viewer; never reuse another student's SID.
- Default `일괄 처리 현황` to collapsed for idle, paused and completed batches.
  Automatically expand only a running batch with pending or processing jobs.
  Collapsing the panel never clears summaries, completion acknowledgement or save state.
- Show batch summaries directly in `일괄 처리 현황`, without a nested expander.
  Use native Material chevron icon buttons with previous/next tooltips, a student
  selector and an ordinal count. Disable arrows at the first/last summary.
  Keep a 40px / flexible / 40px navigation grid with an 8px gap at all widths.
  Summary edits belong to the selected job and invalidate only its saved flag.
  Do not repeat that batch summary or its single-save action below the batch.

## Summary Runtime

- Check the local Codex login before starting transcription. A signed-out CLI
  must not spend time loading the speech model or extracting the recording.
- On Windows, prefer the installed native `codex.exe` over the npm command
  wrapper so exit details remain available.
- Do not pin a model in application code. Use the Codex CLI configured model
  unless `COUNSEL_NOTE_CODEX_MODEL` explicitly overrides it.
- When login has expired, show the compact recovery action and preserve the
  uploaded recording and saved transcript for retry.

## Refresh Stability

- Keep upload controls in persistent containers rather than clearing placeholders
  before every rerun. Replace history markup in one delta without clearing first.
- CSV upload, selection, save, resume and retry interactions rerender only the CSV
  workspace fragment. Keep its expander open while a CSV is loaded.
- `정리본 생성·복사` prepares the single-recording job in its click callback so
  processing starts after one full-page rerun, not a second forced rerun.
- Keep startup and operation feedback inside a fixed sibling above the columns.
- Disable Streamlit's stale-content opacity transition, not widget disabled states.
  Processing status, save guards, warnings and errors must remain visible.

## Verification

The accepted baseline is the uploader/action/history layout above, frozen on
2026-09-05. Do not move controls during unrelated behavior fixes.

Use the real rendering helpers in the isolated fixture described in
`docs/UI_BASELINE.md`. Check empty, selected, saving and completed states on a
wide desktop and a narrow viewport. Measure upload/history alignment (within
2 CSS pixels), upload width (at most 300px), the action below the upload surface,
three non-overlapping history rows and exactly one CSV expander. At 640px or
less component width, verify stacked tracks instead of top alignment.

Run the full-page AppTest transition checks as well: the isolated fixture does
not replace them. Visually inspect screenshots for clipping and transient
duplicates during state changes; a final DOM snapshot cannot prove no flicker.
Never run real recording jobs or admin/Docs writes for layout verification.

## State and Control Contract

- A history strip's `완료` requires the latest CSV history to have no pending,
  failed or review rows. Its `저장 완료 N명` count deduplicates confirmed student
  documents across that date's result logs and the current checkpoint.
- If a detailed result file is missing, recover confirmed identities only from
  an export whose byte hash and row fingerprints match its processing history.
  Count success/duplicate rows, not pending/failure/review/excluded rows. Missing
  identity evidence is `인원 확인 필요`, never a fabricated zero or row count.
- Retain detailed Docs result logs for seven days so the three recent attendance
  dates keep their confirmation evidence through normal session cleanup.
- Pending rows or a missing history entry display `미완료`. Running and
  interrupted details belong in the CSV progress area, not a new history label.
- Keep `정리본 생성·복사` below the uploader. It is disabled without a valid
  single recording/student or while recording processing is active. Multiple
  recordings use the existing sequential-processing action instead.
- Keep `선택한 기록을 학생 Docs에 추가` visible but disabled for an empty or
  already-completed CSV. Hide the completed CSV row list.
- Completed CSVs retain a `Docs 저장 다시 확인` action with the native refresh
  icon. It is disabled during another save or without a configured endpoint.
  Read-only verification keeps confirmed records completed, reopens missing
  records for retry, and marks verification errors as review instead of success.
- Keep an unacknowledged run's result panel visible across reruns and refreshes.
  A run that leaves rows pending says `이번 묶음 처리 완료` with the day's
  resolved/total count and uses `이번 묶음 확인`. Only a run that resolves the
  full CSV says `오늘 전체 처리 완료` and uses `오늘 전체 완료 확인`. Close the
  panel only after its matching acknowledgement is persisted in the checkpoint.
- When loading history written by the older chunk behavior, convert any currently
  eligible row recorded as `excluded` back to pending/review before deciding the
  CSV is complete. Persist that repair so an old partial run cannot stay falsely
  completed.
- For a new CSV, enable the same action only with eligible selected rows,
  a configured web-app URL and readable processing history.
- While saving, hide both the save action and `남은 작업 이어서 저장 (N건)`.
  After interruption, show resume only when there are resumable rows for the
  matching upload and the history does not block processing.
- See `docs/OPERATIONS.md` for persistence and duplicate/replacement policies.
