from __future__ import annotations

import argparse
import csv
import json
import re
import subprocess
import sys
from dataclasses import asdict, dataclass
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

REQUIRED_FILES = (
    "app.py",
    "run_app.bat",
    "run_app.ps1",
    "\uc138\ube48_\uc5c5\ub370\uc774\ud2b8_\ud655\uc778.bat",
    "publish_sebin_update.bat",
    "진단_패키지_생성.bat",
    "requirements.txt",
    "prompts/summary_ko.txt",
    "README_\uc138\ube48_\uc790\ub3d9\uc5c5\ub370\uc774\ud2b8.txt",
    "scripts/make_diagnostic_bundle.ps1",
    "scripts/publish_sebin_update.ps1",
    "scripts/sebin_check_and_apply_update.ps1",
    "scripts/check_release_ready.ps1",
    "scripts/check_import_contracts.py",
    "scripts/check_normalize_summary.py",
    "scripts/wait_for_streamlit_port.ps1",
    "scripts/google_apps_script_doPost.js",
)

URL_PATTERN = re.compile(r"^https://script\.google\.com/macros/s/.+/exec\s*$")


@dataclass
class HealthItem:
    status: str
    name: str
    description: str
    action: str = ""

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


def _item(status: str, name: str, description: str, action: str = "") -> HealthItem:
    return HealthItem(status=status, name=name, description=description, action=action)


