# 주관식 답안지 Crop Lab

`tools/subjective_sheet_lab`는 전부 주관식인 단원평가 답안지를 다루기 위한 독립 프로토타입입니다.

이번 단계에서는 손글씨 OCR, 자동 채점, 학생 페이지 저장 API 연결을 하지 않습니다. 답안칸을 정확히 잘라내고, OCR/AI 인식 전 검증 자료 또는 OCR/AI 인식 결과 확인 자료로 쓸 수 있는 preview/result 구조를 만드는 것이 목적입니다.

## 정책 정리

- crop preview는 학생에게 답을 직접 입력시키는 화면이 아닙니다.
- crop preview는 OCR/AI 인식 전 단계의 검증 자료이거나, OCR/AI 인식 결과를 확인하기 위한 자료입니다.
- 학생용 최종 흐름은 `자동 인식 결과 확인 -> 문제 있는 문항만 수정 -> 최종 제출`입니다.
- OCR이 없는 현재 crop-only 단계는 학생 제출/자동 채점 플로우가 아닙니다.
- 주관식 `answersText`는 line-based 포맷이지만, OCR 전에는 생성하지 않고 `null`로 둡니다.

## 판독 파이프라인

1. `generate_subjective_sheet.py`
   - A4 세로형 답안지 PNG/PDF 생성
   - 네 귀퉁이 검은 마커 생성
   - 문항별 답안칸 bbox/crop bbox를 layout JSON에 저장

2. `make_synthetic_filled_sheet.py`
   - 실제 촬영본 없이 검증할 synthetic 답안 이미지 생성
   - `--answers "1|-3|x=2|sqrt(3)"`처럼 샘플 답안을 넣음

3. `crop_answer_boxes.py`
   - 네 귀퉁이 검은 마커를 찾아 homography 원근 보정을 시도
   - 보정 성공 시 보정된 전체 페이지 기준으로 crop
   - 마커 후보가 정사각형/크기/위치/geometry 검증을 통과하지 못하면 crop을 중단하고 `needs_retake` 처리
   - layout 좌표를 이미지 크기에 맞춰 스케일링
   - 문항별 crop 이미지 생성
   - OCR 연결 전 상태인 `pending_recognition` result JSON 생성

4. `make_crop_preview.py`
   - crop 이미지를 확인용 contact sheet 형태의 preview PNG로 생성
   - source filename, correction, fallback, marker_detected 상태 표시

5. `source_overlay.png`
   - 원본 사진 위에 detected marker 위치와 문항별 crop bbox를 표시
   - crop 실패 원인을 눈으로 확인하기 위한 디버그 자료

