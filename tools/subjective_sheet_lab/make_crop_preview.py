#!/usr/bin/env python
"""Create a crop verification contact sheet from subjective answer crops."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


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


def read_result(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def resolve_crop_path(crop_path: str, result_dir: Path) -> Path:
    path = Path(crop_path)
    if path.is_absolute():
        return path
    return result_dir / path


def fit_image(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    max_w, max_h = max_size
    scale = min(max_w / image.width, max_h / image.height)
    size = (max(1, int(image.width * scale)), max(1, int(image.height * scale)))
    return image.resize(size, Image.Resampling.LANCZOS)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a crop verification PNG from cropped subjective answer boxes.")
    parser.add_argument("--result", required=True, help="Result JSON from crop_answer_boxes.py.")
    parser.add_argument("--out", required=True, help="Output crop verification PNG path.")
    parser.add_argument("--columns", type=int, default=2, help="Preview columns.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    result_path = Path(args.result)
    result = read_result(result_path)
    result_dir = result_path.parent
    items = result.get("items") or []
    columns = max(1, int(args.columns))
    rows = (len(items) + columns - 1) // columns
    preprocess = result.get("preprocess") or {}
    alignment_ok = bool(result.get("alignment_ok", preprocess.get("alignment_ok", result.get("ok"))))

    cell_w = 1060
    cell_h = 250
    margin = 44
    header_h = 230 if not alignment_ok else 120
    width = margin * 2 + columns * cell_w
    height = margin * 2 + header_h + max(1, rows) * cell_h
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)
    title_font = load_font(34, bold=True)
    label_font = load_font(28, bold=True)
    small_font = load_font(21)

    title = f"{result.get('test_name') or ''} crop verification preview".strip()
    input_name = Path(str(result.get("input_image") or "")).name or "(unknown)"
    draw.text((margin, margin), title, fill="black", font=title_font)
    draw.text(
        (margin, margin + 48),
        f"test_id={result.get('test_id')}  source={input_name}  crops={len(items)}",
        fill=(70, 70, 70),
        font=small_font,
    )
    draw.text(
        (margin, margin + 78),
        f"alignment_ok={alignment_ok}  correction={preprocess.get('correction')}  pass={preprocess.get('marker_pass')}  fallback={preprocess.get('fallback')}  marker_detected={preprocess.get('marker_detected')}  status={result.get('status')}",
        fill=(70, 70, 70) if alignment_ok else (170, 0, 0),
        font=small_font,
    )

    if not alignment_ok:
        reason = str((preprocess.get("marker_validation") or {}).get("reason") or preprocess.get("fallback_reason") or "retake_photo_required")
        draw.rectangle([margin, margin + 106, width - margin, margin + 198], fill=(160, 0, 0))
        draw.text((margin + 18, margin + 120), "INVALID ALIGNMENT - RETAKE PHOTO REQUIRED", fill="white", font=label_font)
        draw.text((margin + 18, margin + 156), reason[:150], fill="white", font=small_font)

    for index, item in enumerate(items):
        row = index // columns
        col = index % columns
        x = margin + col * cell_w
        y = margin + header_h + row * cell_h
        draw.rectangle([x, y, x + cell_w - 22, y + cell_h - 24], outline=(180, 180, 180), width=2)
        draw.text((x + 18, y + 14), f"Q{int(item.get('question') or 0):03d}", fill="black", font=label_font)

        crop_path = resolve_crop_path(str(item.get("cropPath") or ""), result_dir)
        if crop_path.exists():
            crop = Image.open(crop_path).convert("RGB")
            fitted = fit_image(crop, (cell_w - 140, cell_h - 60))
            image.paste(fitted, (x + 115, y + 32))
        else:
            draw.text((x + 115, y + 82), f"Missing crop: {crop_path}", fill=(180, 0, 0), font=small_font)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(out_path)
    print(f"Wrote {out_path}")
    print(f"items={len(items)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
