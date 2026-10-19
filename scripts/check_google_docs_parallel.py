from __future__ import annotations

import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT_DIR))

from scripts.check_csv_worker import load_app, transfer_args


def transfer_args_for_rows(app, rows):
    request = transfer_args(app)
    student_names = list(dict.fromkeys(str(row["name"]) for row in rows))
    maps = [
        {"student_name": name, "doc_id": f"test-doc-{position}"}
        for position, name in enumerate(student_names)
    ]
    matches = app.match_log_rows_to_docs(rows, maps)
    indices = list(range(len(rows)))
    history = app.empty_log_csv_processing_history()
    entry = app.prepare_log_csv_history_entry(
        history,
        app.LogCsvHistoryStart(
            csv_hash="parallel-fixture",
            row_hashes=tuple(app.fingerprint_log_csv_rows(rows)),
            selected_indices=tuple(indices),
            review_indices=(),
            new_row_count=len(rows),
            started_at="2026-09-20T22:00:00+09:00",
            source_date="2026-09-20",
        ),
    )
    state = app.create_log_csv_batch_state(
        upload_signature="parallel-fixture",
        source_csv_name="parallel.csv",
        source_csv_size=1,
        source_csv_path="",
        source_mtime_ns=0,
        selected_indices=indices,
        started_at="2026-09-20T22:00:00+09:00",
        run_id="parallel-test-run",
    )
    request.update(
        history_entry=entry,
        matched_rows=matches,
        process_selected_indices=indices,
        processing_history=history,
        run_scope_indices=indices,
        run_state=state,
        save_batch_size=10,
    )
    return request


def in_flight_request(app, item, source_index):
    row = item["source_row"]
    docs_match = item["docs_matches"][0]
    return {
        "source_index": source_index,
        "request": {
            "student_name": str(row["name"]),
            "counseling_date": str(row["date"]),
            "summary": app.prepare_log_csv_preview_for_google_docs(
                item,
                consumed_filter_enabled=False,
            ),
            "doc_id": str(docs_match["doc_id"]),
            "dedupe_key": app.build_log_csv_dedupe_key(row),
            "subject": str(row.get("curriculum") or ""),
            "book": app.google_docs_book_from_log_item(item),
        },
    }


def check_completed_student_counts(app) -> None:
    day = "2026-09-20"
    results = [
        {"date": day, "name": "TEST_A", "doc_id": "doc-a", "result_status": "성공"},
        {"date": day, "name": "TEST_A", "doc_id": "doc-a", "updated_existing": "True"},
        {"date": day, "name": "TEST_ALIAS", "doc_id": "doc-a", "duplicate_skipped": "True"},
        {"date": day, "name": "TEST_A", "doc_url": "https://docs.google.com/document/d/doc-a/edit", "result_status": "성공"},
        {"date": day, "name": "TEST_B", "doc_id": "doc-b", "result_status": "failed"},
        {"date": day, "name": "TEST_B", "doc_id": "doc-b", "result_status": "성공"},
        {"date": day, "name": "TEST_C", "doc_id": "doc-c", "result_status": "saved_confirmed_after_timeout"},
        {"date": day, "name": "TEST_D", "doc_id": "doc-d", "result_status": "실패"},
        {"date": day, "name": "TEST_E", "doc_id": "doc-e", "result_status": "timeout_unknown"},
        {"date": day, "name": "TEST_F", "doc_id": "doc-f", "duplicate_write_suspected": "True"},
        {"date": day, "name": "TEST_G", "doc_id": "doc-g", "result_status": "제외"},
        {"date": day, "name": "TEST_H", "doc_id": "doc-h", "needs_review": "True"},
        {"date": day, "name": "TEST_I", "doc_id": "doc-i"},
        {"date": "invalid", "name": "TEST_J", "result_status": "성공"},
        {"date": day, "result_status": "성공"},
        {"date": "2026-09-21", "name": "TEST_A", "doc_id": "doc-a", "result_status": "성공"},
    ]
    keys = app.log_csv_confirmed_student_keys(results)
    assert sum(source_date == day for source_date, _key in keys) == 3
    assert sum(source_date == "2026-09-21" for source_date, _key in keys) == 1
    assert len(app.log_csv_confirmed_student_keys([
        {"date": day, "name": " TEST K ", "result_status": "성공"},
        {"date": day, "name": "testk", "result_status": "성공"},
    ])) == 1
    with tempfile.TemporaryDirectory(prefix="docs-count-test-") as directory:
        folder = Path(directory)
        with (
            patch.object(app, "GOOGLE_DOCS_APPEND_LOG_DIR", folder),
            patch.object(app, "load_current_log_csv_batch_state", return_value={"results": results[5:]}),
            patch.object(app, "load_current_log_csv_processing_history", return_value=app.empty_log_csv_processing_history()),
            patch.object(app, "default_log_csv_downloads_dir", return_value=folder),
        ):
            app.save_log_csv_to_docs_result_log(results[:5], "test.csv", 1)
            assert app.current_log_csv_saved_student_keys() == keys
            app.save_log_csv_to_docs_result_log(results, "test-again.csv", 1)
            assert app.current_log_csv_saved_student_keys() == keys
    print("PASS: repeat saves count each confirmed student once; failures and unknown saves excluded")


