"""Standalone ASR provider comparison CLI.

This lab script intentionally avoids importing the production Streamlit app.
It should not touch student data, Google Docs, transcript folders, or app state.
"""

from __future__ import annotations

import argparse
import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


LAB_DIR = Path(__file__).resolve().parent
DEFAULT_OUT_DIR = LAB_DIR / "sample_outputs"
DEFAULT_WHISPER_MODEL = "small"
DEFAULT_FUNASR_MODEL = "iic/SenseVoiceSmall"
DEFAULT_DEVICE = "cpu"
DEFAULT_COMPUTE_TYPE = "int8"
DEFAULT_WHISPER_BEAM_SIZE = 3


class MissingDependencyError(RuntimeError):
    """Raised when an optional lab dependency is not installed."""


@dataclass(frozen=True)
class ProviderConfig:
    audio_path: Path
    whisper_model: str
    funasr_model: str
    device: str
    compute_type: str


@dataclass(frozen=True)
class TranscriptOutput:
    text: str
    segments: list[dict[str, Any]]


ProviderResult = dict[str, Any]
ProviderRunner = Callable[[ProviderConfig], TranscriptOutput]


def safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    return cleaned.strip("_") or "audio"


def round_float(value: Any) -> float | None:
    try:
        return round(float(value), 3)
    except (TypeError, ValueError):
        return None


def make_result(
    config: ProviderConfig,
    provider: str,
    status: str,
    elapsed_sec: float,
    model: str,
    text: str = "",
    segments: list[dict[str, Any]] | None = None,
    error: str = "",
) -> ProviderResult:
    return {
        "audio_path": str(config.audio_path),
        "provider": provider,
        "status": status,
        "elapsed_sec": round(elapsed_sec, 3),
        "text": text,
        "segments": segments or [],
        "model": model,
        "device": config.device,
        "error": error,
    }


def run_provider(provider: str, runner: ProviderRunner, config: ProviderConfig) -> ProviderResult:
    model = config.whisper_model if provider == "whisper" else config.funasr_model
    started_at = time.monotonic()
    try:
        output = runner(config)
    except MissingDependencyError as exc:
        return make_result(
            config,
            provider,
            "missing_dependency",
            time.monotonic() - started_at,
            model=model,
            error=str(exc),
        )
    except Exception as exc:  # Keep one provider failure from blocking the other.
        return make_result(
            config,
            provider,
            "error",
            time.monotonic() - started_at,
            model=model,
            error=str(exc),
        )

    return make_result(
        config,
        provider,
        "ok",
        time.monotonic() - started_at,
        model=model,
        text=output.text,
        segments=output.segments,
    )


def transcribe_with_whisper(config: ProviderConfig) -> TranscriptOutput:
    try:
        from faster_whisper import WhisperModel  # type: ignore
    except ImportError as exc:
        raise MissingDependencyError(
            "faster-whisper is not installed. Install lab dependencies before running "
            "the whisper provider."
        ) from exc

    model = WhisperModel(
        config.whisper_model,
        device=config.device,
        compute_type=config.compute_type,
    )
    segments_iter, _info = model.transcribe(
        str(config.audio_path),
        language="ko",
        beam_size=DEFAULT_WHISPER_BEAM_SIZE,
        temperature=0,
        condition_on_previous_text=False,
        task="transcribe",
        word_timestamps=False,
        vad_filter=False,
    )

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

    return TranscriptOutput(text="\n".join(lines).strip(), segments=segment_rows)


def transcribe_with_funasr(config: ProviderConfig) -> TranscriptOutput:
    try:
        from funasr import AutoModel  # type: ignore
    except ImportError as exc:
        raise MissingDependencyError(
            "funasr is not installed. Review requirements-funasr.txt and install "
            "lab dependencies before running the funasr provider."
        ) from exc

    try:
        model = AutoModel(
            model=config.funasr_model,
            vad_model="fsmn-vad",
            device=config.device,
        )
    except (ImportError, ModuleNotFoundError) as exc:
        raise MissingDependencyError(f"FunASR dependency is missing: {exc}") from exc

    try:
        raw_result = model.generate(
            input=str(config.audio_path),
            language="ko",
            use_itn=True,
            batch_size_s=60,
            merge_vad=True,
            merge_length_s=15,
        )
    except TypeError:
        raw_result = model.generate(input=str(config.audio_path))

    return normalize_funasr_output(raw_result)


