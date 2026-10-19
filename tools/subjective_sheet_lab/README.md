# Subjective Sheet Lab

## v2 sheet layout

The default example config now generates a v2 sheet. The goal is to improve real-photo marker detection by changing the printed form, not by accepting suspicious marker candidates.

- Larger black corner markers: `marker.size_px=128`.
- Marker inset: `marker.inset_px=110`.
- White quiet zone around each marker: `marker.quiet_zone_px=70`.
- Answer grid starts lower: `layout.top_content_start_px=720`.
- Bottom margin is larger: `layout.bottom_margin_px=390`.
- Column gap is wider: `layout.column_gap_px=150`.
- Crops use the inner answer-writing area, so labels, borders, and corner markers stay outside OCR/AI input crops.

Real-photo guidance for v2:

- Print and photograph the v2 sheet, not an older v1 sheet, when testing the improved layout.
- Keep all four corner markers fully visible with white paper around them.
- Avoid putting fingers, shadows, or desk edges over the corner marker quiet zones.
- If alignment fails, the cropper should return `needs_retake` instead of creating misleading crops.

## Mathpix crop-5 dry-run

`mathpix_crop_ocr.py` prepares a limited five-crop Mathpix OCR experiment. It is dry-run by default and calls the network only when `--allow-network` is present.

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\mathpix_crop_ocr.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1,2,3,4,5 --out .\tools\subjective_sheet_lab\samples\output\ocr_result_crop5_mathpix_dryrun.json
```

Actual calls require `MATHPIX_APP_ID` and `MATHPIX_APP_KEY` environment variables and may cost money. The adapter does not read `.env` or secret files, and it is not connected to student submission or auto-grading.

## Manual Vision crop-5 contact sheet

Use this when testing ChatGPT/Gemini web UI without API keys:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_vision_contact_sheet.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1,2,3,4,5 --out .\tools\subjective_sheet_lab\samples\output\vision_contact_crop5.png
```

Upload `vision_contact_crop5.png`, paste `vision_manual_prompt_crop5.md`, save the JSON result, and run `evaluate_ocr_result.py`. This is a manual feasibility check only.

## Manual Vision 20-question split

`make_vision_contact_sheet.py` accepts ranges such as `1-10` and `11-20`.

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_vision_contact_sheet.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1-10 --out .\tools\subjective_sheet_lab\samples\output\vision_contact_q001_q010.png

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_vision_contact_sheet.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 11-20 --out .\tools\subjective_sheet_lab\samples\output\vision_contact_q011_q020.png
```

Upload the two images separately, use `vision_manual_prompt_20.md`, then merge:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\merge_manual_vision_results.py --part .\tools\subjective_sheet_lab\samples\output\ocr_result_manual_vision_q001_q010.json .\tools\subjective_sheet_lab\samples\output\ocr_result_manual_vision_q011_q020.json --out .\tools\subjective_sheet_lab\samples\output\ocr_result_manual_vision_20.json
```

Evaluate the merged JSON with `evaluate_ocr_result.py` and `expected_answers.example.txt`.

## Manual Vision stress test

The crop-5 and 20-question manual Vision checks are promising, but one 20/20 result is not enough to decide whether the flow is operationally safe. Use the stress test tools to repeat the same crop -> contact sheet -> manual Vision JSON -> evaluation flow across multiple handwriting samples and photo conditions.

Recommended folder structure:

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

