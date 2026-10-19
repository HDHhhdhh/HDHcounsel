# Subjective OCR Review Rules

This note documents the review gate used by `evaluate_ocr_result.py`. It is for the standalone subjective sheet lab only and does not connect to the app, server, student page, database, or any OCR API.

## Core Distinction

- `needs_review`: the recognized answer is missing or does not match the expected/canonical/accepted answer.
- `review_required`: the answer may match, but warnings, crop diagnostics, or answer-key-specific risks mean a person should confirm it.
- `safe_auto_grade`: the answer matched and no review-required risk signal was found.

## Risk Warnings

These warnings force `review_required=true`:

- `uncertain_read`
- `blank_or_missing`
- `original_enhanced_disagree`
- `low_visible_ink`
- `possible_crop_cutoff`
- `plus_minus_uncertain`
- `jamo_choice_uncertain`
- `jamo_choice_confusion`
- `jamo_choice_mixed_with_confusables`
- `fraction_structure_uncertain`
- `sqrt_structure_uncertain`
- `exponent_uncertain`
- `multiple_possible_reads`

Historical warning codes such as `manual_read_uncertain`, `recognized_uncertain`, `crop_partially_cut`, and `answer_not_visible_or_crop_missed` are also kept as review-required risks for backward compatibility.

## Crop Diagnostics

If OCR/crop result items include any of these true flags, the item becomes `review_required=true`:

- `low_visible_ink`
- `ink_near_top_edge`
- `ink_near_bottom_edge`
- `ink_near_left_edge`
- `ink_near_right_edge`
- `possible_answer_outside_safe_zone`

## Jamo Choice Confusables

When the answer key contains `ㄱ`, `ㄴ`, `ㄷ`, or `ㄹ`, visually similar recognized characters trigger review:

- `ㄱ`: `7`
- `ㄴ`: `4`, `L`, `l`
- `ㄷ`: `C`, `c`
- `ㄹ`: `2`

The evaluator does not auto-correct these characters. It preserves `recognized` and sends the item to review.
