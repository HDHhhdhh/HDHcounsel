#!/usr/bin/env python
"""Mathpix adapter for subjective crop OCR experiments.

Default mode is dry-run. Network calls are only made when --allow-network is
provided. Credentials are read only from MATHPIX_APP_ID and MATHPIX_APP_KEY.
"""

from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


MATHPIX_TEXT_ENDPOINT = "https://api.mathpix.com/v3/text"
DEFAULT_QUESTIONS = "1,2,3,4,5"


def parse_questions(raw: str) -> list[int]:
    questions: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        try:
            question = int(piece)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid question number: {piece}") from exc
        if question < 1:
            raise argparse.ArgumentTypeError(f"question number must be >= 1: {piece}")
        questions.append(question)
    if not questions:
        raise argparse.ArgumentTypeError("at least one question is required")
    return questions


def crop_path(crop_dir: Path, question: int) -> Path:
    return crop_dir / f"q{question:03d}.png"


def data_uri(path: Path) -> str:
    mime_type = mimetypes.guess_type(str(path))[0] or "image/png"
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime_type};base64,{encoded}"


def mathpix_payload(path: Path) -> dict[str, Any]:
    return {
        "src": data_uri(path),
        "formats": ["text", "latex_styled", "data"],
        "data_options": {
            "include_asciimath": True,
            "include_latex": True,
        },
    }


def compact_raw(raw: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "text",
        "latex_styled",
        "latex_simplified",
        "confidence",
        "confidence_rate",
        "error",
        "error_info",
    ]
    compact = {key: raw.get(key) for key in keys if key in raw}
    data = raw.get("data")
    if isinstance(data, list):
        compact["data_count"] = len(data)
        compact["data_preview"] = data[:3]
    return compact


