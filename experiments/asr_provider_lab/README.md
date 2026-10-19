# ASR Provider Lab

This folder is an isolated experiment area for comparing ASR providers without
changing the production counsel-note app.

## Purpose

- Compare faster-whisper and FunASR on the same local audio file.
- Save each provider result as JSON for manual review.
- Save one summary JSON that contains every provider result.
- Explore a future `ASR_PROVIDER=whisper|funasr` provider abstraction with
  Whisper fallback if FunASR fails.

## Separation From Production

This lab does not import or modify `app.py`, `counsel_modules/`, `data/`,
Google Docs save logic, student DB/API code, templates, routes, or static
assets. It is a standalone CLI experiment.

You can delete this entire folder if the experiment is no longer needed.

## Before Running

- Use only copied, non-sensitive test audio.
- Do not place real counseling recordings, transcripts, or student data in this
  folder.
- Install optional ASR dependencies in a separate virtual environment if needed.
- Review `requirements-funasr.txt` before installing anything.
- The first actual provider run may download models. Syntax checks and README
  review do not download models.

## Install Checks

Check whether the lab dependencies are already importable:

```powershell
python -c "import importlib.util as u; print('faster_whisper', bool(u.find_spec('faster_whisper'))); print('funasr', bool(u.find_spec('funasr')))"
```

Install the lab dependency candidates only when you are ready to run local ASR:

```powershell
python -m pip install -r .\experiments\asr_provider_lab\requirements-funasr.txt
```

If you only want the Whisper side first:

```powershell
python -m pip install faster-whisper
```

## Sample Run

Run from the repository root with a copied, non-sensitive audio file:

```powershell
python .\experiments\asr_provider_lab\asr_compare.py --audio path\to\sample.wav --provider both
```

Optional model controls:

```powershell
python .\experiments\asr_provider_lab\asr_compare.py --audio path\to\sample.wav --provider both --whisper-model small --funasr-model iic/SenseVoiceSmall --device cpu --compute-type int8
```

The default Whisper model is `small` with `compute_type=int8`, matching the
production app's balanced-mode model choice without importing production code.
The default FunASR model is `iic/SenseVoiceSmall` for Korean-capable local
experiments.

## Output

By default, JSON files are saved in:

```text
experiments/asr_provider_lab/sample_outputs
```

Each provider JSON contains:

- `audio_path`
- `provider`
- `status`
- `elapsed_sec`
- `text`
- `segments`
- `model`
- `device`
- `error`

The summary JSON includes both provider results when `--provider both` is used.

## Comparison Criteria

- Korean transcript readability and missing/extra words.
- Counseling-domain words such as curriculum, book names, homework, tests, and
  student/family references.
- Long silence, background noise, overlapped speech, and short back-and-forth
  handling.
- Segment/timestamp usefulness, when available.
- Runtime, memory pressure, install burden, and failure mode clarity.

Keep generated outputs outside production data folders, and avoid committing
real audio or transcript content.

## 2026-06-05 FunASR Experiment Result

This record documents the local Windows/CPU experiment only. It is not an
accuracy comparison because FunASR did not reach transcript generation.

Observed results:

- faster-whisper completed on the original m4a sample.
- faster-whisper elapsed time: 65.531 seconds.
- faster-whisper output size: 1,313 characters and 71 segments.
- FunASR on the original m4a sample timed out after 15 minutes and did not write
  a provider JSON result.
- FunASR on the first 30 seconds converted to wav also timed out after about
  724 seconds and did not write a provider JSON result.
- The 30-second wav test input was valid: 29.98 seconds, 16 kHz, mono.
- `funasr_diagnose.py` showed that `import funasr` completed in 14.297 seconds,
  `from funasr import AutoModel` completed, and `AutoModel(...)` initialization
  then timed out after 10 minutes.
- The diagnosis did not reach `model.generate(...)`.

Diagnosis JSON:

```text
experiments/asr_provider_lab/sample_outputs/20260605_160840_funasr_30s_test_funasr_diagnose.json
```

## Decision

For the current Windows/CPU PC environment, FunASR is excluded as a production
replacement candidate because it times out during `AutoModel(...)`
initialization before any transcription quality can be measured.

