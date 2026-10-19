#!/usr/bin/env python
"""Dry-run matcher for Drive unit-test problem/answer PDFs.

The script is offline-only. It does not call Google Drive, does not touch PDFs,
and does not modify the counseling app. Feed it a Drive listing exported as
JSON/CSV/TXT and a tests-config.json snapshot, then inspect the console report.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

CURRICULUM_ALIASES = {
    "공통수학1": "공수1",
    "공수1": "공수1",
    "공통수학2": "공수2",
    "공수2": "공수2",
    "대수": "대수",
    "미적분1": "미적1",
    "미적1": "미적1",
    "미적분2": "미적2",
    "미적2": "미적2",
    "확률과 통계": "확통",
    "확통": "확통",
    "기하": "기하",
}

ROUND_FOLDER_RE = re.compile(r"^(1|2|3)$")
LEVEL_RE = re.compile(r"(?:Lv|lv)\.?\s*([0-9]+)")
PDF_RE = re.compile(r"\.pdf$", re.IGNORECASE)
SEQ_RE = re.compile(r"^\s*0*(\d{1,3})\s*[.]\s*(.+?)\s*\.pdf\s*$", re.IGNORECASE)
ANSWER_MARKERS = ("해설", "정답", "답지")
ROUND_LABEL_RE = re.compile(r"(?:^|[\s_])([123])\s*(?:차|회차)(?:$|[\s_.-])")


@dataclass
class CatalogRow:
    test_id: str
    category: str
    curriculum: str
    name: str
    problems: int | None
    sequence: int | None
    level: str | None
    normalized_key: str


@dataclass
class DriveFile:
    title: str
    url: str
    mime_type: str
    path: str
    curriculum: str | None
    level: str | None
    round_id: str | None
    sequence: int | None
    test_name: str | None
    is_answer_pdf: bool
    is_problem_pdf: bool


@dataclass
class MatchRow:
    catalog: CatalogRow
    round_id: str
    status: str
    problem_candidates: list[DriveFile]
    answer_candidates: list[DriveFile]
    notes: list[str]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Inspect Drive unit-test PDF listings and match them to tests-config."
    )
    parser.add_argument("--catalog", default="tests-config.json", help="Path to tests-config.json")
    parser.add_argument(
        "--drive-list",
        help="Drive listing file: JSON, CSV, or TXT. No Drive API calls are made.",
    )
    parser.add_argument(
        "--write-report",
        action="store_true",
        help="Write reports/drive_unit_pdf_inspection_YYYYMMDD_HHMMSS.txt",
    )
    return parser.parse_args()


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def normalize_text(value: Any) -> str:
    text = str(value or "").strip().lower()
    text = text.replace("_", " ")
    text = re.sub(r"\s+", "", text)
    return text


def normalize_unit_name(value: Any) -> str:
    text = str(value or "")
    text = PDF_RE.sub("", text)
    text = re.sub(r"^\s*0*\d{1,3}\s*[.]\s*", "", text)
    text = re.sub(r"\s*-\s*(해설|정답|답지).*?$", "", text)
    text = re.sub(r"(?:Lv|lv)\.?\s*[0-9]+", "", text)
    text = re.sub(r"(?:^|[\s_])[123]\s*(?:차|회차)(?:$|[\s_.-])", " ", text)
    for marker in ANSWER_MARKERS:
        text = text.replace(marker, " ")
    return normalize_text(text)


def normalize_level(value: Any) -> str | None:
    text = str(value or "")
    match = LEVEL_RE.search(text)
    if not match:
        return None
    return f"Lv.{match.group(1)}"


def normalize_curriculum(value: Any) -> str | None:
    text = str(value or "")
    for alias, canonical in CURRICULUM_ALIASES.items():
        if alias in text:
            return canonical
    return None


def infer_sequence_from_name(name: str) -> int | None:
    match = re.search(r"(?:^|_)(\d{1,3})(?:_|$)", name or "")
    if match:
        return int(match.group(1))
    return None


def flatten_catalog(config: dict[str, Any]) -> list[CatalogRow]:
    rows: list[CatalogRow] = []
    categories = config.get("categories") if isinstance(config, dict) else {}
    if not isinstance(categories, dict):
        return rows

    for category, category_data in categories.items():
        if category != "UNIT" or not isinstance(category_data, dict):
            continue
        for test in category_data.get("tests") or []:
            if not isinstance(test, dict):
                continue
            name = str(test.get("name") or "").strip()
            curriculum = str(test.get("curriculum") or "").strip()
            level = normalize_level(name)
            sequence = infer_sequence_from_name(str(test.get("id") or ""))
            key = normalize_text(f"{curriculum} {name}")
            problems = None
            try:
                problems = int(test.get("problems"))
            except (TypeError, ValueError):
                pass
            rows.append(
                CatalogRow(
                    test_id=str(test.get("id") or ""),
                    category=category,
                    curriculum=curriculum,
                    name=name,
                    problems=problems,
                    sequence=sequence,
                    level=level,
                    normalized_key=key,
                )
            )
    return rows


def collect_json_records(obj: Any, inherited_path: str = "") -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    if isinstance(obj, dict):
        if "files" in obj and isinstance(obj["files"], list):
            for item in obj["files"]:
                records.extend(collect_json_records(item, inherited_path))
            return records
        title = obj.get("title") or obj.get("name") or obj.get("display_title")
        if title:
            item = dict(obj)
            if inherited_path and not item.get("path"):
                item["path"] = inherited_path
            records.append(item)
        for key in ("children", "items"):
            if isinstance(obj.get(key), list):
                next_path = inherited_path
                if title:
                    next_path = join_path(inherited_path, str(title))
                for child in obj[key]:
                    records.extend(collect_json_records(child, next_path))
    elif isinstance(obj, list):
        for item in obj:
            records.extend(collect_json_records(item, inherited_path))
    return records


def join_path(*parts: str) -> str:
    clean = [str(part).strip("/\\ ") for part in parts if str(part or "").strip("/\\ ")]
    return "/".join(clean)


def load_drive_listing(path: Path) -> list[dict[str, Any]]:
    suffix = path.suffix.lower()
    if suffix == ".json":
        return collect_json_records(read_json(path))
    if suffix == ".csv":
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            return list(csv.DictReader(f))

    records: list[dict[str, Any]] = []
    for raw_line in path.read_text(encoding="utf-8-sig", errors="replace").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = re.split(r"\t+|\s{2,}", line)
        if len(parts) >= 2 and parts[-1].startswith("http"):
            title_or_path = " ".join(parts[:-1]).strip()
            records.append({"title": Path(title_or_path).name, "path": title_or_path, "url": parts[-1]})
        else:
            records.append({"title": Path(line).name, "path": line})
    return records


def parse_pdf_title(title: str) -> tuple[int | None, str | None, str | None, bool]:
    if not PDF_RE.search(title or ""):
        return None, None, None, False
    match = SEQ_RE.match(title)
    if not match:
        return None, None, normalize_level(title), any(marker in title for marker in ANSWER_MARKERS)

    sequence = int(match.group(1))
    body = match.group(2).strip()
    is_answer = any(marker in body for marker in ANSWER_MARKERS)
    body = re.sub(r"\s*-\s*(해설|정답|답지).*?$", "", body).strip()
    body = re.sub(r"(?:^|[\s_])[123]\s*(?:차|회차)(?:$|[\s_.-])", " ", body).strip()
    level = normalize_level(body)
    name = body.replace("_", " ")
    name = re.sub(r"\s+", " ", name).strip()
    return sequence, name, level, is_answer


def infer_round(path: str, title: str) -> str | None:
    parts = [part.strip() for part in re.split(r"[/\\]", path or "") if part.strip()]
    for part in reversed(parts[:-1]):
        if ROUND_FOLDER_RE.match(part):
            return part
    match = ROUND_LABEL_RE.search(title or "")
    if match:
        return match.group(1)
    return None


def normalize_drive_file(record: dict[str, Any]) -> DriveFile | None:
    title = str(record.get("title") or record.get("name") or record.get("display_title") or "").strip()
    path = str(record.get("path") or record.get("full_path") or title).strip()
    url = str(record.get("url") or record.get("webViewLink") or record.get("display_url") or "").strip()
    mime_type = str(record.get("mime_type") or record.get("mimeType") or "").strip()
    if not title or not PDF_RE.search(title):
        return None

    sequence, parsed_name, parsed_level, title_says_answer = parse_pdf_title(title)
    path_says_answer = any(part in ANSWER_MARKERS for part in re.split(r"[/\\]", path))
    is_answer = title_says_answer or path_says_answer
    curriculum = normalize_curriculum(path) or normalize_curriculum(title)
    level = parsed_level or normalize_level(path)
    round_id = infer_round(path, title)
    if round_id is None:
        round_id = "1"

    return DriveFile(
        title=title,
        url=url,
        mime_type=mime_type,
        path=path,
        curriculum=curriculum,
        level=level,
        round_id=round_id,
        sequence=sequence,
        test_name=parsed_name,
        is_answer_pdf=is_answer,
        is_problem_pdf=not is_answer,
    )


def catalog_candidates(catalog: list[CatalogRow], drive_file: DriveFile) -> list[CatalogRow]:
    if not drive_file.test_name:
        return []
    drive_name_key = normalize_unit_name(drive_file.test_name)
    by_name = [row for row in catalog if normalize_unit_name(row.name) == drive_name_key]
    if drive_file.curriculum:
        by_name = [row for row in by_name if row.curriculum == drive_file.curriculum]
    if drive_file.level:
        by_name = [row for row in by_name if row.level == drive_file.level]
    return by_name


def build_matches(catalog: list[CatalogRow], files: list[DriveFile]) -> list[MatchRow]:
    by_catalog_round_problem: dict[tuple[str, str], list[DriveFile]] = defaultdict(list)
    by_catalog_round_answer: dict[tuple[str, str], list[DriveFile]] = defaultdict(list)

    for file in files:
        candidates = catalog_candidates(catalog, file)
        for row in candidates:
            round_id = file.round_id or "?"
            key = (row.test_id, round_id)
            if file.is_answer_pdf:
                by_catalog_round_answer[key].append(file)
            else:
                by_catalog_round_problem[key].append(file)

    catalog_by_id = {row.test_id: row for row in catalog}
    keys = set(by_catalog_round_problem) | set(by_catalog_round_answer)
    matches: list[MatchRow] = []
    for test_id, round_id in sorted(keys):
        row = catalog_by_id.get(test_id)
        if not row:
            continue
        problem_candidates = by_catalog_round_problem.get((test_id, round_id), [])
        answer_candidates = by_catalog_round_answer.get((test_id, round_id), [])
        notes: list[str] = []
        if len(problem_candidates) == 1 and len(answer_candidates) == 1:
            status = "matched"
        elif not problem_candidates and answer_candidates:
            status = "missing_problem_pdf"
        elif problem_candidates and not answer_candidates:
            status = "missing_answer_pdf"
        elif len(problem_candidates) > 1 or len(answer_candidates) > 1:
            status = "ambiguous"
        else:
            status = "missing"
        if problem_candidates:
            notes.append("qr_source=problem_pdf_last_page")
        matches.append(MatchRow(row, round_id, status, problem_candidates, answer_candidates, notes))
    return matches


def build_report(catalog_path: Path, drive_list_path: Path | None) -> str:
    lines: list[str] = []
    lines.append("Drive Unit PDF Mapping Inspection")
    lines.append(f"Generated at: {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("Mode: dry-run; no Drive API calls; no file writes unless --write-report is used.")
    lines.append("")
    lines.append("Input")
    lines.append("=====")
    lines.append(f"catalog: {catalog_path} {'FOUND' if catalog_path.exists() else 'MISSING'}")
    lines.append(f"drive-list: {drive_list_path or '(not provided)'}")

    if not catalog_path.exists():
        lines.append("ERROR: catalog file missing")
        return "\n".join(lines) + "\n"

    catalog = flatten_catalog(read_json(catalog_path))
    lines.append("")
    lines.append("Catalog")
    lines.append("=======")
    lines.append(f"UNIT tests: {len(catalog)}")
    for curriculum, count in sorted(Counter(row.curriculum for row in catalog).items()):
        lines.append(f"- {curriculum}: {count}")

    if not drive_list_path:
        lines.append("")
        lines.append("Drive Listing")
        lines.append("=============")
        lines.append("No --drive-list provided. Provide JSON/CSV/TXT exported from Drive folder listings.")
        lines.append("Expected fields: title/name, url, path/full_path, mime_type/mimeType.")
        return "\n".join(lines) + "\n"

    if not drive_list_path.exists():
        lines.append(f"ERROR: drive-list file missing: {drive_list_path}")
        return "\n".join(lines) + "\n"

    raw_records = load_drive_listing(drive_list_path)
    files = [parsed for record in raw_records if (parsed := normalize_drive_file(record))]

    lines.append("")
    lines.append("Drive Listing")
    lines.append("=============")
    lines.append(f"raw records: {len(raw_records)}")
    lines.append(f"pdf records: {len(files)}")
    lines.append(f"problem PDFs: {sum(1 for item in files if item.is_problem_pdf)}")
    lines.append(f"answer PDFs: {sum(1 for item in files if item.is_answer_pdf)}")
    lines.append("by curriculum:")
    for curriculum, count in sorted(Counter(item.curriculum or '(unknown)' for item in files).items()):
        lines.append(f"- {curriculum}: {count}")
    lines.append("by round:")
    for round_id, count in sorted(Counter(item.round_id or '(unknown)' for item in files).items()):
        lines.append(f"- {round_id}: {count}")

    unmatched_files: list[DriveFile] = []
    for file in files:
        if not catalog_candidates(catalog, file):
            unmatched_files.append(file)

    matches = build_matches(catalog, files)
    status_counts = Counter(match.status for match in matches)

    lines.append("")
    lines.append("Mapping Summary")
    lines.append("===============")
    for status, count in sorted(status_counts.items()):
        lines.append(f"- {status}: {count}")
    lines.append(f"- unmatched PDF files: {len(unmatched_files)}")

    lines.append("")
    lines.append("Sample Matches")
    lines.append("==============")
    for match in matches[:20]:
        problem = match.problem_candidates[0].title if match.problem_candidates else "-"
        answer = match.answer_candidates[0].title if match.answer_candidates else "-"
        lines.append(
            f"- {match.status} | {match.catalog.test_id} | round={match.round_id} | "
            f"problem={problem} | answer={answer}"
        )

    if unmatched_files:
        lines.append("")
        lines.append("Unmatched PDF Samples")
        lines.append("=====================")
        for file in unmatched_files[:30]:
            lines.append(f"- {file.title} | path={file.path}")

    lines.append("")
    lines.append("Next Steps")
    lines.append("==========")
    lines.append("- Use problem_pdf_url as the QR source because QR is on the last page of the problem PDF.")
    lines.append("- Keep answer_pdf_url separate for fast-answer extraction from 해설 PDFs.")
    lines.append("- Add PDF last-page QR extraction only after mapping is stable.")
    return "\n".join(lines) + "\n"


def write_report(report: str, cwd: Path) -> Path:
    reports = cwd / "reports"
    reports.mkdir(parents=True, exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = reports / f"drive_unit_pdf_inspection_{stamp}.txt"
    path.write_text(report, encoding="utf-8")
    return path


def main() -> int:
    args = parse_args()
    catalog_path = Path(args.catalog).expanduser().resolve()
    drive_list_path = Path(args.drive_list).expanduser().resolve() if args.drive_list else None
    report = build_report(catalog_path, drive_list_path)
    print(report, end="")
    if args.write_report:
        path = write_report(report, Path.cwd())
        print(f"\nReport written: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
