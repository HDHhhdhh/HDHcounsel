# Existing Student Submission Flow Audit

작성 목적: 주관식 OCR Lab을 실제 학생 페이지와 서버에 이식하기 전에, 현재 확인 가능한 기존 학생 제출 API와 저장 흐름을 읽기 전용으로 정리한다. 이 문서는 코드 변경 없이 조사 결과만 고정한다.

## 조사 범위와 근거

- 로컬 프로젝트: `C:\Users\idotd\Desktop\OneDrive-Local-Projects\01_apps\counsel-note`
- 외부 학생 페이지 스냅샷: `C:\Users\idotd\Desktop\student_page_extra_20260510_182443\student.js`
- 외부 학생 페이지 힌트 스냅샷: `C:\Users\idotd\Desktop\student_page_extra_20260510_182443\student_js_test_hints.txt`
- 테스트 페이지 분석 문서: `test_pipeline_analysis_for_gpt.txt`
- 조회용 API helper: `counsel_modules/test_api_utils.py`

주의: 현재 로컬 `counsel-note` 프로젝트에는 실제 `/api/submit-test` 서버 구현이 보이지 않는다. 기존 학생 제출 흐름의 세부 동작은 외부 `student.js` 스냅샷 기준으로 확인했다. 실제 저장소와 DB 구현은 학생 페이지 서버 원본 코드를 추가로 확인해야 한다.

## 발견한 파일, 함수, endpoint 목록

| 구분 | 위치 | 확인 내용 |
|---|---|---|
| 학생 페이지 JS 스냅샷 | `C:\Users\idotd\Desktop\student_page_extra_20260510_182443\student.js` | 학생 제출 모달, `answersText`, `/api/submit-test`, fallback 저장 흐름 확인 |
| 학생 페이지 힌트 | `C:\Users\idotd\Desktop\student_page_extra_20260510_182443\student_js_test_hints.txt` | `tsSubmit`, `tsAnswersText`, `/api/submit-test`, `/api/logs/patch` 관련 라인 정리 |
| 상담앱 테스트 API helper | `counsel_modules/test_api_utils.py` | `/api/tests-config`, `/api/tests-stats` 조회용 helper만 존재 |
| 상담앱 본체 | `app.py` | Streamlit 상담앱. `data/uploads`는 상담 녹음/로그 CSV 업로드용이며 학생 답안 업로드 API가 아님 |
| 테스트 페이지 분석 | `test_pipeline_analysis_for_gpt.txt` | `/api/tests-config`, `/api/tests-stats`, `/api/tests-records`, `POST /api/tests-config` 위험성 기록 |
| Lab 도구 | `tools/subjective_sheet_lab/**` | crop/enhance/evaluate/final payload/grade dry-run 도구. 실제 학생 제출 API와는 아직 분리됨 |

확인된 endpoint 성격:

- `GET /api/tests-config`: 시험 카탈로그 조회.
- `GET /api/tests-stats`: 시험 통계 조회.
- `GET /api/tests-records`: 테스트 기록 조회용으로 분석 문서에 언급됨.
- `POST /api/submit-test`: 기존 학생 답안 제출 API. 외부 `student.js` 스냅샷에서 확인됨.
- `GET /api/logs/entry`: fallback에서 기존 로그 entry 조회.
- `POST /api/logs/patch`: fallback 마지막 단계에서 테스트 결과를 로그에 병합.
- `POST /api/tests-config`: 테스트 설정 저장/삭제에 쓰이는 위험 endpoint. 이번 이식에서 건드리면 안 되는 영역.

## 1. 기존 학생 페이지 경로

외부 `student.js` 스냅샷 기준 학생 식별자는 다음 순서로 결정된다.

1. `window.__STU_SID__`
2. 경로 마지막 segment: `/student/{sid}`
3. query string의 `sid`

따라서 기존 학생 페이지 경로 패턴은 `/student/{sid}` 계열로 보는 것이 안전하다. 로컬 `counsel-note` 프로젝트 자체에는 `routes`, `static`, `templates` 디렉터리가 없어서 이 학생 페이지 서버 구현은 현재 폴더 밖에 있는 것으로 보인다.

## 2. 기존 테스트 제출 API

외부 `student.js` 스냅샷 기준 1차 제출은 다음 payload를 보낸다.

```json
{
  "sid": "...",
  "testId": "...",
  "round": 1,
  "answersText": "...",
  "memo": "..."
}
```

제출 대상은 `POST /api/submit-test`이다. 성공 응답은 다음 형태를 기대한다.

```json
{
  "ok": true,
  "score": "18/20",
  "wrong": [2, 7],
  "pct": 90
}
```

