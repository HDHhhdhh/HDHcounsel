#!/usr/bin/env python
"""Create a synthetic marked OMR sheet for dry-run testing."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance


def parse_answers(text: str, question_count: int) -> list[str]:
    compact = "".join(ch for ch in str(text or "") if ch.isalnum() or ch == "?")
    answers = list(compact)
    if len(answers) < question_count:
        answers.extend(["?"] * (question_count - len(answers)))
    return answers[:question_count]


def load_layout(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def bubble_lookup(layout: dict) -> dict[tuple[int, str], dict]:
    lookup = {}
    for bubble in layout.get("bubbles") or []:
        lookup[(int(bubble["question"]), str(bubble["choice"]))] = bubble
    return lookup


def add_noise(image: Image.Image, sigma: float) -> Image.Image:
    if sigma <= 0:
        return image
    arr = np.asarray(image).astype(np.int16)
    noise = np.random.normal(0, sigma, arr.shape).astype(np.int16)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode=image.mode)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Fill a generated OMR sheet with synthetic answers.")
    parser.add_argument("--layout", required=True, help="Path to .layout.json.")
    parser.add_argument("--sheet", required=True, help="Path to blank generated OMR PNG.")
    parser.add_argument("--answers", required=True, help="Answers text, e.g. 13245132451324513245.")
    parser.add_argument("--out", required=True, help="Output marked PNG path.")
    parser.add_argument("--rotate", type=float, default=0.0, help="Optional small rotation in degrees. Default: 0.")
    parser.add_argument("--brightness", type=float, default=1.0, help="Brightness multiplier. Default: 1.0.")
    parser.add_argument("--noise", type=float, default=0.0, help="Gaussian noise sigma, 0 disables it.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for repeatable noise.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    layout = load_layout(Path(args.layout))
    image = Image.open(args.sheet).convert("RGB")
    draw = ImageDraw.Draw(image)
    lookup = bubble_lookup(layout)
    answers = parse_answers(args.answers, int(layout["question_count"]))

    for question, answer in enumerate(answers, start=1):
        if answer == "?":
            continue
        bubble = lookup.get((question, answer))
        if not bubble:
            continue
        x = int(bubble["center"]["x"])
        y = int(bubble["center"]["y"])
        radius = int(bubble["radius"]) - 5
        draw.ellipse([x - radius, y - radius, x + radius, y + radius], fill=(15, 15, 15))

    if args.brightness != 1.0:
        image = ImageEnhance.Brightness(image).enhance(args.brightness)
    if args.noise > 0:
        image = add_noise(image, args.noise)
    if args.rotate:
        image = image.rotate(args.rotate, resample=Image.Resampling.BICUBIC, expand=False, fillcolor="white")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
