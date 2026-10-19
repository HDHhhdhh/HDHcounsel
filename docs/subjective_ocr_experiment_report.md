# 주관식 답안지 OCR/Vision 검증 요약

상세 보고서: `tools/subjective_sheet_lab/subjective_ocr_experiment_report.md`

## 최신 summary

| 항목 | 값 |
|---|---:|
| case_count | 5 |
| total_items | 100 |
| average_accuracy | 96.00% |
| aggregate_accuracy | 96.00% |
| total_needs_review | 4 |
| total_missing | 0 |

## 케이스별 결과

| Case | 결과 | Accuracy | Needs Review |
|---|---:|---:|---:|
| `person_02_good_fullbox` | 20/20 | 100.00% | 0 |
| `person_02_tilted_fullbox` | 20/20 | 100.00% | 0 |
| `person_03_good_fullbox` | 18/20 | 90.00% | 2 |
| `person_04_guided_good` | 20/20 | 100.00% | 0 |
| `person_05_guided_good` | 18/20 | 90.00% | 2 |

## Worst Questions

| 문항 | review/missing 횟수 | 해석 |
|---:|---:|---|
| Q006 | 2 | 답안 가시성 또는 필기 위치가 불안정한 케이스 |
| Q019 | 1 | `+`와 `±` 기호가 애매하게 읽힌 케이스 |
| Q004 | 1 | `ㄱ`, `ㄷ` 같은 한글 자음 선택지형 답안이 숫자/영문으로 오인식될 수 있는 케이스 |

## 현재 결론

- 키 없는 수동 Vision 기준으로 100문항 중 96문항을 정확 인식했고, 4문항은 needs_review였다.
- 가능성은 높다.
- 정면/밝음, 기울어진 사진, 여러 사람 글씨에서 1차 인식 가능성이 확인됐다.
- missing 0문항은 긍정적 결과다.
- `full_answer_box` 계열 crop 정책은 유지하되, 실제 crop은 답안 네모칸 전체와 작은 안전 여백을 포함하는 `full_answer_box_with_safe_margin`을 사용한다.
- 원본 crop + enhanced crop 병렬 contact sheet를 권장한다.
- 시험별 answer key JSON으로 `canonical_answer`, `accepted_answers`, `order_insensitive`, `review_if_contains`를 관리한다.
- 운영 판단에서는 `safe_auto_grade_count`와 `review_required_count`를 함께 본다.
- 답안칸 안쪽 중앙에는 연한 쓰기 안전영역 가이드를 추가한다. 이는 필기 위치 유도용이며 답안지 형식 변경은 아니다.
- 답안지 형식은 현재 v2/current format을 유지한다. A4 1장, 20문항, 2열 x 10행 구조를 유지하고 답안칸 높이 변경이나 2페이지 분리는 보류한다.
- 완전 자동 채점보다 “자동 인식 → safe 문항 자동 처리 → review_required 문항만 확인 → 최종 제출” 구조가 안전하다.

## 학생 작성 가이드

- 답은 네모칸 중앙에 크게 쓴다.
- 연한 쓰기 안전영역 안쪽을 기준으로 쓴다.
- 아래 선에 붙여 쓰지 않는다.
- 칸 밖으로 나가지 않는다.
- `+`, `-`, `±`를 명확히 구분해서 쓴다.
- `0/O`, `1/7`, `+/±`, `< / <=`는 특히 구분해서 쓴다.
- `ㄱ`, `ㄴ`, `ㄷ`, `ㄹ` 선택지는 또렷하게 쓴다. `ㄱ`은 `7`, `ㄴ`은 `4`/`L`, `ㄷ`은 `C`, `ㄹ`은 `2`로 오인식될 수 있다.

## needs_review 규칙

- `recognized`가 `?`인 경우
- `+`/`±`, `-`/`+`, `0`/`O`, `1`/`7`처럼 위험 기호가 포함된 경우
- `<`/`<=`, `>`/`>=`처럼 부등호 형태가 애매한 경우
- `ㄱ/ㄴ/ㄷ/ㄹ` 선택지가 `7`/`4`/`C`/`2`/`L`처럼 읽힌 경우
- crop에서 답안이 잘 안 보이는 경우
- Vision 경고가 있는 경우

## 다음 단계

- 학생 글씨 샘플을 추가해 평균 정확도가 유지되는지 확인한다.
- 필요하면 batch stress test 자동화로 여러 case 평가를 더 빠르게 반복한다.
- 답안칸 안쪽의 연한 쓰기 안전영역을 기준으로 크게 쓰는 가이드를 사용한다.
- 현재 답안지 형식은 유지한다.
- crop은 답안 네모칸 전체와 작은 안전 여백을 포함한다.
- 답안칸 높이 변경이나 2페이지 분리는 보류 또는 후순위 검토로 둔다.
- `+`, `-`, `±`, `0/O`, `1/7`, `<`/`<=`, `>`/`>=`, `ㄱ/ㄴ/ㄷ/ㄹ` 선택지 혼동 같은 위험 기호 검토 규칙을 적용한다.
- 자동 OCR/API 연결은 비용, 개인정보, 정확도 검토 후 결정한다.
- 학생 페이지 이식은 서버컴에서 별도 분석 후 진행한다.