def check_nonblocking_transfers(app, *, slow_verification: bool) -> None:
    rows = [
        {"date": "2026-09-20", "name": f"TEST_{index:02}", "sid": f"TEST_{index:02}",
         "notes": f"Test note {index}", "subject": "math"}
        for index in range(60)
    ]
    blocked_started = threading.Event()
    allow_finish = threading.Event()
    sixth_started = threading.Event()
    other_finished = threading.Event()
    with tempfile.TemporaryDirectory(prefix="docs-queue-test-") as directory:
        folder = Path(directory)
        checkpoint = folder / "run.json"
        save_checkpoint = app.save_log_csv_batch_state

        def persist_checkpoint(path, state):
            save_checkpoint(path, state)
            completed = set(state.get("completed_indices") or [])
            if completed == set(range(1, 60)):
                other_finished.set()

        def post(*values, **_kwargs):
            index = int(str(values[1]).rsplit("_", 1)[1])
            saved = app.load_log_csv_batch_state(checkpoint)
            pending = app.log_csv_batch_in_flight_requests(saved)
            assert index in {request["source_index"] for request in pending}, "POST preceded durable checkpoint"
            assert len(pending) <= 5, "checkpoint exceeded five concurrent requests"
            if index == 0:
                if slow_verification:
                    raise app.GoogleDocsPostTimeoutError("Docs fixture", "uncertain save")
                blocked_started.set()
                assert allow_finish.wait(20), "slow request was not released"
            if index == 5:
                sixth_started.set()
            return {"ok": True, "message": "added"}

        def verify(*_values, **_kwargs):
            blocked_started.set()
            assert allow_finish.wait(20), "slow verification was not released"
            return {"ok": True, "verify_only": True, "found_existing": True}

        with (
            patch.object(app, "LOG_CSV_DOCS_STATE_PATH", checkpoint),
            patch.object(app, "save_log_csv_batch_state", new=persist_checkpoint),
            patch.object(app, "LOG_CSV_PROCESSING_HISTORY_PATH", folder / "history.json"),
            patch.object(app, "GOOGLE_DOCS_TIMEOUT_VERIFY_PAUSE_SECONDS", 0),
            patch.object(app, "save_log_csv_to_docs_result_log", return_value=folder / "result.csv"),
            patch.object(app, "append_summary_to_google_doc", new=post),
            patch.object(app, "verify_summary_in_google_doc_after_timeout", new=verify),
            ThreadPoolExecutor(max_workers=1) as executor,
        ):
            future = executor.submit(app.execute_log_csv_transfer, **transfer_args_for_rows(app, rows))
            try:
                assert blocked_started.wait(5), "blocked request never started"
                assert sixth_started.wait(2), "one slow document blocked the next student"
                assert other_finished.wait(10), "the other 59 students did not finish around the blocked document"
            finally:
                allow_finish.set()
            future.result(timeout=15)
        saved = app.load_log_csv_batch_state(checkpoint)
        assert saved["status"] == "completed"
        assert saved["completed_count"] == 60
        assert {int(result["source_index"]) for result in saved["results"]} == set(range(60))
        assert len(app.log_csv_confirmed_student_keys(saved["results"])) == 60
        assert not app.log_csv_batch_in_flight_requests(saved)
    kind = "timeout verification" if slow_verification else "slow POST"
    print(f"PASS: sixty students continue around one blocked {kind}")