This is a runtime/environment stability failure, not a Korean ASR accuracy
ranking. No conclusion is made about FunASR transcript quality because the
experiment never reached `model.generate(...)`.

The recommended ASR path for counsel-note remains faster-whisper.

## Production Integration

Do not connect FunASR to the production app from this experiment.

Specifically:

- Do not change any `ASR_PROVIDER` default.
- Do not add FunASR fallback wiring.
- Do not change the counseling app transcription path.
- Do not modify production `app.py`, `data/`, Google Docs save logic, student
  DB/API code, templates, routes, or static assets for FunASR.

## Re-Evaluation Conditions

Re-evaluate FunASR only in a separate environment where all of the following are
true:

- A GPU PC is available, or a Linux runtime is available.
- Model cache/download has already completed successfully.
- A 30-second, 16 kHz mono wav sample can finish FunASR initialization and
  transcription within 1 minute.
- The experiment can produce provider JSON results for both faster-whisper and
  FunASR without touching production app code.

## Next Experiment: faster-whisper Optimization

FunASR testing is stopped for this Windows/CPU environment. The next safe lab
direction is to keep the production app on faster-whisper and compare
faster-whisper settings in this isolated folder only.

Candidate settings to compare:

- Model size: `tiny`, `base`, `small`.
- Compute type: start with `int8`; `float32` may be much slower on CPU and
  should be tested only with `--max-runs` or short wav clips.
- Device: keep `cpu` for matching the current production PC.
- VAD: compare `vad_filter=false` and `vad_filter=true` with the same audio.
- Segment handling: compare raw segment count and later consider simple segment
  merge/postprocessing rules outside the production app.
- Correction dictionaries: evaluate possible name/book-term correction only as
  a post-ASR lab step; do not modify production transcription output yet.

Benchmark CLI:

```powershell
python .\experiments\asr_provider_lab\whisper_benchmark.py --audio ".\experiments\asr_provider_lab\samples\funasr_30s_test.wav" --models tiny,base,small --compute-types int8 --device cpu
```

Use `--max-runs 1` for smoke tests. Results are written to
`experiments/asr_provider_lab/sample_outputs` as one JSON file plus one CSV
summary. The JSON keeps the transcript text for local comparison, while the CSV
keeps timing and size metrics for quick scanning.

Do not change the production ASR defaults from this experiment. Any production
change must wait until the lab shows a faster setting with acceptable Korean
readability, counseling-domain word handling, and stable runtime on the target
PC.

## 2026-06-05 faster-whisper 30s benchmark result

Input:

- `experiments/asr_provider_lab/samples/funasr_30s_test.wav`
- 29.98 seconds, 16 kHz, mono.
- CPU device, `int8` compute type.
- Benchmark output:
  `experiments/asr_provider_lab/sample_outputs/20260605_164541_funasr_30s_test_whisper_benchmark.json`
- CSV summary:
  `experiments/asr_provider_lab/sample_outputs/20260605_164541_funasr_30s_test_whisper_benchmark.csv`

Speed and size:

| model | VAD | elapsed_sec | text_len | segment_count | status |
| --- | --- | ---: | ---: | ---: | --- |
| tiny | off | 8.140 | 177 | 10 | ok |
| tiny | on | 3.094 | 185 | 14 | ok |
| base | off | 4.094 | 186 | 12 | ok |
| base | on | 6.031 | 190 | 12 | ok |
| small | off | 17.453 | 197 | 14 | ok |
| small | on | 11.906 | 185 | 12 | ok |

Quality notes, without storing the full transcript in this README:

- `tiny` is the fastest when VAD is on, but it has more unnatural Korean,
  repeated phrasing, and distorted assignment/book-page wording. Use only as a
  speed-first candidate.
- `base` preserves the homework and book/page context better than `tiny` while
  staying much faster than `small`. `base` with VAD off was the strongest
  speed/quality balance in this short sample.
- `small` gives the most natural counseling flow and keeps the key homework
  context best, but it is slower. `small` with VAD on was faster than `small`
  with VAD off, but the text was slightly more compressed.
- VAD on/off did not have a single winner. VAD improved `tiny` and `small`
  speed in this sample, but `base` was faster with VAD off. Segment counts also
  shifted, so VAD should be judged with transcript readability, not speed alone.

Lab recommendation:

