"""Collect human-review ASR misrecognition candidates from lab JSON outputs.

This script reads transcript text from ASR lab JSON files and proposes
candidate terms for manual review. It never updates correction rules
automatically and does not import the production app.
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any


LAB_DIR = Path(__file__).resolve().parent
DEFAULT_INPUT_DIR = LAB_DIR / "sample_outputs"
DEFAULT_OUT_DIR = LAB_DIR / "sample_outputs"
DEFAULT_KNOWN_TERMS = LAB_DIR / "asr_known_terms.json"

TOKEN_RE = re.compile(r"[A-Za-z0-9:]+|[가-힣]+")
STOPWORDS = {
    "그",
    "네",
    "어",
    "아",
    "자",
    "이제",
    "그럼",
    "그냥",
    "근데",
    "아니",
    "오늘",
    "지금",
    "제가",
    "너무",
    "정도",
    "이런",
    "저",
}
DOMAIN_ALIASES = {
    "A:ble": ["에이블", "에이 블", "에이벌"],
    "APEX": ["에이팩스", "에이펙스", "아펙스", "에펙스"],
}
KOREAN_PARTICLES = (
    "은",
    "는",
    "이",
    "가",
    "을",
    "를",
    "과",
    "와",
    "랑",
    "하고",
    "도",
    "만",
    "에",
    "에서",
    "으로",
    "로",
    "부터",
    "까지",
)
SHORT_GENERAL_TERMS = {
    "공부",
    "문제",
    "숙제",
    "시험",
    "프린트",
    "페이지",
    "친구",
    "엄마",
    "선생님",
    "수업",
}


@dataclass(frozen=True)
class TextRecord:
    label: str
    source_file: Path
    text: str


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def load_known_terms(path: Path) -> list[str]:
    payload = load_json(path)
    if not isinstance(payload, list):
        raise ValueError("Known terms must be a JSON list.")
    terms = [str(item).strip() for item in payload if str(item).strip()]
    if not terms:
        raise ValueError("Known terms list is empty.")
    return terms


def normalize_for_match(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]+", "", value).lower()


def safe_stem(value: str) -> str:
    cleaned = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in value)
    return cleaned.strip("_") or "asr_candidates"


def iter_json_files(input_json: str | None, input_dir: Path) -> list[Path]:
    if input_json:
        return [Path(input_json).expanduser().resolve()]
    if not input_dir.exists():
        return []
    files: list[Path] = []
    for path in sorted(input_dir.glob("*.json")):
        name = path.name
        if any(
            marker in name
            for marker in (
                "misrecognition_candidates",
                "high_confidence_candidates",
                "excluded_candidates",
                "funasr_diagnose",
            )
        ):
            continue
        files.append(path.resolve())
    return files


def extract_text_records(path: Path) -> list[TextRecord]:
    try:
        payload = load_json(path)
    except Exception:
        return []

    records: list[TextRecord] = []
    if isinstance(payload, dict) and isinstance(payload.get("results"), list):
        for index, item in enumerate(payload["results"], start=1):
            if not isinstance(item, dict) or not isinstance(item.get("text"), str):
                continue
            label_parts = [
                str(item.get("provider", "")).strip(),
                str(item.get("model", "")).strip(),
                str(item.get("compute_type", "")).strip(),
            ]
            vad = item.get("vad_filter")
            if vad is not None:
                label_parts.append(f"vad={vad}")
            label = " / ".join(part for part in label_parts if part) or f"result_{index}"
            records.append(TextRecord(label=label, source_file=path, text=item["text"]))

    if isinstance(payload, dict) and isinstance(payload.get("text"), str) and payload["text"].strip():
        label = str(payload.get("provider", "root_text"))
        records.append(TextRecord(label=label, source_file=path, text=payload["text"]))

    if isinstance(payload, dict) and isinstance(payload.get("result"), dict):
        result = payload["result"]
        if isinstance(result.get("text"), str) and result["text"].strip():
            label = str(result.get("provider", "result_text"))
            records.append(TextRecord(label=label, source_file=path, text=result["text"]))

    return records


def tokenize(text: str) -> list[str]:
    return TOKEN_RE.findall(text)


def ngrams(tokens: list[str], max_n: int = 4) -> list[str]:
    items: list[str] = []
    for size in range(1, max_n + 1):
        for index in range(0, len(tokens) - size + 1):
            gram_tokens = tokens[index : index + size]
            if all(token in STOPWORDS for token in gram_tokens):
                continue
            joined = " ".join(gram_tokens).strip()
            if len(normalize_for_match(joined)) < 2:
                continue
            items.append(joined)
    return items


def snippet_around(text: str, phrase: str, width: int = 34) -> str:
    index = text.find(phrase)
    if index < 0:
        compact = re.sub(r"\s+", " ", text).strip()
        return compact[: width * 2].strip()
    start = max(index - width, 0)
    end = min(index + len(phrase) + width, len(text))
    snippet = re.sub(r"\s+", " ", text[start:end]).strip()
    return snippet


def sensitive_like(phrase: str, snippets: list[str]) -> bool:
    compact = normalize_for_match(phrase)
    if re.fullmatch(r"[가-힣]{2,3}", compact):
        context = " ".join(snippets)
        if re.search(r"학생|어머님|아버님|부모|친구|선생님|이름", context):
            return True
    return bool(re.search(r"\d{2,}", phrase))


def known_term_variants(term: str) -> list[str]:
    variants = [term, term.replace(" ", "")]
    variants.extend(DOMAIN_ALIASES.get(term, []))
    return list(dict.fromkeys(variant for variant in variants if variant))


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize_for_match(a), normalize_for_match(b)).ratio()


def collect_phrase_stats(records: list[TextRecord]) -> tuple[Counter[str], dict[str, set[str]], dict[str, list[str]]]:
    counts: Counter[str] = Counter()
    sources: dict[str, set[str]] = defaultdict(set)
    snippets: dict[str, list[str]] = defaultdict(list)
    for record in records:
        text = record.text
        tokens = tokenize(text)
        seen_in_record: set[str] = set()
        for phrase in ngrams(tokens):
            counts[phrase] += 1
            sources[phrase].add(record.source_file.name)
            if phrase not in seen_in_record and len(snippets[phrase]) < 3:
                snippets[phrase].append(snippet_around(text, phrase))
                seen_in_record.add(phrase)
    return counts, sources, snippets


def base_candidate(
    phrase: str,
    count: int,
    sources: dict[str, set[str]],
    snippets: dict[str, list[str]],
    candidate_type: str,
    suggested_term: str = "",
    score: float = 0.0,
) -> dict[str, Any]:
    return {
        "candidate": phrase,
        "suggested_term": suggested_term,
        "candidate_type": candidate_type,
        "count": count,
        "source_files": sorted(sources[phrase]),
        "nearby_snippets": snippets[phrase],
        "similarity": round(score, 3),
        "review_only": True,
        "sensitive_like": sensitive_like(phrase, snippets[phrase]),
        "auto_rule_allowed": False,
        "confidence_bucket": "unclassified",
        "confidence_reason": "",
        "exclude_reason": "",
    }


def collect_candidates(records: list[TextRecord], known_terms: list[str], min_count: int) -> list[dict[str, Any]]:
    counts, sources, snippets = collect_phrase_stats(records)
    candidates: dict[tuple[str, str], dict[str, Any]] = {}
    known_norms = {normalize_for_match(term) for term in known_terms}

    for phrase, count in counts.items():
        if count < min_count:
            continue
        normalized = normalize_for_match(phrase)
        if normalized in known_norms:
            continue
        candidates[(phrase, "frequent_phrase")] = base_candidate(
            phrase,
            count,
            sources,
            snippets,
            "frequent_phrase",
        )

    phrase_items = list(counts.items())
    for known_term in known_terms:
        variants = known_term_variants(known_term)
        term_norm = normalize_for_match(known_term)
        for phrase, count in phrase_items:
            if count < 1:
                continue
            phrase_norm = normalize_for_match(phrase)
            if phrase == known_term:
                continue
            alias_hit = any(normalize_for_match(variant) == phrase_norm for variant in variants[1:])
            spacing_variant = phrase_norm == term_norm and phrase != known_term
            best_score = max(similarity(phrase, variant) for variant in variants)
            if not alias_hit and not spacing_variant and best_score < 0.72:
                continue
            candidates[(phrase, f"known:{known_term}")] = base_candidate(
                phrase,
                count,
                sources,
                snippets,
                "known_term_similarity",
                suggested_term=known_term,
                score=best_score,
            )

    return sorted(
        candidates.values(),
        key=lambda item: (
            item["sensitive_like"],
            -item["count"],
            -float(item["similarity"]),
            item["candidate_type"],
            item["candidate"],
        ),
    )


def ends_with_particle_variant(candidate_norm: str, term_norm: str) -> bool:
    if not candidate_norm.startswith(term_norm) or candidate_norm == term_norm:
        return False
    suffix = candidate_norm[len(term_norm) :]
    return suffix in KOREAN_PARTICLES


def looks_like_name(candidate: str, snippets: list[str]) -> bool:
    compact = normalize_for_match(candidate)
    if not re.fullmatch(r"[가-힣]{2,3}", compact):
        return False
    context = " ".join(snippets)
    return bool(re.search(r"학생|어머님|아버님|부모|친구|선생님|이름", context))


def classify_known_term_candidate(candidate: dict[str, Any]) -> tuple[str, str, str]:
    phrase = str(candidate["candidate"])
    suggested = str(candidate.get("suggested_term", ""))
    phrase_norm = normalize_for_match(phrase)
    target_norm = normalize_for_match(suggested)
    if not suggested:
        return "excluded", "", "no_suggested_known_term"

    if candidate.get("sensitive_like") or looks_like_name(phrase, candidate.get("nearby_snippets", [])):
        return "excluded", "", "possible_name_or_sensitive_like"

    if ends_with_particle_variant(phrase_norm, target_norm):
        return "excluded", "", "particle_attached_to_known_term"

    if target_norm and target_norm in phrase_norm and phrase_norm != target_norm:
        return "excluded", "", "contains_known_term_with_extra_context"

    if phrase_norm in {normalize_for_match(term) for term in SHORT_GENERAL_TERMS}:
        return "excluded", "", "short_general_or_partial_term"

    length_diff_ratio = abs(len(phrase_norm) - len(target_norm)) / max(len(target_norm), 1)
    if length_diff_ratio > 0.55:
        return "excluded", "", "length_difference_too_large"

    variants = known_term_variants(suggested)
    alias_hit = any(normalize_for_match(variant) == phrase_norm for variant in variants[1:])
    spacing_variant = phrase_norm == target_norm and phrase != suggested
    score = float(candidate.get("similarity") or 0.0)

    if alias_hit:
        return "high_confidence", "known_alias_or_pronunciation_variant", ""
    if spacing_variant:
        return "high_confidence", "spacing_or_case_variant", ""
    if score >= 0.80 and len(tokenize(phrase)) <= 3:
        return "high_confidence", "close_known_term_similarity", ""

    return "excluded", "", "low_similarity_or_context_dependent"


def classify_frequent_candidate(candidate: dict[str, Any]) -> tuple[str, str, str]:
    phrase = str(candidate["candidate"])
    phrase_norm = normalize_for_match(phrase)
    if candidate.get("sensitive_like") or looks_like_name(phrase, candidate.get("nearby_snippets", [])):
        return "excluded", "", "possible_name_or_sensitive_like"
    if phrase_norm in {normalize_for_match(term) for term in SHORT_GENERAL_TERMS}:
        return "excluded", "", "short_general_or_partial_term"
    if len(tokenize(phrase)) < 2:
        return "excluded", "", "single_general_phrase"
    return "excluded", "", "frequent_phrase_requires_manual_context_review"


def split_candidate_buckets(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    high_confidence: list[dict[str, Any]] = []
    excluded: list[dict[str, Any]] = []
    for candidate in candidates:
        if candidate["candidate_type"] == "known_term_similarity":
            bucket, confidence_reason, exclude_reason = classify_known_term_candidate(candidate)
        else:
            bucket, confidence_reason, exclude_reason = classify_frequent_candidate(candidate)

        candidate["confidence_bucket"] = bucket
        candidate["confidence_reason"] = confidence_reason
        candidate["exclude_reason"] = exclude_reason
        if bucket == "high_confidence":
            high_confidence.append(candidate)
        else:
            excluded.append(candidate)

    high_confidence.sort(key=lambda item: (-item["count"], -float(item["similarity"]), item["candidate"]))
    excluded.sort(key=lambda item: (item["exclude_reason"], -item["count"], item["candidate"]))
    return high_confidence, excluded


def write_csv(path: Path, candidates: list[dict[str, Any]]) -> None:
    fieldnames = [
        "candidate",
        "suggested_term",
        "candidate_type",
        "confidence_bucket",
        "confidence_reason",
        "exclude_reason",
        "count",
        "similarity",
        "sensitive_like",
        "auto_rule_allowed",
        "source_files",
        "nearby_snippets",
    ]
    with path.open("w", newline="", encoding="utf-8-sig") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=fieldnames)
        writer.writeheader()
        for item in candidates:
            row = dict(item)
            row["source_files"] = " | ".join(item.get("source_files", []))
            row["nearby_snippets"] = " | ".join(item.get("nearby_snippets", []))
            writer.writerow({key: row.get(key, "") for key in fieldnames})


def write_candidate_json(path: Path, payload: dict[str, Any], key: str, candidates: list[dict[str, Any]]) -> None:
    data = dict(payload)
    data["candidate_count"] = len(candidates)
    data[key] = candidates
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Collect human-review ASR misrecognition candidates.")
    parser.add_argument("--input-json", default=None, help="Optional single ASR lab JSON file.")
    parser.add_argument("--input-dir", default=str(DEFAULT_INPUT_DIR), help="Directory of ASR lab JSON files.")
    parser.add_argument("--out", default=str(DEFAULT_OUT_DIR), help="Directory for candidates JSON/CSV output.")
    parser.add_argument("--min-count", type=int, default=2, help="Minimum repeated n-gram count.")
    parser.add_argument("--known-terms", default=str(DEFAULT_KNOWN_TERMS), help="Known terms JSON path.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    started_at = time.monotonic()
    input_dir = Path(args.input_dir).expanduser().resolve()
    out_dir = Path(args.out).expanduser().resolve()
    known_terms_path = Path(args.known_terms).expanduser().resolve()
    known_terms = load_known_terms(known_terms_path)
    input_files = iter_json_files(args.input_json, input_dir)

    records: list[TextRecord] = []
    for path in input_files:
        records.extend(extract_text_records(path))

    candidates = collect_candidates(records, known_terms, max(args.min_count, 1))
    high_confidence, excluded = split_candidate_buckets(candidates)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    stem = safe_stem(Path(args.input_json).stem) if args.input_json else "sample_outputs"
    candidates_json_path = out_dir / f"{timestamp}_{stem}_misrecognition_candidates.json"
    candidates_csv_path = out_dir / f"{timestamp}_{stem}_misrecognition_candidates.csv"
    high_json_path = out_dir / f"{timestamp}_{stem}_high_confidence_candidates.json"
    high_csv_path = out_dir / f"{timestamp}_{stem}_high_confidence_candidates.csv"
    excluded_json_path = out_dir / f"{timestamp}_{stem}_excluded_candidates.json"
    excluded_csv_path = out_dir / f"{timestamp}_{stem}_excluded_candidates.csv"
    out_dir.mkdir(parents=True, exist_ok=True)

    base_payload = {
        "input_json": str(Path(args.input_json).expanduser().resolve()) if args.input_json else "",
        "input_dir": str(input_dir),
        "known_terms_path": str(known_terms_path),
        "min_count": max(args.min_count, 1),
        "source_file_count": len(input_files),
        "text_record_count": len(records),
        "elapsed_sec": round(time.monotonic() - started_at, 3),
    }
    summary_payload = {
        **base_payload,
        "candidate_count": len(candidates),
        "high_confidence_count": len(high_confidence),
        "excluded_count": len(excluded),
        "candidates": candidates,
        "high_confidence_candidates_path": str(high_json_path),
        "excluded_candidates_path": str(excluded_json_path),
    }
    candidates_json_path.write_text(json.dumps(summary_payload, ensure_ascii=False, indent=2), encoding="utf-8")
    write_csv(candidates_csv_path, candidates)
    write_candidate_json(high_json_path, base_payload, "high_confidence_candidates", high_confidence)
    write_csv(high_csv_path, high_confidence)
    write_candidate_json(excluded_json_path, base_payload, "excluded_candidates", excluded)
    write_csv(excluded_csv_path, excluded)

    print(f"json={candidates_json_path}")
    print(f"csv={candidates_csv_path}")
    print(f"high_confidence_json={high_json_path}")
    print(f"high_confidence_csv={high_csv_path}")
    print(f"excluded_json={excluded_json_path}")
    print(f"excluded_csv={excluded_csv_path}")
    print(f"records={len(records)}")
    print(f"candidate_count={len(candidates)}")
    print(f"high_confidence_count={len(high_confidence)}")
    print(f"excluded_count={len(excluded)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
