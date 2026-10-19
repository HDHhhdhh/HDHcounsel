from __future__ import annotations

import hashlib
import re


def clean_google_doc_url(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff").strip()


def extract_doc_id_from_url(value: str | None) -> str:
    text = clean_google_doc_url(value)
    if not text:
        return ""
    if re.fullmatch(r"[A-Za-z0-9_-]{20,}", text):
        return text
    patterns = [
        r"/document/d/([^/?#]+)",
        r"[?&]id=([^&#]+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1).strip()
    return ""


def clean_google_apps_script_url(value: str | None) -> str:
    return (value or "").strip().lstrip("\ufeff").strip()


def has_hidden_url_prefix(value: str | None) -> bool:
    return bool(value and value.strip().startswith("\ufeff"))


def is_google_docs_lock_timeout_message(message: object) -> bool:
    text = str(message or "").lower()
    return any(
        keyword in text
        for keyword in [
            "exception",
            "잠금 시간초과",
            "lockservice",
            "lock",
            "다른 프로세스",
            "timeout",
        ]
    )


def classify_google_docs_timeout_verification(verify_result: dict[str, object] | None) -> dict[str, object]:
    """Classify a read-only verify result after a write request timed out."""
    data = verify_result if isinstance(verify_result, dict) else {}
    if data.get("ok") is True and data.get("verify_only") is True and data.get("found_existing") is True:
        return {
            "status": "saved_confirmed_after_timeout",
            "user_label": "저장 확인됨 · 응답 지연",
            "failure": False,
            "timeout_unknown": False,
            "retry_recommended": False,
            "needs_review": False,
            "review_category": "saved_confirmed_after_timeout",
            "review_reason": "처음 응답은 지연됐지만, 문서에서 저장된 기록을 확인했습니다. 다시 저장하지 않아도 됩니다.",
        }

    error_type = str(data.get("error_type") or "").strip().lower()
    if error_type in {
        "permission_or_doc_not_found",
        "permission_denied",
        "doc_not_found",
        "missing_target",
        "invalid_web_app_url",
    }:
        return {
            "status": "실패",
            "user_label": "실패",
            "failure": True,
            "timeout_unknown": False,
            "retry_recommended": False,
            "needs_review": False,
            "review_category": "verify_failed",
            "review_reason": "verify-only 확인에서 문서 접근 또는 설정 오류가 확인됐습니다. 오류 사유를 확인하세요.",
        }

    message = " ".join(str(data.get(field) or "") for field in ("error_type", "message", "error"))
    if is_google_docs_lock_timeout_message(message) and any(
        keyword in message.lower()
        for keyword in ("lock", "lockservice", "잠금", "다른 프로세스")
    ):
        return {
            "status": "lock_timeout_retryable",
            "user_label": "잠금 시간초과",
            "failure": False,
            "timeout_unknown": False,
            "retry_recommended": True,
            "needs_review": False,
            "review_category": "lock_timeout",
            "review_reason": "Apps Script 잠금 충돌입니다. 전체 재실행하지 말고 해당 학생만 잠시 후 재시도하세요.",
        }

    return {
        "status": "timeout_unknown",
        "user_label": "추가 여부 불확실",
        "failure": False,
        "timeout_unknown": True,
        "retry_recommended": False,
        "needs_review": True,
        "review_category": "timeout_unknown",
        "review_reason": "응답 시간초과로 저장 여부를 확정하지 못했습니다. 문서에 이미 들어갔을 수 있으므로 Docs 확인 후 해당 학생만 재시도하세요.",
    }


def google_docs_append_key(student_name: str, counseling_date_value, summary: str) -> str:
    digest = hashlib.sha256(summary.strip().encode("utf-8")).hexdigest()[:16]
    return f"{student_name.strip()}|{counseling_date_value.isoformat()}|{digest}"
