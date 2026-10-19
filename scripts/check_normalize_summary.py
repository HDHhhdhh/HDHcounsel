from __future__ import annotations

from contextlib import nullcontext
from datetime import date
from pathlib import Path
import re
import sys
import tempfile
import types
from unittest.mock import patch


ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


def load_normalize_summary():
    try:
        from app import normalize_summary

        return normalize_summary, "app.normalize_summary"
    except ModuleNotFoundError as exc:
        missing_name = getattr(exc, "name", "")
        if missing_name not in {"streamlit", "pyperclip"}:
            raise
        from counsel_modules.text_utils import (
            merge_next_action_sections_into_notes,
            move_today_check_section_to_top,
            normalize_legacy_check_sections,
            normalize_summary_identity,
            remove_empty_placeholder_lines,
            ensure_required_today_focus_section,
            remove_generic_today_focus_items,
            remove_meta_uncertainty_notes,
            remove_misc_record_section,
            remove_parent_message_sections,
            remove_runtime_noise_from_summary,
            remove_status_detail_labels,
        )

        def normalize_summary(summary: str, student_name: str, counseling_date: date) -> str:
            no_runtime_noise = remove_runtime_noise_from_summary(summary)
            identity_fixed = normalize_summary_identity(no_runtime_noise, student_name, counseling_date)
            no_parent_message = remove_parent_message_sections(identity_fixed)
            no_status_labels = remove_status_detail_labels(no_parent_message)
            no_misc_record = remove_misc_record_section(no_status_labels)
            no_empty_placeholders = remove_empty_placeholder_lines(no_misc_record)
            normalized_checks = normalize_legacy_check_sections(no_empty_placeholders)
            normalized_without_placeholders = remove_empty_placeholder_lines(normalized_checks)
            no_next_action_section = merge_next_action_sections_into_notes(normalized_without_placeholders)
            no_generic_today_focus = remove_generic_today_focus_items(no_next_action_section)
            no_meta_uncertainty = remove_meta_uncertainty_notes(no_generic_today_focus)
            with_required_today = ensure_required_today_focus_section(no_meta_uncertainty)
            return move_today_check_section_to_top(with_required_today)

        return normalize_summary, f"text_utils fallback ({missing_name} not installed)"


def assert_contains(text: str, expected: str) -> None:
    assert expected in text, f"Expected to find {expected!r} in:\n{text}"


def assert_not_contains(text: str, unexpected: str) -> None:
    assert unexpected not in text, f"Did not expect {unexpected!r} in:\n{text}"


def check_codex_echoed_prompt_markers_do_not_shadow_summary() -> None:
    from counsel_modules.text_utils import extract_marked_summary_output

    expected = "[오늘 확인할 것]\n\n수업 전 확인\n- 합성 확인 항목\n\n*상담 참고사항*\n- 합성 상담 내용"
    codex_stdout = f"""OpenAI Codex v0.142.3
--------
user
The words SUMMARY_BEGIN and SUMMARY_END are instructions.
codex
SUMMARY_BEGIN
{expected}
SUMMARY_END
SUMMARY_BEGIN
{expected}
tokens used
18,392
SUMMARY_END
"""

    assert extract_marked_summary_output(codex_stdout) == expected

    unmarked_codex_stdout = f"""OpenAI Codex v0.142.3
--------
user
The words SUMMARY_BEGIN and SUMMARY_END are instructions.
codex
{expected}
tokens used
18,392
{expected}
"""

    assert extract_marked_summary_output(unmarked_codex_stdout) == expected


def check_identity_lines_removed(normalize_summary) -> None:
    raw_summary = """학생: 이전이름
상담일: 2020-01-01

[상세 상담 기록]
- 수학 오답을 다시 확인함.
"""
    result = normalize_summary(raw_summary, "홍길동", date(2026, 5, 11))

    assert_contains(result, "- 수학 오답을 다시 확인함.")
    assert_not_contains(result, "학생:")
    assert_not_contains(result, "상담일:")

    bullet_identity_summary = """[오늘 확인할 것]

수업 전 확인

*상담 참고사항*
- 학생: 오세현
- 상담일: 2026-05-25
- 수업 중 학생이 어떤 내용을 다 하지 않았다는 대화가 반복적으로 있었음.
"""
    bullet_result = normalize_summary(bullet_identity_summary, "오세현", date(2026, 5, 25))

    assert_contains(bullet_result, "*상담 참고사항*")
    assert_contains(bullet_result, "수업 중 학생이 어떤 내용을 다 하지 않았다는 대화가 반복적으로 있었음.")
    assert_not_contains(bullet_result, "학생:")
    assert_not_contains(bullet_result, "학생명:")
    assert_not_contains(bullet_result, "상담일:")
    assert_not_contains(bullet_result, "오세현")
    assert_not_contains(bullet_result, "2026-05-25")


def check_parent_misc_and_placeholders(normalize_summary) -> None:
    raw_summary = """학생: 이전이름
상담일: 2020-01-01

[학부모 전달 문구]
- 이 문구는 제거되어야 합니다.

[상세 상담 기록]
- 개념 설명을 다시 진행함.

1. 기타 기록
- 기타 기록도 제거되어야 합니다.

[오늘 바로 확인할 것]
숙제
- [해당 없음]
요청사항
- 없음
특이사항
- 집중 상태 양호
다음 수업 체크
"""
    result = normalize_summary(raw_summary, "김민수", date(2026, 5, 11))

    assert_not_contains(result, "학생:")
    assert_not_contains(result, "상담일:")
    assert_contains(result, "- 개념 설명을 다시 진행함.")
    assert_contains(result, "- 집중 상태 양호")
    assert_not_contains(result, "이 문구는 제거되어야 합니다.")
    assert_not_contains(result, "기타 기록도 제거되어야 합니다.")
    assert_not_contains(result, "- [해당 없음]")
    assert_not_contains(result, "- 없음")


def check_legacy_section_merge_and_move(normalize_summary) -> None:
    raw_summary = """[상세 상담 기록]
학생: 임시
상담일: 2020-01-01
- 진도 확인을 진행함.

[확인 필요]
- 숙제 제출 여부
- 다음 단원 준비물

[오늘 바로 확인할 것]
숙제
요청사항
특이사항
다음 수업 체크
- 기존 확인
"""
    result = normalize_summary(raw_summary, "박서연", date(2026, 5, 11))

    assert_contains(result, "- 기존 확인")
    assert_not_contains(result, "- 숙제 제출 여부")
    assert_not_contains(result, "- 다음 단원 준비물")
    assert_not_contains(result, "[확인 필요]")
    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "수업 전 확인")


def check_google_docs_progress_book_from_context() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """진도(대수): 35차시, 36차시, 37차시

[오늘 확인할 것]
숙제 체크
- 트레이닝팩과 APEX를 함께 진행 중인지 확인
"""
    result = prepare_summary_for_google_docs_cell(
        raw_summary,
        curriculum="대수",
        book="트레이닝팩",
    )

    assert_contains(result, "진도(대수 APEX): 35차시, 36차시, 37차시")
    assert_not_contains(result, "진도(대수): 35차시, 36차시, 37차시")


def check_google_docs_next_action_absorbed() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """[오늘 상담할 것]
숙제 체크
- APEX 숙제 완료 여부 확인

*상담 참고사항*
- 최근 풀이 속도가 느려졌다고 말함.

*다음 조치*
- APEX 오답 정리 여부 확인
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "상담 참고사항")
    assert_contains(result, "- APEX 오답 정리 여부 확인")
    assert_not_contains(result, "*다음 조치*")
    assert_not_contains(result, "다음 수업 조치")


def check_google_docs_homework_duplicate_books_same_assignment() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """진도(대수): 24차시, 26차시, 27차시(중단)

숙제:
- 교재: 트레이닝팩
- 다음 숙제: 삼각함수 그래프
- 교재: APEX
- 다음 숙제: 삼각함수 그래프
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_contains(result, "진도(대수 APEX): 24차시, 26차시, 27차시(중단)")
    assert_contains(result, "숙제:\n- 교재: 트레이닝팩, APEX\n- 다음 숙제: 삼각함수 그래프")
    assert result.count("다음 숙제: 삼각함수 그래프") == 1, result
    assert result.count("교재:") == 1, result


def check_google_docs_homework_distinct_book_assignments() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """숙제:
- 교재: 트레이닝팩
- 다음 숙제: 삼각함수 그래프
- 교재: APEX
- 다음 숙제: 26차시 오답 정리
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_contains(result, "숙제:")
    assert_contains(result, "- 트레이닝팩: 삼각함수 그래프")
    assert_contains(result, "- APEX: 26차시 오답 정리")
    assert_not_contains(result, "- 교재: 트레이닝팩, APEX")


def check_google_docs_homework_progress_lifted_to_progress_line() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """숙제:
- 올포유: 진행률 100%, 다음 숙제 그래프+활용 풀 수 있는 데까지
- APEX: 진행률 100%, 다음 숙제 풀어오기
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_contains(result, "진도(대수 APEX): 진행률 100%")
    assert_contains(result, "- 올포유: 다음 숙제 그래프+활용 풀 수 있는 데까지")
    assert_contains(result, "- APEX: 다음 숙제 풀어오기")
    assert result.count("진행률 100%") == 1, result


def check_google_docs_homework_progress_does_not_invent_unknown_progress_line() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """숙제:
- 올포유: 진행률 100%, 다음 숙제 그래프+활용 풀 수 있는 데까지
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_not_contains(result, "진도: 확인 필요")
    assert_contains(result, "올포유")
    assert_contains(result, "진행률 100%")
    assert_contains(result, "그래프+활용 풀 수 있는 데까지")


def check_google_docs_homework_does_not_swallow_request_note_and_check_sections() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """진도(대수 APEX): 36차시

숙제:
- [부분 완료] 첫 번째 과제 진행
- [미완료] 월요일까지 트레이닝팩 4회차 풀어오기

요청사항
- [진행 중] 영상은 4개 목표였으나 2개까지 가능하다고 함

특이사항
- 시험 1등급을 받음
- 일부 문항은 찍어서 맞힌 부분이 있다고 언급

다음 수업 체크
- 트레이닝팩 4회차 완료 여부 확인
- 영상 2개 시청 여부 확인
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_contains(result, "진도(대수 APEX): 36차시")
    assert_contains(result, "상담 참고사항")
    assert_contains(result, "- [진행 중] 영상은 4개 목표였으나 2개까지 가능하다고 함")
    assert_contains(result, "- 시험 1등급을 받음")
    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "- 트레이닝팩 4회차 완료 여부 확인")
    assert_contains(result, "숙제:\n- [부분 완료] 첫 번째 과제 진행")
    assert_not_contains(result, "숙제:\n- [부분 완료] 첫 번째 과제 진행\n- [미완료] 월요일까지 트레이닝팩 4회차 풀어오기\n- 요청사항")
    assert_not_contains(result, "- 요청사항")


def check_google_docs_empty_notes_removed_and_progress_homework_kept() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """진도(대수 APEX): 38차시, 39차시, 40차시

상담 참고사항

.

숙제:
- APEX: 진행률 100%, 다음 숙제 풀어오기
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_not_contains(result, "상담 참고사항")
    assert_not_contains(result, "\n.\n")
    assert_contains(result, "진도(대수 APEX): 38차시, 39차시, 40차시")
    assert_contains(result, "숙제:")
    assert result.rfind("숙제:") > result.rfind("진도"), result


def check_google_docs_placeholder_notes_removed() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    result = prepare_summary_for_google_docs_cell("상담 참고사항\n- 없음")

    assert_not_contains(result, "상담 참고사항")
    assert_not_contains(result, "진도: 확인 필요")
    assert_not_contains(result, "숙제:")
    assert result == ""


def check_google_docs_real_notes_kept() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    result = prepare_summary_for_google_docs_cell(
        "상담 참고사항\n- 시험기간 중 발표 준비 시간이 부족하다는 맥락이 있었음."
    )

    assert_contains(result, "상담 참고사항")
    assert_contains(result, "- 시험기간 중 발표 준비 시간이 부족하다는 맥락이 있었음.")
    assert_not_contains(result, "숙제:")


def check_google_docs_special_note_placeholder_removed_with_order_kept() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    raw_summary = """진도(대수 APEX): 41차시

상담 참고사항
특이사항 없음

숙제:
- 트레이닝팩: 다음 숙제
"""
    result = prepare_summary_for_google_docs_cell(raw_summary, curriculum="대수", book="APEX")

    assert_not_contains(result, "상담 참고사항")
    assert_contains(result, "진도(대수 APEX): 41차시")
    assert_contains(result, "숙제:")
    assert_contains(result, "- 교재: 트레이닝팩")
    assert result.endswith("- 다음 숙제: 다음 숙제"), result
    assert_not_contains(result, "- 특이사항")
    assert_not_contains(result, "- 다음 수업 체크")


def check_next_action_section_absorbed(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]
숙제 체크
- APEX 숙제 완료 여부 확인

*상담 참고사항*
- 최근 풀이 속도가 느려졌다고 말함.

*다음 조치*
- APEX 오답 정리 여부 확인
"""
    result = normalize_summary(raw_summary, "김민수", date(2026, 5, 11))

    assert_not_contains(result, "[오늘 상담할 것]")
    assert_not_contains(result, "APEX 숙제 완료 여부 확인")
    assert_contains(result, "*상담 참고사항*")
    assert_contains(result, "- APEX 오답 정리 여부 확인")
    assert_not_contains(result, "*다음 조치*")
    assert_not_contains(result, "다음 수업 조치")


def check_generic_homework_scope_removed_from_today_focus(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]

숙제 체크
- 수요일까지 정한 숙제 범위를 어디까지 풀어왔는지 확인

*상담 참고사항*
- 테스트 상담 참고사항
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "숙제 체크")
    assert_not_contains(result, "수요일까지 정한 숙제 범위를 어디까지 풀어왔는지 확인")
    assert_not_contains(result, "[오늘 상담할 것]")
    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "수업 전 확인")
    assert_contains(result, "*상담 참고사항*")
    assert_contains(result, "- 테스트 상담 참고사항")


def check_generic_today_focus_bullets_removed(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]

수업 전 확인
- 숙제 진행 여부 확인
- 리뷰 완료 여부 확인
- 이해도 확인
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "숙제 진행 여부 확인")
    assert_not_contains(result, "리뷰 완료 여부 확인")
    assert_not_contains(result, "이해도 확인")
    assert_not_contains(result, "[오늘 상담할 것]")
    assert_not_contains(result, "수업 전 확인")


def check_concrete_today_focus_bullets_preserved(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]

수업 전 확인
- 트레이닝팩 p.42~45 풀이 흔적 확인
- APEX 26차시 백지리뷰 제출 여부 확인
- 단원평가 3회 12번, 15번 오답 재풀이 확인
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "수업 전 확인")
    assert_contains(result, "- 트레이닝팩 p.42~45 풀이 흔적 확인")
    assert_contains(result, "- APEX 26차시 백지리뷰 제출 여부 확인")
    assert_contains(result, "- 단원평가 3회 12번, 15번 오답 재풀이 확인")


def check_homework_completion_removed_but_concrete_evidence_preserved(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]

수업 전 확인
- APEX 26차시 숙제 완료 여부 확인
- 트레이닝팩 p.42~45 풀이 흔적 확인
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "APEX 26차시 숙제 완료 여부 확인")
    assert_contains(result, "- 트레이닝팩 p.42~45 풀이 흔적 확인")
    assert_contains(result, "[오늘 확인할 것]")


def check_due_day_generic_range_removed(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]

수업 전 확인
- 다음 시간까지 정한 범위를 어디까지 풀었는지 확인
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "다음 시간까지 정한 범위를 어디까지 풀었는지 확인")
    assert_not_contains(result, "[오늘 상담할 것]")
    assert_not_contains(result, "수업 전 확인")


def check_ambiguous_today_focus_without_target_removed(normalize_summary) -> None:
    from counsel_modules.text_utils import summary_has_required_today_focus

    raw_summary = """[오늘 확인할 것]

수업 전 확인
- 이전 숙제를 실제로 해왔는지 풀이 흔적 기준으로 확인
- 수업 영상 청취를 진행했는지 확인

*상담 참고사항*
- 학생이 피곤하다고 답함.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "이전 숙제를 실제로 해왔는지 풀이 흔적 기준으로 확인")
    assert_not_contains(result, "수업 영상 청취를 진행했는지 확인")
    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "수업 전 확인")
    assert_contains(result, "*상담 참고사항*")
    assert_contains(result, "학생이 피곤하다고 답함")
    assert summary_has_required_today_focus(result) is False


def check_specific_today_focus_targets_preserved(normalize_summary) -> None:
    raw_summary = """[오늘 확인할 것]

수업 전 확인
- 마플 p.268 풀이 흔적 확인
- APEX 42차시 백지리뷰 제출 여부 확인

*상담 참고사항*
- 숙제 확인이 필요함.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_contains(result, "- 마플 p.268 풀이 흔적 확인")
    assert_contains(result, "- APEX 42차시 백지리뷰 제출 여부 확인")


def check_generic_homework_check_concretized_from_homework_section(normalize_summary) -> None:
    raw_summary = """[오늘 확인할 것]

수업 전 확인
- 숙제 풀이 흔적 확인

숙제:
- 트레이닝팩: p.10~12

*상담 참고사항*
- 숙제 관련 대화가 있었음.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "숙제 풀이 흔적 확인")
    assert_contains(result, "- 트레이닝팩 p.10~12 풀이 흔적 확인")
    assert_contains(result, "숙제:")
    assert_contains(result, "트레이닝팩: p.10~12")


def check_generic_video_check_concretized_from_homework_section(normalize_summary) -> None:
    raw_summary = """[오늘 확인할 것]

수업 전 확인
- 영상 시청 여부 확인

숙제:
- APEX: 42차시 영상 보기

*상담 참고사항*
- 영상 숙제가 있었음.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "- 영상 시청 여부 확인")
    assert_contains(result, "- APEX 42차시 영상 시청 여부 확인")
    assert_contains(result, "숙제:")
    assert_contains(result, "APEX: 42차시 영상 보기")


def check_only_broad_today_focus_items_make_summary_invalid(normalize_summary) -> None:
    from counsel_modules.text_utils import summary_has_required_today_focus

    raw_summary = """[오늘 확인할 것]

수업 전 확인
- 이해도 확인
- 집중도 확인
- 태도 확인

*상담 참고사항*
- 짧은 상담이 있었음.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "이해도 확인")
    assert_not_contains(result, "집중도 확인")
    assert_not_contains(result, "태도 확인")
    assert summary_has_required_today_focus(result) is False


def check_meta_uncertainty_notes_removed_with_homework_preserved(normalize_summary) -> None:
    raw_summary = """상담 참고사항
- 원문상 특정 교재명이나 과제 범위는 명확하지 않음.
- “이거 가져왔어”, “조금 더 끝내고 ... 볼 것 같습니다”라는 발화가 있어, 지참 자료나 진행 중인 내용이 있었던 것으로만 확인됨.

숙제:
- APEX: 26차시 마무리
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "원문상")
    assert_not_contains(result, "발화가 있어")
    assert_not_contains(result, "상담 참고사항")
    assert_contains(result, "숙제:")
    assert_contains(result, "APEX: 26차시 마무리")


