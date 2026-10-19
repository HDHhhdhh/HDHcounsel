from __future__ import annotations

import csv
from contextlib import redirect_stderr
from datetime import date
from io import StringIO
from pathlib import Path
import sys
import tempfile
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def check_confirmed_history_counts_survive_missing_result_files() -> None:
    with redirect_stderr(StringIO()):
        import app

    rows = [
        {"date": "2026-10-05", "name": "TEST-A", "sid": "a", "notes": "note\nline"},
        {"date": "2026-10-05", "name": "TEST-A", "sid": "a", "notes": "second"},
        {"date": "2026-10-05", "name": "TEST-B", "sid": "b", "notes": "note"},
        {"date": "2026-10-05", "name": "TEST-C", "sid": "c", "notes": "failed"},
    ]
    output = StringIO(newline="")
    writer = csv.DictWriter(output, fieldnames=list(rows[0]))
    writer.writeheader()
    writer.writerows(rows)
    raw = output.getvalue().encode("utf-8-sig")
    history = app.empty_log_csv_processing_history()
    entry = app.prepare_log_csv_history_entry(history, app.LogCsvHistoryStart(
        csv_hash=app.csv_bytes_sha256(raw), row_hashes=tuple(app.fingerprint_log_csv_rows(rows)),
        selected_indices=(0, 1, 2, 3), review_indices=(), started_at="2026-10-05T12:00:00+09:00",
        source_date="2026-10-05", new_row_count=0,
    ))
    for index, outcome in enumerate(("success", "duplicate", "success", "failure")):
        entry = app.record_log_csv_history_outcome(entry, app.LogCsvHistoryUpdate(
            index, outcome, "2026-10-05T12:01:00+09:00",
        ))
    history = app.upsert_log_csv_history_entry(history, entry)
    mapping = [
        {"student_name": f"TEST-{name}", "doc_id": f"doc-{name}", "doc_url": ""}
        for name in "ABC"
    ]
    with tempfile.TemporaryDirectory() as temporary:
        directory = Path(temporary)
        exports = directory / "Downloads"
        exports.mkdir()
        source = exports / "수업기록_선택일_2026-10-05.csv"
        source.write_bytes(raw)
        with (
            patch.object(app.st, "session_state", {}),
            patch.object(app, "GOOGLE_DOCS_APPEND_LOG_DIR", directory / "missing-results"),
            patch.object(app, "load_current_log_csv_batch_state", return_value=None),
            patch.object(app, "load_current_log_csv_processing_history", return_value=history),
            patch.object(app, "default_log_csv_downloads_dir", return_value=exports),
            patch.object(app, "load_google_docs_map_rows", return_value=mapping),
        ):
            confirmed = app.current_log_csv_saved_student_keys()
            assert confirmed is not None and len(confirmed) == 2, "Missing result logs erased confirmed unique students"
            source.write_bytes(raw + b"\r\n")
            assert app.current_log_csv_saved_student_keys() == set(), "A different export must not count as confirmation"


def render_review_fixture(app_root: str) -> None:
    import sys
    from pathlib import Path
    import streamlit as st

    sys.path.insert(0, app_root)
    import app

    app.load_admin_api_base_url = lambda: "https://example.invalid"
    app.find_admin_sid_candidates_for_student = lambda *_: []
    app.save_audio_batch_state = lambda *_: None
    if "audio_batch_state" not in st.session_state:
        jobs = [app.create_audio_batch_job(
            audio_path=f"C:/fixture/{index}.wav", source_name=f"TEST-{index}.wav",
            student_name=f"TEST-{index}", author_name="TEST", counseling_date="2026-10-09",
            processing_mode="balanced", summary_style="default", use_vad=False, use_prompt_hint=False,
        ) for index in range(3)]
        state = app.create_audio_batch_state(jobs, "2026-10-09T12:00:00")
        for index, job in enumerate(jobs):
            state = app.update_audio_batch_job(
                state, job["job_id"], status="completed", detail="done",
                transcript_path=f"C:/fixture/{index}.txt", summary=f"*상담 참고사항*\n- TEST-{index} 정리본",
                updated_at="2026-10-09T12:01:00",
            )
            state["jobs"][index]["admin_saved"] = True
            state["jobs"][index]["admin_sid"] = f"TEST-SID-{index}"
        st.session_state["audio_batch_state"] = state
    app.render_audio_batch_state_ui(False)


