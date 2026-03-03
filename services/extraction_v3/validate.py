from __future__ import annotations

from typing import Any


CRITICAL_FIELDS = ("nmck", "payment_terms_days", "execution_days", "penalty_percent_per_day")
FIELD_TO_SECTION = {
    "nmck": "price",
    "payment_terms_days": "payment",
    "execution_days": "execution",
    "penalty_percent_per_day": "liability",
}


def _is_valid(field: str, value: Any) -> bool:
    try:
        if field == "nmck":
            return isinstance(value, (int, float)) and float(value) > 0
        if field in ("payment_terms_days", "execution_days"):
            return isinstance(value, (int, float)) and int(value) > 0
        if field == "penalty_percent_per_day":
            return isinstance(value, (int, float)) and 0 <= float(value) <= 100
    except Exception:
        return False
    return False


def validate_extracted(extracted_data: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    section_presence = meta.get("section_presence") or {}
    candidate_counts = meta.get("candidate_counts") or {}
    selections = meta.get("selections") or {}
    corpus_meta = meta.get("corpus") or {}

    input_mode = str(corpus_meta.get("input_mode") or "")
    is_manual = input_mode in {"manual_text", "attachments_plus_text"}
    is_partial = bool(corpus_meta.get("is_partial"))

    missing_reasons: dict[str, str] = {}
    valid_count = 0

    for field in CRITICAL_FIELDS:
        value = extracted_data.get(field)
        if _is_valid(field, value):
            valid_count += 1
            continue

        section = FIELD_TO_SECTION[field]
        has_section = bool(section_presence.get(section))
        count_key = "payment_terms" if field == "payment_terms_days" else ("execution" if field == "execution_days" else ("penalties" if field == "penalty_percent_per_day" else field))
        has_candidates = int(candidate_counts.get(count_key) or 0) > 0
        has_selection = bool(selections.get(count_key))

        if is_manual and is_partial and not has_section:
            missing_reasons[field] = "partial_input"
        elif not has_section and not has_candidates:
            missing_reasons[field] = "not_provided_in_docs"
        elif has_candidates and not has_selection:
            missing_reasons[field] = "parse_failed"
        else:
            missing_reasons[field] = "parse_failed"

    completeness_score = int(round(valid_count * 100 / len(CRITICAL_FIELDS)))
    blocking_missing: list[str] = []
    if not _is_valid("nmck", extracted_data.get("nmck")):
        blocking_missing.append("nmck")

    return {
        "completeness_score": max(0, min(100, completeness_score)),
        "missing_reasons": missing_reasons,
        "blocking_missing": sorted(set(blocking_missing)),
    }