def check_meta_uncertainty_notes_empty_section_removed(normalize_summary) -> None:
    raw_summary = """상담 참고사항
- 특정 교재명은 확인되지 않음.
- 과제 범위는 명확하지 않음.
- 진행 중인 내용이 있었던 것으로 보임.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "확인되지")
    assert_not_contains(result, "명확하지")
    assert_not_contains(result, "것으로 보임")
    assert_not_contains(result, "상담 참고사항")


def check_actionable_uncertainty_check_targets_preserved(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]

수업 전 확인
- 학생이 가져온 자료명 확인
- 학생이 가져온 프린트의 남은 풀이 범위 확인
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "학생이 가져온 자료명 확인")
    assert_contains(result, "학생이 가져온 프린트의 남은 풀이 범위 확인")


def check_meta_uncertainty_today_focus_removed(normalize_summary) -> None:
    raw_summary = """[오늘 상담할 것]

수업 전 확인
- 원문에는 직접 언급되지 않았으나 숙제가 있었던 것으로 보임.
- 확인 필요해 보임.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "원문에는")
    assert_not_contains(result, "확인 필요해 보임")
    assert_not_contains(result, "[오늘 상담할 것]")


def check_meta_uncertainty_keeps_confirmed_notes(normalize_summary) -> None:
    raw_summary = """상담 참고사항
- APEX 진도 진행 중.
- 과제 범위는 명확하지 않음.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_contains(result, "상담 참고사항")
    assert_contains(result, "APEX 진도 진행 중.")
    assert_not_contains(result, "과제 범위는 명확하지 않음.")


def check_normalize_summary_removes_empty_notes_placeholder(normalize_summary) -> None:
    raw_summary = """[오늘 확인할 것]

수업 전 확인
- APEX 38차시 진행 상황 확인

상담 참고사항
.

진도(대수 APEX): 38차시

숙제:
- APEX: 다음 숙제 풀어오기
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 11))

    assert_not_contains(result, "상담 참고사항")
    assert_not_contains(result, "\n.\n")
    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "진도(대수 APEX): 38차시")
    assert_contains(result, "숙제:")


def check_log_csv_homework_rows_merge_same_core() -> None:
    from counsel_modules.log_csv_utils import (
        match_log_rows_to_docs,
        merge_homework_duplicate_log_rows,
    )
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    docs_rows = [{"student_name": "전수민", "doc_id": "doc-1", "doc_url": "https://docs.example/doc-1"}]
    log_rows = [
        {
            "date": "2026-05-15",
            "name": "전수민",
            "sid": "전수민001",
            "curriculum": "대수 APEX",
            "notes": "[오늘 확인할 것]\n- APEX 숙제 확인\n\n상담 참고사항\n- 상담 내용 동일",
            "progress": "34차시",
            "homework_book": "라이트센",
            "homework_progress": "100%",
        },
        {
            "date": "2026-05-15",
            "name": "전수민",
            "sid": "전수민001",
            "curriculum": "대수 APEX",
            "notes": "[오늘 확인할 것]\n- APEX 숙제 확인\n\n상담 참고사항\n- 상담 내용 동일",
            "progress": "34차시",
            "homework_book": "트레이닝팩",
            "homework_progress": "100%",
            "homework_next": "넓이 2개",
        },
    ]

    merged = merge_homework_duplicate_log_rows(match_log_rows_to_docs(log_rows, docs_rows))
    assert len(merged) == 1, merged
    result = prepare_summary_for_google_docs_cell(
        str(merged[0].get("preview") or ""),
        student_name="전수민",
        curriculum="대수",
        book="APEX",
    )
    assert_contains(result, "진도(대수 APEX): 34차시")
    assert_contains(result, "- 라이트센: 진행률 100%")
    assert_contains(result, "- 트레이닝팩: 진행률 100%, 다음 숙제 넓이 2개")


def check_log_csv_homework_rows_merge_same_assignment() -> None:
    from counsel_modules.log_csv_utils import (
        match_log_rows_to_docs,
        merge_homework_duplicate_log_rows,
    )
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    docs_rows = [{"student_name": "정지효", "doc_id": "doc-2", "doc_url": "https://docs.example/doc-2"}]
    log_rows = [
        {
            "date": "2026-05-15",
            "name": "정지효",
            "sid": "정지효001",
            "curriculum": "대수 APEX",
            "notes": "상담 참고사항\n- 상담 내용 동일",
            "progress": "35차시",
            "homework_book": "트레이닝팩",
            "homework_next": "오답 정리",
        },
        {
            "date": "2026-05-15",
            "name": "정지효",
            "sid": "정지효001",
            "curriculum": "대수 APEX",
            "notes": "상담 참고사항\n- 상담 내용 동일",
            "progress": "35차시",
            "homework_book": "APEX",
            "homework_next": "오답 정리",
        },
    ]

    merged = merge_homework_duplicate_log_rows(match_log_rows_to_docs(log_rows, docs_rows))
    assert len(merged) == 1, merged
    result = prepare_summary_for_google_docs_cell(
        str(merged[0].get("preview") or ""),
        student_name="정지효",
        curriculum="대수",
        book="APEX",
    )
    assert_contains(result, "- 교재: 트레이닝팩, APEX")
    assert result.count("다음 숙제: 오답 정리") == 1, result


def check_log_csv_homework_rows_do_not_merge_different_core() -> None:
    from counsel_modules.log_csv_utils import match_log_rows_to_docs, merge_homework_duplicate_log_rows

    docs_rows = [{"student_name": "전수민", "doc_id": "doc-1", "doc_url": "https://docs.example/doc-1"}]
    log_rows = [
        {
            "date": "2026-05-15",
            "name": "전수민",
            "sid": "전수민001",
            "curriculum": "대수 APEX",
            "notes": "상담 참고사항\n- 첫 번째 상담",
            "progress": "34차시",
            "homework_book": "라이트센",
        },
        {
            "date": "2026-05-15",
            "name": "전수민",
            "sid": "전수민001",
            "curriculum": "대수 APEX",
            "notes": "상담 참고사항\n- 다른 상담",
            "progress": "34차시",
            "homework_book": "트레이닝팩",
        },
    ]

    merged = merge_homework_duplicate_log_rows(match_log_rows_to_docs(log_rows, docs_rows))
    assert len(merged) == 2, merged


def check_log_csv_same_content_different_dates_remain_separate() -> None:
    from counsel_modules.log_csv_utils import (
        build_log_csv_dedupe_key,
        log_csv_confirmed_student_keys,
        match_log_rows_to_docs,
        merge_homework_duplicate_log_rows,
    )

    docs_rows = [{"student_name": "테스트학생", "doc_id": "doc-date-test"}]
    first_row = {
        "date": "2026-10-01",
        "name": "테스트학생",
        "sid": "student-1",
        "notes": "상담 참고사항\n- 같은 내용",
        "homework_row": "1",
    }
    second_row = {**first_row, "date": "2026-10-02"}

    matched = match_log_rows_to_docs([first_row, second_row], docs_rows)
    merged = merge_homework_duplicate_log_rows(matched)
    confirmed = log_csv_confirmed_student_keys(
        [
            {
                "date": row["date"],
                "name": row["name"],
                "doc_id": "doc-date-test",
                "result_status": "성공",
            }
            for row in (first_row, second_row)
        ]
    )

    assert len(merged) == 2, merged
    assert all(bool(item.get("selected")) for item in merged), merged
    assert [item["source_row"]["date"] for item in merged] == ["2026-10-01", "2026-10-02"]
    assert build_log_csv_dedupe_key(first_row) != build_log_csv_dedupe_key(second_row)
    assert {source_date for source_date, _student_key in confirmed} == {
        "2026-10-01",
        "2026-10-02",
    }


def check_log_csv_homework_check_only_preserved() -> None:
    from counsel_modules.log_csv_utils import match_log_rows_to_docs
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    docs_rows = [{"student_name": "테스트학생", "doc_id": "doc-check-only"}]
    log_rows = [
        {
            "date": "2026-10-01",
            "name": "테스트학생",
            "notes": "",
            "homework_row": "1",
        }
    ]

    matched = match_log_rows_to_docs(log_rows, docs_rows)
    assert matched[0]["selected"], matched
    result = prepare_summary_for_google_docs_cell(
        str(matched[0].get("preview") or ""),
        student_name="테스트학생",
        counseling_date="2026-10-01",
    )
    assert_contains(result, "숙제:")
    assert_contains(result, "- 검사: 완료")


def check_log_csv_attendance_only_rows_remain_saveable() -> None:
    from app import prepare_log_csv_preview_for_google_docs
    from counsel_modules.log_csv_utils import log_row_has_docs_content, match_log_rows_to_docs

    row = {"date": "2026-10-01", "name": "TEST_ATTENDANCE", "notes": ""}
    docs_rows = [{"student_name": row["name"], "doc_id": "doc-attendance"}]

    item = match_log_rows_to_docs([row], docs_rows)[0]
    text = prepare_log_csv_preview_for_google_docs(item, consumed_filter_enabled=False)

    assert item["selected"], item
    assert text == "출결: 출석", text
    assert not log_row_has_docs_content({**row, "date": ""})
    assert not log_row_has_docs_content({**row, "name": ""})


def check_log_csv_consumed_notes_cannot_remove_attendance() -> None:
    import app
    from counsel_modules import local_consumed_admin_notes
    from counsel_modules.log_csv_utils import match_log_rows_to_docs

    note = "APEX 42차시 백지리뷰 제출 여부 확인"
    row = {"date": "2026-10-01", "name": "TEST_ATTENDANCE", "sid": "test-attendance", "notes": note}
    docs_rows = [{"student_name": row["name"], "doc_id": "doc-attendance"}]
    with tempfile.TemporaryDirectory() as directory:
        registry_path = Path(directory) / "consumed.json"
        with patch.object(local_consumed_admin_notes, "CONSUMED_ADMIN_NOTES_PATH", registry_path):
            marked = local_consumed_admin_notes.mark_admin_notes_consumed(
                row["name"], row["sid"], note, "added",
                final_text=note, counseling_date=row["date"],
            )
            filtered_rows, diagnostic = app.filter_consumed_admin_notes_from_log_rows([row], enabled=True)
            item = match_log_rows_to_docs(filtered_rows, docs_rows)[0]
            text = app.prepare_log_csv_preview_for_google_docs(item, consumed_filter_enabled=True)

    assert marked["marked_count"] == 1, marked
    assert diagnostic["removed_count"] == 1, diagnostic
    assert filtered_rows[0]["notes"] == "", filtered_rows
    assert item["selected"], item
    assert text == "출결: 출석", text


def check_google_docs_attendance_survives_final_reformatting() -> None:
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    text = "출결: 출석\n\n진도(대수 APEX): 42차시\n\n숙제:\n- 검사: 완료"
    prepared = prepare_summary_for_google_docs_cell(text)
    final = prepare_summary_for_google_docs_cell(prepared)

    assert final.startswith("출결: 출석\n\n"), final
    assert final == prepared, final
    assert final.count("출결: 출석") == 1, final
    assert_contains(final, "진도(대수 APEX): 42차시")
    assert_contains(final, "숙제:\n- 검사: 완료")
    assert_not_contains(final, "상담 참고사항")


def check_google_docs_lock_timeout_detection() -> None:
    from counsel_modules.google_docs_utils import is_google_docs_lock_timeout_message

    message = "Apps Script 오류 · HTTP 200 · Exception: 잠금 시간초과: 다른 프로세스에서 잠금 상태를 너무 오래 유지하고 있습니다."
    assert is_google_docs_lock_timeout_message(message)


def check_google_docs_timeout_verify_classification() -> None:
    from counsel_modules.google_docs_utils import classify_google_docs_timeout_verification

    confirmed = classify_google_docs_timeout_verification(
        {"ok": True, "verify_only": True, "found_existing": True}
    )
    assert confirmed["status"] == "saved_confirmed_after_timeout"
    assert confirmed["timeout_unknown"] is False
    assert confirmed["retry_recommended"] is False
    assert confirmed["needs_review"] is False

    unknown = classify_google_docs_timeout_verification(
        {"ok": True, "verify_only": True, "found_existing": False}
    )
    assert unknown["status"] == "timeout_unknown"
    assert unknown["timeout_unknown"] is True
    assert unknown["retry_recommended"] is False
    assert unknown["needs_review"] is True

    lock_timeout = classify_google_docs_timeout_verification(
        {
            "ok": False,
            "verify_only": True,
            "error_type": "lock_timeout",
            "message": "LockService 잠금 시간초과: 다른 프로세스",
        }
    )
    assert lock_timeout["status"] == "lock_timeout_retryable"
    assert lock_timeout["retry_recommended"] is True

    explicit_failure = classify_google_docs_timeout_verification(
        {
            "ok": False,
            "verify_only": True,
            "error_type": "permission_or_doc_not_found",
            "message": "permission denied",
        }
    )
    assert explicit_failure["status"] == "실패"
    assert explicit_failure["failure"] is True

    unsafe_similar = classify_google_docs_timeout_verification(
        {
            "ok": True,
            "verify_only": True,
            "found_existing": False,
            "duplicate_skipped": True,
            "duplicate_reason": "unsafe_similar_record",
        }
    )
    assert unsafe_similar["status"] == "timeout_unknown"


def check_google_docs_timeout_verify_helper_import_smoke() -> None:
    from counsel_modules.google_docs_utils import classify_google_docs_timeout_verification

    assert callable(classify_google_docs_timeout_verification)


def assert_google_docs_uncertain_errors_are_caught(app_text: str) -> None:
    normalized_source = re.sub(r"\s+", " ", app_text)
    expected_handler = (
        "except (GoogleDocsPostTimeoutError, GoogleDocsPostIndeterminateError, "
        "GoogleDocsLockTimeoutError) as exc:"
    )
    assert expected_handler in normalized_source


def check_google_docs_html_error_response_is_delivery_uncertain() -> None:
    import app
    from counsel_modules.google_docs_utils import classify_google_docs_timeout_verification

    class HtmlErrorResponse:
        status_code = 404
        text = "<html><body>Not Found</body></html>"

        def json(self) -> dict[str, object]:
            raise ValueError("HTML response")

    class VerifiedResponse:
        status_code = 200
        text = '{"ok": true, "verify_only": true, "found_existing": true}'

        def json(self) -> dict[str, object]:
            return {"ok": True, "verify_only": True, "found_existing": True}

    with patch("requests.post", side_effect=[HtmlErrorResponse(), VerifiedResponse()]):
        try:
            app.append_summary_to_google_doc(
                "https://script.google.com/macros/s/example/exec",
                "테스트학생",
                date(2026, 8, 5),
                "상담 참고사항\n- 테스트 기록",
                "test-document-id",
            )
        except app.GoogleDocsPostIndeterminateError:
            pass
        else:
            raise AssertionError("HTML 404 response must require verify-only confirmation")

        verify_result = app.verify_summary_in_google_doc_after_timeout(
            "https://script.google.com/macros/s/example/exec",
            "테스트학생",
            date(2026, 8, 5),
            "상담 참고사항\n- 테스트 기록",
            "test-document-id",
        )

    assert classify_google_docs_timeout_verification(verify_result)["status"] == "saved_confirmed_after_timeout"
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    assert_google_docs_uncertain_errors_are_caught(app_text)
    assert "GoogleDocsPostIndeterminateError," in app_text


def check_google_docs_request_callable_can_be_reused() -> None:
    import json

    import app

    calls: list[dict[str, object]] = []

    class JsonResponse:
        status_code = 200

        def __init__(self, payload: dict[str, object]) -> None:
            self.payload = payload
            self.text = json.dumps(payload, ensure_ascii=False)

        def json(self) -> dict[str, object]:
            return self.payload

    def batch_post(url: str, **kwargs: object) -> JsonResponse:
        calls.append({"url": url, **kwargs})
        payload = kwargs.get("json") or {}
        if isinstance(payload, dict) and payload.get("verify_only") is True:
            return JsonResponse({"ok": True, "verify_only": True, "found_existing": True})
        return JsonResponse({"ok": True, "message": "added"})

    app.append_summary_to_google_doc(
        "https://script.google.com/macros/s/example/exec",
        "테스트학생",
        date(2026, 8, 31),
        "상담 참고사항\n- 연결 재사용 확인",
        "test-document-id",
        post_request=batch_post,
    )
    verify_result = app.verify_summary_in_google_doc_after_timeout(
        "https://script.google.com/macros/s/example/exec",
        "테스트학생",
        date(2026, 8, 31),
        "상담 참고사항\n- 연결 재사용 확인",
        "test-document-id",
        post_request=batch_post,
    )

    assert len(calls) == 2
    assert calls[0]["timeout"] == app.GOOGLE_DOCS_POST_TIMEOUT_SECONDS
    assert calls[1]["timeout"] == app.GOOGLE_DOCS_VERIFY_TIMEOUT_SECONDS
    assert verify_result["found_existing"] is True


def check_google_docs_lock_timeout_verifies_before_retry_classification() -> None:
    from counsel_modules.google_docs_utils import classify_google_docs_timeout_verification

    confirmed = classify_google_docs_timeout_verification(
        {"ok": True, "verify_only": True, "found_existing": True}
    )
    assert confirmed["status"] == "saved_confirmed_after_timeout"
    assert confirmed["retry_recommended"] is False

    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    assert_google_docs_uncertain_errors_are_caught(app_text)


def check_counsel_duplicate_fingerprint_matches_legacy_and_current_homework_formats() -> None:
    sys.modules.setdefault(
        "pyperclip",
        types.SimpleNamespace(copy=lambda _value: None, paste=lambda: ""),
    )
    if "streamlit" not in sys.modules:
        streamlit_stub = types.ModuleType("streamlit")

        def cache_data_stub(*_args, **_kwargs):
            def decorator(func):
                return func

            return decorator

        streamlit_stub.cache_data = cache_data_stub
        streamlit_stub.cache_resource = cache_data_stub
        streamlit_stub.error = lambda *_args, **_kwargs: None
        streamlit_stub.warning = lambda *_args, **_kwargs: None
        streamlit_stub.markdown = lambda *_args, **_kwargs: None
        streamlit_stub.write = lambda *_args, **_kwargs: None
        streamlit_stub.caption = lambda *_args, **_kwargs: None
        streamlit_stub.stop = lambda *_args, **_kwargs: None
        sys.modules["streamlit"] = streamlit_stub
        sys.modules["streamlit.components"] = types.ModuleType("streamlit.components")
        sys.modules["streamlit.components.v1"] = types.ModuleType("streamlit.components.v1")
    from app import build_log_csv_duplicate_summary_fingerprint

    legacy_summary = """특이사항: 올림포스 가져와서 숙제로 나감

진도 (대수 APEX) : 30차시, 31차시, 32차시

숙제 :
교재 / 이번 숙제 / 진행률 / 코멘트 / 다음숙제
트레이닝팩 / / / 사인코사인 2개
올림포스 / / 100% / / p.86
"""
    current_summary = """진도(대수 APEX): 30차시, 31차시, 32차시

상담 참고사항
올림포스 가져와서 숙제로 나감

숙제:
- 올림포스: 진행률 100%, 다음 숙제 p.86
- 트레이닝팩: 다음 숙제 사인코사인 2개
"""
    different_summary = current_summary.replace("32차시", "33차시")

    legacy_fingerprint = build_log_csv_duplicate_summary_fingerprint(legacy_summary)
    current_fingerprint = build_log_csv_duplicate_summary_fingerprint(current_summary)
    different_fingerprint = build_log_csv_duplicate_summary_fingerprint(different_summary)

    assert legacy_fingerprint == current_fingerprint, (legacy_fingerprint, current_fingerprint)
    assert legacy_fingerprint != different_fingerprint, different_fingerprint


