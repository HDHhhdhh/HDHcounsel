#!/usr/bin/env python
"""Crop subjective answer boxes from a scanned or synthetic sheet image."""

from __future__ import annotations

import argparse
import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image, ImageDraw, ImageFont


MARKER_ORDER = ("top_left", "top_right", "bottom_right", "bottom_left")


MARKER_PASS_CONFIGS: dict[str, dict[str, float | int | str | bool]] = {
    "strict": {
        "name": "strict",
        "dark_threshold": 135,
        "marker_search_ratio": 0.22,
        "min_fill": 0.42,
        "min_aspect": 0.72,
        "max_aspect": 1.38,
        "min_side_factor": 0.58,
        "max_side_factor": 1.75,
        "min_area_factor": 0.28,
        "max_area_factor": 2.30,
        "max_corner_distance_ratio": 0.72,
        "adaptive_margin": 24,
    },
    "normal": {
        "name": "normal",
        "dark_threshold": 165,
        "marker_search_ratio": 0.26,
        "min_fill": 0.32,
        "min_aspect": 0.62,
        "max_aspect": 1.55,
        "min_side_factor": 0.45,
        "max_side_factor": 2.20,
        "min_area_factor": 0.16,
        "max_area_factor": 3.00,
        "max_corner_distance_ratio": 0.82,
        "adaptive_margin": 34,
    },
    "tolerant": {
        "name": "tolerant",
        "dark_threshold": 195,
        "marker_search_ratio": 0.30,
        "min_fill": 0.22,
        "min_aspect": 0.50,
        "max_aspect": 1.80,
        "min_side_factor": 0.34,
        "max_side_factor": 2.75,
        "min_area_factor": 0.08,
        "max_area_factor": 4.20,
        "max_corner_distance_ratio": 0.92,
        "adaptive_margin": 46,
    },
}


def load_layout(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def page_size(layout: dict[str, Any]) -> tuple[int, int]:
    page = layout.get("page") or {}
    return int(page.get("width_px") or 0), int(page.get("height_px") or 0)


def scale_box(box: dict[str, int], sx: float, sy: float, width: int, height: int) -> tuple[int, int, int, int]:
    left = max(0, min(width, int(round(int(box["left"]) * sx))))
    top = max(0, min(height, int(round(int(box["top"]) * sy))))
    right = max(0, min(width, int(round(int(box["right"]) * sx))))
    bottom = max(0, min(height, int(round(int(box["bottom"]) * sy))))
    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)
    return left, top, right, bottom


def component_boxes(mask: np.ndarray, min_area: int) -> list[dict[str, Any]]:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    boxes: list[dict[str, Any]] = []
    ys, xs = np.nonzero(mask)

    for start_y, start_x in zip(ys.tolist(), xs.tolist()):
        if visited[start_y, start_x]:
            continue
        queue: deque[tuple[int, int]] = deque([(start_y, start_x)])
        visited[start_y, start_x] = True
        count = 0
        min_x = max_x = start_x
        min_y = max_y = start_y
        while queue:
            y, x = queue.popleft()
            count += 1
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)
            for ny in (y - 1, y, y + 1):
                if ny < 0 or ny >= height:
                    continue
                for nx in (x - 1, x, x + 1):
                    if nx < 0 or nx >= width or visited[ny, nx] or not mask[ny, nx]:
                        continue
                    visited[ny, nx] = True
                    queue.append((ny, nx))
        if count < min_area:
            continue
        area = max(1, (max_x - min_x + 1) * (max_y - min_y + 1))
        fill = count / area
        boxes.append(
            {
                "bbox": [int(min_x), int(min_y), int(max_x), int(max_y)],
                "area": int(count),
                "fill": round(float(fill), 4),
                "score": float(count * max(fill, 0.001)),
            }
        )
    return boxes


def corner_windows(width: int, height: int, ratio: float) -> dict[str, tuple[int, int, int, int]]:
    ratio = max(0.12, min(0.30, ratio))
    win_w = max(1, int(round(width * ratio)))
    win_h = max(1, int(round(height * ratio)))
    return {
        "top_left": (0, 0, win_w, win_h),
        "top_right": (width - win_w, 0, width, win_h),
        "bottom_left": (0, height - win_h, win_w, height),
        "bottom_right": (width - win_w, height - win_h, width, height),
    }


