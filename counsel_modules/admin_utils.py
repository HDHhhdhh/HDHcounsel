from __future__ import annotations

from datetime import date
import hashlib
import re


def admin_notes_preview_key(
    student_name: str,
    counseling_date_value: date,
    admin_sid: str,
    today_focus_text: str,
) -> str:
    digest = hashlib.sha256(today_focus_text.strip().encode("utf-8")).hexdigest()[:16]
    return f"{student_name.strip()}|{counseling_date_value.isoformat()}|{admin_sid}|{digest}"


def extract_admin_students_from_payload(payload: object) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ["students", "data", "items", "rows", "result"]:
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def admin_student_name_from_row(row: dict) -> str:
    for key in ["name", "student_name", "studentName", "student", "label"]:
        value = row.get(key)
        if value:
            return str(value).strip()
    return ""


def admin_student_sid_from_row(row: dict) -> str:
    for key in ["id", "sid", "admin_sid", "student_id", "studentId"]:
        value = row.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def admin_student_detail_from_row(row: dict) -> str:
    detail_keys = [
        "curriculum",
        "subCurriculum",
        "course",
        "class",
        "class_name",
        "className",
        "subject",
        "program",
        "group",
        "class_type",
        "lesson_type",
        "course_type",
        "수업구분",
        "강의구분",
        "구분",
        "type",
        "category",
        "level",
        "time",
        "start_time",
        "startTime",
        "day",
        "day1",
        "visitTime1",
        "day2",
        "visitTime2",
        "day3",
        "visitTime3",
        "day4",
        "visitTime4",
        "day5",
        "visitTime5",
        "schedule",
        "teacher",
    ]
    parts = []
    for key in detail_keys:
        value = row.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in parts:
            parts.append(text)
    return " · ".join(parts)


ADMIN_SID_INTERNAL_DETAIL_LABELS = {
    "수동 매핑",
    "manual",
    "manual_dropdown",
    "manual_session_label",
    "stored_label_candidate",
    "local_override",
    "auto_roster_match",
    "CSV",
}


def public_admin_sid_candidate_detail(candidate: dict[str, str]) -> str:
    detail = candidate.get("detail", "").strip()
    if detail in ADMIN_SID_INTERNAL_DETAIL_LABELS:
        return ""
    return detail


def format_admin_sid_candidate_label(candidate: dict[str, str]) -> str:
    student_name = candidate.get("student_name", "").strip()
    admin_sid = candidate.get("admin_sid", "").strip()
    detail = public_admin_sid_candidate_detail(candidate)
    parts = [part for part in [student_name, admin_sid, detail] if part]
    return " · ".join(parts)

ADMIN_SID_AUTO_MATCH_KEYWORDS = [
    "대수",
    "공통수학1",
    "공통수학2",
    "공수1",
    "공수2",
    "기하",
    "수1",
    "수2",
    "수학1",
    "수학2",
    "미적",
    "미적분",
    "확통",
    "확률과통계",
    "공통",
    "정규",
    "중등",
    "고등",
    "문법",
    "영어",
    "국어",
    "과학",
]

ADMIN_SID_SUBJECT_GROUPS = [
    ("대수", ("대수",)),
    ("공통수학1", ("공통수학1", "공수1")),
    ("공통수학2", ("공통수학2", "공수2")),
    ("수학1", ("수학1", "수1")),
    ("수학2", ("수학2", "수2")),
    ("미적분1", ("미적분1",)),
    ("미적분2", ("미적분2",)),
    ("미적분", ("미적분",)),
    ("확률과 통계", ("확률과통계", "확통")),
    ("기하", ("기하",)),
]

ADMIN_SID_TYPE_ONLY_MATCH_TERMS = {
    "특강",
    "방학특강",
    "내신특강",
    "보충특강",
    "정규",
    "정규강의",
    "보충",
    "내신",
    "수능",
    "수능특강",
    "수특",
}

ADMIN_SID_SUBJECT_MATCH_SCORE = 100
ADMIN_SID_SCHEDULE_SLOT_MATCH_SCORE = 30
ADMIN_SID_TIME_MATCH_SCORE = 25
ADMIN_SID_WEEKDAY_MATCH_SCORE = 10

ADMIN_SID_WEEKDAY_NAMES = {
    "월": "월요일",
    "화": "화요일",
    "수": "수요일",
    "목": "목요일",
    "금": "금요일",
    "토": "토요일",
    "일": "일요일",
}


def normalize_admin_match_text(value: str | None) -> str:
    return re.sub(r"\s+", "", str(value or "")).lower()


