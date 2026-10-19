#!/usr/bin/env python
"""Enhance subjective answer crops for manual Vision OCR testing."""

from __future__ import annotations

import argparse
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps


def parse_questions(raw: str | None) -> set[int] | None:
    if not raw:
        return None
    questions: set[int] = set()
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if "-" in piece:
            start_raw, end_raw = piece.split("-", 1)
            start = int(start_raw.strip())
            end = int(end_raw.strip())
            step = 1 if end >= start else -1
            questions.update(range(start, end + step, step))
        else:
            questions.add(int(piece))
    return {question for question in questions if question >= 1}


def question_from_path(path: Path) -> int | None:
    stem = path.stem.lower()
    if not stem.startswith("q"):
        return None
    try:
        return int(stem[1:])
    except ValueError:
        return None


def enhance_crop(
    image: Image.Image,
    *,
    scale: float,
    contrast: float,
    sharpness: float,
    background_boost: int,
    ink_darken: float,
    ink_threshold: int,
    background_threshold: int,
    autocontrast_cutoff: float,
) -> Image.Image:
    gray = image.convert("L")
    gray = ImageOps.autocontrast(gray, cutoff=max(0.0, float(autocontrast_cutoff)))
    gray = ImageEnhance.Contrast(gray).enhance(max(0.1, float(contrast)))
    gray = ImageEnhance.Sharpness(gray).enhance(max(0.1, float(sharpness)))

    def remap(pixel: int) -> int:
        if pixel <= ink_threshold:
            return max(0, min(255, int(pixel * ink_darken)))
        if pixel >= background_threshold:
            return max(0, min(255, pixel + background_boost))
        return pixel

    gray = gray.point(remap)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.2, percent=140, threshold=2))
    if scale != 1.0:
        width = max(1, int(gray.width * scale))
        height = max(1, int(gray.height * scale))
        gray = gray.resize((width, height), Image.Resampling.LANCZOS)
    return gray.convert("RGB")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Enhance crop PNG files for manual Vision OCR testing.")
    parser.add_argument("--crop-dir", required=True, help="Directory containing original q001.png, q002.png, ... crops.")
    parser.add_argument("--out-dir", required=True, help="Directory for enhanced q001.png, q002.png, ... crops.")
    parser.add_argument("--questions", help="Optional question list/ranges, e.g. 1-5,8,10.")
    parser.add_argument("--scale", type=float, default=2.0, help="Resize factor for enhanced crops. Default: 2.0.")
    parser.add_argument("--contrast", type=float, default=1.55, help="Contrast multiplier. Default: 1.55.")
    parser.add_argument("--sharpness", type=float, default=1.8, help="Sharpness multiplier. Default: 1.8.")
    parser.add_argument("--background-boost", type=int, default=18, help="Brightness added to bright background pixels.")
    parser.add_argument("--ink-darken", type=float, default=0.72, help="Multiplier for dark ink pixels. Lower is darker.")
    parser.add_argument("--ink-threshold", type=int, default=155, help="Pixels at or below this value are treated as ink.")
    parser.add_argument("--background-threshold", type=int, default=205, help="Pixels at or above this value are brightened.")
    parser.add_argument("--autocontrast-cutoff", type=float, default=1.0, help="Pillow autocontrast cutoff percentage.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    crop_dir = Path(args.crop_dir)
    out_dir = Path(args.out_dir)
    if crop_dir.resolve() == out_dir.resolve():
        raise SystemExit("--out-dir must be different from --crop-dir; original crops are never overwritten.")
    wanted = parse_questions(args.questions)

    out_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for path in sorted(crop_dir.glob("q*.png")):
        question = question_from_path(path)
        if question is None or (wanted is not None and question not in wanted):
            continue
        image = Image.open(path)
        enhanced = enhance_crop(
            image,
            scale=float(args.scale),
            contrast=float(args.contrast),
            sharpness=float(args.sharpness),
            background_boost=int(args.background_boost),
            ink_darken=float(args.ink_darken),
            ink_threshold=int(args.ink_threshold),
            background_threshold=int(args.background_threshold),
            autocontrast_cutoff=float(args.autocontrast_cutoff),
        )
        enhanced.save(out_dir / path.name)
        count += 1

    print(f"Wrote {count} enhanced crops to {out_dir}")
    print(f"scale={args.scale} contrast={args.contrast} sharpness={args.sharpness}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
