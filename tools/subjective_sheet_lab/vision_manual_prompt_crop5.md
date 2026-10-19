# Manual Vision OCR Prompt For Crop 5

Upload `vision_contact_crop5.png` to ChatGPT or Gemini web UI, then paste this prompt.

```text
이미지에 있는 Q001~Q005 답만 읽어주세요.

규칙:
- Q001, Q002, Q003, Q004, Q005만 읽습니다.
- 보이지 않는 내용은 추측하지 않습니다.
- 애매하면 recognized와 final에 "?"를 넣고 status를 "needs_review"로 둡니다.
- LaTeX를 과하게 만들지 말고, 사람이 읽는 짧은 텍스트로 씁니다.
- 예: 1, -3, x=2, 0.5, 1/2
- 설명하지 말고 JSON만 출력합니다.
- 아래 예시의 recognized/final 값은 그대로 복사하지 말고, 반드시 이미지에서 직접 읽은 값으로 채우세요.

반드시 아래 JSON 형식만 출력하세요.

{
  "ok": true,
  "engine": "manual_vision",
  "items": [
    {"question": 1, "recognized": "<Q001에서 읽은 값>", "final": "<Q001에서 읽은 값>", "status": "recognized"},
    {"question": 2, "recognized": "<Q002에서 읽은 값>", "final": "<Q002에서 읽은 값>", "status": "recognized"},
    {"question": 3, "recognized": "<Q003에서 읽은 값>", "final": "<Q003에서 읽은 값>", "status": "recognized"},
    {"question": 4, "recognized": "<Q004에서 읽은 값>", "final": "<Q004에서 읽은 값>", "status": "recognized"},
    {"question": 5, "recognized": "<Q005에서 읽은 값>", "final": "<Q005에서 읽은 값>", "status": "recognized"}
  ],
  "warnings": []
}
```

Save the model output as:

```text
tools/subjective_sheet_lab/samples/output/ocr_result_crop5_manual_vision.json
```

Then evaluate it with `evaluate_ocr_result.py`.
