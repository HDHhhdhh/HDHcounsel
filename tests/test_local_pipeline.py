from __future__ import annotations

import json
import math
import struct
import subprocess
import sys
import types
import wave
from dataclasses import replace
from pathlib import Path
from unittest.mock import Mock

import pytest

from hdhcounsel import pipeline, service
from hdhcounsel.audio import normalize_audio
from hdhcounsel.config import CounselError, Settings
from hdhcounsel.domain import Segment, Transcript, Word
from hdhcounsel.storage import Record, write_json


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(tmp_path / "models", tmp_path / "records", device="cpu", compute_type="int8")


@pytest.fixture
def audio(tmp_path: Path) -> Path:
    path = tmp_path / "synthetic.wav"
    with wave.open(str(path), "wb") as handle:
        handle.setparams((2, 2, 22050, 0, "NONE", "not compressed"))
        for index in range(2205):
            value = round(1000 * math.sin(2 * math.pi * 440 * index / 22050))
            handle.writeframesraw(struct.pack("<hh", value, value))
    return path


def test_ffmpeg_normalizes_real_synthetic_audio(audio: Path, tmp_path: Path) -> None:
    output = tmp_path / "normalized.wav"
    normalize_audio(audio, output)
    with wave.open(str(output), "rb") as handle:
        assert (handle.getnchannels(), handle.getsampwidth(), handle.getframerate()) == (1, 2, 16000)
        assert 1590 <= handle.getnframes() <= 1610
    assert audio.exists()


def test_ffmpeg_rejects_invalid_audio(tmp_path: Path) -> None:
    source = tmp_path / "invalid.wav"
    source.write_text("not audio")
    with pytest.raises(CounselError, match="rejected"):
        normalize_audio(source, tmp_path / "output.wav")


@pytest.mark.parametrize("changes", [
    {"device": "npu"},
    {"device": "cpu", "compute_type": "float16"},
    {"batch_size": 0},
    {"batch_size": True},
    {"num_speakers": 0},
    {"diarize": "false"},
    {"timeout_seconds": 0},
])
def test_invalid_configuration(settings: Settings, changes: dict) -> None:
    with pytest.raises(CounselError):
        replace(settings, **changes)


