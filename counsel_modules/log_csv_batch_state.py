from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime
from pathlib import Path
from typing import Literal, NotRequired, TypedDict

from counsel_modules.atomic_json import write_json_atomic


LogCsvBatchStatus = Literal["running", "completed", "interrupted"]


class LogCsvInFlightRequest(TypedDict):
    source_index: int
    request: NotRequired[dict[str, str]]


class LogCsvInFlightBatch(TypedDict):
    requests: list[LogCsvInFlightRequest]


class LogCsvBatchState(TypedDict):
    version: int
    upload_signature: str
    source_csv_name: str
    source_csv_size: int
    source_csv_path: str
    source_mtime_ns: int
    run_id: str
    status: LogCsvBatchStatus
    total: int
    selected_indices: list[int]
    completed_indices: list[int]
    completed_count: int
    failed_indices: list[int]
    results: list[dict[str, object]]
    current_position: int
    current_name: str
    phase: str
    started_at: str
    updated_at: str
    completed_at: str
    acknowledged_at: str
    result_log_path: str
    error: str
    in_flight: LogCsvInFlightRequest | LogCsvInFlightBatch | None


def create_log_csv_batch_state(
    *,
    upload_signature: str,
    source_csv_name: str,
    source_csv_size: int,
    source_csv_path: str,
    source_mtime_ns: int,
    selected_indices: list[int],
    started_at: str,
    run_id: str,
) -> LogCsvBatchState:
    indices = _unique_ints(selected_indices)
    return {
        "version": 1,
        "upload_signature": str(upload_signature),
        "source_csv_name": str(source_csv_name),
        "source_csv_size": int(source_csv_size),
        "source_csv_path": str(source_csv_path),
        "source_mtime_ns": int(source_mtime_ns),
        "run_id": str(run_id),
        "status": "running",
        "total": len(indices),
        "selected_indices": indices,
        "completed_indices": [],
        "completed_count": 0,
        "failed_indices": [],
        "results": [],
        "current_position": 0,
        "current_name": "",
        "phase": "저장 준비 중",
        "started_at": str(started_at),
        "updated_at": str(started_at),
        "completed_at": "",
        "acknowledged_at": "",
        "result_log_path": "",
        "error": "",
        "in_flight": None,
    }


def set_log_csv_batch_phase(
    state: LogCsvBatchState,
    *,
    current_position: int,
    current_name: str,
    phase: str,
    updated_at: str,
) -> LogCsvBatchState:
    updated = _copy_state(state)
    updated["current_position"] = max(0, int(current_position))
    updated["current_name"] = str(current_name)
    updated["phase"] = str(phase)
    updated["updated_at"] = str(updated_at)
    return updated


def log_csv_batch_in_flight_requests(
    state: LogCsvBatchState | None,
) -> list[LogCsvInFlightRequest]:
    if state is None:
        return []
    in_flight = state.get("in_flight")
    if not isinstance(in_flight, dict):
        return []
    raw_requests = in_flight.get("requests")
    candidates = raw_requests if isinstance(raw_requests, list) else [in_flight]
    requests: list[LogCsvInFlightRequest] = []
    seen: set[int] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        try:
            source_index = int(candidate.get("source_index", ""))
        except (TypeError, ValueError):
            continue
        if source_index in seen:
            continue
        seen.add(source_index)
        request: LogCsvInFlightRequest = {"source_index": source_index}
        raw_request = candidate.get("request")
        if isinstance(raw_request, dict):
            request["request"] = {
                str(key): str(value)
                for key, value in raw_request.items()
            }
        requests.append(request)
    return requests


def set_log_csv_batch_in_flight_requests(
    state: LogCsvBatchState,
    *,
    requests: list[LogCsvInFlightRequest],
    updated_at: str,
) -> LogCsvBatchState:
    updated = _copy_state(state)
    selected = set(updated["selected_indices"])
    completed = set(updated["completed_indices"])
    normalized = [
        request
        for request in log_csv_batch_in_flight_requests(
            {**updated, "in_flight": {"requests": requests}}
        )
        if request["source_index"] in selected
        and request["source_index"] not in completed
    ]
    if not normalized:
        updated["in_flight"] = None
    elif len(normalized) == 1:
        updated["in_flight"] = normalized[0]
    else:
        updated["in_flight"] = {"requests": normalized}
    updated["updated_at"] = str(updated_at)
    return updated


