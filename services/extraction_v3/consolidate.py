from __future__ import annotations

from typing import Any


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _set_if_present(data: dict[str, Any], field: str, value: Any) -> None:
    if value is None:
        return
    if not _is_non_empty(data.get(field)):
        data[field] = value


def apply_to_legacy(
    extracted_data: dict[str, Any],
    selections: dict[str, dict[str, Any] | None],
    meta: dict[str, Any],
) -> dict[str, Any]:
    out = extracted_data
    out.setdefault("nmck", None)
    out.setdefault("payment_terms_days", None)
    out.setdefault("execution_days", None)
    out.setdefault("penalty_percent_per_day", None)
    out.setdefault("fine_percent", None)

    meta_ref = out.setdefault("meta", {})
    meta_ref.update(meta or {})
    evidence = meta_ref.setdefault("evidence", {})

    nmck = selections.get("nmck")
    if nmck:
        value = nmck.get("value")
        if isinstance(value, (int, float)):
            _set_if_present(out, "nmck", float(value))
        evidence["nmck"] = {
            "quote": nmck.get("quote"),
            "file": nmck.get("file"),
            "offset": nmck.get("offset"),
        }

    payment = selections.get("payment_terms")
    if payment and isinstance(payment.get("value"), dict):
        value = payment["value"]
        meta_ref["payment"] = value
        pay_days = value.get("conservative_days")
        if isinstance(pay_days, (int, float)):
            _set_if_present(out, "payment_terms_days", int(round(float(pay_days))))
        evidence["payment_terms"] = {
            "quote": payment.get("quote"),
            "file": payment.get("file"),
            "offset": payment.get("offset"),
        }

    execution = selections.get("execution")
    if execution:
        value = execution.get("value")
        if isinstance(value, (int, float)):
            _set_if_present(out, "execution_days", int(round(float(value))))
        evidence["execution"] = {
            "quote": execution.get("quote"),
            "file": execution.get("file"),
            "offset": execution.get("offset"),
        }

    penalties = selections.get("penalties")
    if penalties and isinstance(penalties.get("value"), dict):
        value = penalties["value"]
        meta_ref["penalties"] = value
        if "penalty_percent_per_day" in out and isinstance(value.get("penalty_percent_per_day"), (int, float)):
            _set_if_present(out, "penalty_percent_per_day", float(value.get("penalty_percent_per_day")))
        if "fine_percent" in out and isinstance(value.get("fine_percent"), (int, float)):
            _set_if_present(out, "fine_percent", float(value.get("fine_percent")))
        evidence["penalties"] = {
            "quote": penalties.get("quote"),
            "file": penalties.get("file"),
            "offset": penalties.get("offset"),
        }

    return out
