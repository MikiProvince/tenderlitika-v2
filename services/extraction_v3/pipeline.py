from __future__ import annotations

import re
from typing import Any

from core.risk_engine import calculate_risk
from services.extraction_v3.candidates import Candidate, mine_candidates
from services.extraction_v3.consolidate import apply_to_legacy
from services.extraction_v3.corpus import build_corpus
from services.extraction_v3.llm_ranker import rank_candidates, repair_field
from services.extraction_v3.normalize import normalize_text
from services.extraction_v3.retrieval import retrieve_sections
from services.extraction_v3.validate import validate_extracted


def _base_extracted_data() -> dict[str, Any]:
    return {
        "nmck": None,
        "currency": None,
        "execution_days": None,
        "payment_terms_days": None,
        "bid_security_percent": None,
        "contract_security_percent": None,
        "advance_percent": None,
        "penalty_percent_per_day": None,
        "fine_percent": None,
        "has_vague_acceptance_terms": False,
        "payment_after_full_delivery": False,
        "delivery_by_customer_requests": False,
        "supplier_must_hold_stock": False,
        "meta": {},
    }


def _section_presence(retrieved: dict[str, list[dict[str, Any]]]) -> dict[str, bool]:
    return {section: bool(items) for section, items in retrieved.items()}


def _resolve_selected(
    candidates_by_field: dict[str, list[Candidate]],
    rankings: dict[str, dict[str, Any]],
) -> dict[str, Candidate | None]:
    selected: dict[str, Candidate | None] = {}
    for field, candidates in candidates_by_field.items():
        rank = rankings.get(field) or {}
        selected_id = rank.get("selected_id")
        picked = None
        if selected_id is not None:
            picked = next((item for item in candidates if item.get("id") == selected_id), None)
        if picked is None and candidates:
            picked = candidates[0]
        selected[field] = picked
    return selected


def _extract_traps(text: str) -> dict[str, bool]:
    lowered = text.lower()
    return {
        "payment_after_full_delivery": bool(
            re.search(
                r"(?iu)(после\s+полной\s+поставки|после\s+поставки\s+всего\s+объема|после\s+полного\s+исполнения)",
                lowered,
            )
        ),
        "delivery_by_customer_requests": bool(
            re.search(
                r"(?iu)(по\s+заявк\w+\s+заказчика|поставка\s+партиями|по\s+мере\s+необходимости|отгрузка\s+партиями)",
                lowered,
            )
        ),
        "supplier_must_hold_stock": bool(
            re.search(
                r"(?iu)(обязан\s+иметь\s+товар\s+на\s+складе|обеспечить\s+наличие\s+товара\s+на\s+складе)",
                lowered,
            )
        ),
        "has_vague_acceptance_terms": bool(
            re.search(
                r"(?iu)(по\s+усмотрению\s+заказчика|вправе\s+отказать|на\s+усмотрение\s+заказчика)",
                lowered,
            )
        ),
    }


def _build_corpus_meta(
    corpus_info: dict[str, Any],
    section_presence: dict[str, bool],
) -> dict[str, Any]:
    input_mode = str(corpus_info.get("input_mode") or "manual_text")
    length = int(corpus_info.get("length") or 0)
    missing_core_sections = [
        key
        for key in ("price", "payment", "execution", "liability")
        if not section_presence.get(key)
    ]

    partial_reasons: list[str] = []
    if input_mode == "manual_text" and missing_core_sections:
        partial_reasons.append("manual_text_missing_sections")
    if not section_presence.get("price"):
        partial_reasons.append("missing_price_section")
    if length < 1200 and missing_core_sections:
        partial_reasons.append("corpus_too_short")

    return {
        "input_mode": input_mode,
        "length": length,
        "has_price_section": bool(section_presence.get("price")),
        "has_payment_section": bool(section_presence.get("payment")),
        "has_execution_section": bool(section_presence.get("execution")),
        "has_liability_section": bool(section_presence.get("liability")),
        "is_partial": bool(partial_reasons),
        "partial_reasons": sorted(set(partial_reasons)),
        "missing_sections": missing_core_sections,
    }


def _can_compute_financials(extracted_data: dict[str, Any], corpus_meta: dict[str, Any]) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    nmck = extracted_data.get("nmck")
    nmck_ok = isinstance(nmck, (int, float)) and float(nmck) > 0
    is_partial = bool(corpus_meta.get("is_partial"))

    if not nmck_ok:
        reasons.append("nmck_missing")
    if is_partial:
        reasons.append("partial_input")

    return len(reasons) == 0, reasons


def _apply_repair(
    field: str,
    repaired: Any,
    extracted_data: dict[str, Any],
    meta: dict[str, Any],
) -> None:
    if repaired is None:
        return
    if field == "nmck" and isinstance(repaired, (int, float)):
        extracted_data["nmck"] = float(repaired)
    elif field == "payment_terms" and isinstance(repaired, dict):
        payment = meta.setdefault("payment", {})
        payment.update(repaired)
        days = repaired.get("conservative_days")
        if isinstance(days, (int, float)):
            extracted_data["payment_terms_days"] = int(round(float(days)))
    elif field == "execution" and isinstance(repaired, (int, float)):
        extracted_data["execution_days"] = int(round(float(repaired)))
    elif field == "penalties" and isinstance(repaired, dict):
        penalties = meta.setdefault("penalties", {})
        penalties.update(repaired)
        per_day = repaired.get("penalty_percent_per_day")
        if isinstance(per_day, (int, float)):
            extracted_data["penalty_percent_per_day"] = float(per_day)


