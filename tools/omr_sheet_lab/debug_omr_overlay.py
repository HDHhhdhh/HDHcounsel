#!/usr/bin/env python
"""Draw a visual debug overlay for OMR sheet recognition."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont

from omr_core import marker_target_points


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_font(size: int) -> ImageFont.ImageFont:
    for candidate in [r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\arial.ttf"]:
        path = Path(candidate)
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except OSError:
                pass
    return ImageFont.load_default()


def scale_box(box: dict[str, int], sx: float, sy: float) -> tuple[int, int, int, int]:
    return (
        int(round(box["left"] * sx)),
        int(round(box["top"] * sy)),
        int(round(box["right"] * sx)),
        int(round(box["bottom"] * sy)),
    )


def draw_cross(draw: ImageDraw.ImageDraw, x: float, y: float, color: tuple[int, int, int], size: int = 18) -> None:
    draw.line((x - size, y, x + size, y), fill=color, width=4)
    draw.line((x, y - size, x, y + size), fill=color, width=4)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a debug overlay for an OMR read result.")
    parser.add_argument("--image", required=True, help="Input OMR image path, usually corrected-out when available.")
    parser.add_argument("--layout", required=True, help="Path to .layout.json.")
    parser.add_argument("--result", required=True, help="Path to read_omr_sheet result JSON.")
    parser.add_argument("--out", required=True, help="Output overlay PNG path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    image = Image.open(args.image).convert("RGB")
    layout = load_json(Path(args.layout))
    result = load_json(Path(args.result))
    draw = ImageDraw.Draw(image)
    font = load_font(22)
    big_font = load_font(30)
    small_font = load_font(18)

    width, height = image.size
    page = layout.get("page") or {}
    lw = int(page.get("width_px") or width)
    lh = int(page.get("height_px") or height)
    sx = width / max(lw, 1)
    sy = height / max(lh, 1)

    preprocess = result.get("preprocess") or {}
    items_by_q = {int(item["question"]): item for item in result.get("items") or []}
    warn_questions = {int(item.get("question")) for item in result.get("warnings") or [] if item.get("question")}

    for bubble in layout.get("bubbles") or []:
        question = int(bubble["question"])
        choice = str(bubble["choice"])
        item = items_by_q.get(question, {})
        selected = str(item.get("answer") or "") == choice
        status = str(item.get("status") or "")
        box = scale_box(bubble["roi"], sx, sy)
        cx = int(round(bubble["center"]["x"] * sx))
        cy = int(round(bubble["center"]["y"] * sy))
        radius = max(3, int(round(int(bubble.get("radius") or 20) * (sx + sy) / 2)))

        if selected and status == "ok":
            color = (0, 150, 0)
            width_px = 5
        elif question in warn_questions:
            color = (230, 70, 20)
            width_px = 4
        else:
            color = (40, 120, 220)
            width_px = 2

        draw.rectangle(box, outline=color, width=width_px)
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=color, width=width_px)

    for question, item in sorted(items_by_q.items()):
        bubbles = [b for b in layout.get("bubbles") or [] if int(b["question"]) == question]
        if not bubbles:
            continue
        x = int(round((bubbles[0]["center"]["x"] - 255) * sx))
        y = int(round((bubbles[0]["center"]["y"] - 22) * sy))
        answer = str(item.get("answer") or "?")
        status = str(item.get("status") or "")
        color = (0, 130, 0) if status == "ok" else (220, 50, 20)
        draw.text((x, y), f"{question:02d}:{answer}", fill=color, font=font)

    for key, (x, y) in marker_target_points(layout).items():
        draw_cross(draw, x * sx, y * sy, (180, 0, 220), size=22)
        draw.text((x * sx + 12, y * sy + 10), key, fill=(180, 0, 220), font=small_font)

    marker_points = preprocess.get("marker_points") or {}
    source_size = preprocess.get("source_image_size") or {}
    if source_size.get("width_px") == width and source_size.get("height_px") == height:
        for key, point in marker_points.items():
            draw_cross(draw, float(point["x"]), float(point["y"]), (255, 120, 0), size=26)
            draw.text((float(point["x"]) + 12, float(point["y"]) - 26), f"detected {key}", fill=(255, 120, 0), font=small_font)

    fallback = bool(preprocess.get("fallback"))
    marker_detected = bool(preprocess.get("marker_detected"))
    basis = "corrected/layout" if marker_detected and not fallback else "scale-only/fallback"
    summary = (
        f"basis={basis} marker={marker_detected} fallback={fallback} "
        f"answersText={result.get('answersText', '')} warnings={len(result.get('warnings') or [])}"
    )
    draw.rectangle([30, 30, min(width - 30, 1800), 88], fill=(255, 255, 210), outline=(0, 0, 0), width=2)
    draw.text((45, 45), summary, fill=(0, 0, 0), font=big_font)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
