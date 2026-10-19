from __future__ import annotations

import argparse
from pathlib import Path


def render_fixture(app_root: str, scenario: str = "success") -> None:
    import importlib.util
    import sys
    from datetime import date
    from pathlib import Path

    import streamlit as st

    sys.path.insert(0, app_root)
    spec = importlib.util.spec_from_file_location("admin_save_ui_fixture_app", Path(app_root) / "app.py")
    app = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = app
    spec.loader.exec_module(app)

    # Patch only this isolated app module; fragment reruns retain these fakes.
    app.load_admin_api_base_url = lambda: "https://example.invalid"
    app.find_admin_sid_candidates_for_student = lambda *_: [{"admin_sid": "TEST001"}]

    def fake_sync(request):
        st.session_state["test_sync_calls"] = st.session_state.get("test_sync_calls", 0) + 1
        if scenario == "failure":
            raise app.WorkflowStepError("ADMIN", "Test save failure")
        return app.AdminNotesSyncResult(
            updated=scenario != "duplicate",
            notes=request.export_text,
            backup_path=None,
            response={"ok": True} if scenario != "duplicate" else None,
        )

    app.sync_admin_notes = fake_sync
    summary = "*상담 참고사항*\n- 테스트용 상담 내용"
    student_name = "" if scenario == "missing_student" else "TEST"
    if scenario == "batch_recovered":
        job = app.create_audio_batch_job(
            audio_path="C:/fixture/test.wav", source_name="test.wav", student_name="TEST",
            author_name="teacher", counseling_date="2026-09-05", processing_mode="balanced",
            summary_style="default", use_vad=False, use_prompt_hint=False,
        )
        state = app.update_audio_batch_job(
            app.create_audio_batch_state([job], "2026-09-05T12:00:00"), job["job_id"],
            status="completed", detail="done", transcript_path="C:/fixture/saved.txt",
            summary=summary, updated_at="2026-09-05T12:01:00",
        )
        st.session_state.setdefault("student_name", "")
        st.session_state["author_name"] = "teacher"
        st.session_state["counseling_date"] = date(2026, 9, 5)
        st.session_state["audio_batch_state"] = state
        st.session_state["latest_summary"] = summary
        st.session_state["current_transcript_path"] = "C:/fixture/saved.txt"
        app.apply_pending_student_name_from_file()
        student_name = st.text_input("학생명", key="student_name")
    st.session_state["test_main_runs"] = st.session_state.get("test_main_runs", 0) + 1
    st.title("ADMIN save scroll check")
    st.caption(f"Main renders: {st.session_state['test_main_runs']}")
    st.html('<div style="height:650px"></div>')
    request = app.render_admin_notes_save_ui(
        student_name=student_name,
        counseling_date_value=date(2026, 9, 5),
        summary_text=summary,
        export_allowed=scenario != "blocked",
    )
    st.session_state["test_pending_request"] = request.preview_key if request is not None else ""
    st.text_input("Below save area", value="Unchanged input", key="test_stable_input")
    st.html('<div style="height:600px"></div>')


def main() -> None:
    from streamlit.testing.v1 import AppTest

    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", default=str(Path(__file__).resolve().parents[1]))
    args = parser.parse_args()
    for scenario in ("success", "duplicate", "failure", "blocked", "batch_recovered", "missing_student"):
        at = AppTest.from_function(render_fixture, args=(args.app_root, scenario)).run(timeout=30)
        assert not at.exception, [item.message for item in at.exception]
        request_before = at.session_state["test_pending_request"]
        at.button[0].click().run(timeout=30)
        assert not at.exception, [item.message for item in at.exception]
        assert not any("scrollIntoView" in item.proto.srcdoc for item in at.get("iframe")), "Save must not force a scroll"
        assert at.session_state["test_pending_request"] == request_before
        assert at.text_input(key="test_stable_input").value == "Unchanged input"
        if scenario in {"success", "duplicate", "batch_recovered"}:
            assert at.session_state["last_admin_notes_save_key"] == request_before
            assert at.session_state["test_sync_calls"] == 1
            at.run()
            assert not any(button.label == "5A ADMIN 특이사항으로 내보내기" for button in at.button)
            if scenario == "batch_recovered":
                assert at.text_input(key="student_name").value == "TEST"
        elif scenario == "failure":
            assert len(at.error) == 1
            assert at.session_state["test_sync_calls"] == 1
        else:
            assert len(at.warning) == 1
            assert "test_sync_calls" not in at.session_state
        print(f"PASS: admin save UI ({scenario})")

    source = (Path(args.app_root) / "app.py").read_text(encoding="utf-8-sig")
    assert "@st.fragment\ndef render_admin_notes_save_ui(" in source
    print("PASS: admin save is isolated from full-page reruns")


if __name__ == "__main__":
    main()
