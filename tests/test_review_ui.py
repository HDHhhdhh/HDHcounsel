from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from hdhcounsel import ui
from hdhcounsel.config import Settings
from hdhcounsel.domain import Segment, Transcript
from hdhcounsel.storage import Record


def test_fresh_ui_needs_no_private_google_configuration(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(tmp_path / "missing-models", tmp_path / "records")
    monkeypatch.setattr(Settings, "load", lambda path=None: settings)
    app = AppTest.from_file(str(Path(ui.__file__))).run()
    assert not app.exception
    assert app.button[0].disabled
    assert not settings.output_dir.exists()


def test_review_save_preserves_original_transcript(tmp_path: Path, monkeypatch) -> None:
    settings = Settings(tmp_path / "missing-models", tmp_path / "records")
    monkeypatch.setattr(Settings, "load", lambda path=None: settings)
    transcript = Transcript((Segment(0, 1, "다음 주에 확인합니다", "SPEAKER_00"),), 1, diarized=True)
    record = Record.create(settings.output_dir, "합성 학생", "2026-10-19", transcript)
    evidence = (record.path / "transcript.json").read_bytes()
    app = AppTest.from_file(str(Path(ui.__file__)))
    app.session_state["record"] = record
    app.session_state["notes"] = "검수 완료"
    app.session_state["reviewed"] = True
    app.run()
    assert not app.exception
    next(button for button in app.button if button.label == "검수 기록 저장").click().run()
    assert not app.exception
    review = json.loads((record.path / "review.json").read_text(encoding="utf-8"))
    assert review["notes"] == "검수 완료"
    assert review["reviewed"] is True
    assert (record.path / "transcript.json").read_bytes() == evidence
