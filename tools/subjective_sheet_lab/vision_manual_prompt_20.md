# Manual Vision OCR Prompt For 20 Questions

Use this prompt twice:

1. Upload `vision_contact_q001_q010.png` and ask for Q001-Q010.
2. Upload `vision_contact_q011_q020.png` and ask for Q011-Q020.

Save the two JSON outputs as:

```text
tools/subjective_sheet_lab/samples/output/ocr_result_manual_vision_q001_q010.json
tools/subjective_sheet_lab/samples/output/ocr_result_manual_vision_q011_q020.json
```

Prompt to paste:

```text
이미지에 있는 표시된 문제 번호의 답만 읽어주세요.

규칙:
- 이미지에 보이는 Q번호만 읽습니다.
- 이미지에 보이는 모든 Q번호를 빠짐없이 items에 넣습니다.
- 첫 번째 이미지에서는 Q001~Q010, 두 번째 이미지에서는 Q011~Q020을 기대합니다.
- 보이지 않는 내용은 추측하지 않습니다.
- 애매하면 recognized와 final에 "?"를 넣고 status를 "needs_review"로 둡니다.
- LaTeX를 과하게 만들지 말고, 사람이 읽는 짧은 텍스트로 씁니다.
- 설명하지 말고 JSON만 출력합니다.
- 아래 예시의 recognized/final 값은 그대로 복사하지 말고, 반드시 이미지에서 직접 읽은 값으로 채우세요.

반드시 아래 JSON 형식만 출력하세요.

{
  "ok": true,
  "engine": "manual_vision",
  "items": [
    {"question": 1, "recognized": "<Q001에서 읽은 값>", "final": "<Q001에서 읽은 값>", "status": "recognized"},
    {"question": 2, "recognized": "<Q002에서 읽은 값>", "final": "<Q002에서 읽은 값>", "status": "recognized"},
    {"question": 3, "recognized": "<Q003에서 읽은 값>", "final": "<Q003에서 읽은 값>", "status": "recognized"}
  ],
  "warnings": []
}
```

For the first image, continue this pattern through question 10. For the second image, use the actual Q011-Q020 question numbers in the `question` field.
