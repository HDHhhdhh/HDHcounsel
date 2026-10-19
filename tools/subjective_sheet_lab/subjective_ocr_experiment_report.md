# 주관식 답안지 OCR/Vision 가능성 검증 보고서

작성일: 2026-05-29

이 문서는 개발/운영 판단용 보고서다. 학생용 화면이 아니며, 답안을 제출하거나 자동 채점하지 않는다. 현재 결과는 키 없는 수동 Vision 검증 단계의 성과이며, 서버 자동화나 학생 페이지 이식이 완료됐다는 의미가 아니다.

## 1. 목적

단원평가 주관식 답안지를 촬영한 뒤 문항별 답안칸을 안정적으로 잘라내고, Vision 모델이 답안을 읽을 수 있는지 확인한다. 최종 목표는 나중에 학생 페이지에서 자동 인식 결과를 확인하고 필요한 문항만 수정한 뒤 제출하는 흐름이지만, 이번 검증은 독립 프로토타입과 수동 Vision 평가에 한정한다.

## 2. 현재까지 만든 파이프라인

1. 답안지 생성
   - `generate_subjective_sheet.py`로 A4 주관식 답안지 PNG/PDF/layout JSON을 생성한다.
   - 네 귀퉁이에 정렬용 검은 마커를 둔다.

2. 촬영본 정렬
   - `crop_answer_boxes.py`가 네 귀퉁이 마커를 찾아 homography 기반 정렬을 시도한다.
   - 마커 검출이 불안정하면 잘못된 crop을 성공으로 처리하지 않고 재촬영 필요 상태로 보낸다.

3. 문항별 crop
   - 현재 기본 정책은 `full_answer_box_with_safe_margin`이다.
   - 문제번호 칸은 제외하고, 답안 작성 네모칸 전체와 작은 안전 여백을 crop한다.
   - 테두리 선이 들어오는 것은 허용한다. 글씨가 잘리는 것보다 테두리가 포함되는 것이 낫다.
   - 안전 여백은 글씨 잘림을 줄이기 위한 것이며, 이전/다음 문항이나 마커 영역이 섞이지 않도록 제한된 범위에서만 확장한다.

4. contact sheet 생성
   - `make_vision_contact_sheet.py`로 Q001-Q010, Q011-Q020 contact sheet를 만든다.
   - contact sheet는 ChatGPT/Gemini 웹 UI에 사람이 업로드해 읽기 가능성을 보는 검증용 이미지다.
   - 정확도 확인용으로는 `enhance_vision_crops.py`로 crop을 고대비/확대 처리한 뒤 Q001-Q005, Q006-Q010, Q011-Q015, Q016-Q020처럼 5문항 단위 contact sheet를 쓰는 것을 권장한다.
   - enhanced crop은 원본 대체본이 아니라 보조본이다. 수동 Vision 검증에서는 원본 crop과 enhanced crop을 같은 문항에 나란히 보여주는 `original_and_enhanced` contact sheet를 우선 사용한다.

5. manual Vision 인식
   - ChatGPT/Gemini 웹 UI에 contact sheet를 올리고, 정해진 JSON 형식으로 인식 결과를 받는다.
   - 이 단계는 외부 API 호출 자동화가 아니라 사람이 웹 UI를 사용하는 수동 검증이다.

6. 평가 리포트 생성
   - `evaluate_ocr_result.py`가 Vision 결과 JSON과 기대 답안을 비교한다.
   - exact match, normalized match, needs review, missing을 집계한다.
   - 운영 판단에서는 `safe_auto_grade_count`와 `review_required_count`를 함께 본다. 문자열이 맞아도 경고가 있으면 review_required로 남긴다.

7. stress test summary
   - `summarize_stress_test_results.py`가 각 case의 `eval/eval.json`을 모아 전체 정확도와 위험 문항을 요약한다.

## 3. 최신 stress test summary

| 항목 | 값 |
|---|---:|
| case_count | 5 |
| total_items | 100 |
| average_accuracy | 96.00% |
| aggregate_accuracy | 96.00% |
| total_needs_review | 4 |
| total_missing | 0 |

