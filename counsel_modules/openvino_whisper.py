from __future__ import annotations

from collections.abc import Iterator, Sequence
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import TYPE_CHECKING, Final, TypedDict

import numpy as np
from faster_whisper.audio import decode_audio
from faster_whisper.vad import SpeechTimestampsMap, VadOptions, collect_chunks, get_speech_timestamps
from numpy.typing import NDArray

if TYPE_CHECKING:
    from openvino_genai import WhisperPipeline

SAMPLE_RATE: Final = 16000


class VadSettings(TypedDict, total=False):
    min_silence_duration_ms: int


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    start: float
    end: float
    text: str


@dataclass(frozen=True, slots=True)
class TranscriptInfo:
    duration: float


def normalize_segments(
    segments: Sequence[TranscriptSegment],
    duration: float,
    timestamp_map: SpeechTimestampsMap | None = None,
) -> Iterator[TranscriptSegment]:
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        start = min(max(segment.start, 0.0), duration)
        end = duration if segment.end < 0 else min(max(segment.end, start), duration)
        if timestamp_map is not None:
            start = timestamp_map.get_original_time(start)
            end = timestamp_map.get_original_time(end, is_end=True)
        yield TranscriptSegment(start, end, text)


class OpenVINOWhisperModel:
    def __init__(self, model_path: Path) -> None:
        from openvino_genai import WhisperPipeline

        self._pipeline: WhisperPipeline = WhisperPipeline(
            str(model_path), "GPU", CACHE_DIR=str(model_path / ".gpu_cache")
        )
        self._lock = Lock()

    def transcribe(
        self,
        audio: str,
        language: str = "ko",
        beam_size: int = 1,
        temperature: float = 0,
        condition_on_previous_text: bool = False,
        task: str = "transcribe",
        word_timestamps: bool = False,
        vad_filter: bool = False,
        vad_parameters: VadSettings | None = None,
        initial_prompt: str | None = None,
    ) -> tuple[Iterator[TranscriptSegment], TranscriptInfo]:
        samples = decode_audio(audio, sampling_rate=SAMPLE_RATE)
        info = TranscriptInfo(len(samples) / SAMPLE_RATE)
        timestamp_map = None
        if vad_filter:
            speech = get_speech_timestamps(samples, VadOptions(**(vad_parameters or {})))
            chunks, _ = collect_chunks(samples, speech, sampling_rate=SAMPLE_RATE)
            samples = np.concatenate(chunks)
            if speech:
                timestamp_map = SpeechTimestampsMap(speech, SAMPLE_RATE)
        if condition_on_previous_text or word_timestamps or temperature != 0:
            raise NotImplementedError("GPU mode requires greedy/beam decoding without word timestamps or previous-text conditioning")
        return self._generate(samples, language, task, beam_size, initial_prompt, timestamp_map), info

    def _generate(
        self,
        samples: NDArray[np.float32],
        language: str,
        task: str,
        beam_size: int,
        initial_prompt: str | None,
        timestamp_map: SpeechTimestampsMap | None,
    ) -> Iterator[TranscriptSegment]:
        if not len(samples):
            return
        with self._lock:
            result = self._pipeline.generate(
                samples,
                language=language,
                task=task,
                return_timestamps=True,
                num_beams=beam_size,
                initial_prompt=initial_prompt or "",
            )
        duration = len(samples) / SAMPLE_RATE
        chunks = [TranscriptSegment(chunk.start_ts, chunk.end_ts, chunk.text) for chunk in (result.chunks or [])]
        if not chunks and result.texts:
            chunks = [TranscriptSegment(0, duration, result.texts[0])]
        yield from normalize_segments(chunks, duration, timestamp_map)
