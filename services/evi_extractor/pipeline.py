from __future__ import annotations

from copy import deepcopy
from typing import Any

from services.evi_extractor.candidates import Candidate, mine_candidates_by_field
from services.evi_extractor.consolidate import apply_consolidation
from services.evi_extractor.corpus import build_corpus
from services.evi_extractor.guard import apply_financial_guard
from services.evi_extractor.llm_verify import verify_and_select
from services.evi_extractor.retrieval import retrieve_sections
from services.evi_extractor.validate import validate_selection


def _base_extracted_data() -> dict[str, Any]:
    return {
        "nmck": None,
        "currency": "RUB",
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


def _seed_extracted_data(existing: dict[str, Any] | None) -> dict[str, Any]:
    out = _base_extracted_data()
    if not isinstance(existing, dict):
        return out
    for key, value in existing.items():
        if key == "meta":
            continue
        out[key] = deepcopy(value)
    if isinstance(existing.get("meta"), dict):
        out["meta"] = deepcopy(existing["meta"])
    return out


def _quote_has_anchor(field: str, quote: str) -> bool:
    lowered = (quote or "").lower()
    anchors = {
        "nmck": ["нмцк", "начальная (максимальная) цена", "цена контракта", "цена договора"],
        "payment_terms": ["оплат", "расчет", "платеж", "аванс", "предоплат", "приемк"],
        "execution_days": ["срок", "поставк", "исполн", "оказани", "дн"],
        "penalties": ["пеня", "неустойк", "штраф", "1/300", "ключевой ставк", "1042"],
    }
    return any(anchor in lowered for anchor in anchors.get(field, []))


def _deterministic_fallback(field: str, candidates: list[Candidate]) -> Candidate | None:
    if not candidates:
        return None
    ranked = sorted(
        candidates,
        key=lambda item: (-float(item.get("confidence_hint") or 0.0), int(item.get("offset") or 0), str(item.get("id") or "")),
    )
    for candidate in ranked:
        quote = str(candidate.get("quote") or "")
        if _quote_has_anchor(field, quote):
            return candidate
    return ranked[0]


def _quality_gate_payload(
    *,
    validated: dict[str, Any],
    guard_allowed: bool,
    guard_reasons: list[str],
    sections: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    missing_reasons = validated.get("missing_reasons") or {}
    blocking_missing: list[str] = []
    if "nmck" in missing_reasons:
        blocking_missing.append("nmck")
    if "nmck_missing" in guard_reasons and "nmck" not in blocking_missing:
        blocking_missing.append("nmck")

    corpus_meta = {
        "has_price_section": bool(sections.get("price")),
        "has_payment_section": bool(sections.get("payment")),
        "has_execution_section": bool(sections.get("execution")),
        "has_liability_section": bool(sections.get("liability")),
        "is_partial": bool(validated.get("is_partial")),
        "partial_reasons": validated.get("partial_reasons") or [],
    }

    return {
        "can_compute_financials": bool(guard_allowed),
        "blocking_missing": sorted(set(blocking_missing)),
        "missing_reasons": missing_reasons,
        "missing_reasons_base": missing_reasons,
        "completeness_score": int(validated.get("completeness_score") or 0),
        "corpus": corpus_meta,
        "financials_block_reasons": guard_reasons,
    }


def run_evi_extractor(
    files_text: list[tuple[str, str]],
    manual_text: str | None,
    extracted_data_existing: dict[str, Any] | None,
) -> dict[str, Any]:
    corpus_info = build_corpus(files_text, manual_text)
    corpus = str(corpus_info.get("corpus") or "")
    input_mode = str(corpus_info.get("input_mode") or "manual_text")

    sections = retrieve_sections(corpus)
    candidates_by_field = mine_candidates_by_field(sections)

    selected_by_field: dict[str, Candidate | None] = {}
    llm_decisions: dict[str, dict[str, Any]] = {}
    selection_method: dict[str, str] = {}

    for field, candidates in candidates_by_field.items():
        decision = verify_and_select(field, candidates)
        llm_decisions[field] = decision
        selected_id = decision.get("selected_id")
        selected = next((c for c in candidates if c.get("id") == selected_id), None)
        if selected is not None:
            selected_by_field[field] = selected
            selection_method[field] = "llm"
            continue
        selected_by_field[field] = _deterministic_fallback(field, candidates)
        selection_method[field] = "deterministic"

    validated = validate_selection(
        selected_by_field=selected_by_field,
        candidates_by_field=candidates_by_field,
        input_mode=input_mode,
    )

    extracted_data = _seed_extracted_data(extracted_data_existing)
    extracted_data = apply_consolidation(
        extracted_data=extracted_data,
        validated=validated,
        input_mode=input_mode,
    )

    guard_allowed, guard_reasons = apply_financial_guard(extracted_data)
    meta = extracted_data.setdefault("meta", {})
    evi_meta = meta.setdefault("evi_extractor", {})
    evi_meta.update(
        {
            "candidate_counts": {field: len(values) for field, values in candidates_by_field.items()},
            "selections": {field: (candidate.get("id") if candidate else None) for field, candidate in selected_by_field.items()},
            "selection_method": selection_method,
            "llm_decisions": llm_decisions,
            "corpus_length": int(corpus_info.get("length") or 0),
            "input_mode": input_mode,
        }
    )

    gate = _quality_gate_payload(
        validated=validated,
        guard_allowed=guard_allowed,
        guard_reasons=guard_reasons,
        sections=sections,
    )
    meta["quality_gate"] = gate
    meta["missing_reasons"] = gate.get("missing_reasons_base") or {}
    meta["missing_reasons_detail"] = gate.get("missing_reasons") or {}
    meta["input_mode"] = input_mode
    meta["corpus"] = gate.get("corpus") or {}

    return extracted_data
