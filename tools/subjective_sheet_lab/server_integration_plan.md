# Subjective Sheet Server Integration Plan

이 문서는 `tools/subjective_sheet_lab`에서 검증한 주관식 답안지 처리 흐름을 서버/학생 페이지에 이식하기 전 계획을 정리한다. 앱 본체, 학생 페이지, 서버 API, DB, `data/**`를 수정하지 않는 설계 문서다.

## 1. 이식 목표

- 학생이 답안지 사진 제출
- 서버가 crop/enhance/evaluate 처리
- `review_required` 문항만 학생 확인
- `retake_required` 문항은 문항별 재촬영
- final payload 생성
- answer key 기준 채점

## 2. 서버로 이식할 핵심 로직

- `crop_answer_boxes.py`
- `enhance_vision_crops.py`
- `evaluate_ocr_result.py`
- `normalize_math_answer.py`
- `grade_final_payload.py`
- answer key JSON 평가 규칙
- `final_answer_payload_schema`

## 3. Lab 전용으로 유지할 것

- `vision_manual_prompt_batch.md`
- `review_ui_mock.html`
- `student_review_ui_mock.html`
- `batch_prepare_stress_test.py`
- `batch_evaluate_stress_test.py`
- stress test report 문서들

## 4. 학생 페이지에 필요한 화면

- 답안지 촬영/업로드
- 인식 처리 중 화면
- `review_required` 문항 확인 화면
- 후보 선택/직접 입력
- 문항별 재촬영
- 최종 제출 전 확인
- 제출 완료 화면

## 5. 필요한 API 후보

- `POST /api/subjective/upload-sheet`
- `GET /api/subjective/attempt/{attempt_id}`
- `POST /api/subjective/confirm-item`
- `POST /api/subjective/retake-item`
- `POST /api/subjective/finalize`
- `GET /api/subjective/result/{attempt_id}`

## 6. 저장해야 할 데이터

- `attempt_id`
- `test_id`
- `student_id`
- original sheet image path
- corrected/warped image path
- crop paths
- enhanced crop paths
- recognized
- candidates
- warnings
- review_reasons
- status
- final_answer
- final_answer_source
- student_action
- retake_count
- retake_history
- grade report

## 7. 상태 흐름

```text
uploaded
→ processed
→ pending_student_input
→ retake_required
→ student_finalized
→ blocked_unconfirmed
→ finalized
→ graded
```

상태는 문항 단위와 attempt 단위 모두에서 추적할 수 있어야 한다.

## 8. 안전 원칙

- `safe_auto_grade` 문항은 학생 입력 없이 자동 확정
- `review_required` 문항만 학생 후보 선택/직접 입력 허용
- `retake_required`는 직접 입력 불가
- 문항별 재촬영 우선
- 원본 crop 덮어쓰기 금지
- final payload 기준으로만 채점

## 9. 이식 순서

1. 서버 내부 처리만 붙이기
2. 학생 확인 UI 붙이기
3. 문항별 재촬영 붙이기
4. final payload 저장
5. grade report 생성
6. 기존 학생 테스트 제출 흐름과 연결

## 10. 이식 전 필수 검증

- `end_to_end_dry_run_guide.md` 1회 이상 통과
- 실제 학생 샘플 20~30명 테스트
- missing 0
- `blocked_unconfirmed` 비율 기록
- `retake_required` 비율 기록
- answer key JSON 검증
- final payload JSON 파싱
- grade report JSON 파싱

## 11. 절대 금지

- 기존 `data/**` 직접 변경
- 기존 학생 제출 API 무리하게 수정
- OCR 실패값을 자동 오답 처리
- `retake_required` 문항을 학생 직접 입력으로 해결
- 원본 crop/evidence 덮어쓰기
