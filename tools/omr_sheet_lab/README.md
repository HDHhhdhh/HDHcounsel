# OMR Sheet Lab

단원평가 OMR 답안지 판독을 학생 페이지에 붙이기 전, 독립적으로 방식만 검증하는 프로토타입입니다.

이 도구는 앱 본체, 학생 데이터, DB, `/api/submit-test`를 건드리지 않습니다. 현재 1단계는 Pillow와 numpy만 사용합니다.

## 목표

- 20문항 5지선다 OMR PNG/PDF 생성
- 판독용 `.layout.json` 생성
- 실제 촬영본 없이 synthetic 마킹 이미지 생성
- 이미지에서 `answersText` 추출
- debug overlay 이미지로 판독 위치 확인

## 최소 실행 예시

PowerShell에서 프로젝트 루트 기준으로 실행합니다.

```powershell
.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\generate_omr_sheet.py --config .\tools\omr_sheet_lab\omr_sheet_config.example.json --out .\tools\omr_sheet_lab\samples\output\unit_omr

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\make_synthetic_marked_sheet.py --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --sheet .\tools\omr_sheet_lab\samples\output\unit_omr.png --answers 13245132451324513245 --out .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\read_omr_sheet.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_result.json

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\debug_omr_overlay.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --result .\tools\omr_sheet_lab\samples\output\unit_omr_result.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_debug.png
```

## 촬영본에 가까운 synthetic 샘플 검증

```powershell
.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\make_synthetic_photo_like_sample.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_like.png --rotate 3 --brightness 0.92 --noise 3

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\read_omr_sheet.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_photo_like.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_result.json --corrected-out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_corrected.png

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\debug_omr_overlay.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_photo_corrected.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --result .\tools\omr_sheet_lab\samples\output\unit_omr_photo_result.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_debug.png
```

## 판독 파이프라인

1. 네 귀퉁이 search window에서 검은 사각 마커를 찾습니다.
2. 마커 4점이 모두 검출되면 homography를 계산해서 layout 크기로 원근 보정합니다.
3. 보정 이미지에서 layout JSON의 버블 ROI를 읽습니다.
4. 각 ROI의 dark pixel ratio를 계산합니다.
5. 문항별 선택 결과를 `answersText`로 만듭니다.

마커 검출 또는 원근 보정이 실패하면 기존처럼 scale-only 판독으로 fallback합니다. 이때 result JSON의 `preprocess.fallback`이 `true`가 됩니다.

## 결과 JSON 핵심 필드

```json
{
  "ok": true,
  "test_id": "unit_test_sample",
  "answersText": "13245132451324513245",
  "answersTextSpaced": "1 3 2 4 5 ...",
  "answers": ["1", "3", "2", "4", "5"],
  "items": [],
  "warnings": []
}
```

`answersText`가 나중에 학생 페이지의 `tsAnswersText.value`에 들어갈 값입니다.

## 현재 한계

- 원근 보정은 검은 사각 마커가 네 모서리 search window 안에 보일 때 가장 안정적입니다.
- 그림자, 구겨짐, 흐림, 연필 농도에 따라 오판 가능성이 있습니다.
- 실제 학생 페이지 이식은 2단계에서 별도로 진행합니다.

## 실제 촬영 가이드

- 답안지 네 귀퉁이 검은 마커가 모두 나오게 촬영합니다.
- 종이를 화면에 꽉 채우되 마커가 잘리지 않게 둡니다.
- 그림자가 마커나 버블 위를 지나가지 않게 합니다.
- 흐린 사진은 재촬영합니다.
- 판독 후 debug overlay를 보고 `?`, `multi`, `uncertain` 문항을 확인합니다.

## 1단계 성공 기준

- `unit_omr.png`, `unit_omr.pdf`, `unit_omr.layout.json` 생성
- synthetic marked sheet 생성
- synthetic photo-like sample 생성
- `read_omr_sheet.py`가 synthetic 답안을 정확히 복원
- debug overlay 생성
- 앱 본체와 학생 데이터에는 영향 없음
