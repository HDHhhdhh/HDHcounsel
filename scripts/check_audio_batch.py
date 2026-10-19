from __future__ import annotations

from contextlib import nullcontext, redirect_stderr
from io import StringIO
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def make_job(index: int):
    from counsel_modules.audio_batch import create_audio_batch_job

    return create_audio_batch_job(
        audio_path=f"C:/recordings/student_{index}.m4a",
        source_name=f"student_{index}.m4a",
        student_name=f"student_{index}",
        author_name="teacher",
        counseling_date="2026-08-14",
        processing_mode="balanced",
        summary_style="default",
        use_vad=False,
        use_prompt_hint=False,
    )


def check_thirty_jobs_are_allowed_but_thirty_one_are_rejected() -> None:
    from counsel_modules.audio_batch import AudioBatchLimitError, create_audio_batch_state

    state = create_audio_batch_state([make_job(index) for index in range(30)], "2026-08-14T10:00:00")
    assert state["total"] == 30

    try:
        create_audio_batch_state([make_job(index) for index in range(31)], "2026-08-14T10:00:00")
    except AudioBatchLimitError as exc:
        assert exc.selected_count == 31
    else:
        raise AssertionError("31 recording jobs must be rejected")


def check_one_uploader_routes_by_selected_file_count() -> None:
    from counsel_modules.audio_batch import classify_audio_upload_selection

    assert classify_audio_upload_selection(0) == "empty"
    assert classify_audio_upload_selection(1) == "single"
    assert classify_audio_upload_selection(2) == "batch"
    assert classify_audio_upload_selection(30) == "batch"
    assert classify_audio_upload_selection(31) == "over_limit"


def check_multiple_uploads_clear_stale_single_selection() -> None:
    with redirect_stderr(StringIO()):
        import app

    session_state = {
        "audio_upload_key": "audio_upload",
        "audio_upload": [SimpleNamespace(name="first.wav"), SimpleNamespace(name="second.wav")],
        "current_audio_path": "C:/uploads/first.wav",
        "selected_audio_path": "C:/uploads/first.wav",
        "uploaded_audio_key": "first.wav|100",
        "uploaded_audio_saved_path": "C:/uploads/first.wav",
        "recent_recording_path": "C:/recordings/first.wav",
    }

    with patch.object(app.st, "session_state", session_state):
        app.handle_audio_upload_change()

    assert session_state["current_audio_path"] is None
    assert session_state["selected_audio_path"] is None
    assert session_state["uploaded_audio_key"] == ""
    assert session_state["uploaded_audio_saved_path"] == ""
    assert "recent_recording_path" not in session_state


def check_removing_last_upload_clears_stale_single_selection() -> None:
    with redirect_stderr(StringIO()):
        import app

    session_state = {
        "audio_upload_key": "audio_upload",
        "audio_upload": [],
        "current_audio_path": "C:/uploads/first.wav",
        "selected_audio_path": "C:/uploads/first.wav",
        "uploaded_audio_key": "first.wav|100",
        "uploaded_audio_saved_path": "C:/uploads/first.wav",
        "recent_recording_path": "C:/uploads/first.wav",
    }

    with patch.object(app.st, "session_state", session_state):
        app.handle_audio_upload_change()

    assert session_state["current_audio_path"] is None
    assert session_state["selected_audio_path"] is None
    assert session_state["uploaded_audio_key"] == ""
    assert session_state["uploaded_audio_saved_path"] == ""
    assert "recent_recording_path" not in session_state


def check_stalled_batch_recovery_clears_runtime_flags() -> None:
    with redirect_stderr(StringIO()):
        import app

    session_state = {
        "is_processing": True,
        "pending_main_run": False,
        "current_job_snapshot": {"batch_job_id": "stalled-job"},
    }

    with patch.object(app.st, "session_state", session_state):
        app.clear_stalled_audio_batch_runtime_flags()

    assert session_state["is_processing"] is False
    assert session_state["pending_main_run"] is False
    assert session_state["current_job_snapshot"] is None


