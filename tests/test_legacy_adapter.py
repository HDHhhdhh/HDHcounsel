"""Exercise the real adapter function without importing the operational app."""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

from hdhcounsel.config import Settings
from hdhcounsel.domain import Segment, Transcript


def adapter():
    source = Path(__file__).resolve().parents[1] / "app.py"
    tree = ast.parse(source.read_text(encoding="utf-8"))
    function = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == "transcribe_audio")
    module = ast.Module(body=[
        ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0),
        function,
    ], type_ignores=[])
    ast.fix_missing_locations(module)
    namespace = {"format_timestamp": lambda value: f"{int(value) // 60:02}:{int(value) % 60:02}"}
    exec(compile(module, str(source), "exec"), namespace)
    return namespace["transcribe_audio"]


def test_legacy_adapter_preserves_tuple_and_row_timestamp_contract(tmp_path: Path, monkeypatch) -> None:
    import hdhcounsel.service

    result = Transcript((Segment(0.25, 65.9, "합성 발화", "SPEAKER_00"),), 66, diarized=True)
    monkeypatch.setattr(hdhcounsel.service, "transcribe", lambda source, settings: result)
    text, rows = adapter()(tmp_path / "input.wav", Settings(tmp_path, tmp_path), 5, True)
    assert "SPEAKER_00" in text
    assert rows == [{"start": "00:00", "end": "01:05", "text": "합성 발화", "speaker": "SPEAKER_00"}]


def test_legacy_adapter_propagates_empty_transcript_as_failure(tmp_path: Path, monkeypatch) -> None:
    import hdhcounsel.service

    monkeypatch.setattr(hdhcounsel.service, "transcribe", lambda source, settings: Transcript((), 1))
    with pytest.raises(RuntimeError):
        adapter()(tmp_path / "input.wav", Settings(tmp_path, tmp_path), 5, True)