## 실행 예시

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\generate_subjective_sheet.py --config .\tools\subjective_sheet_lab\subjective_sheet_config.example.json --out .\tools\subjective_sheet_lab\samples\output\subjective_sheet

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_synthetic_filled_sheet.py --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet.layout.json --sheet .\tools\subjective_sheet_lab\samples\output\subjective_sheet.png --answers "1|-3|x=2|sqrt(3)" --out .\tools\subjective_sheet_lab\samples\output\subjective_sheet_filled.png

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\crop_answer_boxes.py --image .\tools\subjective_sheet_lab\samples\output\subjective_sheet_filled.png --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet.layout.json --out-dir .\tools\subjective_sheet_lab\samples\output\crops --result-out .\tools\subjective_sheet_lab\samples\output\subjective_crop_result.json --corrected-out .\tools\subjective_sheet_lab\samples\output\subjective_corrected.png --source-overlay-out .\tools\subjective_sheet_lab\samples\output\source_overlay.png

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_crop_preview.py --result .\tools\subjective_sheet_lab\samples\output\subjective_crop_result.json --out .\tools\subjective_sheet_lab\samples\output\subjective_preview.png
```

마커 검출 기본값은 `--marker-mode auto`입니다. `strict -> normal -> tolerant` 순서로 시도하고, corner search window마다 adaptive threshold를 적용합니다. 실제 사진을 디버그할 때만 `--marker-mode strict|normal|tolerant`, `--no-adaptive-threshold`, `--dark-threshold`, `--marker-search-ratio`를 조정합니다.

## result JSON 상태값

```json
{
  "ok": true,
  "mode": "subjective_handwriting_crop_only",
  "test_id": "subjective_unit_test_sample",
  "answersText": null,
  "items": [
    {
      "question": 1,
      "cropPath": "crops/q001.png",
      "recognized": null,
      "final": null,
      "status": "pending_recognition"
    }
  ],
  "warnings": ["ocr_not_connected"]
}
```

`recognized`는 OCR/AI가 읽은 후보값, `final`은 확인 후 최종값을 담기 위한 자리입니다. 현재 단계에서는 둘 다 `null`입니다.

`preprocess.correction`은 원근 보정 성공 시 `homography`, 마커 검증 실패 시 `marker_validation_failed`입니다. `preprocess.corrected_image`가 있으면 그 파일은 crop 기준이 된 보정 이미지입니다. `preprocess.source_overlay`는 원본 사진 위에 마커 후보와 crop bbox를 그린 디버그 이미지입니다.

마커 검증 실패 시 result는 다음 정책을 따릅니다.

```json
{
  "ok": false,
  "status": "needs_retake",
  "alignment_ok": false,
  "items": [],
  "warnings": ["ocr_not_connected", "marker_validation_failed", "retake_photo_required"]
}
```

Marker diagnostics fields:

- `preprocess.marker_pass`: accepted pass name, such as `strict`, `normal`, or `tolerant`.
- `preprocess.marker_mode`: requested mode, usually `auto`.
- `preprocess.adaptive_threshold`: whether local corner thresholds were used.
- `preprocess.marker_attempts`: compact strict/normal/tolerant attempt summary for debugging false positives and false negatives.

## 1단계 성공 기준

- 주관식 답안지 PNG/PDF 생성
- layout JSON 생성
- synthetic filled sheet 생성
- `crops/q001.png` 등 문항별 crop 이미지 생성
- `subjective_preview.png` 생성
- result JSON이 OCR/AI 인식 전 대기 상태를 명확히 표현

## 학생 페이지 이식 방향

2단계에서 학생 페이지에 붙일 때는 OCR 결과를 바로 저장하지 않고, crop preview와 후보 텍스트를 보여준 뒤 문제가 있는 문항만 수정하게 하는 방식이 안전합니다.

주관식 최종 `answersText`는 line-based 포맷이 안전합니다.

```text
1
-3
x=2
sqrt(3)
```

## 현재 한계

- OCR 없음
- 자동 채점 없음
- 실제 촬영본의 강한 원근 왜곡은 추가 튜닝 필요
- 마커가 가려지거나 그림자가 강하면 crop을 생성하지 않고 다시 촬영해야 함
- 자동 인식 결과 확인/수정 UI는 아직 없음
- 서버/API/DB 이식은 별도 단계
## v2 sheet layout

The v2 generated sheet is designed to reduce marker false negatives and false positives before OCR/AI is added.

- Larger black markers: `128px`.
- Marker inset from page edges: `110px`.
- Marker quiet zone: `70px` of clean white margin.
- Answer grid starts at `720px`, leaving more distance from the top markers and header.
- Bottom margin is `390px`, keeping Q010/Q020 away from the bottom markers.
- Column gap is `150px`, and each `crop_bbox` targets the inner answer-writing area instead of the full answer box.

Use v2 output for new real-photo tests. Existing `real_01_good.jpg` and `real_03_shadow.jpg` are v1 photos, so `real_03_shadow` is not a valid measure of the v2 layout. Print or display `subjective_sheet_v2.pdf`, take a new photo with all four corner markers visible, then run `crop_answer_boxes.py` against `subjective_sheet_v2.layout.json`.

## OCR/AI recognition planning

The crop-only stage is not a student submission or auto-grading flow. It intentionally keeps `answersText` as `null` and each item in `pending_recognition` until an OCR/AI layer produces a candidate answer.

The student-facing policy remains:

1. Automatic recognition fills candidate answers.
2. The student reviews the recognized result.
3. Only problem items are corrected.
4. The reviewed `final` values are joined into line-based `answersText`.
5. Final submission/auto-grading happens only after review.

Current candidate recommendation:

- First paid/API benchmark: Mathpix, because it is purpose-built for STEM handwriting and math images.
- Secondary API benchmark: OpenAI or Gemini vision, with strict JSON prompts and review-required output.
- Cheap baseline OCR: Google Cloud Vision or Azure Read, useful for digits/plain text but not enough for math answers alone.
- Local experiment after API baseline: Pix2Text first, then pix2tex/PaddleOCR/TrOCR only if install/runtime burden is acceptable.

Prototype files for the recognition layer:

- `tools/subjective_sheet_lab/ocr_candidates_report.md`: candidate comparison and evaluation design.
- `tools/subjective_sheet_lab/ocr_result_schema.example.json`: common recognition result shape.
- `tools/subjective_sheet_lab/mock_recognition_result.py`: no-OCR mock generator that injects expected answers into the future recognition result schema.

Mock command:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\mock_recognition_result.py --crop-result .\tools\subjective_sheet_lab\samples\output\subjective_sheet_v2_result.json --answers "1|-3|x=2|sqrt(3)|1/2|0|5|2x+1|3sqrt(2)|6|256|9/2|1,3|1<=x<=3|-1<x<5|y=3|1/2,9/2|129/2|281|26sqrt(21)" --out .\tools\subjective_sheet_lab\samples\output\subjective_sheet_v2_mock_ocr_result.json
```

