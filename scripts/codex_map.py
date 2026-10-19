from __future__ import annotations

import argparse
import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
FILE_MAP = [
    (
        "app.py",
        "Streamlit UI/main flow",
        "Large file. Use topic searches and read narrow line ranges instead of scanning it end to end.",
    ),
    (
        "counsel_modules/log_csv_utils.py",
        "CSV/Docs save result classification and log CSV helpers",
        "Use for CSV-to-Google-Docs status rules and retry classification.",
    ),
    (
        "counsel_modules/text_utils.py",
        "summary normalize/validate helpers",
        "Use for [오늘 확인할 것], 상담 참고사항, runtime noise, clipboard/Docs text policy.",
    ),
    (
        "counsel_modules/local_consumed_admin_notes.py",
        "ADMIN consumed registry filtering",
        "Do not print or modify data/local_consumed_admin_notes.json during mapping.",
    ),
    (
        "counsel_modules/admin_utils.py",
        "ADMIN student row extraction and candidate label helpers",
        "Use for admin SID/candidate display helpers before changing app.py.",
    ),
    (
        "counsel_modules/google_docs_utils.py",
        "Google Docs URL/doc ID and append result helpers",
        "Do not run live Google Docs POST from mapping or verification.",
    ),
    (
        "scripts/check_app_health.py",
        "health check",
        "Read-only operational checks; use --fast for quick Codex verification.",
    ),
    (
        "scripts/check_release_ready.ps1",
        "full release check",
        "Full syntax/health/import/normalize/registry check; does not build ZIPs or publish.",
    ),
    (
        "scripts/check_quick.ps1",
        "quick check",
        "Fast default verification: health --fast, import contracts, app/module py_compile.",
    ),
    (
        "scripts/check_normalize_summary.py",
        "summary/admin/CSV regression tests",
        "Golden regression checks; use when text policy or export behavior changes.",
    ),
    (
        "scripts/make_sebin_update_zip.ps1",
        "update zip",
        "Do not run unless the user explicitly requests ZIP creation.",
    ),
    (
        "scripts/publish_sebin_update.ps1",
        "sebin update publish",
        "Do not run unless the user explicitly requests publish.",
    ),
]
DEFAULT_FILES = [
    "app.py",
    "counsel_modules/text_utils.py",
    "counsel_modules/log_csv_utils.py",
    "counsel_modules/admin_utils.py",
    "counsel_modules/google_docs_utils.py",
    "counsel_modules/local_consumed_admin_notes.py",
    "scripts/check_normalize_summary.py",
    "scripts/check_app_health.py",
    "scripts/check_import_contracts.py",
]


def iter_symbols(path: Path) -> list[tuple[str, str, int, int]]:
    try:
        source = path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        source = path.read_text(encoding="utf-8", errors="replace")
    tree = ast.parse(source, filename=str(path))
    rows: list[tuple[str, str, int, int]] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            kind = "class" if isinstance(node, ast.ClassDef) else "def"
            end_line = int(getattr(node, "end_lineno", node.lineno))
            rows.append((kind, node.name, int(node.lineno), end_line))
    return rows


def matches_text(value: str, queries: list[str]) -> bool:
    if not queries:
        return True
    lowered = value.lower()
    return all(query.lower() in lowered for query in queries)


def print_file_map(queries: list[str]) -> list[str]:
    matched_files: list[str] = []
    print("# File map")
    for relative, role, note in FILE_MAP:
        haystack = f"{relative} {role} {note}"
        if not matches_text(haystack, queries):
            continue
        print(f"- {relative}: {role}")
        print(f"  note: {note}")
        matched_files.append(relative)
    if queries and not matched_files:
        print("- No file-map entries matched the query; showing symbol matches below if any.")
    return matched_files


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Print a small counsel-note file/symbol map for Codex without importing the Streamlit app."
    )
    parser.add_argument("query", nargs="*", help="Filter symbols by substring, e.g. summary save")
    parser.add_argument(
        "--files",
        nargs="+",
        default=DEFAULT_FILES,
        help="Relative files to scan. Defaults to the heavy counsel-note files.",
    )
    parser.add_argument("--map-only", action="store_true", help="Only print the file role map.")
    parser.add_argument("--symbols-only", action="store_true", help="Only print symbols.")
    args = parser.parse_args()

    if not args.symbols_only:
        print_file_map(args.query)
        if args.map_only:
            return 0

    total = 0
    if not args.map_only:
        print("\n# Symbols")
    for relative in args.files:
        path = ROOT / relative
        if not path.exists():
            continue
        rows = [row for row in iter_symbols(path) if matches_text(row[1], args.query)]
        if not rows:
            continue
        print(f"\n# {relative}")
        for kind, name, start, end in rows:
            span = f"{start}" if start == end else f"{start}-{end}"
            print(f"{span:>10}  {kind:<5} {name}")
            total += 1

    if total == 0:
        print("No matching symbols found.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
