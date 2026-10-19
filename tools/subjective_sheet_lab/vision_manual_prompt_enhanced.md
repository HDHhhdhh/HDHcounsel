# Enhanced Manual Vision OCR Prompt

Upload one enhanced contact sheet, then paste this prompt.

```text
이미지에 있는 Q번호의 수학 답안만 읽어 주세요.

규칙:
- 이미지에 보이는 Q번호만 읽습니다.
- 모든 Q번호를 빠짐없이 items에 넣습니다.
- 추측하지 않습니다.
- 애매하면 recognized와 final에 "?"를 넣고 status를 "needs_review"로 둡니다.
- 수식 답안은 사람이 읽기 쉬운 간단한 텍스트로 씁니다.
- JSON만 출력합니다.
- 설명 문장, Markdown, 코드블록은 출력하지 않습니다.

특히 주의:
- +, -, ±를 명확히 구분합니다.
- 0/O, 1/7을 구분합니다.
- <, <=, >, >=를 구분합니다.
- sqrt, 분수, 벡터, 적분, 시그마 표기는 의미가 보존되게 씁니다.
- 루트 안 내용이 애매하면 "sqrt(?)"처럼 ?를 남깁니다.
- 읽을 수 없는 문항은 "?"로 둡니다.
- ㄱ, ㄴ, ㄷ, ㄹ은 가능한 답안입니다.
- ㄱ을 7로, ㄴ을 4/L로, ㄷ을 C로, ㄹ을 2로 바꾸지 않습니다.
- ㄱ/ㄴ/ㄷ/ㄹ 선택지가 애매하면 추측하지 말고 "?" 또는 status "needs_review"로 표시합니다.

아래 JSON 형식만 출력하세요.

{
  "ok": true,
  "engine": "manual_vision_enhanced",
  "items": [
    {"question": 1, "recognized": "<Q001에서 읽은 값>", "final": "<Q001에서 읽은 값>", "status": "recognized", "warnings": []},
    {"question": 2, "recognized": "<Q002에서 읽은 값>", "final": "<Q002에서 읽은 값>", "status": "recognized", "warnings": []}
  ],
  "warnings": ["manual_vision_enhanced_result"]
}
```

For each contact sheet, continue the same `items` pattern for the Q numbers shown in that image.