def record_log_csv_batch_result(
    state: LogCsvBatchState,
    *,
    source_index: int,
    result: dict[str, object],
    failed: bool,
    updated_at: str,
) -> LogCsvBatchState:
    updated = _copy_state(state)
    index = int(source_index)
    results = [
        existing
        for existing in updated["results"]
        if _result_source_index(existing) != index
    ]
    result_copy = dict(result)
    result_copy.setdefault("source_index", index)
    results.append(result_copy)
    updated["results"] = results
    updated["completed_indices"] = _ordered_completed_indices(updated, index)
    updated["completed_count"] = len(updated["completed_indices"])
    failed_indices = set(updated["failed_indices"])
    if failed:
        failed_indices.add(index)
    else:
        failed_indices.discard(index)
    updated["failed_indices"] = [
        selected_index
        for selected_index in updated["selected_indices"]
        if selected_index in failed_indices
    ]
    updated["updated_at"] = str(updated_at)
    remaining_requests = [
        request
        for request in log_csv_batch_in_flight_requests(updated)
        if request["source_index"] != index
    ]
    updated = set_log_csv_batch_in_flight_requests(
        updated,
        requests=remaining_requests,
        updated_at=updated_at,
    )
    return updated


def resume_log_csv_batch_state(
    state: LogCsvBatchState,
    *,
    updated_at: str,
) -> LogCsvBatchState:
    updated = _copy_state(state)
    updated["status"] = "running"
    updated["phase"] = "남은 작업 이어서 처리 준비 중"
    updated["updated_at"] = str(updated_at)
    updated["completed_at"] = ""
    updated["acknowledged_at"] = ""
    updated["error"] = ""
    return updated


def interrupt_log_csv_batch_state(
    state: LogCsvBatchState,
    *,
    error: str,
    updated_at: str,
) -> LogCsvBatchState:
    updated = _copy_state(state)
    updated["status"] = "interrupted"
    updated["phase"] = "처리 중단"
    updated["updated_at"] = str(updated_at)
    updated["error"] = str(error)
    return updated


def complete_log_csv_batch_state(
    state: LogCsvBatchState,
    *,
    result_log_path: str,
    updated_at: str,
) -> LogCsvBatchState:
    if set(state["selected_indices"]) - set(state["completed_indices"]):
        raise ValueError("처리하지 않은 CSV 항목이 있어 완료로 표시할 수 없습니다.")
    updated = _copy_state(state)
    updated["status"] = "completed"
    updated["phase"] = "처리 완료"
    updated["updated_at"] = str(updated_at)
    updated["completed_at"] = str(updated_at)
    updated["acknowledged_at"] = ""
    updated["result_log_path"] = str(result_log_path)
    updated["error"] = ""
    return updated


def acknowledge_log_csv_batch_state(
    state: LogCsvBatchState,
    *,
    acknowledged_at: str,
) -> LogCsvBatchState:
    if state["status"] != "completed":
        raise ValueError("완료되지 않은 CSV 작업은 확인 처리할 수 없습니다.")
    updated = _copy_state(state)
    updated["acknowledged_at"] = str(acknowledged_at)
    updated["updated_at"] = str(acknowledged_at)
    return updated


def remaining_log_csv_batch_indices(
    state: LogCsvBatchState,
    eligible_indices: list[int],
) -> list[int]:
    eligible = set(_unique_ints(eligible_indices))
    completed = set(state["completed_indices"])
    return [
        index
        for index in state["selected_indices"]
        if index in eligible and index not in completed
    ]


def log_csv_batch_state_matches(
    state: LogCsvBatchState | None,
    upload_signature: str,
) -> bool:
    return bool(
        state
        and state.get("upload_signature")
        and state.get("upload_signature") == str(upload_signature)
    )


def log_csv_batch_state_is_recently_running(
    state: LogCsvBatchState | None,
    *,
    now: str,
    max_age_seconds: float = 240.0,
) -> bool:
    if not state or state.get("status") != "running":
        return False
    try:
        now_value = datetime.fromisoformat(str(now))
        updated_value = datetime.fromisoformat(str(state.get("updated_at") or ""))
    except ValueError:
        return False
    if now_value.tzinfo is None or updated_value.tzinfo is None:
        return False
    age_seconds = (now_value - updated_value).total_seconds()
    return 0 <= age_seconds <= float(max_age_seconds)


