#!/usr/bin/env python
"""Make a synthetic photo-like OMR image for marker/warp dry-runs."""

from __future__ import annotations

import argparse
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageEnhance

from omr_core import load_layout, warp_perspective


def add_noise(image: Image.Image, sigma: float) -> Image.Image:
    if sigma <= 0:
        return image
    arr = np.asarray(image).astype(np.int16)
    noise = np.random.normal(0, sigma, arr.shape).astype(np.int16)
    out = np.clip(arr + noise, 0, 255).astype(np.uint8)
    return Image.fromarray(out, mode=image.mode)


def destination_corners(width: int, height: int, margin: int, perspective: float) -> list[tuple[float, float]]:
    p = max(0.0, min(0.16, perspective))
    return [
        (margin + width * p * 0.35, margin + height * p * 0.95),
        (margin + width - width * p * 1.05, margin + height * p * 0.25),
        (margin + width - width * p * 0.25, margin + height - height * p * 0.90),
        (margin + width * p * 1.00, margin + height - height * p * 0.20),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a synthetic photo-like OMR sample.")
    parser.add_argument("--image", required=True, help="Input marked sheet image.")
    parser.add_argument("--layout", required=True, help="Path to .layout.json.")
    parser.add_argument("--out", required=True, help="Output photo-like PNG path.")
    parser.add_argument("--rotate", type=float, default=3.0, help="Final rotation in degrees.")
    parser.add_argument("--brightness", type=float, default=0.92, help="Brightness multiplier.")
    parser.add_argument("--noise", type=float, default=3.0, help="Gaussian noise sigma.")
    parser.add_argument("--margin", type=int, default=180, help="White margin around warped page.")
    parser.add_argument("--perspective", type=float, default=0.035, help="Perspective distortion strength.")
    parser.add_argument("--seed", type=int, default=0, help="Random seed.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    np.random.seed(args.seed)

    layout = load_layout(Path(args.layout))
    image = Image.open(args.image).convert("RGB")
    width, height = image.size
    margin = max(0, int(args.margin))
    output_size = (width + margin * 2, height + margin * 2)
    source_corners = [(0.0, 0.0), (float(width - 1), 0.0), (float(width - 1), float(height - 1)), (0.0, float(height - 1))]
    target_corners = destination_corners(width, height, margin, float(args.perspective))

    warped = warp_perspective(image, source_corners, target_corners, output_size, fill=(245, 245, 245))
    if args.brightness != 1.0:
        warped = ImageEnhance.Brightness(warped).enhance(args.brightness)
    if args.noise > 0:
        warped = add_noise(warped, args.noise)
    if args.rotate:
        warped = warped.rotate(args.rotate, resample=Image.Resampling.BICUBIC, expand=False, fillcolor=(245, 245, 245))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    warped.save(out_path)
    print(f"Wrote {out_path}")
    print(f"layout_test_id={layout.get('test_id')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
