#!/usr/bin/env python
"""Evaluate subjective answer OCR/mock recognition output against expected answers."""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path
from typing import Any

from normalize_math_answer import normalize_math_answer


FIELDNAMES = [
    "question",
    "expected",
    "recognized",
    "final",
    "normalized_expected",
    "normalized_recognized",
    "match_status",
    "cropPath",
    "warnings",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_expected(path: Path) -> list[str]:
    return [line.rstrip("\n\r") for line in path.read_text(encoding="utf-8-sig").splitlines()]


def value_to_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value)


def item_question(item: dict[str, Any], index: int) -> int:
    try:
        return int(item.get("question") or index + 1)
    except (TypeError, ValueError):
        return index + 1


def status_for(expected: str, recognized: str, normalized_expected: str, normalized_recognized: str) -> str:
    if not recognized:
        return "missing"
    if recognized == expected:
        return "exact_match"
    if normalized_recognized and normalized_recognized == normalized_expected:
        return "normalized_match"
    return "needs_review"


def build_rows(ocr_result: dict[str, Any], expected_answers: list[str]) -> list[dict[str, Any]]:
    items_by_question: dict[int, dict[str, Any]] = {}
    for index, item in enumerate(ocr_result.get("items") or []):
        if isinstance(item, dict):
            items_by_question[item_question(item, index)] = item

    total = max(len(expected_answers), max(items_by_question.keys(), default=0))
    rows: list[dict[str, Any]] = []
    for question in range(1, total + 1):
        item = items_by_question.get(question, {})
        expected = expected_answers[question - 1] if question - 1 < len(expected_answers) else ""
        recognized = value_to_text(item.get("recognized"))
        final = value_to_text(item.get("final"))
        normalized_expected = normalize_math_answer(expected)
        normalized_recognized = normalize_math_answer(recognized)
        warnings = item.get("warnings") or []
        if isinstance(warnings, str):
            warning_text = warnings
        else:
            warning_text = ";".join(str(warning) for warning in warnings)
        rows.append(
            {
                "question": question,
                "expected": expected,
                "recognized": recognized,
                "final": final,
                "normalized_expected": normalized_expected,
                "normalized_recognized": normalized_recognized,
                "match_status": status_for(expected, recognized, normalized_expected, normalized_recognized),
                "cropPath": value_to_text(item.get("cropPath")),
                "warnings": warning_text,
            }
        )
    return rows


def build_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    total = len(rows)
    exact = sum(1 for row in rows if row["match_status"] == "exact_match")
    normalized = sum(1 for row in rows if row["match_status"] == "normalized_match")
    needs_review = sum(1 for row in rows if row["match_status"] == "needs_review")
    missing = sum(1 for row in rows if row["match_status"] == "missing")
    matched = exact + normalized
    return {
        "total": total,
        "exact_match_count": exact,
        "normalized_match_count": normalized,
        "needs_review_count": needs_review,
        "missing_count": missing,
        "accuracy_exact": round(exact / total, 6) if total else 0.0,
        "accuracy_normalized_or_exact": round(matched / total, 6) if total else 0.0,
        "review_rate": round((needs_review + missing) / total, 6) if total else 0.0,
    }


def write_json(path: Path, ocr_result: dict[str, Any], rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    payload = {
        "ok": True,
        "mode": "subjective_handwriting_ocr_evaluation",
        "engine": ocr_result.get("engine"),
        "test_id": ocr_result.get("test_id"),
        "test_name": ocr_result.get("test_name"),
        "summary": summary,
        "items": rows,
        "policy": {
            "student_flow": "review_auto_recognition_then_fix_only_problem_items",
            "developer_report_only": True,
            "auto_grading_connected": False,
        },
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


def escape_md(value: Any) -> str:
    text = value_to_text(value).replace("\n", "<br>")
    return text.replace("|", "\\|")


def write_markdown(path: Path, ocr_result: dict[str, Any], rows: list[dict[str, Any]], summary: dict[str, Any]) -> None:
    review_rows = [row for row in rows if row["match_status"] in {"needs_review", "missing"}]
    lines = [
        "# Subjective OCR Evaluation Report",
        "",
        "This is a developer/admin evaluation report. It is not a student-facing screen and does not submit or grade answers.",
        "",
        "## Summary",
        "",
        f"- Engine: `{escape_md(ocr_result.get('engine'))}`",
        f"- Test ID: `{escape_md(ocr_result.get('test_id'))}`",
        f"- Total: {summary['total']}",
        f"- Exact match: {summary['exact_match_count']}",
        f"- Normalized match: {summary['normalized_match_count']}",
        f"- Needs review: {summary['needs_review_count']}",
        f"- Missing: {summary['missing_count']}",
        f"- Accuracy exact: {summary['accuracy_exact']:.2%}",
        f"- Accuracy normalized or exact: {summary['accuracy_normalized_or_exact']:.2%}",
        f"- Review rate: {summary['review_rate']:.2%}",
        "",
        "## Item Results",
        "",
        "| Q | Expected | Recognized | Final | Status | Crop | Warnings |",
        "|---:|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row["question"]),
                    escape_md(row["expected"]),
                    escape_md(row["recognized"]),
                    escape_md(row["final"]),
                    escape_md(row["match_status"]),
                    escape_md(row["cropPath"]),
                    escape_md(row["warnings"]),
                ]
            )
            + " |"
        )
    lines.extend(["", "## Needs Review Or Missing", ""])
    if review_rows:
        for row in review_rows:
            lines.append(
                f"- Q{int(row['question']):03d}: expected `{escape_md(row['expected'])}`, "
                f"recognized `{escape_md(row['recognized'])}`, status `{row['match_status']}`, crop `{escape_md(row['cropPath'])}`"
            )
    else:
        lines.append("- None")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate OCR/mock recognition JSON against expected line-based answers.")
    parser.add_argument("--ocr-result", required=True, help="OCR/mock result JSON path.")
    parser.add_argument("--expected", required=True, help="Expected answers text file, one answer per line.")
    parser.add_argument("--out-json", required=True, help="Output evaluation JSON path.")
    parser.add_argument("--out-csv", required=True, help="Output evaluation CSV path.")
    parser.add_argument("--out-md", required=True, help="Output evaluation Markdown report path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    ocr_result = load_json(Path(args.ocr_result))
    expected_answers = load_expected(Path(args.expected))
    rows = build_rows(ocr_result, expected_answers)
    summary = build_summary(rows)

    write_json(Path(args.out_json), ocr_result, rows, summary)
    write_csv(Path(args.out_csv), rows)
    write_markdown(Path(args.out_md), ocr_result, rows, summary)

    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_csv}")
    print(f"Wrote {args.out_md}")
    print(f"total={summary['total']}")
    print(f"exact_match={summary['exact_match_count']}")
    print(f"normalized_match={summary['normalized_match_count']}")
    print(f"needs_review={summary['needs_review_count']}")
    print(f"missing={summary['missing_count']}")
    print(f"accuracy_normalized_or_exact={summary['accuracy_normalized_or_exact']:.2%}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