def check_resume_dispatch_refreshes_before_processing() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, set_audio_batch_status

    state = set_audio_batch_status(
        create_audio_batch_state([make_job(0), make_job(1)], "2026-08-14T10:00:00"),
        "paused",
        "2026-08-14T10:01:00",
    )
    session_state = {"audio_batch_state": state, "pending_main_run": False}

    class ResumeButtonSlot:
        def __init__(self) -> None:
            self.calls = []
            self.info_calls = []

        def button(self, label, **kwargs):
            self.calls.append((label, kwargs))
            return len(self.calls) == 1

        def info(self, message):
            self.info_calls.append(message)

    resume_button_slot = ResumeButtonSlot()

    def persist_state(updated_state):
        session_state["audio_batch_state"] = updated_state

    def schedule_first_job():
        session_state["pending_main_run"] = True
        return True

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app.st, "progress"),
        patch.object(app.st, "caption"),
        patch.object(app.st, "info"),
        patch.object(app.st, "warning"),
        patch.object(app.st, "columns", return_value=[nullcontext(), nullcontext()]),
        patch.object(app.st, "empty", return_value=resume_button_slot),
        patch.object(app.st, "dataframe"),
        patch.object(
            app.st,
            "button",
            side_effect=lambda label, **kwargs: label == "남은 작업 이어서 처리",
        ),
        patch.object(app.st, "rerun") as rerun,
        patch.object(app, "persist_audio_batch_session_state", side_effect=persist_state),
        patch.object(app, "start_next_audio_batch_job", side_effect=schedule_first_job) as start_next,
        patch.object(app, "audio_batch_now_iso", return_value="2026-08-14T10:02:00"),
    ):
        app.render_audio_batch_state_ui(ui_locked=False)

    start_next.assert_called_once_with()
    assert session_state["pending_main_run"] is True
    rerun.assert_called_once_with()
    assert [label for label, _ in resume_button_slot.calls] == ["남은 작업 이어서 처리"]
    assert resume_button_slot.info_calls == ["처리를 시작했습니다."]


def check_duplicate_dispatch_is_ignored_while_job_is_processing() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state

    state = create_audio_batch_state([make_job(0), make_job(1)], "2026-08-14T10:00:00")
    session_state = {"audio_batch_state": state, "pending_main_run": False}

    def persist_state(updated_state):
        session_state["audio_batch_state"] = updated_state

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app, "persist_audio_batch_session_state", side_effect=persist_state),
        patch.object(app, "audio_batch_now_iso", return_value="2026-08-14T10:02:00"),
    ):
        first_scheduled = app.start_next_audio_batch_job()
        duplicate_scheduled = app.start_next_audio_batch_job()

    assert first_scheduled is True
    assert duplicate_scheduled is False
    assert [job["status"] for job in session_state["audio_batch_state"]["jobs"]] == [
        "processing",
        "pending",
    ]
    assert [job["attempts"] for job in session_state["audio_batch_state"]["jobs"]] == [1, 0]


def check_batch_dispatch_does_not_modify_instantiated_input_widgets() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, set_audio_batch_status

    class WidgetLockedSessionState(dict):
        def __setitem__(self, key, value):
            if key in {"student_name", "counseling_date", "counseling_date_input"}:
                raise RuntimeError(f"widget state is locked: {key}")
            super().__setitem__(key, value)

    state = set_audio_batch_status(
        create_audio_batch_state([make_job(0)], "2026-08-14T10:00:00"),
        "running",
        "2026-08-14T10:01:00",
    )
    session_state = WidgetLockedSessionState(audio_batch_state=state, pending_main_run=False)

    def persist_state(updated_state):
        session_state["audio_batch_state"] = updated_state

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app, "persist_audio_batch_session_state", side_effect=persist_state),
        patch.object(app, "audio_batch_now_iso", return_value="2026-08-14T10:02:00"),
    ):
        scheduled = app.start_next_audio_batch_job()

    assert scheduled is True
    assert session_state["pending_main_run"] is True
    assert session_state["current_job_snapshot"]["student_name"] == "student_0"


def check_batch_table_includes_all_pending_jobs() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, set_audio_batch_status

    state = set_audio_batch_status(
        create_audio_batch_state([make_job(0), make_job(1), make_job(2)], "2026-08-14T10:00:00"),
        "paused",
        "2026-08-14T10:01:00",
    )
    session_state = {"audio_batch_state": state, "pending_main_run": False}
    resume_button_slot = SimpleNamespace(button=lambda *args, **kwargs: False)

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app.st, "progress"),
        patch.object(app.st, "caption"),
        patch.object(app.st, "info"),
        patch.object(app.st, "warning"),
        patch.object(app.st, "columns", return_value=[nullcontext(), nullcontext()]),
        patch.object(app.st, "empty", return_value=resume_button_slot),
        patch.object(app.st, "button", return_value=False),
        patch.object(app.st, "dataframe") as dataframe,
        patch.object(app.st, "expander", return_value=nullcontext()),
        patch.object(app, "audio_batch_now_iso", return_value="2026-08-14T10:02:00"),
    ):
        app.render_audio_batch_state_ui(ui_locked=False)

    dataframe.assert_called_once()
    rows = dataframe.call_args.args[0]
    assert len(rows) == 3
    assert [row["순서"] for row in rows] == [1, 2, 3]
    assert all(row["상태"] == "대기" for row in rows)
    assert all(row["내용"] == "처리 대기 중" for row in rows)