def normalize_funasr_output(result: Any) -> TranscriptOutput:
    if isinstance(result, list):
        outputs = [normalize_funasr_output(item) for item in result]
        text = "\n".join(output.text for output in outputs if output.text).strip()
        segments = [segment for output in outputs for segment in output.segments]
        return TranscriptOutput(text=text, segments=segments)

    if isinstance(result, dict):
        sentence_segments = extract_funasr_sentence_segments(result.get("sentence_info"))
        if sentence_segments:
            return TranscriptOutput(
                text="\n".join(str(row.get("text", "")).strip() for row in sentence_segments).strip(),
                segments=sentence_segments,
            )

        text_value = result.get("text")
        if isinstance(text_value, str):
            return TranscriptOutput(text=text_value.strip(), segments=[])

        value = result.get("value")
        if isinstance(value, str):
            return TranscriptOutput(text=value.strip(), segments=[])

        return TranscriptOutput(text=json.dumps(result, ensure_ascii=False), segments=[])

    return TranscriptOutput(text=str(result or "").strip(), segments=[])


def extract_funasr_sentence_segments(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []

    rows: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, dict):
            continue
        text = str(item.get("text", "") or "").strip()
        if not text:
            continue
        rows.append(
            {
                "start": round_float(item.get("start")),
                "end": round_float(item.get("end")),
                "text": text,
            }
        )
    return rows


def selected_providers(provider: str) -> list[str]:
    if provider == "both":
        return ["whisper", "funasr"]
    return [provider]


def write_provider_result(
    out_dir: Path,
    timestamp: str,
    audio_stem: str,
    result: ProviderResult,
) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    output_path = out_dir / f"{timestamp}_{audio_stem}_{result['provider']}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def summarize_status(results: list[ProviderResult]) -> str:
    statuses = {str(result.get("status", "")) for result in results}
    if statuses == {"ok"}:
        return "ok"
    if "ok" in statuses:
        return "partial"
    return "failed"


def write_summary_result(
    out_dir: Path,
    timestamp: str,
    audio_stem: str,
    config: ProviderConfig,
    provider_arg: str,
    results: list[ProviderResult],
    elapsed_sec: float,
) -> Path:
    output_path = out_dir / f"{timestamp}_{audio_stem}_summary.json"
    errors = [str(result.get("error", "")) for result in results if result.get("error")]
    payload = {
        "audio_path": str(config.audio_path),
        "provider": provider_arg,
        "status": summarize_status(results),
        "elapsed_sec": round(elapsed_sec, 3),
        "text": "",
        "segments": [],
        "model": {
            "whisper": config.whisper_model,
            "funasr": config.funasr_model,
        },
        "device": config.device,
        "error": " | ".join(errors),
        "results": results,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compare ASR provider outputs on one audio file.")
    parser.add_argument("--audio", required=True, help="Path to a copied, non-sensitive test audio file.")
    parser.add_argument(
        "--provider",
        choices=["whisper", "funasr", "both"],
        default="both",
        help="Provider to run. With both, whisper runs first and funasr runs second.",
    )
    parser.add_argument(
        "--out",
        default=str(DEFAULT_OUT_DIR),
        help="Directory for provider and summary JSON outputs.",
    )
    parser.add_argument(
        "--whisper-model",
        default=DEFAULT_WHISPER_MODEL,
        help="faster-whisper model name. Default follows the production balanced mode.",
    )
    parser.add_argument(
        "--funasr-model",
        default=DEFAULT_FUNASR_MODEL,
        help="FunASR AutoModel model name. The default is a Korean-capable SenseVoiceSmall model.",
    )
    parser.add_argument("--device", default=DEFAULT_DEVICE, help="Runtime device, default cpu.")
    parser.add_argument(
        "--compute-type",
        default=DEFAULT_COMPUTE_TYPE,
        help="faster-whisper compute_type, default int8 for CPU experiments.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    audio_path = Path(args.audio).expanduser()
    if not audio_path.exists() or not audio_path.is_file():
        print(f"Audio file not found: {audio_path}")
        return 2

    config = ProviderConfig(
        audio_path=audio_path.resolve(),
        whisper_model=args.whisper_model,
        funasr_model=args.funasr_model,
        device=args.device,
        compute_type=args.compute_type,
    )
    runners: dict[str, ProviderRunner] = {
        "whisper": transcribe_with_whisper,
        "funasr": transcribe_with_funasr,
    }

    out_dir = Path(args.out).expanduser()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    audio_stem = safe_stem(config.audio_path.stem)
    started_at = time.monotonic()
    results: list[ProviderResult] = []

    for provider in selected_providers(args.provider):
        result = run_provider(provider, runners[provider], config)
        results.append(result)
        output_path = write_provider_result(out_dir, timestamp, audio_stem, result)
        print(f"{provider}: {result['status']} -> {output_path}")

    summary_path = write_summary_result(
        out_dir,
        timestamp,
        audio_stem,
        config,
        args.provider,
        results,
        time.monotonic() - started_at,
    )
    print(f"summary: {summarize_status(results)} -> {summary_path}")

    return 0 if summarize_status(results) == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
