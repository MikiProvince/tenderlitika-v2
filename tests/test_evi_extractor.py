from __future__ import annotations

from services.evi_extractor.pipeline import run_evi_extractor


def _disable_llm_env(monkeypatch):
    for key in (
        "GEMINI_API_KEY",
        "GIGACHAT_ACCESS_TOKEN",
        "GIGACHAT_AUTH_KEY",
        "GIGACHAT_AUTH_HEADER",
    ):
        monkeypatch.delenv(key, raising=False)


def test_evi_extractor_extracts_expected_fields_and_evidence(monkeypatch):
    _disable_llm_env(monkeypatch)
    files = [
        (
            "contract.txt",
            (
                "Оплата производится в течение 7 рабочих дней после подписания документа о приемке. "
                "Аванс не предусмотрен. "
                "Пеня рассчитывается в размере 1/300 ключевой ставки за каждый день просрочки. "
                "Штраф составляет 1%, не более 5000 руб. и не менее 1000 руб., согласно постановлению 1042."
            ),
        ),
        (
            "nmck.txt",
            "Начальная (максимальная) цена контракта составляет 752 183,09 руб.",
        ),
    ]

    result = run_evi_extractor(files_text=files, manual_text=None, extracted_data_existing={})
    meta = result.get("meta") or {}
    penalties = meta.get("penalties") or {}

    assert result["nmck"] == 752183.09
    assert result["payment_terms_days"] == 10
    assert (meta.get("payment") or {}).get("advance_allowed") is False
    assert penalties.get("penalty", {}).get("denominator") == 300
    assert penalties.get("fine", {}).get("percent") == 1.0
    assert penalties.get("fine", {}).get("min") == 1000.0
    assert penalties.get("fine", {}).get("max") == 5000.0
    assert penalties.get("pp_reference") == "1042"

    evidence = meta.get("evidence") or {}
    assert evidence.get("nmck", {}).get("file") == "nmck.txt"
    assert evidence.get("payment_terms", {}).get("file") == "contract.txt"
    assert evidence.get("penalties", {}).get("file") == "contract.txt"


def test_evi_extractor_skips_financials_without_nmck(monkeypatch):
    _disable_llm_env(monkeypatch)
    manual = (
        "Оплата производится в течение 7 рабочих дней. "
        "Аванс не предусмотрен. "
        "Срок поставки 30 календарных дней."
    )

    result = run_evi_extractor(files_text=[], manual_text=manual, extracted_data_existing={})
    meta = result.get("meta") or {}
    reasons = meta.get("financials_skipped_reason") or []

    assert result.get("nmck") is None
    assert result.get("safe_cost_price") is None
    assert result.get("roi_percent") is None
    assert result.get("cash_gap") is None
    assert "nmck_missing" in reasons
    assert bool((meta.get("evi_extractor") or {}).get("is_partial_for_price")) is True


def test_evi_extractor_is_idempotent(monkeypatch):
    _disable_llm_env(monkeypatch)
    files = [
        ("a.txt", "НМЦК: 1 200 000 руб. Оплата в течение 15 календарных дней."),
        ("b.txt", "Срок поставки 40 календарных дней."),
    ]

    run1 = run_evi_extractor(files_text=files, manual_text=None, extracted_data_existing={})
    run2 = run_evi_extractor(files_text=files, manual_text=None, extracted_data_existing={})

    snap1 = {
        "nmck": run1.get("nmck"),
        "payment_terms_days": run1.get("payment_terms_days"),
        "execution_days": run1.get("execution_days"),
        "evidence": (run1.get("meta") or {}).get("evidence"),
    }
    snap2 = {
        "nmck": run2.get("nmck"),
        "payment_terms_days": run2.get("payment_terms_days"),
        "execution_days": run2.get("execution_days"),
        "evidence": (run2.get("meta") or {}).get("evidence"),
    }
    assert snap1 == snap2