Create one case from a photographed sheet:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\init_stress_test_case.py --case-id person_01 --image .\tools\subjective_sheet_lab\samples\input\real_01_good.jpg --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet.layout.json --out-root .\tools\subjective_sheet_lab\samples\stress_test
```

The case initializer copies the input photo, runs `crop_answer_boxes.py`, and creates:

- `contact/vision_contact_q001_q010.png`
- `contact/vision_contact_q011_q020.png`
- `vision_result/README.txt`

Manual Vision result flow:

1. Upload `contact/vision_contact_q001_q010.png` to ChatGPT/Gemini web UI.
2. Paste `tools/subjective_sheet_lab/vision_manual_prompt_stress_test.md`.
3. Save the JSON as `vision_result/ocr_result_manual_vision_q001_q010.json`.
4. Repeat for `contact/vision_contact_q011_q020.png`.
5. Merge the two JSON parts if desired, or save a finished 20-question JSON directly as `vision_result/ocr_result_manual_vision_20.json`.

Evaluate one case:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\samples\stress_test\person_01\vision_result\ocr_result_manual_vision_20.json --expected .\tools\subjective_sheet_lab\stress_test_answers.example.txt --out-json .\tools\subjective_sheet_lab\samples\stress_test\person_01\eval\eval.json --out-csv .\tools\subjective_sheet_lab\samples\stress_test\person_01\eval\eval.csv --out-md .\tools\subjective_sheet_lab\samples\stress_test\person_01\eval\eval.md
```

