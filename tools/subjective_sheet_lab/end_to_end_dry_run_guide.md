# End-to-End Dry-Run Guide

이 문서는 서버 이식 전, `tools/subjective_sheet_lab` 안에서 주관식 답안지 OCR/Vision 흐름을 수동으로 검증하는 표준 루틴이다. 앱 본체, 학생 페이지, 서버 API, DB, `data/**`는 수정하지 않는다.

## 1. 사진 준비

학생 답안지 사진을 batch input 폴더에 넣는다.

```text
tools/subjective_sheet_lab/samples/batch_input/
```

권장:

- 한 학생/한 촬영본당 파일 1개
- 파일명은 case id로 쓰기 쉬운 이름 사용
- 예: `person_06_good.jpg`, `person_07_tilted.jpg`

## 2. Batch Prepare

`batch_prepare_stress_test.py`를 실행해 case별 crop, enhanced crop, contact sheet를 만든다.

예시:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\batch_prepare_stress_test.py --input-dir .\tools\subjective_sheet_lab\samples\batch_input --layout .\tools\subjective_sheet_lab\samples\output\subjective_sheet_guided.layout.json --out-root .\tools\subjective_sheet_lab\samples\stress_test_batch
```

확인할 출력:

- `crops/q001.png` ~ `crops/q020.png`
- `enhanced_crops/q001.png` ~ `enhanced_crops/q020.png`
- `contact/vision_contact_q001_q005_compare.png`
- `contact/vision_contact_q006_q010_compare.png`
- `contact/vision_contact_q011_q015_compare.png`
- `contact/vision_contact_q016_q020_compare.png`
- `case_manifest.json`
- `batch_manifest.json`
- `failed_cases.json`

## 3. 수동 Vision

`vision_manual_prompt_batch.md`의 표준 프롬프트를 사용한다.

절차:

1. 5문항 단위 contact sheet를 Vision 모델 화면에 업로드한다.
2. `vision_manual_prompt_batch.md`의 프롬프트를 붙여넣는다.
3. JSON만 출력하도록 한다.
4. 결과를 case별 `vision_result` 폴더에 저장한다.

예시 저장 파일:

```text
vision_result/ocr_result_manual_vision_q001_q005.json
vision_result/ocr_result_manual_vision_q006_q010.json
vision_result/ocr_result_manual_vision_q011_q015.json
vision_result/ocr_result_manual_vision_q016_q020.json
```

## 4. Merge / Evaluate

문항 단위 Vision 결과를 병합한 뒤 평가한다.

병합 예시:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\merge_manual_vision_results.py --part .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\vision_result\ocr_result_manual_vision_q001_q005.json .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\vision_result\ocr_result_manual_vision_q006_q010.json .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\vision_result\ocr_result_manual_vision_q011_q015.json .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\vision_result\ocr_result_manual_vision_q016_q020.json --out .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\vision_result\ocr_result_manual_vision_20.json
```

단일 case 평가 예시:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\evaluate_ocr_result.py --ocr-result .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\vision_result\ocr_result_manual_vision_20.json --answer-key .\tools\subjective_sheet_lab\answer_key_schema.example.json --out-json .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\eval\eval.json --out-csv .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\eval\eval.csv --out-md .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\eval\eval.md
```

batch 평가 예시:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\batch_evaluate_stress_test.py --batch-root .\tools\subjective_sheet_lab\samples\stress_test_batch --answer-key .\tools\subjective_sheet_lab\answer_key_schema.example.json
```

확인할 분기:

- `safe_auto_grade`
- `review_required`
- `retake_required`

## 5. 학생 확인 Mock

`student_review_ui_mock.html`을 브라우저에서 열고 학생 확인 흐름을 검증한다.

```text
tools/subjective_sheet_lab/student_review_ui_mock.html
```

검증할 행동:

- `safe_auto_grade` 문항은 자동 인식 완료 목록에만 표시
- `review_required` 문항은 후보 선택 가능
- `review_required` 문항은 직접 입력 가능
- `review_required` 문항은 문항별 재촬영 가능
- `retake_required` 문항은 후보 선택/직접 입력 불가
- `retake_required` 문항은 문항별 재촬영만 가능
- final payload export 가능

문항별 재촬영 정책은 `retake_policy.md`를 따른다.

## 6. 최종 채점 Dry-Run

학생 확인 mock에서 export한 final payload와 answer key JSON으로 최종 채점 리포트를 생성한다.

예시:

```powershell
.\.venv\Scripts\python.exe .\tools\subjective_sheet_lab\grade_final_payload.py --payload .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\final_payload.json --answer-key .\tools\subjective_sheet_lab\answer_key_schema.example.json --output .\tools\subjective_sheet_lab\samples\stress_test_batch\person_06_good\grade_report.json
```

생성 결과:

- `grade_report.json`
- schema: `subjective_grade_report`
- `external_api_calls = false`

## 7. 확인할 지표

OCR/evaluate 단계:

- `safe_auto_grade_count`
- `review_required_count`
- `retake_required_count`
- `blocked_unconfirmed_count`

학생 확인/final payload 단계:

- `gradable_count`
- `blocked_count`
- `student_selected_count`
- `student_manual_input_count`
- `retake_required_count`
- `blocked_unconfirmed_count`

최종 채점 단계:

- `gradable_questions`
- `blocked_questions`
- `correct_count`
- `incorrect_count`
- `score`

## 8. 통과 기준 예시

- missing 0
- `blocked_unconfirmed` 최소화
- `safe_auto_grade` 비율 기록
- `review_required` / `retake_required` 원인 기록
- final payload JSON 파싱 가능
- grade report JSON 파싱 가능
- blocked 문항은 채점에서 제외됨
- `student_selected`, `student_manual_input`, `retake_recognized` 문항이 answer key 기준으로 채점됨

## 9. 실패 시 조치

- crop 문제: crop 정책/촬영 가이드 확인
- `ㄱ/ㄴ/ㄷ/ㄹ` 혼동: `review_required`로 분리되는지 확인
- `±` 혼동: `review_required`로 분리되는지 확인
- retake 반복 실패: `blocked_unconfirmed`로 처리되는지 확인
- answer key 불일치: answer key JSON의 `canonical_answer`, `accepted_answers`, `normalize`, `order_insensitive` 재검토
- final payload 파싱 실패: `final_answer_payload_schema.example.json`과 필드 비교
- grade report 파싱 실패: `grade_final_payload.py` 출력 JSON 확인

## 10. 서버 이식 전 체크리스트

- answer key JSON 준비됨
- final payload schema 확정됨
- student confirmation policy 확정됨
- retake policy 확정됨
- `grade_final_payload.py` dry-run 통과
- `student_review_ui_mock.html`에서 final payload export 가능
- 앱 본체/API/DB/data 수정 없이 lab에서 검증 완료