def run_pipeline(
    files_text: list[tuple[str, str]],
    manual_text: str | None,
    existing_user_inputs: dict[str, Any] | None,
) -> dict[str, Any]:
    corpus_info = build_corpus(files_text, manual_text)
    corpus = normalize_text(corpus_info.get("corpus") or "")

    retrieved = retrieve_sections(corpus)
    section_presence = _section_presence(retrieved)
    corpus_meta = _build_corpus_meta(corpus_info, section_presence)

    candidates_by_field = mine_candidates(corpus, retrieved)
    rankings: dict[str, dict[str, Any]] = {}
    for field, candidates in candidates_by_field.items():
        rankings[field] = rank_candidates(field, candidates)
    selected = _resolve_selected(candidates_by_field, rankings)

    extracted_data = _base_extracted_data()
    meta: dict[str, Any] = extracted_data.setdefault("meta", {})
    meta["pipeline_version"] = "v3"
    meta["corpus"] = corpus_meta
    meta["section_presence"] = section_presence
    meta["retrieved_sections"] = retrieved
    meta["candidate_counts"] = {field: len(values) for field, values in candidates_by_field.items()}
    meta["rankings"] = rankings
    meta["selections"] = {field: (item.get("id") if item else None) for field, item in selected.items()}

    apply_to_legacy(extracted_data, selected, meta)

    payment_meta = meta.get("payment") if isinstance(meta.get("payment"), dict) else {}
    if isinstance(payment_meta.get("advance_percent"), (int, float)):
        extracted_data["advance_percent"] = float(payment_meta.get("advance_percent"))
    penalties_meta = meta.get("penalties") if isinstance(meta.get("penalties"), dict) else {}
    if isinstance(penalties_meta.get("fine_percent"), (int, float)):
        extracted_data["fine_percent"] = float(penalties_meta.get("fine_percent"))

    extracted_data.update(_extract_traps(corpus))

    quality = validate_extracted(extracted_data, meta)
    meta["quality_gate"] = {
        "completeness_score": quality.get("completeness_score"),
        "missing_reasons": quality.get("missing_reasons"),
        "missing_reasons_base": quality.get("missing_reasons"),
        "blocking_missing": quality.get("blocking_missing"),
        "corpus": corpus_meta,
    }

    # Single-shot repair loop for fields with parse_failed.
    field_map = {
        "nmck": "nmck",
        "payment_terms_days": "payment_terms",
        "execution_days": "execution",
        "penalty_percent_per_day": "penalties",
    }
    for legacy_field, reason in (quality.get("missing_reasons") or {}).items():
        if reason != "parse_failed":
            continue
        candidate_field = field_map.get(legacy_field)
        if not candidate_field:
            continue
        snippets = []
        section = "liability" if candidate_field == "penalties" else ("payment" if candidate_field == "payment_terms" else ("execution" if candidate_field == "execution" else "price"))
        for item in retrieved.get(section) or []:
            snippets.append(
                {
                    "section": item.get("section"),
                    "keyword": item.get("keyword"),
                    "snippet": item.get("snippet"),
                    "offset": item.get("offset"),
                    "file": item.get("file"),
                }
            )
        if not snippets:
            continue
        current_value = extracted_data.get(legacy_field)
        repaired = repair_field(candidate_field, snippets, current_value)
        _apply_repair(candidate_field, repaired, extracted_data, meta)

    quality_after = validate_extracted(extracted_data, meta)
    financials_allowed, financial_block_reasons = _can_compute_financials(extracted_data, corpus_meta)
    gate = {
        "can_compute_financials": financials_allowed,
        "blocking_missing": quality_after.get("blocking_missing") or [],
        "missing_reasons": quality_after.get("missing_reasons") or {},
        "missing_reasons_base": quality_after.get("missing_reasons") or {},
        "completeness_score": quality_after.get("completeness_score") or 0,
        "corpus": corpus_meta,
        "financials_block_reasons": financial_block_reasons,
    }
    meta["quality_gate"] = gate
    meta["missing_reasons"] = gate["missing_reasons_base"]
    meta["missing_reasons_detail"] = gate["missing_reasons"]

    if not financials_allowed:
        meta["financials_skipped_due_to_missing_nmck"] = True
        meta["financials_skipped_reason"] = financial_block_reasons or ["unknown"]

    # Preview calculations for diagnostics only; API response contract remains unchanged.
    pipeline_diag = meta.setdefault("pipeline_v3", {})
    try:
        risk_score, risk_level, risk_reasons = calculate_risk(extracted_data, gate)
    except TypeError:
        risk_score, risk_level, risk_reasons = calculate_risk(extracted_data)
    pipeline_diag["risk_preview"] = {
        "score": risk_score,
        "level": risk_level,
        "reasons": risk_reasons,
    }

    pipeline_diag["financial_preview"] = {
        "expected_roi_percent": None,
        "rough_cash_gap": None,
        "safe_cost_price": None,
    }

    return extracted_data

