# Upstream assessment (2026-10-19)

Source: https://github.com/jangkyuri/counsel-note-public

Reviewed snapshot: `47da11d` (`상담 앱 공개 소스 초기 등록`).

## What it does

The 11,094-line Streamlit `app.py` accepts student counseling recordings, extracts
Korean text, persists the transcript, invokes Codex CLI to generate notes, and
supports clipboard, batch review, ADMIN, CSV and Google Docs workflows.
`counsel_modules/` already separates batch state, atomic writes, CSV workers,
Google transport, text helpers and an optional OpenVINO engine. `scripts/`
contains operational installers, release tools and regression checks.

The actual ASR is not one obsolete Whisper model. `PROCESSING_MODES` selects
faster-whisper base/small/medium on CPU INT8, or OpenVINO INT8 large-v3-turbo.
Default session initialization chooses the OpenVINO GPU turbo mode. No
speaker-attributed, word-aligned transcript is retained by the original
`consume_whisper_segments` contract.

## Issues driving this revision

- Runtime setup assumes private student mappings and an Apps Script URL.
  Without them, startup stops before transcription can be used.
- Transcription, UI state, filesystem handling, retry behavior, remote summaries
  and external storage are coupled in one large entry point.
- Dependency versions are unconstrained. Speech setup differs between machines.
- Old ASR runs CPU or Intel OpenVINO rather than the owner's NVIDIA CUDA path.
- Codex summaries and ADMIN/Docs use external services: they cannot be advertised
  as a fully local counseling workflow.
- Speaker IDs, alignment evidence and model revision provenance are missing.
- Existing batch/checkpoint and duplicate-save logic is valuable and is preserved;
  rebuilding the operational integrations would add unrelated regression risk.

## Boundary decision

HDHcounsel introduces an independent local default entry point and small typed
modules, rather than rewriting all operational integrations. The existing
`app.py` and its operational launchers remain an explicitly legacy workflow.
The same new speech service is also available as a legacy processing mode.
Default local operation requires no student registry, Google configuration,
Codex login, cloud ASR or paid API.

## License status

No LICENSE/COPYING file or explicit source license grant was present in the
snapshot inspected. Public visibility alone is not treated as a license grant.
No new license is asserted over upstream work. Upstream authorship and commit
history are retained. The derivative is kept private pending clarification of
redistribution terms by the copyright holder; privacy is not a replacement for
obtaining those terms. Third-party models are acquired separately under their
own licenses and are not committed.
