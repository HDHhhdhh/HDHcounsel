# OMR Sheet Lab 설계 메모

이 문서는 단원평가용 OMR 답안지 판독 기능을 학생 페이지에 이식하기 전, 독립 프로토타입의 사용법과 한계를 정리합니다.

## 범위

1단계는 앱 본체와 분리된 실험실입니다.

- 수정 대상: `tools/omr_sheet_lab/**`, `docs/omr_sheet_lab.md`
- 비대상: `app.py`, `routes/**`, `static/**`, `templates/**`, `data/**`, 학생 데이터, DB, 외부 API

## 방식

현재 MVP는 네 귀퉁이 마커와 고정 좌표 기반 판독을 전제로 합니다.

1. `generate_omr_sheet.py`가 OMR 답안지와 layout JSON을 생성합니다.
2. `make_synthetic_marked_sheet.py`가 테스트용 마킹 이미지를 만듭니다.
3. `make_synthetic_photo_like_sample.py`가 촬영본에 가까운 왜곡 샘플을 만듭니다.
4. `read_omr_sheet.py`가 마커를 검출하고 원근 보정한 뒤 버블 ROI를 읽습니다.
5. `debug_omr_overlay.py`가 사람이 확인할 수 있는 overlay 이미지를 만듭니다.

## PowerShell 실행 예시

```powershell
.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\generate_omr_sheet.py --config .\tools\omr_sheet_lab\omr_sheet_config.example.json --out .\tools\omr_sheet_lab\samples\output\unit_omr

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\make_synthetic_marked_sheet.py --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --sheet .\tools\omr_sheet_lab\samples\output\unit_omr.png --answers 13245132451324513245 --out .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\read_omr_sheet.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_result.json

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\debug_omr_overlay.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --result .\tools\omr_sheet_lab\samples\output\unit_omr_result.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_debug.png
```

## Photo-like 샘플 검증

```powershell
.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\make_synthetic_photo_like_sample.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_marked.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_like.png --rotate 3 --brightness 0.92 --noise 3

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\read_omr_sheet.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_photo_like.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_result.json --corrected-out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_corrected.png

.\.venv\Scripts\python.exe .\tools\omr_sheet_lab\debug_omr_overlay.py --image .\tools\omr_sheet_lab\samples\output\unit_omr_photo_corrected.png --layout .\tools\omr_sheet_lab\samples\output\unit_omr.layout.json --result .\tools\omr_sheet_lab\samples\output\unit_omr_photo_result.json --out .\tools\omr_sheet_lab\samples\output\unit_omr_photo_debug.png
```

## 판독 파이프라인

1. 이미지를 grayscale로 변환합니다.
2. 각 모서리 search window에서 dark pixel component를 찾습니다.
3. 가장 큰 검은 사각 component의 bounding box 중심을 marker point로 사용합니다.
4. 네 marker point와 layout marker point로 homography를 계산합니다.
5. inverse mapping으로 이미지를 layout page size에 맞게 warp합니다.
6. 보정 이미지에서 각 버블 ROI의 dark pixel ratio를 계산합니다.
7. 문항별로 선택지를 판정하고 `answersText`를 만듭니다.

마커 4개를 안정적으로 찾지 못하거나 보정 중 오류가 나면 scale-only fallback으로 판독합니다. 이 경우 결과 JSON에 `preprocess.fallback: true`와 실패 이유가 남습니다.

## 결과 포맷

`read_omr_sheet.py` 출력 JSON의 핵심은 다음입니다.

```json
{
  "ok": true,
  "test_id": "unit_test_sample",
  "answersText": "13245132451324513245",
  "answersTextSpaced": "1 3 2 4 5 1 3 2 4 5 1 3 2 4 5 1 3 2 4 5",
  "answers": ["1", "3", "2", "4", "5"],
  "warnings": [],
  "preprocess": {
    "perspective_enabled": true,
    "marker_detected": true,
    "fallback": false,
    "marker_points": {}
  }
}
```

2단계 이식 때는 `answersText`를 기존 학생 테스트 페이지의 `tsAnswersText.value`에 넣고, 사용자가 확인 후 기존 제출 버튼으로 저장하게 하는 방식이 가장 안전합니다.

## 판독 상태

- `ok`: 하나의 선택지가 충분히 진하게 표시됨
- `blank`: 표시가 없음
- `multi`: 복수 선택지가 진하게 표시됨
- `uncertain`: 가장 진한 선택지가 기준선 근처이거나 2등과 차이가 작음
- 실패/애매한 문항은 `answersText`에서 `?`로 표시됩니다.

## 현재 한계

- 원근 보정은 구현되어 있지만, 마커가 잘리거나 그림자에 묻히면 fallback됩니다.
- 촬영 이미지가 크게 기울거나 구겨지면 판독 실패 가능성이 있습니다.
- 실제 운영 전에는 여러 촬영 환경 샘플로 threshold를 보정해야 합니다.
- OpenCV 없이 Pillow+numpy만 쓰므로 복잡한 곡면/구김 보정은 아직 다루지 않습니다.

## 실제 촬영 가이드

- 네 귀퉁이 검은 마커가 모두 보이게 촬영합니다.
- 답안지 바깥 여백이 조금 남아도 괜찮지만 마커가 잘리면 안 됩니다.
- 그림자와 손가락이 마커/버블을 덮지 않게 합니다.
- 흐린 사진은 재촬영합니다.
- debug overlay에서 초록색 선택, 주황색 warning 문항, 보라색 marker 기준점을 확인합니다.

## 1단계 성공 기준

- OMR PNG/PDF 생성
- layout JSON 생성
- synthetic marked sheet 생성
- synthetic photo-like sample 생성
- synthetic 답안 정확 복원
- debug overlay 생성
- 학생 데이터/DB/API 쓰기 없음

## 2단계 이식 체크리스트

- 실제 학생 페이지 route
- 실제 HTML/template 위치
- 운영 `student.js` 위치
- 기존 `/api/submit-test` request/response
- OMR 업로드 route 위치
- 업로드 결과를 `tsAnswersText.value`에 넣을 UI 위치
- 저장 전 미리보기/수정 UX