def check_apps_script_same_date_replace_rules_present() -> None:
    script_text = (ROOT_DIR / "scripts" / "google_apps_script_doPost.js").read_text(encoding="utf-8")
    match_body = script_text[
        script_text.index("function findExistingCounselSummary_") : script_text.index("function findCounselHeader_")
    ]
    assert "updated_existing_same_date" in script_text
    assert 'duplicateReason: "same_date_replaced"' in match_body
    assert 'action: "update_existing"' in match_body
    assert 'duplicateReason: "content"' in match_body
    assert "normalizeCounselSummaryForExactMatch_" in match_body
    assert "sameDateCandidate" in match_body
    assert "progressOnlyCandidates" not in match_body
    assert "formatOnlyCandidates" not in match_body
    assert "unsafeSimilarCandidates" not in match_body
    assert "verifyExistingCounselSummary_" in script_text
    assert "verify_only" in script_text
    assert "verify_existing" in script_text
    assert "found_existing" in script_text
    assert 'duplicate.action !== "update_existing"' in script_text
    assert "existingDetailCell.setText(summary)" in script_text
    assert "if (!expectedDateKey) {\n    return null;\n  }" in script_text
    date_filter_index = match_body.index("if (!rowMatchesCounselDate_(row, dateColIndex, expectedDateKey))")
    exact_duplicate_index = match_body.index('duplicateReason: "content"')
    same_date_replace_index = match_body.index('duplicateReason: "same_date_replaced"')
    assert date_filter_index < exact_duplicate_index
    assert exact_duplicate_index < same_date_replace_index


def check_admin_auto_match_does_not_treat_suneung_teukgang_as_lesson_type() -> None:
    from counsel_modules.admin_utils import auto_select_admin_sid_candidate, find_admin_subject_groups

    assert "특강" not in find_admin_subject_groups("EBS 수능특강 숙제 확인")
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "regular-1",
            "detail": "대수 정규 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "special-1",
            "detail": "대수 특강 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
    ]
    selected_candidate, _reason = auto_select_admin_sid_candidate(
        candidates,
        "월1 EBS 수능특강 숙제 확인",
    )
    assert selected_candidate is None, selected_candidate


def check_admin_auto_match_selects_unique_roster_subject_schedule_match() -> None:
    from counsel_modules.admin_utils import auto_select_admin_sid_candidate

    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "regular-daesu",
            "detail": "대수 정규 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "geometry",
            "detail": "기하 정규 화1",
            "curriculum": "기하",
            "schedule": "화1",
        },
    ]
    selected_candidate, reason = auto_select_admin_sid_candidate(candidates, "월1 대수 수업")
    assert selected_candidate and selected_candidate["admin_sid"] == "regular-daesu", (selected_candidate, reason)
    assert "명단 대조" in reason, reason


def check_admin_auto_match_does_not_use_book_text_as_lesson_type() -> None:
    from counsel_modules.admin_utils import auto_select_admin_sid_candidate

    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "regular-daesu",
            "detail": "대수 정규 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "special-daesu",
            "detail": "대수 특강 화1",
            "curriculum": "대수",
            "schedule": "화1",
        },
    ]
    selected_candidate, reason = auto_select_admin_sid_candidate(candidates, "월1 대수 EBS 수능특강 숙제")
    assert selected_candidate and selected_candidate["admin_sid"] == "regular-daesu", (selected_candidate, reason)

    same_schedule_candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "regular-daesu",
            "detail": "대수 정규 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "special-daesu",
            "detail": "대수 특강 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
    ]
    selected_candidate, reason = auto_select_admin_sid_candidate(
        same_schedule_candidates,
        "월1 대수 EBS 수능특강 숙제",
    )
    assert selected_candidate is None, (selected_candidate, reason)


def check_admin_auto_match_keeps_tie_for_review() -> None:
    from counsel_modules.admin_utils import auto_select_admin_sid_candidate

    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "candidate-a",
            "detail": "대수 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "candidate-b",
            "detail": "대수 월1",
            "curriculum": "대수",
            "schedule": "월1",
        },
    ]
    selected_candidate, _reason = auto_select_admin_sid_candidate(candidates, "월1 대수")
    assert selected_candidate is None, selected_candidate


def check_admin_sid_manual_selection_resolves_final_target() -> None:
    from app import (
        ADMIN_SID_MANUAL_SELECT_PLACEHOLDER,
        find_admin_sid_candidate_by_sid,
        format_admin_sid_candidate_label,
        get_local_admin_sid_override,
        resolve_admin_sid_manual_candidate,
        save_local_admin_sid_override,
    )

    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "candidate-a",
            "detail": "대수 정규 월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "candidate-b",
            "detail": "미적분1 하",
        },
    ]

    no_candidate, was_manual = resolve_admin_sid_manual_candidate(
        candidates,
        ADMIN_SID_MANUAL_SELECT_PLACEHOLDER,
    )
    assert no_candidate is None
    assert was_manual is False

    selected_label = format_admin_sid_candidate_label(candidates[1])
    selected_candidate, was_manual = resolve_admin_sid_manual_candidate(candidates, selected_label)
    assert selected_candidate == candidates[1]
    assert was_manual is True

    stale_candidate, was_manual = resolve_admin_sid_manual_candidate(candidates, "없는 후보")
    assert stale_candidate is None
    assert was_manual is False

    assert find_admin_sid_candidate_by_sid(candidates, "candidate-b") == candidates[1]
    assert find_admin_sid_candidate_by_sid(candidates, "missing") is None

    with tempfile.TemporaryDirectory() as temp_dir:
        override_path = Path(temp_dir) / "local_admin_sid_overrides.json"
        assert save_local_admin_sid_override(
            "테 스트",
            candidates[1],
            selected_label,
            path=override_path,
        )
        override = get_local_admin_sid_override("테스트", path=override_path)
        assert override["selected_admin_sid"] == "candidate-b"
        assert find_admin_sid_candidate_by_sid(candidates, override["selected_admin_sid"]) == candidates[1]
        missing_current_candidate = find_admin_sid_candidate_by_sid(
            [candidates[0]],
            override["selected_admin_sid"],
        )
        assert missing_current_candidate is None


def check_admin_auto_match_allows_only_single_or_explicit_sid() -> None:
    from counsel_modules.admin_utils import auto_select_admin_sid_candidate

    single_candidate = [{"student_name": "테스트", "admin_sid": "only-sid", "detail": "대수 월1"}]
    selected_candidate, reason = auto_select_admin_sid_candidate(single_candidate, "월1 대수")
    assert selected_candidate == single_candidate[0], (selected_candidate, reason)

    candidates = [
        {"student_name": "테스트", "admin_sid": "sid-a", "detail": "대수 월1"},
        {"student_name": "테스트", "admin_sid": "sid-b", "detail": "기하 월1"},
    ]
    selected_candidate, reason = auto_select_admin_sid_candidate(candidates, "대수")
    assert selected_candidate is None, (selected_candidate, reason)

    selected_candidate, reason = auto_select_admin_sid_candidate(candidates, "월1")
    assert selected_candidate is None, (selected_candidate, reason)

    selected_candidate, reason = auto_select_admin_sid_candidate(
        candidates,
        "selected_admin_sid: sid-b",
    )
    assert selected_candidate == candidates[1], (selected_candidate, reason)


def check_admin_candidate_label_includes_real_disambiguators() -> None:
    from app import admin_student_detail_from_row, format_admin_sid_candidate_label

    row = {
        "name": "테스트",
        "sid": "sid-1",
        "curriculum": "미적분1",
        "subCurriculum": "하",
        "level": "고2",
        "day1": "월",
        "visitTime1": "18:00",
    }
    detail = admin_student_detail_from_row(row)
    assert_contains(detail, "미적분1")
    assert_contains(detail, "하")
    assert_contains(detail, "고2")
    assert_contains(detail, "월")
    assert_contains(detail, "18:00")

    label = format_admin_sid_candidate_label(
        {
            "student_name": row["name"],
            "admin_sid": row["sid"],
            "detail": detail,
        }
    )
    assert_contains(label, "테스트")
    assert_contains(label, "sid-1")
    assert_contains(label, "미적분1")
    assert_contains(label, "18:00")


def check_admin_candidate_label_hides_internal_display_detail() -> None:
    from app import format_admin_sid_candidate_label, public_admin_sid_candidate_detail

    manual_candidate = {
        "student_name": "테스트",
        "admin_sid": "sid-1",
        "detail": "수동 매핑",
        "source": "CSV",
    }
    label = format_admin_sid_candidate_label(manual_candidate)
    assert_contains(label, "테스트")
    assert_contains(label, "sid-1")
    assert_not_contains(label, "수동 매핑")
    assert public_admin_sid_candidate_detail(manual_candidate) == ""

    target_parts = [
        part
        for part in [
            manual_candidate["admin_sid"],
            public_admin_sid_candidate_detail(manual_candidate),
        ]
        if part
    ]
    assert " · ".join(target_parts) == "sid-1"

    real_detail_candidate = {
        "student_name": "테스트",
        "admin_sid": "sid-2",
        "detail": "미적분1 · 하 · 월 18:00",
    }
    real_label = format_admin_sid_candidate_label(real_detail_candidate)
    assert_contains(real_label, "미적분1")
    assert_contains(real_label, "18:00")


def check_log_csv_admin_match_selects_single_weekday_candidate() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "monday-daesu",
            "curriculum": "대수",
            "schedule": "월1",
        }
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert result["match_confidence"] == "auto", result
    assert result["weekday_candidate_count"] == 1, result


def check_log_csv_admin_match_prefers_csv_date_weekday() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "monday-daesu",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "wednesday-daesu",
            "curriculum": "대수",
            "schedule": "수1",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert "월1" in result["candidate_preview"], result


def check_log_csv_admin_match_prefers_time_when_weekday_ties() -> None:
    from app import infer_admin_subject_for_log_row

    row = {
        "date": "2026-05-18",
        "name": "테스트",
        "curriculum": "대수",
        "time": "18:00",
    }
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "monday-1800",
            "curriculum": "대수",
            "schedule": "월1",
            "time": "18:00",
        },
        {
            "student_name": "테스트",
            "admin_sid": "monday-1900",
            "curriculum": "대수",
            "schedule": "월1",
            "time": "19:00",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert "18:00" in result["candidate_preview"], result
    assert "time_match" in result["match_reason"], result


def check_log_csv_admin_match_uses_day1_visit_time1_fields() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수", "time": "18:00"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "day1-daesu",
            "curriculum": "대수",
            "day1": "M1",
            "visitTime1": "18:00",
        }
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert result["weekday_candidate_count"] == 1, result
    assert "day_index_match:day1" in result["match_reason"], result
    assert "visit_time_match:visitTime1" in result["match_reason"], result


def check_log_csv_admin_match_uses_day2_field() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-22", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "day2-daesu",
            "curriculum": "대수",
            "day1": "W1",
            "visitTime1": "18:00",
            "day2": "F1",
            "visitTime2": "19:00",
        }
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert "day_index_match:day2" in result["match_reason"], result


def check_log_csv_admin_match_prefers_matching_visit_time_when_day_ties() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수", "time": "18:00"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "day1-1800",
            "curriculum": "대수",
            "day1": "M1",
            "visitTime1": "18:00",
        },
        {
            "student_name": "테스트",
            "admin_sid": "day1-1900",
            "curriculum": "대수",
            "day1": "M1",
            "visitTime1": "19:00",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert "18:00" in result["candidate_preview"], result
    assert "visit_time_match:visitTime1" in result["match_reason"], result


def check_log_csv_admin_match_filters_to_matching_visit_time_before_subject_score() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수", "time": "18:00"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "subject-only-wrong-time",
            "curriculum": "대수",
            "day1": "M1",
            "visitTime1": "20:00",
        },
        {
            "student_name": "테스트",
            "admin_sid": "time-match",
            "curriculum": "기하",
            "day1": "M1",
            "visitTime1": "18:00",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert "18:00" in result["candidate_preview"], result
    assert "20:00" not in result["candidate_preview"], result
    assert "visit_time_match:visitTime1" in result["match_reason"], result


def check_log_csv_admin_match_uses_sub_curriculum_subject() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "확통"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "sub-curriculum",
            "curriculum": "대수",
            "subCurriculum": "확통",
            "day1": "M1",
            "visitTime1": "18:00",
        }
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="확통")
    assert result["status"] == "매칭 성공", result
    assert result["subject"] == "확통", result
    assert "sub_curriculum_match" in result["match_reason"], result


def check_log_csv_explicit_subject_overrides_admin_curriculum_with_sub_curriculum() -> None:
    from app import build_applied_subject_info, csv_subject_from_log_row, infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "과목": "확통", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "sub-curriculum",
            "curriculum": "대수",
            "subCurriculum": "확통",
            "day1": "M1",
            "visitTime1": "18:00",
        }
    ]
    subject_hint = str(csv_subject_from_log_row(row).get("subject") or "")
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint=subject_hint)
    applied = build_applied_subject_info(row, result)
    assert result["status"] == "매칭 성공", result
    assert result["sub_curriculum_match"] is True, result
    assert applied["applied_subject"] == "확통", applied
    assert applied["selected_subject_source"] == "csv_explicit", applied
    assert applied["selected_by_csv_subject"] is True, applied
    assert applied["subject_conflict"] is True, applied


def check_log_csv_explicit_subject_kept_when_admin_sub_curriculum_missing() -> None:
    from app import build_applied_subject_info, csv_subject_from_log_row, infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "최종 적용 과목": "확통"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "default-daesu",
            "curriculum": "대수",
            "day1": "M1",
        }
    ]
    subject_hint = str(csv_subject_from_log_row(row).get("subject") or "")
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint=subject_hint)
    applied = build_applied_subject_info(row, result)
    assert applied["applied_subject"] == "확통", applied
    assert applied["selected_subject_source"] == "csv_explicit", applied
    assert applied["subject_conflict"] is True, applied


def check_log_csv_course_subject_precedes_admin_curriculum() -> None:
    from app import build_applied_subject_info, csv_subject_from_log_row, infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "course": "확통", "curriculum": "대수"}
    candidates = [{"student_name": "테스트", "admin_sid": "default-daesu", "curriculum": "대수", "day1": "M1"}]
    subject_hint = str(csv_subject_from_log_row(row).get("subject") or "")
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint=subject_hint)
    applied = build_applied_subject_info(row, result)
    assert subject_hint == "확통", subject_hint
    assert applied["applied_subject"] == "확통", applied
    assert applied["selected_subject_source"] == "csv_explicit", applied


def check_log_csv_matching_curriculum_kept_over_other_sub_curriculum() -> None:
    from app import build_applied_subject_info, csv_subject_from_log_row, infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "과목": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "daesu-main",
            "curriculum": "대수",
            "subCurriculum": "확통",
            "day1": "M1",
        }
    ]
    subject_hint = str(csv_subject_from_log_row(row).get("subject") or "")
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint=subject_hint)
    applied = build_applied_subject_info(row, result)
    assert applied["applied_subject"] == "대수", applied
    assert applied["curriculum_match"] is True, applied


def check_log_csv_suneung_textbook_does_not_change_subject_or_lesson_type() -> None:
    from app import build_applied_subject_info, csv_subject_from_log_row, infer_admin_subject_for_log_row, infer_lesson_type_from_log_row

    row = {"date": "2026-05-18", "name": "테스트", "과목": "확통", "notes": "EBS 수능특강 숙제"}
    candidates = [{"student_name": "테스트", "admin_sid": "stat", "curriculum": "확통", "day1": "M1"}]
    subject_hint = str(csv_subject_from_log_row(row).get("subject") or "")
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint=subject_hint)
    applied = build_applied_subject_info(row, result)
    lesson_type = infer_lesson_type_from_log_row(row)
    assert applied["applied_subject"] == "확통", applied
    assert lesson_type["lesson_type"] == "미확인", lesson_type


def check_log_csv_explicit_special_type_stays_separate_from_subject() -> None:
    from app import build_applied_subject_info, csv_subject_from_log_row, infer_admin_subject_for_log_row, infer_lesson_type_from_log_row

    row = {"date": "2026-05-18", "name": "테스트", "과목": "확통", "class_type": "특강"}
    candidates = [{"student_name": "테스트", "admin_sid": "stat", "curriculum": "확통", "day1": "M1"}]
    subject_hint = str(csv_subject_from_log_row(row).get("subject") or "")
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint=subject_hint)
    applied = build_applied_subject_info(row, result)
    lesson_type = infer_lesson_type_from_log_row(row)
    assert applied["applied_subject"] == "확통", applied
    assert lesson_type["lesson_type"] == "특강", lesson_type


def check_log_csv_csv_subject_wins_between_same_time_candidates() -> None:
    from app import build_applied_subject_info, csv_subject_from_log_row, infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "과목": "확통", "time": "18:00"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "daesu",
            "curriculum": "대수",
            "day1": "M1",
            "visitTime1": "18:00",
        },
        {
            "student_name": "테스트",
            "admin_sid": "stat",
            "curriculum": "확통",
            "day1": "M1",
            "visitTime1": "18:00",
        },
    ]
    subject_hint = str(csv_subject_from_log_row(row).get("subject") or "")
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint=subject_hint)
    applied = build_applied_subject_info(row, result)
    assert result["status"] == "매칭 성공", result
    assert result["subject"] == "확통", result
    assert applied["applied_subject"] == "확통", applied
    assert "csv_subject_match" in result["match_reason"], result


def check_log_csv_admin_match_does_not_infer_lesson_type_without_explicit_field() -> None:
    from app import admin_lesson_type_from_candidate, infer_lesson_type_from_log_row

    row_result = infer_lesson_type_from_log_row({"program": "EBS 수능특강", "notes": "수특 숙제"})
    assert row_result["lesson_type"] == "미확인", row_result
    program_result = infer_lesson_type_from_log_row({"program": "여름 특강", "notes": "보강 안내"})
    assert program_result["lesson_type"] == "미확인", program_result
    generic_type_result = infer_lesson_type_from_log_row({"type": "특강", "category": "정규"})
    assert generic_type_result["lesson_type"] == "미확인", generic_type_result
    admin_result = admin_lesson_type_from_candidate(
        {
            "student_name": "테스트",
            "admin_sid": "book-only",
            "curriculum": "대수",
            "subBook1": "EBS 수능특강",
            "day1": "M1",
        }
    )
    assert admin_result["lesson_type"] == "미확인", admin_result
    admin_program_result = admin_lesson_type_from_candidate(
        {
            "student_name": "테스트",
            "admin_sid": "program-only",
            "curriculum": "대수",
            "program": "여름 특강",
            "day1": "M1",
        }
    )
    assert admin_program_result["lesson_type"] == "미확인", admin_program_result


def check_log_csv_admin_match_falls_back_when_day_code_unparseable() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "unparseable-day",
            "curriculum": "대수",
            "day1": "A1",
            "visitTime1": "18:00",
        }
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert result["subject"] == "대수", result
    assert "weekday_parse_failed" in result["match_reason"], result


