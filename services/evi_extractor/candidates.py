from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal
from typing import Any, TypedDict

from services.evi_extractor.parsers import (
    normalize_number_tokens,
    parse_days_ru,
    parse_fraction_penalty,
    parse_money_ru,
    parse_percent_ru,
)
from services.evi_extractor.retrieval import Snippet


class Candidate(TypedDict):
    id: str
    field: str
    value: Any
    value_raw: str
    quote: str
    file: str | None
    offset: int
    section: str
    confidence_hint: float
    signals: dict[str, list[str]]


_MONEY_RE = re.compile(
    r"(?<!\d)(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?!\d)"
)
_DATE_RE = re.compile(r"\b(\d{2}\.\d{2}\.\d{4})\b")
_FILE_MARKER_RE = re.compile(r"^===== FILE\s+(.+?)\s*=====$")
_NMCK_ANCHORS = [
    "начальная (максимальная) цена контракта",
    "нмцк",
]
_NMCK_KEYWORDS = _NMCK_ANCHORS + ["цена контракта", "цена договора", "начальная цена", "максимальная цена"]
_NMCK_EXCLUSIONS = ["обеспечение", "банковская гарантия", "задаток", "штраф", "пеня"]
_PAYMENT_TRIGGERS = {
    "after_acceptance": ["приемк", "документ о приемке", "подписан"],
    "after_invoice": ["счет", "счета", "счет-фактур", "invoice"],
    "after_delivery": ["поставк", "доставк", "отгрузк"],
}


def _clip_quote(text: str, max_chars: int = 320) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) <= max_chars:
        return cleaned
    return cleaned[: max_chars - 1].rstrip() + "…"


def _build_candidate(
    *,
    field: str,
    index: int,
    value: Any,
    value_raw: str,
    quote: str,
    file_name: str | None,
    offset: int,
    section: str,
    confidence_hint: float,
    keywords: list[str],
    exclusions: list[str],
) -> Candidate:
    return {
        "id": f"{field}_{index}",
        "field": field,
        "value": value,
        "value_raw": value_raw,
        "quote": _clip_quote(quote),
        "file": file_name,
        "offset": offset,
        "section": section,
        "confidence_hint": max(0.0, min(1.0, float(confidence_hint))),
        "signals": {
            "keywords": keywords,
            "exclusions": exclusions,
        },
    }


def _line_start_offsets(snippet: str, base_offset: int) -> list[tuple[int, str]]:
    rows = snippet.splitlines() or [snippet]
    out: list[tuple[int, str]] = []
    cursor = 0
    for row in rows:
        out.append((base_offset + cursor, row))
        cursor += len(row) + 1
    return out


def _line_rows_with_file(snippet: str, base_offset: int, initial_file: str | None) -> list[tuple[int, str, str | None]]:
    rows = snippet.splitlines() or [snippet]
    out: list[tuple[int, str, str | None]] = []
    cursor = 0
    current_file = initial_file
    for row in rows:
        marker = _FILE_MARKER_RE.match(row.strip())
        if marker:
            marker_name = marker.group(1).strip()
            current_file = None if marker_name == "MANUAL_TEXT" else marker_name
        out.append((base_offset + cursor, row, current_file))
        cursor += len(row) + 1
    return out


def _iter_money_matches(text: str) -> list[tuple[str, Decimal]]:
    out: list[tuple[str, Decimal]] = []
    for match in _MONEY_RE.finditer(text):
        raw = match.group(1)
        parsed = parse_money_ru(raw)
        if parsed is not None:
            out.append((raw, parsed))
    return out


def _detect_trigger(text: str) -> str:
    lowered = text.lower()
    for trigger, words in _PAYMENT_TRIGGERS.items():
        if any(word in lowered for word in words):
            return trigger
    return "after_acceptance"


