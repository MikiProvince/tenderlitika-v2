from __future__ import annotations

import re
from typing import Any

from services.extraction.normalize import normalize_text
from services.extraction.retrieval import SECTION_QUERIES


_CRITICAL_FIELDS = ("nmck", "payment_terms_days", "execution_days", "penalty_percent_per_day")
_FIELD_SECTION = {
    "nmck": "price",
    "payment_terms_days": "payment",
    "execution_days": "execution",
    "penalty_percent_per_day": "penalties",
}
_FIELD_KEYWORDS = {
    "nmck": ["нмцк", "нмц", "начальная (максимальная) цена", "цена договора", "цена контракта", "цена лота"],
    "payment_terms_days": SECTION_QUERIES["payment"],
    "execution_days": SECTION_QUERIES["execution"],
    "penalty_percent_per_day": SECTION_QUERIES["penalties"],
}
_FIELD_LABELS = {
    "nmck": "НМЦК",
    "payment_terms_days": "срок оплаты",
    "execution_days": "срок исполнения",
    "penalty_percent_per_day": "пеня в день",
}
_MISSING_REASON_LABELS = {
    "absent_in_docs": "Отсутствует в документах",
    "parse_failed": "Ошибка извлечения",
    "conflict": "Конфликт/некорректное значение",
}


def _is_valid(field: str, value: Any) -> bool:
    if value is None:
        return False
    try:
        if field == "nmck":
            return 1_000 <= float(value) <= 100_000_000_000
        if field == "payment_terms_days":
            return 1 <= int(value) <= 3650
        if field == "execution_days":
            return 1 <= int(value) <= 5000
        if field == "penalty_percent_per_day":
            return 0 <= float(value) <= 10
    except Exception:
        return False
    return False


def _keywords_exist(corpus: str, field: str) -> bool:
    for keyword in _FIELD_KEYWORDS.get(field, []):
        if re.search(re.escape(keyword), corpus, flags=re.IGNORECASE):
            return True
    return False


def _first_snippet(retrieved_sections: dict[str, list[dict[str, Any]]], field: str) -> str:
    section = _FIELD_SECTION.get(field)
    if not section:
        return ""
    snippets = retrieved_sections.get(section) or []
    if not snippets:
        return ""
    return str(snippets[0].get("snippet") or "")


def validate_extracted_data(
    extracted_data: dict[str, Any],
    corpus: str,
    retrieved_sections: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    normalized_corpus = normalize_text(corpus or "")
    warnings: list[str] = []
    missing_reasons: dict[str, str] = {}
    critical_missing: list[str] = []
    valid_count = 0

    for field in _CRITICAL_FIELDS:
        field_label = _FIELD_LABELS.get(field, field)
        value = extracted_data.get(field)
        if _is_valid(field, value):
            valid_count += 1
            continue

        critical_missing.append(field)

        if value is not None:
            reason = "conflict"
            warnings.append(f"{field_label}: значение есть, но выходит за допустимые границы.")
        elif not _keywords_exist(normalized_corpus, field):
            reason = "absent_in_docs"
        else:
            reason = "parse_failed"
            snippet = _first_snippet(retrieved_sections, field)
            if snippet:
                preview = re.sub(r"\s+", " ", snippet)[:200]
                warnings.append(f"{field_label}: найдены ключевые слова, но парсинг не сработал. Фрагмент: {preview}")
            else:
                warnings.append(f"{field_label}: найдены ключевые слова, но подходящий фрагмент не найден.")

        missing_reasons[field] = reason

    completeness_score = int(round((valid_count / len(_CRITICAL_FIELDS)) * 100))
    missing_reasons_ru = {
        field: _MISSING_REASON_LABELS.get(code, code)
        for field, code in missing_reasons.items()
    }
    return {
        "completeness_score": completeness_score,
        "critical_missing": critical_missing,
        "missing_reasons": missing_reasons,
        "missing_reasons_ru": missing_reasons_ru,
        "warnings": warnings,
    }
