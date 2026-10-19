#!/usr/bin/env python
"""Batch-prepare subjective OCR stress test cases from a folder of photos.

For each jpg/jpeg/png input image, this script creates a stress test case,
copies the source image, crops answer boxes, creates enhanced crops, and builds
manual Vision contact sheets. No network calls are made.
"""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any


SCRIPT_DIR = Path(__file__).resolve().parent
IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Batch prepare subjective OCR stress test cases.")
    parser.add_argument("--input-dir", required=True, help="Folder containing jpg/jpeg/png answer sheet photos.")
    parser.add_argument("--layout", required=True, help="Subjective sheet layout JSON path.")
    parser.add_argument("--out-root", required=True, help="Output stress test batch root.")
    parser.add_argument("--case-prefix", default="", help="Optional prefix prepended to each case id.")
    parser.add_argument("--overwrite", action="store_true", help="Allow regenerating an existing case folder.")
    parser.add_argument(
        "--contact-mode",
        choices=["original", "enhanced", "original_and_enhanced"],
        default="original_and_enhanced",
        help="Contact sheet mode. Default: original_and_enhanced.",
    )
    parser.add_argument(
        "--questions-chunks",
        default="1-5,6-10,11-15,16-20",
        help='Comma-separated question chunks, e.g. "1-5,6-10,11-15,16-20".',
    )
    return parser.parse_args()


def safe_case_id(raw: str) -> str:
    cleaned = raw.strip()
    replacements = {
        "\\": "_",
        "/": "_",
        ":": "_",
        "*": "_",
        "?": "_",
        '"': "_",
        "<": "_",
        ">": "_",
        "|": "_",
        " ": "_",
    }
    for old, new in replacements.items():
        cleaned = cleaned.replace(old, new)
    cleaned = "_".join(part for part in cleaned.split("_") if part)
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError(f"invalid case id from {raw!r}")
    return cleaned


def discover_images(input_dir: Path) -> list[Path]:
    return [
        path
        for path in sorted(input_dir.iterdir(), key=lambda item: item.name.lower())
        if path.is_file() and path.suffix.lower() in IMAGE_SUFFIXES
    ]


def parse_question_numbers(raw: str) -> list[int]:
    numbers: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if "-" in piece:
            start_raw, end_raw = piece.split("-", 1)
            start = int(start_raw.strip())
            end = int(end_raw.strip())
            step = 1 if end >= start else -1
            numbers.extend(range(start, end + step, step))
        else:
            numbers.append(int(piece))
    if not numbers:
        raise ValueError(f"empty question chunk: {raw!r}")
    return numbers


def parse_chunks(raw: str) -> list[str]:
    chunks = [chunk.strip() for chunk in raw.split(",") if chunk.strip()]
    if not chunks:
        raise ValueError("--questions-chunks must contain at least one chunk")
    for chunk in chunks:
        parse_question_numbers(chunk)
    return chunks


def chunk_label(chunk: str) -> str:
    numbers = parse_question_numbers(chunk)
    return f"q{min(numbers):03d}_q{max(numbers):03d}"


def contact_filename(chunk: str, mode: str) -> str:
    suffix = "compare" if mode == "original_and_enhanced" else mode
    return f"vision_contact_{chunk_label(chunk)}_{suffix}.png"


def run_step(command: list[str]) -> dict[str, str | int]:
    print("RUN " + " ".join(command))
    completed = subprocess.run(command, text=True, capture_output=True, check=True)
    if completed.stdout:
        print(completed.stdout.strip())
    if completed.stderr:
        print(completed.stderr.strip())
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def count_question_pngs(path: Path) -> int:
    return len([item for item in path.glob("q*.png") if item.is_file()])