def check_arrows_review_each_summary_and_preserve_edits() -> None:
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_function(render_review_fixture, args=(str(ROOT),)).run(timeout=30)
    assert not at.exception, [item.message for item in at.exception]
    next_buttons = [button for button in at.button if button.key == "audio_batch_summary_next"]
    assert len(next_buttons) == 1, "Batch status has no next-summary arrow"
    jobs = at.session_state["audio_batch_state"]["jobs"]
    assert at.text_area(key=f"audio_batch_review_{jobs[0]['job_id']}").value.endswith("TEST-0 정리본")
    assert at.button(key="audio_batch_summary_previous").disabled
    edited = "*상담 참고사항*\n- TEST-0 수정본"
    at.text_area(key=f"audio_batch_review_{jobs[0]['job_id']}").set_value(edited)
    at.button(key="audio_batch_summary_next").click().run(timeout=30)
    assert not at.exception, [item.message for item in at.exception]
    assert at.text_area(key=f"audio_batch_review_{jobs[1]['job_id']}").value.endswith("TEST-1 정리본")
    assert at.session_state["audio_batch_state"]["jobs"][0]["summary"] == edited
    assert not at.session_state["audio_batch_state"]["jobs"][0]["admin_saved"]
    at.button(key="audio_batch_summary_next").click().run(timeout=30)
    assert at.button(key="audio_batch_summary_next").disabled
    at.button(key="audio_batch_summary_previous").click().run(timeout=30)
    at.button(key="audio_batch_summary_previous").click().run(timeout=30)
    assert at.text_area(key=f"audio_batch_review_{jobs[0]['job_id']}").value == edited
    assert not any(button.label == "5A ADMIN 특이사항으로 내보내기" for button in at.button)


def check_incomplete_edited_summary_is_not_saved() -> None:
    with redirect_stderr(StringIO()):
        import app
    job = app.create_audio_batch_job(
        audio_path="C:/fixture/test.wav", source_name="test.wav", student_name="TEST",
        author_name="TEST", counseling_date="2026-10-09", processing_mode="balanced",
        summary_style="default", use_vad=False, use_prompt_hint=False,
    )
    state = app.create_audio_batch_state([job], "2026-10-09T12:00:00")
    state = app.update_audio_batch_job(
        state, job["job_id"], status="completed", detail="edited", transcript_path="fixture.txt",
        summary="진도(수학): 1쪽", updated_at="2026-10-09T12:01:00",
    )
    session = {"audio_batch_state": state}
    with (
        patch.object(app.st, "session_state", session),
        patch.object(app, "persist_audio_batch_session_state", side_effect=lambda value: session.update(audio_batch_state=value)),
        patch.object(app, "find_admin_sid_candidates_for_student", return_value=[{"admin_sid": "TEST-SID"}]),
        patch.object(app, "load_admin_api_base_url", return_value="https://example.invalid"),
        patch.object(app, "sync_admin_notes", return_value=app.AdminNotesSyncResult(True, "saved", None, {"ok": True})) as sync,
    ):
        app.save_audio_batch_job_to_admin(job["job_id"])
        sync.assert_not_called()
        assert not session["audio_batch_state"]["jobs"][0]["admin_saved"]


def main() -> None:
    with redirect_stderr(StringIO()):
        import app
    result_policy = next(policy for policy in app.APP_MAINTENANCE_CLEANUP_POLICIES
                         if policy["root"] == app.GOOGLE_DOCS_APPEND_LOG_DIR)
    assert result_policy["days"] >= 7, "Recent attendance counts lose their result logs after one day"
    check_confirmed_history_counts_survive_missing_result_files()
    print("PASS: historical confirmation counts without result CSVs")
    check_arrows_review_each_summary_and_preserve_edits()
    print("PASS: batch review arrows, boundaries and per-student edits")
    check_incomplete_edited_summary_is_not_saved()
    print("PASS: edited summaries retain existing save validation")


if __name__ == "__main__":
    main()