def marker_passes(mode: str) -> list[dict[str, float | int | str | bool]]:
    if mode == "auto":
        return [MARKER_PASS_CONFIGS["strict"], MARKER_PASS_CONFIGS["normal"], MARKER_PASS_CONFIGS["tolerant"]]
    return [MARKER_PASS_CONFIGS[mode]]


def local_dark_threshold(window: np.ndarray, global_threshold: int, adaptive: bool, margin: int) -> int:
    if not adaptive or window.size == 0:
        return int(global_threshold)
    percentile = float(np.percentile(window, 8))
    return int(max(35, min(global_threshold, percentile + margin)))


def detect_corner_markers(
    image: Image.Image,
    layout: dict[str, Any],
    *,
    dark_threshold: int,
    marker_search_ratio: float,
    marker_mode: str,
    adaptive_threshold: bool,
) -> dict[str, Any]:
    attempts = [
        _detect_corner_markers_single_pass(
            image,
            layout,
            dark_threshold=int(dark_threshold if marker_mode != "auto" else pass_config["dark_threshold"]),
            marker_search_ratio=float(marker_search_ratio if marker_mode != "auto" else pass_config["marker_search_ratio"]),
            pass_config=pass_config,
            adaptive_threshold=adaptive_threshold,
        )
        for pass_config in marker_passes(marker_mode)
    ]
    for attempt in attempts:
        validation = validate_marker_alignment(attempt, image.size, layout)
        attempt["validation"] = validation
        if validation.get("ok"):
            attempt["attempts"] = attempts
            return attempt

    best = max(attempts, key=lambda item: (len(item.get("points") or {}), -len(item.get("failures") or [])))
    if "validation" not in best:
        best["validation"] = validate_marker_alignment(best, image.size, layout)
    best["attempts"] = attempts
    return best


