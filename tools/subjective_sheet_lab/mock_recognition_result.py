#!/usr/bin/env python
"""Build a mock recognition result from subjective crop output.

This script does not run OCR. It injects expected answers into the same shape
that a later OCR/AI engine adapter should produce.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_answers(args: argparse.Namespace, fallback_count: int) -> list[str]:
    if args.answers_file:
        text = Path(args.answers_file).read_text(encoding="utf-8-sig")
        answers = text.splitlines()
    else:
        raw = args.answers or ""
        answers = raw.split("|") if "|" in raw else raw.splitlines()
    answers = [answer.strip() for answer in answers]
    if len(answers) < fallback_count:
        answers.extend([""] * (fallback_count - len(answers)))
    return answers


def item_question(item: dict[str, Any], index: int) -> int:
    try:
        return int(item.get("question") or index + 1)
    except (TypeError, ValueError):
        return index + 1


def build_result(crop_result: dict[str, Any], answers: list[str], engine: str) -> dict[str, Any]:
    crop_items = list(crop_result.get("items") or [])
    if not crop_items:
        crop_items = [{"question": index + 1, "cropPath": None} for index in range(len(answers))]

    source_ok = bool(crop_result.get("ok")) and bool(crop_result.get("items"))
    warnings: list[str] = []
    if not source_ok:
        warnings.append("crop_result_not_ready")

    result_items: list[dict[str, Any]] = []
    final_answers: list[str] = []
    for index, item in enumerate(crop_items):
        question = item_question(item, index)
        answer = answers[question - 1] if 0 <= question - 1 < len(answers) else ""
        answer = answer.strip()
        item_warnings: list[str] = []
        if not answer:
            item_warnings.append("empty_expected_answer")
        if not item.get("cropPath"):
            item_warnings.append("missing_crop_path")
        status = "recognized" if source_ok and answer else "needs_review"
        result_items.append(
            {
                "question": question,
                "cropPath": item.get("cropPath"),
                "recognized": answer if answer else None,
                "final": answer if answer else None,
                "status": status,
                "confidence": None,
                "warnings": item_warnings,
            }
        )
        final_answers.append(answer)

    return {
        "ok": source_ok,
        "mode": "subjective_handwriting_recognition",
        "engine": engine,
        "test_id": crop_result.get("test_id"),
        "test_name": crop_result.get("test_name"),
        "answersText": "\n".join(final_answers),
        "items": result_items,
        "warnings": warnings,
        "source": {
            "crop_result_ok": bool(crop_result.get("ok")),
            "crop_result_status": crop_result.get("status"),
            "crop_result_mode": crop_result.get("mode"),
        },
        "policy": {
            "student_flow": "review_auto_recognition_then_fix_only_problem_items",
            "manual_first_entry": False,
            "auto_grading_connected": False,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a mock OCR/AI recognition result from a crop result JSON.")
    parser.add_argument("--crop-result", required=True, help="Path to crop_answer_boxes.py result JSON.")
    parser.add_argument("--answers", help="Expected answers separated by |, or by newlines if provided by a shell.")
    parser.add_argument("--answers-file", help="Line-based expected answers text file.")
    parser.add_argument("--out", required=True, help="Output mock recognition JSON path.")
    parser.add_argument("--engine", default="mock_expected_answers", help="Engine name to store in the output JSON.")
    args = parser.parse_args()
    if not args.answers and not args.answers_file:
        parser.error("one of --answers or --answers-file is required")
    return args


def main() -> int:
    args = parse_args()
    crop_result = load_json(Path(args.crop_result))
    fallback_count = len(crop_result.get("items") or [])
    answers = parse_answers(args, fallback_count)
    result = build_result(crop_result, answers, str(args.engine))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"ok={result['ok']}")
    print(f"items={len(result['items'])}")
    print(f"answersText_lines={len(result['answersText'].splitlines()) if result['answersText'] else 0}")
    if result["warnings"]:
        print("warnings=" + ",".join(result["warnings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
