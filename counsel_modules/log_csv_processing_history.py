from __future__ import annotations

import hashlib
import json
from collections import Counter
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Literal, TypedDict, assert_never

from counsel_modules.atomic_json import write_json_atomic


LogCsvHistoryOutcome = Literal[
    "pending",
    "success",
    "duplicate",
    "excluded",
    "failure",
    "review",
]
LogCsvHistoryStatus = Literal["incomplete", "completed", "needs_review"]


class LogCsvProcessingHistoryError(RuntimeError):
    pass


class LogCsvHistoryEntry(TypedDict):
    version: int
    csv_hash: str
    source_date: str
    row_hashes: list[str]
    outcomes: list[LogCsvHistoryOutcome]
    total_count: int
    resolved_count: int
    success_count: int
    duplicate_count: int
    excluded_count: int
    failed_count: int
    review_count: int
    new_row_count: int
    status: LogCsvHistoryStatus
    started_at: str
    updated_at: str
    completed_at: str


class LogCsvProcessingHistory(TypedDict):
    version: int
    entries: list[LogCsvHistoryEntry]


class LogCsvHistoryDaySummary(TypedDict):
    source_date: str
    status: Literal["completed", "incomplete"]
    resolved_count: int
    total_count: int
    updated_at: str
    has_history: bool


@dataclass(frozen=True, slots=True)
class LogCsvHistoryStart:
    csv_hash: str
    row_hashes: tuple[str, ...]
    selected_indices: tuple[int, ...]
    review_indices: tuple[int, ...]
    started_at: str
    new_row_count: int
    source_date: str = ""


@dataclass(frozen=True, slots=True)
class LogCsvHistoryUpdate:
    source_index: int
    outcome: LogCsvHistoryOutcome
    updated_at: str


def empty_log_csv_processing_history() -> LogCsvProcessingHistory:
    return {"version": 1, "entries": []}


def csv_bytes_sha256(raw_bytes: bytes) -> str:
    return hashlib.sha256(raw_bytes).hexdigest()


def fingerprint_log_csv_rows(rows: list[dict[str, str]]) -> list[str]:
    fingerprints: list[str] = []
    for row in rows:
        normalized = {
            str(key).strip().lstrip("\ufeff"): str(value or "").strip()
            for key, value in row.items()
        }
        canonical = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        fingerprints.append(hashlib.sha256(canonical.encode("utf-8")).hexdigest())
    return fingerprints


def log_csv_history_source_indices(item: dict[str, object]) -> list[int]:
    source_values = list(item.get("merged_homework_items") or [])
    if not source_values:
        source_values = [item.get("row_index")]
    indices: list[int] = []
    for value in source_values:
        try:
            source_index = int(str(value).strip()) - 1
        except (TypeError, ValueError):
            continue
        if source_index >= 0 and source_index not in indices:
            indices.append(source_index)
    return indices


def load_log_csv_processing_history(path: Path) -> LogCsvProcessingHistory:
    if not path.is_file():
        return empty_log_csv_processing_history()
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise LogCsvProcessingHistoryError(
            "CSV 처리 이력 파일을 읽을 수 없습니다."
        ) from exc
    if not isinstance(raw, dict) or not isinstance(raw.get("entries"), list):
        raise LogCsvProcessingHistoryError("CSV 처리 이력 파일 형식이 올바르지 않습니다.")
    try:
        entries = []
        for item in raw["entries"]:
            parsed = _parse_entry(item)
            if parsed is None:
                raise LogCsvProcessingHistoryError(
                    "CSV 처리 이력 항목 형식이 올바르지 않습니다."
                )
            entries.append(parsed)
        return {"version": 1, "entries": entries}
    except (TypeError, ValueError) as exc:
        raise LogCsvProcessingHistoryError(
            "CSV 처리 이력 항목을 해석할 수 없습니다."
        ) from exc


def save_log_csv_processing_history(path: Path, history: LogCsvProcessingHistory) -> None:
    write_json_atomic(path, history)


def find_log_csv_history_entry(
    history: LogCsvProcessingHistory,
    csv_hash: str,
) -> LogCsvHistoryEntry | None:
    return next(
        (entry for entry in reversed(history["entries"]) if entry["csv_hash"] == csv_hash),
        None,
    )


def log_csv_history_is_completed(entry: LogCsvHistoryEntry) -> bool:
    return entry["status"] == "completed"