def check_batch_status_layout_is_stable_while_processing() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    state = create_audio_batch_state([make_job(0), make_job(1), make_job(2)], "2026-08-14T10:00:00")
    first_job = state["jobs"][0]
    state = update_audio_batch_job(
        state,
        first_job["job_id"],
        status="processing",
        detail="1/3 processing",
        transcript_path="",
        summary="",
        updated_at="2026-08-14T10:01:00",
    )
    session_state = {"audio_batch_state": state, "pending_main_run": True}
    resume_button_slot = SimpleNamespace(button=lambda *args, **kwargs: False)

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app.st, "progress"),
        patch.object(app.st, "caption") as caption,
        patch.object(app.st, "info") as info,
        patch.object(app.st, "warning"),
        patch.object(app.st, "columns", return_value=[nullcontext(), nullcontext()]),
        patch.object(app.st, "empty", return_value=resume_button_slot),
        patch.object(app.st, "button", return_value=False),
        patch.object(app.st, "dataframe"),
        patch.object(app.st, "expander", return_value=nullcontext()) as expander,
        patch.object(app, "render_audio_batch_summary_review") as review,
        patch.object(app, "audio_batch_now_iso", return_value="2026-08-14T10:02:00"),
    ):
        app.render_audio_batch_state_ui(ui_locked=True)

    caption_texts = [str(call.args[0]) for call in caption.call_args_list if call.args]
    assert any("1/3 처리 중" in text for text in caption_texts)
    info.assert_not_called()
    expander.assert_not_called()
    review.assert_called_once()
    assert review.call_args.args[:2] == (state, True)


def check_batch_panel_opens_only_during_processing() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, set_audio_batch_status

    completed_state = set_audio_batch_status(
        create_audio_batch_state([make_job(0)], "2026-08-14T10:00:00"),
        "completed",
        "2026-08-14T10:01:00",
    )

    assert app.audio_batch_panel_expanded(None) is False
    assert app.audio_batch_panel_expanded(completed_state) is False, (
        "An idle retained batch must not automatically expand"
    )
    paused_state = set_audio_batch_status(completed_state, "paused", "2026-08-14T10:02:00")
    assert app.audio_batch_panel_expanded(paused_state) is False
    running_state = set_audio_batch_status(completed_state, "running", "2026-08-14T10:03:00")
    assert app.audio_batch_panel_expanded(running_state) is True
    finished_job = dict(running_state["jobs"][0], status="completed", summary="Saved summary")
    idle_running_state = {**running_state, "jobs": [finished_job]}
    assert app.audio_batch_panel_expanded(idle_running_state) is False


def check_batch_completion_feedback_uses_toast_without_banner() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    state = create_audio_batch_state([make_job(0)], "2026-08-14T10:00:00")
    job = state["jobs"][0]
    state = update_audio_batch_job(
        state,
        job["job_id"],
        status="completed",
        detail="done",
        transcript_path="C:/transcripts/student_0.txt",
        summary="summary",
        updated_at="2026-08-14T10:01:00",
    )
    session_state = {
        "audio_batch_state": state,
        "post_run_success": "",
        "pending_main_run": False,
    }

    def persist_state(updated_state):
        session_state["audio_batch_state"] = updated_state

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app, "persist_audio_batch_session_state", side_effect=persist_state),
        patch.object(app, "audio_batch_now_iso", return_value="2026-08-14T10:02:00"),
    ):
        scheduled = app.start_next_audio_batch_job()

    assert scheduled is False
    assert "저장 미완료" in session_state["post_run_toast"]
    assert not session_state["post_run_success"]


def check_completed_job_defers_next_dispatch_until_following_run() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    state = create_audio_batch_state([make_job(0), make_job(1)], "2026-08-14T10:00:00")
    first_job = state["jobs"][0]
    state = update_audio_batch_job(
        state,
        first_job["job_id"],
        status="processing",
        detail="1/2 processing",
        transcript_path="",
        summary="",
        updated_at="2026-08-14T10:01:00",
    )
    session_state = {
        "audio_batch_state": state,
        "current_job_snapshot": {"batch_job_id": first_job["job_id"]},
        "is_processing": True,
        "pending_main_run": False,
    }

    def persist_state(updated_state):
        session_state["audio_batch_state"] = updated_state

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app, "persist_audio_batch_session_state", side_effect=persist_state),
        patch.object(app, "start_next_audio_batch_job") as start_next,
        patch.object(app, "audio_batch_now_iso", return_value="2026-08-14T10:02:00"),
        patch.object(app, "save_audio_batch_job_to_admin"),
    ):
        app.finish_active_audio_batch_job(
            status="completed",
            detail="done",
            transcript_path="C:/transcripts/student_0.txt",
            summary="summary",
            pause_batch=False,
        )

    start_next.assert_not_called()
    assert [job["status"] for job in session_state["audio_batch_state"]["jobs"]] == [
        "completed",
        "pending",
    ]

    with (
        patch.object(app.st, "session_state", session_state),
        patch.object(app, "start_next_audio_batch_job", return_value=True) as start_next,
    ):
        assert app.continue_running_audio_batch_if_needed() is True
    start_next.assert_called_once_with()


