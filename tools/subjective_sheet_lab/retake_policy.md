# Question-Level Retake Policy

이 문서는 서버 이식 전 기준으로, 전체 답안지 재촬영이 아니라 문제가 있는 문항만 다시 촬영하는 정책을 고정한다. 앱 본체, 학생 페이지, 서버 API, DB, `data/**`와는 연결하지 않는 독립 정책 문서다.

## 1. 목적

- `retake_required` 문항 또는 학생이 재촬영을 선택한 `review_required` 문항만 다시 촬영한다.
- 전체 답안지 재촬영을 기본으로 하지 않는다.

## 2. 재촬영 대상

- `retake_required` 문항: 재촬영 필수
- `review_required` 문항: 학생이 원하면 재촬영 가능
- `safe_auto_grade` 문항: 원칙적으로 재촬영 대상 아님

## 3. 학생 UI 원칙

- “6번 답안칸만 다시 촬영해주세요”처럼 문항 단위로 안내한다.
- 재촬영 대상 문항 번호를 명확히 표시한다.
- `retake_required`는 후보 선택/직접 입력 불가.
- `review_required`는 후보 선택/직접 입력/재촬영 중 선택 가능.

## 4. 저장 구조

예:

```text
retakes/q006_attempt2.png
retakes/q006_attempt2_enhanced.png
```

필드:

- `retake_count`
- `retake_image_path`
- `retake_enhanced_crop_path`
- `retake_reason`
- `retaken_at`

## 5. 처리 흐름

```text
문항별 재촬영
→ 해당 문항만 crop/enhance
→ Vision 재판독
→ evaluate 재실행
→ 통과 시 final_answer_source = "retake_recognized"
→ 실패 시 재촬영 반복 또는 blocked_unconfirmed
```

## 6. 반복 실패 정책

- `retake_count`가 기준값을 넘으면 `blocked_unconfirmed`.
- 권장 `max_retake_count = 2`.
- `blocked_unconfirmed`는 채점 불가 상태.
- 운영자는 이후 별도 정책으로 처리.

## 7. payload 반영

`final_answer_payload_schema`와 연결:

- `final_answer_source = "retake_recognized"`
- `student_action = "retake"`
- `confirmation_status = "retaken"` 또는 `"blocked_unconfirmed"`
- `grading_status = "gradable"` 또는 `"blocked"`
- `evidence.retake_crop`에 경로 저장
- `retake_count` 증가

## 8. 로그/증거 보존

- 원본 crop 유지
- enhanced crop 유지
- 재촬영 crop 유지
- 재촬영 후 recognized 유지
- 이전 recognized도 덮어쓰지 말고 history에 남기는 것이 권장

## 9. 금지 사항

- 재촬영으로 기존 원본 crop을 덮어쓰지 말 것
- 학생이 `retake_required` 문항을 직접 입력으로 해결하게 하지 말 것
- 전체 답안지를 무조건 다시 찍게 하지 말 것