def log_csv_history_processing_is_finished(entry: LogCsvHistoryEntry) -> bool:
    match entry["status"]:
        case "completed" | "needs_review":
            return True
        case "incomplete":
            return False
        case unreachable:
            assert_never(unreachable)


def previous_log_csv_operation_dates(
    reference_date: date,
    count: int = 3,
) -> list[date]:
    operation_weekdays = {0, 2, 4, 5, 6}
    result: list[date] = []
    candidate = reference_date
    while len(result) < max(0, int(count)):
        if candidate.weekday() in operation_weekdays:
            result.append(candidate)
        candidate -= timedelta(days=1)
    return result


def recent_log_csv_history_day_summaries(
    history: LogCsvProcessingHistory,
    *,
    reference_date: date,
    count: int = 3,
) -> list[LogCsvHistoryDaySummary]:
    summaries: list[LogCsvHistoryDaySummary] = []
    for operation_date in previous_log_csv_operation_dates(reference_date, count):
        source_date = operation_date.isoformat()
        entry = next(
            (
                candidate
                for candidate in reversed(history["entries"])
                if candidate.get("source_date") == source_date
            ),
            None,
        )
        summaries.append(
            {
                "source_date": source_date,
                "status": (
                    "completed"
                    if entry is not None and log_csv_history_is_completed(entry)
                    else "incomplete"
                ),
                "resolved_count": int(entry.get("resolved_count") or 0) if entry else 0,
                "total_count": int(entry.get("total_count") or 0) if entry else 0,
                "updated_at": (
                    str(entry.get("completed_at") or entry.get("updated_at") or "")
                    if entry
                    else ""
                ),
                "has_history": entry is not None,
            }
        )
    return summaries


def log_csv_history_can_seed_from_completed_batch(
    entry: LogCsvHistoryEntry,
    *,
    batch_status: str,
    selected_indices: list[int],
    result_indices: set[int],
    matched_count: int,
) -> bool:
    return bool(
        batch_status == "completed"
        and selected_indices
        and all(0 <= index < matched_count for index in selected_indices)
        and set(selected_indices).issubset(result_indices)
        and not any(
            outcome in {"success", "duplicate", "failure"}
            for outcome in entry["outcomes"]
        )
    )


def count_new_log_csv_rows(
    history: LogCsvProcessingHistory,
    current_csv_hash: str,
    current_row_hashes: list[str],
) -> int:
    completed = [
        entry
        for entry in history["entries"]
        if entry["status"] == "completed" and entry["csv_hash"] != current_csv_hash
    ]
    if not completed:
        return 0
    baseline = max(completed, key=lambda entry: entry["completed_at"] or entry["updated_at"])
    baseline_counts = Counter(baseline["row_hashes"])
    current_counts = Counter(current_row_hashes)
    return sum((current_counts - baseline_counts).values())


def prepare_log_csv_history_entry(
    history: LogCsvProcessingHistory,
    start: LogCsvHistoryStart,
) -> LogCsvHistoryEntry:
    existing = find_log_csv_history_entry(history, start.csv_hash)
    same_rows = bool(existing and existing["row_hashes"] == list(start.row_hashes))
    outcomes = list(existing["outcomes"]) if same_rows and existing else ["excluded"] * len(start.row_hashes)
    source_date = (
        _normalize_source_date(start.source_date)
        or (str(existing.get("source_date") or "") if same_rows and existing else "")
        or _source_date_from_timestamps(start.started_at)
    )
    selected = set(start.selected_indices)
    review = set(start.review_indices)
    for index in range(len(outcomes)):
        if index in selected and outcomes[index] not in {"success", "duplicate"}:
            outcomes[index] = "pending"
        elif index in review and outcomes[index] not in {"success", "duplicate"}:
            outcomes[index] = "review"
    entry: LogCsvHistoryEntry = {
        "version": 1,
        "csv_hash": start.csv_hash,
        "source_date": source_date,
        "row_hashes": list(start.row_hashes),
        "outcomes": outcomes,
        "total_count": len(outcomes),
        "resolved_count": 0,
        "success_count": 0,
        "duplicate_count": 0,
        "excluded_count": 0,
        "failed_count": 0,
        "review_count": 0,
        "new_row_count": existing["new_row_count"] if existing else max(0, start.new_row_count),
        "status": "incomplete",
        "started_at": existing["started_at"] if existing else start.started_at,
        "updated_at": start.started_at,
        "completed_at": "",
    }
    return _summarize_entry(entry, outcomes, start.started_at)