Summarize all cases:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\summarize_stress_test_results.py --eval-root .\tools\subjective_sheet_lab\samples\stress_test --out-md .\tools\subjective_sheet_lab\samples\stress_test\summary\summary.md --out-json .\tools\subjective_sheet_lab\samples\stress_test\summary\summary.json --out-csv .\tools\subjective_sheet_lab\samples\stress_test\summary\summary.csv
```

Suggested stress test coverage:

- At least 3 people before treating the workflow as reliable.
- Bright/front-facing photo.
- Slightly tilted photo.
- Mild shadow photo.

Decision guide:

- Average 18/20 or higher: promising.
- Average 16-17/20: needs crop/prompt/layout tuning.
- Average 15/20 or lower: operationally risky.

High-risk answer shapes to watch:

- `-3` vs `-7`
- `1` vs `7`
- `0` vs `O`
- `1/2` vs `7/2`
- inequalities such as `<` and `<=`
- comma answers such as `1,3`
- `sqrt(...)` answers

This stress test path still makes no external API calls from this project. It is for developer/admin validation only and remains separate from the student page, submission API, database, and grading.

주관식 단원평가 답안지 crop 독립 프로토타입입니다.

이 실험 폴더는 상담앱 본체, 학생 페이지, 서버 API, DB, `data/**`와 연결하지 않습니다. 1단계 목표는 OCR/자동 채점이 아니라 답안칸 이미지를 안정적으로 잘라내고, 나중에 OCR/AI 인식 후보 확인 단계에 넘길 수 있는 구조를 만드는 것입니다.

## 정책

- crop preview는 학생에게 답을 처음부터 직접 입력시키는 화면이 아닙니다.
- crop preview는 OCR/AI 인식 전 단계의 검증 자료이거나, OCR/AI 인식 결과를 확인하기 위한 자료입니다.
- 학생용 최종 흐름은 `자동 인식 결과 확인 -> 문제 있는 문항만 수정 -> 최종 제출`입니다.
- OCR이 없는 현재 단계는 학생 제출/자동 채점 플로우로 간주하지 않습니다.
- 주관식 `answersText`는 line-based 포맷을 사용하지만, OCR 전 crop-only 단계에서는 생성하지 않고 `null`로 둡니다.

## 흐름

1. 주관식 답안지 PNG/PDF와 layout JSON을 생성합니다.
2. synthetic 답안 이미지를 만듭니다.
3. 문항별 답안칸을 `crops/q001.png`처럼 잘라냅니다.
4. crop 확인용 preview PNG를 만듭니다.
5. result JSON은 OCR/AI 인식 전 대기 상태인 `pending_recognition`으로 둡니다.

실제 촬영본에서는 네 귀퉁이 검은 마커를 찾아 homography 원근 보정을 먼저 시도합니다. 기본값은 `--marker-mode auto`이며, `strict -> normal -> tolerant` 순서로 여러 pass를 시도합니다. 각 pass는 corner window, dark threshold, fill ratio, 크기 허용 범위를 다르게 적용하고, corner별 adaptive threshold를 사용합니다.

마커 후보는 모서리 근처, 정사각형 비율, 예상 크기, fill ratio, 네 점 geometry를 모두 통과해야 합니다. tolerant pass에서도 최종 validation은 반드시 통과해야 하며, 검증 실패 시 잘못된 crop을 만들지 않고 `needs_retake` 상태로 둡니다.

## PowerShell 예시

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\generate_subjective_sheet.py --config .\tools\subjective_sheet_lab\subjective_sheet_config.example.json --out .\tools\subjective_sheet_lab\samples\output\subjective_sheet

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_synthetic_filled_sheet.py --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet.layout.json --sheet .\tools\subjective_sheet_lab\samples\output\subjective_sheet.png --answers "1|-3|x=2|sqrt(3)" --out .\tools\subjective_sheet_lab\samples\output\subjective_sheet_filled.png

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\crop_answer_boxes.py --image .\tools\subjective_sheet_lab\samples\output\subjective_sheet_filled.png --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet.layout.json --out-dir .\tools\subjective_sheet_lab\samples\output\crops --result-out .\tools\subjective_sheet_lab\samples\output\subjective_crop_result.json --corrected-out .\tools\subjective_sheet_lab\samples\output\subjective_corrected.png --source-overlay-out .\tools\subjective_sheet_lab\samples\output\source_overlay.png

.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\make_crop_preview.py --result .\tools\subjective_sheet_lab\samples\output\subjective_crop_result.json --out .\tools\subjective_sheet_lab\samples\output\subjective_preview.png
```

Marker detection options are normally left at the defaults. Use them only when debugging a difficult photo.

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\crop_answer_boxes.py --image .\tools\subjective_sheet_lab\samples\input\real_01_good.jpg --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet.layout.json --out-dir .\tools\subjective_sheet_lab\samples\real_eval\real_01_good_v4\crops --result-out .\tools\subjective_sheet_lab\samples\real_eval\real_01_good_v4\result.json --corrected-out .\tools\subjective_sheet_lab\samples\real_eval\real_01_good_v4\corrected.png --source-overlay-out .\tools\subjective_sheet_lab\samples\real_eval\real_01_good_v4\source_overlay.png --marker-mode auto
```

- `--marker-mode strict|normal|tolerant|auto`: default is `auto`, which tries strict, normal, then tolerant.
- `--adaptive-threshold`: adjusts dark marker thresholds per corner window. This is enabled by default.
- `--no-adaptive-threshold`: disables per-corner adaptive thresholds.
- `--dark-threshold`, `--marker-search-ratio`: use only for focused photo debugging.

## 출력물

- `subjective_sheet.png`
- `subjective_sheet.pdf`
- `subjective_sheet.layout.json`
- `subjective_sheet_filled.png`
- `crops/q001.png` ... `crops/q020.png`
- `subjective_crop_result.json`
- `subjective_preview.png`
- `source_overlay.png`

## result JSON

OCR이 아직 연결되지 않았기 때문에 `recognized`와 `final`은 `null`입니다. 이 단계의 `answersText`도 `null`입니다.

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
      "status": "pending_recognition",
      "bbox": [370, 698, 1146, 892]
    }
  ],
  "preprocess": {
    "marker_detected": true,
    "fallback": false,
    "correction": "homography",
    "marker_pass": "normal",
    "marker_mode": "auto",
    "adaptive_threshold": true,
    "marker_attempts": [],
    "corrected_image": "subjective_corrected.png",
    "source_overlay": "source_overlay.png",
    "alignment_ok": true
  },
  "warnings": ["ocr_not_connected"]
}
```

## 현재 한계

- OCR 없음
- 자동 채점 없음
- 강한 그림자, 흐림, 마커 가림이 있으면 원근 보정이 실패할 수 있음
- 마커 검증 실패 시 `marker_validation_failed`, `retake_photo_required` 경고를 남기고 crop을 생성하지 않음
- 자동 인식 결과 확인/수정 UI는 2단계에서 구현
- 학생 페이지 이식은 별도 단계
