#!/usr/bin/env python
"""Batch-evaluate subjective OCR stress test cases.

This script reads manually produced Vision OCR JSON files, writes per-case
evaluation reports, and creates batch summary files. No network calls are made.
"""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

from evaluate_ocr_result import (
    build_rows,
    build_summary,
    load_answer_key,
    load_expected,
    load_json,
    specs_from_expected,
    write_csv as write_eval_csv,
    write_json as write_eval_json,
    write_markdown as write_eval_markdown,
)


CASE_SUMMARY_FIELDS = [
    "case_id",
    "status",
    "ocr_result",
    "eval_json",
    "total",
    "exact_match_count",
    "normalized_match_count",
    "accepted_match_count",
    "needs_review_count",
    "missing_count",
    "review_required_count",
    "exact_but_review_required_count",
    "accepted_but_review_required_count",
    "safe_auto_grade_count",
    "accuracy_exact",
    "accuracy_normalized_or_exact",
    "accuracy_accepted_or_exact",
    "safe_auto_grade_rate",
    "review_required_rate",
]

REVIEW_REQUIRED_FIELDS = [
    "case_id",
    "question",
    "match_status",
    "expected",
    "accepted_answers",
    "recognized",
    "final",
    "review_reasons",
    "warnings",
    "cropPath",
    "eval_path",
]

PENDING_FIELDS = ["case_id", "case_dir", "expected_ocr_result"]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch evaluate subjective OCR stress test cases.")
    parser.add_argument("--batch-root", required=True, help="Batch stress test root containing case folders.")
    parser.add_argument("--expected", help="Expected answers text file, one answer per line.")
    parser.add_argument("--answer-key", help="Answer key JSON with accepted answers and review policy.")
    parser.add_argument(
        "--out-summary-dir",
        help="Output summary directory. Default: <batch-root>/summary.",
    )
    parser.add_argument(
        "--include-pending",
        action="store_true",
        help="Include pending cases in summary CSV/Markdown case tables.",
    )
    parser.add_argument(
        "--pattern",
        default="*/vision_result/ocr_result_manual_vision_20.json",
        help='Glob pattern under --batch-root. Default: "*/vision_result/ocr_result_manual_vision_20.json".',
    )
    args = parser.parse_args()
    if bool(args.expected) == bool(args.answer_key):
        parser.error("exactly one of --expected or --answer-key is required")
    return args


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def escape_md(value: Any) -> str:
    return str(value if value is not None else "").replace("\n", "<br>").replace("|", "\\|")


def case_dirs(batch_root: Path, out_summary_dir: Path) -> list[Path]:
    summary_resolved = out_summary_dir.resolve()
    dirs: list[Path] = []
    for path in sorted(batch_root.iterdir(), key=lambda item: item.name.lower()):
        if not path.is_dir():
            continue
        try:
            if path.resolve() == summary_resolved:
                continue
        except OSError:
            pass
        if path.name.startswith("."):
            continue
        dirs.append(path)
    return dirs


def case_id_for_result(batch_root: Path, result_path: Path) -> str:
    try:
        relative = result_path.relative_to(batch_root)
        if relative.parts:
            return relative.parts[0]
    except ValueError:
        pass
    if result_path.parent.name == "vision_result":
        return result_path.parent.parent.name
    return result_path.stem


def find_results(batch_root: Path, pattern: str) -> dict[str, Path]:
    results: dict[str, Path] = {}
    for path in sorted(batch_root.glob(pattern), key=lambda item: str(item).lower()):
        if not path.is_file():
            continue
        results[case_id_for_result(batch_root, path)] = path
    return results