- Speed-first candidate: `tiny / int8 / cpu / VAD on`.
- Speed/quality balance candidate: `base / int8 / cpu / VAD off`.
- Quality-first candidate: keep the current `small / int8 / cpu` family and
  compare VAD on/off on longer samples.

Production decision:

- Do not change the production ASR default from this 30-second benchmark alone.
- Do not change the counseling app transcription path.
- Next experiment: run `base` and `small` on at least one longer non-sensitive
  sample and review Korean readability, missed speech, hallucinations, and
  homework/book-name retention before considering any production setting change.

## 2026-06-05 faster-whisper 2min base vs small benchmark result

Input:

- `experiments/asr_provider_lab/samples/whisper_2min_test.wav`
- 119.98 seconds, 16 kHz, mono.
- CPU device, `int8` compute type, VAD off.
- Benchmark output:
  `experiments/asr_provider_lab/sample_outputs/20260605_165453_whisper_2min_test_whisper_benchmark.json`
- CSV summary:
  `experiments/asr_provider_lab/sample_outputs/20260605_165453_whisper_2min_test_whisper_benchmark.csv`

Speed and size:

| model | VAD | elapsed_sec | text_len | segment_count | status |
| --- | --- | ---: | ---: | ---: | --- |
| base | off | 35.750 | 814 | 46 | ok |
| small | off | 43.437 | 825 | 44 | ok |

Quality notes, without storing the full transcript in this README:

- `base` was faster and preserved the broad counseling flow: homework was not
  done, a friend visit was mentioned, and the discussion moved into motivation,
  tests, and study concerns.
- `base` had more visible word-level distortions in key places, including
  homework wording, the friend context, and some later study/test phrases.
- `small` was slower by 7.687 seconds on this 2-minute clip, but Korean sentence
  flow was more natural and the counseling context was easier to follow.
- `small` better preserved several important context words around the student
  name, homework, a friend living in the US, parent conflict, and the transformed
  printout/homework discussion.
- `small` still made errors, so this benchmark is not enough to justify a
  production default change by itself.

Lab recommendation:

- Candidate 1 for production-quality notes: `small / int8 / cpu / VAD off`.
- Candidate 2 for speed-sensitive operation: `base / int8 / cpu / VAD off`.
- Do not use `tiny` for production-quality counseling notes based on the 30s
  benchmark quality.

Production decision:

- Do not change the production ASR setting from this lab result alone.
- If runtime becomes the main operational pain point, test `base / int8 / cpu /
  VAD off` on more non-sensitive longer samples before considering it.
- If transcript quality remains the priority, keep the current `small / int8 /
  cpu` family and focus next on glossary/name correction and post-ASR cleanup in
  the lab.

## Next Experiment: ASR postprocess correction rules

Purpose:

- Test whether a small correction dictionary can improve faster-whisper output
  after transcription without changing model settings.
- Keep the experiment isolated to this lab. No production ASR path, app state,
  Google Docs logic, or student data is changed.

Lab files:

- Script:
  `experiments/asr_provider_lab/asr_postprocess_lab.py`
- Rules:
  `experiments/asr_provider_lab/asr_correction_rules.json`

Example:

```powershell
python .\experiments\asr_provider_lab\asr_postprocess_lab.py --input-json ".\experiments\asr_provider_lab\sample_outputs\20260605_165453_whisper_2min_test_whisper_benchmark.json"
```

Initial rule candidates are general academy terms only, such as:

- `에이블` or `에이 블` -> `A:ble`
- `에이팩스` or `아펙스` -> `APEX`
- `변형 프린터` -> `변형 프린트`
- `공통 수학` or `공수` -> `공통수학`
- `대수학` -> `대수`

Do not add student names, parent names, document IDs, URLs, or real counseling
sensitive details to the correction rules.

Before production consideration, validate:

- The rule does not incorrectly rewrite ordinary conversation.
- The rule improves copied summaries and saved transcript readability.
- The rule is deterministic and reversible enough for audit.
- The rule does not introduce private data, prompt hints, runtime logs, or
  process noise into transcript text.
- At least several non-sensitive samples show clear benefit with no harmful
  replacements.

## Next Experiment: ASR misrecognition candidate collection

Purpose:

