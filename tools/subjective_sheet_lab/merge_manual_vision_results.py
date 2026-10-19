#!/usr/bin/env python
"""Merge manual Vision OCR result JSON parts into one evaluation-ready JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def item_question(item: dict[str, Any], fallback: int) -> int:
    try:
        return int(item.get("question") or fallback)
    except (TypeError, ValueError):
        return fallback


def normalize_item(item: dict[str, Any], question: int) -> dict[str, Any]:
    recognized = item.get("recognized")
    final = item.get("final", recognized)
    status = item.get("status")
    if not status:
        status = "recognized" if recognized not in (None, "") else "needs_review"
    warnings = item.get("warnings") or []
    if isinstance(warnings, str):
        warnings = [warnings]
    return {
        "question": question,
        "cropPath": item.get("cropPath") or f"q{question:03d}.png",
        "recognized": recognized,
        "final": final,
        "status": status,
        "confidence": item.get("confidence"),
        "warnings": warnings,
    }


def merge_parts(paths: list[Path], engine: str) -> dict[str, Any]:
    items_by_question: dict[int, dict[str, Any]] = {}
    warnings: list[str] = []
    part_summaries: list[dict[str, Any]] = []
    ok = True

    for path in paths:
        data = load_json(path)
        ok = ok and bool(data.get("ok", True))
        part_items = [item for item in data.get("items") or [] if isinstance(item, dict)]
        part_summaries.append(
            {
                "path": str(path),
                "engine": data.get("engine"),
                "ok": bool(data.get("ok", True)),
                "items": len(part_items),
            }
        )
        for part_warning in data.get("warnings") or []:
            warnings.append(f"{path.name}:{part_warning}")
        for index, item in enumerate(part_items, start=1):
            question = item_question(item, index)
            normalized = normalize_item(item, question)
            if question in items_by_question:
                warnings.append(f"duplicate_question:{question}:kept_first:ignored_from:{path.name}")
                continue
            items_by_question[question] = normalized

    items = [items_by_question[question] for question in sorted(items_by_question)]
    return {
        "ok": ok,
        "mode": "subjective_handwriting_recognition",
        "engine": engine,
        "items": items,
        "warnings": warnings,
        "source_parts": part_summaries,
        "policy": {
            "student_flow": "review_auto_recognition_then_fix_only_problem_items",
            "manual_first_entry": False,
            "auto_grading_connected": False,
            "manual_web_ui_only": True,
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Merge manual Vision OCR JSON parts by question number.")
    parser.add_argument("--part", nargs="+", required=True, help="One or more manual Vision result JSON files.")
    parser.add_argument("--out", required=True, help="Output merged JSON path.")
    parser.add_argument("--engine", default="manual_vision_merged", help="Engine name for the merged result.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result = merge_parts([Path(path) for path in args.part], str(args.engine))
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"items={len(result['items'])}")
    if result["warnings"]:
        print("warnings=" + ";".join(result["warnings"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
