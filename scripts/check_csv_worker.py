from __future__ import annotations

import argparse
import importlib.util
import sys
import tempfile
import threading
import time
from contextlib import ExitStack
from copy import deepcopy
from pathlib import Path
from unittest.mock import patch


def load_app(root: Path, overlay: Path | None):
    import streamlit as st

    sys.path.insert(0, str(root))
    import counsel_modules

    if overlay:
        counsel_modules.__path__.insert(0, str(overlay / "counsel_modules"))
    spec = importlib.util.spec_from_file_location("csv_worker_test_app", root / "app.py")
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    source = (overlay or root) / "app.py"
    with patch.object(st, "stop"), patch.object(st, "error"), patch.object(st, "warning"), patch.object(st, "write"), patch.object(st, "caption"):
        exec(compile(source.read_text(encoding="utf-8-sig"), str(source), "exec"), app.__dict__)
    return app


def transfer_args(app):
    rows = [
        {"date": "2026-09-06", "name": f"TEST{index}", "sid": f"TEST{index}", "notes": "Test note", "subject": "math"}
        for index in range(2)
    ]
    maps = [{"student_name": row["name"], "doc_id": f"test-doc-{index}"} for index, row in enumerate(rows)]
    matches = app.match_log_rows_to_docs(rows, maps)
    history = app.empty_log_csv_processing_history()
    entry = app.prepare_log_csv_history_entry(history, app.LogCsvHistoryStart(
        csv_hash="fixture", row_hashes=tuple(app.fingerprint_log_csv_rows(rows)),
        selected_indices=(0, 1), review_indices=(), new_row_count=2,
        started_at="2026-09-06T12:00:00+09:00", source_date="2026-09-06",
    ))
    state = app.create_log_csv_batch_state(
        upload_signature="fixture", source_csv_name="test.csv", source_csv_size=1,
        source_csv_path="", source_mtime_ns=0, selected_indices=[0, 1],
        started_at="2026-09-06T12:00:00+09:00", run_id="test-run",
    )
    return dict(
        batch_pause_seconds=0, completed_before=0, consumed_filter_enabled=False,
        history_entry=entry, lock_retry_pause_seconds=0, matched_rows=matches,
        process_selected_indices=[0, 1], processing_history=history, results=[],
        retry_attempt=0, retry_of_run_id="", retry_run_active=False,
        retry_source_status_by_index={}, row_pause_seconds=0, run_scope_indices=[0, 1],
        run_state=state, save_batch_size=5, source_csv_name="test.csv", source_csv_size=1,
        web_app_url="https://example.invalid/exec",
    )


