#!/usr/bin/env python
"""Summarize subjective OCR stress test evaluation JSON files."""

from __future__ import annotations

import argparse
import csv
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


SUMMARY_FIELDS = [
    "case_id",
    "eval_path",
    "total",
    "exact_match_count",
    "normalized_match_count",
    "needs_review_count",
    "missing_count",
    "accuracy_exact",
    "accuracy_normalized_or_exact",
    "review_rate",
]


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def find_eval_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for path in root.glob("*/eval/*.json"):
        if path.parts and "summary" in path.parts:
            continue
        files.append(path)
    return sorted(files)


def case_id_for(eval_root: Path, path: Path) -> str:
    try:
        relative = path.relative_to(eval_root)
        return relative.parts[0]
    except ValueError:
        return path.parent.parent.name


def summarize_file(eval_root: Path, path: Path) -> tuple[dict[str, Any], Counter[int]]:
    data = load_json(path)
    summary = data.get("summary") or {}
    row = {
        "case_id": case_id_for(eval_root, path),
        "eval_path": str(path),
        "total": int(summary.get("total") or 0),
        "exact_match_count": int(summary.get("exact_match_count") or 0),
        "normalized_match_count": int(summary.get("normalized_match_count") or 0),
        "needs_review_count": int(summary.get("needs_review_count") or 0),
        "missing_count": int(summary.get("missing_count") or 0),
        "accuracy_exact": float(summary.get("accuracy_exact") or 0.0),
        "accuracy_normalized_or_exact": float(summary.get("accuracy_normalized_or_exact") or 0.0),
        "review_rate": float(summary.get("review_rate") or 0.0),
    }
    risky_questions: Counter[int] = Counter()
    for item in data.get("items") or []:
        if not isinstance(item, dict):
            continue
        if item.get("match_status") in {"needs_review", "missing"}:
            try:
                risky_questions[int(item.get("question"))] += 1
            except (TypeError, ValueError):
                pass
    return row, risky_questions


def build_summary(eval_root: Path) -> dict[str, Any]:
    eval_files = find_eval_files(eval_root)
    rows: list[dict[str, Any]] = []
    question_counter: Counter[int] = Counter()
    for path in eval_files:
        row, risky = summarize_file(eval_root, path)
        rows.append(row)
        question_counter.update(risky)

    case_count = len(rows)
    total_items = sum(row["total"] for row in rows)
    total_exact = sum(row["exact_match_count"] for row in rows)
    total_normalized = sum(row["normalized_match_count"] for row in rows)
    total_needs_review = sum(row["needs_review_count"] for row in rows)
    total_missing = sum(row["missing_count"] for row in rows)
    matched = total_exact + total_normalized
    average_accuracy = sum(row["accuracy_normalized_or_exact"] for row in rows) / case_count if case_count else 0.0
    aggregate_accuracy = matched / total_items if total_items else 0.0
    worst_questions = [
        {"question": question, "needs_review_or_missing_count": count}
        for question, count in question_counter.most_common()
    ]
    return {
        "ok": True,
        "mode": "subjective_ocr_stress_test_summary",
        "eval_root": str(eval_root),
        "case_count": case_count,
        "total_items": total_items,
        "total_exact_match": total_exact,
        "total_normalized_match": total_normalized,
        "total_needs_review": total_needs_review,
        "total_missing": total_missing,
        "average_accuracy": round(average_accuracy, 6),
        "aggregate_accuracy": round(aggregate_accuracy, 6),
        "worst_questions": worst_questions,
        "cases": rows,
        "warnings": [] if rows else ["no_eval_json_files_found"],
    }


def write_json(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(path: Path, summary: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Subjective OCR Stress Test Summary",
        "",
        "This report is for developer/admin validation only. It is not student-facing and does not submit or grade answers.",
        "",
        "## Overall",
        "",
        f"- Case count: {summary['case_count']}",
        f"- Total items: {summary['total_items']}",
        f"- Average accuracy: {summary['average_accuracy']:.2%}",
        f"- Aggregate accuracy: {summary['aggregate_accuracy']:.2%}",
        f"- Total needs review: {summary['total_needs_review']}",
        f"- Total missing: {summary['total_missing']}",
        "",
    ]
    if summary["warnings"]:
        lines.extend(["## Warnings", ""])
        for warning in summary["warnings"]:
            lines.append(f"- {warning}")
        lines.append("")

    lines.extend(
        [
            "## Cases",
            "",
            "| Case | Total | Exact | Normalized | Needs Review | Missing | Accuracy | Review Rate |",
            "|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in summary["cases"]:
        lines.append(
            f"| {row['case_id']} | {row['total']} | {row['exact_match_count']} | "
            f"{row['normalized_match_count']} | {row['needs_review_count']} | {row['missing_count']} | "
            f"{row['accuracy_normalized_or_exact']:.2%} | {row['review_rate']:.2%} |"
        )
    lines.extend(["", "## Worst Questions", ""])
    if summary["worst_questions"]:
        for item in summary["worst_questions"]:
            lines.append(f"- Q{int(item['question']):03d}: {item['needs_review_or_missing_count']} review/missing cases")
    else:
        lines.append("- None")
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Summarize stress test eval JSON files.")
    parser.add_argument("--eval-root", required=True, help="Stress test root folder.")
    parser.add_argument("--out-md", required=True, help="Output summary Markdown path.")
    parser.add_argument("--out-json", required=True, help="Output summary JSON path.")
    parser.add_argument("--out-csv", required=True, help="Output summary CSV path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    summary = build_summary(Path(args.eval_root))
    write_json(Path(args.out_json), summary)
    write_csv(Path(args.out_csv), summary["cases"])
    write_markdown(Path(args.out_md), summary)
    print(f"Wrote {args.out_json}")
    print(f"Wrote {args.out_csv}")
    print(f"Wrote {args.out_md}")
    print(f"case_count={summary['case_count']}")
    print(f"total_items={summary['total_items']}")
    if summary["warnings"]:
        print("warnings=" + ",".join(summary["warnings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