## OCR evaluation harness

Before connecting a real OCR/AI engine, use the evaluation harness to compare recognized answers with a line-based expected answer file.

Files:

- `tools/subjective_sheet_lab/expected_answers.example.txt`: 20-line expected answer sample.
- `tools/subjective_sheet_lab/normalize_math_answer.py`: conservative comparison normalization.
- `tools/subjective_sheet_lab/evaluate_ocr_result.py`: JSON/CSV/Markdown evaluation report generator.

Normalization is intentionally light:

- trim leading/trailing whitespace
- normalize fullwidth/halfwidth forms
- remove whitespace
- normalize minus variants to `-`
- normalize `√` to `sqrt`
- normalize `π` to `pi`
- normalize `≤`/`≥` to `<=`/`>=`
- remove explicit multiplication symbols `×`, `⋅`, `·`, `*`

It does not perform symbolic equivalence. For example, `1/2` and `0.5` are not treated as equal.

Evaluation statuses:

- `exact_match`: raw recognized text equals expected text.
- `normalized_match`: raw text differs but normalized text matches.
- `missing`: recognized text is empty or null.
- `needs_review`: not matched and not missing.

Evaluation command:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\samples\output\subjective_sheet_v2_mock_ocr_result.json --expected .\tools\subjective_sheet_lab\expected_answers.example.txt --out-json .\tools\subjective_sheet_lab\samples\output\subjective_sheet_v2_eval.json --out-csv .\tools\subjective_sheet_lab\samples\output\subjective_sheet_v2_eval.csv --out-md .\tools\subjective_sheet_lab\samples\output\subjective_sheet_v2_eval.md
```

The Markdown/CSV/JSON reports are developer/admin evaluation artifacts. They are not a student-facing UI and do not submit or grade answers. Real OCR engine adapters should produce the same recognition JSON shape, then reuse this evaluator for apples-to-apples comparison.

## Mathpix crop-5 adapter

`tools/subjective_sheet_lab/mathpix_crop_ocr.py` prepares a limited Mathpix experiment for the first five crops. It is dry-run by default and does not call Mathpix unless `--allow-network` is explicitly supplied.

Security/cost rules:

- Credentials are read only from environment variables: `MATHPIX_APP_ID`, `MATHPIX_APP_KEY`.
- The script does not read `.env`, key files, token files, or secret files.
- Default run is dry-run and writes a skeleton JSON only.
- Real Mathpix calls may cost money and upload crop images to an external service.
- Default `--limit` is `5`.
- This is still not connected to the student page, submission API, or auto-grading.

PowerShell environment variables:

```powershell
$env:MATHPIX_APP_ID="여기에_APP_ID"
$env:MATHPIX_APP_KEY="여기에_APP_KEY"
```

Dry-run:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\mathpix_crop_ocr.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1,2,3,4,5 --out .\tools\subjective_sheet_lab\samples\output\ocr_result_crop5_mathpix_dryrun.json
```

