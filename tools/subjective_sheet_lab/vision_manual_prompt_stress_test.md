# Manual Vision Stress Test Prompt

Use this prompt for each stress test contact sheet.

Workflow:

1. Upload a case contact sheet, such as `contact/vision_contact_q001_q010.png` or `contact/vision_contact_q011_q020.png`.
2. Paste the prompt below.
3. Save the JSON-only output into the case folder:
   - `vision_result/ocr_result_manual_vision_q001_q010.json`
   - `vision_result/ocr_result_manual_vision_q011_q020.json`
4. Merge the two parts with `merge_manual_vision_results.py`.
5. Evaluate with `evaluate_ocr_result.py`.

Prompt:

```text
이미지에 있는 표시된 문제 번호의 답만 읽어주세요.

규칙:
- 이미지에 보이는 모든 Q번호를 빠짐없이 items에 넣습니다.
- 보이지 않는 내용은 추측하지 않습니다.
- 애매하면 recognized와 final에 "?"를 넣고 status를 "needs_review"로 둡니다.
- LaTeX를 과하게 만들지 말고, 사람이 읽는 짧은 텍스트로 씁니다.
- 설명하지 말고 JSON만 출력합니다.
- 아래 예시의 recognized/final 값은 그대로 복사하지 말고, 반드시 이미지에서 직접 읽은 값으로 채우세요.

반드시 아래 JSON 형식만 출력하세요.

{
  "ok": true,
  "engine": "manual_vision_stress_test",
  "items": [
    {"question": 1, "recognized": "<Q001에서 읽은 값>", "final": "<Q001에서 읽은 값>", "status": "recognized"},
    {"question": 2, "recognized": "<Q002에서 읽은 값>", "final": "<Q002에서 읽은 값>", "status": "recognized"},
    {"question": 3, "recognized": "<Q003에서 읽은 값>", "final": "<Q003에서 읽은 값>", "status": "recognized"}
  ],
  "warnings": []
}
```

For Q011-Q020 contact sheets, use the actual question numbers in the `question` field.
