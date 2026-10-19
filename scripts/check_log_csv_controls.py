from __future__ import annotations

import argparse
from pathlib import Path


_LIVE_PATCHERS: list[object] = []


def render_fixture(app_root: str, mode: str, live_worker: bool = False, recheck_outcome: str = "found") -> None:
    import csv
    import hashlib
    import io
    import json
    import sys
    from contextlib import ExitStack, nullcontext
    from unittest.mock import patch

    import streamlit as st

    if app_root not in sys.path:
        sys.path.insert(0, app_root)
    import app

    mode = st.session_state.get("log_controls_test_mode", mode)
    completed_mode = mode == "completed"
    row = {
        "date": "2026-09-04" if completed_mode else "2026-09-05",
        "name": "TEST",
        "sid": "TEST001",
        "notes": (
            "Completed test counseling note"
            if mode == "completed_pending"
            else "Test counseling note"
        ),
        "subject": "math",
    }
    rows = [row]
    if mode in {"batch_pending", "legacy_partial"}:
        rows.append(
            {
                "date": "2026-09-05",
                "name": "TEST2",
                "sid": "TEST002",
                "notes": "Second test counseling note",
                "subject": "math",
            }
        )
    text = io.StringIO()
    writer = csv.DictWriter(text, fieldnames=list(row))
    writer.writeheader()
    writer.writerows(rows)
    raw = text.getvalue().encode("utf-8-sig")
    upload = io.BytesIO(raw)
    upload.name = "test-log.csv"
    upload.size = len(raw)
    history = app.empty_log_csv_processing_history()
    if completed_mode or mode in {"batch_pending", "legacy_partial"}:
        initial_selected_indices = (
            (0,) if mode == "legacy_partial" else tuple(range(len(rows)))
        )
        entry = app.prepare_log_csv_history_entry(
            history,
            app.LogCsvHistoryStart(
                csv_hash=app.csv_bytes_sha256(raw),
                row_hashes=tuple(app.fingerprint_log_csv_rows(rows)),
                selected_indices=initial_selected_indices,
                review_indices=(),
                started_at="2026-09-05T12:00:00+09:00",
                new_row_count=1,
                source_date=row["date"],
            ),
        )
        entry = app.record_log_csv_history_outcome(
            entry, app.LogCsvHistoryUpdate(0, "success", "2026-09-05T12:01:00+09:00")
        )
        if completed_mode or mode == "legacy_partial":
            entry = app.finalize_log_csv_history_entry(entry, "2026-09-05T12:01:00+09:00")
        history = app.upsert_log_csv_history_entry(history, entry)

    # Keep real parsing, selection, history decisions and Streamlit controls.
    original_uploader = st.file_uploader

    def fixture_uploader(*args, **kwargs):
        original_uploader(*args, **kwargs)
        return None if mode == "empty" else upload

    completed_batch_state = None
    if mode in {"completed_pending", "batch_pending"}:
        signature_upload = io.BytesIO(raw)
        signature_upload.name = upload.name
        signature_upload.size = upload.size
        signature_rows, _signature_columns, _signature_encoding = app.read_log_export_csv(
            signature_upload
        )
        signature_rows, _signature_diagnostic = app.filter_consumed_admin_notes_from_log_rows(
            signature_rows,
            enabled=False,
        )
        upload_content_signature = hashlib.sha256(
            json.dumps(signature_rows, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()[:16]
        upload_signature = "|".join(
            [upload.name, str(upload.size), str(len(signature_rows)), upload_content_signature]
        )
        upload_signature_hash = hashlib.sha256(upload_signature.encode("utf-8")).hexdigest()[:12]
        completed_batch_state = app.create_log_csv_batch_state(
            upload_signature=upload_signature_hash,
            source_csv_name=upload.name,
            source_csv_size=upload.size,
            source_csv_path="",
            source_mtime_ns=0,
            selected_indices=[0],
            started_at="2026-09-05T12:00:00+09:00",
            run_id=f"fixture-{mode}-run",
        )
        completed_batch_state = app.record_log_csv_batch_result(
            completed_batch_state,
            source_index=0,
            result={
                "source_index": 0,
                "date": row["date"],
                "name": row["name"],
                "sid": row["sid"],
                "result_status": "성공",
                "결과": "성공",
                "메시지": "added",
                "doc_url": "https://example.invalid/document",
            },
            failed=False,
            updated_at="2026-09-05T12:00:30+09:00",
        )
        completed_batch_state = app.complete_log_csv_batch_state(
            completed_batch_state,
            result_log_path="C:/fixture/result.csv",
            updated_at="2026-09-05T12:01:00+09:00",
        )
        existing_batch_state = st.session_state.get("log_controls_batch_state") or {}
        rechecked_same_file = (
            str(existing_batch_state.get("run_id") or "").startswith("docs_recheck_")
            and existing_batch_state.get("upload_signature") == upload_signature_hash
        )
        if existing_batch_state.get("run_id") != completed_batch_state.get("run_id") and not rechecked_same_file:
            st.session_state["log_controls_batch_state"] = completed_batch_state

    def load_fixture_batch_state():
        return st.session_state.get("log_controls_batch_state")

    def persist_fixture_batch_state(state):
        st.session_state["log_controls_batch_state"] = state
        return True

    def load_fixture_history():
        stored = st.session_state.get("log_controls_history")
        if stored and app.find_log_csv_history_entry(stored, app.csv_bytes_sha256(raw)):
            return stored
        return history

    def save_fixture_history(_path, state):
        st.session_state["log_controls_history"] = state

    def save_fixture_batch_state(_path, state):
        if recheck_outcome == "persistence_error":
            raise OSError("Fixture checkpoint write failed")
        persist_fixture_batch_state(state)

    def verify_fixture_storage(*_args, **kwargs):
        assert kwargs.get("subject") is not None
        st.session_state["log_controls_verify_calls"] = st.session_state.get("log_controls_verify_calls", 0) + 1
        return {"ok": recheck_outcome != "unknown", "verify_only": True,
                "found_existing": recheck_outcome != "missing"}

    def execute_fixture_transfer(**kwargs):
        st.session_state["log_controls_dispatched_indices"] = kwargs["process_selected_indices"]

    def start_fixture_worker(_path, target, _on_failure):
        target()

    def fixture_auto_export(**kwargs):
        st.session_state["log_controls_auto_export_blocked"] = kwargs["is_saving"]
        return False

    mocks = {
        "release_stale_log_csv_session_lock": None,
        "restore_log_csv_auto_import_from_batch_state": None,
        "render_log_csv_auto_import_watcher": None,
        "active_auto_import_log_csv": None,
        "load_current_log_csv_processing_history": (lambda: None) if mode == "blocked" else load_fixture_history,
        "persist_current_log_csv_processing_history": True,
        "refresh_log_csv_processing_history_summary": None,
        "current_log_csv_saved_student_keys": set(),
        "load_current_log_csv_batch_state": load_fixture_batch_state,
        "persist_current_log_csv_batch_state": persist_fixture_batch_state,
        "render_log_csv_persisted_progress": None,
        "admin_consumed_filter_enabled": False,
        "load_google_docs_map_rows": [
            {"student_name": "TEST", "doc_id": "test-only"},
            {"student_name": "TEST2", "doc_id": "test-only-2"},
        ],
        "load_admin_api_base_url": "https://example.invalid",
        "load_admin_students_from_api": [],
        "load_google_apps_script_webapp_url": "" if mode == "unconfigured" else "https://example.invalid/exec",
        "should_auto_export_log_csv": fixture_auto_export,
        "verify_summary_in_google_doc_after_timeout": verify_fixture_storage,
    }
    st.session_state["log_csv_to_docs_is_saving"] = mode == "saving"
    if live_worker:
        mocks.pop("load_current_log_csv_batch_state")
        mocks.pop("persist_current_log_csv_batch_state")
        mocks.pop("render_log_csv_persisted_progress")
    else:
        mocks["csv_worker_is_running"] = False
        mocks["CsvRunLease"] = lambda _path: nullcontext()
        mocks["load_log_csv_processing_history"] = lambda _path: load_fixture_history()
        mocks["save_log_csv_processing_history"] = save_fixture_history
        mocks["save_log_csv_batch_state"] = save_fixture_batch_state
        mocks["start_csv_worker"] = start_fixture_worker
        mocks["execute_log_csv_transfer"] = execute_fixture_transfer
    if live_worker:
        if not _LIVE_PATCHERS:
            for name, value in mocks.items():
                patcher = (
                    patch.object(app, name, side_effect=value)
                    if callable(value)
                    else patch.object(app, name, return_value=value)
                )
                patcher.start()
                _LIVE_PATCHERS.append(patcher)
            for patcher in (
                patch.object(st, "file_uploader", side_effect=fixture_uploader),
                patch(
                    "requests.sessions.Session.request",
                    side_effect=AssertionError("No network in UI checks"),
                ),
                patch.object(
                    app,
                    "sync_admin_notes",
                    side_effect=AssertionError("No admin writes in UI checks"),
                ),
            ):
                patcher.start()
                _LIVE_PATCHERS.append(patcher)
        app.render_log_csv_to_docs_preview_ui(st.empty())
        return

    with ExitStack() as stack:
        for name, value in mocks.items():
            if callable(value):
                stack.enter_context(patch.object(app, name, side_effect=value))
            else:
                stack.enter_context(patch.object(app, name, return_value=value))
        stack.enter_context(patch.object(st, "file_uploader", side_effect=fixture_uploader))
        stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("No network in UI checks")))
        stack.enter_context(patch.object(app, "sync_admin_notes", side_effect=AssertionError("No admin writes in UI checks")))
        app.render_log_csv_to_docs_preview_ui(st.empty())