Actual limited call:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\mathpix_crop_ocr.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1,2,3,4,5 --out .\tools\subjective_sheet_lab\samples\output\ocr_result_crop5_mathpix.json --allow-network --limit 5
```

Evaluation:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\samples\output\ocr_result_crop5_mathpix.json --expected .\tools\subjective_sheet_lab\expected_answers_crop5.txt --out-json .\tools\subjective_sheet_lab\samples\output\ocr_eval_crop5_mathpix.json --out-csv .\tools\subjective_sheet_lab\samples\output\ocr_eval_crop5_mathpix.csv --out-md .\tools\subjective_sheet_lab\samples\output\ocr_eval_crop5_mathpix.md
```

## Manual Vision crop-5 benchmark

If there is no API key, use the manual Vision benchmark. This is only for feasibility testing and is not an operational automation path.

Create a contact sheet:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_vision_contact_sheet.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1,2,3,4,5 --out .\tools\subjective_sheet_lab\samples\output\vision_contact_crop5.png
```

Then:

1. Upload `tools/subjective_sheet_lab/samples/output/vision_contact_crop5.png` to ChatGPT or Gemini web UI.
2. Paste `tools/subjective_sheet_lab/vision_manual_prompt_crop5.md`.
3. Save the JSON-only answer as `tools/subjective_sheet_lab/samples/output/ocr_result_crop5_manual_vision.json`.
4. Evaluate it:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\samples\output\ocr_result_crop5_manual_vision.json --expected .\tools\subjective_sheet_lab\expected_answers_crop5.txt --out-json .\tools\subjective_sheet_lab\samples\output\ocr_eval_crop5_manual_vision.json --out-csv .\tools\subjective_sheet_lab\samples\output\ocr_eval_crop5_manual_vision.csv --out-md .\tools\subjective_sheet_lab\samples\output\ocr_eval_crop5_manual_vision.md
```

This manual route does not call any API from this project, does not read API keys, does not submit answers, and does not grade. It only tests whether a general Vision model can read the five crop images.

## Manual Vision 20-question benchmark

After crop-5 passes, split the full 20-question evaluation into two contact sheets. This keeps each upload readable and avoids forcing a web Vision model to inspect a very tall single image.

Create contact sheets:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_vision_contact_sheet.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1-10 --out .\tools\subjective_sheet_lab\samples\output\vision_contact_q001_q010.png

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_vision_contact_sheet.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 11-20 --out .\tools\subjective_sheet_lab\samples\output\vision_contact_q011_q020.png
```

Manual web flow:

1. Upload `vision_contact_q001_q010.png` to ChatGPT/Gemini web UI.
2. Paste `tools/subjective_sheet_lab/vision_manual_prompt_20.md`.
3. Save JSON as `tools/subjective_sheet_lab/samples/output/ocr_result_manual_vision_q001_q010.json`.
4. Repeat for `vision_contact_q011_q020.png`.
5. Save JSON as `tools/subjective_sheet_lab/samples/output/ocr_result_manual_vision_q011_q020.json`.

Merge the two result parts:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\merge_manual_vision_results.py --part .\tools\subjective_sheet_lab\samples\output\ocr_result_manual_vision_q001_q010.json .\tools\subjective_sheet_lab\samples\output\ocr_result_manual_vision_q011_q020.json --out .\tools\subjective_sheet_lab\samples\output\ocr_result_manual_vision_20.json
```