def cleanup_recognized(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text.startswith("$$") and text.endswith("$$") and len(text) >= 4:
        text = text[2:-2].strip()
    if text.startswith("$") and text.endswith("$") and len(text) >= 2:
        text = text[1:-1].strip()
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return lines[0] if lines else text


def choose_recognized(raw: dict[str, Any]) -> tuple[str, list[str]]:
    warnings: list[str] = []
    for key in ("text", "latex_styled", "latex_simplified", "latex"):
        value = cleanup_recognized(raw.get(key))
        if value:
            if key != "text":
                warnings.append(f"recognized_from_{key}")
            return value, warnings
    warnings.append("empty_mathpix_text")
    return "", warnings


def call_mathpix(path: Path, *, app_id: str, app_key: str, timeout: float) -> dict[str, Any]:
    body = json.dumps(mathpix_payload(path)).encode("utf-8")
    request = urllib.request.Request(
        MATHPIX_TEXT_ENDPOINT,
        data=body,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "app_id": app_id,
            "app_key": app_key,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310 - explicit opt-in CLI.
        return json.loads(response.read().decode("utf-8"))


def dry_run_item(question: int, path: Path) -> dict[str, Any]:
    warnings = ["dry_run_no_network_call"]
    if not path.exists():
        warnings.append("crop_file_missing")
    return {
        "question": question,
        "cropPath": str(path),
        "recognized": None,
        "final": None,
        "status": "dry_run" if path.exists() else "missing_crop",
        "confidence": None,
        "warnings": warnings,
        "raw": {},
    }


def network_item(question: int, path: Path, *, app_id: str, app_key: str, timeout: float) -> dict[str, Any]:
    if not path.exists():
        return {
            "question": question,
            "cropPath": str(path),
            "recognized": None,
            "final": None,
            "status": "missing_crop",
            "confidence": None,
            "warnings": ["crop_file_missing"],
            "raw": {},
        }
    try:
        raw = call_mathpix(path, app_id=app_id, app_key=app_key, timeout=timeout)
    except urllib.error.HTTPError as exc:
        message = exc.read().decode("utf-8", errors="replace")
        return {
            "question": question,
            "cropPath": str(path),
            "recognized": None,
            "final": None,
            "status": "failed",
            "confidence": None,
            "warnings": [f"mathpix_http_error:{exc.code}", message[:300]],
            "raw": {},
        }
    except (urllib.error.URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
        return {
            "question": question,
            "cropPath": str(path),
            "recognized": None,
            "final": None,
            "status": "failed",
            "confidence": None,
            "warnings": [f"mathpix_request_failed:{exc}"],
            "raw": {},
        }

    recognized, warnings = choose_recognized(raw)
    confidence = raw.get("confidence")
    status = "recognized" if recognized else "needs_review"
    return {
        "question": question,
        "cropPath": str(path),
        "recognized": recognized or None,
        "final": recognized or None,
        "status": status,
        "confidence": confidence if isinstance(confidence, (int, float)) else None,
        "warnings": warnings,
        "raw": compact_raw(raw),
    }


def build_result(args: argparse.Namespace) -> dict[str, Any]:
    crop_dir = Path(args.crop_dir)
    selected = parse_questions(args.questions)
    if len(selected) > args.limit:
        selected = selected[: args.limit]
        truncated = True
    else:
        truncated = False

    dry_run = bool(args.dry_run or not args.allow_network)
    warnings: list[str] = []
    if dry_run:
        warnings.append("dry_run_no_network_call")
    if truncated:
        warnings.append(f"question_list_truncated_to_limit:{args.limit}")

    app_id = ""
    app_key = ""
    if not dry_run:
        app_id = os.environ.get("MATHPIX_APP_ID", "")
        app_key = os.environ.get("MATHPIX_APP_KEY", "")
        if not app_id or not app_key:
            raise RuntimeError("MATHPIX_APP_ID and MATHPIX_APP_KEY environment variables are required with --allow-network")

    items: list[dict[str, Any]] = []
    for question in selected:
        path = crop_path(crop_dir, question)
        if dry_run:
            items.append(dry_run_item(question, path))
        else:
            items.append(network_item(question, path, app_id=app_id, app_key=app_key, timeout=float(args.timeout)))

    failed = any(item["status"] in {"failed", "missing_crop"} for item in items)
    return {
        "ok": not failed,
        "mode": "subjective_handwriting_recognition",
        "engine": args.engine_name,
        "dry_run": dry_run,
        "network_allowed": bool(args.allow_network),
        "endpoint": MATHPIX_TEXT_ENDPOINT if not dry_run else None,
        "items": items,
        "warnings": warnings,
        "policy": {
            "student_flow": "review_auto_recognition_then_fix_only_problem_items",
            "manual_first_entry": False,
            "auto_grading_connected": False,
            "max_default_limit": 5,
            "credentials_source": "environment_variables_only",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a limited Mathpix OCR experiment for subjective answer crops.")
    parser.add_argument("--crop-dir", required=True, help="Directory containing q001.png, q002.png, ...")
    parser.add_argument("--questions", default=DEFAULT_QUESTIONS, help="Comma-separated question numbers, e.g. 1,2,3,4,5.")
    parser.add_argument("--out", required=True, help="Output OCR result JSON path.")
    parser.add_argument("--engine-name", default="mathpix", help="Engine name stored in the output JSON.")
    parser.add_argument("--allow-network", action="store_true", help="Actually call Mathpix. Without this, dry-run is used.")
    parser.add_argument("--dry-run", action="store_true", help="Force dry-run mode with no network calls.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum crop count to process. Default: 5.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Mathpix request timeout in seconds. Default: 30.")
    args = parser.parse_args()
    if args.limit < 1:
        parser.error("--limit must be >= 1")
    return args


def main() -> int:
    args = parse_args()
    try:
        result = build_result(args)
    except RuntimeError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"dry_run={result['dry_run']}")
    print(f"network_allowed={result['network_allowed']}")
    print(f"items={len(result['items'])}")
    for item in result["items"]:
        print(f"Q{int(item['question']):03d} {item['status']} {item['cropPath']}")
    if result["warnings"]:
        print("warnings=" + ",".join(result["warnings"]))
    return 0 if result["ok"] or result["dry_run"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