def check_log_csv_admin_match_prefers_actual_admin_row_subject() -> None:
    from app import build_applied_subject_info, infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "default-daesu",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "actual-stat",
            "curriculum": "확통",
            "schedule": "수1",
            "date": "2026-05-18",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="")
    assert result["status"] == "매칭 성공", result
    assert result["subject"] == "확통", result
    assert result["actual_date_candidate_count"] == 1, result
    assert "actual_date_match" in result["match_reason"], result
    applied = build_applied_subject_info(row, result)
    assert applied["applied_subject"] == "확통", applied
    assert applied["applied_source"] == "admin 실제 수업일 매칭", applied


def check_log_csv_admin_match_prefers_actual_admin_row_lesson_type() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수", "class_type": "정규"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "default-regular",
            "curriculum": "대수",
            "schedule": "월1",
            "class_type": "정규",
        },
        {
            "student_name": "테스트",
            "admin_sid": "actual-special",
            "curriculum": "대수",
            "schedule": "월2",
            "class_type": "특강",
            "date": "2026-05-18",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert result["matched_class_type"] == "특강", result
    assert result["actual_date_candidate_count"] == 1, result


def check_log_csv_admin_match_prefers_actual_admin_row_over_default_weekday() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "default-monday",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "actual-makeup",
            "curriculum": "기하",
            "schedule": "수1",
            "date": "2026-05-18",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert result["subject"] == "기하", result
    assert "actual_date_match" in result["match_reason"], result


def check_log_csv_admin_match_prefers_actual_admin_sid_when_same_date_multiple() -> None:
    from app import infer_admin_subject_for_log_row

    row = {
        "date": "2026-05-18",
        "name": "테스트",
        "curriculum": "대수",
        "admin_sid": "actual-geometry",
    }
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "actual-daesu",
            "curriculum": "대수",
            "schedule": "월1",
            "date": "2026-05-18",
        },
        {
            "student_name": "테스트",
            "admin_sid": "actual-geometry",
            "curriculum": "기하",
            "schedule": "월2",
            "date": "2026-05-18",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert result["subject"] == "기하", result
    assert "explicit_admin_sid" in result["match_reason"], result


def check_log_csv_admin_match_keeps_same_date_tie_for_review() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "actual-a",
            "curriculum": "대수",
            "schedule": "월1",
            "date": "2026-05-18",
        },
        {
            "student_name": "테스트",
            "admin_sid": "actual-b",
            "curriculum": "대수",
            "schedule": "월1",
            "date": "2026-05-18",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "같은 날짜 후보 여러 개", result
    assert result["match_needs_review"] is True, result
    assert result["actual_date_candidate_count"] == 2, result


def check_log_csv_lesson_type_does_not_use_suneung_teukgang_textbook() -> None:
    from app import infer_lesson_type_from_log_row

    row = {
        "class_type": "정규",
        "program": "EBS 수능특강",
        "notes": "수능특강 숙제 확인",
    }
    result = infer_lesson_type_from_log_row(row)
    assert result["lesson_type"] == "정규강의", result


def check_log_csv_lesson_type_accepts_explicit_special_class() -> None:
    from app import infer_lesson_type_from_log_row

    result = infer_lesson_type_from_log_row({"class_type": "특강"})
    assert result["lesson_type"] == "특강", result


def check_log_csv_admin_match_falls_back_when_date_weekday_unavailable() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "not-a-date", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "daesu",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "geometry",
            "curriculum": "기하",
            "schedule": "수1",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "매칭 성공", result
    assert result["subject"] == "대수", result


def check_log_csv_admin_match_keeps_top_score_tie_for_review() -> None:
    from app import infer_admin_subject_for_log_row

    row = {"date": "2026-05-18", "name": "테스트", "curriculum": "대수"}
    candidates = [
        {
            "student_name": "테스트",
            "admin_sid": "candidate-a",
            "curriculum": "대수",
            "schedule": "월1",
        },
        {
            "student_name": "테스트",
            "admin_sid": "candidate-b",
            "curriculum": "대수",
            "schedule": "월1",
        },
    ]
    result = infer_admin_subject_for_log_row(row, candidates, subject_hint="대수")
    assert result["status"] == "후보 여러 개", result
    assert result["match_needs_review"] is True, result


def check_prompt_latex_math_rules() -> None:
    prompt_text = (ROOT_DIR / "prompts" / "summary_ko.txt").read_text(encoding="utf-8")
    assert r"\(\frac{1}{2}\)" in prompt_text
    assert r"\(\frac{x+1}{x-2}\)" in prompt_text
    assert r"\(\sqrt{x}\)" in prompt_text
    assert "2026/05/15" in prompt_text
    assert "https://..." in prompt_text
    assert "C:/Users/..." in prompt_text


def check_consumed_admin_notes_fail_open_on_broken_json() -> None:
    from counsel_modules.local_consumed_admin_notes import filter_consumed_admin_notes

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        registry_path.write_text("{broken json", encoding="utf-8")
        notes = ["반복 특이사항"]
        result = filter_consumed_admin_notes("학생A", "sid-a", notes, registry_path=registry_path)
        assert result["filtered_notes"] == notes
        assert result["removed_notes"] == []


def check_log_csv_consumed_filter_reuses_single_registry_load() -> None:
    import app

    shared_registry = {"items": []}
    load_count = 0
    received_registries = []
    received_dates = []
    original_loader = app.load_consumed_admin_notes
    original_filter = app.filter_consumed_admin_notes

    def fake_loader():
        nonlocal load_count
        load_count += 1
        return shared_registry

    def fake_filter(
        student_name,
        admin_sid,
        notes,
        *,
        enabled,
        registry=None,
        counseling_date=None,
    ):
        del student_name, admin_sid, enabled
        received_registries.append(registry)
        received_dates.append(counseling_date)
        return {
            "filtered_notes": notes,
            "removed_notes": [],
            "diagnostic": {"failed_open": False},
        }

    try:
        app.load_consumed_admin_notes = fake_loader
        app.filter_consumed_admin_notes = fake_filter
        app.filter_consumed_admin_notes_from_log_rows(
            [
                {"date": "2026-08-23", "name": "학생A", "sid": "sid-a", "notes": "참고 A"},
                {"date": "2026-08-24", "name": "학생B", "sid": "sid-b", "notes": "참고 B"},
            ],
            enabled=True,
        )
    finally:
        app.load_consumed_admin_notes = original_loader
        app.filter_consumed_admin_notes = original_filter

    assert load_count == 1, load_count
    assert received_registries == [shared_registry, shared_registry], received_registries
    assert received_dates == ["2026-08-23", "2026-08-24"], received_dates


def check_log_csv_auto_import_finds_only_new_completed_download() -> None:
    import os
    import time

    from app import LocalLogCsvUpload, find_latest_completed_log_csv

    now_ns = time.time_ns()
    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        stable = root / "수업기록_선택일_2026-08-23 (2).csv"
        stable.write_text("date,name,notes\n2026-08-23,학생A,참고\n", encoding="utf-8-sig")
        os.utime(stable, ns=(now_ns - 2_000_000_000, now_ns - 2_000_000_000))

        fresh = root / "수업기록_완료미정리_2026-08-23.csv"
        fresh.write_text("date,name,notes\n2026-08-23,학생B,참고\n", encoding="utf-8-sig")
        os.utime(fresh, ns=(now_ns - 100_000_000, now_ns - 100_000_000))

        stale = root / "수업기록_선택일_2026-08-22.csv"
        stale.write_text("date,name,notes\n2026-08-22,학생C,참고\n", encoding="utf-8-sig")
        os.utime(stale, ns=(now_ns - 20_000_000_000, now_ns - 20_000_000_000))

        unrelated = root / "다른파일.csv"
        unrelated.write_text("date,name,notes\n", encoding="utf-8-sig")
        os.utime(unrelated, ns=(now_ns - 2_000_000_000, now_ns - 2_000_000_000))

        selected = find_latest_completed_log_csv(
            root,
            newer_than_ns=now_ns - 10_000_000_000,
            now_ns=now_ns,
        )
        assert selected == stable, selected

        upload = LocalLogCsvUpload(stable)
        assert upload.name == stable.name
        assert upload.size == stable.stat().st_size
        assert upload.getvalue() == stable.read_bytes()


def check_log_csv_auto_import_requests_one_shot_docs_export() -> None:
    from app import log_csv_auto_export_token, should_auto_export_log_csv

    sample_path = Path(r"C:\Users\tester\Downloads\수업기록_선택일_2026-08-24.csv")
    first_token = log_csv_auto_export_token(sample_path, 123)
    assert first_token == log_csv_auto_export_token(sample_path, 123)
    assert first_token != log_csv_auto_export_token(sample_path, 124)
    auto_export_args = {
        "current_token": first_token,
        "pending_token": first_token,
        "started_token": "",
        "selected_count": 3,
        "has_web_app_url": True,
        "is_saving": False,
    }
    assert should_auto_export_log_csv(**auto_export_args) is True
    assert should_auto_export_log_csv(**{**auto_export_args, "current_token": ""}) is False
    assert should_auto_export_log_csv(**{**auto_export_args, "pending_token": "other"}) is False
    assert should_auto_export_log_csv(**{**auto_export_args, "started_token": first_token}) is False
    assert should_auto_export_log_csv(**{**auto_export_args, "selected_count": 0}) is False
    assert should_auto_export_log_csv(**{**auto_export_args, "has_web_app_url": False}) is False
    assert should_auto_export_log_csv(**{**auto_export_args, "is_saving": True}) is False

    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    watcher_body = _function_body(app_text, "render_log_csv_auto_import_watcher")
    preview_body = _function_body(app_text, "render_log_csv_to_docs_preview_ui")
    assert 'st.session_state["log_csv_auto_export_pending_token"]' in watcher_body
    assert 'st.session_state["log_csv_auto_export_started_token"]' in preview_body
    assert 'st.session_state["log_csv_auto_export_pending_token"] = ""' in preview_body
    assert "auto_export_requested" in preview_body
    assert "save_button_clicked or retry_failed_pending or auto_export_requested" in preview_body


def check_consumed_admin_registry_diagnostics_and_reset_backup() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        diagnose_consumed_admin_notes,
        load_consumed_admin_notes,
        mark_admin_notes_consumed,
        reset_consumed_admin_notes,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        note = "정상 registry 진단용 특이사항"
        mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [note],
            "added",
            final_text=f"상담 참고사항\n- {note}",
            registry_path=registry_path,
        )
        diagnostic = diagnose_consumed_admin_notes(registry_path)
        reset = reset_consumed_admin_notes(registry_path)
        registry = load_consumed_admin_notes(registry_path)

        assert diagnostic["load_ok"] is True
        assert diagnostic["item_count"] == 1
        assert reset["ok"] is True
        assert reset.get("backup_path")
        assert Path(reset["backup_path"]).exists()
        assert registry["items"] == []


def check_consumed_admin_registry_broken_json_diagnostic() -> None:
    from counsel_modules.local_consumed_admin_notes import diagnose_consumed_admin_notes, filter_consumed_admin_notes

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        registry_path.write_text("{broken json", encoding="utf-8")
        notes = ["깨진 registry fail-open 확인"]
        diagnostic = diagnose_consumed_admin_notes(registry_path)
        filtered = filter_consumed_admin_notes("학생A", "sid-a", notes, registry_path=registry_path)

        assert diagnostic["load_ok"] is False
        assert "load_error" in diagnostic
        assert filtered["filtered_notes"] == notes
        assert filtered["removed_notes"] == []


def check_app_health_helpers() -> None:
    from scripts.check_app_health import (
        REQUIRED_FILES,
        check_apps_script_url,
        check_consumed_registry,
        check_google_docs_map,
        check_required_files,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        root = Path(temp_dir)
        for relative_path in REQUIRED_FILES:
            path = root / relative_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("", encoding="utf-8")
        (root / "counsel_modules").mkdir(parents=True, exist_ok=True)
        assert check_required_files(root)[0].status == "PASS"

        map_path = root / "data" / "students" / "google_docs_map.csv"
        map_path.parent.mkdir(parents=True, exist_ok=True)
        map_path.write_text("student_name,doc_url\n학생A,\n", encoding="utf-8")
        map_result = check_google_docs_map(root)[0]
        assert map_result.status == "WARN"
        assert "rows missing doc_url/doc_id" in map_result.description

        map_path.write_text("student_name\n학생A\n", encoding="utf-8")
        assert check_google_docs_map(root)[0].status == "FAIL"

        registry_path = root / "data" / "local_consumed_admin_notes.json"
        registry_path.write_text("{broken json", encoding="utf-8")
        registry_result = check_consumed_registry(root)[0]
        assert registry_result.status == "WARN"

        registry_path.unlink()
        assert check_consumed_registry(root)[0].status == "PASS"

        url_result = check_apps_script_url(root)[0]
        assert url_result.status == "WARN"


def check_consumed_admin_notes_filters_same_student_only() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_notes,
        mark_admin_notes_consumed,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        note = "APEX 26차시 백지리뷰 제출"
        mark = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [note],
            "added",
            final_text=f"상담 참고사항\n- {note}",
            registry_path=registry_path,
        )
        assert mark["marked_count"] == 1
        same_student = filter_consumed_admin_notes("학생A", "sid-a", [note], registry_path=registry_path)
        other_student = filter_consumed_admin_notes("학생B", "sid-b", [note], registry_path=registry_path)
        assert same_student["filtered_notes"] == []
        assert same_student["removed_notes"] == [note]
        assert other_student["filtered_notes"] == [note]
        assert other_student["removed_notes"] == []


def check_consumed_admin_notes_are_scoped_by_counseling_date() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_sections_from_docs_text,
        filter_consumed_admin_notes,
        load_consumed_admin_notes,
        mark_admin_notes_consumed,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        note = "날짜가 다르면 다시 저장할 상담 참고사항"
        first_mark = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [note],
            "added",
            final_text=f"상담 참고사항\n- {note}",
            registry_path=registry_path,
            counseling_date="2026-08-23",
        )
        same_date = filter_consumed_admin_notes(
            "학생A",
            "sid-a",
            [note],
            registry_path=registry_path,
            counseling_date="2026-08-23",
        )
        different_date = filter_consumed_admin_notes(
            "학생A",
            "sid-a",
            [note],
            registry_path=registry_path,
            counseling_date="2026-08-24",
        )
        docs_text = f"상담 참고사항\n- {note}"
        same_date_docs = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            docs_text,
            admin_source_notes=note,
            registry_path=registry_path,
            counseling_date="2026-08-23",
        )
        different_date_docs = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            docs_text,
            admin_source_notes=note,
            registry_path=registry_path,
            counseling_date="2026-08-24",
        )
        second_mark = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [note],
            "added",
            final_text=f"상담 참고사항\n- {note}",
            registry_path=registry_path,
            counseling_date="2026-08-24",
        )
        registry = load_consumed_admin_notes(registry_path)

    assert first_mark["marked_count"] == 1
    assert same_date["filtered_notes"] == []
    assert same_date["removed_notes"] == [note]
    assert different_date["filtered_notes"] == [note]
    assert different_date["removed_notes"] == []
    assert note not in same_date_docs["filtered_text"]
    assert note in different_date_docs["filtered_text"]
    assert second_mark["marked_count"] == 1
    assert [item.get("counseling_date") for item in registry["items"]] == [
        "2026-08-23",
        "2026-08-24",
    ]
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    row_filter_body = _function_body(app_text, "filter_consumed_admin_notes_from_log_rows")
    mark_body = _function_body(app_text, "mark_consumed_admin_notes_for_saved_row")
    preview_body = _function_body(app_text, "prepare_log_csv_preview_for_google_docs")
    assert 'counseling_date=row_copy.get("date")' in row_filter_body
    assert 'counseling_date=row.get("date")' in mark_body
    assert 'counseling_date=row.get("date")' in preview_body


def check_consumed_admin_notes_context_and_disabled_behaviour() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_notes,
        mark_admin_notes_consumed,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        note = "트레이닝팩 p.42 풀이 흔적 확인"
        mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [note],
            "updated_existing",
            final_text=f"상담 참고사항\n- {note}",
            registry_path=registry_path,
        )
        preview_result = filter_consumed_admin_notes("학생A", "sid-a", [note], registry_path=registry_path)
        prompt_result = filter_consumed_admin_notes("학생A", "sid-a", [note], registry_path=registry_path)
        disabled_result = filter_consumed_admin_notes(
            "학생A",
            "sid-a",
            [note],
            enabled=False,
            registry_path=registry_path,
        )
        transcript_text = f"오늘 새로 말한 내용: {note}"
        assert preview_result["filtered_notes"] == []
        assert prompt_result["filtered_notes"] == []
        assert disabled_result["filtered_notes"] == [note]
        assert note in transcript_text


def check_consumed_admin_notes_mark_success_and_skip_timeout() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_notes,
        mark_admin_notes_consumed,
    )

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        success_note = "올포유 숙제 범위 확인"
        timeout_note = "시간초과 때는 저장하지 않을 특이사항"
        success = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [success_note],
            "saved_confirmed_after_timeout",
            final_text=f"상담 참고사항\n- {success_note}",
            registry_path=registry_path,
        )
        timeout = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [timeout_note],
            "timeout_unknown",
            final_text=f"상담 참고사항\n- {timeout_note}",
            registry_path=registry_path,
        )
        unsafe = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            ["유사 기록 확인 필요 특이사항"],
            "unsafe_similar_record",
            final_text="유사 기록 확인 필요 특이사항",
            registry_path=registry_path,
        )
        filtered = filter_consumed_admin_notes(
            "학생A",
            "sid-a",
            [success_note, timeout_note, "유사 기록 확인 필요 특이사항"],
            registry_path=registry_path,
        )
        assert success["marked_count"] == 1
        assert timeout["marked_count"] == 0
        assert unsafe["marked_count"] == 0
        assert filtered["filtered_notes"] == [timeout_note, "유사 기록 확인 필요 특이사항"]
        assert filtered["removed_notes"] == [success_note]


def check_consumed_admin_notes_mark_save_failure_fail_open() -> None:
    from counsel_modules.local_consumed_admin_notes import mark_admin_notes_consumed

    with tempfile.TemporaryDirectory() as temp_dir:
        directory_path = Path(temp_dir)
        result = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            ["저장 실패에도 앱 저장 결과를 깨지 않을 특이사항"],
            "added",
            final_text="저장 실패에도 앱 저장 결과를 깨지 않을 특이사항",
            registry_path=directory_path,
        )
        assert result["ok"] is False
        assert result["marked_count"] == 0


