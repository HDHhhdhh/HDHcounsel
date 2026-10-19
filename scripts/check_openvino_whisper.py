# /// script
# requires-python = ">=3.12"
# dependencies = ["faster-whisper", "openvino-genai==2026.4.1.0"]
# ///
# Run with the installed app interpreter: python scripts/check_openvino_whisper.py [test.wav]
from __future__ import annotations

import ast
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check_adapter() -> None:
    # Given: the app's existing modes and an installed GPU backend.
    tree = ast.parse((ROOT / "app.py").read_text(encoding="utf-8"))
    modes = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(isinstance(target, ast.Name) and target.id == "PROCESSING_MODES" for target in node.targets)
    )
    # When: resolving the configured model backend.
    gpu_modes = [config for config in modes.values() if config["compute_type"] == "openvino-int8"]
    # Then: GPU mode uses Turbo, while all four CPU modes remain available.
    assert len(gpu_modes) == 1, "GPU Turbo mode is missing"
    assert gpu_modes[0]["model_size"] == "large-v3-turbo"
    assert len([config for config in modes.values() if config["compute_type"] == "int8"]) == 4

    from counsel_modules.openvino_whisper import TranscriptSegment, normalize_segments
    from faster_whisper.vad import SpeechTimestampsMap

    # Given: missing final timestamps and empty recognition chunks.
    chunks = [TranscriptSegment(0, -1, " text "), TranscriptSegment(1, 2, " ")]
    # When: adapting native timestamps to the app segment contract.
    segments = list(normalize_segments(chunks, 5.0))
    # Then: final timestamps are bounded and empty chunks are omitted.
    assert segments == [TranscriptSegment(0, 5, "text")]

    # Given: VAD removed three seconds before speech.
    mapping = SpeechTimestampsMap([{"start": 48000, "end": 128000}], 16000)
    # When: restoring original recording timestamps.
    segments = list(normalize_segments([TranscriptSegment(0, 2, "hello")], 5.0, mapping))
    # Then: displayed timestamps refer to the original recording.
    assert segments == [TranscriptSegment(3, 5, "hello")]
    print("PASS: mode routing, CPU preservation, timestamps, VAD mapping")


def check_gpu(audio_path: Path) -> None:
    from counsel_modules.openvino_whisper import OpenVINOWhisperModel

    started = time.perf_counter()
    model = OpenVINOWhisperModel(ROOT / "models" / "whisper-large-v3-turbo-int8-ov")
    print(f"GPU load seconds: {time.perf_counter() - started:.2f}", flush=True)
    started = time.perf_counter()
    segments, info = model.transcribe(str(audio_path), language="ko", beam_size=1)
    rows = list(segments)
    assert rows, "GPU produced no speech segments"
    assert all(0 <= row.start <= row.end <= info.duration for row in rows)
    print(f"Audio seconds: {info.duration:.2f}; GPU inference seconds: {time.perf_counter() - started:.2f}")
    print("\n".join(row.text for row in rows))


if __name__ == "__main__":
    check_adapter()
    if len(sys.argv) == 2:
        check_gpu(Path(sys.argv[1]))
