# Answer Sheet v3 Design Notes

Purpose: create an OCR/Vision-friendly answer sheet prototype while preserving the current fixed format.

## Fixed Format Preserved

- A4 page at 2480 x 3508 px, 300 dpi.
- 20 questions.
- 2 columns x 10 rows.
- 4 bold corner markers.
- Marker quiet zones remain clear.
- Problem numbers remain outside the answer crop.
- Crop policy remains compatible with `full_answer_box_with_safe_margin`.

## v3 Design Direction

- Keep the current one-page layout concept.
- Increase answer box height where the fixed A4 layout allows it.
- Use lighter answer-box borders so Vision models are less likely to treat borders as answer strokes.
- Make the safe-zone dotted guide slightly darker than the first v3 draft while keeping it light gray.
- Start the answer crop after the question-number divider clearance so the vertical number-cell line is not included.
- Keep the internal write-safe-zone guide very light and text-free.
- Raise the bottom edge of the write-safe-zone to discourage answers touching the lower border.
- Use a shorter, larger two-line header for common OCR confusion cases:
  - 칸 중앙에 크게 작성
  - 아래 선에 붙이지 않기
  - 칸 밖으로 나가지 않기
  - 0/6, 0/O, 1/7, x/n 구분
  - ㄱ/ㄴ/ㄷ/ㄹ은 숫자처럼 쓰지 않기
  - < 와 <= 명확히 작성

## Generated Prototype

Suggested output folder:

`C:\server-ocr\answer_sheet_v3`

Expected generated files:

- `answer_sheet_v3.png`
- `answer_sheet_v3.pdf`
- `answer_sheet_v3.layout.json`
- `answer_sheet_v3_coordinate_spec_report.md`
- `answer_sheet_v3_visual_qa_report.md`
- `answer_sheet_v3_comparison_report.md`

## Compatibility Notes

The v3 generator reuses the existing layout builder and then applies v3-only visual styling. That keeps marker target coordinates, `answer_box_bbox`, `crop_bbox`, and crop metadata compatible with existing crop extraction logic.

The v3 prototype should be tested with the same `crop_answer_boxes.py` flow before any server or student-page integration.