def _detect_corner_markers_single_pass(
    image: Image.Image,
    layout: dict[str, Any],
    *,
    dark_threshold: int,
    marker_search_ratio: float,
    pass_config: dict[str, float | int | str | bool],
    adaptive_threshold: bool,
) -> dict[str, Any]:
    gray = image.convert("L")
    width, height = gray.size
    arr = np.asarray(gray)
    layout_width, layout_height = page_size(layout)
    marker_size = float(next(iter((layout.get("markers") or {}).values())).get("size") or 92)
    expected_scale = min(width / max(layout_width, 1), height / max(layout_height, 1))
    expected_side = max(4.0, marker_size * expected_scale)
    expected_area = max(25.0, (marker_size * expected_scale) ** 2)
    min_area = max(20, int(expected_area * 0.08))
    windows = corner_windows(width, height, marker_search_ratio)
    target_points = marker_target_points(layout)
    scaled_expected_centers = {
        key: (
            target_points.get(key, (0.0, 0.0))[0] * width / max(layout_width, 1),
            target_points.get(key, (0.0, 0.0))[1] * height / max(layout_height, 1),
        )
        for key in MARKER_ORDER
    }
    corner_targets = {
        "top_left": (0.0, 0.0),
        "top_right": (float(width), 0.0),
        "bottom_left": (0.0, float(height)),
        "bottom_right": (float(width), float(height)),
    }

    points: dict[str, dict[str, float]] = {}
    details: dict[str, Any] = {}
    failures: list[str] = []
    rejected_candidates: list[dict[str, Any]] = []
    for key in ("top_left", "top_right", "bottom_left", "bottom_right"):
        x0, y0, x1, y1 = windows[key]
        crop = arr[y0:y1, x0:x1]
        threshold = local_dark_threshold(
            crop,
            int(dark_threshold),
            adaptive_threshold,
            int(pass_config["adaptive_margin"]),
        )
        boxes = component_boxes(crop < threshold, min_area=min_area)
        if not boxes:
            failures.append(f"{key}: no dark marker candidate")
            details[key] = {
                "window": [x0, y0, x1, y1],
                "component_count": 0,
                "accepted": None,
                "threshold": threshold,
            }
            continue

        def describe_candidate(candidate: dict[str, Any]) -> dict[str, Any]:
            bx0, by0, bx1, by1 = candidate["bbox"]
            comp_w = max(1, bx1 - bx0 + 1)
            comp_h = max(1, by1 - by0 + 1)
            abs_box = [x0 + bx0, y0 + by0, x0 + bx1, y0 + by1]
            cx = x0 + (bx0 + bx1) / 2
            cy = y0 + (by0 + by1) / 2
            aspect = comp_w / comp_h
            side = (comp_w + comp_h) / 2
            corner_x, corner_y = corner_targets[key]
            max_dist = max(1.0, ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
            corner_distance = ((cx - corner_x) ** 2 + (cy - corner_y) ** 2) ** 0.5
            expected_x, expected_y = scaled_expected_centers.get(key, (corner_x, corner_y))
            expected_center_distance = ((cx - expected_x) ** 2 + (cy - expected_y) ** 2) ** 0.5
            reasons: list[str] = []
            if not float(pass_config["min_aspect"]) <= aspect <= float(pass_config["max_aspect"]):
                reasons.append("aspect_not_square")
            if not expected_side * float(pass_config["min_side_factor"]) <= comp_w <= expected_side * float(pass_config["max_side_factor"]):
                reasons.append("width_out_of_range")
            if not expected_side * float(pass_config["min_side_factor"]) <= comp_h <= expected_side * float(pass_config["max_side_factor"]):
                reasons.append("height_out_of_range")
            if not expected_area * float(pass_config["min_area_factor"]) <= float(candidate["area"]) <= expected_area * float(pass_config["max_area_factor"]):
                reasons.append("area_out_of_range")
            if float(candidate.get("fill") or 0.0) < float(pass_config["min_fill"]):
                reasons.append("fill_too_low")
            if corner_distance / max_dist > float(pass_config["max_corner_distance_ratio"]):
                reasons.append("too_far_from_corner")
            return {
                "corner": key,
                "pass": str(pass_config["name"]),
                "bbox": abs_box,
                "center": {"x": round(float(cx), 3), "y": round(float(cy), 3)},
                "width": int(comp_w),
                "height": int(comp_h),
                "area": int(candidate["area"]),
                "fill": float(candidate.get("fill") or 0.0),
                "aspect": round(float(aspect), 4),
                "corner_distance_ratio": round(float(corner_distance / max_dist), 4),
                "expected_center_distance_ratio": round(float(expected_center_distance / max_dist), 4),
                "threshold": threshold,
                "reasons": reasons,
            }

        candidates = [describe_candidate(box) for box in boxes]
        accepted = [candidate for candidate in candidates if not candidate["reasons"]]
        for candidate in candidates:
            if candidate["reasons"]:
                rejected_candidates.append(candidate)

        if not accepted:
            failures.append(f"{key}: all marker candidates rejected")
            details[key] = {
                "window": [x0, y0, x1, y1],
                "component_count": len(boxes),
                "accepted": None,
                "rejected": candidates[:12],
                "threshold": threshold,
                "expected_side": round(float(expected_side), 3),
                "expected_area": round(float(expected_area), 3),
            }
            continue

        def marker_score(candidate: dict[str, Any]) -> float:
            aspect_score = min(candidate["aspect"], 1 / max(candidate["aspect"], 1e-9))
            side = (candidate["width"] + candidate["height"]) / 2
            side_score = max(0.0, 1.0 - abs(side - expected_side) / max(expected_side * 1.4, 1.0))
            area_score = max(0.0, 1.0 - abs(candidate["area"] - expected_area) / max(expected_area * 2.2, 1.0))
            fill_score = float(candidate.get("fill") or 0.0)
            proximity_score = max(0.0, 1.0 - candidate["corner_distance_ratio"])
            expected_center_score = max(0.0, 1.0 - candidate.get("expected_center_distance_ratio", 1.0))
            return (
                (aspect_score**2)
                * max(side_score, 0.05)
                * max(area_score, 0.05)
                * max(fill_score, 0.05)
                * max(proximity_score, 0.05)
                * max(expected_center_score, 0.12)
            )

        for candidate in candidates:
            candidate["score"] = round(float(marker_score(candidate)), 6)

        best = max(accepted, key=marker_score)
        best_score = marker_score(best)
        points[key] = {"x": best["center"]["x"], "y": best["center"]["y"]}
        details[key] = {
            "window": [x0, y0, x1, y1],
            "component_count": len(boxes),
            "accepted": best,
            "rejected": [candidate for candidate in candidates if candidate is not best][:12],
            "bbox": best["bbox"],
            "area": best["area"],
            "fill": best["fill"],
            "marker_score": round(float(best_score), 6),
            "threshold": threshold,
            "expected_side": round(float(expected_side), 3),
            "expected_area": round(float(expected_area), 3),
            "uses_layout_marker_targets": True,
        }

    return {
        "detected": all(key in points for key in MARKER_ORDER),
        "points": points,
        "details": details,
        "failures": failures,
        "rejected_candidates": rejected_candidates[:80],
        "pass": str(pass_config["name"]),
        "adaptive_threshold": adaptive_threshold,
        "dark_threshold": dark_threshold,
        "marker_search_ratio": marker_search_ratio,
    }


def marker_target_points(layout: dict[str, Any]) -> dict[str, tuple[float, float]]:
    points: dict[str, tuple[float, float]] = {}
    for key, marker in (layout.get("markers") or {}).items():
        roi = marker.get("roi") or {}
        if roi:
            x = (float(roi["left"]) + float(roi["right"])) / 2
            y = (float(roi["top"]) + float(roi["bottom"])) / 2
        else:
            size = float(marker.get("size") or 0)
            x = float(marker["x"]) + size / 2
            y = float(marker["y"]) + size / 2
        points[key] = (x, y)
    return points


def polygon_area(points: list[tuple[float, float]]) -> float:
    area = 0.0
    for index, (x1, y1) in enumerate(points):
        x2, y2 = points[(index + 1) % len(points)]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def distance(point_a: tuple[float, float], point_b: tuple[float, float]) -> float:
    return float(((point_a[0] - point_b[0]) ** 2 + (point_a[1] - point_b[1]) ** 2) ** 0.5)


def validate_marker_alignment(
    marker_result: dict[str, Any],
    image_size: tuple[int, int],
    layout: dict[str, Any],
) -> dict[str, Any]:
    width, height = image_size
    points_raw = marker_result.get("points") or {}
    accepted = marker_result.get("details") or {}
    rejected = marker_result.get("rejected_candidates") or []
    reasons: list[str] = []

    missing = [key for key in MARKER_ORDER if key not in points_raw]
    if missing:
        reasons.append(f"missing_markers:{','.join(missing)}")
        return {
            "ok": False,
            "reason": "; ".join(reasons),
            "accepted": points_raw,
            "accepted_details": accepted,
            "rejected_candidates": rejected,
        }

    tl = (float(points_raw["top_left"]["x"]), float(points_raw["top_left"]["y"]))
    tr = (float(points_raw["top_right"]["x"]), float(points_raw["top_right"]["y"]))
    br = (float(points_raw["bottom_right"]["x"]), float(points_raw["bottom_right"]["y"]))
    bl = (float(points_raw["bottom_left"]["x"]), float(points_raw["bottom_left"]["y"]))
    quad = [tl, tr, br, bl]

    if not (tl[0] < tr[0] - width * 0.16):
        reasons.append("top_markers_x_order_invalid")
    if not (bl[0] < br[0] - width * 0.16):
        reasons.append("bottom_markers_x_order_invalid")
    if not (tl[1] < bl[1] - height * 0.36):
        reasons.append("left_markers_y_order_invalid")
    if not (tr[1] < br[1] - height * 0.36):
        reasons.append("right_markers_y_order_invalid")

    top_y = max(tl[1], tr[1])
    bottom_y = min(bl[1], br[1])
    if top_y > height * 0.34:
        reasons.append("top_markers_not_near_page_top")
    if bottom_y < height * 0.64:
        reasons.append("bottom_markers_not_near_page_bottom")

    quad_area_ratio = polygon_area(quad) / max(width * height, 1)
    if quad_area_ratio < 0.24:
        reasons.append("marker_quad_area_too_small")

    top_width = distance(tl, tr)
    bottom_width = distance(bl, br)
    left_height = distance(tl, bl)
    right_height = distance(tr, br)
    avg_width = (top_width + bottom_width) / 2
    avg_height = (left_height + right_height) / 2
    projected_aspect = avg_width / max(avg_height, 1e-9)
    if not 0.40 <= projected_aspect <= 1.08:
        reasons.append("marker_quad_aspect_unlikely_for_a4")

    top_skew = abs(tl[1] - tr[1]) / max(avg_height, 1)
    bottom_skew = abs(bl[1] - br[1]) / max(avg_height, 1)
    if top_skew > 0.28:
        reasons.append("top_marker_skew_too_large")
    if bottom_skew > 0.28:
        reasons.append("bottom_marker_skew_too_large")

    try:
        matrix = layout_to_source_matrix(layout, marker_result)
        answer_boxes = layout.get("answer_boxes") or []
        if answer_boxes:
            first_top = min(transform_point(point, matrix)[1] for point in box_corners(answer_boxes[0]["bbox"]))
            last_bottom = max(transform_point(point, matrix)[1] for point in box_corners(answer_boxes[-1]["bbox"]))
            if top_y > first_top - height * 0.03:
                reasons.append("top_markers_overlap_answer_area")
            if bottom_y < last_bottom + height * 0.03:
                reasons.append("bottom_markers_overlap_answer_area")
    except Exception as exc:  # noqa: BLE001 - diagnostics should fail closed.
        reasons.append(f"answer_area_validation_failed:{exc}")

    return {
        "ok": not reasons,
        "reason": "; ".join(reasons),
        "accepted": points_raw,
        "accepted_details": accepted,
        "rejected_candidates": rejected,
        "quad_area_ratio": round(float(quad_area_ratio), 6),
        "projected_aspect": round(float(projected_aspect), 6),
        "top_skew": round(float(top_skew), 6),
        "bottom_skew": round(float(bottom_skew), 6),
    }


def homography_from_points(
    source_points: list[tuple[float, float]],
    target_points: list[tuple[float, float]],
) -> np.ndarray:
    if len(source_points) != 4 or len(target_points) != 4:
        raise ValueError("homography requires exactly four source and target points")
    rows = []
    values = []
    for (x, y), (u, v) in zip(source_points, target_points):
        rows.append([x, y, 1, 0, 0, 0, -u * x, -u * y])
        values.append(u)
        rows.append([0, 0, 0, x, y, 1, -v * x, -v * y])
        values.append(v)
    h = np.linalg.solve(np.asarray(rows, dtype=np.float64), np.asarray(values, dtype=np.float64))
    return np.asarray(
        [[h[0], h[1], h[2]], [h[3], h[4], h[5]], [h[6], h[7], 1.0]],
        dtype=np.float64,
    )


def warp_perspective(
    image: Image.Image,
    source_points: list[tuple[float, float]],
    target_points: list[tuple[float, float]],
    output_size: tuple[int, int],
    *,
    fill: int | tuple[int, int, int] = 255,
) -> Image.Image:
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    width, height = output_size
    source = np.asarray(image)
    channels = 1 if source.ndim == 2 else source.shape[2]
    if channels == 1:
        out = np.full((height, width), int(fill if isinstance(fill, int) else fill[0]), dtype=np.uint8)
    else:
        fill_tuple = fill if isinstance(fill, tuple) else (int(fill), int(fill), int(fill))
        out = np.zeros((height, width, channels), dtype=np.uint8)
        out[:, :] = fill_tuple[:channels]

    h_target_to_source = homography_from_points(target_points, source_points)
    xs = np.arange(width, dtype=np.float64)
    src_h, src_w = source.shape[:2]

    for y in range(height):
        denom = h_target_to_source[2, 0] * xs + h_target_to_source[2, 1] * y + h_target_to_source[2, 2]
        src_x = (h_target_to_source[0, 0] * xs + h_target_to_source[0, 1] * y + h_target_to_source[0, 2]) / denom
        src_y = (h_target_to_source[1, 0] * xs + h_target_to_source[1, 1] * y + h_target_to_source[1, 2]) / denom
        ix = np.rint(src_x).astype(np.int64)
        iy = np.rint(src_y).astype(np.int64)
        valid = (ix >= 0) & (ix < src_w) & (iy >= 0) & (iy < src_h)
        if channels == 1:
            out[y, valid] = source[iy[valid], ix[valid]]
        else:
            out[y, valid, :] = source[iy[valid], ix[valid], :]

    return Image.fromarray(out, mode=image.mode)


def warp_to_layout(image: Image.Image, layout: dict[str, Any], detected_markers: dict[str, Any]) -> Image.Image:
    width, height = page_size(layout)
    if width <= 0 or height <= 0:
        raise ValueError("layout page size is missing")
    target_points_all = marker_target_points(layout)
    source_points = [(detected_markers["points"][key]["x"], detected_markers["points"][key]["y"]) for key in MARKER_ORDER]
    target_points = [target_points_all[key] for key in MARKER_ORDER]
    return warp_perspective(image, source_points, target_points, (width, height), fill=255)


def transform_point(point: tuple[float, float], matrix: np.ndarray) -> tuple[float, float]:
    x, y = point
    denom = matrix[2, 0] * x + matrix[2, 1] * y + matrix[2, 2]
    if abs(denom) < 1e-9:
        return x, y
    out_x = (matrix[0, 0] * x + matrix[0, 1] * y + matrix[0, 2]) / denom
    out_y = (matrix[1, 0] * x + matrix[1, 1] * y + matrix[1, 2]) / denom
    return float(out_x), float(out_y)


def layout_to_source_matrix(layout: dict[str, Any], detected_markers: dict[str, Any]) -> np.ndarray:
    target_points_all = marker_target_points(layout)
    layout_points = [target_points_all[key] for key in MARKER_ORDER]
    source_points = [(detected_markers["points"][key]["x"], detected_markers["points"][key]["y"]) for key in MARKER_ORDER]
    return homography_from_points(layout_points, source_points)


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


def box_corners(box: dict[str, int]) -> list[tuple[float, float]]:
    return [
        (float(box["left"]), float(box["top"])),
        (float(box["right"]), float(box["top"])),
        (float(box["right"]), float(box["bottom"])),
        (float(box["left"]), float(box["bottom"])),
    ]


def draw_polyline(draw: ImageDraw.ImageDraw, points: list[tuple[float, float]], fill: str, width: int) -> None:
    int_points = [(int(round(x)), int(round(y))) for x, y in points]
    draw.line(int_points + [int_points[0]], fill=fill, width=width)


def create_source_overlay(
    image: Image.Image,
    layout: dict[str, Any],
    marker_result: dict[str, Any],
    *,
    correction: str,
    marker_validation: dict[str, Any],
) -> Image.Image:
    overlay = image.copy().convert("RGB")
    draw = ImageDraw.Draw(overlay)
    font = load_font(max(14, min(34, overlay.width // 42)), bold=True)

    alignment_ok = bool(marker_validation.get("ok"))
    if correction == "homography" and alignment_ok:
        try:
            matrix = layout_to_source_matrix(layout, marker_result)
        except Exception:
            matrix = None
    else:
        matrix = None

    width, height = overlay.size
    layout_width, layout_height = page_size(layout)
    sx = width / max(layout_width, 1)
    sy = height / max(layout_height, 1)

    for item in layout.get("answer_boxes") or []:
        question = int(item["question"])
        crop_box = item.get("crop_bbox") or item.get("bbox")
        if matrix is not None:
            points = [transform_point(point, matrix) for point in box_corners(crop_box)]
        else:
            left, top, right, bottom = scale_box(crop_box, sx, sy, width, height)
            points = [(left, top), (right, top), (right, bottom), (left, bottom)]
        draw_polyline(draw, points, fill="#ffcc00" if alignment_ok else "#ff9900", width=max(2, overlay.width // 420))
        label_x = int(round(points[0][0]))
        label_y = int(round(points[0][1]))
        draw.rectangle([label_x, label_y, label_x + 72, label_y + 28], fill="#111111")
        draw.text((label_x + 4, label_y + 2), f"Q{question:03d}", fill="#ffffff", font=font)

    small_font = load_font(max(12, min(24, overlay.width // 55)), bold=True)
    for candidate in (marker_result.get("rejected_candidates") or [])[:24]:
        bbox = candidate.get("bbox") or []
        if len(bbox) != 4:
            continue
        color = "#888888" if "aspect_not_square" in candidate.get("reasons", []) else "#ff9900"
        draw.rectangle([int(v) for v in bbox], outline=color, width=max(2, overlay.width // 520))
        label = f"{candidate.get('pass')} {candidate.get('score')} " + (",".join(candidate.get("reasons", [])[:2]) or "rejected")
        draw.text((int(bbox[0]), int(bbox[1]) - 18), label[:34], fill=color, font=small_font)

    for key, point in (marker_result.get("points") or {}).items():
        x = int(round(float(point["x"])))
        y = int(round(float(point["y"])))
        r = max(8, overlay.width // 95)
        draw.ellipse([x - r, y - r, x + r, y + r], outline="#ff3333", width=max(3, overlay.width // 300))
        draw.line([x - r, y, x + r, y], fill="#ff3333", width=max(2, overlay.width // 420))
        draw.line([x, y - r, x, y + r], fill="#ff3333", width=max(2, overlay.width // 420))
        detail = (marker_result.get("details") or {}).get(key) or {}
        accepted = detail.get("accepted") or {}
        label = f"{key} {marker_result.get('pass')} {accepted.get('score', detail.get('marker_score', ''))}"
        draw.text((x + r + 4, y - r), label[:36], fill="#ff3333", font=font)

    banner = f"alignment_ok={alignment_ok} correction={correction} pass={marker_result.get('pass')}"
    if not alignment_ok:
        reason = str(marker_validation.get("reason") or "marker validation failed")
        draw.rectangle([0, 0, width, max(64, height // 16)], fill=(150, 0, 0))
        draw.text((18, 12), "INVALID ALIGNMENT - RETAKE PHOTO REQUIRED", fill="white", font=font)
        draw.text((18, 42), reason[:110], fill="white", font=small_font)
        watermark_font = load_font(max(42, width // 11), bold=True)
        draw.text((width * 0.10, height * 0.45), "INVALID ALIGNMENT", fill=(220, 0, 0), font=watermark_font)
    else:
        draw.rectangle([0, 0, min(width, 420), max(34, height // 34)], fill=(0, 110, 0))
        draw.text((12, 6), banner, fill="white", font=small_font)

    return overlay


def relative_path(path: Path, base: Path) -> str:
    try:
        return path.resolve().relative_to(base.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Crop subjective answer boxes from a sheet image.")
    parser.add_argument("--image", required=True, help="Scanned/photo/synthetic filled sheet image.")
    parser.add_argument("--layout", required=True, help="Path to .layout.json.")
    parser.add_argument("--out-dir", required=True, help="Directory for q001.png, q002.png, ... crops.")
    parser.add_argument("--result-out", required=True, help="Output result JSON path.")
    parser.add_argument("--corrected-out", help="Optional full-page corrected image output path.")
    parser.add_argument("--source-overlay-out", help="Optional source image overlay path for marker and crop diagnostics.")
    parser.add_argument("--disable-perspective", action="store_true", help="Disable marker-based homography correction.")
    parser.add_argument("--dark-threshold", type=int, default=150, help="Dark pixel threshold for marker diagnostics.")
    parser.add_argument("--marker-search-ratio", type=float, default=0.22, help="Corner search window ratio.")
    parser.add_argument("--marker-mode", choices=["strict", "normal", "tolerant", "auto"], default="auto", help="Marker detection pass mode.")
    parser.add_argument("--adaptive-threshold", dest="adaptive_threshold", action="store_true", default=True, help="Use per-corner adaptive dark thresholds.")
    parser.add_argument("--no-adaptive-threshold", dest="adaptive_threshold", action="store_false", help="Disable per-corner adaptive dark thresholds.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    layout = load_layout(Path(args.layout))
    image = Image.open(args.image).convert("RGB")
    original_width, original_height = image.size
    layout_width, layout_height = page_size(layout)
    if layout_width <= 0:
        layout_width = original_width
    if layout_height <= 0:
        layout_height = original_height

    marker_result = detect_corner_markers(
        image,
        layout,
        dark_threshold=int(args.dark_threshold),
        marker_search_ratio=float(args.marker_search_ratio),
        marker_mode=str(args.marker_mode),
        adaptive_threshold=bool(args.adaptive_threshold),
    )
    marker_validation = validate_marker_alignment(marker_result, (original_width, original_height), layout)

    corrected_image = image
    correction = "marker_validation_failed"
    fallback = False
    fallback_reason = ""
    alignment_ok = False
    corrected_image_rel: str | None = None
    source_overlay_rel: str | None = None
    warning_details: list[dict[str, Any]] = []

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result_path = Path(args.result_out)
    result_path.parent.mkdir(parents=True, exist_ok=True)
    result_base = result_path.parent

    if not marker_validation.get("ok"):
        fallback_reason = str(marker_validation.get("reason") or "marker_validation_failed")
        warning_details.append({"code": "marker_validation_failed", "message": fallback_reason})
        warning_details.append({"code": "retake_photo_required"})
    elif args.disable_perspective:
        correction = "perspective_disabled"
        fallback_reason = "perspective_disabled"
        warning_details.append({"code": "perspective_disabled"})
        warning_details.append({"code": "retake_photo_required"})
    else:
        try:
            corrected_image = warp_to_layout(image, layout, marker_result)
            correction = "homography"
            alignment_ok = True
        except Exception as exc:  # noqa: BLE001 - dry-run tool should fail open.
            correction = "perspective_correction_failed"
            fallback_reason = f"perspective_correction_failed: {exc}"
            warning_details.append({"code": "perspective_correction_failed", "message": str(exc)})
            warning_details.append({"code": "retake_photo_required"})

    if args.corrected_out:
        corrected_path = Path(args.corrected_out)
        corrected_path.parent.mkdir(parents=True, exist_ok=True)
        if alignment_ok:
            corrected_image.save(corrected_path)
            corrected_image_rel = relative_path(corrected_path, result_base)
        elif corrected_path.exists():
            corrected_path.unlink()

    source_overlay_path = Path(args.source_overlay_out) if args.source_overlay_out else result_path.parent / "source_overlay.png"
    source_overlay_path.parent.mkdir(parents=True, exist_ok=True)
    source_overlay = create_source_overlay(image, layout, marker_result, correction=correction, marker_validation=marker_validation)
    source_overlay.save(source_overlay_path)
    source_overlay_rel = relative_path(source_overlay_path, result_base)

    width, height = corrected_image.size
    sx = width / layout_width
    sy = height / layout_height

    for stale_crop in out_dir.glob("q*.png"):
        stale_crop.unlink()

    items: list[dict[str, Any]] = []
    if alignment_ok:
        for item in layout.get("answer_boxes") or []:
            question = int(item["question"])
            crop_box = item.get("crop_bbox") or item.get("bbox")
            scaled = scale_box(crop_box, sx, sy, width, height)
            crop = corrected_image.crop(scaled)
            crop_path = out_dir / f"q{question:03d}.png"
            crop.save(crop_path)
            items.append(
                {
                    "question": question,
                    "cropPath": relative_path(crop_path, result_base),
                    "recognized": None,
                    "final": None,
                    "status": "pending_recognition",
                    "bbox": [int(value) for value in scaled],
                }
            )

    result = {
        "ok": alignment_ok,
        "status": "pending_recognition" if alignment_ok else "needs_retake",
        "alignment_ok": alignment_ok,
        "mode": "subjective_handwriting_crop_only",
        "test_id": layout.get("test_id"),
        "test_name": layout.get("test_name"),
        "input_image": str(Path(args.image)),
        "answersText": None,
        "items": items,
        "preprocess": {
            "alignment_ok": alignment_ok,
            "marker_detected": alignment_ok,
            "raw_marker_detected": bool(marker_result["detected"]),
            "marker_validation": marker_validation,
            "marker_pass": marker_result.get("pass"),
            "marker_mode": str(args.marker_mode),
            "adaptive_threshold": bool(args.adaptive_threshold),
            "marker_attempts": [
                {
                    "pass": attempt.get("pass"),
                    "detected": attempt.get("detected"),
                    "point_count": len(attempt.get("points") or {}),
                    "validation_ok": (attempt.get("validation") or {}).get("ok"),
                    "validation_reason": (attempt.get("validation") or {}).get("reason"),
                    "failures": attempt.get("failures") or [],
                }
                for attempt in (marker_result.get("attempts") or [])
            ],
            "fallback": fallback,
            "fallback_reason": fallback_reason,
            "correction": correction,
            "note": "Crops are taken from the corrected page image when homography succeeds; OCR and recognition review are deferred.",
            "marker_points": marker_result.get("points") or {},
            "marker_failures": marker_result.get("failures") or [],
            "image_size": {"width_px": original_width, "height_px": original_height},
            "layout_size": {"width_px": layout_width, "height_px": layout_height},
            "scale_x": round(original_width / layout_width, 6),
            "scale_y": round(original_height / layout_height, 6),
            "corrected_image": corrected_image_rel,
            "source_overlay": source_overlay_rel,
        },
        "diagnostics": {
            "crop_basis_size": {"width_px": width, "height_px": height},
            "layout_size": {"width_px": layout_width, "height_px": layout_height},
            "scale": {"x": round(sx, 6), "y": round(sy, 6)},
            "crop_count": len(items),
        },
        "warnings": ["ocr_not_connected", *[item["code"] for item in warning_details]],
        "warning_details": warning_details,
    }
    result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(items)} crops to {out_dir}")
    print(f"Wrote {result_path}")
    print(f"Wrote {source_overlay_path}")
    print(f"alignment_ok={alignment_ok}")
    print(f"marker_detected={result['preprocess']['marker_detected']} raw_marker_detected={result['preprocess']['raw_marker_detected']}")
    print(f"correction={correction}")
    print(f"fallback={fallback}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
