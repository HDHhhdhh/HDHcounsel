# Student Confirmation Policy

이 문서는 관리자 검토 없는 운영을 전제로, 주관식 답안 OCR/Vision 결과를 학생 확인 또는 재촬영으로 처리하는 정책을 고정한다. 앱 본체, 학생 페이지, 서버 API, DB, `data/**`와는 연결하지 않는 독립 정책 문서다.

## 1. 운영 목표

- 관리자 검토 없이 주관식 답안을 자동 처리한다.
- OCR/Vision은 최종 채점기가 아니라 1차 판독기다.
- 위험한 답안은 학생 확인 또는 재촬영으로 처리한다.

## 2. 기본 플로우

```text
사진 제출
→ crop/enhance
→ Vision 판독
→ evaluate
→ safe_auto_grade / review_required / retake_required 분기
→ 학생 확인
→ 최종 제출
```

## 3. 상태 정의

### safe_auto_grade

- 매칭 성공
- 위험 warning 없음
- crop diagnostics 문제 없음
- OCR/Vision 결과를 `final_answer`로 사용
- 학생 개입 없음
- `final_answer_source = "safe_auto_grade"`

### review_required

- 답은 읽혔거나 맞아 보이지만 위험 신호 있음
- 학생에게 original/enhanced crop, recognized, candidates를 보여줌
- 학생은 후보 선택 또는 직접 입력 가능
- 학생이 선택/입력한 값을 `final_answer`로 사용
- `final_answer_source`는 `student_selected` 또는 `student_manual_input`
- 제출 후 수정 불가 문구를 표시

### retake_required

- 비어 있음
- 답안 잘림
- 글씨가 너무 흐림
- crop 품질이 낮음
- 학생 직접 입력 불가
- 후보 선택 불가
- 재촬영 필수
- `final_answer = null`

## 4. 학생 허용 행동

전체 원칙:

- 모든 문항에 자유 입력을 허용하지 않는다.
- 학생 입력 허용은 `review_required` 문항에만 제한한다.
- `safe_auto_grade`는 학생 입력 없이 자동 확정한다.
- `retake_required`는 입력으로 해결하지 않고 반드시 재촬영한다.
- 최종 제출 후 수정 불가.

상태별 허용:

- `safe_auto_grade`: 학생 입력 없음
- `review_required`: 후보 선택 또는 직접 입력 가능
- `retake_required`: 재촬영만 가능

## 5. 학생 확인 원칙

### safe_auto_grade 문항

- OCR/Vision 결과를 그대로 `final_answer`로 사용
- 학생 개입 없이 자동 확정
- `final_answer_source = "safe_auto_grade"`

### review_required 문항

- 문항별 original/enhanced crop, recognized, candidates를 표시
- 학생이 후보를 선택하면 `final_answer_source = "student_selected"`
- 학생이 직접 입력하면 `final_answer_source = "student_manual_input"`
- 학생이 선택/입력한 값을 `final_answer`로 사용
- 제출 전 “최종 제출 후 수정할 수 없습니다.” 문구를 표시

### retake_required 문항

- 후보 선택 불가
- 직접 입력 불가
- 재촬영만 가능
- `final_answer = null`

## 6. 최종 채점 허용 조건

채점 가능:

- `safe_auto_grade`
- `student_selected`
- `student_manual_input`

채점 불가:

- `review_required`인데 학생 선택/입력 없음
- `retake_required`
- recognized에 `?` 포함
- `blank_or_missing`
- crop cutoff 가능성 높음

## 7. 로그/증거 보존

각 문항별로 보존:

- original crop path
- enhanced crop path
- recognized
- warnings
- review_reasons
- student_action
- confirmed_at
- retake_count
- final_answer
- final_answer_source

## 8. 반복 오류 처리

같은 문항이 반복해서 `review_required`가 되면:

- 해당 문항은 retake 우선
- 다음 시험지 생성 시 guided 작성 규칙 강화 대상으로 표시

같은 학생이 여러 문항에서 반복 오류가 나면:

- 전체 답안지 재촬영 권장

같은 답안 유형에서 반복 오류가 나면:

- 해당 유형은 기본 `review_required` 또는 `retake_required`로 격상 가능
- 예: `ㄱ/ㄴ/ㄷ/ㄹ`, `±`, 루트, 분수, 지수

## 9. 권장 UI 문구 예시

### safe_auto_grade

“답안 인식이 완료되었습니다.”

### review_required

“이 문항은 글씨 또는 기호가 불확실합니다. 원본과 보정 이미지를 확인한 뒤 후보를 선택하거나 직접 입력해주세요. 최종 제출 후에는 수정할 수 없습니다.”

### retake_required

“이 문항은 답안이 잘 보이지 않아 채점할 수 없습니다. 다시 촬영해주세요.”

## 10. 서버 이식 시 주의

- 학생 페이지에서 모든 문항에 직접 답안 입력 필드를 만들지 말 것.
- `review_required` 문항에 한해서만 후보 선택/직접 입력 UI를 제공.
- `safe_auto_grade` 문항은 시스템 recognized를 그대로 최종 답안으로 사용.
- `retake_required` 문항은 후보 선택/직접 입력 없이 재촬영만 제공.
- 최종 제출 payload에는 `final_answer`, `final_answer_source`, `student_action`, timestamp를 함께 저장.
- 최종 제출 후 수정 불가 정책을 UI와 payload 상태에 반영.