def check_consumed_admin_docs_filter_removes_today_and_notes_keeps_progress_homework() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_sections_from_docs_text,
        mark_admin_notes_consumed,
    )

    today_note = "개념원리 또는 트레이닝팩 중 하나라도 풀어온 풀이 흔적 확인"
    counsel_note = "최근 성적표/시험 결과가 예상보다 나쁘지 않게 나와 수시를 계속 챙기는 방향으로 상담함."
    docs_text = f"""진도(대수 APEX): 42차시, 43차시

[오늘 확인할 것]
수업 전 확인
- {today_note}

상담 참고사항
- {counsel_note}

숙제:
- 마플: p.268
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [today_note, counsel_note],
            "added",
            final_text=f"{today_note}\n{counsel_note}",
            registry_path=registry_path,
        )
        result = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            docs_text,
            admin_source_notes=f"{today_note}\n{counsel_note}",
            registry_path=registry_path,
        )

    filtered_text = result["filtered_text"]
    assert_not_contains(filtered_text, "[오늘 확인할 것]")
    assert_not_contains(filtered_text, "상담 참고사항")
    assert_contains(filtered_text, "진도(대수 APEX): 42차시, 43차시")
    assert filtered_text.endswith("숙제:\n- 마플: p.268"), filtered_text
    assert result["diagnostic"]["removed_count"] == 2


def check_consumed_admin_docs_filter_keeps_transcript_source() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_sections_from_docs_text,
        mark_admin_notes_consumed,
        normalize_admin_note_for_hash,
    )

    today_note = "개념원리 또는 트레이닝팩 중 하나라도 풀어온 풀이 흔적 확인"
    docs_text = f"""진도(대수 APEX): 42차시

[오늘 확인할 것]
수업 전 확인
- {today_note}

숙제:
- 마플: p.268
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [today_note],
            "added",
            final_text=today_note,
            registry_path=registry_path,
        )
        result = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            docs_text,
            admin_source_notes=today_note,
            source_by_line={normalize_admin_note_for_hash(today_note): "transcript"},
            registry_path=registry_path,
        )

    assert_contains(result["filtered_text"], today_note)
    assert result["removed_notes"] == []


def check_consumed_admin_docs_filter_never_removes_progress_or_homework() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_sections_from_docs_text,
        mark_admin_notes_consumed,
    )

    progress_note = "진도(대수 APEX): 42차시, 43차시"
    homework_note = "마플: p.268"
    docs_text = f"""{progress_note}

숙제:
- {homework_note}
"""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [progress_note, homework_note],
            "added",
            final_text=f"{progress_note}\n{homework_note}",
            registry_path=registry_path,
        )
        result = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            docs_text,
            admin_source_notes=f"{progress_note}\n{homework_note}",
            registry_path=registry_path,
        )

    assert_contains(result["filtered_text"], progress_note)
    assert_contains(result["filtered_text"], homework_note)
    assert result["removed_notes"] == []


def check_consumed_admin_filter_removes_repeated_test_assignment_section() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_notes,
        filter_consumed_admin_sections_from_docs_text,
        mark_admin_notes_consumed,
    )

    test_assignment = """[테스트 배정]
- 단원평가 / 기하 / Lv.3 / 1회차: 공간에서 점의 좌표와 내분점 Lv.3
- 단원평가 / 기하 / Lv.3 / 1회차: 구의 방정식 Lv.3"""
    repeated_text = f"""상담 참고사항
{test_assignment}
{test_assignment}

숙제:
- 교재: 프린트
- 다음 숙제: 풀기"""
    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        mark_result = mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            test_assignment,
            "added",
            final_text=test_assignment,
            registry_path=registry_path,
        )
        row_filter = filter_consumed_admin_notes(
            "학생A",
            "sid-a",
            test_assignment,
            registry_path=registry_path,
        )
        docs_filter = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            repeated_text,
            admin_source_notes=test_assignment,
            registry_path=registry_path,
        )

    assert mark_result["marked_count"] == 2
    assert row_filter["filtered_notes"] == "[테스트 배정]"
    assert row_filter["removed_notes"] == [
        "- 단원평가 / 기하 / Lv.3 / 1회차: 공간에서 점의 좌표와 내분점 Lv.3",
        "- 단원평가 / 기하 / Lv.3 / 1회차: 구의 방정식 Lv.3",
    ]
    assert_not_contains(docs_filter["filtered_text"], "공간에서 점의 좌표와 내분점")
    assert_not_contains(docs_filter["filtered_text"], "구의 방정식")
    assert_contains(docs_filter["filtered_text"], "숙제:")
    assert_contains(docs_filter["filtered_text"], "다음 숙제: 풀기")
    assert docs_filter["diagnostic"]["removed_count"] == 4

    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        repeated_only_filter = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            repeated_text,
            admin_source_notes=test_assignment,
            registry_path=registry_path,
        )

    assert repeated_only_filter["filtered_text"].count("공간에서 점의 좌표와 내분점") == 1
    assert repeated_only_filter["filtered_text"].count("구의 방정식") == 1
    assert repeated_only_filter["diagnostic"]["removed_count"] == 2


def assert_homework_section_is_last(text: str) -> None:
    stripped = str(text or "").strip()
    homework_index = stripped.rfind("숙제:")
    assert homework_index >= 0, stripped
    tail = stripped[homework_index:]
    assert tail.startswith("숙제:"), stripped
    assert not re.search(r"\n\s*(?:진도|\[오늘 확인할 것\]|상담 참고사항)\b", tail), stripped


def check_google_docs_text_golden_policies() -> None:
    from counsel_modules.local_consumed_admin_notes import (
        filter_consumed_admin_sections_from_docs_text,
        mark_admin_notes_consumed,
    )
    from counsel_modules.text_utils import prepare_summary_for_google_docs_cell

    # A. Empty counseling notes are removed, while progress and homework remain.
    result_a = prepare_summary_for_google_docs_cell(
        """진도(대수 APEX): 42차시

상담 참고사항

.

숙제:
- 마플: p.268"""
    )
    assert_not_contains(result_a, "상담 참고사항")
    assert_not_contains(result_a, "\n.\n")
    assert_contains(result_a, "진도(대수 APEX): 42차시")
    assert_contains(result_a, "숙제:")
    assert_homework_section_is_last(result_a)

    # B. Missing progress does not create a placeholder.
    result_b = prepare_summary_for_google_docs_cell(
        """[오늘 확인할 것]
수업 전 확인
- APEX 42차시 백지리뷰 제출 여부 확인

숙제:
- APEX: 42차시 풀어오기"""
    )
    assert_not_contains(result_b, "진도: 확인 필요")
    assert_contains(result_b, "[오늘 확인할 것]")
    assert_contains(result_b, "APEX 42차시 백지리뷰 제출 여부 확인")
    assert_contains(result_b, "숙제:")
    assert_homework_section_is_last(result_b)

    # C. Missing homework does not create a placeholder.
    result_c = prepare_summary_for_google_docs_cell(
        """진도(대수 APEX): 42차시

[오늘 확인할 것]
수업 전 확인
- APEX 42차시 백지리뷰 제출 여부 확인"""
    )
    assert_contains(result_c, "진도(대수 APEX): 42차시")
    assert_contains(result_c, "[오늘 확인할 것]")
    assert_not_contains(result_c, "숙제:\n- 확인 필요")
    assert_not_contains(result_c, "숙제:")

    # D/G. Consumed ADMIN-derived today/notes can be removed, but progress and homework stay.
    today_note = "consumed 처리된 ADMIN 유래 확인 항목"
    counsel_note = "consumed 처리된 ADMIN 유래 참고사항"
    docs_text = prepare_summary_for_google_docs_cell(
        f"""진도(대수 APEX): 42차시, 43차시

[오늘 확인할 것]
수업 전 확인
- {today_note}

상담 참고사항
- {counsel_note}

숙제:
- 마플: p.268"""
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            [today_note, counsel_note],
            "added",
            final_text=f"{today_note}\n{counsel_note}",
            registry_path=registry_path,
        )
        filtered = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            docs_text,
            admin_source_notes=f"{today_note}\n{counsel_note}",
            registry_path=registry_path,
        )["filtered_text"]
    assert_not_contains(filtered, "[오늘 확인할 것]")
    assert_not_contains(filtered, "상담 참고사항")
    assert_contains(filtered, "진도(대수 APEX): 42차시, 43차시")
    assert_contains(filtered, "숙제:\n- 마플: p.268")
    assert_homework_section_is_last(filtered)

    # E. Even similar consumed notes must not remove progress or homework.
    docs_text_e = prepare_summary_for_google_docs_cell(
        """진도(대수 APEX): 42차시

숙제:
- APEX: 43차시 풀어오기"""
    )
    with tempfile.TemporaryDirectory() as temp_dir:
        registry_path = Path(temp_dir) / "local_consumed_admin_notes.json"
        mark_admin_notes_consumed(
            "학생A",
            "sid-a",
            ["진도(대수 APEX): 42차시", "APEX: 43차시 풀어오기"],
            "added",
            final_text="진도(대수 APEX): 42차시\nAPEX: 43차시 풀어오기",
            registry_path=registry_path,
        )
        filtered_e = filter_consumed_admin_sections_from_docs_text(
            "학생A",
            "sid-a",
            docs_text_e,
            admin_source_notes="진도(대수 APEX): 42차시\nAPEX: 43차시 풀어오기",
            registry_path=registry_path,
        )["filtered_text"]
    assert_contains(filtered_e, "진도(대수 APEX): 42차시")
    assert_contains(filtered_e, "숙제:")
    assert_contains(filtered_e, "43차시 풀어오기")
    assert_homework_section_is_last(filtered_e)

    # F. Real counseling notes are preserved.
    result_f = prepare_summary_for_google_docs_cell(
        """진도(대수 APEX): 42차시

상담 참고사항
- 시험기간 중 발표 준비 시간을 확보하기 어렵다는 맥락이 있었음.

숙제:
- APEX: 43차시 풀어오기"""
    )
    assert_contains(result_f, "상담 참고사항")
    assert_contains(result_f, "시험기간 중 발표 준비 시간을 확보하기 어렵다는 맥락이 있었음.")
    assert_homework_section_is_last(result_f)

    # H. Missing progress and homework do not create placeholders.
    result_h = prepare_summary_for_google_docs_cell(
        """상담 참고사항
- 실제 상담 참고 내용"""
    )
    assert_contains(result_h, "상담 참고사항")
    assert_contains(result_h, "실제 상담 참고 내용")
    assert_not_contains(result_h, "진도: 확인 필요")
    assert_not_contains(result_h, "숙제:\n- 확인 필요")
    assert_not_contains(result_h, "숙제:")


def check_recording_summary_validation_stays_separate_from_docs_filter() -> None:
    from app import is_valid_generated_summary

    docs_text_without_today = """진도(대수 APEX): 42차시

상담 참고사항
- 실제 상담 참고 내용

숙제:
- 마플: p.268"""
    assert is_valid_generated_summary(docs_text_without_today) is True


def _function_body(source: str, function_name: str) -> str:
    marker = f"def {function_name}("
    start = source.index(marker)
    next_def = source.find("\ndef ", start + len(marker))
    return source[start:] if next_def < 0 else source[start:next_def]


def check_log_csv_safe_batch_settings() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    preview_body = _function_body(app_text, "render_log_csv_to_docs_preview_ui")
    transfer_body = _function_body(app_text, "execute_log_csv_transfer")
    assert "LOG_CSV_TO_DOCS_BATCH_SIZE_OPTIONS = (3, 5, 10)" in app_text
    assert "LOG_CSV_TO_DOCS_DEFAULT_BATCH_SIZE = 10" in app_text
    assert "LOG_CSV_TO_DOCS_ROW_PAUSE_SECONDS = 0.5" in app_text
    assert "LOG_CSV_TO_DOCS_BATCH_PAUSE_SECONDS = 3" in app_text
    assert "LOG_CSV_TO_DOCS_LOCK_RETRY_PAUSE_SECONDS = 12" in app_text
    assert "LOG_CSV_TO_DOCS_MAX_WORKERS = 5" in app_text
    assert "ThreadPoolExecutor(" in transfer_body
    assert "max_workers=LOG_CSV_TO_DOCS_MAX_WORKERS" in transfer_body
    assert "target_key not in target_keys" in transfer_body
    assert "position = completed_before + remaining_position" in app_text
    assert 'st.session_state["log_csv_to_docs_pacing_version"] = LOG_CSV_TO_DOCS_PACING_VERSION' in preview_body
    assert "completed_post_count = 0" in transfer_body
    assert "completed_post_count += 1" in transfer_body
    assert "completed_post_count % save_batch_size == 0" in transfer_body
    assert "set_log_csv_batch_in_flight_requests(" in transfer_body
    no_content_block = transfer_body[
        transfer_body.index("if not final_docs_summary:") : transfer_body.index("if len(docs_matches) != 1:")
    ]
    no_mapping_block = transfer_body[
        transfer_body.index("if len(docs_matches) != 1:") : transfer_body.index("docs_match = docs_matches[0]")
    ]
    assert "time.sleep(" not in no_content_block
    assert "time.sleep(" not in no_mapping_block
    assert "asyncio.gather" not in app_text


def check_log_csv_progress_checkpoint_static() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    preview_body = _function_body(app_text, "render_log_csv_to_docs_preview_ui")
    transfer_body = _function_body(app_text, "execute_log_csv_transfer")
    assert 'LOG_CSV_DOCS_STATE_PATH = DRAFT_DIR / "log_csv_to_docs_run.json"' in app_text
    assert "restore_log_csv_auto_import_from_batch_state()" in preview_body
    assert "render_log_csv_persisted_progress(upload_signature_hash)" in preview_body
    assert "create_log_csv_batch_state(" in preview_body
    assert "record_log_csv_batch_result(" in transfer_body
    assert "complete_log_csv_batch_state(" in transfer_body
    assert "interrupt_log_csv_batch_state(" in transfer_body
    assert "남은 작업 이어서 저장" in preview_body
    assert 'st.session_state["log_csv_to_docs_save_results_signature"] = upload_signature_hash' in preview_body
    assert '"source_index": result.get("source_index", "")' in app_text


def check_log_csv_retry_status_policy_static() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    preview_body = _function_body(app_text, "render_log_csv_to_docs_preview_ui")
    compact_list_body = _function_body(app_text, "render_compact_log_csv_result_list")
    progress_body = _function_body(app_text, "render_log_csv_persisted_progress")
    transfer_body = _function_body(app_text, "execute_log_csv_transfer")
    assert "st.checkbox(" not in compact_list_body
    assert "results[:max_items]" not in compact_list_body
    assert "classify_google_docs_save_result(result)" in _function_body(app_text, "is_log_csv_retry_target_result")
    assert "compact_result_groups = group_compact_log_csv_results(save_results)" in app_text
    assert 'render_compact_log_csv_result_list("이미 처리됨"' not in app_text
    assert 'render_compact_log_csv_result_list("확인 필요"' in app_text
    assert 'render_compact_log_csv_result_list("실패"' in app_text
    assert "문제 학생만 다시 저장" in app_text
    assert "문제 학생만 다시 선택" not in app_text
    assert "log_csv_to_docs_select_problem_only_after_save_" not in app_text
    assert "log_csv_to_docs_retry_problem_only_after_save_" in app_text
    assert "retry_selection_from_results" in app_text
    assert "retry_target_results" in app_text
    assert "st.session_state[retry_failed_pending_key] = True" in app_text
    assert "Google Docs 저장 진행 중" in progress_body
    assert "현재 {current_position:,}/{total:,}" in progress_body
    assert "phase='Google Docs 응답 대기 중'" in transfer_body
    assert "retry_run_active = bool(retry_failed_pending)" in preview_body
    assert "resume_run_active = bool(resume_pending)" in preview_body
    assert "log_csv_to_docs_result_detail_table_" in app_text
    assert "log_csv_to_docs_search_detail_table_" not in app_text
    assert "log_csv_to_docs_retry_failed_after_save_" not in app_text
    assert "log_csv_to_docs_select_failed_after_save_" not in app_text
    assert 'result_summary = f"총 ' not in preview_body
    assert "추가 여부 불확실 항목은 Docs에서 먼저 확인" not in preview_body
    assert "log_csv_duplicate_diagnostic_table_" in app_text
    assert "log_csv_special_class_diagnostic_table_" in app_text


def check_google_docs_save_result_classification_helper() -> None:
    from counsel_modules.log_csv_utils import classify_google_docs_save_result

    new_saved = classify_google_docs_save_result({"result_status": "성공"})
    assert new_saved["count_key"] == "new_saved"
    assert new_saved["show_in_compact_list"] is False
    assert new_saved["retry_allowed"] is False

    already_saved = classify_google_docs_save_result({"duplicate_skipped": True})
    assert already_saved["label"] == "이미 저장됨"
    assert already_saved["compact_section"] == "이미 처리됨"
    assert already_saved["is_success_like"] is True

    updated_same_date = classify_google_docs_save_result({"message": "updated_existing_same_date"})
    assert updated_same_date["label"] == "기존 기록 업데이트"
    assert updated_same_date["count_key"] == "updated_existing"
    assert updated_same_date["is_success_like"] is True

    unsafe = classify_google_docs_save_result(
        {"duplicate_skipped": True, "duplicate_reason": "unsafe_similar_record"}
    )
    assert unsafe["label"] == "중복 저장 의심"
    assert unsafe["count_key"] == "duplicate_write_suspected"
    assert unsafe["compact_section"] == "확인 필요"

    confirmed = classify_google_docs_save_result({"result_status": "saved_confirmed_after_timeout"})
    assert confirmed["label"] == "저장 확인됨 · 응답 지연"
    assert confirmed["retry_allowed"] is False
    assert confirmed["is_success_like"] is True

    timeout = classify_google_docs_save_result({"result_status": "timeout_unknown"})
    assert timeout["label"] == "추가 여부 불확실"
    assert timeout["is_failure_like"] is False
    assert timeout["retry_allowed"] is False

    lock_timeout = classify_google_docs_save_result({"result_status": "lock_timeout_retryable"})
    assert lock_timeout["label"] == "잠금 시간초과"
    assert lock_timeout["retry_allowed"] is True
    assert lock_timeout["retry_scope"] == "same_student_only"

    failed = classify_google_docs_save_result(
        {"ok": False, "error_type": "permission_or_doc_not_found"}
    )
    assert failed["label"] == "실패"
    assert failed["compact_section"] == "실패"
    assert failed["is_failure_like"] is True

    review = classify_google_docs_save_result({"needs_review": True})
    assert review["label"] == "문서 확인 필요"
    assert review["group"] == "needs_check"
    assert review["is_failure_like"] is False


