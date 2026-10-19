# OCR Crop-5 Evaluation Plan

Scope: prepare a five-crop OCR/AI experiment before any real external API call. This plan does not call Mathpix, OpenAI, Gemini, Google Vision, Azure, or any other OCR service. It does not read API keys, install packages, submit student answers, or run auto-grading.

## Experiment Target

Use the first five cropped subjective-answer images from the v2 synthetic/real-test pipeline:

| Question | Crop file | Expected answer | Notes |
|---:|---|---|---|
| 1 | `tools/subjective_sheet_lab/samples/output/v2_crops/q001.png` | `1` | single digit |
| 2 | `tools/subjective_sheet_lab/samples/output/v2_crops/q002.png` | `-3` | negative sign |
| 3 | `tools/subjective_sheet_lab/samples/output/v2_crops/q003.png` | `x=2` | variable/equality |
| 4 | `tools/subjective_sheet_lab/samples/output/v2_crops/q004.png` | `0.5` | decimal |
| 5 | `tools/subjective_sheet_lab/samples/output/v2_crops/q005.png` | `1/2` | fraction-like text |

Expected answers are stored in:

```text
tools/subjective_sheet_lab/expected_answers_crop5.txt
```

## Candidate Order

1. Mathpix
   - First candidate because the target answers are short math/STEM handwriting snippets.
   - Run only five crop images for the first paid/API experiment.
   - Store raw OCR output separately from normalized/evaluated output.

2. OpenAI or Gemini Vision
   - Second candidate if Mathpix is too costly, operationally inconvenient, or inaccurate on these crops.
   - Use strict JSON output prompts and keep all results review-required.

## Result JSON Format

The OCR adapter should produce a JSON file shaped like:

```json
{
  "ok": true,
  "mode": "subjective_handwriting_recognition",
  "engine": "mathpix",
  "test_id": "subjective_unit_test_sample",
  "items": [
    {"question": 1, "cropPath": "q001.png", "recognized": "1", "final": "1", "status": "recognized", "confidence": null, "warnings": []},
    {"question": 2, "cropPath": "q002.png", "recognized": "-3", "final": "-3", "status": "recognized", "confidence": null, "warnings": []},
    {"question": 3, "cropPath": "q003.png", "recognized": "x=2", "final": "x=2", "status": "recognized", "confidence": null, "warnings": []},
    {"question": 4, "cropPath": "q004.png", "recognized": "0.5", "final": "0.5", "status": "recognized", "confidence": null, "warnings": []},
    {"question": 5, "cropPath": "q005.png", "recognized": "1/2", "final": "1/2", "status": "recognized", "confidence": null, "warnings": []}
  ],
  "warnings": []
}
```

Example file:

```text
tools/subjective_sheet_lab/ocr_result_crop5.example.json
```

## Evaluation Command

After a real OCR engine writes a crop-5 result JSON, evaluate it with:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\ocr_result_crop5.example.json --expected .\tools\subjective_sheet_lab\expected_answers_crop5.txt --out-json .\tools\subjective_sheet_lab\samples\output\ocr_crop5_eval.json --out-csv .\tools\subjective_sheet_lab\samples\output\ocr_crop5_eval.csv --out-md .\tools\subjective_sheet_lab\samples\output\ocr_crop5_eval.md
```

For a real engine, replace `ocr_result_crop5.example.json` with the engine output file.

For manual Vision testing, do not paste the expected-answer file into the Vision prompt. Upload only the contact sheet and use `vision_manual_prompt_crop5.md`, so the result measures image reading rather than copying the answer key.

## Pass / Tune / Reject Rule

- Pass: 4 or 5 of 5 items are `exact_match` or `normalized_match`.
- Tune: 2 or 3 of 5 items are `exact_match` or `normalized_match`.
- Reject for this use case: 0 or 1 of 5 items are `exact_match` or `normalized_match`.

Even if a candidate passes, it is not allowed to auto-submit answers. The student-facing flow remains:

1. Automatic recognition.
2. Student reviews recognized answers.
3. Student fixes only incorrect/uncertain items.
4. Reviewed `final` values become line-based `answersText`.
5. Final submit/grade step happens later.

## Safety Checklist Before Real OCR

- Do not read API keys in this repository.
- Do not commit or print API keys.
- Do not send more than five crops in the first experiment.
- Save raw engine output and evaluated output separately.
- Record engine name, date, prompt/options, and any confidence values.
- Treat missing or low-confidence outputs as review-required.

## Mathpix Adapter Commands

The adapter is:

```text
tools/subjective_sheet_lab/mathpix_crop_ocr.py
```

It is dry-run by default. Credentials are read only from `MATHPIX_APP_ID` and `MATHPIX_APP_KEY` environment variables. It does not read `.env` or secret files.

Dry-run:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\mathpix_crop_ocr.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1,2,3,4,5 --out .\tools\subjective_sheet_lab\samples\output\ocr_result_crop5_mathpix_dryrun.json
```

Actual limited call:

```powershell
$env:MATHPIX_APP_ID="여기에_APP_ID"
$env:MATHPIX_APP_KEY="여기에_APP_KEY"
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\mathpix_crop_ocr.py --crop-dir .\tools\subjective_sheet_lab\samples\output\v2_crops --questions 1,2,3,4,5 --out .\tools\subjective_sheet_lab\samples\output\ocr_result_crop5_mathpix.json --allow-network --limit 5
```