케이스별 결과:

| Case | Total | Exact | Needs Review | Missing | Accuracy |
|---|---:|---:|---:|---:|---:|
| `person_02_good_fullbox` | 20 | 20 | 0 | 0 | 100.00% |
| `person_02_tilted_fullbox` | 20 | 20 | 0 | 0 | 100.00% |
| `person_03_good_fullbox` | 20 | 18 | 2 | 0 | 90.00% |
| `person_04_guided_good` | 20 | 20 | 0 | 0 | 100.00% |
| `person_05_guided_good` | 20 | 18 | 2 | 0 | 90.00% |

Worst Questions:

| 문항 | review/missing 횟수 | 해석 |
|---:|---:|---|
| Q006 | 2 | 답안 가시성 또는 필기 위치가 불안정한 케이스 |
| Q019 | 1 | `+`와 `±` 기호가 애매하게 읽힌 케이스 |
| Q004 | 1 | `ㄱ`, `ㄷ` 같은 한글 자음 선택지형 답안이 숫자/영문으로 오인식될 수 있는 케이스 |

주요 needs_review 세부:

| 문항 | expected | recognized | 사유 |
|---:|---|---|---|
| Q006 | `7` | `?` | `answer_not_visible_or_crop_missed` |
| Q019 | `x+2=4` | `x±2=4` | `plus_minus_uncertain` |
| Q004 | `ㄱ,ㄷ` | `7,C` | `jamo_choice_confusion` |

요약하면, 키 없는 수동 Vision 기준으로 100문항 중 96문항은 정확 인식했고 4문항은 needs_review로 분류됐다. missing은 0문항이었다.

## 4. 핵심 결론

- 키 없는 수동 Vision 검증 기준으로 주관식 답안 인식 가능성은 높다.
- 정면/밝음, 기울어진 사진, 여러 사람 글씨에서 1차 인식 가능성이 확인됐다.
- missing 0문항은 긍정적 결과다. 다만 needs_review 4문항은 운영상 반드시 별도 확인 대상으로 분리해야 한다.
- 현재까지는 답안 네모칸 전체를 자르는 `full_answer_box` 계열 crop 정책을 유지하는 것이 가장 안정적이다.
- 실제 crop 설정은 `full_answer_box_with_safe_margin`으로 두어 답안 네모칸 전체에 작은 안전 여백을 추가한다.
- 원본 crop과 enhanced crop을 나란히 보여주는 `original_and_enhanced` contact sheet를 정확도 검증용 기본으로 권장한다.
- 답안지에는 답안칸 안쪽 중앙에 연한 쓰기 안전영역 가이드를 추가한다. 이는 필기 위치를 유도하기 위한 표시이며, 답안지 형식 자체는 바꾸지 않는다.
- 답안지 형식은 현재 v2/current format을 유지한다. A4 1장, 20문항, 2열 x 10행 구조를 유지하고 2페이지 분리나 답안칸 높이 변경은 현재 보류한다.
- 수동 Vision 기준 1차 stress test는 통과 수준이지만, 100% 완전 자동 채점으로 바로 연결하기에는 아직 이르다.
- `person_03_good_fullbox`에서 확인된 것처럼 답안이 crop에서 잘 보이지 않거나, `+`와 `±`처럼 애매한 기호는 검토 대상으로 빠질 수 있다.
- `person_05_guided_good`에서 확인된 것처럼 `ㄱ/ㄴ/ㄷ/ㄹ` 선택지형 답안은 `7/C/4/2/L` 같은 숫자/영문으로 오인식될 수 있다.
- `person_04_guided_good`처럼 expected/recognized 문자열이 같아도 `?`나 manual uncertainty warning이 있으면 `review_required`로 집계해야 한다.
- 실제 주관식 채점 기준은 단순 expected txt보다 answer key JSON으로 관리한다. `answer_key_schema.example.json`은 샘플용이며, 다른 시험이나 `person_04_guided_good`처럼 답안 구성이 다른 case에는 별도 answer key를 만들어야 한다.
- 다음 manual Vision 검증에서는 5문항 단위 `original_and_enhanced` contact sheet를 우선 사용한다.
- 따라서 운영 후보 구조는 “자동 인식 + answer key 평가 + safe 문항 자동 처리 + review_required 문항 확인 + 필요 시 수정 + 최종 제출”이 안전하다.

