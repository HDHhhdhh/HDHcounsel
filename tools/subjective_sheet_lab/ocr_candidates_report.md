# Subjective Answer OCR/AI Candidate Report

Scope: evaluate candidate engines for reading cropped subjective answer images (`q001.png` ... `q020.png`). This report is design-only. No external OCR/AI API was called, no API key was read, and no student-page integration or auto-grading was implemented.

Date checked: 2026-05-28.

## Current Pipeline State

- `crop_answer_boxes.py` produces per-question crop images and a crop result JSON.
- Crop-only result uses `answersText: null`, `status: pending_recognition`, and item fields `recognized: null`, `final: null`.
- The next layer should fill `recognized` with OCR/AI output, let the student review it, store corrections in `final`, then generate line-based `answersText`.
- Manual-first entry is out of policy. The expected flow is: automatic recognition -> review -> fix only problem items -> final submit.

## Common Output Contract

Every engine adapter should produce the same shape:

```json
{
  "ok": true,
  "mode": "subjective_handwriting_recognition",
  "engine": "engine_name",
  "test_id": "subjective_unit_test_sample",
  "answersText": "1\n-3\nx=2",
  "items": [
    {
      "question": 1,
      "cropPath": "crops/q001.png",
      "recognized": "1",
      "final": "1",
      "status": "recognized",
      "confidence": null,
      "warnings": []
    }
  ],
  "warnings": []
}
```

Recommended item statuses:

- `recognized`: engine output is present and reviewable.
- `low_confidence`: engine supplied a low confidence or the output is suspicious.
- `ambiguous`: multiple plausible outputs exist.
- `failed`: engine failed for this crop.
- `needs_review`: final value must be checked before submission.

## Candidate Comparison

| Candidate | Math answers | Handwriting | Cost | Privacy/ops risk | Windows/server burden | Fit |
|---|---:|---:|---:|---:|---:|---|
| Mathpix Convert API | High | High for STEM | Paid per image | Medium, external upload | Low | Best first benchmark |
| OpenAI vision | Medium-High | Medium-High | Paid token/image input | Medium, external upload and model variance | Low | Good fallback/normalizer benchmark |
| Gemini vision | Medium-High | Medium-High | Paid/free tier depends on model/tier | Medium, external upload and tier policy | Low | Good cost-speed benchmark |
| Google Cloud Vision | Low-Medium for math | Medium for handwriting text | Low per 1000 units | Medium, Google Cloud auth | Low | Baseline OCR, not enough for math alone |
| Azure AI Vision / Document Intelligence Read | Low-Medium for math | Medium for handwriting text | Region/tier pricing | Medium, Azure auth | Low | Baseline OCR, not enough for math alone |
| Pix2Text | Medium-High for formulas | Unknown for messy handwriting answers | Free runtime, heavy install | Low if local | High | Best local experiment after API baseline |
| pix2tex / LaTeX-OCR | Medium for isolated formulas | Weak for mixed text | Free runtime, heavy install | Low if local | Medium-High | Formula-only sub-engine |
| TrOCR | Low for math | Medium for ordinary handwriting | Free runtime, heavy install | Low if local | High | Not ideal for math symbols |
| PaddleOCR | Medium with formula modules | Medium | Free runtime, heavy install | Low if local | High | Promising but heavier than this app stage |

## Candidate Notes

### Mathpix

Best fit for the first real benchmark because it is explicitly built for printed and handwritten STEM content, including math. It can process single images and return text/LaTeX/Markdown-like structures. The operational risks are cost, account setup, billing controls, and image retention policy review.

Use only in a gated evaluation script later. Never call it from the student page until a human-review flow and spending cap are in place.

### Google Cloud Vision

`DOCUMENT_TEXT_DETECTION` supports handwriting OCR and returns document text structure. It is useful as a cheap baseline for digits, plain text, and simple symbols, but it is not math-specific. Expect errors with roots, stacked fractions, inequalities, and compact algebra unless a later normalization/review layer catches them.

### Azure AI Vision / Document Intelligence

The Read model extracts printed and handwritten text from images/documents. It is a reasonable baseline for handwriting, especially if Azure is already operationally acceptable. Like Google Vision, it should not be treated as a math-answer engine by itself.

### OpenAI / Gemini Vision

Vision-language models can read images and can be prompted to output exactly one short answer per crop. They may handle messy symbols better than generic OCR in some cases, but they can also normalize too aggressively or hallucinate. They should be evaluated with strict prompts, JSON schema expectations, and mandatory review.

### Local/Open-Source

Pix2Text is the strongest local candidate for math/formula recognition because it targets text plus LaTeX formula extraction. pix2tex is useful for isolated formula snippets but less suitable for mixed short answers. TrOCR is better for ordinary handwriting than math. PaddleOCR has modern formula-recognition modules, but installation/model size/runtime complexity is higher than the current prototype.

## Recommended Strategy

1. Build an offline evaluation harness around existing crop outputs and expected answers.
2. Use `mock_recognition_result.py` now to validate result shape, review UI assumptions, and line-based `answersText`.
3. For a paid/API pilot, benchmark Mathpix first on a small set of 20-60 crops, then compare OpenAI or Gemini vision on the same crops.
4. Keep Google Vision or Azure Read as cheap baselines, not as final math engines.
5. Try Pix2Text locally only after the API benchmark confirms which answer shapes matter most.

## Evaluation Design

Dataset:

- Start with v2 synthetic crops for schema sanity.
- Add 3-5 real photographed v2 sheets.
- Keep expected answer files separate from crop result JSON.

Metrics:

- Exact match after light normalization.
- Symbol-critical match for `-`, `/`, `sqrt`, `<=`, `>=`, comma-separated pairs.
- `needs_review` rate.
- Per-crop latency.
- Cost per 20-question sheet.
- Engine failure rate.

Normalization for evaluation only:

- Trim whitespace.
- Convert common OCR variants such as `√3` -> `sqrt(3)` only in an evaluation helper, not in raw recognized output.
- Preserve raw output separately.

Stop criteria:

- If a candidate cannot reliably distinguish negative signs, fractions, and square roots, it cannot be the sole first engine.
- If an engine has no confidence score, treat all outputs as review-required.
- No answer should be auto-submitted without the review screen.

## Sources Checked

- Mathpix OCR API docs: https://docs.mathpix.com/
- Mathpix Convert API pricing: https://website.mathpix.com/pricing/api
- Google Cloud Vision handwriting docs: https://docs.cloud.google.com/vision/docs/handwriting
- Google Cloud Vision pricing: https://cloud.google.com/vision/pricing
- Azure Document Intelligence overview: https://learn.microsoft.com/en-us/azure/ai-services/document-intelligence/overview
- Azure Document Intelligence pricing: https://azure.microsoft.com/en-us/pricing/details/ai-document-intelligence/
- OpenAI image/vision docs: https://platform.openai.com/docs/guides/images-vision
- Gemini API pricing: https://ai.google.dev/gemini-api/docs/pricing
- Pix2Text: https://github.com/breezedeus/Pix2Text
- pix2tex docs: https://pix2tex.readthedocs.io/en/latest/pix2tex.html
- TrOCR docs: https://huggingface.co/docs/transformers/model_doc/trocr
- PaddleOCR docs: https://www.paddleocr.ai/main/en/index/index.html