서버 제출이 실패하면 클라이언트가 `tests-config` 정답키로 fallback 채점한 뒤, 구버전 payload를 다시 `POST /api/submit-test`로 보낸다.

```json
{
  "sid": "...",
  "name": "시험명",
  "score": "18/20",
  "wrong": [2, 7],
  "memo": "..."
}
```

그마저 실패하면 `GET /api/logs/entry`로 당일 로그를 읽고, `POST /api/logs/patch`로 `entry.tests`에 `{ name, score, wrong, memo, createdAt }`를 추가하는 백업 흐름이 있다.

## 3. answer / answersText 처리 방식

기존 학생 페이지는 `textarea#tsAnswersText`에서 답안을 문자열로 받는다. UI 안내는 공백, 쉼표, 붙여쓰기 입력을 모두 허용하는 객관식 중심 구조다.

관련 흐름:

1. `tsAnswersText` 값을 trim 한다.
2. 비어 있으면 제출을 막는다.
3. 서버에는 `answersText` 문자열 그대로 보낸다.
4. 서버 채점 실패 시 클라이언트 fallback에서 `parseAnswerSpec(answersText, problems)`로 답안을 배열화한다.
5. 정답키는 `test.answerKeys[round]`를 우선 사용하고, legacy `test.answerKey`를 fallback으로 사용한다.

주관식 Lab의 line-based `answersText`와 final payload는 아직 기존 `/api/submit-test` payload에 직접 연결되어 있지 않다.

## 4. student_id 또는 sid 처리 방식

기존 흐름의 학생 식별자는 `sid`이다. 외부 `student.js`에서는 `window.__STU_SID__`, `/student/{sid}`, `?sid=`를 순서대로 사용한다.

로컬 Lab 문서와 schema는 `student_id`를 사용하지만, 실제 기존 학생 페이지와 연결할 때는 `sid`와 `student_id` 매핑 정책이 필요하다. 권장 방식은 다음과 같다.

- 서버 내부 attempt에는 `student_id`와 `sid`를 모두 보존한다.
- 기존 학생 페이지와 로그 API를 건드릴 때는 `sid` 호환성을 유지한다.
- 새 주관식 payload에는 `student_id`, `attempt_id`, `case_id`를 함께 둔다.

## 5. test_id / attempt_id 유사 구조 존재 여부

기존 학생 제출에는 `testId`와 `round`가 존재한다. `attempt_id`에 해당하는 독립 시도 ID는 외부 `student.js` 스냅샷에서 확인되지 않았다.

주관식 OCR 이식에는 `attempt_id`가 새로 필요하다. 이유는 다음과 같다.

- 원본 사진, 보정 이미지, crop, enhanced crop, retake history를 한 제출 단위로 묶어야 한다.
- 문항별 재촬영이 여러 번 발생할 수 있다.
- final payload와 grade report를 추적해야 한다.

## 6. 제출 결과 저장 위치

현재 로컬 `counsel-note` 프로젝트에서는 `/api/submit-test`의 서버 저장 구현을 찾지 못했다. 외부 `student.js` fallback 흐름에서 유추 가능한 저장 경로는 다음뿐이다.

- 1차: `/api/submit-test` 서버 내부 저장.
- fallback: `/api/logs/patch`로 당일 log entry의 `tests` 배열에 결과 병합.
- admin/test 분석 문서: `/api/tests-stats`, `/api/tests-records`가 존재하므로 서버 쪽에는 테스트 기록 조회 저장소가 별도로 있을 가능성이 높다.

정확한 저장 위치는 실제 학생 페이지 서버 소스에서 `/api/submit-test`, `/api/logs/patch`, `/api/tests-records` 구현을 확인해야 한다.

## 7. 파일 업로드 기능 존재 여부

현재 로컬 `counsel-note`의 `app.py`에는 Streamlit `st.file_uploader`가 존재하지만 용도는 다음으로 제한된다.

- 상담 녹음 파일 업로드.
- admin 로그 CSV를 학생 Docs로 옮기기 위한 CSV 업로드.

기존 학생 제출 흐름에서 답안지 이미지 업로드 API는 확인되지 않았다. 주관식 OCR 이식에는 별도 답안지 업로드 endpoint와 파일 저장 구조가 필요하다.

## 8. static / templates / routes 구조

현재 로컬 `counsel-note` 프로젝트에서 확인한 결과:

- `routes/`: 없음.
- `static/`: 없음.
- `templates/`: 없음.
- `app.py`: Streamlit 단일 앱 구조.
- `counsel_modules/`: Streamlit 앱 helper 중심.
- `tools/subjective_sheet_lab/`: 독립 Lab 도구.

