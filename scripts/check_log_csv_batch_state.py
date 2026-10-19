from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from counsel_modules.log_csv_batch_state import (
    acknowledge_log_csv_batch_state,
    complete_log_csv_batch_state,
    create_log_csv_batch_state,
    interrupt_log_csv_batch_state,
    load_log_csv_batch_state,
    log_csv_batch_in_flight_requests,
    log_csv_batch_state_is_recently_running,
    log_csv_batch_state_matches,
    record_log_csv_batch_result,
    remaining_log_csv_batch_indices,
    resume_log_csv_batch_state,
    save_log_csv_batch_state,
    set_log_csv_batch_in_flight_requests,
    set_log_csv_batch_phase,
    should_release_log_csv_session_lock,
)


def main() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    render_start = app_text.index("def render_log_csv_to_docs_preview_ui")
    render_end = app_text.index("\ndef ", render_start + 4)
    render_body = app_text[render_start:render_end]
    release_call = "release_stale_log_csv_session_lock()"
    watcher_call = "render_log_csv_auto_import_watcher()"
    assert release_call in render_body
    assert render_body.index(release_call) < render_body.index(watcher_call)
    action_start = render_body.index(
        "if save_button_clicked or retry_failed_pending or auto_export_requested or resume_pending:"
    )
    saving_flag_set = render_body.index(
        'st.session_state["log_csv_to_docs_is_saving"] = True',
        action_start,
    )
    for clear_call in (
        "resume_button_slot.empty()",
        "save_button_slot.empty()",
    ):
        clear_position = render_body.index(clear_call, action_start)
        assert action_start < clear_position < saving_flag_set

    state = create_log_csv_batch_state(
        upload_signature="upload-abc",
        source_csv_name="sample.csv",
        source_csv_size=123,
        source_csv_path="C:/Users/test/Downloads/sample.csv",
        source_mtime_ns=456,
        selected_indices=[2, 5, 8],
        started_at="2026-08-29T18:00:00+09:00",
        run_id="log_csv_to_docs_20260829_180000",
    )
    assert state["status"] == "running"
    assert state["total"] == 3
    assert remaining_log_csv_batch_indices(state, [2, 5, 8, 13]) == [2, 5, 8]

    state = set_log_csv_batch_in_flight_requests(
        state,
        requests=[
            {"source_index": index, "request": {"doc_id": f"doc-{index}"}}
            for index in (2, 5, 8)
        ],
        updated_at="2026-08-29T18:00:00+09:00",
    )
    assert [
        request["source_index"] for request in log_csv_batch_in_flight_requests(state)
    ] == [2, 5, 8]

    state = set_log_csv_batch_phase(
        state,
        current_position=1,
        current_name="학생 A",
        phase="Google Docs 응답 대기",
        updated_at="2026-08-29T18:00:01+09:00",
    )
    state = record_log_csv_batch_result(
        state,
        source_index=2,
        result={"source_index": 2, "result_status": "성공"},
        failed=False,
        updated_at="2026-08-29T18:00:02+09:00",
    )
    assert state["completed_indices"] == [2]
    assert state["completed_count"] == 1
    assert [
        request["source_index"] for request in log_csv_batch_in_flight_requests(state)
    ] == [5, 8]
    assert remaining_log_csv_batch_indices(state, [2, 5, 8, 13]) == [5, 8]

    interrupted = interrupt_log_csv_batch_state(
        state,
        error="unexpected response",
        updated_at="2026-08-29T18:00:03+09:00",
    )
    assert interrupted["status"] == "interrupted"
    assert interrupted["completed_count"] == 1
    assert interrupted["error"] == "unexpected response"
    assert (
        log_csv_batch_state_is_recently_running(
            state,
            now="2026-08-29T18:01:00+09:00",
        )
        is True
    )
    assert (
        log_csv_batch_state_is_recently_running(
            state,
            now="2026-08-29T18:10:00+09:00",
        )
        is False
    )
    assert (
        should_release_log_csv_session_lock(
            state,
            session_is_saving=True,
            now="2026-08-29T18:01:00+09:00",
        )
        is False
    )
    assert (
        should_release_log_csv_session_lock(
            state,
            session_is_saving=True,
            now="2026-08-29T18:10:00+09:00",
        )
        is True
    )
    assert (
        should_release_log_csv_session_lock(
            None,
            session_is_saving=True,
            now="2026-08-29T18:10:00+09:00",
        )
        is True
    )
    assert (
        should_release_log_csv_session_lock(
            state,
            session_is_saving=False,
            now="2026-08-29T18:10:00+09:00",
        )
        is False
    )
    resumed = resume_log_csv_batch_state(
        interrupted,
        updated_at="2026-08-29T18:00:03+09:00",
    )
    assert resumed["status"] == "running"
    assert resumed["error"] == ""

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "log_csv_to_docs_run.json"
        save_log_csv_batch_state(path, interrupted)
        loaded = load_log_csv_batch_state(path)
        assert loaded == interrupted
        assert log_csv_batch_state_matches(loaded, "upload-abc") is True
        assert log_csv_batch_state_matches(loaded, "different") is False

        completed = record_log_csv_batch_result(
            loaded,
            source_index=5,
            result={"source_index": 5, "result_status": "중복으로 추가하지 않음"},
            failed=False,
            updated_at="2026-08-29T18:00:04+09:00",
        )
        completed = record_log_csv_batch_result(
            completed,
            source_index=8,
            result={"source_index": 8, "result_status": "실패"},
            failed=True,
            updated_at="2026-08-29T18:00:05+09:00",
        )
        completed = complete_log_csv_batch_state(
            completed,
            result_log_path="C:/tmp/result.csv",
            updated_at="2026-08-29T18:00:06+09:00",
        )
        assert completed["status"] == "completed"
        assert completed["acknowledged_at"] == ""
        assert completed["completed_count"] == 3
        assert completed["failed_indices"] == [8]
        assert remaining_log_csv_batch_indices(completed, [2, 5, 8]) == []

        acknowledged = acknowledge_log_csv_batch_state(
            completed,
            acknowledged_at="2026-08-29T18:00:07+09:00",
        )
        assert acknowledged["acknowledged_at"] == "2026-08-29T18:00:07+09:00"
        save_log_csv_batch_state(path, acknowledged)
        assert load_log_csv_batch_state(path) == acknowledged

        try:
            acknowledge_log_csv_batch_state(
                interrupted,
                acknowledged_at="2026-08-29T18:00:07+09:00",
            )
        except ValueError:
            pass
        else:
            raise AssertionError("Only completed CSV runs can be acknowledged")

        path.write_text("{broken", encoding="utf-8")
        assert load_log_csv_batch_state(path) is None

        path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        assert load_log_csv_batch_state(path) is None

    print("log CSV batch state checks passed")


if __name__ == "__main__":
    main()
