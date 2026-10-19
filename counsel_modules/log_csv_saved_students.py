from __future__ import annotations

from counsel_modules.log_csv_processing_history import LogCsvHistoryEntry, fingerprint_log_csv_rows
from counsel_modules.log_csv_utils import log_csv_confirmed_student_keys, match_log_rows_to_docs


def confirmed_students_from_history_export(
    entry: LogCsvHistoryEntry,
    rows: list[dict[str, str]],
    docs_rows: list[dict[str, str]],
) -> set[tuple[str, str]] | None:
    if fingerprint_log_csv_rows(rows) != entry["row_hashes"]:
        return None
    confirmed_results = []
    for row, outcome, matched in zip(rows, entry["outcomes"], match_log_rows_to_docs(rows, docs_rows)):
        if outcome not in {"success", "duplicate"}:
            continue
        if matched["docs_status"] != "매칭":
            return None
        target = matched["docs_matches"][0]
        confirmed_results.append({
            **row,
            "doc_id": target.get("doc_id", ""),
            "doc_url": target.get("doc_url", ""),
            "status": "성공",
            "newly_added": outcome == "success",
            "duplicate_skipped": outcome == "duplicate",
        })
    return log_csv_confirmed_student_keys(confirmed_results)