def _read_csv_rows(path: Path) -> tuple[list[str], list[dict[str, str]]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = [dict(row) for row in reader]
    return fieldnames, rows


def check_required_files(root: Path) -> list[HealthItem]:
    results: list[HealthItem] = []
    missing = [relative for relative in REQUIRED_FILES if not (root / relative).exists()]
    module_dir = root / "counsel_modules"
    if not module_dir.is_dir():
        missing.append("counsel_modules/")
    if missing:
        results.append(
            _item(
                "FAIL",
                "required_files",
                f"missing {len(missing)} required path(s): {', '.join(missing[:8])}",
                "Restore the missing app files from the latest update package.",
            )
        )
    else:
        results.append(_item("PASS", "required_files", "all required files found"))
    return results


def check_build_info(root: Path) -> list[HealthItem]:
    path = root / "BUILD_INFO.json"
    if not path.exists():
        return [_item("WARN", "build_info", "BUILD_INFO.json missing", "App will show last update time as unknown.")]
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:
        return [_item("WARN", "build_info", f"could not parse BUILD_INFO.json: {exc}", "Regenerate the update package.")]
    if not isinstance(data, dict):
        return [_item("WARN", "build_info", "BUILD_INFO.json root is not an object", "Regenerate the update package.")]
    updated_at = str(data.get("last_updated_at") or "").strip()
    if not updated_at:
        return [_item("WARN", "build_info", "last_updated_at missing", "Regenerate the update package.")]
    channel = str(data.get("channel") or "").strip() or "-"
    return [_item("PASS", "build_info", f"last_updated_at: {updated_at}; channel: {channel}")]


def check_google_docs_map(root: Path) -> list[HealthItem]:
    path = root / "data" / "students" / "google_docs_map.csv"
    if not path.exists():
        return [
            _item(
                "WARN",
                "google_docs_map",
                "file missing; Google Docs save mapping is unavailable",
                "Add students through the app's Google Docs registration UI.",
            )
        ]
    try:
        fieldnames, rows = _read_csv_rows(path)
    except Exception as exc:
        return [_item("FAIL", "google_docs_map", f"could not read CSV: {exc}", "Check CSV encoding/format.")]

    columns = {name.strip() for name in fieldnames}
    failures: list[str] = []
    warnings: list[str] = []
    if "student_name" not in columns:
        failures.append("missing column student_name")
    if "doc_url" not in columns and "doc_id" not in columns:
        failures.append("missing doc_url/doc_id column")

    duplicate_names = 0
    missing_doc_ref = 0
    seen_names: set[str] = set()
    duplicated: set[str] = set()
    for row in rows:
        name = str(row.get("student_name") or "").strip()
        if name:
            key = re.sub(r"\s+", "", name).lower()
            if key in seen_names:
                duplicated.add(key)
            seen_names.add(key)
        if not str(row.get("doc_url") or "").strip() and not str(row.get("doc_id") or "").strip():
            missing_doc_ref += 1
    duplicate_names = len(duplicated)
    if duplicate_names:
        warnings.append(f"duplicate student_name count: {duplicate_names}")
    if missing_doc_ref:
        warnings.append(f"rows missing doc_url/doc_id: {missing_doc_ref}")

    if failures:
        return [_item("FAIL", "google_docs_map", "; ".join(failures), "Fix required columns in google_docs_map.csv.")]
    description = f"rows: {len(rows)}"
    if warnings:
        return [_item("WARN", "google_docs_map", description + "; " + "; ".join(warnings), "Review the mapping in the app.")]
    return [_item("PASS", "google_docs_map", description)]


def check_apps_script_url(root: Path) -> list[HealthItem]:
    path = root / "data" / "students" / "google_apps_script_webapp_url.txt"
    if not path.exists():
        return [_item("WARN", "apps_script_url", "file missing", "Set the Google Apps Script URL in the app.")]
    try:
        value = path.read_text(encoding="utf-8").strip()
    except Exception as exc:
        return [_item("WARN", "apps_script_url", f"could not read URL file: {exc}", "Check the settings file.")]
    if not value:
        return [_item("WARN", "apps_script_url", "URL file is empty", "Set the Google Apps Script URL in the app.")]
    if not URL_PATTERN.match(value):
        return [_item("WARN", "apps_script_url", "URL format looks unusual", "Confirm the deployed Apps Script web app URL.")]
    return [_item("PASS", "apps_script_url", "URL file exists and format looks valid")]


def check_admin_settings(root: Path) -> list[HealthItem]:
    results: list[HealthItem] = []
    base_url_path = root / "data" / "students" / "admin_api_base_url.txt"
    sid_map_path = root / "data" / "students" / "admin_sid_map.csv"
    if base_url_path.exists():
        results.append(_item("PASS", "admin_api_base_url", "file exists"))
    else:
        results.append(_item("WARN", "admin_api_base_url", "file missing; admin lookup may be unavailable"))
    if not sid_map_path.exists():
        results.append(_item("WARN", "admin_sid_map", "file missing; admin matching cache may be unavailable"))
        return results
    try:
        fieldnames, rows = _read_csv_rows(sid_map_path)
    except Exception as exc:
        results.append(_item("WARN", "admin_sid_map", f"could not read CSV: {exc}"))
        return results
    columns = {name.strip() for name in fieldnames}
    if {"student_name", "admin_sid"}.issubset(columns):
        results.append(_item("PASS", "admin_sid_map", f"rows: {len(rows)}"))
    else:
        results.append(_item("WARN", "admin_sid_map", "missing student_name/admin_sid column"))
    return results


def check_admin_candidate_field_support(root: Path) -> list[HealthItem]:
    app_path = root / "app.py"
    try:
        app_text = app_path.read_text(encoding="utf-8")
    except Exception as exc:
        return [_item("WARN", "admin_candidate_fields", f"could not inspect app.py: {exc}")]

    required_groups = {
        "day1~day5": [f"day{index}" for index in range(1, 6)],
        "visitTime1~visitTime5": [f"visitTime{index}" for index in range(1, 6)],
        "subCurriculum": ["subCurriculum"],
    }
    missing: list[str] = []
    for label, fields in required_groups.items():
        if not all(field in app_text for field in fields):
            missing.append(label)
    if missing:
        return [
            _item(
                "WARN",
                "admin_candidate_fields",
                "missing support marker(s): " + ", ".join(missing),
                "Update admin candidate matching fields if /api/students uses these columns.",
            )
        ]
    return [_item("PASS", "admin_candidate_fields", "day1~day5, visitTime1~5, subCurriculum supported")]


def check_ffmpeg(root: Path) -> list[HealthItem]:
    path = root / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if path.exists():
        return [_item("PASS", "ffmpeg", "found")]
    return [_item("FAIL", "ffmpeg", "missing; audio processing may fail", "Restore tools/ffmpeg/bin/ffmpeg.exe.")]


def check_consumed_registry(root: Path) -> list[HealthItem]:
    path = root / "data" / "local_consumed_admin_notes.json"
    if not path.exists():
        return [_item("PASS", "consumed_registry", "not found; app can create it when needed")]
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("registry root must be an object")
        items = data.get("items")
        if not isinstance(items, list):
            raise ValueError("items must be a list")
        return [_item("PASS", "consumed_registry", f"items: {len(items)}")]
    except Exception as exc:
        return [
            _item(
                "WARN",
                "consumed_registry",
                f"registry could not be read: {exc}",
                "The app should fail open, but reset the registry in developer diagnostics if needed.",
            )
        ]


def check_codex_cli(root: Path) -> list[HealthItem]:
    from counsel_modules.codex_runner import find_codex_executable

    executable = find_codex_executable()
    if executable is None:
        return [
            _item(
                "WARN",
                "codex_cli",
                "codex command not found in PATH",
                "Codex CLI 확인 필요: 정리본 생성 기능이 동작하지 않을 수 있습니다.",
            )
        ]
    codex_path = str(executable.path)
    try:
        completed = subprocess.run(
            [codex_path, "--version"],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=10,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [
            _item(
                "WARN",
                "codex_cli",
                "codex --version timed out",
                "Codex CLI 확인 필요: 정리본 생성 기능이 동작하지 않을 수 있습니다.",
            )
        ]
    except Exception as exc:
        return [
            _item(
                "WARN",
                "codex_cli",
                f"codex --version could not run: {exc}",
                "Codex CLI 확인 필요: 정리본 생성 기능이 동작하지 않을 수 있습니다.",
            )
        ]
    if completed.returncode != 0:
        detail_lines = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
        detail = detail_lines[0] if detail_lines else f"exit code {completed.returncode}"
        return [
            _item(
                "WARN",
                "codex_cli",
                f"codex --version failed: {detail}",
                "Codex CLI 확인 필요: 정리본 생성 기능이 동작하지 않을 수 있습니다.",
            )
        ]
    first_line = (completed.stdout or completed.stderr or "").strip().splitlines()[:1]
    detail = first_line[0] if first_line else "codex --version ok"
    return [_item("PASS", "codex_cli", detail)]


def run_python_script(root: Path, script_relative: str, label: str) -> HealthItem:
    script_path = root / script_relative
    if not script_path.exists():
        return _item("FAIL", label, "script missing", f"Restore {script_relative}.")
    try:
        completed = subprocess.run(
            [sys.executable, "-B", str(script_path)],
            cwd=str(root),
            text=True,
            capture_output=True,
            timeout=120,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return _item("FAIL", label, "timed out", "Run the script manually and inspect the error.")
    except Exception as exc:
        return _item("FAIL", label, f"could not run: {exc}", "Check the Python environment.")
    if completed.returncode == 0:
        first_line = (completed.stdout or "").splitlines()[:1]
        detail = first_line[0] if first_line else "OK"
        return _item("PASS", label, detail)
    detail_lines = (completed.stdout + "\n" + completed.stderr).strip().splitlines()
    detail = detail_lines[0] if detail_lines else f"exit code {completed.returncode}"
    return _item("FAIL", label, detail, f"Run {script_relative} for details.")


def run_health_checks(root: Path = ROOT_DIR, *, include_slow: bool = True) -> list[HealthItem]:
    root = Path(root)
    results: list[HealthItem] = []
    results.extend(check_required_files(root))
    results.extend(check_build_info(root))
    results.extend(check_google_docs_map(root))
    results.extend(check_apps_script_url(root))
    results.extend(check_admin_settings(root))
    results.extend(check_admin_candidate_field_support(root))
    results.extend(check_ffmpeg(root))
    results.extend(check_consumed_registry(root))
    results.extend(check_codex_cli(root))
    if include_slow:
        results.append(run_python_script(root, "scripts/check_import_contracts.py", "import_contracts"))
        results.append(run_python_script(root, "scripts/check_normalize_summary.py", "normalize_summary_golden"))
    return results


def summarize(results: list[HealthItem]) -> dict[str, int]:
    counts = {"PASS": 0, "WARN": 0, "FAIL": 0}
    for result in results:
        counts[result.status] = counts.get(result.status, 0) + 1
    return counts


def print_results(results: list[HealthItem]) -> None:
    for result in results:
        line = f"{result.status} {result.name}: {result.description}"
        if result.action:
            line += f" | action: {result.action}"
        print(line)
    counts = summarize(results)
    print(f"summary: PASS {counts.get('PASS', 0)} / WARN {counts.get('WARN', 0)} / FAIL {counts.get('FAIL', 0)}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Run counsel-note app health checks without writes or POSTs.")
    parser.add_argument("--root", type=Path, default=ROOT_DIR)
    parser.add_argument("--fast", action="store_true", help="Skip slower import/golden test subprocess checks.")
    args = parser.parse_args()

    results = run_health_checks(args.root, include_slow=not args.fast)
    print_results(results)
    return 1 if any(result.status == "FAIL" for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
