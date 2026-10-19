from __future__ import annotations

import atexit
import sys
import tempfile
import threading
from pathlib import Path

import streamlit as st

from check_csv_worker import load_app
from check_log_csv_controls import render_fixture


@st.cache_resource
def fixture_runtime():
    root = Path(__file__).resolve().parents[1]
    app = load_app(root, None)
    sys.modules["app"] = app
    directory = tempfile.TemporaryDirectory(prefix="csv-browser-fixture-")
    atexit.register(directory.cleanup)
    folder = Path(directory.name)
    app.LOG_CSV_DOCS_STATE_PATH = folder / "run.json"
    app.LOG_CSV_PROCESSING_HISTORY_PATH = folder / "history.json"
    app.LOG_CSV_WORKER_LOCK_PATH = folder / "worker.lock"
    app.GOOGLE_DOCS_TIMEOUT_VERIFY_PAUSE_SECONDS = 0
    release = threading.Event()
    calls: list[str] = []

    def fake_post(*args, **kwargs):
        calls.append("POST")
        if not release.wait(120):
            raise TimeoutError("Fixture response was not released")
        return {"ok": True, "message": "added"}

    def reject_network(*args, **kwargs):
        raise AssertionError("Real network is disabled in this fixture")

    import requests

    requests.sessions.Session.request = reject_network
    app.append_summary_to_google_doc = fake_post
    app.verify_summary_in_google_doc_after_timeout = reject_network
    app.sync_admin_notes = reject_network
    app.save_log_csv_to_docs_result_log = lambda *args, **kwargs: folder / "result.csv"
    return app, release, calls, directory


st.set_page_config(page_title="CSV Worker Fixture")
runtime, release_response, post_calls, temporary_directory = fixture_runtime()
st.title("CSV Worker Fixture")
if st.button("검사 응답 완료"):
    release_response.set()


evidence_run_every = (
    None
    if (
        runtime.load_log_csv_batch_state(runtime.LOG_CSV_DOCS_STATE_PATH) or {}
    ).get("status") == "completed"
    else 1
)


@st.fragment(run_every=evidence_run_every)
def evidence():
    state = runtime.load_log_csv_batch_state(runtime.LOG_CSV_DOCS_STATE_PATH)
    st.code({
        "fake_post_count": len(post_calls),
        "worker_running": runtime.csv_worker_is_running(runtime.LOG_CSV_WORKER_LOCK_PATH),
        "status": state.get("status") if state else "idle",
        "completed": state.get("completed_count", 0) if state else 0,
    })


evidence()
render_fixture(str(Path(__file__).resolve().parents[1]), "new", live_worker=True)