def should_release_log_csv_session_lock(
    state: LogCsvBatchState | None,
    *,
    session_is_saving: bool,
    now: str,
    max_age_seconds: float = 240.0,
) -> bool:
    return bool(
        session_is_saving
        and not log_csv_batch_state_is_recently_running(
            state,
            now=now,
            max_age_seconds=max_age_seconds,
        )
    )


def load_log_csv_batch_state(path: Path) -> LogCsvBatchState | None:
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return None
        status = str(raw["status"])
        if status not in {"running", "completed", "interrupted"}:
            return None
        selected_indices = _unique_ints(raw["selected_indices"])
        completed_indices = _unique_ints(raw.get("completed_indices", []))
        completed_indices = [index for index in selected_indices if index in set(completed_indices)]
        failed_indices = _unique_ints(raw.get("failed_indices", []))
        failed_indices = [index for index in selected_indices if index in set(failed_indices)]
        raw_results = raw.get("results", [])
        if not isinstance(raw_results, list) or any(not isinstance(item, dict) for item in raw_results):
            return None
        return {
            "version": int(raw.get("version", 1)),
            "upload_signature": str(raw["upload_signature"]),
            "source_csv_name": str(raw.get("source_csv_name", "")),
            "source_csv_size": int(raw.get("source_csv_size", 0)),
            "source_csv_path": str(raw.get("source_csv_path", "")),
            "source_mtime_ns": int(raw.get("source_mtime_ns", 0)),
            "run_id": str(raw["run_id"]),
            "status": status,
            "total": len(selected_indices),
            "selected_indices": selected_indices,
            "completed_indices": completed_indices,
            "completed_count": len(completed_indices),
            "failed_indices": failed_indices,
            "results": [dict(item) for item in raw_results],
            "current_position": int(raw.get("current_position", 0)),
            "current_name": str(raw.get("current_name", "")),
            "phase": str(raw.get("phase", "")),
            "started_at": str(raw.get("started_at", "")),
            "updated_at": str(raw.get("updated_at", "")),
            "completed_at": str(raw.get("completed_at", "")),
            "acknowledged_at": str(raw.get("acknowledged_at", "")),
            "result_log_path": str(raw.get("result_log_path", "")),
            "error": str(raw.get("error", "")),
            "in_flight": dict(raw["in_flight"]) if isinstance(raw.get("in_flight"), dict) else None,
        }
    except (OSError, UnicodeError, json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def save_log_csv_batch_state(path: Path, state: LogCsvBatchState) -> None:
    write_json_atomic(path, state, default=str)


def _copy_state(state: LogCsvBatchState) -> LogCsvBatchState:
    return {
        "version": state["version"],
        "upload_signature": state["upload_signature"],
        "source_csv_name": state["source_csv_name"],
        "source_csv_size": state["source_csv_size"],
        "source_csv_path": state["source_csv_path"],
        "source_mtime_ns": state["source_mtime_ns"],
        "run_id": state["run_id"],
        "status": state["status"],
        "total": state["total"],
        "selected_indices": list(state["selected_indices"]),
        "completed_indices": list(state["completed_indices"]),
        "completed_count": state["completed_count"],
        "failed_indices": list(state["failed_indices"]),
        "results": [dict(item) for item in state["results"]],
        "current_position": state["current_position"],
        "current_name": state["current_name"],
        "phase": state["phase"],
        "started_at": state["started_at"],
        "updated_at": state["updated_at"],
        "completed_at": state["completed_at"],
        "acknowledged_at": state["acknowledged_at"],
        "result_log_path": state["result_log_path"],
        "error": state["error"],
        "in_flight": deepcopy(state["in_flight"]) if state.get("in_flight") else None,
    }


def _unique_ints(values: object) -> list[int]:
    if not isinstance(values, (list, tuple)):
        return []
    unique: list[int] = []
    seen: set[int] = set()
    for value in values:
        index = int(value)
        if index in seen:
            continue
        seen.add(index)
        unique.append(index)
    return unique


def _result_source_index(result: dict[str, object]) -> int | None:
    try:
        return int(result.get("source_index", ""))
    except (TypeError, ValueError):
        return None


def _ordered_completed_indices(state: LogCsvBatchState, new_index: int) -> list[int]:
    completed = set(state["completed_indices"])
    completed.add(new_index)
    return [index for index in state["selected_indices"] if index in completed]