def check_log_csv_compact_result_display_policy() -> None:
    from app import compact_log_csv_result_text, google_docs_url_from_fields, group_compact_log_csv_results

    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    compact_link_body = _function_body(app_text, "render_compact_docs_link_line")
    assert "st.columns([5, 1])" not in compact_link_body
    assert "[Docs 열기]" in compact_link_body

    already_saved_results = [
        {
            "name": "김OO",
            "date": "2026-05-18",
            "duplicate_skipped": True,
            "doc_url": "https://docs.google.com/document/d/doc-a/edit",
        },
        {
            "name": "이OO",
            "result_status": "saved_confirmed_after_timeout",
            "doc_id": "doc-b",
        },
    ]
    already_grouped = group_compact_log_csv_results(already_saved_results)
    assert len(already_grouped["already_processed"]) == 2
    assert compact_log_csv_result_text(already_saved_results[0]) == "김OO · 이미 저장됨"
    assert compact_log_csv_result_text(already_saved_results[1]) == "이OO · 저장 확인됨 · 응답 지연"
    assert "2026-05-18" not in compact_log_csv_result_text(already_saved_results[0])
    assert google_docs_url_from_fields("", "doc-b") == "https://docs.google.com/document/d/doc-b/edit"

    timeout_result = {
        "name": "박OO",
        "result_status": "timeout_unknown",
        "timeout_unknown": True,
        "needs_review": True,
    }
    timeout_grouped = group_compact_log_csv_results([timeout_result])
    assert timeout_grouped["needs_review"] == [timeout_result]
    assert timeout_grouped["failed"] == []
    assert compact_log_csv_result_text(timeout_result) == "박OO · 추가 여부 불확실"

    unsafe_result = {
        "name": "최OO",
        "duplicate_skipped": True,
        "duplicate_reason": "unsafe_similar_record",
    }
    unsafe_grouped = group_compact_log_csv_results([unsafe_result])
    assert unsafe_grouped["needs_review"] == [unsafe_result]
    assert unsafe_grouped["already_processed"] == []
    assert compact_log_csv_result_text(unsafe_result) == "최OO · 중복 저장 의심"

    new_results = [
        {"name": "신규1", "result_status": "성공"},
        {"name": "신규2", "result_status": "성공"},
        {"name": "신규3", "result_status": "성공"},
        {"name": "이미1", "duplicate_skipped": True},
    ]
    new_grouped = group_compact_log_csv_results(new_results)
    assert len(new_grouped["newly_added"]) == 3
    assert len(new_grouped["already_processed"]) == 1
    assert not new_grouped["needs_review"]
    assert not new_grouped["failed"]


def check_google_docs_timeout_retry_classification_policy() -> None:
    from counsel_modules.google_docs_utils import classify_google_docs_timeout_verification

    confirmed = classify_google_docs_timeout_verification(
        {"ok": True, "verify_only": True, "found_existing": True}
    )
    unknown = classify_google_docs_timeout_verification(
        {"ok": True, "verify_only": True, "found_existing": False}
    )
    lock_timeout = classify_google_docs_timeout_verification(
        {"ok": False, "verify_only": True, "error_type": "LockService", "message": "lock timeout"}
    )
    assert confirmed["status"] == "saved_confirmed_after_timeout"
    assert confirmed["failure"] is False
    assert confirmed["retry_recommended"] is False
    assert unknown["status"] == "timeout_unknown"
    assert unknown["failure"] is False
    assert unknown["retry_recommended"] is False
    assert unknown["needs_review"] is True
    assert lock_timeout["status"] == "lock_timeout_retryable"
    assert lock_timeout["failure"] is False
    assert lock_timeout["retry_recommended"] is True


def check_invalid_generated_summary_rejected() -> None:
    from app import is_valid_generated_summary, summary_generation_output_state

    for value in ["", "   ", "c", "C", ".", "-", "없음", "null", "None"]:
        assert is_valid_generated_summary(value) is False, value
    only_notes = "*상담 참고사항*\n- 학교에서 발표 준비 관련 대화가 있었음."
    assert is_valid_generated_summary(only_notes) is True
    only_today = """[오늘 확인할 것]

수업 전 확인
- 마플 p.268 풀이 흔적 확인"""
    assert is_valid_generated_summary(only_today) is False
    generic_today = """[오늘 확인할 것]

수업 전 확인
- 이해도 확인

*상담 참고사항*
- 짧은 상담이 있었음."""
    normalized_generic_today = load_normalize_summary()[0](generic_today, "테스트", date(2026, 5, 18))
    assert is_valid_generated_summary(normalized_generic_today) is True
    valid = """[오늘 확인할 것]

수업 전 확인
- 발표 준비 진행 상황 확인

*상담 참고사항*
- 학교에서 발표 준비 관련 대화가 있었음."""
    assert is_valid_generated_summary(valid) is True
    valid_state = summary_generation_output_state(valid)
    assert valid_state["copy_allowed"] is True
    assert valid_state["copy_text"] == valid
    assert "상담 참고사항" in valid_state["copy_text"]
    valid_without_notes = """[오늘 확인할 것]

수업 전 확인
- APEX 38차시 진행 상황 확인

진도(대수 APEX): 38차시

숙제:
- APEX: 다음 숙제 풀어오기"""
    assert is_valid_generated_summary(valid_without_notes) is False


def check_generated_summary_without_notes_rejected() -> None:
    from app import (
        generated_summary_invalid_reason,
        summary_generation_output_state,
    )

    summary_without_notes = """[오늘 확인할 것]

수업 전 확인
- APEX 38차시 진행 상황 확인

진도(대수 APEX): 38차시

숙제:
- APEX: 다음 숙제 풀어오기"""
    state = summary_generation_output_state(summary_without_notes)

    assert generated_summary_invalid_reason(summary_without_notes) == "missing_notes"
    assert state["valid"] is False
    assert state["copy_allowed"] is False
    assert state["save_allowed"] is False


def check_notes_only_summary_is_valid() -> None:
    from app import (
        generated_summary_invalid_reason,
        summary_generation_output_state,
    )

    notes_only = """*상담 참고사항*
- 학생이 피곤하다고 답함."""
    notes_state = summary_generation_output_state(notes_only)
    assert generated_summary_invalid_reason(notes_only) == ""
    assert notes_state["valid"] is True
    assert notes_state["needs_completion"] is False
    assert notes_state["failed"] is False
    assert notes_state["copy_allowed"] is True
    assert notes_state["save_allowed"] is True
    assert "학생이 피곤하다고 답함" in notes_state["textarea_value"]


def check_runtime_noise_removed_from_summary_body(normalize_summary) -> None:
    from app import is_valid_generated_summary, summary_generation_output_state

    raw_summary = """[오늘 확인할 것]

SUCCESS: The process with PID 21924 (child process of PID 10140) has been terminated.
SUCCESS: The process with PID 10140 (child process of PID 23236) has been terminated.

*상담 참고사항*
- 과제 또는 활동 수행 여부를 묻는 대화에서 하지 않았다는 응답이 반복됨.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))
    state = summary_generation_output_state(result)

    assert_not_contains(result, "SUCCESS: The process with PID")
    assert_not_contains(result, "child process of PID")
    assert_not_contains(result, "has been terminated")
    assert_contains(result, "과제 또는 활동 수행 여부")
    assert is_valid_generated_summary(result) is True
    assert state["copy_allowed"] is True
    assert_not_contains(state["copy_text"], "SUCCESS: The process with PID")


def check_runtime_noise_stdout_stderr_removed_but_notes_kept(normalize_summary) -> None:
    raw_summary = """*상담 참고사항*
- 학생이 수업 중 졸림을 호소함.
stdout:
SUCCESS: The process with PID 123 has been terminated.
stderr:
Traceback: ...
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))

    assert_not_contains(result, "stdout:")
    assert_not_contains(result, "stderr:")
    assert_not_contains(result, "SUCCESS: The process")
    assert_not_contains(result, "Traceback")
    assert_contains(result, "학생이 수업 중 졸림을 호소함")


def check_runtime_noise_only_summary_is_invalid() -> None:
    from app import is_valid_generated_summary, summary_generation_output_state
    from counsel_modules.text_utils import remove_runtime_noise_from_summary

    raw_summary = "SUCCESS: The process with PID 123 has been terminated."
    cleaned = remove_runtime_noise_from_summary(raw_summary)
    state = summary_generation_output_state(raw_summary)

    assert cleaned == ""
    assert is_valid_generated_summary(raw_summary) is False
    assert state["copy_allowed"] is False
    assert state["save_allowed"] is False


def check_codex_summary_command_pins_requested_model() -> None:
    from app import CODEX_SUMMARY_MODEL, CODEX_SUMMARY_REASONING_EFFORT, build_codex_command

    command = build_codex_command(Path("data/tmp/codex_input.txt"))
    joined = " ".join(command)

    assert CODEX_SUMMARY_MODEL == "gpt-5.6-luna"
    assert CODEX_SUMMARY_REASONING_EFFORT == "medium"
    assert "--model gpt-5.6-luna" in joined
    assert 'model_reasoning_effort="medium"' in joined


def check_codex_exec_failure_output_is_not_valid_summary() -> None:
    from app import summary_generation_output_state, workflow_step_failure_progress_detail
    from counsel_modules.text_utils import remove_runtime_noise_from_summary

    raw_summary = r"""! 정리본 생성: 실패 · codex exec 실행 실패: Codex CLI 실행 중 오류가 발생했습니다.
선택된 실행 파일: C:\Users\idotd\AppData\Roaming\npm\codex.cmd
실행 명령: powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -Command
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8;
Get-Content -Raw -Encoding UTF8 'C:\Users\idotd\counsel-note-app\data\tmp\codex_input.txt' | &
"""
    cleaned = remove_runtime_noise_from_summary(raw_summary)
    state = summary_generation_output_state(raw_summary)
    progress_detail = workflow_step_failure_progress_detail("정리본 생성", RuntimeError(raw_summary))

    assert cleaned == ""
    assert state["valid"] is False
    assert state["textarea_value"] == ""
    assert state["copy_allowed"] is False
    assert progress_detail == "Codex CLI 실행 실패"
    assert "실행 명령" not in progress_detail
    assert "codex.cmd" not in progress_detail


def check_codex_logged_out_failure_is_actionable() -> None:
    from app import (
        is_codex_authentication_error,
        should_pause_audio_batch_for_codex_error,
        workflow_step_failure_progress_detail,
    )

    error = RuntimeError("codex exec 실행 실패:\nCodex 로그인이 필요합니다.\nstderr:\nNot logged in")

    assert is_codex_authentication_error(error) is True
    assert should_pause_audio_batch_for_codex_error(error) is True
    assert workflow_step_failure_progress_detail("정리본 생성", error) == "Codex 로그인 필요"


def check_codex_network_failure_pauses_batch() -> None:
    from app import should_pause_audio_batch_for_codex_error, workflow_step_failure_progress_detail

    error = RuntimeError("codex exec 실행 실패:\nstderr:\nstream disconnected (os error 10013)")

    assert should_pause_audio_batch_for_codex_error(error) is True
    assert workflow_step_failure_progress_detail("정리본 생성", error) == "Codex 네트워크 연결 실패"


def check_runtime_noise_filter_keeps_normal_counsel_sentence(normalize_summary) -> None:
    raw_summary = """*상담 참고사항*
- 시험을 잘 보면 기분 좋게 볼 수 있고, 못 보면 마음이 좋지 않을 것 같다는 맥락의 대화가 있었음.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))

    assert_contains(result, "잘 보면")
    assert_contains(result, "못 보면")
    assert_contains(result, "상담 참고사항")


def check_ambiguous_today_focus_removed_but_notes_remain_valid(normalize_summary) -> None:
    from app import summary_generation_output_state

    raw_summary = """[오늘 확인할 것]

수업 전 확인
- 이전 숙제를 실제로 해왔는지 확인

*상담 참고사항*
- 학생이 피곤하다고 답함.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))
    state = summary_generation_output_state(result)

    assert_not_contains(result, "이전 숙제를 실제로 해왔는지 확인")
    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "수업 전 확인")
    assert_contains(result, "*상담 참고사항*")
    assert state["valid"] is True
    assert state["needs_completion"] is False
    assert state["failed"] is False
    assert state["copy_allowed"] is True


def check_completed_summary_state_allows_copy_and_save() -> None:
    from app import summary_generation_output_state

    completed = """[오늘 확인할 것]

수업 전 확인
- 마플 p.268 풀이 흔적 확인

*상담 참고사항*
- 학생이 피곤하다고 답함."""
    state = summary_generation_output_state(completed)

    assert state["valid"] is True
    assert state["needs_completion"] is False
    assert state["copy_allowed"] is True
    assert state["save_allowed"] is True


def check_placeholder_notes_summary_is_invalid(normalize_summary) -> None:
    from app import is_valid_generated_summary, summary_generation_output_state

    raw_summary = """*상담 참고사항*
- 없음
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))
    state = summary_generation_output_state(result)

    assert is_valid_generated_summary(result) is False
    assert state["valid"] is False
    assert state["copy_allowed"] is False


def check_private_context_notes_only_summary_is_valid() -> None:
    from app import is_valid_generated_summary, summary_generation_output_state

    summary = """*상담 참고사항*
- 학생이 학교 발표 준비와 시험 일정 부담을 언급함."""
    state = summary_generation_output_state(summary)

    assert is_valid_generated_summary(summary) is True
    assert state["valid"] is True
    assert state["copy_allowed"] is True
    assert state["save_allowed"] is True


def check_meaningful_content_allows_copy_and_save_without_today_focus(normalize_summary) -> None:
    from app import (
        SUMMARY_STATUS_FAILED,
        SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT,
        SUMMARY_STATUS_READY,
        is_valid_generated_summary,
        summary_copy_save_allowed,
        summary_generation_output_state,
    )

    notes_only = """*상담 참고사항*
- 학생이 당일에는 수업을 듣기 어렵고 일을 해야 한다고 말함."""
    notes_state = summary_generation_output_state(notes_only, summary_status=SUMMARY_STATUS_READY)
    assert is_valid_generated_summary(notes_only) is True
    assert notes_state["valid"] is True
    assert notes_state["copy_allowed"] is True
    assert notes_state["save_allowed"] is True
    assert summary_copy_save_allowed(notes_only, SUMMARY_STATUS_READY) is True

    private_context = """*상담 참고사항*
- 학생이 생일 및 개인 일정 이야기를 했고, 시험 준비와 일정 부담이 있는 대화가 있었음."""
    private_state = summary_generation_output_state(private_context)
    assert private_state["valid"] is True
    assert private_state["copy_allowed"] is True
    assert private_state["save_allowed"] is True

    ambiguous_today = """[오늘 확인할 것]

수업 전 확인
- 이전 숙제를 실제로 해왔는지 확인
- 수업 영상 청취를 진행했는지 확인

*상담 참고사항*
- 학생이 피곤하다고 말함."""
    normalized = normalize_summary(ambiguous_today, "테스트", date(2026, 5, 24))
    normalized_state = summary_generation_output_state(normalized)
    assert_contains(normalized, "*상담 참고사항*")
    assert normalized_state["valid"] is True
    assert normalized_state["copy_allowed"] is True
    assert normalized_state["save_allowed"] is True

    meaningful_body_bullet = "- 학생이 학교 발표 준비와 시험 일정 부담을 언급함."
    body_state = summary_generation_output_state(meaningful_body_bullet)
    assert body_state["valid"] is False
    assert body_state["copy_allowed"] is False
    assert body_state["save_allowed"] is False

    assert summary_copy_save_allowed(notes_only, SUMMARY_STATUS_FAILED) is False
    assert summary_copy_save_allowed(notes_only, SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT) is False
    assert summary_copy_save_allowed("*상담 참고사항*\n- 없음", SUMMARY_STATUS_READY) is False
    assert summary_copy_save_allowed("SUCCESS: The process with PID 123 has been terminated.", SUMMARY_STATUS_READY) is False


def check_today_focus_empty_shape_policy_cases(normalize_summary) -> None:
    from app import (
        SUMMARY_STATUS_NEEDS_COMPLETION,
        SUMMARY_STATUS_READY,
        admin_notes_export_text_from_summary,
        extract_today_focus,
        summary_copy_save_allowed,
        summary_generation_output_state,
    )

    def today_focus_bullets(text: str) -> list[str]:
        focus = extract_today_focus(text)
        return [
            line.strip()
            for line in focus.splitlines()
            if line.strip().startswith(("-", "*"))
        ]

    notes_only = """*상담 참고사항*
- 학생이 당일에는 수업을 듣기 어렵고 일을 해야 한다고 말함."""
    expected_notes_only = """[오늘 확인할 것]

수업 전 확인

*상담 참고사항*
- 학생이 당일에는 수업을 듣기 어렵고 일을 해야 한다고 말함."""
    result_a = normalize_summary(notes_only, "테스트", date(2026, 5, 24))
    state_a = summary_generation_output_state(result_a)
    assert result_a == expected_notes_only
    assert today_focus_bullets(result_a) == []
    assert state_a["valid"] is True
    assert state_a["copy_allowed"] is True
    assert state_a["save_allowed"] is True

    ambiguous_today = """[오늘 확인할 것]

수업 전 확인
- 이전 숙제를 실제로 해왔는지 확인
- 수업 영상 청취를 진행했는지 확인

*상담 참고사항*
- 학생이 피곤하다고 말함."""
    result_b = normalize_summary(ambiguous_today, "테스트", date(2026, 5, 24))
    state_b = summary_generation_output_state(result_b)
    assert_not_contains(result_b, "이전 숙제를 실제로 해왔는지 확인")
    assert_not_contains(result_b, "수업 영상 청취를 진행했는지 확인")
    assert_contains(result_b, "[오늘 확인할 것]")
    assert_contains(result_b, "수업 전 확인")
    assert_contains(result_b, "*상담 참고사항*")
    assert today_focus_bullets(result_b) == []
    assert state_b["valid"] is True
    assert state_b["save_allowed"] is True

    concrete_today = """[오늘 확인할 것]

수업 전 확인
- 마플 p.268 풀이 흔적 확인

*상담 참고사항*
- 숙제 관련 대화가 있었음."""
    result_c = normalize_summary(concrete_today, "테스트", date(2026, 5, 24))
    state_c = summary_generation_output_state(result_c)
    assert_contains(result_c, "마플 p.268 풀이 흔적 확인")
    assert today_focus_bullets(result_c) == ["- 마플 p.268 풀이 흔적 확인"]
    assert state_c["valid"] is True

    placeholder_notes = """*상담 참고사항*
- 없음"""
    result_d = normalize_summary(placeholder_notes, "테스트", date(2026, 5, 24))
    state_d = summary_generation_output_state(result_d)
    assert state_d["valid"] is False
    assert state_d["save_allowed"] is False

    runtime_noise = "SUCCESS: The process with PID 123 has been terminated."
    result_e = normalize_summary(runtime_noise, "테스트", date(2026, 5, 24))
    state_e = summary_generation_output_state(result_e)
    assert result_e == ""
    assert state_e["valid"] is False
    assert state_e["save_allowed"] is False

    state_f = summary_generation_output_state(expected_notes_only, summary_status=SUMMARY_STATUS_READY)
    admin_export_text, _source_label = admin_notes_export_text_from_summary(
        extract_today_focus(expected_notes_only),
        expected_notes_only,
    )
    admin_button_condition = bool(
        summary_copy_save_allowed(expected_notes_only, SUMMARY_STATUS_READY)
        and admin_export_text.strip()
        and "테스트"
    )
    stale_completion_state = summary_generation_output_state(
        expected_notes_only,
        summary_status=SUMMARY_STATUS_NEEDS_COMPLETION,
    )
    assert state_f["valid"] is True
    assert admin_button_condition is True
    assert stale_completion_state["copy_allowed"] is True
    assert stale_completion_state["save_allowed"] is True

    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    assert_contains(app_text, 'st.button("5A ADMIN 특이사항으로 내보내기"')
    assert_not_contains(app_text, 'if st.button("학생 Docs 저장"')
    assert_not_contains(app_text, 'if st.button("상세 상담 기록 추가"')
    assert_not_contains(app_text, "[오늘 확인할 것]에 구체 확인 항목이 부족합니다")


def check_admin_notes_export_uses_notes_when_today_focus_is_absent() -> None:
    from app import (
        SUMMARY_STATUS_READY,
        admin_notes_export_text_from_summary,
        summary_copy_save_allowed,
    )

    notes_only = """*상담 참고사항*
