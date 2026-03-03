from __future__ import annotations

import re
from typing import Any, TypedDict

from services.extraction_v3.normalize import normalize_text


SECTION_KEYWORDS: dict[str, list[str]] = {
    "price": [
        "нмцк",
        "нмц",
        "начальная (максимальная) цена",
        "цена договора",
        "цена контракта",
        "цена лота",
        "по извещению",
    ],
    "payment": [
        "оплата",
        "расчет",
        "аванс",
        "предоплата",
        "платеж",
        "окончательный расчет",
        "приемка",
        "накладная",
    ],
    "execution": [
        "срок поставки",
        "срок исполнения",
        "исполнения обязательств",
        "отгрузка",
        "поставка",
    ],
    "liability": [
        "ответственность",
        "неустойка",
        "пеня",
        "штраф",
    ],
    "specs": [
        "техническое задание",
        "спецификация",
        "характеристики",
        "требования к товару",
    ],
    "security": [
        "обеспечение заявки",
        "обеспечение исполнения",
        "банковская гарантия",
        "задаток",
    ],
}


_FILE_MARKER_RE = re.compile(
    r"^===== FILE\s+\d+/\d+:\s*(.+?)\s*=====$",
    flags=re.MULTILINE,
)


class Snippet(TypedDict, total=False):
    section: str
    keyword: str
    snippet: str
    offset: int
    file: str


def _parse_file_markers(corpus: str) -> list[tuple[int, str]]:
    markers: list[tuple[int, str]] = []
    for match in _FILE_MARKER_RE.finditer(corpus):
        name = (match.group(1) or "").strip()
        markers.append((match.start(), name))
    return markers


def _file_for_offset(markers: list[tuple[int, str]], offset: int) -> str | None:
    if not markers:
        return None
    current: str | None = None
    for marker_offset, name in markers:
        if marker_offset <= offset:
            current = name
        else:
            break
    return current


def _keyword_hits(text: str, keywords: list[str]) -> int:
    lowered = text.lower()
    total = 0
    for keyword in keywords:
        total += lowered.count(keyword.lower())
    return total


def retrieve_sections(corpus: str) -> dict[str, list[Snippet]]:
    normalized = normalize_text(corpus or "")
    markers = _parse_file_markers(normalized)
    out: dict[str, list[Snippet]] = {}

    radius = 350
    max_snippets = 8

    for section, keywords in SECTION_KEYWORDS.items():
        hits: list[tuple[int, int, str]] = []
        for keyword in keywords:
            pattern = re.compile(re.escape(keyword), flags=re.IGNORECASE)
            for match in pattern.finditer(normalized):
                hits.append((match.start(), match.end(), keyword))

        if not hits:
            out[section] = []
            continue

        hits.sort(key=lambda item: (item[0], item[1], item[2]))
        ranges: list[dict[str, Any]] = []

        for start, end, keyword in hits:
            left = max(0, start - radius)
            right = min(len(normalized), end + radius)
            if ranges and left <= ranges[-1]["right"]:
                ranges[-1]["right"] = max(ranges[-1]["right"], right)
                if keyword not in ranges[-1]["keywords"]:
                    ranges[-1]["keywords"].append(keyword)
                continue
            ranges.append(
                {
                    "left": left,
                    "right": right,
                    "keywords": [keyword],
                }
            )

        ranked: list[tuple[int, int, dict[str, Any]]] = []
        for item in ranges:
            raw = normalized[item["left"] : item["right"]]
            snippet = raw.strip()
            if not snippet:
                continue
            leading_ws = len(raw) - len(raw.lstrip())
            offset = item["left"] + leading_ws
            score = _keyword_hits(snippet, keywords)
            ranked.append((score, offset, item))

        ranked.sort(key=lambda row: (-row[0], row[1]))
        chosen = ranked[:max_snippets]
        chosen.sort(key=lambda row: row[1])

        snippets: list[Snippet] = []
        for _, _, item in chosen:
            raw = normalized[item["left"] : item["right"]]
            snippet = raw.strip()
            leading_ws = len(raw) - len(raw.lstrip())
            offset = item["left"] + leading_ws
            file_name = _file_for_offset(markers, offset)
            entry: Snippet = {
                "section": section,
                "keyword": item["keywords"][0],
                "snippet": snippet,
                "offset": offset,
            }
            if file_name:
                entry["file"] = file_name
            snippets.append(entry)
        out[section] = snippets

    return out
