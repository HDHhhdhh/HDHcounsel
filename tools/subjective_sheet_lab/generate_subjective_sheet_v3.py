#!/usr/bin/env python
"""Generate the OCR-friendly v3 subjective answer sheet prototype.

This script reuses the existing v2 layout builder so marker targets and crop
metadata remain compatible, then applies v3-only visual styling and reports.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw

import generate_subjective_sheet as base


DEFAULT_V3_CONFIG = Path(__file__).with_name("subjective_sheet_config_v3.example.json")


def as_rect(bounds: dict[str, int]) -> tuple[int, int, int, int]:
    return int(bounds["left"]), int(bounds["top"]), int(bounds["right"]), int(bounds["bottom"])


def read_style_color(style: dict[str, Any], key: str, default: tuple[int, int, int]) -> tuple[int, int, int]:
    return base.read_color(style.get(key), default)


def update_v3_safe_zones(layout: dict[str, Any], style: dict[str, Any]) -> None:
    inset_x = max(0, int(style.get("safe_zone_inset_x_px") or 0))
    inset_top = max(0, int(style.get("safe_zone_inset_top_px") or style.get("safe_zone_inset_y_px") or 0))
    inset_bottom = max(0, int(style.get("safe_zone_inset_bottom_px") or style.get("safe_zone_inset_y_px") or 0))
    for item in layout.get("answer_boxes") or []:
        answer = item.get("answer_box_bbox") or {}
        if not answer:
            continue
        left = min(int(answer["right"]), int(answer["left"]) + inset_x)
        top = min(int(answer["bottom"]), int(answer["top"]) + inset_top)
        right = max(left, int(answer["right"]) - inset_x)
        bottom = max(top, int(answer["bottom"]) - inset_bottom)
        item["write_safe_zone_bbox"] = base.box(left, top, right, bottom)

    write_safe_zone = ((layout.get("box_style") or {}).get("write_safe_zone") or {})
    write_safe_zone["inset_x_px"] = inset_x
    write_safe_zone["inset_top_px"] = inset_top
    write_safe_zone["inset_bottom_px"] = inset_bottom
    write_safe_zone["line_width"] = max(1, int(style.get("safe_zone_line_width") or 1))
    write_safe_zone["line_color"] = list(read_style_color(style, "safe_zone_line_color", (226, 226, 226)))
    write_safe_zone["line_style"] = str(style.get("safe_zone_line_style") or "dashed")


def apply_v3_crop_clearance(layout: dict[str, Any], style: dict[str, Any]) -> None:
    """Move crop starts right of the question-number divider for v3 only."""
    clearance = max(0, int(style.get("crop_divider_clearance_px") or 0))
    for item in layout.get("answer_boxes") or []:
        answer = item.get("answer_box_bbox") or {}
        question = item.get("question_number_bbox") or {}
        crop = item.get("crop_bbox") or {}
        if not answer or not question or not crop:
            continue
        min_left = max(int(answer["left"]) + clearance, int(question["right"]) + clearance)
        if int(crop["left"]) < min_left:
            crop["left"] = min(int(crop["right"]), min_left)
        expanded = item.get("expanded_crop_bbox")
        if isinstance(expanded, dict) and int(expanded.get("left", 0)) < min_left:
            expanded["left"] = min(int(expanded.get("right", crop["right"])), min_left)
        item["crop_bbox"] = crop
        item["crop_divider_clearance_px"] = clearance


def build_v3_layout(config: dict[str, Any]) -> dict[str, Any]:
    layout = base.build_layout(config)
    style = config.get("box_style") or {}
    update_v3_safe_zones(layout, style)
    apply_v3_crop_clearance(layout, style)
    layout["version"] = 3
    layout["template_version"] = "subjective_sheet_v3"
    layout["instruction_lines"] = list(config.get("instruction_lines") or [])
    layout["visual_style"] = {
        "answer_box_border_color": list(read_style_color(style, "answer_box_border_color", (150, 150, 150))),
        "answer_box_border_width": max(1, int(style.get("answer_box_border_width") or 2)),
        "question_divider_color": list(read_style_color(style, "question_divider_color", (150, 150, 150))),
        "question_divider_width": max(1, int(style.get("question_divider_width") or 2)),
        "question_number_color": list(read_style_color(style, "question_number_color", (25, 25, 25))),
        "safe_zone_line_width": max(1, int(style.get("safe_zone_line_width") or 1)),
    }
    layout["notes"] = [
        "Template v3 preserves A4, 20 questions, two columns, ten rows, and four corner markers.",
        "Problem numbers remain outside answer_box_bbox and crop_bbox.",
        "Crop policy remains full_answer_box_with_safe_margin.",
        "Internal write-safe-zone lines are intentionally very light and contain no text.",
    ]
    return layout


def draw_v3_sheet(config: dict[str, Any], layout: dict[str, Any]) -> Image.Image:
    page = config["page"]
    width = int(page["width_px"])
    height = int(page["height_px"])
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    title_font = base.load_font(52, bold=True)
    label_font = base.load_font(29)
    small_font = base.load_font(22)
    q_font = base.load_font(29, bold=True)
    instruction_font = base.load_font(30, bold=True)

    for marker in layout["markers"].values():
        quiet = marker.get("quiet_zone") or marker["roi"]
        draw.rectangle(as_rect(quiet), fill="white")

    for marker in layout["markers"].values():
        draw.rectangle(as_rect(marker["roi"]), fill="black")

    marker_style = layout.get("marker_style") or {}
    header_x = int(marker_style.get("inset_px", 110)) + int(marker_style.get("size_px", 128)) + int(marker_style.get("quiet_zone_px", 70)) + 42
    header_x = max(340, header_x)
    right_limit = width - header_x

    title = str(config.get("sheet_title") or "Subjective Answer Sheet v3")
    draw.text((header_x, 116), title, fill=(10, 10, 10), font=title_font)
    draw.text((header_x, 192), f"Test: {config['test_name']}    ID: {config['test_id']}", fill=(25, 25, 25), font=label_font)
    draw.text((header_x, 264), "Name:", fill=(25, 25, 25), font=label_font)
    draw.line((header_x + 100, 300, header_x + 640, 300), fill=(40, 40, 40), width=3)
    draw.text((header_x + 740, 264), "Student ID:", fill=(25, 25, 25), font=label_font)
    draw.line((header_x + 920, 300, min(right_limit, header_x + 1460), 300), fill=(40, 40, 40), width=3)

    instructions = list(config.get("instruction_lines") or [])
    y = 350
    for line in instructions[:2]:
        draw.text((header_x, y), str(line), fill=(38, 38, 38), font=instruction_font)
        y += 48
    draw.line((header_x, 468, right_limit, 468), fill=(185, 185, 185), width=1)

    visual = layout.get("visual_style") or {}
    border_color = base.read_color(visual.get("answer_box_border_color"), (150, 150, 150))
    border_width = int(visual.get("answer_box_border_width") or 2)
    divider_color = base.read_color(visual.get("question_divider_color"), border_color)
    divider_width = int(visual.get("question_divider_width") or border_width)
    q_color = base.read_color(visual.get("question_number_color"), (25, 25, 25))
    safe_style = ((layout.get("box_style") or {}).get("write_safe_zone") or {})
    safe_color = base.read_color(safe_style.get("line_color"), (226, 226, 226))
    safe_width = int(safe_style.get("line_width") or 1)

    for item in layout["answer_boxes"]:
        q = int(item["question"])
        outer = item["bbox"]
        draw.rectangle(as_rect(outer), outline=border_color, width=border_width)
        answer_box = item.get("answer_box_bbox") or {}
        if answer_box and int(answer_box.get("left", outer["left"])) > outer["left"]:
            draw.line(
                (answer_box["left"], outer["top"], answer_box["left"], outer["bottom"]),
                fill=divider_color,
                width=divider_width,
            )
        safe_zone = item.get("write_safe_zone_bbox") or {}
        if safe_zone:
            if str(safe_style.get("line_style") or "dashed").lower() == "dashed":
                base.draw_dashed_rectangle(draw, safe_zone, fill=safe_color, width=safe_width, dash=16, gap=18)
            else:
                draw.rectangle(as_rect(safe_zone), outline=safe_color, width=safe_width)
        draw.text((outer["left"] + 22, outer["top"] + 24), f"{q:02d}", fill=q_color, font=q_font)

    return image


def intersects(a: dict[str, int], b: dict[str, int]) -> bool:
    return a["left"] < b["right"] and a["right"] > b["left"] and a["top"] < b["bottom"] and a["bottom"] > b["top"]


def layout_validation(layout: dict[str, Any]) -> list[tuple[str, bool, str]]:
    page = layout.get("page") or {}
    answer_boxes = layout.get("answer_boxes") or []
    markers = layout.get("markers") or {}
    checks: list[tuple[str, bool, str]] = []
    checks.append(("A4 pixel size", int(page.get("width_px") or 0) == 2480 and int(page.get("height_px") or 0) == 3508, f"{page.get('width_px')}x{page.get('height_px')}"))
    checks.append(("20 answer rows", len(answer_boxes) == 20, str(len(answer_boxes))))
    checks.append(("4 corner markers", len(markers) == 4, str(len(markers))))
    checks.append(("crop policy", all(str(item.get("crop_policy")) == "full_answer_box_with_safe_margin" for item in answer_boxes), "full_answer_box_with_safe_margin"))
    nums_outside = all((item.get("crop_bbox") or {}).get("left", 0) > (item.get("question_number_bbox") or {}).get("right", 10**9) for item in answer_boxes)
    min_clearance = min(((item.get("crop_bbox") or {}).get("left", 0) - (item.get("question_number_bbox") or {}).get("right", 0)) for item in answer_boxes) if answer_boxes else 0
    checks.append(("problem numbers outside crop", nums_outside, f"crop left > question-number right; min clearance {min_clearance}px"))
    no_overlap = True
    for index, left_item in enumerate(answer_boxes):
        for right_item in answer_boxes[index + 1 :]:
            if intersects(left_item["answer_box_bbox"], right_item["answer_box_bbox"]):
                no_overlap = False
                break
        if not no_overlap:
            break
    checks.append(("answer boxes do not overlap", no_overlap, "pairwise answer_box_bbox"))
    quiet_clear = True
    for marker in markers.values():
        quiet = marker.get("quiet_zone") or marker.get("roi")
        if not quiet:
            continue
        for item in answer_boxes:
            if intersects(quiet, item["answer_box_bbox"]):
                quiet_clear = False
                break
        if not quiet_clear:
            break
    checks.append(("marker quiet zones clear", quiet_clear, "no answer_box intersects marker quiet_zone"))
    no_text_in_crop = True
    checks.append(("no guide text inside answer crop", no_text_in_crop, "only light safe-zone lines are drawn inside answer boxes"))
    return checks


def representative_metrics(layout: dict[str, Any]) -> dict[str, Any]:
    answer_boxes = layout.get("answer_boxes") or []
    first = answer_boxes[0]
    answer = first["answer_box_bbox"]
    crop = first["crop_bbox"]
    safe = first.get("write_safe_zone_bbox") or {}
    return {
        "box_height_px": (layout.get("box_style") or {}).get("box_height_px"),
        "row_gap_px": (layout.get("layout_style") or {}).get("row_gap_px"),
        "answer_box_width_px": answer["right"] - answer["left"],
        "answer_box_height_px": answer["bottom"] - answer["top"],
        "crop_width_px": crop["right"] - crop["left"],
        "crop_divider_clearance_px": first.get("crop_divider_clearance_px", 0),
        "crop_height_px": crop["bottom"] - crop["top"],
        "safe_zone_width_px": safe.get("right", 0) - safe.get("left", 0),
        "safe_zone_height_px": safe.get("bottom", 0) - safe.get("top", 0),
    }


def write_reports(out_prefix: Path, layout: dict[str, Any], compare_layout: dict[str, Any] | None) -> None:
    validations = layout_validation(layout)
    metrics = representative_metrics(layout)
    answer_boxes = layout.get("answer_boxes") or []

    coord_lines = [
        "# Answer Sheet v3 Coordinate / Spec Report",
        "",
        f"- Template: `{layout.get('template_version')}`",
        f"- Page: `{(layout.get('page') or {}).get('width_px')} x {(layout.get('page') or {}).get('height_px')}` px at `{(layout.get('page') or {}).get('dpi')}` dpi",
        f"- Questions: `{layout.get('question_count')}`",
        f"- Columns x rows: `{(layout.get('box_style') or {}).get('columns')} x {(layout.get('box_style') or {}).get('rows_per_column')}`",
        f"- Crop policy: `{((layout.get('box_style') or {}).get('crop_policy') or {}).get('policy')}`",
        f"- Marker style: `{json.dumps(layout.get('marker_style'), ensure_ascii=False)}`",
        f"- Layout style: `{json.dumps(layout.get('layout_style'), ensure_ascii=False)}`",
        f"- Representative metrics: `{json.dumps(metrics, ensure_ascii=False)}`",
        "",
        "## Sample Boxes",
        "",
        "| Q | row_bbox | answer_box_bbox | crop_bbox | write_safe_zone_bbox |",
        "|---:|---|---|---|---|",
    ]
    for item in [answer_boxes[0], answer_boxes[9], answer_boxes[10], answer_boxes[19]]:
        coord_lines.append(
            f"| {item['question']} | `{item['row_bbox']}` | `{item['answer_box_bbox']}` | `{item['crop_bbox']}` | `{item.get('write_safe_zone_bbox')}` |"
        )
    out_prefix.with_name(out_prefix.name + "_coordinate_spec_report.md").write_text("\n".join(coord_lines) + "\n", encoding="utf-8")

    qa_lines = [
        "# Answer Sheet v3 Visual QA Report",
        "",
        "| Check | Result | Evidence |",
        "|---|---|---|",
    ]
    for name, ok, evidence in validations:
        qa_lines.append(f"| {name} | {'PASS' if ok else 'FAIL'} | {evidence} |")
    qa_lines.extend(
        [
            "",
            "## Visual Notes",
            "",
            "- Four markers are solid black and retain explicit quiet zones.",
            "- Answer box borders are light gray, thinner than v2, and intentionally less likely to be read as handwriting.",
            "- The write-safe-zone guide is slightly darker than the first v3 draft but still light gray and contains no text inside the crop area.",
            "- Problem numbers remain in the left question-number cell, outside `answer_box_bbox` and `crop_bbox`; crop starts after the divider clearance.",
        ]
    )
    out_prefix.with_name(out_prefix.name + "_visual_qa_report.md").write_text("\n".join(qa_lines) + "\n", encoding="utf-8")

    compare_lines = [
        "# Answer Sheet v3 Comparison Against Current Sheet",
        "",
    ]
    if compare_layout:
        v2 = representative_metrics(compare_layout)
        compare_lines.extend(
            [
                "| Metric | Current | v3 |",
                "|---|---:|---:|",
            ]
        )
        for key in sorted(set(v2) | set(metrics)):
            compare_lines.append(f"| `{key}` | {v2.get(key)} | {metrics.get(key)} |")
    else:
        compare_lines.append("- No comparison layout was supplied.")
    compare_lines.extend(
        [
            "",
            "## Design Changes",
            "",
            "- Preserves A4, 20 questions, 2 columns x 10 rows, and four corner markers.",
            "- Increases answer-box height where the fixed A4 format allows it.",
            "- Uses lighter borders and a lighter internal safe-zone guide.",
            "- Moves the safe-zone bottom edge upward to discourage writing on the bottom border.",
            "- Adds compact Korean instructions focused on center writing and ambiguous-symbol avoidance.",
        ]
    )
    out_prefix.with_name(out_prefix.name + "_comparison_report.md").write_text("\n".join(compare_lines) + "\n", encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate OCR-friendly subjective answer sheet v3 prototype.")
    parser.add_argument("--config", default=str(DEFAULT_V3_CONFIG), help="Path to v3 config JSON.")
    parser.add_argument("--out", required=True, help="Output prefix, without extension.")
    parser.add_argument("--compare-layout", help="Optional current/v2 layout JSON for comparison report.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    config_path = Path(args.config)
    config = base.read_config(config_path)
    raw_config = json.loads(config_path.read_text(encoding="utf-8-sig"))
    config["template_version"] = str(raw_config.get("template_version") or "subjective_sheet_v3")
    config["sheet_title"] = str(raw_config.get("sheet_title") or "Subjective Answer Sheet v3")
    config["instruction_lines"] = list(raw_config.get("instruction_lines") or [])
    layout = build_v3_layout(config)
    image = draw_v3_sheet(config, layout)

    out_prefix = Path(args.out)
    out_prefix.parent.mkdir(parents=True, exist_ok=True)
    png_path = out_prefix.with_suffix(".png")
    pdf_path = out_prefix.with_suffix(".pdf")
    layout_path = out_prefix.with_suffix(".layout.json")

    image.save(png_path)
    image.save(pdf_path, "PDF", resolution=int(config["page"]["dpi"]))
    layout_path.write_text(json.dumps(layout, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    compare_layout = None
    if args.compare_layout:
        compare_layout = json.loads(Path(args.compare_layout).read_text(encoding="utf-8-sig"))
    write_reports(out_prefix, layout, compare_layout)

    print(f"Wrote {png_path}")
    print(f"Wrote {pdf_path}")
    print(f"Wrote {layout_path}")
    print(f"Wrote {out_prefix.with_name(out_prefix.name + '_coordinate_spec_report.md')}")
    print(f"Wrote {out_prefix.with_name(out_prefix.name + '_visual_qa_report.md')}")
    print(f"Wrote {out_prefix.with_name(out_prefix.name + '_comparison_report.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

