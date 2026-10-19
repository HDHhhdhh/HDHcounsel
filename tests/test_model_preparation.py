from __future__ import annotations

import json
import sys
import types
from pathlib import Path

import pytest

from hdhcounsel.config import CounselError, Settings
from hdhcounsel.prepare import prepare_models
from hdhcounsel.storage import write_json


def test_prepare_pins_downloads_and_keeps_existing_diarization_revision(tmp_path: Path, monkeypatch):
    config = Settings(tmp_path / "models", tmp_path / "records", diarize=False)
    write_json(config.models_dir / "manifest.json", {"pyannote/speaker-diarization-community-1": "prior-sha"})
    calls = []
    hub = types.ModuleType("huggingface_hub")
    hub.HfApi = lambda: types.SimpleNamespace(model_info=lambda *a, **k: types.SimpleNamespace(sha="new-sha"))
    hub.snapshot_download = lambda repository, **kwargs: calls.append((repository, kwargs))
    nltk = types.ModuleType("nltk")
    nltk.download = lambda *a, **k: True
    nltk.data = types.SimpleNamespace(path=[], load=lambda *a: None)
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setitem(sys.modules, "nltk", nltk)
    monkeypatch.setattr(Settings, "validate_assets", lambda self: None)
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("PYANNOTE_METRICS_ENABLED", "0")
    monkeypatch.delenv("HF_TOKEN", raising=False)
    manifest = prepare_models(config)
    assert len(calls) == 2
    assert all(kwargs["revision"] == "new-sha" and kwargs["token"] is False for _, kwargs in calls)
    assert manifest["pyannote/speaker-diarization-community-1"] == "prior-sha"
    assert json.loads((config.models_dir / "manifest.json").read_text()) == manifest


def test_prepare_error_does_not_expose_authentication_details(tmp_path: Path, monkeypatch):
    hub = types.ModuleType("huggingface_hub")

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic-private-token-value")

    hub.HfApi = lambda: types.SimpleNamespace(model_info=fail)
    hub.snapshot_download = fail
    monkeypatch.setitem(sys.modules, "huggingface_hub", hub)
    monkeypatch.setenv("HF_HUB_DISABLE_TELEMETRY", "1")
    monkeypatch.setenv("PYANNOTE_METRICS_ENABLED", "0")
    with pytest.raises(CounselError) as caught:
        prepare_models(Settings(tmp_path, tmp_path))
    assert "synthetic-private-token-value" not in str(caught.value)
