from services.extraction.corpus_awareness import analyze_corpus
from services.extraction_v3.pipeline import _extract_traps
from services.extraction_v3.retrieval import retrieve_sections


def test_analyze_corpus_detects_russian_sections():
    corpus = (
        "НМЦК по извещению: 1 500 000 руб. "
        "Оплата в течение 30 дней. "
        "Срок поставки 15 дней. "
        "Ответственность: неустойка 0.1%."
    )
    meta = analyze_corpus(corpus, {"nmck": 1_500_000}, "manual_text")
    assert meta["has_price_section"] is True
    assert meta["has_payment_section"] is True
    assert meta["has_execution_section"] is True
    assert meta["has_liability_section"] is True


def test_v3_retrieval_finds_price_section_for_nmck():
    corpus = "===== FILE 1/1: notice.txt (txt) =====\nНМЦК: 1 500 000 рублей"
    sections = retrieve_sections(corpus)
    assert sections["price"]


def test_v3_extract_traps_detects_common_russian_patterns():
    text = (
        "Оплата производится после полной поставки. "
        "Поставка партиями по заявке заказчика. "
        "Поставщик обязан иметь товар на складе."
    )
    flags = _extract_traps(text)
    assert flags["payment_after_full_delivery"] is True
    assert flags["delivery_by_customer_requests"] is True
    assert flags["supplier_must_hold_stock"] is True