def check_next_job_keeps_selection_order() -> None:
    from counsel_modules.audio_batch import (
        create_audio_batch_state,
        next_pending_audio_batch_job,
        update_audio_batch_job,
    )

    jobs = [make_job(index) for index in range(3)]
    state = create_audio_batch_state(jobs, "2026-08-14T10:00:00")
    first = next_pending_audio_batch_job(state)
    assert first is not None
    assert first[1]["source_name"] == "student_0.m4a"

    state = update_audio_batch_job(
        state,
        first[1]["job_id"],
        status="completed",
        detail="done",
        transcript_path="C:/transcripts/student_0.txt",
        summary="summary",
        updated_at="2026-08-14T10:01:00",
    )
    second = next_pending_audio_batch_job(state)
    assert second is not None
    assert second[1]["source_name"] == "student_1.m4a"


def check_interrupted_job_recovers_paused_with_saved_transcript() -> None:
    from counsel_modules.audio_batch import (
        create_audio_batch_state,
        recover_interrupted_audio_batch_state,
        update_audio_batch_job,
    )

    job = make_job(0)
    state = create_audio_batch_state([job], "2026-08-14T10:00:00")
    state = update_audio_batch_job(
        state,
        job["job_id"],
        status="processing",
        detail="summary",
        transcript_path="C:/transcripts/student_0.txt",
        summary="",
        updated_at="2026-08-14T10:01:00",
    )

    recovered = recover_interrupted_audio_batch_state(state, "2026-08-14T10:02:00")

    assert recovered["status"] == "paused"
    assert recovered["jobs"][0]["status"] == "pending"
    assert recovered["jobs"][0]["transcript_path"] == "C:/transcripts/student_0.txt"


def check_running_batch_with_only_pending_jobs_recovers_as_stalled() -> None:
    from counsel_modules.audio_batch import (
        create_audio_batch_state,
        recover_stalled_audio_batch_state,
        update_audio_batch_job,
    )

    state = create_audio_batch_state(
        [make_job(0), make_job(1), make_job(2)],
        "2026-08-14T10:00:00",
    )

    recovered = recover_stalled_audio_batch_state(
        state,
        "2026-08-14T10:02:00",
        runtime_scheduled=False,
    )

    assert recovered["status"] == "paused"
    assert [job["status"] for job in recovered["jobs"]] == ["pending", "pending", "pending"]

    still_running = recover_stalled_audio_batch_state(
        state,
        "2026-08-14T10:02:00",
        runtime_scheduled=True,
    )
    assert still_running is state

    processing_state = update_audio_batch_job(
        state,
        state["jobs"][0]["job_id"],
        status="processing",
        detail="1/3 processing",
        transcript_path="",
        summary="",
        updated_at="2026-08-14T10:01:00",
    )
    recovered_processing = recover_stalled_audio_batch_state(
        processing_state,
        "2026-08-14T10:02:00",
        runtime_scheduled=False,
    )
    assert recovered_processing["status"] == "paused"
    assert recovered_processing["jobs"][0]["status"] == "pending"


def check_retry_resets_only_problem_jobs() -> None:
    from counsel_modules.audio_batch import (
        create_audio_batch_state,
        prepare_audio_batch_retry,
        update_audio_batch_job,
    )

    jobs = [make_job(index) for index in range(3)]
    state = create_audio_batch_state(jobs, "2026-08-14T10:00:00")
    statuses = ("completed", "failed", "needs_review")
    for job, status in zip(jobs, statuses, strict=True):
        state = update_audio_batch_job(
            state,
            job["job_id"],
            status=status,
            detail=status,
            transcript_path="" if status == "failed" else f"C:/transcripts/{job['job_id']}.txt",
            summary="summary" if status == "completed" else "",
            updated_at="2026-08-14T10:01:00",
        )

    retried = prepare_audio_batch_retry(state, "2026-08-14T10:02:00")

    assert [job["status"] for job in retried["jobs"]] == ["completed", "pending", "pending"]
    assert retried["status"] == "running"


