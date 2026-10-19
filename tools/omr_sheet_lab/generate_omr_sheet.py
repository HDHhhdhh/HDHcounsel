#!/usr/bin/env python
"""Generate a fixed-layout OMR answer sheet and matching layout JSON.

This prototype intentionally depends only on Pillow and the Python standard
library so it can run inside the current counsel-note environment.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


DEFAULT_PAGE = {"width_px": 2480, "height_px": 3508, "dpi": 300}
MARKER_SIZE = 92
MARKER_MARGIN = 130
BUBBLE_RADIUS = 24
BUBBLE_ROI_PAD = 34


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


def read_config(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8-sig") as file:
        data = json.load(file)
    page = {**DEFAULT_PAGE, **(data.get("page") or {})}
    return {
        "test_id": str(data.get("test_id") or "unit_test_sample"),
        "test_name": str(data.get("test_name") or "Unit Test Sample"),
        "question_count": int(data.get("question_count") or 20),
        "choice_count": int(data.get("choice_count") or 5),
        "answer_text_format": str(data.get("answer_text_format") or "compact"),
        "page": page,
    }


def roi_from_center(x: int, y: int, pad: int = BUBBLE_ROI_PAD) -> dict[str, int]:
    return {"left": x - pad, "top": y - pad, "right": x + pad, "bottom": y + pad}


def marker_roi(x: int, y: int, size: int = MARKER_SIZE) -> dict[str, int]:
    return {"left": x, "top": y, "right": x + size, "bottom": y + size}


def build_layout(config: dict[str, Any]) -> dict[str, Any]:
    page = config["page"]
    width = int(page["width_px"])
    height = int(page["height_px"])
    q_count = int(config["question_count"])
    choice_count = int(config["choice_count"])

    markers = {
        "top_left": {"x": MARKER_MARGIN, "y": MARKER_MARGIN, "size": MARKER_SIZE},
        "top_right": {"x": width - MARKER_MARGIN - MARKER_SIZE, "y": MARKER_MARGIN, "size": MARKER_SIZE},
        "bottom_left": {"x": MARKER_MARGIN, "y": height - MARKER_MARGIN - MARKER_SIZE, "size": MARKER_SIZE},
        "bottom_right": {
            "x": width - MARKER_MARGIN - MARKER_SIZE,
            "y": height - MARKER_MARGIN - MARKER_SIZE,
            "size": MARKER_SIZE,
        },
    }
    for marker in markers.values():
        marker["roi"] = marker_roi(marker["x"], marker["y"], marker["size"])

    columns = 2 if q_count > 12 else 1
    rows_per_col = (q_count + columns - 1) // columns
    top_y = 720
    bottom_limit = height - 360
    row_gap = max(92, min(190, (bottom_limit - top_y) // max(rows_per_col - 1, 1)))
    col_width = (width - 420) // columns
    base_x = 260
    choice_gap = 112

    bubbles: list[dict[str, Any]] = []
    for question in range(1, q_count + 1):
        col = (question - 1) // rows_per_col
        row = (question - 1) % rows_per_col
        y = top_y + row * row_gap
        qx = base_x + col * col_width
        first_choice_x = qx + 180
        for choice_num in range(1, choice_count + 1):
            x = first_choice_x + (choice_num - 1) * choice_gap
            bubbles.append(
                {
                    "question": question,
                    "choice": str(choice_num),
                    "center": {"x": x, "y": y},
                    "radius": BUBBLE_RADIUS,
                    "roi": roi_from_center(x, y),
                }
            )

    return {
        "version": 1,
        "test_id": config["test_id"],
        "test_name": config["test_name"],
        "question_count": q_count,
        "choice_count": choice_count,
        "answer_text_format": config["answer_text_format"],
        "page": page,
        "markers": markers,
        "bubbles": bubbles,
        "notes": [
            "Coordinates are in the generated page pixel space.",
            "Perspective correction is intentionally deferred in prototype 1.",
        ],
    }


def draw_sheet(config: dict[str, Any], layout: dict[str, Any]) -> Image.Image:
    page = config["page"]
    width = int(page["width_px"])
    height = int(page["height_px"])
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title_font = load_font(54, bold=True)
    label_font = load_font(30)
    small_font = load_font(24)
    q_font = load_font(28, bold=True)

    for marker in layout["markers"].values():
        box = marker["roi"]
        draw.rectangle([box["left"], box["top"], box["right"], box["bottom"]], fill="black")

    draw.text((260, 135), "Unit OMR Answer Sheet", fill="black", font=title_font)
    draw.text((260, 210), f"Test: {config['test_name']}    ID: {config['test_id']}", fill="black", font=label_font)
    draw.text((260, 280), "Name:", fill="black", font=label_font)
    draw.line((360, 315, 920, 315), fill="black", width=3)
    draw.text((1020, 280), "Student ID:", fill="black", font=label_font)
    draw.line((1200, 315, 1780, 315), fill="black", width=3)
    draw.text(
        (260, 365),
        "Fill one bubble per question. Use dark pencil/pen. Do not fold marker corners.",
        fill=(70, 70, 70),
        font=small_font,
    )
    draw.line((240, 455, width - 240, 455), fill=(160, 160, 160), width=2)

    bubbles_by_q: dict[int, list[dict[str, Any]]] = {}
    for bubble in layout["bubbles"]:
        bubbles_by_q.setdefault(int(bubble["question"]), []).append(bubble)

    for question, bubbles in sorted(bubbles_by_q.items()):
        y = int(bubbles[0]["center"]["y"])
        qx = int(bubbles[0]["center"]["x"]) - 180
        draw.text((qx - 80, y - 18), f"{question:02d}", fill="black", font=q_font)
        for bubble in bubbles:
            x = int(bubble["center"]["x"])
            choice = str(bubble["choice"])
            r = int(bubble["radius"])
            draw.ellipse([x - r, y - r, x + r, y + r], outline="black", width=4)
            draw.text((x - 8, y + r + 12), choice, fill=(60, 60, 60), font=small_font)

    return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a unit-test OMR sheet PNG/PDF and layout JSON.")
    parser.add_argument("--config", required=True, help="Path to omr_sheet_config JSON.")
    parser.add_argument("--out", required=True, help="Output prefix, without extension.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    out_prefix = Path(args.out)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)

    config = read_config(config_path)
    layout = build_layout(config)
    image = draw_sheet(config, layout)

    png_path = out_prefix.with_suffix(".png")
    pdf_path = out_prefix.with_suffix(".pdf")
    layout_path = out_prefix.with_suffix(".layout.json")
    image.save(png_path)
    image.save(pdf_path, "PDF", resolution=int(config["page"]["dpi"]))
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {png_path}")
    print(f"Wrote {pdf_path}")
    print(f"Wrote {layout_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