def admin_subject_keyword_in_text(normalized_text: str, normalized_keyword: str) -> bool:
    if not normalized_text or not normalized_keyword:
        return False
    if normalized_keyword == "수1":
        return re.search(r"(?<!공)수1", normalized_text) is not None
    if normalized_keyword == "수2":
        return re.search(r"(?<!공)수2", normalized_text) is not None
    if normalized_keyword == "수학1":
        return re.search(r"(?<!공통)수학1", normalized_text) is not None
    if normalized_keyword == "수학2":
        return re.search(r"(?<!공통)수학2", normalized_text) is not None
    if normalized_keyword == "미적분":
        return re.search(r"미적분(?![12])", normalized_text) is not None
    return normalized_keyword in normalized_text


def find_admin_subject_groups(value: str | None) -> list[str]:
    normalized_text = normalize_admin_match_text(value)
    matched_groups: list[str] = []
    for group_name, keywords in ADMIN_SID_SUBJECT_GROUPS:
        for keyword in keywords:
            normalized_keyword = normalize_admin_match_text(keyword)
            if admin_subject_keyword_in_text(normalized_text, normalized_keyword):
                matched_groups.append(group_name)
                break
    return matched_groups


def add_unique_match(matches: list[str], value: str) -> None:
    if value and value not in matches:
        matches.append(value)