- Collect repeated ASR phrases and known-term-like candidates for human review.
- Help decide which correction rules are worth adding later.
- Avoid automatic rule creation, especially for possible student or parent
  names.

Lab files:

- Script:
  `experiments/asr_provider_lab/asr_misrecognition_candidates.py`
- Known terms:
  `experiments/asr_provider_lab/asr_known_terms.json`

Example:

```powershell
python .\experiments\asr_provider_lab\asr_misrecognition_candidates.py --input-dir ".\experiments\asr_provider_lab\sample_outputs" --min-count 2
```

The output is one JSON file and one CSV file in
`experiments/asr_provider_lab/sample_outputs`.

Candidate types:

- `frequent_phrase`: repeated n-grams that may deserve review.
- `known_term_similarity`: phrases that look similar to known terms or common
  pronunciation variants, such as APEX candidates.

Safety rules:

- Candidates are review-only and must not be copied into
  `asr_correction_rules.json` without human validation.
- The tool marks possible private/name-like candidates with `sensitive_like`.
- Do not add student names, parent names, document IDs, URLs, or sensitive
  상담 details to correction rules.
- Keep transcript excerpts in generated JSON/CSV only; do not paste full
  transcripts into this README.

Candidate filtering rules:

- The full candidate list is still saved for audit.
- A separate `high_confidence_candidates` JSON/CSV is saved for likely spelling
  or notation variants only.
- A separate `excluded_candidates` JSON/CSV records why noisy candidates were
  excluded from the high-confidence list.
- Particle-attached forms such as `숙제를`, `숙제가`, or `숙제는` are excluded
  from high-confidence rules.
- Longer context phrases that already contain a known term, such as `변형 프린트
  문제`, are excluded because they are not replacement rules.
- Short general terms such as `숙제`, `문제`, or `프린트` are excluded or treated
  as low confidence.
- Candidate and target length must be reasonably close.
- Possible 2-3 character name-like Korean terms are marked with an exclusion
  reason and must not be auto-added to rules.
- High-confidence examples should look like notation/pronunciation variants,
  for example `에이팩스 -> APEX`, `아펙스 -> APEX`, `에이블 -> A:ble`, `공통 수학
  -> 공통수학`, or `변형 프린터 -> 변형 프린트`.

## Final Decision: ASR Lab 2026-06-05

Final lab decision:

- FunASR is excluded as a production replacement candidate on the current
  Windows/CPU PC because it timed out during `AutoModel(...)` initialization.
- The current production faster-whisper default, `small / cpu / int8 / VAD off`,
  matches the lab's quality-first candidate.
- `base / cpu / int8 / VAD off` remains a speed candidate, but it preserved
  counseling context less reliably than `small` in the 2-minute sample.
- `tiny` is excluded from production consideration because it was faster but had
  higher risk of Korean, book, and homework wording distortion.
- The correction-rule lab exists, but the current sample produced 0
  replacements.
- The misrecognition-candidate lab exists, but the high-confidence candidate
  count was 0. Do not expand rules automatically.
- There is no ASR change to apply to production now.

## Do Not Apply to Production Yet

Do not make any production ASR changes from this lab batch:

- Do not change the faster-whisper model default.
- Do not change device, compute type, VAD, or beam settings.
- Do not connect FunASR.
- Do not add automatic correction rules.
- Do not change the counseling app transcription path.

## When to Reopen This Experiment

Reopen this experiment only when enough non-sensitive samples are available for
manual review. At that point:

- Run lab-only benchmarks on those samples.
- Review repeated misrecognition candidates manually.
- Add only validated, non-sensitive, general academy terms to
  `asr_correction_rules.json`.
- Re-run the postprocess lab and confirm that replacements improve readability
  without harmful rewrites.
- Keep production unchanged until the lab result is stable across several
  samples.

## Do Not Commit Samples or Outputs

This lab can contain local audio and transcript-derived outputs. Keep those
files out of commits and release packages.

Do not commit:

- `samples/*`, because these files can contain voice recordings.
- `sample_outputs/*`, because JSON/CSV results can contain transcript text,
  snippets, timings, or other counseling-derived content.

Only commit selected lab source and documentation files when needed:

- `README.md`
- `*.py`
- `asr_correction_rules.json`
- `asr_known_terms.json`
- `.gitignore`
- `.gitkeep`