def test_cpu_configuration_and_relative_paths(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[hdhcounsel]\ndevice="cpu"\nmodels_dir="weights"\n', encoding="utf-8")
    config = Settings.load(path)
    assert config.compute_type == "int8"
    assert config.models_dir == tmp_path / "weights"


def test_configuration_rejects_unknown_field(tmp_path: Path) -> None:
    path = tmp_path / "config.toml"
    path.write_text('[hdhcounsel]\napi_token="not-a-real-token"\n', encoding="utf-8")
    with pytest.raises(CounselError, match="Unknown configuration"):
        Settings.load(path)


@pytest.mark.parametrize("toml", [
    "hdhcounsel = false",
    '[hdhcounsel]\nmodels_dir = 123',
    '[hdhcounsel]\ndevice = ["cuda"]',
    '[hdhcounsel]\nffmpeg = false',
])
def test_configuration_reports_invalid_toml_value_types(tmp_path: Path, toml: str) -> None:
    path = tmp_path / "config.toml"
    path.write_text(toml, encoding="utf-8")
    with pytest.raises(CounselError):
        Settings.load(path)


def test_assets_fail_before_worker_launch(settings: Settings, audio: Path, monkeypatch) -> None:
    run = Mock()
    monkeypatch.setattr(service.subprocess, "run", run)
    with pytest.raises(CounselError, match="assets are missing"):
        service.transcribe(audio, settings)
    run.assert_not_called()


def test_optional_word_alignment_and_unknown_speaker_round_trip() -> None:
    transcript = Transcript.from_whisperx({
        "segments": [{
            "start": 0.1, "end": 1.2, "text": "안녕하세요",
            "words": [{"word": "안녕하세요"}],
        }],
    }, duration=2, diarized=True)
    assert transcript.segments[0].words[0].start is None
    assert "UNKNOWN" in transcript.text()
    assert Transcript.from_dict(json.loads(json.dumps(transcript.to_dict()))) == transcript


@pytest.mark.parametrize("start,end", [(-1, 0), (2, 1), (float("nan"), 1), (0, float("inf"))])
def test_invalid_engine_timestamp(start: float, end: float) -> None:
    with pytest.raises(CounselError):
        Segment(start, end, "text")


def test_atomic_write_preserves_previous_record_on_failure(tmp_path: Path, monkeypatch) -> None:
    import hdhcounsel.storage as storage

    target = tmp_path / "record.json"
    write_json(target, {"previous": True})
    monkeypatch.setattr(storage.os, "replace", Mock(side_effect=OSError("disk error")))
    with pytest.raises(OSError):
        write_json(target, {"new": True})
    assert json.loads(target.read_text()) == {"previous": True}
    assert list(tmp_path.glob(".hdh-*.tmp")) == []


def test_review_does_not_modify_evidence_or_use_names_as_paths(tmp_path: Path) -> None:
    transcript = Transcript((Segment(0, 1, "확인", "SPEAKER_00"),), 1, diarized=True)
    record = Record.create(tmp_path, "../../student", "2026-10-19", transcript)
    original = (record.path / "transcript.json").read_bytes()
    record.save_review("직접 확인", {"SPEAKER_00": "상담자"}, True)
    assert record.path.parent == tmp_path
    assert (record.path / "transcript.json").read_bytes() == original
    assert json.loads((record.path / "review.json").read_text(encoding="utf-8"))["reviewed"] is True


def test_worker_network_policy_is_enforced_in_subprocess() -> None:
    code = (
        "from hdhcounsel.privacy import deny_network; import socket; deny_network(); "
        "socket.socket().connect(('127.0.0.1', 9))"
    )
    result = subprocess.run([sys.executable, "-I", "-c", code], capture_output=True, timeout=15)
    assert result.returncode != 0
    assert b"Network access is disabled" in result.stderr


def test_service_keeps_worker_isolated_and_cleans_temp_audio(
    settings: Settings, audio: Path, monkeypatch,
) -> None:
    monkeypatch.setattr(Settings, "validate_assets", lambda self: None)
    monkeypatch.setattr(service, "normalize_audio", lambda source, target, ffmpeg: target.write_bytes(b"wav"))
    monkeypatch.setenv("HF_TOKEN", "synthetic-test-value")
    worker_directories = []
    expected = Transcript((Segment(0, 1, "안녕", words=(Word("안녕", 0, 1),)),), 1)

    def run(command, **kwargs):
        assert command[1:4] == ["-I", "-m", "hdhcounsel.worker"]
        assert "HF_TOKEN" not in kwargs["env"]
        request = json.loads(Path(command[-2]).read_text(encoding="utf-8"))
        assert Path(request["audio"]).is_file()
        worker_directories.append(kwargs["cwd"])
        write_json(Path(command[-1]), {"ok": True, "transcript": expected.to_dict()})
        return types.SimpleNamespace(returncode=0)

    monkeypatch.setattr(service.subprocess, "run", run)
    assert service.transcribe(audio, settings) == expected
    assert all(not path.exists() for path in worker_directories)


def test_worker_failure_is_not_returned_as_success(settings: Settings, audio: Path, monkeypatch) -> None:
    monkeypatch.setattr(Settings, "validate_assets", lambda self: None)
    monkeypatch.setattr(service, "normalize_audio", lambda *args: None)

    def run(command, **kwargs):
        write_json(Path(command[-1]), {"ok": False, "error": "GPU unavailable"})
        return types.SimpleNamespace(returncode=1)

    monkeypatch.setattr(service.subprocess, "run", run)
    with pytest.raises(CounselError, match="GPU unavailable"):
        service.transcribe(audio, settings)


def test_whisperx_stages_use_local_assets_and_preserve_words(
    settings: Settings, audio: Path, tmp_path: Path, monkeypatch,
) -> None:
    normalized = tmp_path / "normalized.wav"
    normalize_audio(audio, normalized)
    calls = []
    fake = types.ModuleType("whisperx")
    raw = {"segments": [{"start": 0, "end": 0.1, "text": "안녕"}]}
    aligned = {"segments": [{
        "start": 0, "end": 0.1, "text": "안녕",
        "words": [{"word": "안녕", "start": 0, "end": 0.1, "score": 0.9}],
    }]}

    def load_model(path, device, **kwargs):
        calls.append("asr")
        assert path == str(settings.models_dir / "asr")
        assert kwargs["local_files_only"] is True
        assert kwargs["vad_method"] == "pyannote"
        return types.SimpleNamespace(transcribe=lambda *args, **kw: raw)

    def load_align(language, device, **kwargs):
        calls.append("alignment")
        assert language == "ko"
        assert kwargs["model_cache_only"] is True
        assert kwargs["model_name"] == str(settings.models_dir / "align-ko")
        return object(), {}

    class Diarizer:
        def __init__(self, **kwargs):
            calls.append("diarization")
            assert kwargs["model_name"] == str(settings.models_dir / "diarization")
            assert kwargs["token"] is None

        def __call__(self, audio, **kwargs):
            assert kwargs["num_speakers"] == 2
            return "turns"

    def assign(turns, result, **kwargs):
        assert turns == "turns"
        assert kwargs["fill_nearest"] is False
        result["segments"][0]["speaker"] = "SPEAKER_01"
        result["segments"][0]["words"][0]["speaker"] = "SPEAKER_01"
        return result

    fake.load_model = load_model
    fake.load_align_model = load_align
    fake.align = lambda *args, **kwargs: aligned
    fake.assign_word_speakers = assign
    diarize_module = types.ModuleType("whisperx.diarize")
    diarize_module.DiarizationPipeline = Diarizer
    monkeypatch.setitem(sys.modules, "whisperx", fake)
    monkeypatch.setitem(sys.modules, "whisperx.diarize", diarize_module)
    result = pipeline.transcribe_normalized(normalized, replace(settings, num_speakers=2))
    assert calls == ["asr", "alignment", "diarization"]
    assert result.diarized
    assert result.segments[0].words[0].speaker == "SPEAKER_01"
    assert result.segments[0].words[0].score == 0.9


def test_silent_result_does_not_run_alignment(settings: Settings, audio: Path, tmp_path: Path, monkeypatch):
    normalized = tmp_path / "normalized.wav"
    normalize_audio(audio, normalized)
    fake = types.ModuleType("whisperx")
    fake.load_model = lambda *args, **kwargs: types.SimpleNamespace(
        transcribe=lambda *a, **k: {"segments": []},
    )
    fake.load_align_model = Mock(side_effect=AssertionError("alignment must not run for silence"))
    monkeypatch.setitem(sys.modules, "whisperx", fake)
    result = pipeline.transcribe_normalized(normalized, settings)
    assert result.segments == ()
    assert result.diarized is False
    fake.load_align_model.assert_not_called()
