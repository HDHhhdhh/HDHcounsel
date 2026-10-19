#!/usr/bin/env python
"""Inspect external admin test-page snapshots without touching live systems.

This script is intentionally offline-only: it reads local HTML/JS/JSON
snapshots, prints a validation report, and performs no API requests.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import html
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


EXPECTED_FILES = [
    "tests-config.json",
    "tests-stats-30.json",
    "tests-stats-90.json",
    "tests-stats-365.json",
    "tests_page.html",
    "tests.js",
    "tests_js_api_hints.txt",
]

STATS_FILES = [
    "tests-stats-30.json",
    "tests-stats-90.json",
    "tests-stats-365.json",
]

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
VALID_ANSWER_VALUES = {"1", "2", "3", "4", "5"}
QR_PATTERNS = ["qr", "qrcode", "answerqr", "answer_qr", "?듭?qr", "qrfile"]


@dataclass
class TestRow:
    category: str
    category_label: str
    test_id: str
    curriculum: str
    name: str
    problems: int | None
    has_answer_key: bool
    answer_rounds: list[str]
    answer_lengths: dict[str, int]
    source_schema: str
    answers_by_round: dict[str, list[Any]] = field(default_factory=dict)


@dataclass
class StatMatch:
    stats_file: str
    category: str
    curriculum: str
    name: str
    status: str
    candidates: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Dry-run inspector for external admin test snapshots."
    )
    parser.add_argument(
        "--snapshot-dir",
        default=".",
        help="Directory containing tests-config/tests-stats/html/js snapshots.",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write the console report to reports/test_snapshot_inspection_*.txt.",
    )
    return parser.parse_args()


def read_text(path: Path) -> str | None:
    if not path.exists():
        return None
    return path.read_text(encoding="utf-8-sig", errors="replace")


def read_json(path: Path) -> tuple[Any | None, str | None]:
    text = read_text(path)
    if text is None:
        return None, "missing"
    try:
        return json.loads(text), None
    except json.JSONDecodeError as exc:
        return None, f"invalid JSON: {exc}"


def is_non_empty_answer(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, list):
        return any(str(item).strip() for item in value)
    if isinstance(value, dict):
        return any(is_non_empty_answer(v) for v in value.values())
    return bool(str(value).strip())


def answer_array(value: Any) -> list[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            return []
        if re.search(r"[\s,]", stripped):
            return [part for part in re.split(r"[\s,]+", stripped) if part]
        return list(stripped)
    return [value]


def detect_source_schema(test: dict[str, Any]) -> str:
    answer_key_present = (
        ("answerKey" in test and test.get("answerKey") is not None)
        or ("answers" in test and test.get("answers") is not None)
    )
    answer_keys_present = "answerKeys" in test and test.get("answerKeys") is not None
    if answer_key_present and answer_keys_present:
        return "both"
    if answer_keys_present:
        return "answerKeys"
    if answer_key_present:
        return "answerKey"
    return "none"


def normalize_answers(test: dict[str, Any]) -> tuple[dict[str, list[Any]], str, bool]:
    answers_by_round: dict[str, list[Any]] = {}
    answer_keys = test.get("answerKeys")
    answer_key = test.get("answerKey", test.get("answers"))

    if isinstance(answer_keys, dict):
        for round_id in ("1", "2", "3"):
            answers_by_round[round_id] = answer_array(answer_keys.get(round_id))

    if not any(is_non_empty_answer(v) for v in answers_by_round.values()):
        legacy = answer_array(answer_key)
        if legacy:
            answers_by_round["1"] = legacy

    schema = detect_source_schema(test)
    has_answer_key = any(is_non_empty_answer(v) for v in answers_by_round.values())
    return answers_by_round, schema, has_answer_key


def safe_int(value: Any) -> int | None:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed


def flatten_catalog(config: dict[str, Any]) -> list[TestRow]:
    rows: list[TestRow] = []
    categories = config.get("categories") if isinstance(config, dict) else {}
    if not isinstance(categories, dict):
        return rows

    for category, category_data in categories.items():
        if not isinstance(category_data, dict):
            continue
        label = str(category_data.get("label") or "")
        tests = category_data.get("tests")
        if not isinstance(tests, list):
            continue

        for test in tests:
            if not isinstance(test, dict):
                continue
            answers, schema, has_answer_key = normalize_answers(test)
            answer_lengths = {
                round_id: len(values)
                for round_id, values in answers.items()
                if values or round_id in ("1", "2", "3")
            }
            answer_rounds = [
                round_id for round_id, values in answers.items() if is_non_empty_answer(values)
            ]
            rows.append(
                TestRow(
                    category=str(category),
                    category_label=label,
                    test_id=str(test.get("id") or ""),
                    curriculum=str(test.get("curriculum") or ""),
                    name=str(test.get("name") or ""),
                    problems=safe_int(test.get("problems")),
                    has_answer_key=has_answer_key,
                    answer_rounds=answer_rounds,
                    answer_lengths=answer_lengths,
                    source_schema=schema,
                    answers_by_round=answers,
                )
            )
    return rows


def canon(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = html.unescape(text)
    text = re.sub(r"\s+", "", text)
    return text


def inspect_html(html_text: str | None) -> list[str]:
    if html_text is None:
        return ["tests_page.html: missing"]
    checks = {
        "/js/tests.js module load": bool(
            re.search(r"<script[^>]+src=[\"']/js/tests\.js[\"'][^>]*type=[\"']module[\"']", html_text)
            or re.search(r"<script[^>]+type=[\"']module[\"'][^>]*src=[\"']/js/tests\.js[\"']", html_text)
        ),
        "cfgAnswers": "cfgAnswers" in html_text,
        "btnSaveTest": "btnSaveTest" in html_text,
        "btnDeleteTest": "btnDeleteTest" in html_text,
        "btnReloadStats": "btnReloadStats" in html_text,
    }
    return [f"{name}: {'yes' if ok else 'no'}" for name, ok in checks.items()]


def inspect_js(js_text: str | None) -> tuple[list[dict[str, str]], list[str], list[str]]:
    if js_text is None:
        return [], ["tests.js: missing"], []

    endpoints: list[dict[str, str]] = []
    risks: list[str] = []
    qr_hits: list[str] = []

    for match in re.finditer(r"fetch(?:JSONSafe)?\(\s*([`\"'])(?P<url>.*?)(?<!\\)\1", js_text):
        raw_url = match.group("url")
        line = js_text.count("\n", 0, match.start()) + 1
        snippet_start = match.start()
        snippet_end = min(len(js_text), match.end() + 180)
        snippet = js_text[snippet_start:snippet_end]
        method_match = re.search(r"method\s*:\s*[\"'](?P<method>[A-Za-z]+)[\"']", snippet)
        method = method_match.group("method").upper() if method_match else "GET"
        endpoints.append({"method": method, "endpoint": raw_url, "line": str(line)})

    for method in WRITE_METHODS:
        for match in re.finditer(rf"\b{method}\b", js_text, flags=re.IGNORECASE):
            line = js_text.count("\n", 0, match.start()) + 1
            risks.append(f"{method} string at tests.js:{line}")

    lowered = js_text.lower()
    for pattern in QR_PATTERNS:
        idx = lowered.find(pattern.lower())
        if idx >= 0:
            line = js_text.count("\n", 0, idx) + 1
            qr_hits.append(f"{pattern} at tests.js:{line}")

    return endpoints, sorted(set(risks)), sorted(set(qr_hits))


def validate_catalog(rows: list[TestRow]) -> list[str]:
    warnings: list[str] = []
    id_groups: dict[str, list[TestRow]] = defaultdict(list)
    for row in rows:
        id_groups[row.test_id].append(row)

    for test_id, group in sorted(id_groups.items()):
        if not test_id:
            continue
        if len(group) > 1:
            names = ", ".join(f"{item.category}:{item.name}" for item in group)
            warnings.append(f"duplicate test_id '{test_id}': {names}")

    for row in rows:
        label = f"{row.category}/{row.test_id or '(missing id)'}/{row.name or '(missing name)'}"
        if not row.test_id:
            warnings.append(f"missing test_id: {label}")
        if not row.name:
            warnings.append(f"missing name: {label}")
        if not row.curriculum:
            warnings.append(f"missing curriculum: {label}")
        if row.problems is None or row.problems < 1:
            warnings.append(f"invalid problems: {label} -> {row.problems}")

        if row.source_schema == "both":
            warnings.append(f"mixed answerKey/answerKeys: {label}")

        if row.problems and row.problems > 0:
            for round_id, answers in sorted(row.answers_by_round.items()):
                if not is_non_empty_answer(answers):
                    continue
                if len(answers) != row.problems:
                    warnings.append(
                        f"answer length mismatch: {label} round {round_id} "
                        f"len={len(answers)} problems={row.problems}"
                    )

        for round_id, answers in sorted(row.answers_by_round.items()):
            for index, answer in enumerate(answers, start=1):
                answer_text = str(answer).strip()
                if not answer_text:
                    continue
                if answer_text not in VALID_ANSWER_VALUES:
                    warnings.append(
                        f"answer out of 1-5 range: {label} round {round_id} "
                        f"#{index}='{answer_text}'"
                    )
    return warnings


def extract_stat_rows(stats: dict[str, Any], stats_file: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for row in stats.get("final_rows") or []:
        if isinstance(row, dict):
            out.append(
                {
                    "stats_file": stats_file,
                    "category": "FINAL",
                    "curriculum": str(row.get("curriculum") or ""),
                    "name": str(row.get("test_name") or ""),
                }
            )
    for row in stats.get("hell_rows") or []:
        if isinstance(row, dict):
            out.append(
                {
                    "stats_file": stats_file,
                    "category": "HELL",
                    "curriculum": str(row.get("curriculum") or ""),
                    "name": str(row.get("test_name") or ""),
                }
            )
    for row in stats.get("unit_rows") or []:
        if isinstance(row, dict):
            out.append(
                {
                    "stats_file": stats_file,
                    "category": "UNIT",
                    "curriculum": str(row.get("curriculum") or ""),
                    "name": str(row.get("unit_name") or ""),
                }
            )
    return out


def match_stats(rows: list[TestRow], stats_docs: dict[str, dict[str, Any]]) -> list[StatMatch]:
    matches: list[StatMatch] = []
    for stats_file, stats in stats_docs.items():
        for stat_row in extract_stat_rows(stats, stats_file):
            same_name = [
                row
                for row in rows
                if canon(row.name) == canon(stat_row["name"])
            ]
            same_category = [
                row for row in same_name if row.category == stat_row["category"]
            ]
            same_curriculum = [
                row
                for row in same_category
                if not stat_row["curriculum"] or row.curriculum == stat_row["curriculum"]
            ]

            if len(same_curriculum) == 1:
                status = "matched"
                candidates = [same_curriculum[0].test_id]
            elif len(same_curriculum) > 1:
                status = "ambiguous"
                candidates = [row.test_id for row in same_curriculum]
            elif same_name:
                status = "conflict"
                candidates = [
                    f"{row.category}/{row.curriculum}/{row.test_id}" for row in same_name
                ]
            else:
                status = "missing"
                candidates = []

            matches.append(
                StatMatch(
                    stats_file=stat_row["stats_file"],
                    category=stat_row["category"],
                    curriculum=stat_row["curriculum"],
                    name=stat_row["name"],
                    status=status,
                    candidates=candidates,
                )
            )
    return matches


def add_section(lines: list[str], title: str) -> None:
    lines.append("")
    lines.append("=" * len(title))
    lines.append(title)
    lines.append("=" * len(title))


def build_report(snapshot_dir: Path) -> str:
    lines: list[str] = []
    lines.append("Test Snapshot Inspection Report")
    lines.append(f"Snapshot dir: {snapshot_dir}")
    lines.append(f"Generated at: {_dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Mode: dry-run; no API calls; no writes unless --write-report is used.")

    add_section(lines, "Input Files")
    file_status: dict[str, Path] = {}
    for filename in EXPECTED_FILES:
        path = snapshot_dir / filename
        file_status[filename] = path
        status = "FOUND" if path.exists() else "MISSING"
        lines.append(f"- {filename}: {status} ({path})")

    html_text = read_text(file_status["tests_page.html"])
    js_text = read_text(file_status["tests.js"])
    config, config_error = read_json(file_status["tests-config.json"])

    add_section(lines, "HTML/JS Structure")
    lines.extend(f"- {item}" for item in inspect_html(html_text))
    endpoints, method_risks, qr_hits = inspect_js(js_text)

    add_section(lines, "tests.js API Candidates")
    if endpoints:
        for item in endpoints:
            lines.append(f"- {item['method']} {item['endpoint']} (tests.js:{item['line']})")
    else:
        lines.append("- No fetch endpoint candidates found.")

    lines.append("")
    lines.append("Write-method risk strings:")
    if method_risks:
        for risk in method_risks:
            lines.append(f"- {risk}")
    else:
        lines.append("- none")

    lines.append("")
    lines.append("QR-related strings:")
    if qr_hits:
        for hit in qr_hits:
            lines.append(f"- {hit}")
    else:
        lines.append("- none")

    add_section(lines, "Catalog Summary")
    if config_error:
        lines.append(f"- Cannot read tests-config.json: {config_error}")
        rows: list[TestRow] = []
    else:
        rows = flatten_catalog(config)
        lines.append(f"- total tests: {len(rows)}")
        by_category = Counter(row.category for row in rows)
        by_curriculum = Counter(row.curriculum or "(missing)" for row in rows)
        lines.append("- by category:")
        for category, count in sorted(by_category.items()):
            lines.append(f"  - {category}: {count}")
        lines.append("- by curriculum:")
        for curriculum, count in sorted(by_curriculum.items()):
            lines.append(f"  - {curriculum}: {count}")

    add_section(lines, "Answer Registration Summary")
    if rows:
        schema_counts = Counter(row.source_schema for row in rows)
        registered_counts = Counter("registered" if row.has_answer_key else "missing" for row in rows)
        lines.append("- source_schema:")
        for schema, count in sorted(schema_counts.items()):
            lines.append(f"  - {schema}: {count}")
        lines.append("- registration:")
        for key, count in sorted(registered_counts.items()):
            lines.append(f"  - {key}: {count}")
        lines.append("- answer length groups:")
        length_groups = Counter(
            f"{row.category} rounds={','.join(row.answer_rounds) or '-'} "
            f"lengths={row.answer_lengths or '{}'}"
            for row in rows
        )
        for label, count in sorted(length_groups.items()):
            lines.append(f"  - {label}: {count}")
    else:
        lines.append("- skipped; no catalog rows")

    add_section(lines, "Validation Warnings")
    warnings = validate_catalog(rows)
    if warnings:
        for warning in warnings:
            lines.append(f"- {warning}")
    else:
        lines.append("- none")

    add_section(lines, "Stats Matching Summary")
    stats_docs: dict[str, dict[str, Any]] = {}
    for filename in STATS_FILES:
        stats, error = read_json(file_status[filename])
        if error:
            lines.append(f"- {filename}: warning: {error}")
            continue
        if not isinstance(stats, dict):
            lines.append(f"- {filename}: warning: JSON root is not an object")
            continue
        stats_docs[filename] = stats
        summary_keys = ",".join((stats.get("summary") or {}).keys())
        unit_rows = len(stats.get("unit_rows") or [])
        final_rows = len(stats.get("final_rows") or [])
        hell_rows = len(stats.get("hell_rows") or [])
        range_obj = stats.get("range") or {}
        lines.append(
            f"- {filename}: range={range_obj.get('start')}..{range_obj.get('end')} "
            f"summary={summary_keys or '-'} unit_rows={unit_rows} "
            f"final_rows={final_rows} hell_rows={hell_rows}"
        )

    stat_matches = match_stats(rows, stats_docs) if rows else []
    match_counts = Counter(match.status for match in stat_matches)
    lines.append("")
    lines.append("Match counts:")
    for status in ("matched", "missing", "ambiguous", "conflict"):
        lines.append(f"- {status}: {match_counts.get(status, 0)}")

    details = [match for match in stat_matches if match.status != "matched"]
    if details:
        lines.append("")
        lines.append("Non-matched details:")
        for match in details:
            candidate_text = ", ".join(match.candidates) if match.candidates else "-"
            lines.append(
                f"- {match.stats_file} {match.category}/{match.curriculum}/"
                f"{match.name}: {match.status}; candidates={candidate_text}"
            )

    add_section(lines, "Next Steps")
    lines.append("- Keep the first implementation offline: no API calls and no admin writes.")
    lines.append("- Treat answerKeys['1'|'2'|'3'] as the canonical answer schema.")
    lines.append("- Treat answerKey as a legacy round-1 compatibility field.")
    lines.append("- Collect QR filename samples before designing QR matching.")
    lines.append("- Collect tests-records GET samples before designing grading/records output.")
    lines.append("- Defer PDF OCR/answer extraction to a later tool.")

    return "\n".join(lines).strip() + "\n"


def write_report(report: str, cwd: Path) -> Path:
    report_dir = cwd / "reports"
    report_dir.mkdir(parents=True, exist_ok=True)
    stamp = _dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = report_dir / f"test_snapshot_inspection_{stamp}.txt"
    path.write_text(report, encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    snapshot_dir = Path(args.snapshot_dir).expanduser().resolve()
    report = build_report(snapshot_dir)
    print(report, end="")

    if args.write_report:
        out_path = write_report(report, Path.cwd())
        print(f"\nReport written: {out_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