def summary_row(case_id: str, ocr_result_path: Path, eval_json_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    total = int(summary.get("total") or 0)
    safe_auto_grade = int(summary.get("safe_auto_grade_count") or 0)
    review_required = int(summary.get("review_required_count") or 0)
    return {
        "case_id": case_id,
        "status": "evaluated",
        "ocr_result": str(ocr_result_path),
        "eval_json": str(eval_json_path),
        "total": total,
        "exact_match_count": int(summary.get("exact_match_count") or 0),
        "normalized_match_count": int(summary.get("normalized_match_count") or 0),
        "accepted_match_count": int(summary.get("accepted_match_count") or 0),
        "needs_review_count": int(summary.get("needs_review_count") or 0),
        "missing_count": int(summary.get("missing_count") or 0),
        "review_required_count": review_required,
        "exact_but_review_required_count": int(summary.get("exact_but_review_required_count") or 0),
        "accepted_but_review_required_count": int(summary.get("accepted_but_review_required_count") or 0),
        "safe_auto_grade_count": safe_auto_grade,
        "accuracy_exact": float(summary.get("accuracy_exact") or 0.0),
        "accuracy_normalized_or_exact": float(summary.get("accuracy_normalized_or_exact") or 0.0),
        "accuracy_accepted_or_exact": float(summary.get("accuracy_accepted_or_exact") or 0.0),
        "safe_auto_grade_rate": round(safe_auto_grade / total, 6) if total else 0.0,
        "review_required_rate": round(review_required / total, 6) if total else 0.0,
    }


def evaluate_case(case_id: str, result_path: Path, answer_specs: dict[int, dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    case_dir = result_path.parent.parent if result_path.parent.name == "vision_result" else result_path.parent
    eval_dir = case_dir / "eval"
    eval_json = eval_dir / "eval.json"
    eval_csv = eval_dir / "eval.csv"
    eval_md = eval_dir / "eval.md"

    ocr_result = load_json(result_path)
    rows = build_rows(ocr_result, answer_specs)
    summary = build_summary(rows)
    write_eval_json(eval_json, ocr_result, rows, summary)
    write_eval_csv(eval_csv, rows)
    write_eval_markdown(eval_md, ocr_result, rows, summary)

    row = summary_row(case_id, result_path, eval_json, summary)
    review_rows: list[dict[str, Any]] = []
    for item in rows:
        if not item.get("review_required") and item.get("match_status") not in {"needs_review", "missing"}:
            continue
        review_rows.append(
            {
                "case_id": case_id,
                "question": item.get("question"),
                "match_status": item.get("match_status"),
                "expected": item.get("expected"),
                "accepted_answers": item.get("accepted_answers"),
                "recognized": item.get("recognized"),
                "final": item.get("final"),
                "review_reasons": item.get("review_reasons"),
                "warnings": item.get("warnings"),
                "cropPath": item.get("cropPath"),
                "eval_path": str(eval_json),
            }
        )
    return row, review_rows


def build_overall_summary(
    *,
    batch_root: Path,
    input_kind: str,
    input_path: Path,
    case_rows: list[dict[str, Any]],
    pending_rows: list[dict[str, Any]],
    review_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    total_items = sum(int(row.get("total") or 0) for row in case_rows)
    exact = sum(int(row.get("exact_match_count") or 0) for row in case_rows)
    normalized = sum(int(row.get("normalized_match_count") or 0) for row in case_rows)
    accepted = sum(int(row.get("accepted_match_count") or 0) for row in case_rows)
    needs_review = sum(int(row.get("needs_review_count") or 0) for row in case_rows)
    missing = sum(int(row.get("missing_count") or 0) for row in case_rows)
    review_required = sum(int(row.get("review_required_count") or 0) for row in case_rows)
    exact_but_review = sum(int(row.get("exact_but_review_required_count") or 0) for row in case_rows)
    accepted_but_review = sum(int(row.get("accepted_but_review_required_count") or 0) for row in case_rows)
    safe_auto_grade = sum(int(row.get("safe_auto_grade_count") or 0) for row in case_rows)

    question_counter: Counter[int] = Counter()
    for row in review_rows:
        try:
            question_counter[int(row.get("question"))] += 1
        except (TypeError, ValueError):
            pass

    matched = exact + normalized + accepted
    return {
        "ok": True,
        "mode": "subjective_stress_test_batch_evaluation",
        "batch_root": str(batch_root),
        "input_kind": input_kind,
        "input_path": str(input_path),
        "case_count": len(case_rows) + len(pending_rows),
        "evaluated_case_count": len(case_rows),
        "pending_case_count": len(pending_rows),
        "total_items": total_items,
        "exact_match": exact,
        "normalized_match": normalized,
        "accepted_match": accepted,
        "needs_review": needs_review,
        "missing": missing,
        "review_required_count": review_required,
        "exact_but_review_required_count": exact_but_review,
        "accepted_but_review_required_count": accepted_but_review,
        "safe_auto_grade_count": safe_auto_grade,
        "aggregate_accuracy": round(matched / total_items, 6) if total_items else 0.0,
        "safe_auto_grade_rate": round(safe_auto_grade / total_items, 6) if total_items else 0.0,
        "review_required_rate": round(review_required / total_items, 6) if total_items else 0.0,
        "worst_questions": [
            {"question": question, "review_required_or_missing_count": count}
            for question, count in question_counter.most_common()
        ],
        "pending_cases": pending_rows,
        "cases": case_rows,
        "review_required_items_count": len(review_rows),
        "external_api_calls": False,
    }


def write_summary_markdown(
    path: Path,
    summary: dict[str, Any],
    case_rows: list[dict[str, Any]],
    pending_rows: list[dict[str, Any]],
    include_pending: bool,
) -> None:
    lines = [
        "# Subjective OCR Batch Evaluation Summary",
        "",
        "This report is for developer/admin validation only. It does not call external APIs, submit answers, or grade students.",
        "",
        "## Overall",
        "",
        f"- Case count: {summary['case_count']}",
        f"- Evaluated cases: {summary['evaluated_case_count']}",
        f"- Pending cases: {summary['pending_case_count']}",
        f"- Total items: {summary['total_items']}",
        f"- Exact match: {summary['exact_match']}",
        f"- Accepted match: {summary['accepted_match']}",
        f"- Needs review: {summary['needs_review']}",
        f"- Missing: {summary['missing']}",
        f"- Review required: {summary['review_required_count']}",
        f"- Safe auto grade candidates: {summary['safe_auto_grade_count']}",
        f"- Aggregate accuracy: {summary['aggregate_accuracy']:.2%}",
        f"- Safe auto grade rate: {summary['safe_auto_grade_rate']:.2%}",
        f"- Review required rate: {summary['review_required_rate']:.2%}",
        "",
        "## Evaluated Cases",
        "",
        "| Case | Total | Exact | Accepted | Needs Review | Missing | Review Required | Safe Auto Grade | Accuracy |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for row in case_rows:
        lines.append(
            f"| {escape_md(row['case_id'])} | {row['total']} | {row['exact_match_count']} | "
            f"{row['accepted_match_count']} | {row['needs_review_count']} | {row['missing_count']} | "
            f"{row['review_required_count']} | {row['safe_auto_grade_count']} | "
            f"{float(row['accuracy_accepted_or_exact']):.2%} |"
        )

    if include_pending or pending_rows:
        lines.extend(["", "## Pending Cases", ""])
        if pending_rows:
            for row in pending_rows:
                lines.append(
                    f"- `{escape_md(row['case_id'])}`: missing `{escape_md(row['expected_ocr_result'])}`"
                )
        else:
            lines.append("- None")

    lines.extend(["", "## Worst Questions", ""])
    if summary["worst_questions"]:
        for item in summary["worst_questions"]:
            lines.append(f"- Q{int(item['question']):03d}: {item['review_required_or_missing_count']} review-required/missing cases")
    else:
        lines.append("- None")
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    args = parse_args()
    batch_root = Path(args.batch_root)
    if not batch_root.exists():
        raise FileNotFoundError(f"missing --batch-root: {batch_root}")
    out_summary_dir = Path(args.out_summary_dir) if args.out_summary_dir else batch_root / "summary"

    if args.answer_key:
        answer_specs = load_answer_key(Path(args.answer_key))
        input_kind = "answer_key"
        input_path = Path(args.answer_key)
    else:
        answer_specs = specs_from_expected(load_expected(Path(args.expected)))
        input_kind = "expected"
        input_path = Path(args.expected)

    result_by_case = find_results(batch_root, str(args.pattern))
    direct_cases = {path.name: path for path in case_dirs(batch_root, out_summary_dir)}
    all_case_ids = sorted(set(direct_cases) | set(result_by_case), key=str.lower)

    case_rows: list[dict[str, Any]] = []
    review_rows: list[dict[str, Any]] = []
    pending_rows: list[dict[str, Any]] = []

    for case_id in all_case_ids:
        result_path = result_by_case.get(case_id)
        if result_path is None:
            case_dir = direct_cases.get(case_id, batch_root / case_id)
            expected = case_dir / "vision_result" / "ocr_result_manual_vision_20.json"
            pending_rows.append(
                {
                    "case_id": case_id,
                    "case_dir": str(case_dir),
                    "expected_ocr_result": str(expected),
                }
            )
            continue
        print(f"Evaluating {case_id}: {result_path}")
        case_row, case_review_rows = evaluate_case(case_id, result_path, answer_specs)
        case_rows.append(case_row)
        review_rows.extend(case_review_rows)

    summary = build_overall_summary(
        batch_root=batch_root,
        input_kind=input_kind,
        input_path=input_path,
        case_rows=case_rows,
        pending_rows=pending_rows,
        review_rows=review_rows,
    )

    write_json(out_summary_dir / "summary.json", summary)
    summary_csv_rows = list(case_rows)
    if args.include_pending:
        for row in pending_rows:
            summary_csv_rows.append(
                {
                    "case_id": row["case_id"],
                    "status": "pending",
                    "ocr_result": row["expected_ocr_result"],
                }
            )
    write_csv(out_summary_dir / "summary.csv", summary_csv_rows, CASE_SUMMARY_FIELDS)
    write_summary_markdown(out_summary_dir / "summary.md", summary, case_rows, pending_rows, bool(args.include_pending))
    write_csv(out_summary_dir / "review_required_items.csv", review_rows, REVIEW_REQUIRED_FIELDS)
    write_json(out_summary_dir / "pending_cases.json", pending_rows)
    write_csv(out_summary_dir / "pending_cases.csv", pending_rows, PENDING_FIELDS)

    print(f"Wrote {out_summary_dir / 'summary.json'}")
    print(f"Wrote {out_summary_dir / 'summary.csv'}")
    print(f"Wrote {out_summary_dir / 'summary.md'}")
    print(f"Wrote {out_summary_dir / 'review_required_items.csv'}")
    print(f"Wrote {out_summary_dir / 'pending_cases.json'}")
    print(f"Wrote {out_summary_dir / 'pending_cases.csv'}")
    print(f"case_count={summary['case_count']}")
    print(f"evaluated_case_count={summary['evaluated_case_count']}")
    print(f"pending_case_count={summary['pending_case_count']}")
    print(f"total_items={summary['total_items']}")
    print(f"review_required_count={summary['review_required_count']}")
    print("external_api_calls=False")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