def ensure_case_dirs(case_dir: Path) -> dict[str, Path]:
    dirs = {
        "input": case_dir / "input",
        "crops": case_dir / "crops",
        "enhanced_crops": case_dir / "enhanced_crops",
        "contact": case_dir / "contact",
        "vision_result": case_dir / "vision_result",
        "eval": case_dir / "eval",
    }
    for directory in dirs.values():
        directory.mkdir(parents=True, exist_ok=True)
    return dirs


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def prepare_case(
    image_path: Path,
    *,
    case_id: str,
    layout_path: Path,
    out_root: Path,
    overwrite: bool,
    contact_mode: str,
    chunks: list[str],
) -> dict[str, Any]:
    case_dir = out_root / case_id
    if case_dir.exists() and not overwrite:
        raise FileExistsError(f"case already exists: {case_dir} (use --overwrite to regenerate)")
    if case_dir.exists() and overwrite:
        shutil.rmtree(case_dir)

    dirs = ensure_case_dirs(case_dir)
    copied_image = dirs["input"] / image_path.name
    shutil.copy2(image_path, copied_image)

    crop_result = dirs["crops"] / "crop_result.json"
    corrected = dirs["crops"] / "corrected.png"
    source_overlay = dirs["crops"] / "source_overlay.png"
    steps: list[dict[str, Any]] = []
    steps.append(
        {
            "name": "crop_answer_boxes",
            **run_step(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "crop_answer_boxes.py"),
                    "--image",
                    str(copied_image),
                    "--layout",
                    str(layout_path),
                    "--out-dir",
                    str(dirs["crops"]),
                    "--result-out",
                    str(crop_result),
                    "--corrected-out",
                    str(corrected),
                    "--source-overlay-out",
                    str(source_overlay),
                ]
            ),
        }
    )

    steps.append(
        {
            "name": "enhance_vision_crops",
            **run_step(
                [
                    sys.executable,
                    str(SCRIPT_DIR / "enhance_vision_crops.py"),
                    "--crop-dir",
                    str(dirs["crops"]),
                    "--out-dir",
                    str(dirs["enhanced_crops"]),
                    "--scale",
                    "2",
                ]
            ),
        }
    )

    contact_files: list[str] = []
    for chunk in chunks:
        out_path = dirs["contact"] / contact_filename(chunk, contact_mode)
        command = [
            sys.executable,
            str(SCRIPT_DIR / "make_vision_contact_sheet.py"),
            "--crop-dir",
            str(dirs["crops"]),
            "--questions",
            chunk,
            "--show-mode",
            contact_mode,
            "--columns",
            "2",
            "--scale",
            "1",
            "--out",
            str(out_path),
        ]
        if contact_mode in {"enhanced", "original_and_enhanced"}:
            command.extend(["--enhanced-crop-dir", str(dirs["enhanced_crops"])])
        steps.append({"name": f"contact_{chunk}", **run_step(command)})
        contact_files.append(str(out_path))

    (dirs["vision_result"] / "README.txt").write_text(
        "Save manual Vision JSON outputs here, then merge and evaluate them.\n"
        "This batch tool does not call external APIs.\n",
        encoding="utf-8",
    )

    manifest = {
        "ok": True,
        "case_id": case_id,
        "source_image": str(image_path),
        "copied_image": str(copied_image),
        "layout": str(layout_path),
        "case_dir": str(case_dir),
        "crops_dir": str(dirs["crops"]),
        "enhanced_crops_dir": str(dirs["enhanced_crops"]),
        "contact_dir": str(dirs["contact"]),
        "vision_result_dir": str(dirs["vision_result"]),
        "eval_dir": str(dirs["eval"]),
        "crop_result": str(crop_result),
        "corrected_image": str(corrected),
        "source_overlay": str(source_overlay),
        "contact_mode": contact_mode,
        "questions_chunks": chunks,
        "contact_files": contact_files,
        "crop_count": count_question_pngs(dirs["crops"]),
        "enhanced_crop_count": count_question_pngs(dirs["enhanced_crops"]),
        "contact_count": len([item for item in dirs["contact"].glob("*.png") if item.is_file()]),
        "steps": steps,
        "external_api_calls": False,
    }
    write_json(case_dir / "case_manifest.json", manifest)
    return manifest


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def main() -> int:
    args = parse_args()
    input_dir = Path(args.input_dir)
    layout_path = Path(args.layout)
    out_root = Path(args.out_root)
    chunks = parse_chunks(args.questions_chunks)

    if not input_dir.exists():
        raise FileNotFoundError(f"missing --input-dir: {input_dir}")
    if not layout_path.exists():
        raise FileNotFoundError(f"missing --layout: {layout_path}")

    out_root.mkdir(parents=True, exist_ok=True)
    images = discover_images(input_dir)
    manifests: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    started_at = datetime.now().isoformat(timespec="seconds")

    for image_path in images:
        case_id = safe_case_id(f"{args.case_prefix}{image_path.stem}")
        print(f"\n=== {case_id} ===")
        try:
            manifest = prepare_case(
                image_path,
                case_id=case_id,
                layout_path=layout_path,
                out_root=out_root,
                overwrite=bool(args.overwrite),
                contact_mode=str(args.contact_mode),
                chunks=chunks,
            )
            manifests.append(manifest)
        except Exception as exc:  # noqa: BLE001 - batch manifest should retain failures.
            message = str(exc)
            print(f"FAILED {case_id}: {message}")
            failed.append(
                {
                    "case_id": case_id,
                    "source_image": str(image_path),
                    "error": message,
                }
            )

    finished_at = datetime.now().isoformat(timespec="seconds")
    summary = {
        "ok": not failed,
        "mode": "subjective_stress_test_batch_prepare",
        "started_at": started_at,
        "finished_at": finished_at,
        "input_dir": str(input_dir),
        "layout": str(layout_path),
        "out_root": str(out_root),
        "contact_mode": str(args.contact_mode),
        "questions_chunks": chunks,
        "image_count": len(images),
        "prepared_count": len(manifests),
        "failed_count": len(failed),
        "external_api_calls": False,
        "cases": manifests,
        "failed_cases": failed,
    }

    write_json(out_root / "batch_manifest.json", summary)
    write_csv(
        out_root / "batch_manifest.csv",
        manifests,
        [
            "case_id",
            "source_image",
            "case_dir",
            "crop_count",
            "enhanced_crop_count",
            "contact_count",
            "contact_mode",
        ],
    )
    write_json(out_root / "failed_cases.json", failed)
    write_csv(out_root / "failed_cases.csv", failed, ["case_id", "source_image", "error"])

    print(f"\nPrepared {len(manifests)} case(s), failed {len(failed)} case(s).")
    print(f"batch_manifest={out_root / 'batch_manifest.json'}")
    print(f"failed_cases={out_root / 'failed_cases.json'}")
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
