#!/usr/bin/env python
"""Initialize one subjective OCR stress test case.

Creates a case folder, copies the input image, crops answer boxes, and builds
manual Vision contact sheets. No network calls are made.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path


SCRIPT_DIR = Path(__file__).resolve().parent


def run_step(command: list[str]) -> None:
    print("RUN " + " ".join(command))
    subprocess.run(command, check=True)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Initialize a subjective OCR stress test case folder.")
    parser.add_argument("--case-id", required=True, help="Case id, e.g. person_01.")
    parser.add_argument("--image", required=True, help="Original photographed/scanned sheet image path.")
    parser.add_argument("--layout", required=True, help="Layout JSON path used by crop_answer_boxes.py.")
    parser.add_argument("--out-root", required=True, help="Stress test root folder.")
    parser.add_argument("--overwrite", action="store_true", help="Allow replacing generated files in an existing case folder.")
    return parser.parse_args()


def safe_case_id(case_id: str) -> str:
    cleaned = case_id.strip().replace("\\", "_").replace("/", "_")
    if not cleaned or cleaned in {".", ".."}:
        raise ValueError("invalid --case-id")
    return cleaned


def main() -> int:
    args = parse_args()
    case_id = safe_case_id(args.case_id)
    image_path = Path(args.image)
    layout_path = Path(args.layout)
    out_root = Path(args.out_root)
    if not image_path.exists():
        raise FileNotFoundError(f"missing image: {image_path}")
    if not layout_path.exists():
        raise FileNotFoundError(f"missing layout: {layout_path}")

    case_dir = out_root / case_id
    input_dir = case_dir / "input"
    crops_dir = case_dir / "crops"
    contact_dir = case_dir / "contact"
    vision_dir = case_dir / "vision_result"
    eval_dir = case_dir / "eval"
    for directory in (input_dir, crops_dir, contact_dir, vision_dir, eval_dir):
        directory.mkdir(parents=True, exist_ok=True)

    copied_image = input_dir / image_path.name
    if copied_image.exists() and not args.overwrite:
        print(f"Keeping existing input image: {copied_image}")
    else:
        shutil.copy2(image_path, copied_image)
        print(f"Copied {image_path} -> {copied_image}")

    crop_result = crops_dir / "crop_result.json"
    corrected = crops_dir / "corrected.png"
    source_overlay = crops_dir / "source_overlay.png"
    if crop_result.exists() and not args.overwrite:
        print(f"Keeping existing crop result: {crop_result}")
    else:
        run_step(
            [
                sys.executable,
                str(SCRIPT_DIR / "crop_answer_boxes.py"),
                "--image",
                str(copied_image),
                "--layout",
                str(layout_path),
                "--out-dir",
                str(crops_dir),
                "--result-out",
                str(crop_result),
                "--corrected-out",
                str(corrected),
                "--source-overlay-out",
                str(source_overlay),
            ]
        )

    contact_1_10 = contact_dir / "vision_contact_q001_q010.png"
    contact_11_20 = contact_dir / "vision_contact_q011_q020.png"
    for questions, out_path in (("1-10", contact_1_10), ("11-20", contact_11_20)):
        if out_path.exists() and not args.overwrite:
            print(f"Keeping existing contact sheet: {out_path}")
            continue
        run_step(
            [
                sys.executable,
                str(SCRIPT_DIR / "make_vision_contact_sheet.py"),
                "--crop-dir",
                str(crops_dir),
                "--questions",
                questions,
                "--out",
                str(out_path),
            ]
        )

    (vision_dir / "README.txt").write_text(
        "Save manual Vision JSON outputs here, then merge and evaluate them.\n"
        "Expected filenames:\n"
        "- ocr_result_manual_vision_q001_q010.json\n"
        "- ocr_result_manual_vision_q011_q020.json\n",
        encoding="utf-8",
    )

    print(f"case_dir={case_dir}")
    print(f"input={copied_image}")
    print(f"crops={crops_dir}")
    print(f"contact={contact_dir}")
    print(f"vision_result={vision_dir}")
    print(f"eval={eval_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