def main() -> None:
    from streamlit.testing.v1 import AppTest

    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    for mode in (
        "completed",
        "completed_pending",
        "batch_pending",
        "legacy_partial",
        "new",
        "empty",
        "saving",
        "blocked",
        "unconfigured",
    ):
        at = AppTest.from_function(render_fixture, args=(args.app_root, mode)).run(timeout=30)
        assert not at.exception, (mode, [exc.message for exc in at.exception])
        buttons = [button for button in at.button if button.key == "log_csv_to_docs_save_button"]
        if mode == "saving":
            assert not buttons, "Saving must hide the action"
        else:
            assert len(buttons) == 1, f"{mode}: log action is missing"
            button = buttons[0]
            assert button.label == "선택한 기록을 학생 Docs에 추가"
            assert button.disabled == (mode not in {"new", "legacy_partial"}), mode
        if mode in {"empty", "completed", "completed_pending"}:
            assert not at.dataframe, f"{mode}: completed/empty list must stay hidden"
        if mode == "completed_pending":
            confirmation = [button for button in at.button if button.label == "오늘 전체 완료 확인"]
            assert len(confirmation) == 1, "Completion result must wait for acknowledgement"
            assert any(item.value == "저장 결과" for item in at.subheader)
            confirmation[0].click().run(timeout=30)
            assert not at.exception, [exc.message for exc in at.exception]
            assert not [button for button in at.button if button.label == "오늘 전체 완료 확인"]
            assert not at.dataframe
            assert at.button(key="log_csv_to_docs_save_button").disabled
        if mode == "batch_pending":
            confirmation = [button for button in at.button if button.label == "이번 묶음 확인"]
            assert len(confirmation) == 1, "A partial batch must wait for acknowledgement"
            assert any(
                item.value == "이번 묶음 처리 완료 · 오늘 전체 1/2건 · 저장 완료 1명" for item in at.success
            )
            assert at.button(key="log_csv_to_docs_save_button").disabled
            confirmation[0].click().run(timeout=30)
            assert not at.exception, [exc.message for exc in at.exception]
            assert not [button for button in at.button if button.label == "이번 묶음 확인"]
            assert not [item for item in at.subheader if item.value == "저장 결과"]
            assert len(at.dataframe) == 1
            assert bool(at.dataframe[0].value.iloc[0]["선택"])
            assert not at.button(key="log_csv_to_docs_save_button").disabled
        if mode == "legacy_partial":
            assert len(at.dataframe) == 1
            assert bool(at.dataframe[0].value.iloc[0]["선택"])
            assert not at.button(key="log_csv_to_docs_save_button").disabled
            assert not [item for item in at.success if "오늘 전체 처리 완료" in item.value]
        if mode == "new":
            assert len(at.dataframe) == 1
            assert bool(at.dataframe[0].value.iloc[0]["선택"])
        print(f"PASS: log CSV controls ({mode})")

    at = AppTest.from_function(render_fixture, args=(args.app_root, "completed")).run(timeout=30)
    at.session_state["log_controls_test_mode"] = "new"
    at.run(timeout=30)
    assert not at.exception
    assert not at.button(key="log_csv_to_docs_save_button").disabled
    assert bool(at.dataframe[0].value.iloc[0]["선택"])
    print("PASS: completed CSV replaced by new CSV in the same session")

    at = AppTest.from_function(render_fixture, args=(args.app_root, "completed")).run(timeout=30)
    assert not at.exception
    assert any(button.label == "Docs 저장 다시 확인" for button in at.button), (
        "A completed CSV cannot be rechecked when the user reports missing Docs content"
    )
    for outcome in ("found", "missing", "unknown", "persistence_error"):
        at = AppTest.from_function(
            render_fixture, args=(args.app_root, "completed", False, outcome),
        ).run(timeout=30)
        next(button for button in at.button if button.label == "Docs 저장 다시 확인").click().run(timeout=30)
        assert not at.exception, [exc.message for exc in at.exception]
        assert at.session_state["log_controls_verify_calls"] == 1
        if outcome == "persistence_error":
            assert any("재확인 결과를 저장하지 못했습니다" in item.value for item in at.error)
            assert at.button(key="log_csv_to_docs_save_button").disabled
            print("PASS: completed CSV storage recheck (persistence_error)")
            continue
        retry = next(button for button in at.button if button.label == "문제 학생만 다시 저장")
        assert retry.disabled == (outcome != "missing"), outcome
        entries = at.session_state["log_controls_history"]["entries"]
        assert entries[-1]["status"] == ("completed" if outcome == "found" else "needs_review")
        if outcome == "missing":
            assert not any("오늘 전체 처리 완료" in item.value for item in at.success)
        if outcome == "unknown":
            assert any(button.label == "Docs 저장 다시 확인" for button in at.button)
        at.run(timeout=30)
        assert not at.exception
        assert at.session_state["log_controls_history"]["entries"][-1]["status"] == entries[-1]["status"]
        assert next(button for button in at.button if button.label == "문제 학생만 다시 저장").disabled == (outcome != "missing")
        if outcome == "missing":
            next(button for button in at.button if button.label == "문제 학생만 다시 저장").click().run(timeout=30)
            assert not at.exception, [exc.message for exc in at.exception]
            assert at.session_state["log_controls_dispatched_indices"] == [0]
        if outcome == "unknown":
            next(button for button in at.button if button.label == "이번 묶음 확인").click().run(timeout=30)
            assert not at.exception
            assert at.session_state["log_controls_auto_export_blocked"]
        print(f"PASS: completed CSV storage recheck ({outcome})")

    from counsel_modules.log_csv_recheck import LogCsvStorageResponse, classify_log_csv_storage_check
    for response in (
        LogCsvStorageResponse(True, True, None),
        LogCsvStorageResponse(True, False, True),
        LogCsvStorageResponse(False, True, False),
    ):
        assert classify_log_csv_storage_check(0, response).outcome == "review"
    print("PASS: incomplete confirmation responses never reopen writes automatically")


if __name__ == "__main__":
    main()
