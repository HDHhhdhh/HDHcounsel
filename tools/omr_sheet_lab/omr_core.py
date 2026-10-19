"""Core OMR image utilities for the standalone sheet lab.

The functions here intentionally use only Pillow, numpy, and the standard
library. They avoid OpenCV so the prototype can run in the current environment.
"""

from __future__ import annotations

import json
from collections import deque
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image


MARKER_ORDER = ("top_left", "top_right", "bottom_right", "bottom_left")


def load_layout(path: str | Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8-sig"))


def page_size(layout: dict[str, Any]) -> tuple[int, int]:
    page = layout.get("page") or {}
    return int(page.get("width_px") or 0), int(page.get("height_px") or 0)


def scale_box(
    box: dict[str, int],
    sx: float,
    sy: float,
    width: int,
    height: int,
) -> tuple[int, int, int, int]:
    left = max(0, min(width, int(round(box["left"] * sx))))
    top = max(0, min(height, int(round(box["top"] * sy))))
    right = max(0, min(width, int(round(box["right"] * sx))))
    bottom = max(0, min(height, int(round(box["bottom"] * sy))))
    if right <= left:
        right = min(width, left + 1)
    if bottom <= top:
        bottom = min(height, top + 1)
    return left, top, right, bottom


def compute_dark_ratio(gray_array: np.ndarray, roi: tuple[int, int, int, int], threshold: int) -> float:
    left, top, right, bottom = roi
    crop = gray_array[top:bottom, left:right]
    if crop.size == 0:
        return 0.0
    return float(np.mean(crop < threshold))


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


def _corner_windows(width: int, height: int, ratio: float) -> dict[str, tuple[int, int, int, int]]:
    ratio = max(0.12, min(0.45, float(ratio)))
    win_w = max(1, int(round(width * ratio)))
    win_h = max(1, int(round(height * ratio)))
    return {
        "top_left": (0, 0, win_w, win_h),
        "top_right": (width - win_w, 0, width, win_h),
        "bottom_left": (0, height - win_h, win_w, height),
        "bottom_right": (width - win_w, height - win_h, width, height),
    }


def _component_boxes(mask: np.ndarray, min_area: int) -> list[dict[str, float]]:
    height, width = mask.shape
    visited = np.zeros(mask.shape, dtype=bool)
    boxes: list[dict[str, float]] = []
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
            if x < min_x:
                min_x = x
            if x > max_x:
                max_x = x
            if y < min_y:
                min_y = y
            if y > max_y:
                max_y = y

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
        box_area = max(1, (max_x - min_x + 1) * (max_y - min_y + 1))
        fill = count / box_area
        boxes.append(
            {
                "area": float(count),
                "bbox": (int(min_x), int(min_y), int(max_x), int(max_y)),
                "fill": float(fill),
                "score": float(count * max(fill, 0.001)),
            }
        )
    return boxes


def detect_corner_markers(
    image: Image.Image,
    layout: dict[str, Any],
    *,
    dark_threshold: int = 150,
    marker_search_ratio: float = 0.28,
) -> dict[str, Any]:
    gray = image.convert("L")
    width, height = gray.size
    arr = np.asarray(gray)
    layout_width, layout_height = page_size(layout)
    target_points = marker_target_points(layout)
    target_marker_size = float(next(iter((layout.get("markers") or {}).values())).get("size") or 92)
    expected_scale = min(width / max(layout_width, 1), height / max(layout_height, 1))
    expected_area = max(25.0, (target_marker_size * expected_scale) ** 2)
    min_area = max(20, int(expected_area * 0.08))

    windows = _corner_windows(width, height, marker_search_ratio)
    points: dict[str, dict[str, float]] = {}
    confidences: dict[str, float] = {}
    details: dict[str, Any] = {}
    failures: list[str] = []

    for key in ("top_left", "top_right", "bottom_left", "bottom_right"):
        x0, y0, x1, y1 = windows[key]
        crop = arr[y0:y1, x0:x1]
        mask = crop < dark_threshold
        boxes = _component_boxes(mask, min_area=min_area)
        if not boxes:
            failures.append(f"{key}: no dark component over area {min_area}")
            details[key] = {"window": [x0, y0, x1, y1], "components": 0}
            continue
        best = max(boxes, key=lambda item: item["score"])
        min_x, min_y, max_x, max_y = best["bbox"]
        cx = x0 + (min_x + max_x) / 2
        cy = y0 + (min_y + max_y) / 2
        confidence = min(1.0, (best["area"] / max(expected_area * 0.35, 1.0)) * max(best["fill"], 0.001))
        points[key] = {"x": round(float(cx), 3), "y": round(float(cy), 3)}
        confidences[key] = round(float(confidence), 4)
        details[key] = {
            "window": [x0, y0, x1, y1],
            "component_count": len(boxes),
            "bbox": [x0 + min_x, y0 + min_y, x0 + max_x, y0 + max_y],
            "area": round(best["area"], 2),
            "fill": round(best["fill"], 4),
            "target": target_points.get(key),
        }

    detected = all(key in points for key in MARKER_ORDER)
    return {
        "detected": detected,
        "points": points,
        "confidence": confidences,
        "details": details,
        "failures": failures,
        "dark_threshold": dark_threshold,
        "marker_search_ratio": marker_search_ratio,
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
    """Warp image from source_points onto target_points using inverse mapping."""
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

    # We need target pixel -> source pixel, so solve target -> source.
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


def classify_question(
    scores: dict[str, float],
    *,
    min_mark_ratio: float,
    blank_threshold: float,
    ambiguous_gap: float,
) -> tuple[str, str, list[str]]:
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    if not ranked:
        return "?", "missing_layout", ["no choices in layout"]
    best_choice, best_score = ranked[0]
    second_score = ranked[1][1] if len(ranked) > 1 else 0.0
    marked = [choice for choice, score in ranked if score >= min_mark_ratio]

    if best_score < blank_threshold:
        return "?", "blank", [f"best score {best_score:.3f} below blank threshold {blank_threshold:.2f}"]
    if best_score < min_mark_ratio:
        return "?", "uncertain", [f"best score {best_score:.3f} below mark threshold {min_mark_ratio:.2f}"]
    if len(marked) >= 2:
        return "?", "multi", [f"multiple marked choices: {','.join(marked)}"]
    if (best_score - second_score) < ambiguous_gap:
        return "?", "uncertain", [f"small margin: {best_score:.3f} vs {second_score:.3f}"]
    return best_choice, "ok", []


def read_bubbles(
    image: Image.Image,
    layout: dict[str, Any],
    *,
    dark_threshold: int,
    min_mark_ratio: float,
    blank_threshold: float,
    ambiguous_gap: float,
) -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]], dict[str, Any]]:
    gray = image.convert("L")
    width, height = gray.size
    layout_width, layout_height = page_size(layout)
    if layout_width <= 0:
        layout_width = width
    if layout_height <= 0:
        layout_height = height
    sx = width / layout_width
    sy = height / layout_height
    arr = np.asarray(gray)

    by_question: dict[int, list[dict[str, Any]]] = {}
    for bubble in layout.get("bubbles") or []:
        by_question.setdefault(int(bubble["question"]), []).append(bubble)

    answers: list[str] = []
    items: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []
    for question in range(1, int(layout["question_count"]) + 1):
        scores: dict[str, float] = {}
        for bubble in sorted(by_question.get(question, []), key=lambda item: int(item["choice"])):
            roi = scale_box(bubble["roi"], sx, sy, width, height)
            scores[str(bubble["choice"])] = round(compute_dark_ratio(arr, roi, dark_threshold), 4)
        answer, status, notes = classify_question(
            scores,
            min_mark_ratio=min_mark_ratio,
            blank_threshold=blank_threshold,
            ambiguous_gap=ambiguous_gap,
        )
        answers.append(answer)
        item: dict[str, Any] = {"question": question, "answer": answer, "status": status, "scores": scores}
        if notes:
            item["notes"] = notes
        if status != "ok":
            warnings.append({"question": question, "status": status, "notes": notes})
        items.append(item)

    diagnostics = {
        "image_size": {"width_px": width, "height_px": height},
        "layout_size": {"width_px": layout_width, "height_px": layout_height},
        "scale": {"x": round(sx, 6), "y": round(sy, 6)},
    }
    return items, answers, warnings, diagnostics


def build_answers_text(answers: list[str], answer_text_format: str = "compact") -> str:
    if answer_text_format == "spaced":
        return " ".join(answers)
    return "".join(answers)
