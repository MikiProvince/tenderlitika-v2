from __future__ import annotations

import re
from typing import Any

from services.extraction.normalize import normalize_text


SECTION_KEYWORDS = {
    "price": [
        "нмцк",
        "нмц",
        "начальная (максимальная) цена",
        "цена договора",
        "цена контракта",
        "цена лота",
    ],
    "payment": [
        "оплата",
        "расчет",
        "аванс",
        "предоплата",
        "окончательный расчет",
        "платеж",
    ],
    "execution": [
        "срок поставки",
        "срок исполнения",
        "отгруз",
        "поставка",
        "партия",
    ],
    "liability": [
        "ответственность",
        "неустойк",
        "пеня",
        "штраф",
    ],
}

FIELD_TO_SECTION = {
    "nmck": "price",
    "payment_terms_days": "payment",
    "execution_days": "execution",
    "penalty_percent_per_day": "liability",
}

CRITICAL_FIELDS = ["nmck", "payment_terms_days", "execution_days", "penalty_percent_per_day"]


def _count_keyword_hits(text: str, keywords: list[str]) -> int:
    total = 0
    for keyword in keywords:
        total += len(re.findall(re.escape(keyword), text, flags=re.IGNORECASE))
    return total


def _is_valid_numeric(field: str, value: Any) -> bool:
    if not isinstance(value, (int, float)):
        return False
    if field == "nmck":
        return float(value) > 0
    if field in ("payment_terms_days", "execution_days"):
        return float(value) > 0
    if field == "penalty_percent_per_day":
        return 0 < float(value) <= 100
    return False


def analyze_corpus(corpus_text: str, extracted_data: dict[str, Any], input_mode: str) -> dict[str, Any]:
    text = normalize_text(corpus_text or "")
    keyword_hits = {section: _count_keyword_hits(text, keywords) for section, keywords in SECTION_KEYWORDS.items()}

    has_price_section = keyword_hits["price"] > 0
    has_payment_section = keyword_hits["payment"] > 0
    has_execution_section = keyword_hits["execution"] > 0
    has_liability_section = keyword_hits["liability"] > 0

    sections_present = sum(
        [
            has_price_section,
            has_payment_section,
            has_execution_section,
            has_liability_section,
        ]
    )
    completeness_score = min(100, sections_present * 25)

    nmck = extracted_data.get("nmck")
    nmck_ok = _is_valid_numeric("nmck", nmck)
    partial_reasons: list[str] = []

    if input_mode.startswith("manual_text") and (not has_price_section or not nmck_ok):
        partial_reasons.append("manual_text_without_price")
    if not has_price_section:
        partial_reasons.append("missing_price_section")
    if sections_present <= 1:
        partial_reasons.append("only_contract_excerpt")
    if len(text) < 4000:
        partial_reasons.append("corpus_too_short")

    is_partial = bool(partial_reasons)

    return {
        "has_price_section": has_price_section,
        "has_payment_section": has_payment_section,
        "has_execution_section": has_execution_section,
        "has_liability_section": has_liability_section,
        "keyword_hits": keyword_hits,
        "completeness_score": int(completeness_score),
        "is_partial": is_partial,
        "partial_reasons": sorted(set(partial_reasons)),
    }


def build_missing_reasons(
    extracted_data: dict[str, Any],
    corpus_meta: dict[str, Any],
    input_mode: str,
) -> tuple[dict[str, str], dict[str, str]]:
    missing_reasons_base: dict[str, str] = {}
    missing_reasons_detail: dict[str, str] = {}
    is_partial = bool(corpus_meta.get("is_partial"))

    for field in CRITICAL_FIELDS:
        value = extracted_data.get(field)
        if _is_valid_numeric(field, value):
            continue

        section = FIELD_TO_SECTION[field]
        section_present = bool(corpus_meta.get(f"has_{section}_section"))

        if input_mode.startswith("manual_text") and is_partial and not section_present:
            missing_reasons_base[field] = "partial_input"
            missing_reasons_detail[field] = "not_provided_in_text"
        elif not section_present:
            missing_reasons_base[field] = "absent_in_docs"
            missing_reasons_detail[field] = "absent_in_docs"
        else:
            missing_reasons_base[field] = "parse_failed"
            missing_reasons_detail[field] = "parse_failed"

    return missing_reasons_base, missing_reasons_detail


def can_compute_financials(
    extracted_data: dict[str, Any],
    corpus_meta: dict[str, Any],
    input_mode: str,
) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    nmck = extracted_data.get("nmck")
    nmck_ok = _is_valid_numeric("nmck", nmck)
    has_price_section = bool(corpus_meta.get("has_price_section"))
    is_partial = bool(corpus_meta.get("is_partial"))

    if not nmck_ok:
        reasons.append("missing_nmck")

    if input_mode.startswith("manual_text") and is_partial:
        if not (nmck_ok and has_price_section):
            reasons.append("partial_manual_text_without_price_context")

    return len(reasons) == 0, reasons


def build_quality_gate(extracted_data: dict[str, Any], corpus_text: str, input_mode: str) -> dict[str, Any]:
    corpus_meta = analyze_corpus(corpus_text, extracted_data, input_mode)
    missing_reasons_base, missing_reasons_detail = build_missing_reasons(extracted_data, corpus_meta, input_mode)
    can_compute, financial_block_reasons = can_compute_financials(extracted_data, corpus_meta, input_mode)

    valid_count = 0
    for field in CRITICAL_FIELDS:
        if _is_valid_numeric(field, extracted_data.get(field)):
            valid_count += 1

    blocking_missing: list[str] = []
    if not _is_valid_numeric("nmck", extracted_data.get("nmck")):
        blocking_missing.append("nmck")
    if "missing_nmck" in financial_block_reasons and "nmck" not in blocking_missing:
        blocking_missing.append("nmck")

    return {
        "can_compute_financials": can_compute,
        "blocking_missing": sorted(set(blocking_missing)),
        "missing_reasons": missing_reasons_detail,
        "missing_reasons_base": missing_reasons_base,
        "completeness_score": int(round(valid_count * 100 / len(CRITICAL_FIELDS))),
        "corpus": corpus_meta,
        "financials_block_reasons": financial_block_reasons,
    }
