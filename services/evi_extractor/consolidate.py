from __future__ import annotations

from decimal import Decimal
from typing import Any

from services.evi_extractor.candidates import Candidate


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, (list, dict, tuple, set)):
        return len(value) > 0
    return True


def _set_if_not_none(target: dict[str, Any], key: str, value: Any) -> None:
    if value is None:
        return
    target[key] = value


def _to_float(value: Any) -> float | None:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _attach_evidence(meta: dict[str, Any], field: str, candidate: Candidate | None) -> None:
    if not candidate:
        return
    evidence = meta.setdefault("evidence", {})
    evidence[field] = {
        "quote": candidate.get("quote"),
        "file": candidate.get("file"),
        "offset": candidate.get("offset"),
        "section": candidate.get("section"),
    }


def apply_consolidation(
    *,
    extracted_data: dict[str, Any],
    validated: dict[str, Any],
    input_mode: str,
) -> dict[str, Any]:
    final = validated.get("final") or {}
    meta = extracted_data.setdefault("meta", {})

    nmck_candidate = final.get("nmck")
    _attach_evidence(meta, "nmck", nmck_candidate)
    nmck_float = _to_float((nmck_candidate or {}).get("value")) if nmck_candidate else None
    if nmck_float is not None:
        extracted_data["nmck"] = nmck_float

    payment_candidate = final.get("payment_terms")
    _attach_evidence(meta, "payment_terms", payment_candidate)
    payment_value = (payment_candidate or {}).get("value") if payment_candidate else None
    if isinstance(payment_value, dict):
        conservative_days = payment_value.get("conservative_days")
        payment_days = payment_value.get("payment_days")
        days_for_legacy = conservative_days if isinstance(conservative_days, int) else payment_days
        if isinstance(days_for_legacy, (int, float)):
            extracted_data["payment_terms_days"] = int(round(days_for_legacy))

        if payment_value.get("advance_allowed") is False:
            extracted_data["advance_percent"] = 0.0
            policy = meta.setdefault("policy", {})
            policy["avoid_request_advance"] = True
        elif isinstance(payment_value.get("advance_percent"), (int, float)):
            extracted_data["advance_percent"] = float(payment_value.get("advance_percent"))

        meta.setdefault("payment", {}).update(
            {
                "payment_days": payment_value.get("payment_days"),
                "day_type": payment_value.get("day_type"),
                "working_days": payment_value.get("working_days"),
                "calendar_days": payment_value.get("calendar_days"),
                "conservative_days": payment_value.get("conservative_days"),
                "trigger": payment_value.get("trigger"),
                "advance_allowed": payment_value.get("advance_allowed"),
            }
        )

    execution_candidate = final.get("execution_days")
    _attach_evidence(meta, "execution_days", execution_candidate)
    execution_value = (execution_candidate or {}).get("value") if execution_candidate else None
    if isinstance(execution_value, dict):
        raw_days = execution_value.get("execution_days")
    else:
        raw_days = execution_value
    if isinstance(raw_days, (int, float)):
        extracted_data["execution_days"] = int(round(raw_days))

    penalties_candidate = final.get("penalties")
    _attach_evidence(meta, "penalties", penalties_candidate)
    penalties_value = (penalties_candidate or {}).get("value") if penalties_candidate else None
    if isinstance(penalties_value, dict):
        meta["penalties"] = penalties_value
        penalty_info = penalties_value.get("penalty")
        fine_info = penalties_value.get("fine")

        if isinstance(penalty_info, dict):
            penalty_percent = _to_float(penalty_info.get("percent"))
            if penalty_percent is not None:
                extracted_data["penalty_percent_per_day"] = penalty_percent
        if isinstance(fine_info, dict):
            fine_percent = _to_float(fine_info.get("percent"))
            if fine_percent is not None:
                extracted_data["fine_percent"] = fine_percent

    meta["evi_extractor"] = {
        "version": "1.0",
        "input_mode": input_mode,
        "completeness_score": validated.get("completeness_score", 0),
        "missing_reasons": validated.get("missing_reasons") or {},
        "warnings": validated.get("warnings") or [],
        "is_partial": bool(validated.get("is_partial")),
        "partial_reasons": validated.get("partial_reasons") or [],
        "is_partial_for_price": bool(validated.get("is_partial_for_price")),
    }

    # Keep previous non-empty legacy values untouched when new values are absent.
    for key in (
        "nmck",
        "payment_terms_days",
        "execution_days",
        "penalty_percent_per_day",
        "fine_percent",
        "advance_percent",
    ):
        if key not in extracted_data:
            extracted_data[key] = None
        if not _is_non_empty(extracted_data.get(key)):
            continue
        _set_if_not_none(extracted_data, key, extracted_data.get(key))

    return extracted_data
