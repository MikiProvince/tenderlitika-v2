from __future__ import annotations

import json

from core.extractor import consolidate_extraction, extract_tender_data
from services.extraction.corpus_awareness import build_quality_gate


def _run_case(name: str, text: str, expected_partial: bool, expected_can_compute: bool) -> None:
    extracted = extract_tender_data(text)
    consolidate_extraction(extracted)
    gate = build_quality_gate(extracted, text, input_mode="manual_text")

    corpus = gate.get("corpus") or {}
    is_partial = bool(corpus.get("is_partial"))
    can_compute = bool(gate.get("can_compute_financials"))

    print(f"\n=== {name} ===")
    print(
        json.dumps(
            {
                "nmck": extracted.get("nmck"),
                "is_partial": is_partial,
                "partial_reasons": corpus.get("partial_reasons"),
                "can_compute_financials": can_compute,
                "financials_block_reasons": gate.get("financials_block_reasons"),
                "missing_reasons": gate.get("missing_reasons_base"),
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )

    if is_partial != expected_partial:
        raise SystemExit(f"{name}: expected is_partial={expected_partial}, got {is_partial}")
    if can_compute != expected_can_compute:
        raise SystemExit(f"{name}: expected can_compute_financials={expected_can_compute}, got {can_compute}")


def main() -> None:
    long_tail = (" Приложение и дополнительные условия исполнения. " * 120)

    full_package = (
        "Начальная (максимальная) цена контракта (НМЦК): 12 500 000 руб. "
        "Условия оплаты: окончательный расчет в течение 15 календарных дней, аванс 30%. "
        "Срок исполнения и поставки: в течение 45 календарных дней, поставка партиями. "
        "Ответственность сторон: неустойка 0,1% за каждый день просрочки, штраф 5%. "
        + long_tail
    )
    contract_excerpt = (
        "Условия оплаты: окончательный расчет в течение 45 рабочих дней. "
        "Ответственность сторон: неустойка 0,1% за каждый день просрочки, штраф 5%. "
        "Раздел о цене в данном фрагменте отсутствует."
    )
    price_only_excerpt = (
        "НМЦК по извещению: 7 752 436,93 руб. "
        "Цена договора фиксированная."
    )

    _run_case(
        name="CASE_1_FULL_PACKAGE",
        text=full_package,
        expected_partial=False,
        expected_can_compute=True,
    )
    _run_case(
        name="CASE_2_CONTRACT_ONLY",
        text=contract_excerpt,
        expected_partial=True,
        expected_can_compute=False,
    )
    _run_case(
        name="CASE_3_PRICE_ONLY",
        text=price_only_excerpt,
        expected_partial=True,
        expected_can_compute=True,
    )

    print("\nOK: partial mode smoke checks passed.")


if __name__ == "__main__":
    main()