- 학생이 당일에는 수업을 듣기 어렵고 일을 해야 한다고 말함."""
    export_text, source_label = admin_notes_export_text_from_summary("", notes_only)

    assert source_label == "정리본"
    assert_contains(export_text, "*상담 참고사항*")
    assert_contains(export_text, "수업을 듣기 어렵고 일을 해야 한다고 말함")
    assert summary_copy_save_allowed(notes_only, SUMMARY_STATUS_READY) is True

    today_focus = "수업 전 확인\n- 마플 p.268 풀이 흔적 확인"
    focus_export_text, focus_source_label = admin_notes_export_text_from_summary(today_focus, notes_only)

    assert focus_source_label == "오늘 확인할 것+상담 참고사항"
    assert_contains(focus_export_text, "[오늘 확인할 것]")
    assert_contains(focus_export_text, "마플 p.268 풀이 흔적 확인")
    assert_contains(focus_export_text, "*상담 참고사항*")
    assert_contains(focus_export_text, "수업을 듣기 어렵고 일을 해야 한다고 말함")

    empty_today_focus = "[오늘 확인할 것]\n\n수업 전 확인"
    empty_focus_export_text, empty_focus_source_label = admin_notes_export_text_from_summary(
        empty_today_focus,
        notes_only,
    )

    assert empty_focus_source_label == "정리본"
    assert_contains(empty_focus_export_text, "*상담 참고사항*")
    assert_contains(empty_focus_export_text, "수업을 듣기 어렵고 일을 해야 한다고 말함")


def check_log_action_overlays_current_summary_on_matching_csv_row() -> None:
    from app import AdminNotesSyncRequest, apply_pending_admin_notes_to_log_rows

    request = AdminNotesSyncRequest(
        student_name="학생A",
        counseling_date=date(2026, 9, 5),
        admin_sid="student-a-001",
        admin_base_url="http://admin.invalid",
        export_text="*상담 참고사항*\n- 새 정리본",
        export_source_label="정리본",
        today_focus_text="",
        preview_key="preview-a",
    )
    rows = [
        {
            "date": "2026-09-05",
            "name": "학생 A",
            "sid": "student-a-001",
            "notes": "이전 정리본",
        },
        {
            "date": "2026-09-04",
            "name": "학생 A",
            "sid": "student-a-001",
            "notes": "다른 날짜 기록",
        },
        {
            "date": "2026-09-05",
            "name": "학생 A",
            "sid": "student-a-002",
            "notes": "다른 SID 기록",
        },
    ]

    matched_count = apply_pending_admin_notes_to_log_rows(rows, request)

    assert matched_count == 1
    assert rows[0]["notes"] == request.export_text
    assert rows[0]["_pending_admin_notes_sync_key"] == request.preview_key
    assert rows[1]["notes"] == "다른 날짜 기록"
    assert rows[2]["notes"] == "다른 SID 기록"


def check_pending_admin_summary_changes_effective_csv_history_hash() -> None:
    from app import AdminNotesSyncRequest, effective_log_csv_content_hash

    first_request = AdminNotesSyncRequest(
        student_name="학생A",
        counseling_date=date(2026, 9, 5),
        admin_sid="student-a-001",
        admin_base_url="http://admin.invalid",
        export_text="첫 정리본",
        export_source_label="정리본",
        today_focus_text="",
        preview_key="preview-a",
    )
    second_request = AdminNotesSyncRequest(
        student_name="학생A",
        counseling_date=date(2026, 9, 5),
        admin_sid="student-a-001",
        admin_base_url="http://admin.invalid",
        export_text="둘째 정리본",
        export_source_label="정리본",
        today_focus_text="",
        preview_key="preview-b",
    )

    first_hash = effective_log_csv_content_hash("raw-csv-hash", first_request, 1)
    repeated_hash = effective_log_csv_content_hash("raw-csv-hash", first_request, 1)
    changed_hash = effective_log_csv_content_hash("raw-csv-hash", second_request, 1)

    assert first_hash == repeated_hash
    assert changed_hash != first_hash
    assert effective_log_csv_content_hash("raw-csv-hash", first_request, 0) == "raw-csv-hash"


def check_admin_notes_sync_skips_post_when_notes_are_current() -> None:
    import app

    request = app.AdminNotesSyncRequest(
        student_name="학생A",
        counseling_date=date(2026, 9, 5),
        admin_sid="student-a-001",
        admin_base_url="http://admin.invalid",
        export_text="*상담 참고사항*\n- 같은 정리본",
        export_source_label="정리본",
        today_focus_text="",
        preview_key="preview-a",
    )
    with (
        patch.object(app, "get_admin_log_entry", return_value={"notes": request.export_text}),
        patch.object(app, "backup_admin_notes") as backup_mock,
        patch.object(app, "patch_admin_log_notes") as post_mock,
    ):
        result = app.sync_admin_notes(request)

    assert result.updated is False
    assert result.notes == request.export_text
    backup_mock.assert_not_called()
    post_mock.assert_not_called()


def check_log_action_replaces_existing_notes_with_focus_only_export() -> None:
    from app import AdminNotesSyncRequest, apply_pending_admin_notes_to_log_rows

    request = AdminNotesSyncRequest(
        student_name="학생A",
        counseling_date=date(2026, 9, 5),
        admin_sid="student-a-001",
        admin_base_url="http://admin.invalid",
        export_text="[오늘 확인할 것]\n\n수업 전 확인\n- 교재 풀이 흔적 확인",
        export_source_label="오늘 확인할 것",
        today_focus_text="수업 전 확인\n- 교재 풀이 흔적 확인",
        preview_key="preview-a",
    )
    rows = [
        {
            "date": "2026-09-05",
            "name": "학생A",
            "sid": "student-a-001",
            "notes": "*상담 참고사항*\n- 기존 상담 내용",
        }
    ]

    matched_count = apply_pending_admin_notes_to_log_rows(rows, request)

    assert matched_count == 1
    assert_contains(rows[0]["notes"], "교재 풀이 흔적 확인")
    assert_not_contains(rows[0]["notes"], "기존 상담 내용")


def check_admin_notes_sync_backs_up_and_posts_changed_notes() -> None:
    import app

    request = app.AdminNotesSyncRequest(
        student_name="학생A",
        counseling_date=date(2026, 9, 5),
        admin_sid="student-a-001",
        admin_base_url="http://admin.invalid",
        export_text="*상담 참고사항*\n- 새 정리본",
        export_source_label="정리본",
        today_focus_text="",
        preview_key="preview-a",
    )
    backup_path = Path("backup.txt")
    with (
        patch.object(app, "get_admin_log_entry", return_value={"notes": "이전 정리본"}),
        patch.object(app, "backup_admin_notes", return_value=backup_path) as backup_mock,
        patch.object(app, "patch_admin_log_notes", return_value={"ok": True}) as post_mock,
    ):
        result = app.sync_admin_notes(request)

    assert result.updated is True
    assert result.notes == request.export_text
    assert result.backup_path == backup_path
    backup_mock.assert_called_once()
    post_mock.assert_called_once_with(
        request.admin_base_url,
        request.counseling_date,
        request.admin_sid,
        request.export_text,
        "이전 정리본",
    )


def check_log_action_auto_admin_sync_static_contract() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")

    assert_contains(app_text, "pending_admin_sync_match_count = apply_pending_admin_notes_to_log_rows(")
    assert_contains(app_text, "effective_log_csv_content_hash(")
    assert_contains(app_text, "sync_admin_notes(pending_admin_sync)")
    assert_contains(app_text, "pending_admin_sync = render_admin_notes_save_ui(")


def check_admin_notes_export_button_static_contract() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")

    assert_contains(app_text, "5A ADMIN 특이사항으로 내보내기")
    assert_contains(app_text, "summary_text=edited_text")
    assert_contains(app_text, "admin_notes_export_text_from_summary")
    assert_contains(app_text, "admin_notes_export_block_message(")
    assert_not_contains(app_text, "[오늘 확인할 것]이 없어 정리본 내용을 5A ADMIN 특이사항으로 내보냅니다.")
    assert_not_contains(app_text, "if not export_allowed or not clean_export_text:\n        return")
    assert_not_contains(app_text, "if not clean_student_name:\n        return\n\n    sid_candidates")


def check_admin_target_change_button_static_contract() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")

    assert_contains(app_text, 'st.button("저장 위치 바꾸기"')
    assert_contains(app_text, 'change_target_key = f"{select_key}_change_target"')
    assert_contains(app_text, "st.session_state[change_target_key] = True")
    assert_contains(app_text, "st.session_state[select_key] = ADMIN_SID_MANUAL_SELECT_PLACEHOLDER")
    assert_contains(app_text, 'st.session_state.pop("selected_admin_sid_for_student", None)')
    assert_contains(app_text, 'st.session_state.pop("selected_admin_sid_for_student_source", None)')
    assert_contains(app_text, "st.session_state.pop(change_target_key, None)")


def check_admin_notes_export_block_message() -> None:
    from app import admin_notes_export_block_message

    assert (
        admin_notes_export_block_message(
            student_name="테스트",
            export_text="수업 전 확인\n- 마플 p.268 풀이 흔적 확인",
            export_allowed=True,
            admin_sid="test-sid",
        )
        == ""
    )

    missing_student_and_text = admin_notes_export_block_message(
        student_name="",
        export_text="",
        export_allowed=False,
        admin_sid="",
    )
    assert_contains(missing_student_and_text, "학생이 선택되지 않았습니다")
    assert_contains(missing_student_and_text, "내보낼 내용이 없습니다")
    assert_not_contains(missing_student_and_text, "admin 저장 대상을 찾지 못했습니다")

    missing_admin_target = admin_notes_export_block_message(
        student_name="테스트",
        export_text="*상담 참고사항*\n- 컨디션 관련 대화가 있었음.",
        export_allowed=True,
        admin_sid="",
    )
    assert_contains(missing_admin_target, "저장 대상을 먼저 선택하세요")


def check_build_info_badge_format_and_fallbacks() -> None:
    import app

    badge = app.format_build_info_badge(
        {"last_updated_at": "2026-05-24T22:51:28", "channel": "sebin-update"}
    )
    assert badge == "마지막 업데이트: 2026-05-24 22:51"
    assert app.format_build_info_badge({}) == "마지막 업데이트: 알 수 없음"

    original_build_info_path = app.BUILD_INFO_PATH
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            missing_path = Path(temp_dir) / "missing_BUILD_INFO.json"
            app.BUILD_INFO_PATH = missing_path
            assert app.read_build_info() == {}
            assert app.format_build_info_badge() == "마지막 업데이트: 알 수 없음"

            broken_path = Path(temp_dir) / "BUILD_INFO.json"
            broken_path.write_text("{broken", encoding="utf-8")
            app.BUILD_INFO_PATH = broken_path
            assert app.read_build_info() == {}
            assert app.format_build_info_badge() == "마지막 업데이트: 알 수 없음"
    finally:
        app.BUILD_INFO_PATH = original_build_info_path


def check_app_last_modified_badge_rendered_under_title_static() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")

    title_index = app_text.index('st.title("5A Connect Log")')
    badge_index = app_text.index("st.caption(app_last_modified_badge)", title_index)
    next_top_ui_index = app_text.index("apply_korean_text_input_hints()", title_index)

    assert title_index < badge_index < next_top_ui_index
    assert "app_last_modified_badge = format_app_last_modified_badge()" in app_text
    assert "st.sidebar.caption(app_last_modified_badge)" in app_text


def check_runtime_path_diagnostics_static() -> None:
    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")

    assert_contains(app_text, "EXPECTED_RUNTIME_BASE_DIR")
    assert_contains(app_text, "runtime_environment_diagnostics")
    assert_contains(app_text, "현재 실행 경로")
    assert_contains(app_text, "app.py 경로")
    assert_contains(app_text, "BUILD_INFO package_type")
    assert_contains(app_text, "APP_VERSION.txt")
    assert_contains(app_text, "현재 앱이 기준 작업 폴더가 아닌 다른 설치본에서 실행 중입니다.")


def check_empty_failed_summary_stays_failed_not_needs_completion() -> None:
    from app import SUMMARY_STATUS_FAILED, summary_generation_output_state

    state = summary_generation_output_state("", failed=True, summary_status=SUMMARY_STATUS_FAILED)

    assert state["failed"] is True
    assert state["needs_completion"] is False
    assert state["copy_allowed"] is False
    assert state["save_allowed"] is False


def check_summary_section_spacing_format() -> None:
    from counsel_modules.text_utils import format_summary_section_spacing

    raw = """[오늘 확인할 것]
수업 전 확인
- 항목1
- 항목2
*상담 참고사항*
- 참고1
- 참고2"""
    expected = """[오늘 확인할 것]

수업 전 확인
- 항목1
- 항목2

*상담 참고사항*
- 참고1
- 참고2"""
    assert format_summary_section_spacing(raw) == expected


def check_summary_spacing_removes_blank_lines_between_bullets() -> None:
    from counsel_modules.text_utils import format_summary_section_spacing

    raw = """[오늘 확인할 것]

수업 전 확인
- 항목1

- 항목2

*상담 참고사항*
- 참고1

- 참고2"""
    result = format_summary_section_spacing(raw)

    assert_contains(result, "- 항목1\n- 항목2")
    assert_contains(result, "- 참고1\n- 참고2")
    assert_not_contains(result, "- 항목1\n\n- 항목2")
    assert_not_contains(result, "- 참고1\n\n- 참고2")


def check_summary_spacing_notes_only() -> None:
    from counsel_modules.text_utils import format_summary_section_spacing

    raw = """*상담 참고사항*
- 참고1

- 참고2"""
    expected = """*상담 참고사항*
- 참고1
- 참고2"""

    assert format_summary_section_spacing(raw) == expected


def check_summary_spacing_today_only() -> None:
    from counsel_modules.text_utils import format_summary_section_spacing

    raw = """[오늘 확인할 것]

수업 전 확인
- 항목1

- 항목2"""
    expected = """[오늘 확인할 것]

수업 전 확인
- 항목1
- 항목2"""

    assert format_summary_section_spacing(raw) == expected


def check_notes_generate_empty_today_focus_shape(normalize_summary) -> None:
    from app import is_valid_generated_summary

    raw_summary = """*상담 참고사항*
- 학교에서 50분 발표 수업 준비가 필요하다고 언급함.
- 시험기간 중 발표 준비 시간을 확보하기 어렵다는 맥락이 있었음.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))

    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "수업 전 확인")
    assert_contains(result, "*상담 참고사항*")
    assert_contains(result, "학교에서 50분 발표 수업 준비가 필요하다고 언급함")
    assert is_valid_generated_summary(result) is True


def check_learning_flow_section_stays_above_today_focus(normalize_summary) -> None:
    from app import extract_learning_flow_section, prepare_summary_for_google_docs_cell

    raw_summary = """[오늘 확인할 것]

수업 전 확인
- APEX 26차시 백지리뷰 제출 여부 확인

[학생별 방향성]
- 기말 이후 공수2 A:ble로 흐름을 이어가기로 함.

*상담 참고사항*
- 학생별 학습 방향 관련 대화가 있었음.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 7, 6))
    docs_text = prepare_summary_for_google_docs_cell(result)

    assert result.startswith("[학생별 학습흐름]"), result
    assert result.index("[학생별 학습흐름]") < result.index("[오늘 확인할 것]")
    assert_contains(result, "공수2 A:ble로 흐름을 이어가기로 함")
    assert_contains(result, "APEX 26차시 백지리뷰 제출 여부 확인")
    assert_contains(extract_learning_flow_section(result), "공수2 A:ble로 흐름을 이어가기로 함")
    assert_contains(docs_text, "[학생별 학습흐름]")



def check_generic_today_focus_replaced_from_notes(normalize_summary) -> None:
    from app import is_valid_generated_summary

    raw_summary = """[오늘 확인할 것]

수업 전 확인
- 이해도 확인

*상담 참고사항*
- 학생이 APEX 26차시를 진행함.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))

    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "수업 전 확인")
    assert_not_contains(result, "이해도 확인")
    assert_contains(result, "*상담 참고사항*")
    assert_contains(result, "학생이 APEX 26차시를 진행함")
    assert is_valid_generated_summary(result) is True


def check_existing_concrete_today_focus_kept_with_required_heading(normalize_summary) -> None:
    raw_summary = """[오늘 확인할 것]

수업 전 확인
- APEX 26차시 백지리뷰 제출 여부 확인

*상담 참고사항*
- APEX 26차시를 진행함.
"""
    result = normalize_summary(raw_summary, "테스트", date(2026, 5, 18))

    assert_contains(result, "[오늘 확인할 것]")
    assert_contains(result, "APEX 26차시 백지리뷰 제출 여부 확인")
    assert_contains(result, "*상담 참고사항*")


VALID_RETRY_SUMMARY = """[오늘 확인할 것]

수업 전 확인
- APEX 26차시 백지리뷰 제출 여부 확인

*상담 참고사항*
- APEX 26차시를 진행함."""


def _sequence_summary_runner(values: list[str]):
    remaining = list(values)

    def runner(_prompt: str) -> str:
        if not remaining:
            raise AssertionError("summary runner called more times than expected")
        return remaining.pop(0)

    return runner


def check_summary_auto_retry_empty_then_valid() -> None:
    from app import generate_summary_from_transcript, summary_generation_output_state

    result = generate_summary_from_transcript(
        "테스트",
        date(2026, 5, 18),
        "APEX 26차시를 진행한 상담 원문입니다.",
        "기본 상담 정리",
        False,
        summary_runner=_sequence_summary_runner(["", VALID_RETRY_SUMMARY]),
        retry_context="test_auto_retry",
    )

    diagnostics = result["diagnostics"]
    output_state = summary_generation_output_state(result["summary"])
    assert diagnostics["first_attempt_valid"] is False
    assert diagnostics["retry_attempted"] is True
    assert diagnostics["retry_valid"] is True
    assert output_state["valid"] is True
    assert output_state["copy_allowed"] is True


def check_summary_auto_retry_placeholder_then_valid() -> None:
    from app import generate_summary_from_transcript, summary_generation_output_state

    result = generate_summary_from_transcript(
        "테스트",
        date(2026, 5, 18),
        "APEX 26차시를 진행한 상담 원문입니다.",
        "기본 상담 정리",
        False,
        summary_runner=_sequence_summary_runner(["c", VALID_RETRY_SUMMARY]),
        retry_context="test_auto_retry",
    )

    diagnostics = result["diagnostics"]
    output_state = summary_generation_output_state(result["summary"])
    assert diagnostics["first_attempt_valid"] is False
    assert diagnostics["retry_valid"] is True
    assert output_state["textarea_value"] == result["summary"]
    assert "c" != output_state["textarea_value"]


def check_summary_auto_retry_notes_only_then_valid() -> None:
    from app import generate_summary_from_transcript, summary_generation_output_state

    notes_only = """*상담 참고사항*
- 학생 컨디션 관련 대화가 있었음."""
    result = generate_summary_from_transcript(
        "테스트",
        date(2026, 5, 18),
        "APEX 26차시를 진행한 상담 원문입니다.",
        "기본 상담 정리",
        False,
        summary_runner=_sequence_summary_runner([notes_only, VALID_RETRY_SUMMARY]),
        retry_context="test_auto_retry",
    )

    output_state = summary_generation_output_state(result["summary"])
    assert result["diagnostics"]["retry_attempted"] is False
    assert output_state["valid"] is True
    assert output_state["copy_allowed"] is True
    assert_contains(result["summary"], "[오늘 확인할 것]")
    assert_contains(result["summary"], "수업 전 확인")
    assert_contains(result["summary"], "*상담 참고사항*")


