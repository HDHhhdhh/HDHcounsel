from __future__ import annotations

import json
import sys
import tempfile
from datetime import date
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from counsel_modules import log_csv_processing_history as history_module
from counsel_modules.log_csv_processing_history import (
    LogCsvHistoryStart,
    LogCsvHistoryUpdate,
    LogCsvProcessingHistoryError,
    count_new_log_csv_rows,
    csv_bytes_sha256,
    empty_log_csv_processing_history,
    finalize_log_csv_history_entry,
    find_log_csv_history_entry,
    fingerprint_log_csv_rows,
    load_log_csv_processing_history,
    log_csv_history_can_seed_from_completed_batch,
    log_csv_history_is_completed,
    log_csv_history_source_indices,
    previous_log_csv_operation_dates,
    prepare_log_csv_history_entry,
    recent_log_csv_history_day_summaries,
    record_log_csv_history_outcome,
    save_log_csv_processing_history,
    unresolved_log_csv_history_indices,
    upsert_log_csv_history_entry,
)


def make_hashes(count: int) -> list[str]:
    return [csv_bytes_sha256(f"row-{index}".encode("utf-8")) for index in range(count)]


def main() -> None:
    assert log_csv_history_source_indices({"row_index": 5}) == [4]
    assert log_csv_history_source_indices(
        {"row_index": 1, "merged_homework_items": ["1", "3", "3"]}
    ) == [0, 2]
    sensitive_rows = [
        {"date": "2026-09-02", "name": "민감한 학생", "notes": "민감한 원문"},
        {"date": "2026-09-02", "name": "학생 B", "notes": "기록 B"},
        {"date": "2026-09-02", "name": "학생 C", "notes": "기록 C"},
        {"date": "2026-09-02", "name": "학생 D", "notes": ""},
    ]
    row_hashes = fingerprint_log_csv_rows(sensitive_rows)
    different_date_hashes = fingerprint_log_csv_rows(
        [{**sensitive_rows[0], "date": "2026-09-03"}]
    )
    assert different_date_hashes[0] != row_hashes[0]
    csv_hash = csv_bytes_sha256(b"sample-csv")
    history = empty_log_csv_processing_history()
    entry = prepare_log_csv_history_entry(
        history,
        LogCsvHistoryStart(
            csv_hash=csv_hash,
            row_hashes=tuple(row_hashes),
            selected_indices=(0, 1, 2),
            review_indices=(),
            started_at="2026-09-02T21:40:00+09:00",
            new_row_count=0,
            source_date="2026-09-02",
        ),
    )
    assert entry["status"] == "incomplete"
    assert entry["resolved_count"] == 1
    assert entry["source_date"] == "2026-09-02"

    for index, outcome in ((0, "success"), (1, "duplicate"), (2, "success")):
        entry = record_log_csv_history_outcome(
            entry,
            LogCsvHistoryUpdate(
                source_index=index,
                outcome=outcome,
                updated_at="2026-09-02T21:42:00+09:00",
            ),
        )
    entry = finalize_log_csv_history_entry(entry, "2026-09-02T21:42:00+09:00")
    assert entry["status"] == "completed"
    assert entry["resolved_count"] == 4
    assert entry["success_count"] == 2
    assert entry["duplicate_count"] == 1
    assert entry["excluded_count"] == 1
    assert entry["completed_at"] == "2026-09-02T21:42:00+09:00"
    assert log_csv_history_is_completed(entry)
    assert log_csv_history_can_seed_from_completed_batch(
        prepare_log_csv_history_entry(
            empty_log_csv_processing_history(),
            LogCsvHistoryStart(
                csv_hash="legacy",
                row_hashes=tuple(row_hashes),
                selected_indices=(0, 1),
                review_indices=(),
                started_at="2026-09-02T21:40:00+09:00",
                new_row_count=0,
            ),
        ),
        batch_status="completed",
        selected_indices=[0, 1],
        result_indices={0, 1},
        matched_count=4,
    )

    history = upsert_log_csv_history_entry(history, entry)
    assert find_log_csv_history_entry(history, csv_hash) == entry
    assert unresolved_log_csv_history_indices(entry) == []

    appended_hashes = row_hashes + make_hashes(3)
    assert count_new_log_csv_rows(history, "new-csv-hash", appended_hashes) == 3
    assert count_new_log_csv_rows(
        history,
        "repeated-row-csv-hash",
        row_hashes + [row_hashes[0]],
    ) == 1

    incomplete_hashes = make_hashes(32)
    incomplete = prepare_log_csv_history_entry(
        history,
        LogCsvHistoryStart(
            csv_hash="incomplete",
            row_hashes=tuple(incomplete_hashes),
            selected_indices=tuple(range(32)),
            review_indices=(),
            started_at="2026-09-02T22:00:00+09:00",
            new_row_count=3,
            source_date="2026-09-04",
        ),
    )
    for index in range(18):
        incomplete = record_log_csv_history_outcome(
            incomplete,
            LogCsvHistoryUpdate(index, "success", "2026-09-02T22:01:00+09:00"),
        )
    assert incomplete["status"] == "incomplete"
    assert not log_csv_history_is_completed(incomplete)
    assert incomplete["resolved_count"] == 18
    assert len(unresolved_log_csv_history_indices(incomplete)) == 14
    assert hasattr(history_module, "log_csv_history_processing_is_finished")
    processing_is_finished = history_module.log_csv_history_processing_is_finished
    assert processing_is_finished(incomplete) is False

    chunk_hashes = make_hashes(60)
    chunk_entry = prepare_log_csv_history_entry(
        history,
        LogCsvHistoryStart(
            csv_hash="chunked-day",
            row_hashes=tuple(chunk_hashes),
            selected_indices=tuple(range(60)),
            review_indices=(),
            started_at="2026-09-05T12:00:00+09:00",
            new_row_count=60,
            source_date="2026-09-05",
        ),
    )
    chunk_history = upsert_log_csv_history_entry(history, chunk_entry)
    chunk_entry = prepare_log_csv_history_entry(
        chunk_history,
        LogCsvHistoryStart(
            csv_hash="chunked-day",
            row_hashes=tuple(chunk_hashes),
            selected_indices=tuple(range(20)),
            review_indices=(),
            started_at="2026-09-05T12:01:00+09:00",
            new_row_count=60,
            source_date="2026-09-05",
        ),
    )
    assert chunk_entry["outcomes"] == ["pending"] * 60
    for index in range(20):
        chunk_entry = record_log_csv_history_outcome(
            chunk_entry,
            LogCsvHistoryUpdate(index, "success", "2026-09-05T12:02:00+09:00"),
        )
    assert chunk_entry["status"] == "incomplete"
    assert chunk_entry["resolved_count"] == 20
    assert unresolved_log_csv_history_indices(chunk_entry) == list(range(20, 60))

    assert previous_log_csv_operation_dates(date(2026, 9, 5)) == [
        date(2026, 9, 5),
        date(2026, 9, 4),
        date(2026, 9, 2),
    ]
    assert previous_log_csv_operation_dates(date(2026, 9, 8)) == [
        date(2026, 9, 7),
        date(2026, 9, 6),
        date(2026, 9, 5),
    ]
    older_completed = {
        **entry,
        "csv_hash": "older-completed",
        "source_date": "2026-08-31",
        "started_at": "2026-08-31T20:50:00+09:00",
        "updated_at": "2026-08-31T20:51:00+09:00",
        "completed_at": "2026-08-31T20:51:00+09:00",
    }
    day_summaries = recent_log_csv_history_day_summaries(
        {"version": 1, "entries": [older_completed, entry, incomplete]},
        reference_date=date(2026, 9, 5),
    )
    assert [summary["source_date"] for summary in day_summaries] == [
        "2026-09-05",
        "2026-09-04",
        "2026-09-02",
    ]
    assert [summary["status"] for summary in day_summaries] == [
        "incomplete",
        "incomplete",
        "completed",
    ]
    assert day_summaries[0]["has_history"] is False
    assert day_summaries[1]["resolved_count"] == 18
    assert day_summaries[1]["total_count"] == 32

    needs_review = prepare_log_csv_history_entry(
        history,
        LogCsvHistoryStart(
            csv_hash="needs-review",
            row_hashes=tuple(incomplete_hashes),
            selected_indices=tuple(range(32)),
            review_indices=(),
            started_at="2026-09-02T22:10:00+09:00",
            new_row_count=0,
        ),
    )
    for index in range(32):
        outcome = "failure" if index >= 30 else "success"
        needs_review = record_log_csv_history_outcome(
            needs_review,
            LogCsvHistoryUpdate(index, outcome, "2026-09-02T22:12:00+09:00"),
        )
    needs_review = finalize_log_csv_history_entry(needs_review, "2026-09-02T22:12:00+09:00")
    assert needs_review["status"] == "needs_review"
    assert needs_review["resolved_count"] == 32
    assert needs_review["failed_count"] == 2
    assert needs_review["completed_at"] == ""
    assert processing_is_finished(needs_review) is True
    assert not log_csv_history_is_completed(needs_review)
    review_day = recent_log_csv_history_day_summaries(
        {"version": 1, "entries": [needs_review]},
        reference_date=date(2026, 9, 2),
        count=1,
    )
    assert review_day[0]["status"] == "incomplete"

    retry = prepare_log_csv_history_entry(
        upsert_log_csv_history_entry(history, needs_review),
        LogCsvHistoryStart(
            csv_hash="needs-review",
            row_hashes=tuple(incomplete_hashes),
            selected_indices=(30, 31),
            review_indices=(),
            started_at="2026-09-02T22:20:00+09:00",
            new_row_count=0,
        ),
    )
    assert retry["outcomes"][:30] == ["success"] * 30
    assert retry["outcomes"][30:] == ["pending", "pending"]

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "history.json"
        save_log_csv_processing_history(path, history)
        serialized = path.read_text(encoding="utf-8")
        assert "민감한 학생" not in serialized
        assert "민감한 원문" not in serialized
        loaded = load_log_csv_processing_history(path)
        assert loaded == history

        path.write_text("{broken", encoding="utf-8")
        try:
            load_log_csv_processing_history(path)
        except LogCsvProcessingHistoryError:
            pass
        else:
            raise AssertionError("broken history must fail closed")
        assert path.read_text(encoding="utf-8") == "{broken"

        path.write_text(json.dumps({"version": 1, "entries": "wrong"}), encoding="utf-8")
        try:
            load_log_csv_processing_history(path)
        except LogCsvProcessingHistoryError:
            pass
        else:
            raise AssertionError("invalid history schema must fail closed")

    app_source = (ROOT_DIR / "app.py").read_text(encoding="utf-8-sig")
    assert "def create_audio_log_overview(" in app_source
    assert "audio_upload_placeholder.file_uploader(" in app_source
    assert 'audio_action_placeholder.button("정리본 생성·복사"' in app_source
    assert "with right_col:\n        status_placeholder = st.empty()" in app_source
    for marker in (
        "LogCsvProcessingHistoryError",
        "history_processing_blocked",
        "log_csv_history_can_seed_from_completed_batch",
        "render_log_csv_processing_history_summary",
        "render_log_csv_to_docs_preview_ui(",
        "pending_admin_sync",
    ):
        assert marker in app_source, marker
    summary_start = app_source.index("def render_log_csv_processing_history_summary")
    summary_end = app_source.index("def refresh_log_csv_processing_history_summary", summary_start)
    summary_source = app_source[summary_start:summary_end]
    assert 'class="log-history-strip"' in summary_source
    assert "unsafe_allow_html=True" in summary_source
    assert "st.container(border=True)" not in summary_source
    assert "recent_log_csv_history_day_summaries(" in summary_source
    assert 'status_label = "확인 필요"' not in summary_source
    assert 'f"성공 ' not in summary_source
    date_marker = 'class="log-history-date"'
    status_marker = 'class="log-history-status"'
    time_marker = 'class="log-history-time"'
    for marker in (date_marker, status_marker, time_marker):
        assert marker in summary_source, marker
    assert (
        summary_source.index(date_marker)
        < summary_source.index(status_marker)
        < summary_source.index(time_marker)
    )
    assert ".log-history-date,\n              .log-history-status" in summary_source
    assert "font-size:0.9rem;" in summary_source
    assert "font-weight:650;" in summary_source
    assert 'f"최근 Docs에 추가한 기록 ' not in app_source
    assert 'f"새 기록 ' not in app_source
    assert "resolved_history_source_indices" in app_source
    for removed_marker in (
        "다운로드 폴더에서 자동으로 불러옴",
        "완료된 동일 CSV는 다시 전송하지 않고 이전 처리 결과를 표시합니다.",
        "log_csv_to_docs_select_all_",
        "log_csv_to_docs_select_failed_",
        "log_csv_to_docs_clear_all_",
        "render_log_csv_processing_history_badge",
    ):
        assert removed_marker not in app_source, removed_marker

    print("log CSV processing history checks passed")


if __name__ == "__main__":
    main()
