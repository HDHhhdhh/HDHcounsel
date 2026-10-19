#!/usr/bin/env python
"""Dry-run grade a subjective final-answer payload against an answer key.

This standalone tool does not call any app/server/API/OCR service. It reads a
final payload JSON and an answer key JSON, then writes a local grade report.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from evaluate_ocr_result import load_answer_key, status_for_answer_spec, value_to_text


CORRECT_MATCH_STATUSES = {"exact_match", "normalized_match", "accepted_match"}


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def answer_specs_by_question(path: Path) -> dict[int, dict[str, Any]]:
    return load_answer_key(path)


def item_question(item: dict[str, Any], fallback: int) -> int:
    try:
        return int(item.get("question") or fallback)
    except (TypeError, ValueError):
        return fallback


def is_gradable_item(item: dict[str, Any], spec: dict[str, Any] | None) -> bool:
    if item.get("grading_status") != "gradable":
        return False
    if item.get("final_answer") is None:
        return False
    if value_to_text(item.get("final_answer")).strip() == "":
        return False
    return spec is not None


def grade_item(item: dict[str, Any], spec: dict[str, Any] | None, fallback_question: int) -> dict[str, Any]:
    question = item_question(item, fallback_question)
    final_answer = item.get("final_answer")
    final_answer_text = value_to_text(final_answer).strip() if final_answer is not None else ""
    source = item.get("final_answer_source")
    payload_grading_status = value_to_text(item.get("grading_status"))
    expected = value_to_text(spec.get("canonical_answer")) if spec else ""

    if not is_gradable_item(item, spec):
        return {
            "question": question,
            "final_answer": None if final_answer is None else final_answer_text,
            "expected": expected,
            "is_correct": None,
            "grading_status": "blocked",
            "final_answer_source": source,
            "match_status": "not_graded",
            "blocked_reason": blocked_reason(item, spec),
            "payload_grading_status": payload_grading_status,
        }

    match_status = status_for_answer_spec(final_answer_text, spec or {})
    is_correct = match_status in CORRECT_MATCH_STATUSES
    return {
        "question": question,
        "final_answer": final_answer_text,
        "expected": expected,
        "is_correct": is_correct,
        "grading_status": "gradable",
        "final_answer_source": source,
        "match_status": match_status,
        "blocked_reason": None,
        "payload_grading_status": payload_grading_status,
    }


def blocked_reason(item: dict[str, Any], spec: dict[str, Any] | None) -> str:
    if spec is None:
        return "missing_answer_key"
    if item.get("grading_status") != "gradable":
        return "payload_grading_status_blocked"
    if item.get("final_answer") is None:
        return "final_answer_null"
    if value_to_text(item.get("final_answer")).strip() == "":
        return "final_answer_blank"
    return "not_gradable"


def build_report(payload: dict[str, Any], answer_specs: dict[int, dict[str, Any]]) -> dict[str, Any]:
    payload_items = [item for item in payload.get("items") or [] if isinstance(item, dict)]
    graded_items = [
        grade_item(item, answer_specs.get(item_question(item, index + 1)), index + 1)
        for index, item in enumerate(payload_items)
    ]
    gradable_items = [item for item in graded_items if item["grading_status"] == "gradable"]
    blocked_items = [item for item in graded_items if item["grading_status"] == "blocked"]
    correct_count = sum(1 for item in gradable_items if item["is_correct"] is True)
    incorrect_count = sum(1 for item in gradable_items if item["is_correct"] is False)
    return {
        "schema": "subjective_grade_report",
        "schema_version": "0.1",
        "external_api_calls": False,
        "test_id": payload.get("test_id"),
        "student_id": payload.get("student_id"),
        "case_id": payload.get("case_id"),
        "attempt_id": payload.get("attempt_id"),
        "source": {
            "payload_schema": payload.get("schema"),
            "answer_key_test_id": None,
        },
        "summary": {
            "total_questions": len(graded_items),
            "gradable_questions": len(gradable_items),
            "blocked_questions": len(blocked_items),
            "correct_count": correct_count,
            "incorrect_count": incorrect_count,
            "score": correct_count,
        },
        "items": graded_items,
    }


def write_report(path: Path, report: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run grade a subjective final-answer payload against an answer key."
    )
    parser.add_argument("--payload", required=True, help="Final answer payload JSON path.")
    parser.add_argument("--answer-key", required=True, help="Answer key JSON path.")
    parser.add_argument("--output", required=True, help="Output grade report JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    payload = load_json(Path(args.payload))
    answer_specs = answer_specs_by_question(Path(args.answer_key))
    report = build_report(payload, answer_specs)
    key_payload = load_json(Path(args.answer_key))
    report["source"]["answer_key_test_id"] = key_payload.get("test_id")
    write_report(Path(args.output), report)

    summary = report["summary"]
    print(f"Wrote {args.output}")
    print(f"total_questions={summary['total_questions']}")
    print(f"gradable_questions={summary['gradable_questions']}")
    print(f"blocked_questions={summary['blocked_questions']}")
    print(f"correct_count={summary['correct_count']}")
    print(f"incorrect_count={summary['incorrect_count']}")
    print(f"score={summary['score']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
