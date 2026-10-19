from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
DEFAULT_REGISTRY_PATH = ROOT_DIR / "data" / "local_consumed_admin_notes.json"


def check_registry(path: Path) -> tuple[bool, list[str], list[str]]:
    messages: list[str] = []
    warnings: list[str] = []

    if not path.exists():
        messages.append(f"SKIP consumed registry not found: {path}")
        return True, messages, warnings

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        messages.append(f"FAIL consumed registry JSON could not be read: {exc}")
        return False, messages, warnings

    if not isinstance(data, dict):
        messages.append("FAIL consumed registry root must be an object")
        return False, messages, warnings

    items = data.get("items")
    if not isinstance(items, list):
        messages.append("FAIL consumed registry items must be a list")
        return False, messages, warnings

    duplicate_count = 0
    missing_required: list[int] = []
    seen: set[tuple[str, str]] = set()
    for index, item in enumerate(items, start=1):
        if not isinstance(item, dict):
            missing_required.append(index)
            continue
        student_key = str(item.get("student_key") or "")
        note_hash = str(item.get("note_hash") or "")
        if not student_key or not note_hash:
            missing_required.append(index)
            continue
        key = (student_key, note_hash)
        if key in seen:
            duplicate_count += 1
        seen.add(key)

    messages.append(f"PASS consumed registry loaded: {path}")
    messages.append(f"items: {len(items)}")
    messages.append(f"duplicates: {duplicate_count}")
    if missing_required:
        messages.append(f"FAIL missing required fields in item indexes: {missing_required[:20]}")
        return False, messages, warnings
    if duplicate_count:
        warnings.append(f"WARN duplicate consumed entries: {duplicate_count}")
    return True, messages, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate local consumed ADMIN note registry.")
    parser.add_argument("--path", type=Path, default=DEFAULT_REGISTRY_PATH)
    args = parser.parse_args()

    ok, messages, warnings = check_registry(args.path)
    for message in messages:
        print(message)
    for warning in warnings:
        print(warning)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
