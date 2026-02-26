from __future__ import annotations

import re
from typing import Any

from services.extraction.normalize import normalize_text


SECTION_QUERIES = {
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
    "penalties": [
        "пеня",
        "неустойк",
        "штраф",
        "ответственность сторон",
    ],
}


def find_snippets(
    text: str,
    keywords: list[str],
    window: int = 700,
    max_snippets: int = 6,
) -> list[dict[str, Any]]:
    if not text or not keywords:
        return []

    normalized = normalize_text(text)
    if not normalized:
        return []

    hits: list[tuple[int, int, str]] = []
    for keyword in keywords:
        pattern = re.escape(keyword)
        for match in re.finditer(pattern, normalized, flags=re.IGNORECASE):
            hits.append((match.start(), match.end(), keyword))

    if not hits:
        return []

    hits.sort(key=lambda item: item[0])
    merged: list[dict[str, Any]] = []
    for start, end, keyword in hits:
        left = max(0, start - window)
        right = min(len(normalized), end + window)
        if merged and left <= merged[-1]["right"]:
            merged[-1]["right"] = max(merged[-1]["right"], right)
            if keyword not in merged[-1]["keywords"]:
                merged[-1]["keywords"].append(keyword)
            continue
        merged.append(
            {
                "left": left,
                "right": right,
                "keywords": [keyword],
            }
        )

    snippets: list[dict[str, Any]] = []
    for segment in merged[:max_snippets]:
        raw = normalized[segment["left"]:segment["right"]]
        if not raw:
            continue
        trimmed = raw.strip()
        if not trimmed:
            continue
        leading_ws = len(raw) - len(raw.lstrip())
        snippets.append(
            {
                "keyword": segment["keywords"][0],
                "snippet": trimmed,
                "offset": segment["left"] + leading_ws,
            }
        )
    return snippets


def retrieve_sections(corpus: str) -> dict[str, list[dict[str, Any]]]:
    normalized = normalize_text(corpus or "")
    return {
        section: find_snippets(normalized, keywords)
        for section, keywords in SECTION_QUERIES.items()
    }
