from __future__ import annotations

import re
from typing import TypedDict


SECTION_KEYWORDS = {
    "price": [
        "нмцк",
        "нмц",
        "начальная (максимальная) цена",
        "цена контракта",
        "цена договора",
        "начальная цена",
        "максимальная цена",
    ],
    "payment": [
        "оплата",
        "расчет",
        "расчеты",
        "счет",
        "платеж",
        "аванс",
        "предоплата",
        "окончательный расчет",
        "приемк",
        "документ о приемке",
        "подписан",
    ],
    "execution": [
        "срок поставки",
        "срок исполнения",
        "срок оказания",
        "поставка осуществляется",
        "в течение",
        "календарн",
        "рабоч",
    ],
    "liability": [
        "ответственность",
        "неустойк",
        "пеня",
        "штраф",
        "1/300",
        "ключевой ставк",
        "постановлен",
        "1042",
    ],
}


_FILE_MARKER_RE = re.compile(r"^===== FILE\s+(.+?)\s*=====$", flags=re.MULTILINE)


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
    current: str | None = None
    for marker_offset, file_name in markers:
        if marker_offset <= offset:
            current = file_name
        else:
            break
    return current


def _merge_ranges(ranges: list[dict]) -> list[dict]:
    if not ranges:
        return []
    ranges.sort(key=lambda item: (item["left"], item["right"], item["keyword"]))
    merged: list[dict] = [
        {
            "left": ranges[0]["left"],
            "right": ranges[0]["right"],
            "keywords": [ranges[0]["keyword"]],
        }
    ]
    for current in ranges[1:]:
        prev = merged[-1]
        if current["left"] <= prev["right"]:
            prev["right"] = max(prev["right"], current["right"])
            if current["keyword"] not in prev["keywords"]:
                prev["keywords"].append(current["keyword"])
            continue
        merged.append(
            {
                "left": current["left"],
                "right": current["right"],
                "keywords": [current["keyword"]],
            }
        )
    return merged


def find_snippets(corpus: str, keywords: list[str], window: int = 800, max_snippets: int = 10) -> list[Snippet]:
    if not corpus or not keywords:
        return []

    lowered = corpus.lower()
    markers = _parse_file_markers(corpus)

    ranges: list[dict] = []
    for keyword in keywords:
        escaped = re.escape(keyword.lower())
        for match in re.finditer(escaped, lowered):
            left = max(0, match.start() - window)
            right = min(len(corpus), match.end() + window)
            ranges.append(
                {
                    "left": left,
                    "right": right,
                    "keyword": keyword,
                }
            )

    merged = _merge_ranges(ranges)
    snippets: list[Snippet] = []
    for item in merged:
        raw = corpus[item["left"] : item["right"]]
        snippet = raw.strip()
        if not snippet:
            continue
        leading_ws = len(raw) - len(raw.lstrip())
        offset = item["left"] + leading_ws
        file_name = _file_for_offset(markers, offset)
        record: Snippet = {
            "section": "unknown",
            "keyword": item["keywords"][0] if item["keywords"] else "",
            "snippet": snippet,
            "offset": offset,
        }
        if file_name:
            record["file"] = file_name
        snippets.append(record)

    snippets.sort(key=lambda item: (item.get("offset", 0), item.get("keyword", "")))
    return snippets[: max(1, max_snippets)]


def retrieve_sections(corpus: str, window: int = 800, max_snippets: int = 10) -> dict[str, list[Snippet]]:
    out: dict[str, list[Snippet]] = {}
    for section, keywords in SECTION_KEYWORDS.items():
        items = find_snippets(corpus, keywords, window=window, max_snippets=max_snippets)
        fixed: list[Snippet] = []
        for item in items:
            entry = dict(item)
            entry["section"] = section
            fixed.append(entry)  # type: ignore[arg-type]
        out[section] = fixed
    return out
