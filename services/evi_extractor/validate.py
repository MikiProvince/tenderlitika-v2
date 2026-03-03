from __future__ import annotations

import math
from decimal import Decimal
from typing import Any

from services.evi_extractor.candidates import Candidate


_FIELDS = ("nmck", "payment_terms", "execution_days", "penalties")


def _is_empty_quote(candidate: Candidate | None) -> bool:
    if not candidate:
        return True
    quote = str(candidate.get("quote") or "").strip()
    return not quote


def _decimal_to_float(value: Any) -> float | None:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _determine_missing_reason(
    field: str,
    selected: Candidate | None,
    candidates: list[Candidate],
    conflict_fields: set[str],
) -> str | None:
    if field in conflict_fields:
        return "conflict"
    if not candidates:
        return "not_provided"
    if selected is None:
        return "parse_failed"
    return None


def validate_selection(
    *,
    selected_by_field: dict[str, Candidate | None],
    candidates_by_field: dict[str, list[Candidate]],
    input_mode: str,
) -> dict[str, Any]:
    final: dict[str, Candidate | None] = {field: None for field in _FIELDS}
    warnings: list[str] = []
    missing_reasons: dict[str, str] = {}
    partial_reasons: list[str] = []
    conflict_fields: set[str] = set()

    nmck_candidate = selected_by_field.get("nmck")
    if nmck_candidate and not _is_empty_quote(nmck_candidate):
        nmck_value = _decimal_to_float(nmck_candidate.get("value"))
        if nmck_value is None or nmck_value <= 0:
            warnings.append("nmck_non_positive_rejected")
            conflict_fields.add("nmck")
        elif not (100 <= nmck_value <= 10**12):
            warnings.append("nmck_out_of_range_rejected")
            conflict_fields.add("nmck")
        else:
            final["nmck"] = nmck_candidate
    elif nmck_candidate:
        warnings.append("nmck_missing_evidence_quote")
        conflict_fields.add("nmck")

    payment_selected = selected_by_field.get("payment_terms")
    payment_candidates = candidates_by_field.get("payment_terms") or []
    working_days: list[int] = []
    calendar_days: list[int] = []
    strict_no_advance = False

    for candidate in payment_candidates:
        value = candidate.get("value")
        if not isinstance(value, dict):
            continue
        if value.get("advance_allowed") is False:
            strict_no_advance = True
        payment_days = value.get("payment_days")
        if isinstance(payment_days, (int, float)):
            day_type = value.get("day_type")
            if day_type == "working":
                working_days.append(int(round(payment_days)))
            elif day_type == "calendar":
                calendar_days.append(int(round(payment_days)))

    if payment_selected and _is_empty_quote(payment_selected):
        warnings.append("payment_terms_missing_evidence_quote")
        conflict_fields.add("payment_terms")
        payment_selected = None

    if payment_selected:
        value = payment_selected.get("value")
        if isinstance(value, dict):
            payment_days = value.get("payment_days")
            if isinstance(payment_days, (int, float)):
                payment_days_i = int(round(payment_days))
                if payment_days_i < 1 or payment_days_i > 3650:
                    warnings.append("payment_days_out_of_range_rejected")
                    conflict_fields.add("payment_terms")
                    payment_selected = None
                else:
                    value["payment_days"] = payment_days_i
        if payment_selected and strict_no_advance:
            value = payment_selected.get("value")
            if isinstance(value, dict):
                value["advance_allowed"] = False
                if value.get("advance_percent") not in (None, 0):
                    value["advance_percent"] = 0
            lowered_quote = str(payment_selected.get("quote") or "").lower()
            if "аванс не предусмотрен" in lowered_quote:
                value = payment_selected.get("value")
                if isinstance(value, dict):
                    value["advance_allowed"] = False
                    value["advance_percent"] = 0

    if payment_selected:
        value = payment_selected.get("value")
        if isinstance(value, dict):
            conservative_days: int | None = None
            if working_days:
                working_conservative = int(math.ceil(max(working_days) * 1.4))
                conservative_days = working_conservative
                value.setdefault("working_days", max(working_days))
            if calendar_days:
                calendar_value = max(calendar_days)
                conservative_days = max(conservative_days or 0, calendar_value)
                value.setdefault("calendar_days", calendar_value)
            if conservative_days is None and isinstance(value.get("payment_days"), int):
                conservative_days = int(value["payment_days"])
            if conservative_days is not None:
                value["conservative_days"] = int(conservative_days)
            if working_days and calendar_days:
                warnings.append("payment_days_conflict_working_vs_calendar_kept_both")
        final["payment_terms"] = payment_selected

    execution_candidate = selected_by_field.get("execution_days")
    if execution_candidate and not _is_empty_quote(execution_candidate):
        value = execution_candidate.get("value")
        if isinstance(value, dict):
            execution_days = value.get("execution_days")
        else:
            execution_days = value
        if isinstance(execution_days, (int, float)) and int(round(execution_days)) > 0:
            if isinstance(value, dict):
                value["execution_days"] = int(round(execution_days))
            final["execution_days"] = execution_candidate
        else:
            warnings.append("execution_days_invalid_rejected")
            conflict_fields.add("execution_days")
    elif execution_candidate:
        warnings.append("execution_days_missing_evidence_quote")
        conflict_fields.add("execution_days")

    penalties_candidate = selected_by_field.get("penalties")
    if penalties_candidate and not _is_empty_quote(penalties_candidate):
        final["penalties"] = penalties_candidate
    elif penalties_candidate:
        warnings.append("penalties_missing_evidence_quote")
        conflict_fields.add("penalties")

    for field in _FIELDS:
        reason = _determine_missing_reason(
            field=field,
            selected=final.get(field),
            candidates=candidates_by_field.get(field) or [],
            conflict_fields=conflict_fields,
        )
        if reason:
            missing_reasons[field] = reason

    for field in _FIELDS:
        if final.get(field) is None:
            partial_reasons.append(f"missing_{field}")
    if input_mode == "manual_text" and final.get("nmck") is None:
        partial_reasons.append("manual_without_nmck")

    completeness_count = sum(1 for field in _FIELDS if final.get(field) is not None)
    completeness_score = int(round(completeness_count * 100 / len(_FIELDS)))
    is_partial = bool(partial_reasons)
    is_partial_for_price = final.get("nmck") is None

    return {
        "final": final,
        "missing_reasons": missing_reasons,
        "warnings": warnings,
        "completeness_score": max(0, min(100, completeness_score)),
        "is_partial": is_partial,
        "partial_reasons": sorted(set(partial_reasons)),
        "is_partial_for_price": is_partial_for_price,
    }