def check_batch_state_round_trip() -> None:
    from counsel_modules.audio_batch import (
        create_audio_batch_state,
        load_audio_batch_state,
        save_audio_batch_state,
    )

    state = create_audio_batch_state([make_job(0), make_job(1)], "2026-08-14T10:00:00")
    with tempfile.TemporaryDirectory() as temp_dir:
        state_path = Path(temp_dir) / "audio_batch_queue.json"
        save_audio_batch_state(state_path, state)
        loaded = load_audio_batch_state(state_path)

    assert loaded == state


def check_unsaved_completed_batch_is_preserved_for_new_session() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import (
        create_audio_batch_state,
        save_audio_batch_state,
        update_audio_batch_job,
    )

    state = create_audio_batch_state([make_job(0)], "2026-08-14T10:00:00")
    completed_state = update_audio_batch_job(
        state,
        state["jobs"][0]["job_id"],
        status="completed",
        detail="summary completed",
        transcript_path="",
        summary="summary",
        updated_at="2026-08-14T10:01:00",
    )
    assert completed_state["status"] == "completed"

    with tempfile.TemporaryDirectory() as temp_dir:
        state_path = Path(temp_dir) / "audio_batch_queue.json"
        save_audio_batch_state(state_path, completed_state)
        session_state = {}
        with (
            patch.object(app, "AUDIO_BATCH_STATE_PATH", state_path),
            patch.object(app.st, "session_state", session_state),
        ):
            app.initialize_audio_batch_session_state()

        state_file_exists = state_path.exists()

    assert session_state["audio_batch_initialized"] is True
    assert session_state["audio_batch_state"] is not None, "Generated summaries were deleted before ADMIN storage"
    assert state_file_exists is True


def check_unfinished_batch_is_preserved_for_new_session() -> None:
    with redirect_stderr(StringIO()):
        import app

    from counsel_modules.audio_batch import create_audio_batch_state, save_audio_batch_state

    state = create_audio_batch_state([make_job(0)], "2026-08-14T10:00:00")
    with tempfile.TemporaryDirectory() as temp_dir:
        state_path = Path(temp_dir) / "audio_batch_queue.json"
        save_audio_batch_state(state_path, state)
        session_state = {}
        with (
            patch.object(app, "AUDIO_BATCH_STATE_PATH", state_path),
            patch.object(app.st, "session_state", session_state),
        ):
            app.initialize_audio_batch_session_state()

    assert session_state["audio_batch_initialized"] is True
    assert session_state["audio_batch_state"]["status"] == "paused"
    assert session_state["audio_batch_state"]["total"] == 1


def check_recovered_queue_marks_missing_source_for_review() -> None:
    from counsel_modules.audio_batch import create_audio_batch_state, reconcile_audio_batch_paths

    with tempfile.TemporaryDirectory() as temp_dir:
        missing_audio = Path(temp_dir) / "missing.m4a"
        job = make_job(0)
        job["audio_path"] = str(missing_audio)
        state = create_audio_batch_state([job], "2026-08-14T10:00:00")

        reconciled = reconcile_audio_batch_paths(state, "2026-08-14T10:02:00")

    assert reconciled["jobs"][0]["status"] == "needs_review"
    assert reconciled["status"] == "paused"


def check_recovered_queue_keeps_job_when_saved_transcript_exists() -> None:
    from counsel_modules.audio_batch import (
        create_audio_batch_state,
        reconcile_audio_batch_paths,
        update_audio_batch_job,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        transcript_path = temp_path / "saved.txt"
        transcript_path.write_text("saved transcript", encoding="utf-8")
        job = make_job(0)
        job["audio_path"] = str(temp_path / "missing.m4a")
        state = create_audio_batch_state([job], "2026-08-14T10:00:00")
        state = update_audio_batch_job(
            state,
            job["job_id"],
            status="pending",
            detail="",
            transcript_path=str(transcript_path),
            summary="",
            updated_at="2026-08-14T10:01:00",
        )

        reconciled = reconcile_audio_batch_paths(state, "2026-08-14T10:02:00")

    assert reconciled["jobs"][0]["status"] == "pending"
    assert reconciled["status"] == "running"


def check_failed_transcription_removes_converted_wav() -> None:
    with redirect_stderr(StringIO()):
        import app

    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)
        audio_path = temp_path / "recording.m4a"
        converted_wav_path = temp_path / "recording_whisper.wav"
        audio_path.write_bytes(b"audio")
        converted_wav_path.write_bytes(b"wav")

        with (
            patch.object(app.st, "session_state", {}),
            patch.object(app, "audio_needs_whisper_wav_conversion", return_value=True),
            patch.object(
                app,
                "convert_audio_to_whisper_wav",
                return_value=(converted_wav_path, ["ffmpeg"], "", ""),
            ),
            patch.object(app, "consume_whisper_segments", side_effect=RuntimeError("model failure")),
            patch.object(app, "write_extract_error_log", return_value=None),
        ):
            try:
                app.transcribe_audio_with_wav_preprocess(
                    audio_path,
                    object(),
                    {},
                    False,
                )
            except RuntimeError:
                pass
            else:
                raise AssertionError("transcription failure must propagate")

        assert not converted_wav_path.exists()