Evaluate the merged result:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\samples\output\ocr_result_manual_vision_20.json --expected .\tools\subjective_sheet_lab\expected_answers.example.txt --out-json .\tools\subjective_sheet_lab\samples\output\ocr_eval_manual_vision_20.json --out-csv .\tools\subjective_sheet_lab\samples\output\ocr_eval_manual_vision_20.csv --out-md .\tools\subjective_sheet_lab\samples\output\ocr_eval_manual_vision_20.md
```

This is still only a keyless feasibility benchmark. It is not an app feature, not a student-facing flow, and not auto-grading.

## Manual Vision stress test management

A single 20/20 manual Vision result is useful, but it is not enough to approve the workflow for real use. The next validation step is a small stress test across multiple writers and photo conditions.

Default structure:

```text
tools/subjective_sheet_lab/samples/stress_test/
  person_01/
    input/
    crops/
    contact/
    vision_result/
    eval/
  person_02/
    input/
    crops/
    contact/
    vision_result/
    eval/
  person_03/
    input/
    crops/
    contact/
    vision_result/
    eval/
  summary/
```

Create a case:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\init_stress_test_case.py --case-id person_01 --image .\tools\subjective_sheet_lab\samples\input\real_01_good.jpg --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet.layout.json --out-root .\tools\subjective_sheet_lab\samples\stress_test
```

The initializer copies the source photo into `input/`, creates question crops in `crops/`, and creates two manual Vision contact sheets in `contact/`:

- `vision_contact_q001_q010.png`
- `vision_contact_q011_q020.png`

Manual Vision result storage:

1. Upload one contact sheet to ChatGPT/Gemini web UI.
2. Paste `tools/subjective_sheet_lab/vision_manual_prompt_stress_test.md`.
3. Save the JSON result under the case `vision_result/` folder.
4. Repeat for the second contact sheet.
5. Merge parts with `merge_manual_vision_results.py`, or save a final 20-question JSON directly as `vision_result/ocr_result_manual_vision_20.json`.

Evaluate one case:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\samples\stress_test\person_01\vision_result\ocr_result_manual_vision_20.json --expected .\tools\subjective_sheet_lab\stress_test_answers.example.txt --out-json .\tools\subjective_sheet_lab\samples\stress_test\person_01\eval\eval.json --out-csv .\tools\subjective_sheet_lab\samples\stress_test\person_01\eval\eval.csv --out-md .\tools\subjective_sheet_lab\samples\stress_test\person_01\eval\eval.md
```

Summarize all evaluated cases:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\summarize_stress_test_results.py --eval-root .\tools\subjective_sheet_lab\samples\stress_test --out-md .\tools\subjective_sheet_lab\samples\stress_test\summary\summary.md --out-json .\tools\subjective_sheet_lab\samples\stress_test\summary\summary.json --out-csv .\tools\subjective_sheet_lab\samples\stress_test\summary\summary.csv
```

The summarizer reports per-case accuracy, aggregate accuracy, total review/missing counts, and worst questions by review/missing frequency. If no eval JSON files exist yet, it still writes summary files with a `no_eval_json_files_found` warning.

Recommended stress test coverage:

- Minimum 3 writers.
- One front-facing bright photo.
- One slightly tilted photo.
- One mild-shadow photo.

Decision guide:

- Average 18/20 or higher: promising.
- Average 16-17/20: needs prompt, crop, or layout tuning.
- Average 15/20 or lower: operationally risky.

Answers that need extra attention:

- `-3` vs `-7`
- `1` vs `7`
- `0` vs `O`
- `1/2` vs `7/2`
- `<` and `<=`
- comma answers such as `1,3`
- `sqrt(...)` answers

This stress test workflow is still developer/admin validation only. It does not call external APIs from the repo, does not read API keys, does not submit answers, does not grade, and is not connected to the student page.