따라서 학생 페이지 서버는 현재 프로젝트와 분리되어 있거나, 별도 배포 폴더에 존재할 가능성이 높다. 실제 이식 전에 서버 원본 폴더를 확정해야 한다.

## 9. 기존 객관식 / 주관식 처리 분리 여부

외부 `student.js` 기준 기존 제출 모달은 객관식 또는 단순 답안 문자열 제출에 맞춰져 있다.

- `answersText`는 공백, 쉼표, 붙여쓰기 입력을 허용한다.
- `answerKeys[round]` 또는 `answerKey`로 채점한다.
- 주관식 OCR용 `crop`, `recognized`, `review_required`, `retake_required`, `final_answer_payload` 구조는 없다.

현재로서는 객관식과 주관식 OCR 제출 처리가 분리되어 있지 않다. 기존 `/api/submit-test`에 주관식 OCR을 억지로 끼워 넣는 것은 위험하다.

## 10. subjective endpoint 추가 시 충돌 가능 지점

충돌 가능성이 큰 지점:

1. `/api/submit-test`
   - 기존 객관식 제출과 fallback 저장이 이미 연결되어 있다.
   - payload 형태가 `answersText` 중심이라 주관식 final payload와 다르다.

2. `/api/logs/patch`
   - fallback 마지막 단계에서 기존 로그를 직접 병합한다.
   - 주관식 시도/재촬영 history를 이 구조에 넣으면 로그가 비대해지고 충돌 위험이 있다.

3. `student.js`의 제출 모달
   - `tsAnswersText` 직접 입력 흐름과 주관식 OCR 확인 흐름이 다르다.
   - review_required만 학생 입력 허용, retake_required는 재촬영 필수라는 정책이 기존 textarea 흐름과 충돌한다.

4. `tests-config`
   - 기존 정답키 구조와 주관식 answer key JSON schema가 다르다.
   - `POST /api/tests-config`는 전체 설정 덮어쓰기 성격이라 이식 중 호출 금지 대상이다.

5. 파일 저장소
   - 현재 상담앱 `data/uploads`는 상담 녹음용이다.
   - 주관식 답안 이미지/crop 저장소로 재사용하면 cleanup, 보존, 개인정보 관리 충돌이 생길 수 있다.

## 현재 제출 흐름 요약

```text
학생 페이지 /student/{sid}
  -> openTestSubmit 버튼
  -> testSubmitModal 생성 또는 표시
  -> tsTestId, tsRound, tsAnswersText, tsMemo 입력
  -> POST /api/submit-test
       body: { sid, testId, round, answersText, memo }
  -> 서버 채점/저장 성공
       response: { ok, score, wrong, pct }
  -> updateInfo, alert, updPing, close

서버 제출 실패 시
  -> tests-config의 answerKeys 또는 answerKey로 클라이언트 채점
  -> POST /api/submit-test
       body: { sid, name, score, wrong, memo }
  -> 실패하면 GET /api/logs/entry 후 POST /api/logs/patch
       entry.tests에 결과 추가
```

## 데이터 흐름 다이어그램 텍스트

```text
[student.js]
  sid 결정
    window.__STU_SID__
    /student/{sid}
    ?sid=

[tests-config]
  GET /api/tests-config
    categories -> tests -> id/name/problems/curriculum/answerKeys

[submit modal]
  tsTestId
  tsRound
  tsAnswersText
  tsMemo

[primary submit]
  POST /api/submit-test
    sid, testId, round, answersText, memo

[server result]
  score, wrong, pct

[fallback submit]
  parseAnswerSpec
  gradeClientSide
  POST /api/submit-test
    sid, name, score, wrong, memo

[last fallback]
  GET /api/logs/entry
  POST /api/logs/patch
    entry.tests += { name, score, wrong, memo, createdAt }
```

## subjective OCR 이식 시 재사용 가능한 부분

재사용 가능:

- `sid` 기반 학생 식별.
- `testId`와 `round` 개념.
- `tests-config`에서 시험 카탈로그를 읽는 흐름.
- 결과 요약을 학생 페이지에 표시하는 UX 패턴.
- `wrong`, `score`, `pct` 같은 최종 결과 표현 방식.
- Lab의 `normalize_math_answer.py`, `evaluate_ocr_result.py`, `grade_final_payload.py` 평가 규칙.
- Lab의 `final_answer_payload_schema.example.json` payload 구조.
- Lab의 `student_confirmation_policy.md`, `retake_policy.md` 정책.

## 새로 만들어야 할 부분

필수 신규 요소:

