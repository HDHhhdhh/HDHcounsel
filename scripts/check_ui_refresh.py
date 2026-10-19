from __future__ import annotations

import ast
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch
from zoneinfo import ZoneInfo

ROOT_DIR = Path(__file__).resolve().parents[1]


def check_interaction_rerun_contracts(app_root: Path) -> None:
    tree = ast.parse((app_root / "app.py").read_text(encoding="utf-8-sig"))
    functions = {
        node.name: node
        for node in ast.walk(tree)
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }

    csv_workspace = functions["render_log_csv_to_docs_preview_ui"]
    assert any(
        isinstance(decorator, ast.Attribute)
        and isinstance(decorator.value, ast.Name)
        and decorator.value.id == "st"
        and decorator.attr == "fragment"
        for decorator in csv_workspace.decorator_list
    ), "CSV interactions must remain isolated from full-page reruns"
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == "rerun"
        for node in ast.walk(csv_workspace)
    ), "CSV buttons must refresh through the fragment-aware helper"

    single_job = functions["start_single_consultation_job"]
    assert not any(
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "st"
        and node.func.attr == "rerun"
        for node in ast.walk(single_job)
    ), "The generate button must not force a second full-page rerun"
    generate_buttons = [
        node
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr == "button"
        and node.args
        and isinstance(node.args[0], ast.Constant)
        and node.args[0].value == "정리본 생성·복사"
    ]
    assert any(
        any(
            keyword.arg == "on_click"
            and isinstance(keyword.value, ast.Name)
            and keyword.value.id == "start_single_consultation_job"
            for keyword in button.keywords
        )
        for button in generate_buttons
    ), "The generate button must prepare its job in a pre-rerun callback"


def render_overview_fixture(app_root: str) -> None:
    import sys

    sys.path.insert(0, app_root)
    import app

    app.create_audio_log_overview()


def main() -> None:
    import argparse
    from streamlit.testing.v1 import AppTest

    parser = argparse.ArgumentParser()
    parser.add_argument("--app-root", default=str(ROOT_DIR))
    args = parser.parse_args()
    sys.path.insert(0, args.app_root)
    sys.path.insert(0, str(Path(args.app_root) / "scripts"))
    import app
    from check_audio_upload_layout import csv_path, render_fixture

    check_interaction_rerun_contracts(Path(args.app_root))
    print("PASS: interaction reruns stay within their intended scope")

    at = AppTest.from_function(render_overview_fixture, args=(args.app_root,)).run()
    assert not at.exception
    assert not at.get("empty"), "Overview must not be erased before rerendering"
    columns = at.get("column")
    assert len(columns) == 2
    assert all(not column.get("caption") for column in columns), "Put the label above both aligned columns"
    overview_html = "\n".join(element.proto.body for element in at.get("html"))
    assert "grid-template-columns:minmax(0,300px) minmax(0,1fr);" in overview_html, "Restore space for the history list"
    assert "max-width:300px;" in overview_html
    assert "grid-template-columns:minmax(0,1fr) max-content;" not in overview_html, "Action belongs below the upload box"
    assert '.st-key-audio-upload-input [data-testid="stFileUploaderDropzoneInstructions"] { display:none;' in " ".join(overview_html.split())
    assert any("상담 녹음 파일 업로드" in caption.value for caption in at.caption)
    print("PASS: upload and action retain their containers between runs")

    output = Mock()
    target = app.refresh_log_csv_processing_history_summary(output, app.empty_log_csv_processing_history())
    assert target is output.markdown.return_value, "Keep the exact element for subsequent replacements"
    assert [call[0] for call in output.mock_calls] == ["markdown"], "History must be replaced atomically"
    assert output.markdown.call_args.args[0].count('class="log-history-strip"') == 3
    print("PASS: three-day history updates without a blank intermediate delta")

    for reference_day, expected_labels in (
        ("2026-09-05", ("오늘", "어제", "09-02")),
        ("2026-09-08", ("어제", "09-06", "09-05")),
        ("2026-09-09", ("오늘", "09-07", "09-06")),
        ("2026-08-01", ("오늘", "어제", "07-29")),
        ("2027-01-02", ("오늘", "어제", "12-30")),
    ):
        reference_time = datetime.fromisoformat(reference_day).replace(tzinfo=ZoneInfo("Asia/Seoul"))
        output = Mock()
        with patch.object(app, "datetime", wraps=datetime) as clock:
            clock.now.return_value = reference_time
            app.refresh_log_csv_processing_history_summary(output, app.empty_log_csv_processing_history())
            clock.now.assert_called_once_with(ZoneInfo("Asia/Seoul"))
        markup = output.markdown.call_args.args[0]
        positions = []
        for label in expected_labels:
            marker = f'class="log-history-date">{label}</strong>'
            assert marker in markup, f"{reference_day}: missing {label}"
            positions.append(markup.index(marker))
        assert positions == sorted(positions)
        assert markup.count('class="log-history-strip"') == 3
    print("PASS: history uses calendar-relative dates across attendance, month and year boundaries")

    at = AppTest.from_function(render_fixture, args=(args.app_root,)).run(timeout=30)
    assert not at.exception
    expected_path = csv_path(at._tree)
    for flag in ("post_run_warning", "post_run_success", "post_run_error"):
        at.session_state[flag] = "Test feedback"
        at.run(timeout=30)
        assert not at.exception, [error.message for error in at.exception]
        assert csv_path(at._tree) == expected_path, f"{flag}: feedback remounted the page columns"
        assert at.button(key="log_csv_to_docs_save_button").disabled
    print("PASS: feedback does not remount the main columns or unlock actions")

    from ui_contract_fixture import render_contract_fixture

    at = AppTest.from_function(render_contract_fixture, args=(args.app_root,)).run(timeout=30)
    assert not at.exception, [error.message for error in at.exception]
    for mode in (
        "empty",
        "selected",
        "saving",
        "batch_pending",
        "completed_pending",
        "completed",
        "selected",
    ):
        at.radio(key="baseline-state").set_value(mode).run(timeout=30)
        assert not at.exception, [error.message for error in at.exception]
        assert len([item for item in at.expander if item.label == "로그 CSV → 학생 Docs 추가"]) == 1
        save = [button for button in at.button if button.key == "log_csv_to_docs_save_button"]
        resume = [button for button in at.button if button.label.startswith("남은 작업 이어서 저장")]
        if mode == "saving":
            assert not save and not resume
        else:
            assert len(save) == 1
            assert save[0].disabled == (mode != "selected")
        if mode in {"empty", "completed_pending", "completed"}:
            assert not at.dataframe
        if mode == "batch_pending":
            assert any(
                item.value == "이번 묶음 처리 완료 · 오늘 전체 1/2건 · 저장 완료 1명" for item in at.success
            )
            assert len([button for button in at.button if button.label == "이번 묶음 확인"]) == 1
        if mode == "completed_pending":
            assert any(
                item.value == "오늘 전체 처리 완료 · 1/1건 · 저장 완료 1명" for item in at.success
            )
            assert len(
                [button for button in at.button if button.label == "오늘 전체 완료 확인"]
            ) == 1
        generate = next(button for button in at.button if button.label == "정리본 생성·복사")
        assert generate.disabled == (mode != "selected")
        print(f"PASS: isolated baseline state ({mode})")


if __name__ == "__main__":
    main()