def mine_nmck_candidates(snippets: list[Snippet], limit: int = 12) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        section = str(snippet.get("section") or "price")
        text = str(snippet.get("snippet") or "")
        if not text:
            continue
        lowered = text.lower()
        line_offsets = _line_rows_with_file(
            text,
            int(snippet.get("offset") or 0),
            snippet.get("file"),
        )

        for line_index, (line_offset, line, line_file) in enumerate(line_offsets):
            line_lower = line.lower()
            if not any(anchor in line_lower for anchor in _NMCK_KEYWORDS):
                continue

            window_lines = [line]
            if line_index + 1 < len(line_offsets):
                window_lines.append(line_offsets[line_index + 1][1])
            if line_index + 2 < len(line_offsets):
                window_lines.append(line_offsets[line_index + 2][1])
            search_zone = "\n".join(window_lines)

            parsed_rows = normalize_number_tokens(search_zone)
            money_hits: list[tuple[str, Decimal]] = []
            for row in parsed_rows:
                money_hits.extend(_iter_money_matches(row))
            if not money_hits:
                money_hits = _iter_money_matches(search_zone)

            if not money_hits:
                continue

            for raw, value in money_hits:
                confidence = 0.45
                hit_keywords: list[str] = []
                hit_exclusions: list[str] = []

                for anchor in _NMCK_ANCHORS:
                    if anchor in line_lower:
                        confidence += 0.28
                        hit_keywords.append(anchor)
                for keyword in _NMCK_KEYWORDS:
                    if keyword in line_lower and keyword not in hit_keywords:
                        confidence += 0.04
                        hit_keywords.append(keyword)
                for exclusion in _NMCK_EXCLUSIONS:
                    if exclusion in lowered:
                        confidence -= 0.2
                        hit_exclusions.append(exclusion)

                quote = search_zone
                candidates.append(
                    _build_candidate(
                        field="nmck",
                        index=idx,
                        value=value,
                        value_raw=raw,
                        quote=quote,
                        file_name=line_file,
                        offset=line_offset,
                        section=section,
                        confidence_hint=confidence,
                        keywords=hit_keywords,
                        exclusions=hit_exclusions,
                    )
                )
                idx += 1

    candidates.sort(key=lambda item: (-item["confidence_hint"], item["offset"], item["id"]))
    return candidates[: max(1, limit)]


def mine_payment_candidates(snippets: list[Snippet]) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        section = str(snippet.get("section") or "payment")
        text = str(snippet.get("snippet") or "")
        if not text:
            continue
        lowered = text.lower()
        offset = int(snippet.get("offset") or 0)
        file_name = snippet.get("file")

        if re.search(r"(?iu)аванс\w*\s+не\s+предусмотрен", lowered):
            candidates.append(
                _build_candidate(
                    field="payment_terms",
                    index=idx,
                    value={"advance_allowed": False},
                    value_raw="аванс не предусмотрен",
                    quote=text,
                    file_name=file_name,
                    offset=offset,
                    section=section,
                    confidence_hint=0.96,
                    keywords=["аванс", "не предусмотрен"],
                    exclusions=[],
                )
            )
            idx += 1

        if re.search(r"(?iu)\bаванс\w*\b", lowered) and not re.search(r"(?iu)не\s+предусмотрен", lowered):
            percent = parse_percent_ru(text)
            value: dict[str, Any] = {"advance_allowed": True}
            if percent is not None:
                value["advance_percent"] = float(percent)
            candidates.append(
                _build_candidate(
                    field="payment_terms",
                    index=idx,
                    value=value,
                    value_raw="аванс",
                    quote=text,
                    file_name=file_name,
                    offset=offset,
                    section=section,
                    confidence_hint=0.58,
                    keywords=["аванс"],
                    exclusions=[],
                )
            )
            idx += 1

        pay_match = re.search(
            r"(?iu)(оплат\w*|расчет\w*|расчеты|платеж\w*)[^.\n]{0,180}?(в\s+течение|не\s+позднее)\s+(\d{1,4})\s*(рабоч\w*|календар\w*)?\s*дн",
            text,
        )
        if pay_match:
            days = int(pay_match.group(3))
            kind_raw = (pay_match.group(4) or "").lower()
            day_type = "working" if "рабоч" in kind_raw else ("calendar" if "календар" in kind_raw else None)
            trigger = _detect_trigger(text)
            value = {
                "payment_days": days,
                "day_type": day_type,
                "trigger": trigger,
            }
            candidates.append(
                _build_candidate(
                    field="payment_terms",
                    index=idx,
                    value=value,
                    value_raw=pay_match.group(0),
                    quote=pay_match.group(0),
                    file_name=file_name,
                    offset=offset + pay_match.start(),
                    section=section,
                    confidence_hint=0.9,
                    keywords=["оплата", "в течение"],
                    exclusions=[],
                )
            )
            idx += 1
        else:
            days, day_type = parse_days_ru(text)
            if days is not None and any(word in lowered for word in ("оплат", "расчет", "платеж")):
                candidates.append(
                    _build_candidate(
                        field="payment_terms",
                        index=idx,
                        value={
                            "payment_days": days,
                            "day_type": day_type,
                            "trigger": _detect_trigger(text),
                        },
                        value_raw=f"{days} {day_type or ''}".strip(),
                        quote=text,
                        file_name=file_name,
                        offset=offset,
                        section=section,
                        confidence_hint=0.72,
                        keywords=["оплата"],
                        exclusions=[],
                    )
                )
                idx += 1

    candidates.sort(key=lambda item: (-item["confidence_hint"], item["offset"], item["id"]))
    return candidates