def find_admin_schedule_tokens(value: str | None) -> list[str]:
    text = str(value or "")
    compact_text = re.sub(r"\s+", "", text)
    matches: list[str] = []

    for weekday, weekday_name in ADMIN_SID_WEEKDAY_NAMES.items():
        if f"{weekday}요일" in compact_text:
            add_unique_match(matches, weekday_name)
        if re.search(rf"(^|[\n,;/|()\[\]<>_\-]){weekday}($|[\n,;/|()\[\]<>_\-])", text):
            add_unique_match(matches, weekday_name)

    for match in re.finditer(r"([월화수목금토일])\s*([12])", text):
        weekday, slot = match.groups()
        add_unique_match(matches, f"{weekday}{slot}")
        add_unique_match(matches, ADMIN_SID_WEEKDAY_NAMES[weekday])
    for match in re.finditer(r"([월화수목금토일])([12])", compact_text):
        weekday, slot = match.groups()
        add_unique_match(matches, f"{weekday}{slot}")
        add_unique_match(matches, ADMIN_SID_WEEKDAY_NAMES[weekday])

    for match in re.finditer(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", text):
        hour, minute = match.groups()
        add_unique_match(matches, f"{int(hour):02d}:{minute}")
    return matches


def admin_schedule_match_score(label: str) -> int:
    if re.fullmatch(r"[월화수목금토일][12]", label or ""):
        return ADMIN_SID_SCHEDULE_SLOT_MATCH_SCORE
    if re.fullmatch(r"\d{2}:\d{2}", label or ""):
        return ADMIN_SID_TIME_MATCH_SCORE
    if label in ADMIN_SID_WEEKDAY_NAMES.values():
        return ADMIN_SID_WEEKDAY_MATCH_SCORE
    return 0


def admin_sid_candidate_schedule_matches(
    candidate: dict[str, str],
    context_text: str,
) -> list[str]:
    context_tokens = set(find_admin_schedule_tokens(context_text))
    if not context_tokens:
        return []
    descriptor_text = admin_sid_candidate_descriptor_text(candidate)
    if not descriptor_text.strip():
        return []
    candidate_tokens = set(find_admin_schedule_tokens(admin_sid_candidate_search_text(candidate)))
    matches = context_tokens.intersection(candidate_tokens)
    return sorted(matches, key=lambda label: (admin_schedule_match_score(label), label), reverse=True)


def admin_sid_candidate_descriptor_text(candidate: dict[str, str]) -> str:
    descriptor_parts: list[str] = []
    preferred_keys = [
        "detail",
        "source",
        "class",
        "class_name",
        "className",
        "course",
        "curriculum",
        "subject",
        "program",
        "class_type",
        "lesson_type",
        "course_type",
        "수업구분",
        "강의구분",
        "구분",
        "type",
        "category",
        "time",
        "schedule",
    ]
    for key in preferred_keys:
        value = candidate.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in descriptor_parts:
            descriptor_parts.append(text)
    for key, value in candidate.items():
        if key in {"student_name", "admin_sid"} or value is None:
            continue
        text = str(value).strip()
        if text and text not in descriptor_parts:
            descriptor_parts.append(text)
    return "\n".join(descriptor_parts)


def admin_sid_candidate_search_text(candidate: dict[str, str]) -> str:
    parts: list[str] = []
    for key in ["student_name", "admin_sid"]:
        value = candidate.get(key)
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in parts:
            parts.append(text)
    descriptor_text = admin_sid_candidate_descriptor_text(candidate)
    if descriptor_text:
        parts.append(descriptor_text)
    return "\n".join(parts)


def admin_sid_candidate_subject_matches(
    candidate: dict[str, str],
    context_text: str,
) -> list[str]:
    context_subjects = find_admin_subject_groups(context_text)
    if not context_subjects:
        return []
    descriptor_text = admin_sid_candidate_descriptor_text(candidate)
    if not descriptor_text.strip():
        return []
    candidate_subjects = find_admin_subject_groups(admin_sid_candidate_search_text(candidate))
    return [subject for subject in context_subjects if subject in candidate_subjects]


def split_admin_detail_terms(value: str | None) -> set[str]:
    raw_terms = re.split(r"[·,;/|()\[\]{}<>_\-\s]+", str(value or ""))
    return {term.strip() for term in raw_terms if len(term.strip()) >= 2}


def is_admin_type_only_match_term(value: str | None) -> bool:
    normalized_value = normalize_admin_match_text(value)
    if not normalized_value:
        return False
    for term in ADMIN_SID_TYPE_ONLY_MATCH_TERMS:
        normalized_term = normalize_admin_match_text(term)
        if normalized_value == normalized_term or normalized_term in normalized_value:
            return True
    return False


def score_admin_sid_candidate(
    candidate: dict[str, str],
    context_text: str,
) -> tuple[int, list[str]]:
    normalized_context = normalize_admin_match_text(context_text)
    if not normalized_context:
        return 0, []

    detail = admin_sid_candidate_descriptor_text(candidate)
    normalized_detail = normalize_admin_match_text(detail)
    terms = split_admin_detail_terms(detail)
    for keyword in ADMIN_SID_AUTO_MATCH_KEYWORDS:
        if normalize_admin_match_text(keyword) in normalized_detail:
            terms.add(keyword)

    score = 0
    matched_terms: list[str] = []
    subject_matches = admin_sid_candidate_subject_matches(candidate, context_text)
    if subject_matches:
        score += ADMIN_SID_SUBJECT_MATCH_SCORE * len(subject_matches)
        matched_terms.extend(subject_matches)
    schedule_matches = admin_sid_candidate_schedule_matches(candidate, context_text)
    for schedule_match in schedule_matches:
        score += admin_schedule_match_score(schedule_match)
        if schedule_match not in matched_terms:
            matched_terms.append(schedule_match)

    for term in sorted(terms, key=len, reverse=True):
        normalized_term = normalize_admin_match_text(term)
        if is_admin_type_only_match_term(term):
            continue
        if len(normalized_term) < 2 or normalized_term not in normalized_context:
            continue
        if term in matched_terms:
            continue
        weight = 5 if term in ADMIN_SID_AUTO_MATCH_KEYWORDS else 2
        score += weight
        matched_terms.append(term)

    return score, matched_terms


def auto_select_admin_sid_candidate(
    candidates: list[dict[str, str]],
    context_text: str,
) -> tuple[dict[str, str] | None, str]:
    if len(candidates) == 1:
        return candidates[0], "단일 후보"
    if len(candidates) < 1:
        return None, ""

    normalized_context = normalize_admin_match_text(context_text)
    explicit_matches: list[dict[str, str]] = []
    explicit_keys = ("admin_sid", "selected_admin_sid", "student_admin_sid", "sid", "student_id", "studentid", "id")
    for candidate in candidates:
        admin_sid = normalize_admin_match_text(candidate.get("admin_sid", ""))
        if not admin_sid:
            continue
        if any(f"{key}:{admin_sid}" in normalized_context for key in explicit_keys):
            explicit_matches.append(candidate)

    if len(explicit_matches) == 1:
        return explicit_matches[0], "명시 admin SID"

    context_subjects = find_admin_subject_groups(context_text)
    context_schedule_tokens = find_admin_schedule_tokens(context_text)
    if not context_subjects or not context_schedule_tokens:
        return None, ""

    roster_matches: list[tuple[dict[str, str], list[str], list[str]]] = []
    for candidate in candidates:
        subject_matches = admin_sid_candidate_subject_matches(candidate, context_text)
        schedule_matches = admin_sid_candidate_schedule_matches(candidate, context_text)
        if subject_matches and schedule_matches:
            roster_matches.append((candidate, subject_matches, schedule_matches))

    if len(roster_matches) == 1:
        selected_candidate, subject_matches, schedule_matches = roster_matches[0]
        reason_parts = [*subject_matches[:2], *schedule_matches[:2]]
        return selected_candidate, f"명단 대조: {', '.join(reason_parts)}"
    return None, ""
