from __future__ import annotations

from typing import Any


def apply_financial_guard(extracted_data: dict[str, Any]) -> tuple[bool, list[str]]:
    meta = extracted_data.setdefault("meta", {})
    evi_meta = meta.get("evi_extractor") or {}

    nmck = extracted_data.get("nmck")
    nmck_ok = isinstance(nmck, (int, float)) and float(nmck) > 0
    is_partial_for_price = bool(evi_meta.get("is_partial_for_price"))

    reasons: list[str] = []
    if not nmck_ok:
        reasons.append("nmck_missing")
    if is_partial_for_price:
        reasons.append("partial_price_context")

    can_compute = nmck_ok and not is_partial_for_price
    if not can_compute:
        extracted_data["safe_cost_price"] = None
        extracted_data["roi_percent"] = None
        extracted_data["cash_gap"] = None
        meta["financials_skipped_reason"] = reasons or ["guard_blocked"]
        meta["financials_skipped_due_to_missing_nmck"] = not nmck_ok

    return can_compute, reasons