1. 주관식 attempt 저장 구조
   - `attempt_id`, `sid`, `student_id`, `test_id`, `round`, 상태값 보존.

2. 답안지 이미지 업로드 endpoint
   - 원본 사진 저장.
   - 보정 이미지, crop, enhanced crop 저장.

3. 문항별 result 저장 구조
   - `recognized`, `candidates`, `warnings`, `review_reasons`, `review_required`, `retake_required`.

4. 학생 확인 UI
   - safe_auto_grade는 자동 확정.
   - review_required만 후보 선택 또는 직접 입력 허용.
   - retake_required는 문항별 재촬영만 허용.

5. 문항별 재촬영 endpoint
   - 기존 crop/evidence를 덮어쓰지 않고 history에 보존.

6. final payload 생성 및 저장
   - `final_answer_source`를 기준으로 최종 답안 고정.

7. answer key JSON 관리
   - 시험별 `canonical_answer`, `accepted_answers`, `order_insensitive`, `review_if_contains` 관리.

8. grade report 생성
   - final payload와 answer key 기준으로 채점.

## 건드리면 위험한 부분

- 기존 `/api/submit-test` 구현을 직접 변경하는 것.
- 기존 `answersText` textarea 제출 흐름을 제거하는 것.
- `/api/logs/patch` fallback 흐름에 주관식 attempt 전체를 넣는 것.
- `POST /api/tests-config`를 이식 검증 중 호출하는 것.
- 상담앱의 `data/uploads`를 주관식 답안 이미지 저장소로 재사용하는 것.
- 기존 학생 로그나 `data/**`를 직접 수정하는 것.
- 기존 객관식 정답키 구조를 주관식 answer key schema로 덮어쓰는 것.

## 권장 신규 endpoint 위치

현재 로컬 프로젝트에는 서버 route 구조가 없으므로, 실제 학생 서버 원본을 확인한 뒤 별도 module 또는 별도 prefix로 추가하는 것이 안전하다.

권장 prefix:

```text
/api/subjective/upload-sheet
/api/subjective/attempt/{attempt_id}
/api/subjective/confirm-item
/api/subjective/retake-item
/api/subjective/finalize
/api/subjective/result/{attempt_id}
```

원칙:

- 기존 `/api/submit-test`는 객관식/기존 제출용으로 유지.
- 주관식 OCR은 `/api/subjective/*`로 분리.
- 최종 grade report가 안정화된 뒤에만 기존 테스트 기록/통계와 연결.

## 권장 feature flag 위치

서버 원본 구조 확인 전 임시 권장안:

- 서버 config 또는 환경 설정에 `SUBJECTIVE_OCR_ENABLED` 같은 feature flag를 둔다.
- 학생 페이지에서는 해당 학생/시험/test type이 주관식 OCR 대상일 때만 업로드 UI를 노출한다.
- Lab 단계에서는 `tools/subjective_sheet_lab`의 answer key JSON과 final payload schema를 기준으로 검증한다.
- 기존 tests-config 전체 저장 endpoint를 feature flag 저장소로 사용하지 않는다.

## 다음 단계 제안

1. 실제 학생 페이지 서버 원본 폴더를 확정한다.
2. 서버 코드에서 `/api/submit-test`, `/api/logs/patch`, `/api/tests-records`, `/api/tests-stats` 구현을 읽기 전용으로 확인한다.
3. 기존 테스트 결과 저장소가 JSON 파일인지 DB인지 확인한다.
4. `sid`, `student_id`, `testId`, `round`가 저장소에서 어떤 키로 쓰이는지 확인한다.
5. 주관식 전용 `/api/subjective/*` endpoint 설계를 기존 route 스타일에 맞춘다.
6. `end_to_end_dry_run_guide.md`를 실제 학생 샘플로 한 번 더 통과시킨다.
7. feature flag가 꺼진 상태에서 서버 내부 처리만 먼저 붙이고, 기존 학생 제출 흐름이 그대로 동작하는지 확인한다.

## 최종 판단

현재 Lab은 이식 전 검증 도구와 정책 문서가 충분히 갖춰진 상태다. 다만 기존 학생 제출 서버 구현이 이 로컬 프로젝트 내부에 없으므로, 실제 코드 이식 전에는 반드시 서버 원본의 `/api/submit-test` 저장 구조를 확인해야 한다.

가장 안전한 이식 전략은 기존 객관식 제출 흐름을 유지하고, 주관식 OCR은 신규 endpoint와 신규 attempt 저장 구조로 분리한 뒤, 최종 grade report만 기존 통계/기록 흐름에 연결하는 것이다.
