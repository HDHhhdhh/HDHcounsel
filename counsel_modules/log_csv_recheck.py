from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

import streamlit as st

from counsel_modules.log_csv_processing_history import LogCsvHistoryEntry


@dataclass(frozen=True, slots=True)
class LogCsvStorageResponse:
    ok: bool
    verify_only: bool
    found_existing: bool | None


@dataclass(frozen=True, slots=True)
class LogCsvStorageCheck:
    source_index: int
    outcome: Literal["duplicate", "failure", "review"]
    message: str


@dataclass(frozen=True, slots=True)
class LogCsvRecheckActions:
    indices: tuple[int, ...]
    enabled: bool
    verify: Callable[[int], LogCsvStorageCheck]
    persist: Callable[[list[LogCsvStorageCheck]], bool]
    rerun: Callable[[], None]


def classify_log_csv_storage_check(
    source_index: int, response: LogCsvStorageResponse,
) -> LogCsvStorageCheck:
    if response.ok and response.verify_only and response.found_existing is True:
        return LogCsvStorageCheck(source_index, "duplicate", "문서에서 저장된 내용을 다시 확인했습니다.")
    if response.ok and response.verify_only and response.found_existing is False:
        return LogCsvStorageCheck(source_index, "failure", "현재 문서에 저장할 내용이 없습니다. 다시 저장해 주세요.")
    return LogCsvStorageCheck(source_index, "review", "문서 저장 여부를 다시 확인하지 못했습니다.")


def render_completed_log_csv_recheck(
    entry: LogCsvHistoryEntry, actions: LogCsvRecheckActions,
) -> None:
    if not st.button(
        "Docs 저장 다시 확인", icon=":material/refresh:",
        disabled=not actions.enabled or not actions.indices,
        key=f"log_csv_completed_recheck_{entry['csv_hash']}",
    ):
        return
    with st.spinner("Docs 저장 확인 중"):
        checks = [actions.verify(index) for index in actions.indices]
        if not actions.persist(checks):
            st.error("재확인 결과를 저장하지 못했습니다. 기존 기록은 유지됩니다.")
            return
    actions.rerun()