def check_completed_batch_summary_recovers_student_without_clearing_summary() -> None:
    from datetime import date
    import app
    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    # Given a completed summary whose matching student was not handed to the form.
    job = make_job(0)
    state = update_audio_batch_job(
        create_audio_batch_state([job], "2026-08-14T10:00:00"),
        job["job_id"], status="completed", detail="done",
        transcript_path="C:/fixture/saved.txt", summary="Test summary",
        updated_at="2026-08-14T10:01:00",
    )
    session = {
        "student_name": "", "author_name": "screen teacher",
        "counseling_date": date(2026, 8, 14), "audio_batch_state": state,
        "latest_summary": "Test summary", "current_transcript_path": "C:/fixture/saved.txt",
    }
    # When the form prepares its next render, before student widgets are created.
    with patch.object(app.st, "session_state", session):
        app.apply_pending_student_name_from_file()
    # Then both the target student and the existing summary are retained.
    assert session["student_name"] == "student_0", "Completed summary lost its batch student"
    assert session["latest_summary"] == "Test summary"
    assert session["current_transcript_path"] == "C:/fixture/saved.txt"
    assert session["form_transcript_key"] == f"2026-08-14|student_0|{app.sanitize_filename_part('screen teacher')}"
    assert session["author_name"] == "screen teacher"


def check_batch_summary_recovery_rejects_unrelated_or_ambiguous_identity() -> None:
    from copy import deepcopy
    from datetime import date
    import app
    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    job = make_job(0)
    state = update_audio_batch_job(
        create_audio_batch_state([job], "2026-08-14T10:00:00"),
        job["job_id"], status="completed", detail="done",
        transcript_path="C:/fixture/saved.txt", summary="Test summary",
        updated_at="2026-08-14T10:01:00",
    )
    for scenario in ("summary", "path", "date", "selected", "ambiguous", "new_upload"):
        # Given a context that does not uniquely establish the displayed student's identity.
        session = {
            "student_name": "", "author_name": "teacher",
            "counseling_date": date(2026, 8, 14), "audio_batch_state": deepcopy(state),
            "latest_summary": "Test summary", "current_transcript_path": "C:/fixture/saved.txt",
            "form_transcript_key": "old-context",
        }
        if scenario == "summary":
            session["latest_summary"] = "Different summary"
        elif scenario == "path":
            session["current_transcript_path"] = "C:/fixture/other.txt"
        elif scenario == "date":
            session["counseling_date"] = date(2026, 8, 15)
        elif scenario == "selected":
            session["student_name"] = "OTHER"
        elif scenario == "ambiguous":
            other = dict(session["audio_batch_state"]["jobs"][0])
            other["student_name"] = "OTHER"
            other["job_id"] = "another-job"
            session["audio_batch_state"]["jobs"].append(other)
        else:
            session["pending_student_name_from_file"] = "NEW"
        expected_name = "NEW" if scenario == "new_upload" else str(session["student_name"])
        # When the restoration callback runs.
        with patch.object(app.st, "session_state", session):
            app.apply_pending_student_name_from_file()
        # Then it does not guess an owner or overwrite the previous form context.
        assert session["student_name"] == expected_name, scenario
        assert session["form_transcript_key"] == "old-context", scenario


