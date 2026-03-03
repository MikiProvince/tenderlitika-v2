from __future__ import annotations

import json
from typing import Any

from services.extraction.candidates import Candidate


_FIELD_STRENGTH = {
    "nmck": {"нмцк", "нмц", "начальная (максимальная) цена"},
    "payment_terms": {"оплата", "расчет", "аванс", "предоплата"},
    "execution_days": {"срок", "поставка", "исполнения"},
    "penalties": {"пеня", "неустойк", "штраф"},
}


def _numeric(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _is_missing_or_invalid(data: dict[str, Any], field: str) -> bool:
    value = data.get(field)
    if field == "nmck":
        return not isinstance(value, (int, float)) or not (1_000 <= float(value) <= 100_000_000_000)
    if field == "payment_terms_days":
        return not isinstance(value, (int, float)) or not (1 <= float(value) <= 3650)
    if field == "execution_days":
        return not isinstance(value, (int, float)) or not (1 <= float(value) <= 5000)
    if field == "penalty_percent_per_day":
        return not isinstance(value, (int, float)) or not (0 <= float(value) <= 10)
    if field == "fine_percent":
        return not isinstance(value, (int, float)) or not (0 <= float(value) <= 100)
    return value is None


def _candidate_is_sane(candidate: Candidate) -> bool:
    field = candidate.get("field")
    value = candidate.get("value")

    if field == "nmck":
        v = _numeric(value)
        return v is not None and 1_000 <= v <= 100_000_000_000

    if field == "payment_terms":
        if not isinstance(value, dict):
            return False
        days = value.get("payment_terms_days")
        if days is None:
            return True
        return isinstance(days, (int, float)) and 1 <= float(days) <= 3650

    if field == "execution_days":
        v = _numeric(value)
        return v is not None and 1 <= v <= 5000

    if field == "penalties":
        if not isinstance(value, dict):
            return False
        per_day = value.get("penalty_percent_per_day")
        fine = value.get("fine_percent")
        if per_day is not None and (not isinstance(per_day, (int, float)) or not (0 <= float(per_day) <= 10)):
            return False
        if fine is not None and (not isinstance(fine, (int, float)) or not (0 <= float(fine) <= 100)):
            return False
        return True

    return False


def _keyword_strength(candidate: Candidate) -> int:
    field = candidate.get("field")
    strength_kw = _FIELD_STRENGTH.get(field, set())
    hits = [str(hit).lower() for hit in (candidate.get("keyword_hits") or [])]
    return sum(1 for hit in hits if any(strong in hit for strong in strength_kw))


def _stable_value_repr(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except Exception:
        return str(value)


def select_best_candidate(cands: list[Candidate]) -> Candidate | None:
    sane = [candidate for candidate in cands if _candidate_is_sane(candidate)]
    if not sane:
        return None

    sane.sort(
        key=lambda candidate: (
            -float(candidate.get("confidence") or 0.0),
            str(candidate.get("field") or ""),
            _stable_value_repr(candidate.get("value")),
            int((candidate.get("location") or {}).get("offset") or 0),
            -_keyword_strength(candidate),
            -len(candidate.get("keyword_hits") or []),
        ),
    )
    return sane[0]


def _set_meta_evidence(meta: dict[str, Any], field: str, candidate: Candidate) -> None:
    evidence = meta.setdefault("evidence", {})
    location = candidate.get("location") or {}
    evidence[field] = {
        "quote": candidate.get("quote"),
        "file": location.get("file"),
        "offset": location.get("offset"),
    }


def apply_selected_to_extracted_data(
    extracted_data: dict[str, Any],
    selected: dict[str, Candidate | None],
) -> dict[str, Any]:
    meta = extracted_data.setdefault("meta", {})

    nmck_candidate = selected.get("nmck")
    if nmck_candidate and _is_missing_or_invalid(extracted_data, "nmck"):
        extracted_data["nmck"] = float(nmck_candidate["value"])
    if nmck_candidate:
        _set_meta_evidence(meta, "nmck", nmck_candidate)

    payment_candidate = selected.get("payment")
    if payment_candidate and isinstance(payment_candidate.get("value"), dict):
        payment_value = payment_candidate["value"]
        meta["payment"] = payment_value
        payment_days = payment_value.get("payment_terms_days")
        if payment_days is not None and _is_missing_or_invalid(extracted_data, "payment_terms_days"):
            extracted_data["payment_terms_days"] = int(round(float(payment_days)))
        _set_meta_evidence(meta, "payment_terms", payment_candidate)

    execution_candidate = selected.get("execution")
    if execution_candidate and _is_missing_or_invalid(extracted_data, "execution_days"):
        extracted_data["execution_days"] = int(round(float(execution_candidate["value"])))
    if execution_candidate:
        _set_meta_evidence(meta, "execution_days", execution_candidate)

    penalties_candidate = selected.get("penalties")
    if penalties_candidate and isinstance(penalties_candidate.get("value"), dict):
        penalties_value = penalties_candidate["value"]
        meta["penalties"] = penalties_value

        if "penalty_percent_per_day" in extracted_data:
            per_day = penalties_value.get("penalty_percent_per_day")
            if per_day is not None and _is_missing_or_invalid(extracted_data, "penalty_percent_per_day"):
                extracted_data["penalty_percent_per_day"] = float(per_day)

        if "fine_percent" in extracted_data:
            fine_percent = penalties_value.get("fine_percent")
            if fine_percent is not None and _is_missing_or_invalid(extracted_data, "fine_percent"):
                extracted_data["fine_percent"] = float(fine_percent)

        _set_meta_evidence(meta, "penalties", penalties_candidate)

    return extracted_data
