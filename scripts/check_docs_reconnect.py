from __future__ import annotations

import argparse
import sys
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch


def fixture_state(app, mode: str):
    state = app.create_log_csv_batch_state(
        upload_signature="reconnect-fixture", source_csv_name="test.csv",
        source_csv_size=1, source_csv_path="", source_mtime_ns=0,
        selected_indices=[0, 1], started_at="2026-10-05T12:00:00+09:00",
        run_id="reconnect-fixture-run",
    )
    for index in range(1 if mode == "interrupted" else 2):
        failed = mode == "mixed" and index == 1
        state = app.record_log_csv_batch_result(
            state, source_index=index,
            result={
                "source_index": index, "date": "2026-10-05", "name": "TEST",
                "doc_id": "test-doc", "result_status": "실패" if failed else "성공",
                "결과": "실패" if failed else "성공", "메시지": "error" if failed else "added",
            }, failed=failed, updated_at="2026-10-05T12:00:30+09:00",
        )
    if mode == "interrupted":
        return app.interrupt_log_csv_batch_state(
            state, error="fixture interruption", updated_at="2026-10-05T12:01:00+09:00",
        )
    return app.complete_log_csv_batch_state(
        state, result_log_path="", updated_at="2026-10-05T12:01:00+09:00",
    )


def render_reconnect_fixture(mode: str) -> None:
    from contextlib import ExitStack
    from unittest.mock import patch

    import app
    import streamlit as st
    from check_docs_reconnect import fixture_state

    st.session_state.setdefault("fixture_state", fixture_state(app, mode))

    def persist(state):
        if st.session_state.get("fixture_ack_failure"):
            return False
        st.session_state["fixture_state"] = state
        return True

    original_uploader = st.file_uploader

    def empty_upload(*args, **kwargs):
        original_uploader(*args, **kwargs)
        return None

    mocks = {
        "release_stale_log_csv_session_lock": None,
        "restore_log_csv_auto_import_from_batch_state": None,
        "render_log_csv_auto_import_watcher": None,
        "active_auto_import_log_csv": None,
        "load_current_log_csv_batch_state": lambda: st.session_state["fixture_state"],
        "persist_current_log_csv_batch_state": persist,
        "load_current_log_csv_processing_history": app.empty_log_csv_processing_history(),
        "refresh_log_csv_processing_history_summary": None,
        "csv_worker_is_running": False,
    }
    with ExitStack() as stack:
        for name, value in mocks.items():
            stack.enter_context(patch.object(app, name, **(
                {"side_effect": value} if callable(value) else {"return_value": value}
            )))
        stack.enter_context(patch.object(st, "file_uploader", side_effect=empty_upload))
        stack.enter_context(patch("requests.sessions.Session.request", side_effect=AssertionError("No network in reconnect check")))
        stack.enter_context(patch.object(app, "sync_admin_notes", side_effect=AssertionError("No ADMIN writes")))
        app.render_log_csv_to_docs_preview_ui(st.empty())