def check_completed_job_queues_student_handoff_without_mutating_live_widgets() -> None:
    from datetime import date
    import app
    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    class WidgetLockedState(dict):
        widgets_locked = True

        def __setitem__(self, key, value):
            if self.widgets_locked and key == "student_name":
                raise RuntimeError("student widget is already instantiated")
            super().__setitem__(key, value)

    # Given an old selection while a different batch student's summary finishes.
    job = make_job(0)
    state = update_audio_batch_job(
        create_audio_batch_state([job], "2026-08-14T10:00:00"),
        job["job_id"], status="processing", detail="processing",
        transcript_path="", summary="", updated_at="2026-08-14T10:01:00",
    )
    session = WidgetLockedState(
        student_name="OLD", author_name="teacher", counseling_date=date(2026, 8, 14),
        audio_batch_state=state, current_job_snapshot={"batch_job_id": job["job_id"]},
        latest_summary="Test summary", current_transcript_path="C:/fixture/saved.txt",
    )
    with (
        patch.object(app.st, "session_state", session),
        patch.object(app, "persist_audio_batch_session_state", side_effect=lambda value: session.update(audio_batch_state=value)),
        patch.object(app, "save_audio_batch_job_to_admin"),
    ):
        # When completion is recorded while widgets still belong to the prior render.
        app.finish_active_audio_batch_job(
            status="completed", detail="done", transcript_path="C:/fixture/saved.txt",
            summary="Test summary", pause_batch=False,
        )
        # Then identity is queued; widget mutation happens only before the next render.
        assert session["student_name"] == "OLD"
        assert session.get("pending_student_name_from_file") == "student_0", "Batch completion discarded its student"
        session.widgets_locked = False
        app.apply_pending_student_name_from_file()
    assert session["student_name"] == "student_0"
    assert session["form_transcript_key"] == "2026-08-14|student_0|teacher"


def check_one_batch_apply_saves_each_student_and_skips_confirmed_saves() -> None:
    with redirect_stderr(StringIO()):
        import app
    from counsel_modules.audio_batch import create_audio_batch_state

    jobs = [make_job(index) for index in range(4)]
    session = {"audio_batch_state": create_audio_batch_state(jobs, "2026-08-14T10:00:00"), "student_name": "WRONG"}
    with (
        patch.object(app.st, "session_state", session),
        patch.object(app, "persist_audio_batch_session_state", side_effect=lambda value: session.update(audio_batch_state=value)),
        patch.object(app, "find_admin_sid_candidates_for_student", side_effect=lambda name, url: [{"student_name": name, "admin_sid": f"SID-{name}"}]),
        patch.object(app, "sync_admin_notes", return_value=app.AdminNotesSyncResult(True, "saved", None, {"ok": True})) as sync,
    ):
        for job in jobs:
            session["current_job_snapshot"] = {"batch_job_id": job["job_id"]}
            app.finish_active_audio_batch_job(
                status="completed", detail="generated", transcript_path="fixture.txt",
                summary="[오늘 확인할 것]\n\n*상담 참고사항*\n- 단어 학습을 확인하기로 함.", pause_batch=False,
            )
        assert sync.call_count == 0, "Generation saved before the user pressed batch apply"
        app.save_completed_audio_batch_summaries()
        assert sync.call_count == 4, "One batch apply did not store all four students"
        assert [call.args[0].student_name for call in sync.call_args_list] == [job["student_name"] for job in jobs]
        assert all(call.args[0].counseling_date.isoformat() == "2026-08-14" for call in sync.call_args_list)
        assert all(job.get("admin_saved") for job in session["audio_batch_state"]["jobs"])
        app.save_completed_audio_batch_summaries()
        assert sync.call_count == 4, "Confirmed summaries were saved twice"


def check_batch_save_failure_keeps_summary_and_retries_only_unsaved_students() -> None:
    with redirect_stderr(StringIO()):
        import app
    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    state = create_audio_batch_state([make_job(index) for index in range(4)], "2026-08-14T10:00:00")
    summary = "[오늘 확인할 것]\n\n*상담 참고사항*\n- 단어 학습을 확인하기로 함."
    for job in state["jobs"]:
        state = update_audio_batch_job(state, job["job_id"], status="completed", detail="generated", transcript_path="fixture.txt", summary=summary, updated_at="2026-08-14T10:01:00")
    session = {"audio_batch_state": state}

    def sync_request(request):
        if request.student_name == "student_1":
            raise app.WorkflowStepError("admin 특이사항 저장", "test connection failure")
        return app.AdminNotesSyncResult(False, summary, None, None)

    with (
        patch.object(app.st, "session_state", session),
        patch.object(app, "persist_audio_batch_session_state", side_effect=lambda value: session.update(audio_batch_state=value)),
        patch.object(app, "find_admin_sid_candidates_for_student", side_effect=lambda name, url: [{"student_name": name, "admin_sid": f"SID-{name}"}]),
        patch.object(app, "sync_admin_notes", side_effect=sync_request) as sync,
    ):
        app.save_completed_audio_batch_summaries()
        assert app.audio_batch_saved_student_count(session["audio_batch_state"]) == 3
        failed = session["audio_batch_state"]["jobs"][1]
        assert failed["status"] == "needs_review" and failed["summary"] == summary
        sync.side_effect = None
        sync.return_value = app.AdminNotesSyncResult(True, summary, None, {"ok": True})
        app.save_completed_audio_batch_summaries()
        assert sync.call_count == 5, "Retry rewrote students whose saves were confirmed"
        assert app.audio_batch_saved_student_count(session["audio_batch_state"]) == 4
        assert all(job["attempts"] == 0 for job in session["audio_batch_state"]["jobs"]), "Save retry regenerated recordings"


