from __future__ import annotations

from pathlib import Path


def render_contract_fixture(app_root: str) -> None:
    import sys
    from contextlib import ExitStack
    from datetime import datetime
    from pathlib import Path
    from unittest.mock import patch
    from zoneinfo import ZoneInfo

    import streamlit as st

    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    scripts = str(Path(app_root) / "scripts")
    if scripts not in sys.path:
        sys.path.append(scripts)
    import app
    from check_log_csv_controls import render_fixture as render_csv_fixture

    st.set_page_config(page_title="Connect Log UI contract", layout="wide")
    state = st.radio(
        "Fixture state",
        ("empty", "selected", "saving", "batch_pending", "completed_pending", "completed"),
        horizontal=True,
        key="baseline-state",
    )
    st.html(f'<span id="ui-contract-state" data-state="{state}"></span>')
    app.apply_ui_refresh_styles()
    st.title("5A Connect Log")
    history = app.empty_log_csv_processing_history()
    entry = app.prepare_log_csv_history_entry(history, app.LogCsvHistoryStart(
        csv_hash="fixture-only", row_hashes=("row-one", "row-two"),
        selected_indices=(0, 1), review_indices=(),
        started_at="2026-09-05T12:00:00+09:00", new_row_count=2,
        source_date="2026-09-05",
    ))
    if state in {"saving", "batch_pending", "completed_pending", "completed"}:
        entry = app.record_log_csv_history_outcome(
            entry, app.LogCsvHistoryUpdate(0, "success", "2026-09-05T12:01:00+09:00")
        )
        if state in {"completed_pending", "completed"}:
            entry = app.record_log_csv_history_outcome(
                entry, app.LogCsvHistoryUpdate(1, "success", "2026-09-05T12:02:00+09:00")
            )
        history = app.upsert_log_csv_history_entry(history, entry)

    # Render actual components, but never dispatch an operation from a fixture button.
    original_button = st.button

    def inert_button(*args, **kwargs):
        original_button(*args, **kwargs)
        return False

    with ExitStack() as stack:
        stack.enter_context(patch.object(st, "button", side_effect=inert_button))
        saved_students = {
            ("2026-09-05", f"test-student-{index}")
            for index, outcome in enumerate(entry["outcomes"])
            if outcome == "success"
        }
        stack.enter_context(patch.object(app, "current_log_csv_saved_student_keys", return_value=saved_students))
        with st.container(key="contract-screen"):
            left, center, right = st.columns([0.9, 1.45, 1.0], gap="large")
            with left:
                st.subheader("상담 정보")
                st.text_input("학생명", "TEST", disabled=True)
                st.text_input("작성자", "TEST", disabled=True)
            with center:
                upload, action, history_target = app.create_audio_log_overview()
                with upload:
                    st.file_uploader("상담 녹음 파일 업로드 · 최대 30개",
                                     type=["m4a", "mp3", "wav"], accept_multiple_files=True,
                                     label_visibility="collapsed", disabled=state == "saving")
                with action:
                    st.button("정리본 생성·복사", disabled=state != "selected")
                with patch.object(app, "datetime", wraps=datetime) as clock:
                    clock.now.return_value = datetime(2026, 9, 5, 12, 2, tzinfo=ZoneInfo("Asia/Seoul"))
                    app.refresh_log_csv_processing_history_summary(history_target, history)
                with st.container(key="audio-details"):
                    pass
                with st.container(key="log-csv-workspace"):
                    render_csv_fixture(app_root, "new" if state == "selected" else state)
            with right:
                st.subheader("처리 상태")
                st.write("저장 중" if state == "saving" else "대기 중")
                st.divider()
                st.subheader("오늘 정리본 생성 기록")


if __name__ == "__main__":
    render_contract_fixture(str(Path(__file__).resolve().parents[1]))
