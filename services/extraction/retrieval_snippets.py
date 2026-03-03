from __future__ import annotations

import re
from typing import Any


SECTION_KEYWORDS: dict[str, list[str]] = {
    "price": [
        "нмцк",
        "нмц",
        "начальная (максимальная) цена",
        "цена контракта",
        "цена договора",
        "обоснование нмц",
        "итого",
    ],
    "payment": [
        "оплата",
        "платеж",
        "платёж",
        "расчет",
        "расчёт",
        "аванс",
        "предоплата",
        "счет",
        "счёт",
        "документ о приемке",
        "приемк",
    ],
    "liability": [
        "ответственность",
        "неустойк",
        "пеня",
        "штраф",
        "1/300",
        "ключев",
        "1042",
    ],
    "execution": [
        "срок поставки",
        "срок исполнения",
        "поставка",
        "отгруз",
        "партия",
        "в течение",
        "календарн",
        "рабоч",
    ],
}


_SPACE_RE = re.compile(r"\s+")


def normalize_for_search(text: str) -> str:
    if not text:
        return ""
    lowered = text.lower().replace("ё", "е")
    lowered = _SPACE_RE.sub(" ", lowered)
    return lowered.strip()


def _keyword_weight(keyword: str) -> float:
    normalized = normalize_for_search(keyword)
    if " " in normalized:
        return 2.2
    if "/" in normalized:
        return 2.0
    if len(normalized) >= 8:
        return 1.5
    return 1.0


def _merge_ranges(ranges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not ranges:
        return []
    ranges.sort(key=lambda row: (row["left"], row["right"], row["keyword"]))
    merged: list[dict[str, Any]] = [
        {
            "left": ranges[0]["left"],
            "right": ranges[0]["right"],
            "hits": [ranges[0]],
        }
    ]

    for current in ranges[1:]:
        prev = merged[-1]
        if current["left"] <= prev["right"]:
            prev["right"] = max(prev["right"], current["right"])
            prev["hits"].append(current)
            continue
        merged.append(
            {
                "left": current["left"],
                "right": current["right"],
                "hits": [current],
            }
        )
    return merged


def find_snippets(text: str, keywords: list[str], window: int = 900, max_snippets: int = 10) -> list[dict[str, Any]]:
    if not text or not keywords:
        return []

    normalized = normalize_for_search(text)
    if not normalized:
        return []

    ranges: list[dict[str, Any]] = []
    normalized_keywords = [normalize_for_search(keyword) for keyword in keywords if keyword]
    for keyword in normalized_keywords:
        if not keyword:
            continue
        weight = _keyword_weight(keyword)
        pattern = re.escape(keyword)
        for match in re.finditer(pattern, normalized):
            left = max(0, match.start() - window)
            right = min(len(normalized), match.end() + window)
            ranges.append(
                {
                    "left": left,
                    "right": right,
                    "start": match.start(),
                    "end": match.end(),
                    "keyword": keyword,
                    "weight": weight,
                }
            )

    merged = _merge_ranges(ranges)
    snippets: list[dict[str, Any]] = []
    for item in merged:
        left = int(item["left"])
        right = int(item["right"])
        snippet = normalized[left:right].strip()
        if not snippet:
            continue

        hits = item["hits"]
        keyword_weight_sum = sum(float(hit["weight"]) for hit in hits)
        unique_keywords = sorted(set(str(hit["keyword"]) for hit in hits))
        anchor_hits = [keyword for keyword in unique_keywords if (" " in keyword or "/" in keyword or len(keyword) >= 10)]
        proximity_bonus = min(6.0, len(anchor_hits) * 1.5)
        if len(unique_keywords) >= 3:
            proximity_bonus += 1.0
        score = keyword_weight_sum + proximity_bonus

        snippets.append(
            {
                "offset": left,
                "snippet": snippet,
                "score": float(round(score, 4)),
                "keywords": unique_keywords,
            }
        )

    snippets.sort(key=lambda row: (-float(row["score"]), int(row["offset"]), row["snippet"]))
    return snippets[: max(1, max_snippets)]


def _assemble_context(
    snippets_by_section: dict[str, list[dict[str, Any]]],
    sections: tuple[str, ...],
    total_cap: int,
) -> str:
    parts: list[str] = []
    used = 0

    for section in sections:
        snippets = snippets_by_section.get(section) or []
        if not snippets:
            continue

        header = f"### SECTION: {section.upper()}\n"
        if used + len(header) > total_cap:
            break
        parts.append(header)
        used += len(header)

        for index, row in enumerate(snippets, start=1):
            body = str(row.get("snippet") or "").strip()
            if not body:
                continue
            block = f"[SNIPPET {index} | score={float(row.get('score') or 0):.2f} | offset={int(row.get('offset') or 0)}]\n{body}\n\n"
            if used + len(block) <= total_cap:
                parts.append(block)
                used += len(block)
                continue

            remain = total_cap - used
            if remain <= 0:
                break

            min_prefix = f"[SNIPPET {index}]\n"
            if remain <= len(min_prefix):
                break
            allowed = remain - len(min_prefix) - 1
            parts.append(min_prefix + body[:allowed].rstrip() + "\n")
            used = total_cap
            break

        if used >= total_cap:
            break

    return "".join(parts).strip()


def build_llm_context_with_meta(
    corpus: str,
    sections: tuple[str, ...] = ("price", "payment", "liability", "execution"),
    total_cap: int = 20_000,
    window: int = 900,
    max_snippets_per_section: int = 10,
) -> tuple[str, dict[str, Any]]:
    cap = max(1_000, int(total_cap))
    snippets_by_section: dict[str, list[dict[str, Any]]] = {}
    section_counts: dict[str, int] = {}

    for section in sections:
        keywords = SECTION_KEYWORDS.get(section) or []
        snippets = find_snippets(corpus, keywords, window=window, max_snippets=max_snippets_per_section)
        snippets_by_section[section] = snippets
        section_counts[section] = len(snippets)

    context = _assemble_context(snippets_by_section, sections, cap)
    meta = {
        "section_counts": section_counts,
        "context_chars": len(context),
    }
    return context, meta


def build_llm_context(
    corpus: str,
    sections: tuple[str, ...] = ("price", "payment", "liability", "execution"),
) -> str:
    context, _ = build_llm_context_with_meta(corpus, sections=sections)
    return context