def main() -> None:
    from streamlit.testing.v1 import AppTest

    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--overlay", type=Path)
    args = parser.parse_args()
    sys.path.insert(0, str(args.app_root / "scripts"))
    from check_csv_worker import load_app

    app = load_app(args.app_root, args.overlay)
    sys.modules["app"] = app
    failures: list[str] = []

    def check(name, test):
        try:
            test()
        except AssertionError as exc:
            failures.append(name)
            print(f"FAIL: {name}: {exc}")
        else:
            print(f"PASS: {name}")

    def completed_reconnect():
        at = AppTest.from_function(render_reconnect_fixture, args=("completed",)).run(timeout=30)
        assert not at.exception, [exc.message for exc in at.exception]
        assert any(item.value == "저장 결과" for item in at.subheader), "Completed results disappeared without upload"
        assert any("저장 완료 1명" in item.value for item in at.success), "Duplicate student was counted twice"
        assert not any("오늘 전체 처리 완료" in item.value for item in at.success), "Selected batch must not claim full-day completion"
        assert at.expander[0].proto.expanded, "Reconnect results must open automatically"
        at.run(timeout=30)
        assert at.button(key="log_csv_to_docs_completion_confirmation_reconnect-fixture-run")
        at.session_state["fixture_ack_failure"] = True
        at.button(key="log_csv_to_docs_completion_confirmation_reconnect-fixture-run").click().run(timeout=30)
        assert at.error, "Failed acknowledgement must remain visible"
        assert not at.session_state["fixture_state"]["acknowledged_at"]
        at.session_state["fixture_ack_failure"] = False
        at.button(key="log_csv_to_docs_completion_confirmation_reconnect-fixture-run").click().run(timeout=30)
        assert not at.exception, [exc.message for exc in at.exception]
        assert at.session_state["fixture_state"]["acknowledged_at"]
        assert not at.subheader, "Acknowledged results must close"
        assert at.button(key="log_csv_to_docs_save_button").disabled

    def interrupted_reconnect():
        at = AppTest.from_function(render_reconnect_fixture, args=("interrupted",)).run(timeout=30)
        assert not at.exception, [exc.message for exc in at.exception]
        assert any("남음 1건" in item.value for item in at.warning), "Interrupted checkpoint disappeared without upload"
        assert not at.success, "Interruption must not look completed"
        assert not any("completion_confirmation" in (button.key or "") for button in at.button)

    def mixed_reconnect():
        at = AppTest.from_function(render_reconnect_fixture, args=("mixed",)).run(timeout=30)
        assert not at.exception, [exc.message for exc in at.exception]
        assert any("결과 확인 필요" in item.value for item in at.warning), "Failure must not look like saved completion"
        assert not at.success

    def watcher_waits_for_ack():
        state = fixture_state(app, "completed")
        with patch.object(app.st, "session_state", {}), patch.object(app, "csv_worker_is_running", return_value=False), patch.object(app, "load_current_log_csv_batch_state", return_value=state), patch.object(app, "find_latest_completed_log_csv", return_value=None) as scan:
            app.render_log_csv_auto_import_watcher.__wrapped__()
            assert scan.call_count == 0, "Automatic import can replace unacknowledged completion"
            state["acknowledged_at"] = "2026-10-05T12:02:00+09:00"
            app.render_log_csv_auto_import_watcher.__wrapped__()
            assert scan.call_count == 1, "Acknowledgement must unblock automatic import"

    def fast_finish_reruns():
        state = fixture_state(app, "completed")
        session = {}
        render_progress = app.render_log_csv_persisted_progress.__wrapped__

        def monitor(signature):
            assert session.get("log_csv_observed_worker_run") == state["run_id"], "Parent never registered observed worker"
            render_progress(signature)

        with ExitStack() as stack:
            for name, value in {
                "release_stale_log_csv_session_lock": None,
                "restore_log_csv_auto_import_from_batch_state": None,
                "render_log_csv_auto_import_watcher": None,
                "active_auto_import_log_csv": None,
                "load_current_log_csv_batch_state": state,
                "load_current_log_csv_processing_history": app.empty_log_csv_processing_history(),
                "refresh_log_csv_processing_history_summary": None,
            }.items():
                stack.enter_context(patch.object(app, name, return_value=value))
            stack.enter_context(patch.object(app.st, "session_state", session))
            stack.enter_context(patch.object(app.st, "file_uploader", return_value=None))
            stack.enter_context(patch.object(app, "csv_worker_is_running", side_effect=[True, False]))
            stack.enter_context(patch.object(app, "render_log_csv_persisted_progress", side_effect=monitor))
            rerun = stack.enter_context(patch.object(app.st, "rerun"))
            app.render_log_csv_to_docs_preview_ui.__wrapped__(app.st.empty())
            assert rerun.call_count == 1, "Fast completion did not leave running-only view"

    check("completed reconnect retains results and persisted acknowledgement", completed_reconnect)
    check("interrupted reconnect retains remaining count", interrupted_reconnect)
    check("mixed outcome reconnect is not saved completion", mixed_reconnect)
    check("automatic import waits for acknowledgement", watcher_waits_for_ack)
    check("worker finishing before first progress poll refreshes view", fast_finish_reruns)
    if failures:
        raise SystemExit(f"{len(failures)} reconnect checks failed")
    print("All 5 Docs reconnect checks passed")


if __name__ == "__main__":
    main()