def render_worker_ui_fixture(app_root: str, scripts_root: str) -> None:
    import sys
    from pathlib import Path

    sys.path.insert(0, scripts_root)
    from check_log_csv_controls import render_fixture

    render_fixture(app_root, "new", live_worker=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--overlay", type=Path)
    args = parser.parse_args()
    app = load_app(args.app_root, args.overlay)
    sys.modules["app"] = app
    original_session_state = app.st.session_state
    from counsel_modules.log_csv_worker import CsvRunBusyError, csv_worker_is_running, start_csv_worker
    from streamlit.runtime.scriptrunner_utils.exceptions import RerunException
    from streamlit.runtime.scriptrunner_utils.script_requests import RerunData, ScriptRequests

    with tempfile.TemporaryDirectory(prefix="csv-worker-test-") as directory, ExitStack() as mocks:
        class NoSessionState:
            def __getattr__(self, name):
                raise AssertionError("Worker must not read Streamlit session state")

            def __getitem__(self, name):
                raise AssertionError("Worker must not read Streamlit session state")

            def __setitem__(self, name, value):
                raise AssertionError("Worker must not write Streamlit session state")

        mocks.enter_context(patch.object(app.st, "session_state", NoSessionState()))
        folder = Path(directory)
        from counsel_modules import local_consumed_admin_notes

        mocks.enter_context(patch.object(local_consumed_admin_notes, "CONSUMED_ADMIN_NOTES_PATH", folder / "consumed.json"))
        checkpoint = folder / "run.json"
        history_path = folder / "history.json"
        lock_path = folder / "worker.lock"
        mocks.enter_context(patch.object(app, "LOG_CSV_DOCS_STATE_PATH", checkpoint))
        mocks.enter_context(patch.object(app, "LOG_CSV_PROCESSING_HISTORY_PATH", history_path))
        mocks.enter_context(patch.object(app, "LOG_CSV_WORKER_LOCK_PATH", lock_path))
        mocks.enter_context(patch.object(app, "GOOGLE_DOCS_TIMEOUT_VERIFY_PAUSE_SECONDS", 0))
        mocks.enter_context(patch.object(app, "save_log_csv_to_docs_result_log", return_value=folder / "result.csv"))
        mocks.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("No real network in worker tests")))
        entered, release = threading.Event(), threading.Event()
        calls = []

        def slow_post(*values, **kwargs):
            calls.append(values[1])
            entered.set()
            assert release.wait(10), "Test transport was not released"
            return {"ok": True, "message": "added"}

        request = transfer_args(app)
        with patch.object(app, "append_summary_to_google_doc", side_effect=slow_post):
            thread = start_csv_worker(lock_path, lambda: app.execute_log_csv_transfer(**request),
                                      lambda exc: app.record_csv_worker_failure(exc, request["run_state"]))
            try:
                assert entered.wait(5), "Worker did not reach the fake transport"
                assert csv_worker_is_running(lock_path)
                try:
                    start_csv_worker(lock_path, lambda: None, lambda exc: None)
                except CsvRunBusyError:
                    pass
                else:
                    raise AssertionError("A second writer started")
                control = ScriptRequests()
                control.request_rerun(RerunData())
                pending = control.on_scriptrunner_yield()
                assert pending is not None
                try:
                    raise RerunException(pending.rerun_data)
                except RerunException:
                    pass
                assert thread.is_alive(), "UI rerun must not stop the transfer worker"
            finally:
                release.set()
                thread.join(10)
        assert not thread.is_alive()
        saved = app.load_log_csv_batch_state(checkpoint)
        assert saved["status"] == "completed", saved["error"]
        assert saved["completed_count"] == 2 and len(calls) == 2
        assert not csv_worker_is_running(lock_path)
        print("PASS: UI rerun leaves parallel transfer running; second writer blocked")

        class SimulatedProcessStop(BaseException):
            pass

        def saved_then_stopped(*values, **kwargs):
            raise SimulatedProcessStop("Stopped after remote acceptance, before local result")

        request = transfer_args(app)
        with patch.object(app, "append_summary_to_google_doc", side_effect=saved_then_stopped):
            thread = start_csv_worker(lock_path, lambda: app.execute_log_csv_transfer(**request),
                                      lambda exc: app.record_csv_worker_failure(exc, request["run_state"]))
            thread.join(10)
        crashed = app.load_log_csv_batch_state(checkpoint)
        assert crashed["status"] == "interrupted"
        assert [
            request["source_index"]
            for request in app.log_csv_batch_in_flight_requests(crashed)
        ] == [0, 1]
        assert crashed["completed_count"] == 0
        print("PASS: all unacknowledged parallel requests survive process-stop checkpoint")

        for found in (True, False):
            resumed = transfer_args(app)
            resumed["run_state"] = app.resume_log_csv_batch_state(crashed, updated_at="2026-09-06T12:01:00+09:00")
            with patch.object(app, "append_summary_to_google_doc", return_value={"ok": True, "message": "added"}) as post, patch.object(
                app, "verify_summary_in_google_doc_after_timeout",
                return_value={"ok": True, "verify_only": True, "found_existing": found},
            ) as verify:
                app.execute_log_csv_transfer(**resumed)
            assert verify.call_count == 2
            assert post.call_count == 0, "Do not repost any uncertain parallel row"
            saved = app.load_log_csv_batch_state(checkpoint)
            assert saved["status"] == "completed" and saved["in_flight"] is None
            classifications = [
                app.classify_google_docs_save_result(result)["count_key"]
                for result in saved["results"]
            ]
            expected = "saved_confirmed_after_timeout" if found else "timeout_unknown"
            assert classifications == [expected, expected]
            print(f"PASS: restart verifies every parallel request without blind repost (found={found})")

        request = transfer_args(app)
        real_save = app.save_log_csv_batch_state

        def fail_after_response(path, state):
            if state["completed_count"]:
                raise PermissionError("Synthetic durable-checkpoint failure")
            return real_save(path, state)

        with patch.object(app, "append_summary_to_google_doc", return_value={"ok": True, "message": "added"}) as post, patch.object(app, "save_log_csv_batch_state", side_effect=fail_after_response):
            try:
                app.execute_log_csv_transfer(**request)
            except PermissionError:
                pass
        assert post.call_count == 2, "Only the already-checkpointed parallel wave may be in flight"
        saved = app.load_log_csv_batch_state(checkpoint)
        assert [
            request["source_index"]
            for request in app.log_csv_batch_in_flight_requests(saved)
        ] == [0, 1]
        print("PASS: checkpoint failure blocks the next wave and retains all uncertain requests")

        request = transfer_args(app)
        with patch.object(app, "append_summary_to_google_doc", return_value={"ok": True, "message": "added"}) as post, patch.object(
            app, "save_log_csv_processing_history", side_effect=PermissionError("Synthetic history write failure"),
        ):
            try:
                app.execute_log_csv_transfer(**request)
            except PermissionError:
                pass
        assert post.call_count == 0, "History must be durable before the first write"
        print("PASS: history write failure blocks the first POST")

        request = transfer_args(app)
        with patch.object(app, "append_summary_to_google_doc", return_value={"ok": True, "message": "added"}), patch.object(
            app, "save_log_csv_to_docs_result_log", side_effect=PermissionError("Synthetic result log failure"),
        ):
            app.execute_log_csv_transfer(**request)
        saved = app.load_log_csv_batch_state(checkpoint)
        assert saved["status"] == "interrupted" and saved["completed_count"] == 2
        assert "Synthetic result log failure" in saved["error"]
        print("PASS: result log failure is visible and acknowledged rows are retained")

        request = transfer_args(app)
        request["consumed_filter_enabled"] = True
        with patch.object(app, "append_summary_to_google_doc", return_value={"ok": True, "message": "added"}):
            app.execute_log_csv_transfer(**request)
        saved = app.load_log_csv_batch_state(checkpoint)
        assert saved["status"] == "completed"
        assert all(not row.get("admin_consumed_mark_error") for row in saved["results"])
        assert (folder / "consumed.json").is_file()
        print("PASS: enabled consumed-note filtering works without Streamlit context")

        incomplete = transfer_args(app)["run_state"]
        try:
            app.complete_log_csv_batch_state(incomplete, result_log_path="", updated_at="2026-09-06T12:01:00+09:00")
        except ValueError:
            pass
        else:
            raise AssertionError("Unprocessed rows must not be marked completed")
        print("PASS: pending rows cannot be falsely marked completed")

        from streamlit.testing.v1 import AppTest

        entered.clear()
        release.clear()
        calls.clear()
        with patch.object(app.st, "session_state", original_session_state), patch.object(app, "append_summary_to_google_doc", side_effect=slow_post):
            at = AppTest.from_function(render_worker_ui_fixture, args=(str(args.app_root), str((args.overlay or args.app_root) / "scripts"))).run(timeout=10)
            assert not at.exception, [error.message for error in at.exception]
            try:
                at.button(key="log_csv_to_docs_save_button").click().run(timeout=2)
                assert entered.wait(2)
                assert not at.exception, [error.message for error in at.exception]
                assert csv_worker_is_running(lock_path), "UI returned but background work must continue"
                at.run(timeout=2)
                assert not at.exception, [error.message for error in at.exception]
                assert csv_worker_is_running(lock_path), "Second UI run must not cancel saving"
                assert at.expander[0].proto.expanded, "Running progress must be open after a UI rerun"
            finally:
                release.set()
                deadline = time.monotonic() + 10
                while csv_worker_is_running(lock_path) and time.monotonic() < deadline:
                    time.sleep(0.05)
        assert not csv_worker_is_running(lock_path)
        assert app.load_log_csv_batch_state(checkpoint)["status"] == "completed"
        assert len(calls) == 1
        print("PASS: real CSV button returns while transport waits; rerun causes no extra POST")


if __name__ == "__main__":
    main()
