# Minimal Integration Checklist

이 문서는 `tools/subjective_sheet_lab`의 Lab 구현을 실제 서비스에 이식하기 전에 확인해야 할 최소 변경 지점을 정리한다. 코드 이식 작업 지시서가 아니라, 이식 전 분석 체크리스트다.

## 1. 현재 완료된 Lab 구성요소

- `crop_answer_boxes.py`: 주관식 답안지 crop 생성
- `enhance_vision_crops.py`: Vision 판독용 crop 보정
- `evaluate_ocr_result.py`: OCR/Vision 결과 평가 및 `review_required` 판정
- `normalize_math_answer.py`: 답안 비교용 경량 정규화
- `grade_final_payload.py`: 최종 제출 payload dry-run 채점
- `final_answer_payload_schema.example.json`: 최종 제출 payload 스키마 예시
- `student_confirmation_policy.md`: 학생 확인/직접 입력/재촬영 정책
- `retake_policy.md`: 문항별 재촬영 정책
- `end_to_end_dry_run_guide.md`: 서버 이식 전 전체 수동 검증 루틴
- `server_integration_plan.md`: 서버/학생 페이지 이식 계획

## 2. 실제 서비스에 필요한 최소 기능

- 답안지 업로드
- crop
- evaluate
- `review_required` 판정
- 학생 확인
- 문항별 재촬영
- final payload 생성
- 채점

## 3. 기존 시스템에서 확인해야 할 항목

- 학생 제출 데이터 저장 위치
- 테스트 제출 API
- 파일 저장 구조
- `attempt_id` 생성 방식
- `student_id` 연결 방식
- 결과 저장 방식

## 4. 실제 이식 시 추가해야 할 객체

- subjective attempt
- subjective item result
- retake history
- final payload
- grade report

## 5. 이식 순서

1. 데이터 구조 확인
2. 업로드 경로 확인
3. crop 연결
4. evaluate 연결
5. 학생 확인 UI 연결
6. 재촬영 연결
7. 최종 채점 연결

## 6. 위험 요소

- 기존 제출 흐름 충돌
- 파일 저장소 충돌
- `student_id` 매핑 문제
- answer key 연결 문제
- 재촬영 파일 관리

## 7. 권장 이식 전략

- 신규 endpoint 사용
- 신규 데이터 구조 사용
- 기존 객관식 제출 로직 최대한 유지
- 기능 플래그 방식 적용 권장
- Lab 산출물을 바로 기존 제출 API에 섞지 말고, subjective 전용 흐름으로 먼저 검증

## 8. 최종 결론

현재 Lab 단계에서는 주관식 답안지 처리의 핵심 부품과 정책 문서가 준비되어 있다. 실제 코드 이식 전에는 기존 시스템의 학생 제출 저장 구조, 테스트 제출 API, 파일 저장 경로, `attempt_id`/`student_id` 매핑, 결과 저장 방식을 먼저 확인해야 한다.

최소 변경 전략은 기존 객관식 제출 흐름을 건드리지 않고, subjective 전용 endpoint와 데이터 구조를 만든 뒤 기능 플래그로 제한 배포하는 것이다.
