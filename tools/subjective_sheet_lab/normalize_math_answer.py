#!/usr/bin/env python
"""Lightweight normalization for subjective math-answer OCR evaluation.

This module intentionally does not perform symbolic math equivalence.
It only reduces common OCR/typing variants before exact string comparison.
"""

from __future__ import annotations

import argparse
import unicodedata


MINUS_VARIANTS = {
    "\u2212": "-",
    "\u2010": "-",
    "\u2011": "-",
    "\u2012": "-",
    "\u2013": "-",
    "\u2014": "-",
    "\ufe63": "-",
    "\uff0d": "-",
}

MULTIPLY_VARIANTS = ("×", "⋅", "·", "*")


def normalize_math_answer(value: object) -> str:
    """Return a conservative comparison form for short math answers."""
    if value is None:
        return ""
    text = unicodedata.normalize("NFKC", str(value)).strip().lower()
    for source, target in MINUS_VARIANTS.items():
        text = text.replace(source, target)
    text = text.replace("√", "sqrt")
    text = text.replace("π", "pi")
    text = text.replace("≤", "<=")
    text = text.replace("≥", ">=")
    for symbol in MULTIPLY_VARIANTS:
        text = text.replace(symbol, "")
    text = "".join(text.split())
    return text


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Normalize one math answer for OCR evaluation.")
    parser.add_argument("answer", help="Answer text to normalize.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    print(normalize_math_answer(args.answer))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