def check_batch_save_blocks_ambiguous_targets_and_counts_unique_students() -> None:
    with redirect_stderr(StringIO()):
        import app
    from counsel_modules.audio_batch import create_audio_batch_state, update_audio_batch_job

    job = make_job(0)
    state = update_audio_batch_job(create_audio_batch_state([job], "now"), job["job_id"], status="completed", detail="generated", transcript_path="fixture.txt", summary="*상담 참고사항*\n- 단어 학습 확인.", updated_at="now")
    session = {"audio_batch_state": state, "selected_admin_sid_for_student": "OTHER-STUDENT"}
    with (
        patch.object(app.st, "session_state", session),
        patch.object(app, "persist_audio_batch_session_state", side_effect=lambda value: session.update(audio_batch_state=value)),
        patch.object(app, "find_admin_sid_candidates_for_student", return_value=[{"student_name": "student_0", "admin_sid": "ONE"}, {"student_name": "student_0", "admin_sid": "TWO"}]),
        patch.object(app, "get_local_admin_sid_override", return_value={}),
        patch.object(app, "auto_select_admin_sid_candidate", return_value=(None, "ambiguous")),
        patch.object(app, "sync_admin_notes") as sync,
    ):
        app.save_completed_audio_batch_summaries()
        sync.assert_not_called()
        assert app.audio_batch_saved_student_count(session["audio_batch_state"]) == 0
        assert session["audio_batch_state"]["jobs"][0]["status"] == "needs_review"
    saved = dict(state["jobs"][0], admin_saved=True, admin_sid="ONE")
    state["jobs"] = [saved, dict(saved, job_id="another-recording")]
    assert app.audio_batch_saved_student_count(state) == 1


def check_batch_checkpoint_survives_temporary_windows_file_lock() -> None:
    import os
    from counsel_modules.audio_batch import create_audio_batch_state, load_audio_batch_state, save_audio_batch_state

    state = create_audio_batch_state([make_job(0)], "now")
    replace = os.replace
    attempts = 0

    def temporary_lock(source, destination):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise PermissionError("temporary Windows file lock")
        return replace(source, destination)

    with tempfile.TemporaryDirectory() as temp_dir:
        path = Path(temp_dir) / "queue.json"
        save_audio_batch_state(path, state)
        with patch("os.replace", side_effect=temporary_lock), patch("time.sleep"):
            save_audio_batch_state(path, state)
        assert load_audio_batch_state(path) == state
        assert attempts == 2


def main() -> None:
    check_batch_checkpoint_survives_temporary_windows_file_lock()
    check_one_batch_apply_saves_each_student_and_skips_confirmed_saves()
    check_batch_save_failure_keeps_summary_and_retries_only_unsaved_students()
    check_batch_save_blocks_ambiguous_targets_and_counts_unique_students()
    check_thirty_jobs_are_allowed_but_thirty_one_are_rejected()
    check_one_uploader_routes_by_selected_file_count()
    check_multiple_uploads_clear_stale_single_selection()
    check_removing_last_upload_clears_stale_single_selection()
    check_stalled_batch_recovery_clears_runtime_flags()
    check_resume_dispatch_refreshes_before_processing()
    check_duplicate_dispatch_is_ignored_while_job_is_processing()
    check_batch_dispatch_does_not_modify_instantiated_input_widgets()
    check_batch_table_includes_all_pending_jobs()
    check_batch_status_layout_is_stable_while_processing()
    check_batch_panel_opens_only_during_processing()
    check_batch_completion_feedback_uses_toast_without_banner()
    check_completed_job_defers_next_dispatch_until_following_run()
    check_next_job_keeps_selection_order()
    check_interrupted_job_recovers_paused_with_saved_transcript()
    check_running_batch_with_only_pending_jobs_recovers_as_stalled()
    check_retry_resets_only_problem_jobs()
    check_batch_state_round_trip()
    check_unsaved_completed_batch_is_preserved_for_new_session()
    check_unfinished_batch_is_preserved_for_new_session()
    check_recovered_queue_marks_missing_source_for_review()
    check_recovered_queue_keeps_job_when_saved_transcript_exists()
    check_failed_transcription_removes_converted_wav()
    check_completed_batch_summary_recovers_student_without_clearing_summary()
    check_batch_summary_recovery_rejects_unrelated_or_ambiguous_identity()
    check_completed_job_queues_student_handoff_without_mutating_live_widgets()
    print("audio batch checks passed")


if __name__ == "__main__":
    main()
