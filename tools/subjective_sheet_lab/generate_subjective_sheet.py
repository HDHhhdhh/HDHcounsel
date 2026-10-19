#!/usr/bin/env python
"""Generate a fixed-layout subjective answer sheet and layout JSON."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


DEFAULT_PAGE = {"width_px": 2480, "height_px": 3508, "dpi": 300}
DEFAULT_BOX_STYLE = {
    "columns": 2,
    "rows_per_column": 10,
    "box_height_px": 220,
    "answer_area_inset_px": {"left": 145, "top": 58, "right": 95, "bottom": 26},
}
DEFAULT_MARKER = {"size_px": 128, "inset_px": 110, "quiet_zone_px": 70}
DEFAULT_LAYOUT = {
    "top_content_start_px": 720,
    "bottom_margin_px": 390,
    "column_gap_px": 150,
    "side_margin_px": 340,
    "row_gap_px": 22,
    "answer_box_inner_inset_px": 34,
}
LEGACY_MARKER_SIZE = 92


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
    box_style = {**DEFAULT_BOX_STYLE, **(data.get("box_style") or {})}
    marker = {**DEFAULT_MARKER, **(data.get("marker") or {})}
    layout = {**DEFAULT_LAYOUT, **(data.get("layout") or {})}
    return {
        "test_id": str(data.get("test_id") or "subjective_unit_test_sample"),
        "test_name": str(data.get("test_name") or "Subjective Unit Test Sample"),
        "question_count": int(data.get("question_count") or 20),
        "answer_text_format": str(data.get("answer_text_format") or "line_based"),
        "page": page,
        "marker": marker,
        "layout": layout,
        "box_style": box_style,
    }


def box(left: int, top: int, right: int, bottom: int) -> dict[str, int]:
    return {"left": int(left), "top": int(top), "right": int(right), "bottom": int(bottom)}


def marker_box(x: int, y: int, size: int = LEGACY_MARKER_SIZE) -> dict[str, int]:
    return box(x, y, x + size, y + size)


def expanded_box(source: dict[str, int], inset: int, width: int, height: int) -> dict[str, int]:
    return box(
        max(0, source["left"] - inset),
        max(0, source["top"] - inset),
        min(width, source["right"] + inset),
        min(height, source["bottom"] + inset),
    )


def read_inset(style: dict[str, Any]) -> dict[str, int]:
    default = {"left": 145, "top": 55, "right": 90, "bottom": 18}
    raw = style.get("answer_area_inset_px", style.get("crop_inset_px", default))
    if isinstance(raw, int):
        return {"left": raw, "top": raw, "right": raw, "bottom": raw}
    if isinstance(raw, dict):
        merged = {**default, **raw}
        return {key: max(0, int(merged[key])) for key in default}
    return default


def build_layout(config: dict[str, Any]) -> dict[str, Any]:
    page = config["page"]
    width = int(page["width_px"])
    height = int(page["height_px"])
    q_count = int(config["question_count"])
    style = config["box_style"]
    marker_style = config["marker"]
    layout_style = config["layout"]
    columns = max(1, int(style.get("columns") or 2))
    rows_per_column = max(1, int(style.get("rows_per_column") or ((q_count + columns - 1) // columns)))
    rows_per_column = max(rows_per_column, (q_count + columns - 1) // columns)
    box_height = max(120, int(style.get("box_height_px") or 230))
    answer_area_inset = read_inset(style)
    marker_size = max(48, int(marker_style.get("size_px") or DEFAULT_MARKER["size_px"]))
    marker_inset = max(50, int(marker_style.get("inset_px") or DEFAULT_MARKER["inset_px"]))
    quiet_zone = max(20, int(marker_style.get("quiet_zone_px") or DEFAULT_MARKER["quiet_zone_px"]))

    markers = {
        "top_left": {"x": marker_inset, "y": marker_inset, "size": marker_size},
        "top_right": {"x": width - marker_inset - marker_size, "y": marker_inset, "size": marker_size},
        "bottom_left": {"x": marker_inset, "y": height - marker_inset - marker_size, "size": marker_size},
        "bottom_right": {
            "x": width - marker_inset - marker_size,
            "y": height - marker_inset - marker_size,
            "size": marker_size,
        },
    }
    for marker in markers.values():
        marker["roi"] = marker_box(marker["x"], marker["y"], marker["size"])
        marker["expected_bbox"] = dict(marker["roi"])
        marker["quiet_zone"] = expanded_box(marker["roi"], quiet_zone, width, height)

    side_margin = max(240, int(layout_style.get("side_margin_px") or DEFAULT_LAYOUT["side_margin_px"]))
    grid_left = side_margin
    grid_right = width - side_margin
    grid_top = max(620, int(layout_style.get("top_content_start_px") or DEFAULT_LAYOUT["top_content_start_px"]))
    grid_bottom = height - max(260, int(layout_style.get("bottom_margin_px") or DEFAULT_LAYOUT["bottom_margin_px"]))
    col_gap = max(0, int(layout_style.get("column_gap_px") or 0)) if columns > 1 else 0
    col_width = (grid_right - grid_left - col_gap * (columns - 1)) // columns
    row_gap = max(10, int(layout_style.get("row_gap_px") or DEFAULT_LAYOUT["row_gap_px"]))
    needed_height = rows_per_column * box_height + max(0, rows_per_column - 1) * row_gap
    available_height = grid_bottom - grid_top
    if needed_height > available_height:
        box_height = max(120, (available_height - max(0, rows_per_column - 1) * row_gap) // rows_per_column)

    answer_boxes: list[dict[str, Any]] = []
    for question in range(1, q_count + 1):
        col = (question - 1) // rows_per_column
        row = (question - 1) % rows_per_column
        left = grid_left + col * (col_width + col_gap)
        top = grid_top + row * (box_height + row_gap)
        right = left + col_width
        bottom = top + box_height
        crop_left = left + answer_area_inset["left"]
        crop_top = top + answer_area_inset["top"]
        crop_right = right - answer_area_inset["right"]
        crop_bottom = bottom - answer_area_inset["bottom"]
        answer_boxes.append(
            {
                "question": question,
                "bbox": box(left, top, right, bottom),
                "crop_bbox": box(crop_left, crop_top, crop_right, crop_bottom),
                "label_bbox": box(left + 18, top + 18, left + 92, top + 62),
            }
        )

    return {
        "version": 2,
        "template_version": "subjective_sheet_v2",
        "mode": "subjective_handwriting_crop_only",
        "test_id": config["test_id"],
        "test_name": config["test_name"],
        "question_count": q_count,
        "answer_text_format": config["answer_text_format"],
        "page": page,
        "marker_style": {
            "size_px": marker_size,
            "inset_px": marker_inset,
            "quiet_zone_px": quiet_zone,
        },
        "layout_style": {
            "top_content_start_px": grid_top,
            "bottom_margin_px": height - grid_bottom,
            "column_gap_px": col_gap,
            "side_margin_px": side_margin,
            "row_gap_px": row_gap,
            "answer_box_inner_inset_px": int(layout_style.get("answer_box_inner_inset_px") or 0),
        },
        "box_style": {
            "columns": columns,
            "rows_per_column": rows_per_column,
            "box_height_px": box_height,
            "answer_area_inset_px": answer_area_inset,
        },
        "markers": markers,
        "answer_boxes": answer_boxes,
        "notes": [
            "Template v2 uses larger corner markers with quiet zones to improve photo alignment.",
            "Coordinates are in the generated page pixel space.",
            "Stage 1 stores crop boxes only; OCR and auto-grading are intentionally not included.",
        ],
    }


def draw_sheet(config: dict[str, Any], layout: dict[str, Any]) -> Image.Image:
    page = config["page"]
    width = int(page["width_px"])
    height = int(page["height_px"])
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title_font = load_font(56, bold=True)
    label_font = load_font(31)
    small_font = load_font(24)
    q_font = load_font(30, bold=True)

    for marker in layout["markers"].values():
        quiet = marker.get("quiet_zone") or marker["roi"]
        draw.rectangle([quiet["left"], quiet["top"], quiet["right"], quiet["bottom"]], fill="white")

    for marker in layout["markers"].values():
        roi = marker["roi"]
        draw.rectangle([roi["left"], roi["top"], roi["right"], roi["bottom"]], fill="black")

    marker_style = layout.get("marker_style") or {}
    header_x = int(marker_style.get("inset_px", 110)) + int(marker_style.get("size_px", 128)) + int(marker_style.get("quiet_zone_px", 70)) + 42
    header_x = max(340, header_x)
    right_limit = width - header_x

    draw.text((header_x, 126), "Subjective Answer Sheet v2", fill="black", font=title_font)
    draw.text((header_x, 206), f"Test: {config['test_name']}    ID: {config['test_id']}", fill="black", font=label_font)
    draw.text((header_x, 286), "Name:", fill="black", font=label_font)
    draw.line((header_x + 100, 322, header_x + 650, 322), fill="black", width=3)
    draw.text((header_x + 760, 286), "Student ID:", fill="black", font=label_font)
    draw.line((header_x + 945, 322, min(right_limit, header_x + 1490), 322), fill="black", width=3)
    draw.text(
        (header_x, 382),
        "Write one short answer per box. Keep all four black corner markers fully visible.",
        fill=(65, 65, 65),
        font=small_font,
    )
    draw.line((header_x, 482, right_limit, 482), fill=(160, 160, 160), width=2)

    for item in layout["answer_boxes"]:
        q = int(item["question"])
        outer = item["bbox"]
        draw.rectangle([outer["left"], outer["top"], outer["right"], outer["bottom"]], outline="black", width=3)
        draw.text((outer["left"] + 25, outer["top"] + 26), f"{q:02d}", fill="black", font=q_font)

    return image


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate a subjective answer sheet PNG/PDF and layout JSON.")
    parser.add_argument("--config", required=True, help="Path to subjective_sheet_config JSON.")
    parser.add_argument("--out", required=True, help="Output prefix, without extension.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config = read_config(Path(args.config))
    layout = build_layout(config)
    image = draw_sheet(config, layout)

    out_prefix = Path(args.out)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
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
