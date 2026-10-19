"""Diagnose where FunASR stalls in the isolated ASR lab.

This script is intentionally standalone and does not import the production app.
It writes progress JSON after each stage so a timeout still leaves evidence of
the last reached step.
"""

from __future__ import annotations

import argparse
import json
import time
import wave
from datetime import datetime
from pathlib import Path
from typing import Any


LAB_DIR = Path(__file__).resolve().parent
DEFAULT_AUDIO = LAB_DIR / "samples" / "funasr_30s_test.wav"
DEFAULT_OUT_DIR = LAB_DIR / "sample_outputs"
DEFAULT_MODEL = "iic/SenseVoiceSmall"
DEFAULT_DEVICE = "cpu"


class Diagnosis:
    def __init__(self, audio_path: Path, model: str, device: str, out_dir: Path) -> None:
        self.audio_path = audio_path
        self.model = model
        self.device = device
        self.out_dir = out_dir
        self.started_at = time.monotonic()
        self.stage_started_at = self.started_at
        self.stage = "python_start"
        self.status = "running"
        self.text = ""
        self.error = ""
        self.stage_elapsed: dict[str, float] = {}
        self.timestamps: list[dict[str, Any]] = []
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_stem = safe_filename_stem(audio_path.stem)
        self.output_path = out_dir / f"{timestamp}_{safe_stem}_funasr_diagnose.json"

    def mark(self, stage: str, event: str, **extra: Any) -> None:
        now = datetime.now().isoformat(timespec="seconds")
        elapsed = time.monotonic() - self.started_at
        if event == "start":
            self.stage = stage
            self.stage_started_at = time.monotonic()
        elif event in {"end", "error"}:
            self.stage_elapsed[stage] = round(time.monotonic() - self.stage_started_at, 3)
        self.timestamps.append(
            {
                "time": now,
                "stage": stage,
                "event": event,
                "elapsed_sec": round(elapsed, 3),
                **extra,
            }
        )
        print(f"{now} | {stage} | {event} | elapsed={elapsed:.3f}s", flush=True)
        self.write()

    def finish(self, status: str, text: str = "", error: str = "") -> None:
        self.status = status
        self.text = text
        self.error = error
        self.write()

    def write(self) -> None:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "status": self.status,
            "stage": self.stage,
            "elapsed_sec": round(time.monotonic() - self.started_at, 3),
            "model": self.model,
            "device": self.device,
            "audio_path": str(self.audio_path),
            "text": self.text,
            "error": self.error,
            "timestamps": self.timestamps,
            "stage_elapsed": self.stage_elapsed,
        }
        self.output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def safe_filename_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    return cleaned.strip("_") or "audio"


def audio_metadata(audio_path: Path) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "exists": audio_path.exists(),
        "bytes": audio_path.stat().st_size if audio_path.exists() else 0,
    }
    if audio_path.suffix.lower() == ".wav" and audio_path.exists():
        with wave.open(str(audio_path), "rb") as wav_file:
            frames = wav_file.getnframes()
            rate = wav_file.getframerate()
            metadata.update(
                {
                    "duration_sec": round(frames / rate, 3) if rate else None,
                    "sample_rate": rate,
                    "channels": wav_file.getnchannels(),
                    "sample_width": wav_file.getsampwidth(),
                }
            )
    return metadata


def normalize_text(result: Any) -> str:
    if isinstance(result, list):
        return "\n".join(part for item in result if (part := normalize_text(item))).strip()
    if isinstance(result, dict):
        sentence_info = result.get("sentence_info")
        if isinstance(sentence_info, list):
            sentences = []
            for item in sentence_info:
                if isinstance(item, dict) and isinstance(item.get("text"), str):
                    sentences.append(item["text"].strip())
            if sentences:
                return "\n".join(sentence for sentence in sentences if sentence).strip()
        for key in ("text", "value"):
            value = result.get(key)
            if isinstance(value, str):
                return value.strip()
        return json.dumps(result, ensure_ascii=False)
    return str(result or "").strip()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Diagnose FunASR import, model init, and generation stages.")
    parser.add_argument("--audio", default=str(DEFAULT_AUDIO), help="Path to the short WAV test file.")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="FunASR AutoModel model name.")
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Runtime device, default cpu.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="Directory for diagnosis JSON output.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audio_path = Path(args.audio).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    diagnosis = Diagnosis(audio_path=audio_path, model=args.model, device=args.device, out_dir=out_dir)
    diagnosis.mark("python_start", "start")

    try:
        diagnosis.mark("audio_check", "start")
        metadata = audio_metadata(audio_path)
        diagnosis.mark("audio_check", "end", **metadata)
        if not metadata["exists"]:
            raise FileNotFoundError(f"Audio file not found: {audio_path}")

        diagnosis.mark("import_funasr", "start")
        import funasr  # noqa: F401

        diagnosis.mark("import_funasr", "end")

        diagnosis.mark("import_automodel", "start")
        from funasr import AutoModel  # type: ignore

        diagnosis.mark("import_automodel", "end")

        diagnosis.mark("automodel_init", "start")
        model = AutoModel(
            model=args.model,
            vad_model="fsmn-vad",
            device=args.device,
        )
        diagnosis.mark("automodel_init", "end")

        diagnosis.mark("model_generate", "start")
        try:
            result = model.generate(
                input=str(audio_path),
                language="ko",
                use_itn=True,
                batch_size_s=60,
                merge_vad=True,
                merge_length_s=15,
            )
        except TypeError:
            result = model.generate(input=str(audio_path))
        diagnosis.mark("model_generate", "end")

        diagnosis.mark("extract_text", "start")
        text = normalize_text(result)
        diagnosis.mark("extract_text", "end", text_length=len(text))
        diagnosis.finish("ok", text=text)
        print(f"diagnosis_json={diagnosis.output_path}", flush=True)
        return 0
    except Exception as exc:
        diagnosis.mark(diagnosis.stage, "error", error=str(exc))
        diagnosis.finish("error", error=str(exc))
        print(f"diagnosis_json={diagnosis.output_path}", flush=True)
        print(f"error={exc}", flush=True)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