## 5. 현재 한계

- 자동 OCR/API가 아직 연결되지 않았다.
- 서버 API, 학생 페이지, DB, 자동 채점 흐름과 아직 연결하지 않았다.
- 현재 방식은 contact sheet를 사람이 ChatGPT/Gemini 웹 UI에 업로드하는 수동 방식이다.
- 학생 글씨 다양성 검증이 아직 더 필요하다.
- 촬영 조건이 더 나빠질 때의 안정성은 추가 확인이 필요하다.
- 필기가 답안 네모칸 밖으로 벗어나면 crop 정책만으로 복구하기 어렵다.
- `+`, `-`, `±`, `0/O`, `1/7`, 부등호, 분수, 루트, 벡터, 적분, 시그마 같은 기호는 needs_review 정책이 필요하다.

## 6. 다음 단계

1. 학생 또는 다른 사람 글씨 샘플을 더 추가해 평균 정확도와 review_required 비율이 유지되는지 확인한다.
2. 정면/밝음, 살짝 기울어짐, 약한 그림자 조건을 나눠 촬영한다.
3. 필요하면 batch stress test 자동화로 여러 case 평가를 더 빠르게 반복한다.
4. 답안칸 안쪽의 연한 쓰기 안전영역을 기준으로 크게 쓰도록 작성 가이드를 강화한다.
5. crop은 답안 네모칸 전체와 작은 안전 여백을 포함하는 `full_answer_box_with_safe_margin`을 유지한다.
6. 현재 A4 1장, 20문항, 2열 x 10행 형식은 유지한다. 답안칸 높이 변경이나 2페이지 분리는 보류 또는 후순위 검토로 둔다.
7. `+`, `-`, `±`, `0/O`, `1/7`, `<`/`<=`, `>`/`>=`, `ㄱ/ㄴ/ㄷ/ㄹ` 선택지 혼동 같은 위험 기호 검토 규칙을 적용한다.
8. 같은 manual Vision contact sheet 방식으로 결과 JSON을 만들고 `evaluate_ocr_result.py`로 평가한다.
9. 시험별 answer key JSON을 만들어 `canonical_answer`, `accepted_answers`, `order_insensitive`, `review_if_contains`를 명시한다. 샘플 answer key를 다른 답안 세트에 그대로 쓰면 OCR 성공 여부와 무관하게 0점처럼 평가될 수 있다.
10. `summarize_stress_test_results.py`로 전체 평균과 위험 문항을 본다.
11. 자동 OCR/API 연결은 비용, 개인정보, 정확도 검토 후 결정한다.
12. 학생 페이지 이식은 서버컴에서 기존 제출/채점 흐름을 별도 분석한 뒤 진행한다.

## 7. 학생 작성 가이드

- 답은 네모칸 중앙에 크게 쓴다.
- 연한 쓰기 안전영역 안쪽을 기준으로 쓴다.
- 아래 선에 붙여 쓰지 않는다.
- 칸 밖으로 나가지 않는다.
- `+`, `-`, `±`를 명확히 구분해서 쓴다.
- `0/O`, `1/7`, `+/±`, `< / <=`는 특히 구분해서 쓴다.
- `ㄱ`, `ㄴ`, `ㄷ`, `ㄹ` 선택지는 또렷하게 쓴다. Vision/OCR에서 `ㄱ`은 `7`, `ㄴ`은 `4`/`L`, `ㄷ`은 `C`, `ㄹ`은 `2`로 오인식될 수 있다.

## 8. needs_review 규칙

다음 경우는 자동 제출 또는 자동 채점으로 바로 넘기지 않고 검토 대상으로 둔다.

