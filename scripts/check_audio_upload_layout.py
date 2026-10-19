from __future__ import annotations

import argparse
from pathlib import Path


def render_fixture(app_root: str, slow: bool = False) -> None:
    import importlib.util
    import io
    import sys
    import time
    from contextlib import ExitStack
    from datetime import date
    from pathlib import Path
    from unittest.mock import patch

    import streamlit as st
    from streamlit.delta_generator import DeltaGenerator

    sys.path.insert(0, app_root)
    spec = importlib.util.spec_from_file_location("upload_layout_fixture_app", Path(app_root) / "app.py")
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    spec.loader.exec_module(app)

    mode = st.selectbox("Upload state", ["empty", "single", "batch", "summary"], key="test_upload_mode")
    uploads = []
    for index in range(2 if mode == "batch" else int(mode == "single")):
        upload = io.BytesIO(b"test audio")
        upload.name = f"TEST{index}.wav"
        upload.size = len(upload.getvalue())
        uploads.append(upload)

    def initialize_state() -> None:
        st.session_state.setdefault("student_name", "TEST")
        st.session_state.setdefault("author_name", "TEST")
        st.session_state.setdefault("counseling_date_input", date(2026, 9, 5))
        st.session_state["form_transcript_key"] = "2026-09-05|TEST|TEST"
        st.session_state["latest_summary"] = (
            "*상담 참고사항*\n- 다음 수업 전 숙제 풀이 흔적을 확인하기로 함."
            if mode == "summary" else ""
        )
        st.session_state["summary_status"] = app.SUMMARY_STATUS_READY if mode == "summary" else ""
        st.session_state["current_audio_path"] = "test-only.wav" if uploads else None

    original_uploader = DeltaGenerator.file_uploader

    def render_uploader(dg, *args, **kwargs):
        value = original_uploader(dg, *args, **kwargs)
        return uploads if kwargs.get("accept_multiple_files") is True else value

    original_preview = app.render_log_csv_to_docs_preview_ui

    def render_csv(*args, **kwargs) -> None:
        # Hold the run at the transition so stale blocks are observable in-browser.
        if slow:
            time.sleep(2)
        original_preview(*args, **kwargs)
        if slow:
            time.sleep(4)

    mocks = {
        "ensure_project_structure": [],
        "ensure_default_glossary_file": None,
        "ensure_admin_settings_files": None,
        "check_required_project_files": [],
        "initialize_audio_batch_session_state": None,
        "sync_counseling_date_to_kst_today": None,
        "continue_running_audio_batch_if_needed": None,
        "run_recording_cleanup_once_per_session": None,
        "run_app_maintenance_cleanup_once_per_session": None,
        "save_draft": None,
        "save_uploaded_file_copy": None,
        "get_default_author_name": "TEST",
        "load_google_docs_map": {},
        "render_google_apps_script_url_settings_ui": None,
        "render_google_docs_mapping_add_ui": None,
        "transcript_date_dir": Path(app_root),
        "transcripts_for_date": [],
        "load_current_log_csv_processing_history": app.empty_log_csv_processing_history(),
        "release_stale_log_csv_session_lock": None,
        "restore_log_csv_auto_import_from_batch_state": None,
        "render_log_csv_auto_import_watcher": None,
        "active_auto_import_log_csv": None,
        "csv_worker_is_running": False,
        "render_admin_notes_save_ui": None,
    }
    with ExitStack() as stack:
        for name, result in mocks.items():
            stack.enter_context(patch.object(app, name, return_value=result))
        stack.enter_context(patch.object(app, "initialize_draft_state", side_effect=initialize_state))
        stack.enter_context(patch.object(app, "render_log_csv_to_docs_preview_ui", side_effect=render_csv))
        stack.enter_context(patch.object(DeltaGenerator, "file_uploader", new=render_uploader))
        stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("No network in layout checks")))
        app.main()


def csv_path(node, path=()):
    if node.type == "expander" and node.label == "로그 CSV → 학생 Docs 추가":
        return path
    for index, child in getattr(node, "children", {}).items():
        result = csv_path(child, (*path, index))
        if result is not None:
            return result
    return None


def main() -> None:
    from streamlit.testing.v1 import AppTest

    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    at = AppTest.from_function(render_fixture, args=(args.app_root,)).run(timeout=30)
    assert not at.exception, [error.message for error in at.exception]
    expected = csv_path(at._tree)
    assert expected is not None
    for mode in ("single", "batch", "empty", "summary", "single"):
        at.selectbox(key="test_upload_mode").select(mode).run(timeout=30)
        assert not at.exception, [error.message for error in at.exception]
        assert len([el for el in at.expander if el.label == "로그 CSV → 학생 Docs 추가"]) == 1
        actual = csv_path(at._tree)
        assert actual == expected, f"{mode}: CSV moved from {expected} to {actual}; old blocks can linger"
        assert at.button(key="log_csv_to_docs_save_button").label == "선택한 기록을 학생 Docs에 추가"
        print(f"PASS: stable CSV slot after {mode} upload state")


if __name__ == "__main__":
    main()
