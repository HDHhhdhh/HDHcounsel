#!/usr/bin/env python
"""Fill a generated subjective answer sheet with synthetic sample answers."""

from __future__ import annotations

import argparse
import json
import random
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageEnhance, ImageFont


def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\malgunbd.ttf" if bold else r"C:\Windows\Fonts\malgun.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
    ]
    for candidate in candidates:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def load_layout(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def parse_answers(args: argparse.Namespace, question_count: int) -> list[str]:
    if args.answers_file:
        text = Path(args.answers_file).read_text(encoding="utf-8-sig")
        answers = text.splitlines()
    else:
        raw = args.answers or ""
        answers = raw.split("|") if "|" in raw else raw.splitlines()
    if len(answers) < question_count:
        answers.extend([""] * (question_count - len(answers)))
    return [answer.strip() for answer in answers[:question_count]]


def fit_text(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    if not text:
        return [""]
    words = text.split()
    if len(words) <= 1:
        return [text]
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width or not current:
            current = candidate
        else:
            lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def add_noise(image: Image.Image, sigma: float) -> Image.Image:
    if sigma <= 0:
        return image
    arr = np.asarray(image).astype(np.int16)
    noise = np.random.normal(0, sigma, arr.shape).astype(np.int16)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode=image.mode)


def draw_answers(image: Image.Image, layout: dict[str, Any], answers: list[str]) -> Image.Image:
    out = image.copy().convert("RGB")
    draw = ImageDraw.Draw(out)
    answer_font = load_font(46)
    small_font = load_font(34)

    for item in layout.get("answer_boxes") or []:
        question = int(item["question"])
        answer = answers[question - 1] if question - 1 < len(answers) else ""
        if not answer:
            continue
        crop = item["crop_bbox"]
        left = int(crop["left"]) + 22
        top = int(crop["top"]) + 24
        max_width = int(crop["right"]) - left - 18
        font = answer_font if len(answer) <= 18 else small_font
        for line in fit_text(draw, answer, font, max_width)[:3]:
            draw.text((left, top), line, fill=(25, 25, 25), font=font)
            top += font.size + 6 if hasattr(font, "size") else 42
    return out


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a synthetic filled subjective answer sheet.")
    parser.add_argument("--layout", required=True, help="Path to .layout.json.")
    parser.add_argument("--sheet", required=True, help="Blank subjective sheet PNG.")
    parser.add_argument("--answers-file", help="Line-based answer text file.")
    parser.add_argument("--answers", help="Answers separated by |, or by newlines if provided by a shell.")
    parser.add_argument("--out", required=True, help="Output filled sheet PNG.")
    parser.add_argument("--rotate", type=float, default=0.0, help="Optional rotation in degrees.")
    parser.add_argument("--brightness", type=float, default=1.0, help="Brightness multiplier.")
    parser.add_argument("--noise", type=float, default=0.0, help="Gaussian noise sigma.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed for noise.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    layout = load_layout(Path(args.layout))
    image = Image.open(args.sheet).convert("RGB")
    answers = parse_answers(args, int(layout.get("question_count") or 0))
    filled = draw_answers(image, layout, answers)

    if args.brightness != 1.0:
        filled = ImageEnhance.Brightness(filled).enhance(args.brightness)
    if args.noise > 0:
        filled = add_noise(filled, args.noise)
    if args.rotate:
        filled = filled.rotate(args.rotate, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(255, 255, 255))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    filled.save(out_path)
    print(f"Wrote {out_path}")
    print(f"answers={len(answers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
