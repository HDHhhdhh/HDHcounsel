# Vision Manual Prompt For Batch Contact Sheets

이 문서는 `batch_prepare_stress_test.py`가 만든 5문항 단위 original/enhanced compare contact sheet를 ChatGPT 또는 Gemini 웹 화면에 사람이 직접 업로드한 뒤, 답안 인식 JSON을 받기 위한 표준 프롬프트입니다.

contact sheet에는 각 문항별 original crop과 enhanced crop이 함께 있습니다. enhanced crop은 보조본이며, original crop을 대체하지 않습니다. 둘을 함께 보고 판독하되, 서로 다르게 보이면 반드시 `needs_review: true`로 표시하세요.

## 사용 절차

1. `batch_prepare_stress_test.py`로 case별 crop/contact sheet를 생성한다.
2. 5문항 단위 compare contact sheet 이미지를 웹 Vision 모델 화면에 업로드한다.
3. 아래 "복붙용 프롬프트" 전체를 붙여넣는다.
4. 모델이 반환한 JSON을 case의 `vision_result` 폴더에 저장한다.
5. 이후 merge/evaluate 단계로 넘긴다.

## 복붙용 프롬프트

업로드한 contact sheet 이미지에서 Q001~Q005처럼 표시된 문항의 수학 답안만 읽어 주세요.

contact sheet에는 각 문항마다 original crop과 enhanced crop이 함께 있습니다. enhanced crop은 보조본이며 original crop을 대체하지 않습니다. original과 enhanced를 함께 참고하되, 둘이 다르게 보이면 `needs_review`를 `true`로 두세요.

판독 원칙:

- 수학 답안만 읽으세요.
- 문항 번호는 contact sheet에 표시된 번호를 그대로 따르세요.
- 추측하지 마세요.
- 애매하면 recognized에 `"?"`를 포함하세요.
- 답안이 비어 있으면 recognized를 `""`로 두세요.
- original과 enhanced가 다르게 보이면 `needs_review: true`로 두세요.
- 답안이 crop 밖으로 나간 것 같으면 `needs_review: true`로 두세요.

반드시 보존할 기호:

- `+`, `-`, `±`를 구분하세요.
- `0`과 `O`를 구분하세요.
- `1`과 `7`을 구분하세요.
- `<`, `<=`, `>`, `>=`를 구분하세요.
- 분수는 가능하면 `1/2` 형식으로 쓰세요.
- 루트는 `sqrt( )` 형식으로 쓰세요.
- 지수는 `^` 형식으로 쓰세요.
- 벡터는 `vec( )` 또는 원문 형태를 보존하세요.
- 시그마/적분 등 수학 기호는 가능한 텍스트로 보존하세요.

한글 자음 선택지형 답안 주의:

- `ㄱ`, `ㄴ`, `ㄷ`, `ㄹ`은 가능한 답안입니다.
- `ㄱ`을 `7`로 바꾸지 마세요.
- `ㄴ`을 `4` 또는 `L`로 바꾸지 마세요.
- `ㄷ`을 `C`로 바꾸지 마세요.
- `ㄹ`을 `2`로 바꾸지 마세요.
- 그래도 구분이 애매하면 recognized에는 보이는 대로 쓰고, warnings에 `jamo_choice_uncertain` 또는 `jamo_choice_confusion`을 넣으세요.

`needs_review: true`로 둘 상황:

- 답안 일부가 잘린 것 같음
- 글씨가 흐림
- original과 enhanced 판독이 다름
- `+`와 `±`가 헷갈림
- `ㄱ`/`ㄴ`/`ㄷ`/`ㄹ`과 숫자/영문이 헷갈림
- 지수/분수/루트 구조가 불명확함
- crop 안에 답이 없거나 너무 약하게 보임
- 두 개 이상의 해석 가능성이 있음

warnings는 필요한 경우 아래 값 중에서 사용하세요:

- `uncertain_read`
- `blank_or_missing`
- `original_enhanced_disagree`
- `low_visible_ink`
- `possible_crop_cutoff`
- `plus_minus_uncertain`
- `jamo_choice_uncertain`
- `jamo_choice_confusion`
- `fraction_structure_uncertain`
- `sqrt_structure_uncertain`
- `exponent_uncertain`
- `multiple_possible_reads`

confidence는 아래 3개 중 하나만 사용하세요:

- `high`
- `medium`
- `low`

출력은 JSON만 하세요. markdown 코드블록을 쓰지 마세요. 설명문도 쓰지 마세요. 반드시 아래 구조를 따르세요.

```json
{
  "schema": "manual_vision_batch_result",
  "schema_version": "0.1",
  "external_api_calls": false,
  "contact_sheet": "vision_contact_q001_q005_compare.png",
  "items": [
    {
      "question": 1,
      "recognized": "1/2",
      "needs_review": false,
      "confidence": "high",
      "warnings": [],
      "notes": ""
    },
    {
      "question": 2,
      "recognized": "?",
      "needs_review": true,
      "confidence": "low",
      "warnings": ["uncertain_read"],
      "notes": "The answer is unclear."
    }
  ]
}
```

반환 JSON의 `items`에는 업로드한 contact sheet에 들어 있는 문항만 포함하세요.
