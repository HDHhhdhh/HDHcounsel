"""Apply lab-only ASR correction rules to benchmark/provider JSON text.

This script does not import the production app. It is for experimenting with
post-ASR correction dictionaries before any production integration is considered.
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any


LAB_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = LAB_DIR / "sample_outputs"
DEFAULT_RULES = LAB_DIR / "asr_correction_rules.json"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    return cleaned.strip("_") or "asr_text"


def load_rules(path: Path) -> list[dict[str, str]]:
    raw_rules = load_json(path)
    if not isinstance(raw_rules, list):
        raise ValueError("Correction rules must be a JSON list.")

    rules: list[dict[str, str]] = []
    for index, item in enumerate(raw_rules, start=1):
        if not isinstance(item, dict):
            raise ValueError(f"Rule #{index} must be an object.")
        source = str(item.get("from", ""))
        target = str(item.get("to", ""))
        if not source:
            raise ValueError(f"Rule #{index} has an empty 'from' value.")
        rules.append(
            {
                "from": source,
                "to": target,
                "note": str(item.get("note", "")),
            }
        )
    return rules


def extract_text_records(payload: Any) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []

    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        for index, item in enumerate(payload["results"], start=1):
            if not isinstance(item, dict):
                continue
            text = item.get("text")
            if isinstance(text, str):
                label_parts = [str(item.get("model", "")).strip(), str(item.get("compute_type", "")).strip()]
                vad = item.get("vad_filter")
                if vad is not None:
                    label_parts.append(f"vad={vad}")
                label = " / ".join(part for part in label_parts if part) or f"result_{index}"
                records.append({"label": label, "text": text, "metadata": item})

    if isinstance(payload, dict) and isinstance(payload.get("text"), str):
        records.append({"label": str(payload.get("provider", "root_text")), "text": payload["text"], "metadata": payload})

    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        result = payload["result"]
        if isinstance(result.get("text"), str):
            records.append(
                {
                    "label": str(result.get("provider", "result_text")),
                    "text": result["text"],
                    "metadata": result,
                }
            )

    if not records:
        raise ValueError("No text field found in benchmark/provider JSON.")
    return records


def apply_rules(text: str, rules: list[dict[str, str]]) -> tuple[str, list[dict[str, Any]]]:
    processed = text
    replacements: list[dict[str, Any]] = []
    for rule in rules:
        source = rule["from"]
        target = rule["to"]
        count = processed.count(source)
        if count <= 0:
            continue
        processed = processed.replace(source, target)
        replacements.append(
            {
                "from": source,
                "to": target,
                "count": count,
                "note": rule.get("note", ""),
            }
        )
    return processed, replacements


def process_records(records: list[dict[str, Any]], rules: list[dict[str, str]]) -> list[dict[str, Any]]:
    processed_records: list[dict[str, Any]] = []
    for record in records:
        processed_text, replacements = apply_rules(record["text"], rules)
        processed_records.append(
            {
                "label": record["label"],
                "original_text_len": len(record["text"]),
                "processed_text_len": len(processed_text),
                "original_text": record["text"],
                "processed_text": processed_text,
                "replacements": replacements,
                "replacement_count": sum(item["count"] for item in replacements),
            }
        )
    return processed_records


def flatten_replacements(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    flattened: list[dict[str, Any]] = []
    for record in records:
        for replacement in record["replacements"]:
            flattened.append({"label": record["label"], **replacement})
    return flattened


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Apply lab-only ASR correction rules to JSON transcript text.")
    parser.add_argument("--input-json", required=True, help="Benchmark or provider JSON containing transcript text.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="Directory for postprocess output JSON.")
    parser.add_argument("--rules", default=str(DEFAULT_RULES), help="Correction rules JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = time.monotonic()
    input_path = Path(args.input_json).expanduser().resolve()
    rules_path = Path(args.rules).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()

    payload = load_json(input_path)
    rules = load_rules(rules_path)
    records = extract_text_records(payload)
    processed_records = process_records(records, rules)
    replacements = flatten_replacements(processed_records)

    original_text = "\n\n".join(record["original_text"] for record in processed_records)
    processed_text = "\n\n".join(record["processed_text"] for record in processed_records)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = out_dir / f"{timestamp}_{safe_stem(input_path.stem)}_asr_postprocess.json"
    output_path.parent.mkdir(parents=True, exist_ok=True)

    output = {
        "input_json": str(input_path),
        "original_text_len": len(original_text),
        "processed_text_len": len(processed_text),
        "original_text": original_text,
        "processed_text": processed_text,
        "replacements": replacements,
        "rules_path": str(rules_path),
        "elapsed_sec": round(time.monotonic() - started_at, 3),
        "records": processed_records,
    }
    output_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"output_json={output_path}")
    print(f"records={len(processed_records)}")
    print(f"replacement_count={sum(item['count'] for item in replacements)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