def record_log_csv_history_outcome(
    entry: LogCsvHistoryEntry,
    update: LogCsvHistoryUpdate,
) -> LogCsvHistoryEntry:
    outcomes = list(entry["outcomes"])
    if update.source_index < 0 or update.source_index >= len(outcomes):
        raise IndexError("CSV history source index is out of range")
    outcomes[update.source_index] = update.outcome
    return _summarize_entry(entry, outcomes, update.updated_at)


def finalize_log_csv_history_entry(
    entry: LogCsvHistoryEntry,
    updated_at: str,
) -> LogCsvHistoryEntry:
    return _summarize_entry(entry, list(entry["outcomes"]), updated_at)


def unresolved_log_csv_history_indices(entry: LogCsvHistoryEntry) -> list[int]:
    return [
        index
        for index, outcome in enumerate(entry["outcomes"])
        if outcome in {"pending", "failure", "review"}
    ]


def upsert_log_csv_history_entry(
    history: LogCsvProcessingHistory,
    entry: LogCsvHistoryEntry,
) -> LogCsvProcessingHistory:
    entries = [item for item in history["entries"] if item["csv_hash"] != entry["csv_hash"]]
    entries.append(entry)
    return {"version": 1, "entries": entries}


def _summarize_entry(
    entry: LogCsvHistoryEntry,
    outcomes: list[LogCsvHistoryOutcome],
    updated_at: str,
) -> LogCsvHistoryEntry:
    counts = Counter(outcomes)
    pending_count = counts["pending"]
    failed_count = counts["failure"]
    review_count = counts["review"]
    status: LogCsvHistoryStatus = (
        "incomplete"
        if pending_count
        else "needs_review"
        if failed_count or review_count
        else "completed"
    )
    return {
        **entry,
        "outcomes": list(outcomes),
        "total_count": len(outcomes),
        "resolved_count": len(outcomes) - pending_count,
        "success_count": counts["success"],
        "duplicate_count": counts["duplicate"],
        "excluded_count": counts["excluded"],
        "failed_count": failed_count,
        "review_count": review_count,
        "status": status,
        "updated_at": str(updated_at),
        "completed_at": str(updated_at) if status == "completed" else "",
    }


def _parse_entry(raw: object) -> LogCsvHistoryEntry | None:
    if not isinstance(raw, dict):
        return None
    row_hashes = raw.get("row_hashes")
    outcomes = raw.get("outcomes")
    if not isinstance(row_hashes, list) or not isinstance(outcomes, list):
        return None
    if len(row_hashes) != len(outcomes) or any(not isinstance(value, str) for value in row_hashes):
        return None
    valid_outcomes = {"pending", "success", "duplicate", "excluded", "failure", "review"}
    if any(value not in valid_outcomes for value in outcomes):
        return None
    entry: LogCsvHistoryEntry = {
        "version": 1,
        "csv_hash": str(raw.get("csv_hash") or ""),
        "source_date": (
            _normalize_source_date(raw.get("source_date"))
            or _source_date_from_timestamps(
                raw.get("started_at"),
                raw.get("updated_at"),
                raw.get("completed_at"),
            )
        ),
        "row_hashes": [str(value) for value in row_hashes],
        "outcomes": list(outcomes),
        "total_count": len(outcomes),
        "resolved_count": 0,
        "success_count": 0,
        "duplicate_count": 0,
        "excluded_count": 0,
        "failed_count": 0,
        "review_count": 0,
        "new_row_count": max(0, int(raw.get("new_row_count") or 0)),
        "status": "incomplete",
        "started_at": str(raw.get("started_at") or ""),
        "updated_at": str(raw.get("updated_at") or ""),
        "completed_at": "",
    }
    if not entry["csv_hash"]:
        return None
    summarized = _summarize_entry(entry, list(outcomes), entry["updated_at"])
    if summarized["status"] == "completed":
        summarized["completed_at"] = str(raw.get("completed_at") or summarized["updated_at"])
    return summarized


def _normalize_source_date(value: object) -> str:
    try:
        return date.fromisoformat(str(value or "").strip()).isoformat()
    except ValueError:
        return ""


def _source_date_from_timestamps(*values: object) -> str:
    parsed_dates: list[date] = []
    for value in values:
        try:
            parsed_dates.append(datetime.fromisoformat(str(value or "").strip()).date())
        except ValueError:
            continue
    return min(parsed_dates).isoformat() if parsed_dates else ""
