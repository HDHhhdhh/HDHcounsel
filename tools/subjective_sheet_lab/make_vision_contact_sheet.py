#!/usr/bin/env python
"""Create a crop contact sheet for manual ChatGPT/Gemini Vision testing."""

from __future__ import annotations

import argparse
from pathlib import Path

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


def parse_questions(raw: str) -> list[int]:
    questions: list[int] = []
    for piece in raw.split(","):
        piece = piece.strip()
        if not piece:
            continue
        if "-" in piece:
            start_raw, end_raw = piece.split("-", 1)
            try:
                start = int(start_raw.strip())
                end = int(end_raw.strip())
            except ValueError as exc:
                raise argparse.ArgumentTypeError(f"invalid question range: {piece}") from exc
            if start < 1 or end < 1:
                raise argparse.ArgumentTypeError(f"question range must be >= 1: {piece}")
            step = 1 if end >= start else -1
            questions.extend(range(start, end + step, step))
            continue
        try:
            question = int(piece)
        except ValueError as exc:
            raise argparse.ArgumentTypeError(f"invalid question number: {piece}") from exc
        if question < 1:
            raise argparse.ArgumentTypeError(f"question number must be >= 1: {piece}")
        questions.append(question)
    if not questions:
        raise argparse.ArgumentTypeError("at least one question is required")
    return questions


def crop_path(crop_dir: Path, question: int) -> Path:
    return crop_dir / f"q{question:03d}.png"


def load_items(crop_dir: Path, questions: list[int], scale: float) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for question in questions:
        path = crop_path(crop_dir, question)
        if not path.exists():
            raise FileNotFoundError(f"missing crop file: {path}")
        image = Image.open(path).convert("RGB")
        if scale != 1.0:
            width = max(1, int(image.width * scale))
            height = max(1, int(image.height * scale))
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        items.append({"question": question, "path": path, "image": image})
    return items


def build_contact_sheet(items: list[dict[str, object]], columns: int, padding: int, gap: int) -> Image.Image:
    columns = max(1, columns)
    label_h = 74
    title_h = 92
    footer_h = 42
    font_title = load_font(42, bold=True)
    font_label = load_font(34, bold=True)
    font_small = load_font(22)

    max_crop_w = max((item["image"].width for item in items), default=1)  # type: ignore[union-attr]
    max_crop_h = max((item["image"].height for item in items), default=1)  # type: ignore[union-attr]
    cell_w = max_crop_w + padding * 2
    cell_h = max_crop_h + padding * 2 + label_h
    rows = (len(items) + columns - 1) // columns
    width = columns * cell_w + (columns + 1) * gap
    height = title_h + rows * cell_h + (rows + 1) * gap + footer_h

    sheet = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(sheet)
    question_numbers = [int(item["question"]) for item in items]
    q_min = min(question_numbers) if question_numbers else 0
    q_max = max(question_numbers) if question_numbers else 0
    draw.text((gap, 24), "Manual Vision OCR Contact Sheet", fill="black", font=font_title)
    draw.text((gap, 68), f"Read only Q{q_min:03d}-Q{q_max:03d}. If uncertain, use ?.", fill=(90, 90, 90), font=font_small)

    for index, item in enumerate(items):
        row = index // columns
        col = index % columns
        x = gap + col * (cell_w + gap)
        y = title_h + gap + row * (cell_h + gap)
        question = int(item["question"])
        image: Image.Image = item["image"]  # type: ignore[assignment]
        draw.rectangle([x, y, x + cell_w, y + cell_h], outline=(0, 0, 0), width=3)
        draw.rectangle([x, y, x + cell_w, y + label_h], fill=(245, 247, 252), outline=(0, 0, 0), width=2)
        draw.text((x + padding, y + 18), f"Q{question:03d}", fill="black", font=font_label)
        crop_x = x + padding + (max_crop_w - image.width) // 2
        crop_y = y + label_h + padding + (max_crop_h - image.height) // 2
        draw.rectangle(
            [crop_x - 2, crop_y - 2, crop_x + image.width + 2, crop_y + image.height + 2],
            outline=(210, 210, 210),
            width=2,
        )
        sheet.paste(image, (crop_x, crop_y))

    draw.text((gap, height - footer_h + 7), "This sheet is for manual OCR feasibility testing only.", fill=(90, 90, 90), font=font_small)
    return sheet


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Create a contact sheet PNG for manual Vision OCR testing.")
    parser.add_argument("--crop-dir", required=True, help="Directory containing q001.png, q002.png, ...")
    parser.add_argument("--questions", default="1,2,3,4,5", help="Comma-separated question numbers or ranges, e.g. 1,2,3 or 1-10.")
    parser.add_argument("--out", required=True, help="Output contact sheet PNG path.")
    parser.add_argument("--columns", type=int, default=2, help="Number of columns in the contact sheet. Default: 2.")
    parser.add_argument("--scale", type=float, default=2.0, help="Scale factor applied to each crop. Default: 2.0.")
    parser.add_argument("--padding", type=int, default=42, help="Cell padding in pixels. Default: 42.")
    parser.add_argument("--gap", type=int, default=46, help="Gap between cells in pixels. Default: 46.")
    args = parser.parse_args()
    if args.columns < 1:
        parser.error("--columns must be >= 1")
    if args.scale <= 0:
        parser.error("--scale must be > 0")
    return args


def main() -> int:
    args = parse_args()
    questions = parse_questions(args.questions)
    items = load_items(Path(args.crop_dir), questions, float(args.scale))
    sheet = build_contact_sheet(items, int(args.columns), int(args.padding), int(args.gap))

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    sheet.save(out_path)
    print(f"Wrote {out_path}")
    print(f"questions={','.join(f'Q{question:03d}' for question in questions)}")
    print(f"size={sheet.width}x{sheet.height}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
