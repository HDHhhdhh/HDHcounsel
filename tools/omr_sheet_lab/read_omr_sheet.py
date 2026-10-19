#!/usr/bin/env python
"""Read an OMR sheet image using marker correction plus fixed-layout bubbles."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from PIL import Image

from omr_core import (
    build_answers_text,
    detect_corner_markers,
    load_layout,
    page_size,
    read_bubbles,
    warp_to_layout,
)


DEFAULT_DARK_THRESHOLD = 150
DEFAULT_MIN_MARK_RATIO = 0.22
DEFAULT_BLANK_THRESHOLD = 0.17
DEFAULT_AMBIGUOUS_GAP = 0.08


def read_sheet(
    image_path: Path,
    layout: dict,
    *,
    perspective_enabled: bool,
    corrected_out: Path | None,
    normalized_out: Path | None,
    dark_threshold: int,
    min_mark_ratio: float,
    blank_threshold: float,
    ambiguous_gap: float,
    marker_search_ratio: float,
) -> dict:
    source_image = Image.open(image_path).convert("RGB")
    source_width, source_height = source_image.size
    marker_result = {
        "detected": False,
        "points": {},
        "confidence": {},
        "failures": ["perspective disabled"],
    }
    corrected_image = source_image
    fallback = True
    corrected_path_text = ""

    if perspective_enabled:
        marker_result = detect_corner_markers(
            source_image,
            layout,
            dark_threshold=dark_threshold,
            marker_search_ratio=marker_search_ratio,
        )
        if marker_result.get("detected"):
            try:
                corrected_image = warp_to_layout(source_image, layout, marker_result)
                fallback = False
            except Exception as exc:
                marker_result.setdefault("failures", []).append(f"warp failed: {exc}")
                corrected_image = source_image
                fallback = True

    if corrected_out:
        corrected_out.parent.mkdir(parents=True, exist_ok=True)
        corrected_image.save(corrected_out)
        corrected_path_text = str(corrected_out)

    if normalized_out:
        layout_width, layout_height = page_size(layout)
        if layout_width > 0 and layout_height > 0:
            normalized_out.parent.mkdir(parents=True, exist_ok=True)
            corrected_image.convert("L").resize((layout_width, layout_height)).save(normalized_out)

    items, answers, warnings, bubble_diag = read_bubbles(
        corrected_image,
        layout,
        dark_threshold=dark_threshold,
        min_mark_ratio=min_mark_ratio,
        blank_threshold=blank_threshold,
        ambiguous_gap=ambiguous_gap,
    )
    answers_text = build_answers_text(answers, str(layout.get("answer_text_format") or "compact"))

    return {
        "ok": True,
        "test_id": layout.get("test_id"),
        "test_name": layout.get("test_name"),
        "answersText": answers_text,
        "answersTextSpaced": " ".join(answers),
        "answers": answers,
        "items": items,
        "warnings": warnings,
        "preprocess": {
            "perspective_enabled": bool(perspective_enabled),
            "marker_detected": bool(marker_result.get("detected")),
            "fallback": bool(fallback),
            "marker_points": marker_result.get("points") or {},
            "marker_confidence": marker_result.get("confidence") or {},
            "marker_failures": marker_result.get("failures") or [],
            "marker_details": marker_result.get("details") or {},
            "corrected_image": corrected_path_text,
            "source_image_size": {"width_px": source_width, "height_px": source_height},
            "read_image_size": bubble_diag["image_size"],
        },
        "thresholds": {
            "dark_threshold": dark_threshold,
            "min_mark_ratio": min_mark_ratio,
            "blank_threshold": blank_threshold,
            "ambiguous_gap": ambiguous_gap,
            "marker_search_ratio": marker_search_ratio,
        },
        "processing": {
            **bubble_diag,
            "perspective_correction": "applied" if perspective_enabled and not fallback else "fallback_scale_only",
        },
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read answers from a generated OMR sheet image.")
    parser.add_argument("--image", required=True, help="Path to scanned/photographed OMR image.")
    parser.add_argument("--layout", required=True, help="Path to .layout.json.")
    parser.add_argument("--out", required=True, help="Output result JSON path.")
    parser.add_argument("--normalized-out", help="Optional resized grayscale image output path.")
    parser.add_argument("--corrected-out", help="Optional perspective-corrected image output path.")
    parser.add_argument("--disable-perspective", action="store_true", help="Skip marker detection and correction.")
    parser.add_argument("--dark-threshold", type=int, default=None, help="Dark pixel threshold, 0-255.")
    parser.add_argument("--min-mark-ratio", type=float, default=DEFAULT_MIN_MARK_RATIO)
    parser.add_argument("--blank-threshold", type=float, default=DEFAULT_BLANK_THRESHOLD)
    parser.add_argument("--ambiguous-gap", type=float, default=DEFAULT_AMBIGUOUS_GAP)
    parser.add_argument("--marker-search-ratio", type=float, default=0.28)

    # Backward-compatible aliases from prototype 1.
    parser.add_argument("--dark-pixel-threshold", type=int, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--mark-threshold", type=float, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--uncertain-threshold", type=float, default=None, help=argparse.SUPPRESS)
    parser.add_argument("--ambiguity-margin", type=float, default=None, help=argparse.SUPPRESS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    dark_threshold = (
        args.dark_threshold
        if args.dark_threshold is not None
        else args.dark_pixel_threshold
        if args.dark_pixel_threshold is not None
        else DEFAULT_DARK_THRESHOLD
    )
    min_mark_ratio = args.mark_threshold if args.mark_threshold is not None else args.min_mark_ratio
    blank_threshold = args.uncertain_threshold if args.uncertain_threshold is not None else args.blank_threshold
    ambiguous_gap = args.ambiguity_margin if args.ambiguity_margin is not None else args.ambiguous_gap

    layout = load_layout(Path(args.layout))
    result = read_sheet(
        Path(args.image),
        layout,
        perspective_enabled=not args.disable_perspective,
        corrected_out=Path(args.corrected_out) if args.corrected_out else None,
        normalized_out=Path(args.normalized_out) if args.normalized_out else None,
        dark_threshold=int(dark_threshold),
        min_mark_ratio=float(min_mark_ratio),
        blank_threshold=float(blank_threshold),
        ambiguous_gap=float(ambiguous_gap),
        marker_search_ratio=float(args.marker_search_ratio),
    )

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"answersText={result['answersText']}")
    print(f"warnings={len(result['warnings'])}")
    print(
        "preprocess="
        f"marker_detected={result['preprocess']['marker_detected']} "
        f"fallback={result['preprocess']['fallback']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