- `recognized`가 `?`인 경우
- `+`/`±`, `-`/`+`, `0`/`O`, `1`/`7`처럼 위험 기호가 포함된 경우
- `<`/`<=`, `>`/`>=`처럼 부등호 형태가 애매한 경우
- expected에 `ㄱ`, `ㄴ`, `ㄷ`, `ㄹ` 선택지가 있는데 recognized가 `7`, `4`, `C`, `2`, `L`처럼 읽힌 경우
- recognized에 `ㄱ/ㄴ/ㄷ/ㄹ`과 숫자/영문 혼동 후보가 섞여 있는 경우
- crop에서 답안이 잘 보이지 않는 경우
- Vision 결과에 경고가 있는 경우

평가 리포트에서는 두 층을 구분한다.

- `needs_review`: 문자열 매칭 자체가 실패했거나 누락된 문항
- `review_required`: 문자열은 맞더라도 운영상 확인이 필요한 문항

예를 들어 expected와 recognized가 둘 다 `216?9`라서 `exact_match`로 유지되더라도, `?`, `manual_read_uncertain`, `inside_sqrt_uncertain`, `possible_zero_o_confusion`, `plus_minus_uncertain`, `jamo_choice_confusion`, `answer_not_visible_or_crop_missed`, `crop_partially_cut`, `low_visible_ink` 같은 신호가 있으면 `review_required=true`로 집계한다. `person_05`처럼 `Q004 = ㄱ,ㄷ`, `Q006 = ㄴ,ㄹ` 유형이 있으면 answer key에 `review_if_contains: ["?", "7", "C", "4", "2", "L"]`를 넣고, `7,C`나 `4,2`를 자동 치환하지 않고 검토 대상으로 분리한다. 운영 판단에서는 `needs_review_count`보다 `review_required_count`를 더 안전한 확인 대상 수로 본다. 반대로 `safe_auto_grade_count`는 문자열이 맞고 검토 경고도 없는 문항 수로 본다.

## 9. 운영 판단 기준

| 평균 결과 | 판단 |
|---|---|
| 평균 18/20 이상 | 가능성 높음. 자동 인식 + 확인 흐름 검토 가능 |
| 평균 16-17/20 | 보완 필요. crop, 촬영 가이드, Vision prompt 재점검 |
| 평균 15/20 이하 | 운영 위험. 학생 페이지 이식 보류 |

현재 합산 96/100은 평균 19.2/20 수준이므로 가능성은 높다. 다만 needs_review가 실제로 4문항 발생했으므로, 완전 자동 채점보다 `safe_auto_grade_count`와 `review_required_count`를 분리하는 확인 구조를 먼저 설계해야 한다.

특히 다음 유형은 stress test에서 별도 주의가 필요하다.

- `-3`과 `-7`
- `1`과 `7`
- `0`과 `O`
- `+`, `-`, `±`
- `1/2`와 `7/2`
- `<`, `<=`, `>`, `>=`
- 쉼표 답안 `1,3`
- `sqrt(...)` 계열
- 벡터, 적분, 시그마 같은 수식 기호
- `ㄱ`, `ㄴ`, `ㄷ`, `ㄹ` 선택지형 답안

## 10. 위험도

| 항목 | 위험도 | 이유 |
|---|---|---|
| 충돌 위험 | 낮음 | 현재 작업은 독립 도구와 문서 중심이며 앱 본체와 연결하지 않는다. |
| 런타임/오류 위험 | 중간 | 실제 촬영 조건, 글씨체, Vision 모델 응답 품질에 따라 인식률이 달라질 수 있다. |
| 데이터 손실 위험 | 낮음 | 현재 검증은 샘플 이미지와 결과 JSON/리포트 생성 중심이며 학생 데이터나 DB를 수정하지 않는다. |

## 11. 금지/보류 상태

아직 하지 않은 작업:

- 학생 페이지 이식
- 서버 API 추가
- DB 저장
- 자동 채점 연결
- 외부 OCR/API 자동 호출
- API 키/secret 사용
- 실제 학생 데이터 처리