def mine_execution_candidates(snippets: list[Snippet]) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        section = str(snippet.get("section") or "execution")
        text = str(snippet.get("snippet") or "")
        if not text:
            continue
        lowered = text.lower()
        offset = int(snippet.get("offset") or 0)
        file_name = snippet.get("file")

        explicit_match = re.search(
            r"(?iu)((?:срок\s+(?:поставки|исполнения|оказания)|поставка\s+осуществляется)[^.\n]{0,120}?(\d{1,4})\s*(рабоч\w*|календар\w*)?\s*дн)",
            text,
        )
        if explicit_match:
            days = int(explicit_match.group(2))
            day_type_raw = (explicit_match.group(3) or "").lower()
            day_type = "working" if "рабоч" in day_type_raw else ("calendar" if "календар" in day_type_raw else None)
            candidates.append(
                _build_candidate(
                    field="execution_days",
                    index=idx,
                    value={"execution_days": days, "day_type": day_type, "trigger": "from_contract_signing"},
                    value_raw=explicit_match.group(1),
                    quote=explicit_match.group(1),
                    file_name=file_name,
                    offset=offset + explicit_match.start(),
                    section=section,
                    confidence_hint=0.9,
                    keywords=["срок поставки"],
                    exclusions=[],
                )
            )
            idx += 1
        else:
            days, day_type = parse_days_ru(text)
            if days is not None and any(word in lowered for word in ("срок", "поставк", "исполн", "оказани")):
                candidates.append(
                    _build_candidate(
                        field="execution_days",
                        index=idx,
                        value={"execution_days": days, "day_type": day_type, "trigger": "from_contract_signing"},
                        value_raw=f"{days} {day_type or ''}".strip(),
                        quote=text,
                        file_name=file_name,
                        offset=offset,
                        section=section,
                        confidence_hint=0.65,
                        keywords=["срок"],
                        exclusions=[],
                    )
                )
                idx += 1

        dates = [datetime.strptime(value, "%d.%m.%Y") for value in _DATE_RE.findall(text)]
        if len(dates) >= 2:
            first = min(dates)
            last = max(dates)
            if last > first:
                delta = (last - first).days
                candidates.append(
                    _build_candidate(
                        field="execution_days",
                        index=idx,
                        value={"execution_days": delta, "trigger": "date_range"},
                        value_raw=f"{first:%d.%m.%Y}-{last:%d.%m.%Y}",
                        quote=text,
                        file_name=file_name,
                        offset=offset,
                        section=section,
                        confidence_hint=0.63,
                        keywords=["дата", "срок"],
                        exclusions=[],
                    )
                )
                idx += 1

    candidates.sort(key=lambda item: (-item["confidence_hint"], item["offset"], item["id"]))
    return candidates


def mine_penalties_candidates(snippets: list[Snippet]) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        section = str(snippet.get("section") or "liability")
        text = str(snippet.get("snippet") or "")
        if not text:
            continue
        lowered = text.lower()
        offset = int(snippet.get("offset") or 0)
        file_name = snippet.get("file")

        value: dict[str, Any] = {}
        penalty = parse_fraction_penalty(text)
        if penalty:
            penalty["per"] = "day"
            value["penalty"] = penalty

        fine_match = re.search(r"(?iu)штраф", text)
        if fine_match:
            fine_text = text
            fine: dict[str, Any] = {}
            percent = parse_percent_ru(fine_text)
            if percent is not None:
                fine["percent"] = float(percent)

            min_match = re.search(r"(?iu)не\s+менее\s+([0-9\s\u00a0\u202f.,]+)", fine_text)
            max_match = re.search(r"(?iu)не\s+более\s+([0-9\s\u00a0\u202f.,]+)", fine_text)
            if min_match:
                min_money = parse_money_ru(min_match.group(1))
                if min_money is not None:
                    fine["min"] = float(min_money)
            if max_match:
                max_money = parse_money_ru(max_match.group(1))
                if max_money is not None:
                    fine["max"] = float(max_money)

            if fine:
                fine["basis"] = "price"
                value["fine"] = fine

        if "1042" in lowered:
            value["pp_reference"] = "1042"

        if value:
            conf = 0.62
            if "penalty" in value:
                conf += 0.2
            if "fine" in value:
                conf += 0.12
            if value.get("pp_reference"):
                conf += 0.05
            candidates.append(
                _build_candidate(
                    field="penalties",
                    index=idx,
                    value=value,
                    value_raw=text,
                    quote=text,
                    file_name=file_name,
                    offset=offset,
                    section=section,
                    confidence_hint=conf,
                    keywords=["пеня", "штраф", "1042"],
                    exclusions=[],
                )
            )
            idx += 1

    candidates.sort(key=lambda item: (-item["confidence_hint"], item["offset"], item["id"]))
    return candidates


def mine_candidates_by_field(snippets_by_section: dict[str, list[Snippet]]) -> dict[str, list[Candidate]]:
    out: dict[str, list[Candidate]] = {
        "nmck": mine_nmck_candidates(snippets_by_section.get("price") or []),
        "payment_terms": mine_payment_candidates(snippets_by_section.get("payment") or []),
        "execution_days": mine_execution_candidates(snippets_by_section.get("execution") or []),
        "penalties": mine_penalties_candidates(snippets_by_section.get("liability") or []),
    }
    return out
