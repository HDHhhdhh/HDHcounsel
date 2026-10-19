"""Benchmark faster-whisper settings inside the isolated ASR lab.

This script intentionally avoids importing the production Streamlit app. It is
for local experiment runs only and writes JSON/CSV results under the lab output
folder.
"""

from __future__ import annotations

import argparse
import csv
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


LAB_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = LAB_DIR / "sample_outputs"
DEFAULT_MODELS = "tiny,base,small"
DEFAULT_COMPUTE_TYPES = "int8"
DEFAULT_DEVICE = "cpu"
DEFAULT_VAD_OPTIONS = "false,true"
DEFAULT_BEAM_SIZE = 3


@dataclass(frozen=True)
class BenchmarkConfig:
    model: str
    compute_type: str
    device: str
    vad_filter: bool
    beam_size: int


def split_csv(value: str) -> list[str]:
    return [part.strip() for part in value.split(",") if part.strip()]


def parse_bool_list(value: str) -> list[bool]:
    bools: list[bool] = []
    for part in split_csv(value):
        lowered = part.lower()
        if lowered in {"1", "true", "yes", "y", "on"}:
            bools.append(True)
        elif lowered in {"0", "false", "no", "n", "off"}:
            bools.append(False)
        else:
            raise ValueError(f"Unsupported boolean value in --vad-options: {part}")
    return bools or [False]


def safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    return cleaned.strip("_") or "audio"


def build_configs(args: argparse.Namespace) -> list[BenchmarkConfig]:
    configs = [
        BenchmarkConfig(
            model=model,
            compute_type=compute_type,
            device=args.device,
            vad_filter=vad_filter,
            beam_size=args.beam_size,
        )
        for model in split_csv(args.models)
        for compute_type in split_csv(args.compute_types)
        for vad_filter in parse_bool_list(args.vad_options)
    ]
    if args.max_runs is not None:
        return configs[: max(args.max_runs, 0)]
    return configs


def round_float(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def run_one(audio_path: Path, config: BenchmarkConfig) -> dict[str, Any]:
    result = {
        "model": config.model,
        "compute_type": config.compute_type,
        "device": config.device,
        "vad_filter": config.vad_filter,
        "beam_size": config.beam_size,
        "elapsed_sec": 0.0,
        "load_elapsed_sec": 0.0,
        "transcribe_elapsed_sec": 0.0,
        "text_len": 0,
        "segment_count": 0,
        "text": "",
        "error": "",
        "status": "running",
    }
    started_at = time.monotonic()
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        result.update(
            {
                "status": "missing_dependency",
                "elapsed_sec": round(time.monotonic() - started_at, 3),
                "error": "faster-whisper is not installed.",
            }
        )
        return result

    try:
        load_started_at = time.monotonic()
        model = WhisperModel(
            config.model,
            device=config.device,
            compute_type=config.compute_type,
        )
        result["load_elapsed_sec"] = round(time.monotonic() - load_started_at, 3)

        transcribe_options: dict[str, Any] = {
            "language": "ko",
            "beam_size": config.beam_size,
            "temperature": 0,
            "condition_on_previous_text": False,
            "task": "transcribe",
            "word_timestamps": False,
            "vad_filter": config.vad_filter,
        }
        if config.vad_filter:
            transcribe_options["vad_parameters"] = {"min_silence_duration_ms": 700}

        transcribe_started_at = time.monotonic()
        segments_iter, _info = model.transcribe(str(audio_path), **transcribe_options)
        lines: list[str] = []
        segment_rows: list[dict[str, Any]] = []
        for segment in segments_iter:
            text = str(getattr(segment, "text", "") or "").strip()
            if not text:
                continue
            lines.append(text)
            segment_rows.append(
                {
                    "start": round_float(getattr(segment, "start", None)),
                    "end": round_float(getattr(segment, "end", None)),
                    "text": text,
                }
            )
        text = "\n".join(lines).strip()
        result.update(
            {
                "status": "ok",
                "transcribe_elapsed_sec": round(time.monotonic() - transcribe_started_at, 3),
                "text_len": len(text),
                "segment_count": len(segment_rows),
                "text": text,
            }
        )
    except Exception as exc:
        result.update({"status": "error", "error": str(exc)})

    result["elapsed_sec"] = round(time.monotonic() - started_at, 3)
    return result


def write_json(output_path: Path, payload: dict[str, Any]) -> None:
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(output_path: Path, results: list[dict[str, Any]]) -> None:
    fieldnames = [
        "model",
        "compute_type",
        "device",
        "vad_filter",
        "beam_size",
        "status",
        "elapsed_sec",
        "load_elapsed_sec",
        "transcribe_elapsed_sec",
        "text_len",
        "segment_count",
        "error",
    ]
    with output_path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            writer.writerow({key: result.get(key, "") for key in fieldnames})


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run faster-whisper benchmark configs sequentially.")
    parser.add_argument("--audio", required=True, help="Path to a copied, non-sensitive audio file.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="Directory for JSON/CSV benchmark outputs.")
    parser.add_argument("--models", default=DEFAULT_MODELS, help="Comma-separated model sizes, default tiny,base,small.")
    parser.add_argument("--compute-types", default=DEFAULT_COMPUTE_TYPES, help="Comma-separated compute types.")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Runtime device, default cpu.")
    parser.add_argument("--max-runs", type=int, default=None, help="Optional cap on sequential benchmark runs.")
    parser.add_argument("--vad-options", default=DEFAULT_VAD_OPTIONS, help="Comma-separated booleans, default false,true.")
    parser.add_argument("--beam-size", type=int, default=DEFAULT_BEAM_SIZE, help="faster-whisper beam_size.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audio_path = Path(args.audio).expanduser().resolve()
    if not audio_path.exists() or not audio_path.is_file():
        print(f"Audio file not found: {audio_path}")
        return 2

    out_dir = Path(args.out).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_stem = f"{timestamp}_{safe_stem(audio_path.stem)}_whisper_benchmark"
    json_path = out_dir / f"{output_stem}.json"
    csv_path = out_dir / f"{output_stem}.csv"

    started_at = time.monotonic()
    results: list[dict[str, Any]] = []
    configs = build_configs(args)
    for index, config in enumerate(configs, start=1):
        print(
            f"[{index}/{len(configs)}] model={config.model} compute_type={config.compute_type} "
            f"device={config.device} vad={config.vad_filter}",
            flush=True,
        )
        result = run_one(audio_path, config)
        results.append(result)
        write_json(
            json_path,
            {
                "audio_path": str(audio_path),
                "created_at": datetime.now().isoformat(timespec="seconds"),
                "elapsed_sec": round(time.monotonic() - started_at, 3),
                "results": results,
            },
        )
        write_csv(csv_path, results)
        print(
            f"  status={result['status']} elapsed={result['elapsed_sec']}s "
            f"text_len={result['text_len']} segments={result['segment_count']}",
            flush=True,
        )

    print(f"json={json_path}", flush=True)
    print(f"csv={csv_path}", flush=True)
    return 0 if all(result.get("status") == "ok" for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