def main() -> None:
    app = load_app(ROOT_DIR, None)
    check_completed_student_counts(app)
    rows = [
        {
            "date": "2026-09-20",
            "name": name,
            "sid": name,
            "notes": f"Test note {position}",
            "subject": "math",
        }
        for position, name in enumerate(("TEST_A", "TEST_B", "TEST_C", "TEST_A", "TEST_D", "TEST_E"))
    ]

    with tempfile.TemporaryDirectory(prefix="docs-parallel-test-") as directory:
        folder = Path(directory)
        checkpoint = folder / "run.json"
        history_path = folder / "history.json"
        active_names: set[str] = set()
        active_count = 0
        max_active_count = 0
        state_lock = threading.Lock()
        five_started = threading.Event()
        allow_finish = threading.Event()

        def concurrent_post(*values, **_kwargs):
            nonlocal active_count, max_active_count
            name = str(values[1])
            with state_lock:
                assert name not in active_names, f"same document overlapped: {name}"
                active_names.add(name)
                active_count += 1
                max_active_count = max(max_active_count, active_count)
                if active_count == 5:
                    five_started.set()
            assert allow_finish.wait(10), "parallel requests were not released"
            time.sleep(0.03)
            with state_lock:
                active_names.remove(name)
                active_count -= 1
            return {"ok": True, "message": "added"}

        with (
            patch.object(app, "LOG_CSV_DOCS_STATE_PATH", checkpoint),
            patch.object(app, "LOG_CSV_PROCESSING_HISTORY_PATH", history_path),
            patch.object(app, "GOOGLE_DOCS_TIMEOUT_VERIFY_PAUSE_SECONDS", 0),
            patch.object(app, "save_log_csv_to_docs_result_log", return_value=folder / "result.csv"),
        ):
            request = transfer_args_for_rows(app, rows)
            with (
                patch.object(app, "append_summary_to_google_doc", new=concurrent_post),
                ThreadPoolExecutor(max_workers=1) as transfer_executor,
            ):
                transfer_future = transfer_executor.submit(
                    app.execute_log_csv_transfer,
                    **request,
                )
                try:
                    assert five_started.wait(5), "five requests did not start concurrently"
                    active_state = app.load_log_csv_batch_state(checkpoint)
                    assert len(app.log_csv_batch_in_flight_requests(active_state)) == 5
                finally:
                    allow_finish.set()
                transfer_future.result(timeout=15)

            saved = app.load_log_csv_batch_state(checkpoint)
            assert saved["status"] == "completed"
            assert saved["completed_count"] == len(rows)
            assert max_active_count == 5
            assert not app.log_csv_batch_in_flight_requests(saved)

            resumed = transfer_args_for_rows(app, [rows[index] for index in (0, 1, 2, 4, 5)])
            resumed["run_state"] = app.set_log_csv_batch_in_flight_requests(
                resumed["run_state"],
                requests=[
                    in_flight_request(app, item, source_index)
                    for source_index, item in enumerate(resumed["matched_rows"])
                ],
                updated_at="2026-09-20T22:00:01+09:00",
            )
            with (
                patch.object(app, "append_summary_to_google_doc", return_value={"ok": True}) as post,
                patch.object(
                    app,
                    "verify_summary_in_google_doc_after_timeout",
                    return_value={"ok": True, "verify_only": True, "found_existing": True},
                ) as verify,
            ):
                app.execute_log_csv_transfer(**resumed)

            recovered = app.load_log_csv_batch_state(checkpoint)
            assert verify.call_count == 5
            assert post.call_count == 0
            assert recovered["status"] == "completed"
            assert not app.log_csv_batch_in_flight_requests(recovered)

    print("PASS: Docs transfer uses five workers with per-document ordering and safe recovery")
    check_nonblocking_transfers(app, slow_verification=False)
    check_nonblocking_transfers(app, slow_verification=True)


if __name__ == "__main__":
    main()