def check_summary_auto_retry_all_invalid_fails_cleanly() -> None:
    from app import WorkflowStepError, generate_summary_from_transcript, summary_generation_output_state

    try:
        generate_summary_from_transcript(
            "테스트",
            date(2026, 5, 18),
            "구체 확인 항목을 만들 수 없는 상담 원문입니다.",
            "기본 상담 정리",
            False,
            summary_runner=_sequence_summary_runner(["", "c"]),
            retry_context="test_auto_retry",
        )
    except WorkflowStepError as exc:
        diagnostics = getattr(exc, "diagnostics", {})
    else:
        raise AssertionError("expected WorkflowStepError for invalid summaries")

    output_state = summary_generation_output_state(VALID_RETRY_SUMMARY, failed=True)
    assert diagnostics["first_attempt_valid"] is False
    assert diagnostics["retry_attempted"] is True
    assert diagnostics["retry_valid"] is False
    assert output_state["textarea_value"] == ""
    assert output_state["copy_allowed"] is False


def check_summary_retry_uses_same_transcript_signature() -> None:
    from app import generate_summary_from_transcript

    transcript = "같은 원문을 첫 생성과 자동 재시도에 모두 사용합니다."
    result = generate_summary_from_transcript(
        "테스트",
        date(2026, 5, 18),
        transcript,
        "기본 상담 정리",
        False,
        summary_runner=_sequence_summary_runner(["", VALID_RETRY_SUMMARY]),
        retry_context="test_same_transcript",
    )

    attempts = result["diagnostics"]["attempts"]
    assert attempts[0]["transcript_length"] == attempts[1]["transcript_length"]
    assert attempts[0]["transcript_hash"] == attempts[1]["transcript_hash"]


def check_failed_generation_hides_previous_summary_candidate() -> None:
    from app import summary_generation_output_state

    state = summary_generation_output_state(VALID_RETRY_SUMMARY, failed=True)
    assert state["textarea_value"] == ""
    assert state["copy_allowed"] is False
    assert state["save_allowed"] is False


def check_manual_summary_candidate_accepts_meaningful_notes() -> None:
    from app import validate_manual_summary_candidate

    result = validate_manual_summary_candidate(
        "*상담 참고사항*\n- 기말 이후 공통수학2 학습 흐름을 다시 조정하기로 함.",
        "테스트학생",
        date(2026, 8, 26),
    )

    assert result["invalid_reason"] == ""
    assert "공통수학2 학습 흐름" in result["summary"]


def check_manual_summary_candidate_rejects_blank_text() -> None:
    from app import validate_manual_summary_candidate

    result = validate_manual_summary_candidate("", "테스트학생", date(2026, 8, 26))

    assert result["invalid_reason"]
    assert result["summary"] == ""


def check_clipboard_copy_labels_use_full_summary_static() -> None:
    from app import normalize_legacy_today_task_ui_terms

    app_text = (ROOT_DIR / "app.py").read_text(encoding="utf-8")
    legacy_label = "오늘 " + "할 " + "일"

    assert legacy_label not in app_text
    assert "clipboard_label" not in app_text
    assert "정리본 전체 복사 완료" in app_text
    assert "copy_to_clipboard(clipboard_text)" in app_text
    cleaned = normalize_legacy_today_task_ui_terms(
        f"{legacy_label}이 클립보드에 복사되었습니다. Ctrl+V로 붙여넣으세요."
    )
    assert legacy_label not in cleaned
    assert "정리본이 클립보드에 복사되었습니다" in cleaned


def check_insufficient_transcript_blocks_auto_summary() -> None:
    from app import (
        SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT,
        is_insufficient_transcript_for_auto_summary,
        summary_generation_output_state,
        transcript_sufficiency_diagnostics,
    )

    short_transcript = ("짧은발화 " * 16).strip()
    short_transcript = short_transcript + " " + ("가" * max(0, 215 - len(short_transcript) - 1))
    short_transcript = short_transcript[:215]
    diagnostics = transcript_sufficiency_diagnostics(short_transcript)
    state = summary_generation_output_state(
        VALID_RETRY_SUMMARY,
        summary_status=SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT,
    )

    assert diagnostics["transcript_length_chars"] == 215
    assert diagnostics["transcript_word_count"] < diagnostics["min_transcript_words"]
    assert is_insufficient_transcript_for_auto_summary(short_transcript) is True
    assert state["valid"] is False
    assert state["copy_allowed"] is False
    assert state["save_allowed"] is False


def check_sufficient_transcript_allows_auto_summary_flow() -> None:
    from app import is_insufficient_transcript_for_auto_summary, transcript_sufficiency_diagnostics

    long_transcript = (
        ("충분한발화 " * 27).strip()
        + ". "
        + ("수업내용정리 " * 27).strip()
        + ". "
        + ("다음확인사항 " * 27).strip()
        + "."
    )
    diagnostics = transcript_sufficiency_diagnostics(long_transcript)

    assert diagnostics["transcript_length_chars"] >= 500
    assert diagnostics["transcript_word_count"] >= diagnostics["min_transcript_words"]
    assert diagnostics["transcript_sentence_count"] >= diagnostics["min_transcript_sentences"]
    assert is_insufficient_transcript_for_auto_summary(long_transcript) is False


def check_insufficient_transcript_status_is_not_completion() -> None:
    from app import SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT, summary_generation_output_state

    state = summary_generation_output_state(
        VALID_RETRY_SUMMARY,
        summary_status=SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT,
    )

    assert state["valid"] is False
    assert state["copy_allowed"] is False
    assert state["save_allowed"] is False


def check_insufficient_transcript_hides_previous_summary_candidate() -> None:
    from app import SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT, summary_generation_output_state

    state = summary_generation_output_state(
        VALID_RETRY_SUMMARY,
        summary_status=SUMMARY_STATUS_INSUFFICIENT_TRANSCRIPT,
    )

    assert state["textarea_value"] == ""
    assert state["copy_allowed"] is False


def check_student_transcripts_filter_current_student_only() -> None:
    import app

    original_transcript_dir = app.TRANSCRIPT_DIR
    counseling_date = date(2026, 5, 18)
    with tempfile.TemporaryDirectory() as temp_dir:
        app.TRANSCRIPT_DIR = Path(temp_dir)
        date_dir = app.transcript_date_dir(counseling_date)
        date_dir.mkdir(parents=True, exist_ok=True)
        current_path = date_dir / "현재학생_2026-05-18_101010_teacher.txt"
        other_path = date_dir / "다른학생_2026-05-18_101011_teacher.txt"
        current_path.write_text("current", encoding="utf-8")
        other_path.write_text("other", encoding="utf-8")

        result = app.transcripts_for_student_date(counseling_date, "현재학생")

    app.TRANSCRIPT_DIR = original_transcript_dir
    assert [path.name for path in result] == [current_path.name], result


def check_google_docs_mapping_registration_rows() -> None:
    from app import google_docs_mapping_registration_rows

    rows = [
        {
            "student_name": "학생A",
            "doc_url": "https://docs.google.com/document/d/doc-a/edit",
            "doc_id": "doc-a",
        },
        {"student_name": "", "doc_url": "https://docs.google.com/document/d/ignored/edit"},
        {"student_name": "학생B", "doc_url": "", "doc_id": "doc-b"},
    ]

    result = google_docs_mapping_registration_rows(rows)

    assert result == [
        {"학생명": "학생A", "Docs": "https://docs.google.com/document/d/doc-a/edit"},
        {"학생명": "학생B", "Docs": "https://docs.google.com/document/d/doc-b/edit"},
    ]


def check_google_docs_mapping_registration_keeps_csv_widget_run_alive() -> None:
    import app

    rerun_calls: list[bool] = []
    fake_st = types.SimpleNamespace(
        session_state={},
        expander=lambda *args, **kwargs: nullcontext(),
        text_input=lambda label, **kwargs: "학생A" if label == "학생명" else "docs-url",
        button=lambda *args, **kwargs: True,
        success=lambda *args, **kwargs: None,
        warning=lambda *args, **kwargs: None,
        error=lambda *args, **kwargs: None,
        rerun=lambda: rerun_calls.append(True),
        divider=lambda: None,
        caption=lambda *args, **kwargs: None,
    )
    add_result = {"student_name": "학생A", "doc_id": "doc-a", "backup_path": "unused"}

    with (
        patch.object(app, "st", fake_st),
        patch.object(app, "append_google_docs_mapping", return_value=add_result),
        patch.object(app, "load_google_docs_map_rows", return_value=[]),
    ):
        app.render_google_docs_mapping_add_ui(False)

    assert rerun_calls == [], "Docs 등록 직후 rerun이 뒤쪽 CSV 업로더 렌더링을 중단합니다."


def main() -> None:
    normalize_summary, source = load_normalize_summary()
    check_identity_lines_removed(normalize_summary)
    check_parent_misc_and_placeholders(normalize_summary)
    check_legacy_section_merge_and_move(normalize_summary)
    check_google_docs_progress_book_from_context()
    check_google_docs_next_action_absorbed()
    check_google_docs_homework_duplicate_books_same_assignment()
    check_google_docs_homework_distinct_book_assignments()
    check_google_docs_homework_progress_lifted_to_progress_line()
    check_google_docs_homework_progress_does_not_invent_unknown_progress_line()
    check_google_docs_homework_does_not_swallow_request_note_and_check_sections()
    check_google_docs_empty_notes_removed_and_progress_homework_kept()
    check_google_docs_placeholder_notes_removed()
    check_google_docs_real_notes_kept()
    check_google_docs_special_note_placeholder_removed_with_order_kept()
    check_next_action_section_absorbed(normalize_summary)
    check_generic_homework_scope_removed_from_today_focus(normalize_summary)
    check_generic_today_focus_bullets_removed(normalize_summary)
    check_concrete_today_focus_bullets_preserved(normalize_summary)
    check_homework_completion_removed_but_concrete_evidence_preserved(normalize_summary)
    check_due_day_generic_range_removed(normalize_summary)
    check_ambiguous_today_focus_without_target_removed(normalize_summary)
    check_specific_today_focus_targets_preserved(normalize_summary)
    check_generic_homework_check_concretized_from_homework_section(normalize_summary)
    check_generic_video_check_concretized_from_homework_section(normalize_summary)
    check_only_broad_today_focus_items_make_summary_invalid(normalize_summary)
    check_meta_uncertainty_notes_removed_with_homework_preserved(normalize_summary)
    check_meta_uncertainty_notes_empty_section_removed(normalize_summary)
    check_actionable_uncertainty_check_targets_preserved(normalize_summary)
    check_meta_uncertainty_today_focus_removed(normalize_summary)
    check_meta_uncertainty_keeps_confirmed_notes(normalize_summary)
    check_normalize_summary_removes_empty_notes_placeholder(normalize_summary)
    check_log_csv_homework_rows_merge_same_core()
    check_log_csv_homework_rows_merge_same_assignment()
    check_log_csv_homework_rows_do_not_merge_different_core()
    check_log_csv_same_content_different_dates_remain_separate()
    check_log_csv_homework_check_only_preserved()
    check_log_csv_attendance_only_rows_remain_saveable()
    check_log_csv_consumed_notes_cannot_remove_attendance()
    check_google_docs_attendance_survives_final_reformatting()
    check_google_docs_lock_timeout_detection()
    check_google_docs_timeout_verify_helper_import_smoke()
    check_google_docs_timeout_verify_classification()
    check_google_docs_html_error_response_is_delivery_uncertain()
    check_google_docs_request_callable_can_be_reused()
    check_google_docs_lock_timeout_verifies_before_retry_classification()
    check_counsel_duplicate_fingerprint_matches_legacy_and_current_homework_formats()
    check_apps_script_same_date_replace_rules_present()
    check_admin_auto_match_does_not_treat_suneung_teukgang_as_lesson_type()
    check_admin_auto_match_selects_unique_roster_subject_schedule_match()
    check_admin_auto_match_does_not_use_book_text_as_lesson_type()
    check_admin_auto_match_keeps_tie_for_review()
    check_admin_sid_manual_selection_resolves_final_target()
    check_admin_auto_match_allows_only_single_or_explicit_sid()
    check_admin_candidate_label_includes_real_disambiguators()
    check_admin_candidate_label_hides_internal_display_detail()
    check_log_csv_admin_match_selects_single_weekday_candidate()
    check_log_csv_admin_match_prefers_csv_date_weekday()
    check_log_csv_admin_match_prefers_time_when_weekday_ties()
    check_log_csv_admin_match_uses_day1_visit_time1_fields()
    check_log_csv_admin_match_uses_day2_field()
    check_log_csv_admin_match_prefers_matching_visit_time_when_day_ties()
    check_log_csv_admin_match_filters_to_matching_visit_time_before_subject_score()
    check_log_csv_admin_match_uses_sub_curriculum_subject()
    check_log_csv_explicit_subject_overrides_admin_curriculum_with_sub_curriculum()
    check_log_csv_explicit_subject_kept_when_admin_sub_curriculum_missing()
    check_log_csv_course_subject_precedes_admin_curriculum()
    check_log_csv_matching_curriculum_kept_over_other_sub_curriculum()
    check_log_csv_suneung_textbook_does_not_change_subject_or_lesson_type()
    check_log_csv_explicit_special_type_stays_separate_from_subject()
    check_log_csv_csv_subject_wins_between_same_time_candidates()
    check_log_csv_admin_match_does_not_infer_lesson_type_without_explicit_field()
    check_log_csv_admin_match_falls_back_when_day_code_unparseable()
    check_log_csv_admin_match_prefers_actual_admin_row_subject()
    check_log_csv_admin_match_prefers_actual_admin_row_lesson_type()
    check_log_csv_admin_match_prefers_actual_admin_row_over_default_weekday()
    check_log_csv_admin_match_prefers_actual_admin_sid_when_same_date_multiple()
    check_log_csv_admin_match_keeps_same_date_tie_for_review()
    check_log_csv_lesson_type_does_not_use_suneung_teukgang_textbook()
    check_log_csv_lesson_type_accepts_explicit_special_class()
    check_log_csv_admin_match_falls_back_when_date_weekday_unavailable()
    check_log_csv_admin_match_keeps_top_score_tie_for_review()
    check_prompt_latex_math_rules()
    check_consumed_admin_notes_fail_open_on_broken_json()
    check_log_csv_consumed_filter_reuses_single_registry_load()
    check_log_csv_auto_import_finds_only_new_completed_download()
    check_log_csv_auto_import_requests_one_shot_docs_export()
    check_consumed_admin_registry_diagnostics_and_reset_backup()
    check_consumed_admin_registry_broken_json_diagnostic()
    check_app_health_helpers()
    check_consumed_admin_notes_filters_same_student_only()
    check_consumed_admin_notes_are_scoped_by_counseling_date()
    check_consumed_admin_notes_context_and_disabled_behaviour()
    check_consumed_admin_notes_mark_success_and_skip_timeout()
    check_consumed_admin_notes_mark_save_failure_fail_open()
    check_consumed_admin_docs_filter_removes_today_and_notes_keeps_progress_homework()
    check_consumed_admin_docs_filter_keeps_transcript_source()
    check_consumed_admin_docs_filter_never_removes_progress_or_homework()
    check_consumed_admin_filter_removes_repeated_test_assignment_section()
    check_google_docs_text_golden_policies()
    check_recording_summary_validation_stays_separate_from_docs_filter()
    check_log_csv_safe_batch_settings()
    check_log_csv_progress_checkpoint_static()
    check_log_csv_retry_status_policy_static()
    check_google_docs_save_result_classification_helper()
    check_log_csv_compact_result_display_policy()
    check_google_docs_timeout_retry_classification_policy()
    check_invalid_generated_summary_rejected()
    check_generated_summary_without_notes_rejected()
    check_notes_only_summary_is_valid()
    check_runtime_noise_removed_from_summary_body(normalize_summary)
    check_runtime_noise_stdout_stderr_removed_but_notes_kept(normalize_summary)
    check_runtime_noise_only_summary_is_invalid()
    check_codex_exec_failure_output_is_not_valid_summary()
    check_codex_echoed_prompt_markers_do_not_shadow_summary()
    check_codex_logged_out_failure_is_actionable()
    check_codex_network_failure_pauses_batch()
    check_codex_summary_command_pins_requested_model()
    check_runtime_noise_filter_keeps_normal_counsel_sentence(normalize_summary)
    check_ambiguous_today_focus_removed_but_notes_remain_valid(normalize_summary)
    check_completed_summary_state_allows_copy_and_save()
    check_placeholder_notes_summary_is_invalid(normalize_summary)
    check_private_context_notes_only_summary_is_valid()
    check_meaningful_content_allows_copy_and_save_without_today_focus(normalize_summary)
    check_today_focus_empty_shape_policy_cases(normalize_summary)
    check_admin_notes_export_uses_notes_when_today_focus_is_absent()
    check_log_action_overlays_current_summary_on_matching_csv_row()
    check_pending_admin_summary_changes_effective_csv_history_hash()
    check_admin_notes_sync_skips_post_when_notes_are_current()
    check_log_action_replaces_existing_notes_with_focus_only_export()
    check_admin_notes_sync_backs_up_and_posts_changed_notes()
    check_log_action_auto_admin_sync_static_contract()
    check_admin_notes_export_button_static_contract()
    check_admin_target_change_button_static_contract()
    check_admin_notes_export_block_message()
    check_build_info_badge_format_and_fallbacks()
    check_app_last_modified_badge_rendered_under_title_static()
    check_runtime_path_diagnostics_static()
    check_empty_failed_summary_stays_failed_not_needs_completion()
    check_summary_section_spacing_format()
    check_summary_spacing_removes_blank_lines_between_bullets()
    check_summary_spacing_notes_only()
    check_summary_spacing_today_only()
    check_notes_generate_empty_today_focus_shape(normalize_summary)
    check_learning_flow_section_stays_above_today_focus(normalize_summary)
    check_generic_today_focus_replaced_from_notes(normalize_summary)
    check_existing_concrete_today_focus_kept_with_required_heading(normalize_summary)
    check_summary_auto_retry_empty_then_valid()
    check_summary_auto_retry_placeholder_then_valid()
    check_summary_auto_retry_notes_only_then_valid()
    check_summary_auto_retry_all_invalid_fails_cleanly()
    check_summary_retry_uses_same_transcript_signature()
    check_failed_generation_hides_previous_summary_candidate()
    check_manual_summary_candidate_accepts_meaningful_notes()
    check_manual_summary_candidate_rejects_blank_text()
    check_clipboard_copy_labels_use_full_summary_static()
    check_insufficient_transcript_blocks_auto_summary()
    check_sufficient_transcript_allows_auto_summary_flow()
    check_insufficient_transcript_status_is_not_completion()
    check_insufficient_transcript_hides_previous_summary_candidate()
    check_student_transcripts_filter_current_student_only()
    check_google_docs_mapping_registration_rows()
    check_google_docs_mapping_registration_keeps_csv_widget_run_alive()
    print(f"normalize_summary checks passed ({source})")


if __name__ == "__main__":
    main()
