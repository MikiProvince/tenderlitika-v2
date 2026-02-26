from __future__ import annotations

import math
import re
from typing import Any, TypedDict

from services.extraction.file_markers import locate_offset_to_file, split_by_file_markers
from services.extraction.normalize import normalize_text
from services.extraction.parsers import parse_date_range, parse_money, parse_percent
from services.extraction.retrieval import retrieve_sections


class Candidate(TypedDict):
    id: str
    field: str
    value: Any
    value_raw: str
    quote: str
    keyword_hits: list[str]
    location: dict[str, Any]
    confidence: float


_NMCK_KEYWORDS = [
    "нмцк",
    "нмц",
    "начальная (максимальная) цена",
    "цена договора",
    "цена контракта",
    "цена лота",
    "по извещению",
]

_NMCK_KW_RE = re.compile(
    r"(?iu)(нмцк|нмц\b|начальн\w*\s*\(максимальн\w*\)\s*цена|цена\s+(?:договора|контракта|лота)|по\s+извещению)"
)
_NMCK_STRONG_KW_RE = re.compile(r"(?iu)(нмцк|начальн\w*\s*\(максимальн\w*\)\s*цена)")
_MONEY_RE = re.compile(r"\d[\d\s\u00A0\u202F]{0,24}(?:[.,]\d{1,2})?")
_SECURITY_RE = re.compile(r"(?iu)(обеспечени|гаранти|задаток)")

_PAYMENT_KEYWORDS = [
    "оплата",
    "расчет",
    "аванс",
    "предоплата",
    "окончательный",
    "платеж",
]
_PAYMENT_AFTER_FULL_RE = re.compile(
    r"(?iu)(после\s+полной\s+поставки|после\s+поставки\s+всего\s+объема|после\s+полного\s+исполнения)"
)
_PAYMENT_DAYS_RE = re.compile(
    r"(?iu)в\s+течение\s+(\d{1,3})\s*(рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней)"
)
_PAYMENT_DAYS_ALT_RE = re.compile(
    r"(?iu)(?:оплат\w*|расчет\w*|платеж\w*)[^\n]{0,100}?(\d{1,3})\s*(рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней)"
)
_ADVANCE_PERCENT_RE = re.compile(r"(?iu)(?:аванс|предоплат\w*)[^\n%]{0,80}?(\d+(?:[.,]\d+)?)\s*%")
_FINAL_PERCENT_RE = re.compile(
    r"(?iu)(?:окончательн\w*\s+(?:расчет|оплат\w*)|окончательн\w*)[^\n%]{0,120}?(\d+(?:[.,]\d+)?)\s*%"
)
_ADVANCE_DAYS_RE = re.compile(
    r"(?iu)(?:аванс|предоплат\w*)[^\n]{0,120}?(\d{1,3})\s*(рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней)"
)
_FINAL_DAYS_RE = re.compile(
    r"(?iu)(?:окончательн\w*\s+(?:расчет|оплат\w*)|окончательн\w*)[^\n]{0,140}?(\d{1,3})\s*(рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней)"
)

_EXECUTION_KEYWORDS = ["срок", "поставка", "исполнения", "отгруз", "партия"]
_EXECUTION_DAYS_RE = re.compile(
    r"(?iu)(?:срок\s+(?:поставки|исполнения)|поставка|отгруз\w*|исполнени\w*)[^\n]{0,120}?(\d{1,4})\s*(рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней)"
)
_EXECUTION_DAYS_ALT_RE = re.compile(
    r"(?iu)в\s+течение\s+(\d{1,4})\s*(рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней)"
)

_PENALTY_KEYWORDS = ["пеня", "неустойк", "штраф", "ответственность"]
_PENALTY_PER_DAY_RE = re.compile(
    r"(?iu)(?:пен[яи]|неустойк\w*)[^\n%]{0,120}?(\d+(?:[.,]\d+)?)\s*%[^\n]{0,100}?(?:за\s+кажд\w+\s+д|в\s+день|ежеднев|сутк)"
)
_PENALTY_PER_DAY_ALT_RE = re.compile(
    r"(?iu)(\d+(?:[.,]\d+)?)\s*%[^\n]{0,80}?(?:пен[яи]|неустойк\w*)[^\n]{0,80}?(?:за\s+кажд\w+\s+д|в\s+день|ежеднев|сутк)"
)
_PENALTY_CAP_RE = re.compile(r"(?iu)не\s+более\s+(\d+(?:[.,]\d+)?)\s*%")
_FINE_RE = re.compile(r"(?iu)штраф\w*[^\n%]{0,80}?(\d+(?:[.,]\d+)?)\s*%")


def _clamp_confidence(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def _clip_quote(text: str, start: int, end: int, radius: int = 170, max_len: int = 300) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    quote = text[left:right].strip()
    if len(quote) <= max_len:
        return quote
    return quote[: max_len - 1].rstrip() + "…"


def _iter_search_spaces(corpus: str, snippets: list[dict[str, Any]] | None) -> list[tuple[str, int]]:
    if not snippets:
        return [(corpus, 0)]

    spaces: list[tuple[str, int]] = []
    for snippet in snippets:
        text = snippet.get("snippet") or ""
        if not text:
            continue
        offset = int(snippet.get("offset") or 0)
        spaces.append((text, offset))
    return spaces or [(corpus, 0)]


def _keyword_hits(quote: str, keywords: list[str]) -> list[str]:
    quote_l = quote.lower()
    hits: list[str] = []
    for keyword in keywords:
        if keyword.lower() in quote_l and keyword not in hits:
            hits.append(keyword)
    return hits


def _build_candidate(
    *,
    candidate_id: str,
    field: str,
    value: Any,
    value_raw: str,
    quote: str,
    keyword_hits: list[str],
    blocks: list[dict[str, Any]],
    offset: int,
    confidence: float,
) -> Candidate:
    file_name = locate_offset_to_file(blocks, offset)
    location: dict[str, Any] = {"offset": offset}
    if file_name:
        location["file"] = file_name
    return {
        "id": candidate_id,
        "field": field,
        "value": value,
        "value_raw": value_raw,
        "quote": quote,
        "keyword_hits": keyword_hits,
        "location": location,
        "confidence": _clamp_confidence(confidence),
    }


def _working_to_calendar(days: int) -> int:
    return int(math.ceil(days * 1.4))


def _day_pair_to_calendar(days: int, unit: str | None) -> int:
    if unit and "рабоч" in unit.lower():
        return _working_to_calendar(days)
    return days


def _mine_nmck_candidates_in_snippets(
    corpus: str,
    blocks: list[dict[str, Any]],
    snippets: list[dict[str, Any]] | None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    spaces = _iter_search_spaces(corpus, snippets)
    candidate_index = 0

    for snippet, base_offset in spaces:
        for kw_match in _NMCK_KW_RE.finditer(snippet):
            near_left = max(0, kw_match.start() - 220)
            near_right = min(len(snippet), kw_match.end() + 220)
            local = snippet[near_left:near_right]
            for money_match in _MONEY_RE.finditer(local):
                raw_value = money_match.group(0)
                parsed = parse_money(raw_value)
                if parsed is None:
                    continue

                abs_start = base_offset + near_left + money_match.start()
                abs_end = base_offset + near_left + money_match.end()
                quote = _clip_quote(corpus, abs_start, abs_end)
                quote_l = quote.lower()

                distance = abs((near_left + money_match.start()) - kw_match.start())
                confidence = 0.35 + 0.3 * (1.0 - min(distance, 220) / 220.0)
                if _NMCK_STRONG_KW_RE.search(quote):
                    confidence += 0.25
                if "руб" in quote_l or "₽" in quote:
                    confidence += 0.08
                if _SECURITY_RE.search(quote) and not _NMCK_STRONG_KW_RE.search(quote):
                    confidence -= 0.25
                if "цена" in quote_l:
                    confidence += 0.05
                if not (1_000 <= parsed <= 100_000_000_000):
                    confidence -= 0.2

                candidate_index += 1
                candidates.append(
                    _build_candidate(
                        candidate_id=f"nmck_{candidate_index}",
                        field="nmck",
                        value=float(parsed),
                        value_raw=raw_value,
                        quote=quote,
                        keyword_hits=_keyword_hits(quote, _NMCK_KEYWORDS),
                        blocks=blocks,
                        offset=abs_start,
                        confidence=confidence,
                    )
                )

    deduped: list[Candidate] = []
    seen: set[tuple[float, str | None]] = set()
    for candidate in sorted(candidates, key=lambda item: item["confidence"], reverse=True):
        try:
            dedupe_value = round(float(candidate["value"]), 2)
        except Exception:
            continue
        dedupe_key = (dedupe_value, candidate["location"].get("file"))
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        deduped.append(candidate)
        if len(deduped) >= 8:
            break
    return deduped


def mine_nmck_candidates(corpus: str, blocks: list[dict[str, Any]]) -> list[Candidate]:
    normalized = normalize_text(corpus or "")
    snippets = retrieve_sections(normalized).get("price") or []
    return _mine_nmck_candidates_in_snippets(normalized, blocks, snippets)


def _mine_payment_candidates_in_snippets(
    corpus: str,
    blocks: list[dict[str, Any]],
    snippets: list[dict[str, Any]] | None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    spaces = _iter_search_spaces(corpus, snippets)
    candidate_index = 0

    for snippet, base_offset in spaces:
        snippet_l = snippet.lower()
        advance_percent = None
        final_percent = None
        advance_days_calendar = None
        final_days_working = None
        final_days_calendar_alt = None
        payment_after_full_delivery = bool(_PAYMENT_AFTER_FULL_RE.search(snippet))
        generic_calendar_days: list[int] = []

        m = _ADVANCE_PERCENT_RE.search(snippet)
        if m:
            advance_percent = parse_percent(m.group(0))

        m = _FINAL_PERCENT_RE.search(snippet)
        if m:
            final_percent = parse_percent(m.group(0))

        m = _ADVANCE_DAYS_RE.search(snippet)
        if m:
            raw_days = int(m.group(1))
            unit = m.group(2) or ""
            advance_days_calendar = _day_pair_to_calendar(raw_days, unit)

        m = _FINAL_DAYS_RE.search(snippet)
        if m:
            raw_days = int(m.group(1))
            unit = (m.group(2) or "").lower()
            if "рабоч" in unit:
                final_days_working = raw_days
            else:
                final_days_calendar_alt = raw_days

        for match in _PAYMENT_DAYS_RE.finditer(snippet):
            raw_days = int(match.group(1))
            unit = match.group(2) or ""
            generic_calendar_days.append(_day_pair_to_calendar(raw_days, unit))

        for match in _PAYMENT_DAYS_ALT_RE.finditer(snippet):
            raw_days = int(match.group(1))
            unit = match.group(2) or ""
            generic_calendar_days.append(_day_pair_to_calendar(raw_days, unit))

        conservative_days: list[int] = []
        if final_days_working is not None:
            conservative_days.append(_working_to_calendar(final_days_working))
        if final_days_calendar_alt is not None:
            conservative_days.append(final_days_calendar_alt)
        conservative_days.extend(generic_calendar_days)
        payment_terms_days = max(conservative_days) if conservative_days else None

        signals = [
            advance_percent is not None,
            final_percent is not None,
            advance_days_calendar is not None,
            final_days_working is not None,
            final_days_calendar_alt is not None,
            payment_terms_days is not None,
            payment_after_full_delivery,
        ]
        if not any(signals):
            continue

        confidence = 0.2 + 0.1 * sum(1 for signal in signals if signal)
        if any(keyword in snippet_l for keyword in _PAYMENT_KEYWORDS):
            confidence += 0.18
        if "в течение" in snippet_l:
            confidence += 0.08
        if (
            isinstance(advance_percent, (int, float))
            and isinstance(final_percent, (int, float))
            and 70 <= (advance_percent + final_percent) <= 110
        ):
            confidence += 0.07

        value = {
            "advance_percent": advance_percent,
            "advance_days_calendar": advance_days_calendar,
            "final_percent": final_percent,
            "final_days_working": final_days_working,
            "final_days_calendar_alt": final_days_calendar_alt,
            "payment_after_full_delivery": payment_after_full_delivery,
            "payment_terms_days": payment_terms_days,
        }

        offset_in_snippet = 0
        kw_position = re.search(r"(?iu)(оплат\w*|расчет\w*|аванс|предоплат\w*)", snippet)
        if kw_position:
            offset_in_snippet = kw_position.start()

        candidate_index += 1
        candidates.append(
            _build_candidate(
                candidate_id=f"payment_{candidate_index}",
                field="payment_terms",
                value=value,
                value_raw=snippet[:220],
                quote=(snippet[:299] + "…") if len(snippet) > 300 else snippet,
                keyword_hits=_keyword_hits(snippet, _PAYMENT_KEYWORDS),
                blocks=blocks,
                offset=base_offset + offset_in_snippet,
                confidence=confidence,
            )
        )

    candidates.sort(
        key=lambda item: (
            item["confidence"],
            len(item.get("keyword_hits") or []),
            (item["value"].get("payment_terms_days") or 0) if isinstance(item["value"], dict) else 0,
        ),
        reverse=True,
    )
    return candidates[:8]


def mine_payment_candidates(corpus: str, blocks: list[dict[str, Any]]) -> list[Candidate]:
    normalized = normalize_text(corpus or "")
    snippets = retrieve_sections(normalized).get("payment") or []
    return _mine_payment_candidates_in_snippets(normalized, blocks, snippets)


def _mine_execution_candidates_in_snippets(
    corpus: str,
    blocks: list[dict[str, Any]],
    snippets: list[dict[str, Any]] | None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    spaces = _iter_search_spaces(corpus, snippets)
    candidate_index = 0

    for snippet, base_offset in spaces:
        local_candidates: list[tuple[int, str, int, int, float]] = []

        for match in _EXECUTION_DAYS_RE.finditer(snippet):
            raw_days = int(match.group(1))
            unit = match.group(2) or ""
            days = _day_pair_to_calendar(raw_days, unit)
            score = 0.35
            if unit and "календар" in unit.lower():
                score += 0.1
            local_candidates.append((days, match.group(0), match.start(), match.end(), score))

        for match in _EXECUTION_DAYS_ALT_RE.finditer(snippet):
            raw_days = int(match.group(1))
            unit = match.group(2) or ""
            days = _day_pair_to_calendar(raw_days, unit)
            local_candidates.append((days, match.group(0), match.start(), match.end(), 0.28))

        for date_match in re.finditer(
            r"(?iu)(?:с|со)\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*(?:-|–|—|по)\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}",
            snippet,
        ):
            range_days = parse_date_range(date_match.group(0))
            if range_days is None:
                continue
            local_candidates.append((range_days, date_match.group(0), date_match.start(), date_match.end(), 0.3))

        for days, raw_value, start, end, base_score in local_candidates:
            if not (1 <= days <= 5000):
                continue
            abs_start = base_offset + start
            abs_end = base_offset + end
            quote = _clip_quote(corpus, abs_start, abs_end)
            confidence = base_score
            if any(keyword in quote.lower() for keyword in _EXECUTION_KEYWORDS):
                confidence += 0.22
            if "срок" in quote.lower():
                confidence += 0.1

            candidate_index += 1
            candidates.append(
                _build_candidate(
                    candidate_id=f"execution_{candidate_index}",
                    field="execution_days",
                    value=days,
                    value_raw=raw_value,
                    quote=quote,
                    keyword_hits=_keyword_hits(quote, _EXECUTION_KEYWORDS),
                    blocks=blocks,
                    offset=abs_start,
                    confidence=confidence,
                )
            )

    candidates.sort(
        key=lambda item: (
            item["confidence"],
            len(item.get("keyword_hits") or []),
            -int(item.get("value") or 0),
        ),
        reverse=True,
    )
    return candidates[:8]


def mine_execution_candidates(corpus: str, blocks: list[dict[str, Any]]) -> list[Candidate]:
    normalized = normalize_text(corpus or "")
    snippets = retrieve_sections(normalized).get("execution") or []
    return _mine_execution_candidates_in_snippets(normalized, blocks, snippets)


def _mine_penalty_candidates_in_snippets(
    corpus: str,
    blocks: list[dict[str, Any]],
    snippets: list[dict[str, Any]] | None,
) -> list[Candidate]:
    candidates: list[Candidate] = []
    spaces = _iter_search_spaces(corpus, snippets)
    candidate_index = 0

    for snippet, base_offset in spaces:
        penalty_per_day = None
        penalty_cap = None
        fine_percent = None
        first_offset = 0

        m = _PENALTY_PER_DAY_RE.search(snippet)
        if m:
            penalty_per_day = parse_percent(m.group(0))
            first_offset = m.start()
        if penalty_per_day is None:
            m = _PENALTY_PER_DAY_ALT_RE.search(snippet)
            if m:
                penalty_per_day = parse_percent(m.group(0))
                first_offset = m.start()

        m = _PENALTY_CAP_RE.search(snippet)
        if m:
            penalty_cap = parse_percent(m.group(0))
            if first_offset == 0:
                first_offset = m.start()

        m = _FINE_RE.search(snippet)
        if m:
            parsed_fine = parse_percent(m.group(0))
            if parsed_fine is not None:
                fine_quote = snippet[max(0, m.start() - 20): m.end() + 20].lower()
                if not any(word in fine_quote for word in ("день", "дня", "сутк", "ежеднев")):
                    fine_percent = parsed_fine
                    if first_offset == 0:
                        first_offset = m.start()

        if penalty_per_day is None and penalty_cap is None and fine_percent is None:
            continue

        confidence = 0.25
        if penalty_per_day is not None:
            confidence += 0.32
        if penalty_cap is not None:
            confidence += 0.12
        if fine_percent is not None:
            confidence += 0.14
        if any(keyword in snippet.lower() for keyword in _PENALTY_KEYWORDS):
            confidence += 0.12

        value = {
            "penalty_percent_per_day": penalty_per_day,
            "penalty_cap_percent": penalty_cap,
            "fine_percent": fine_percent,
        }

        candidate_index += 1
        candidates.append(
            _build_candidate(
                candidate_id=f"penalties_{candidate_index}",
                field="penalties",
                value=value,
                value_raw=snippet[:220],
                quote=(snippet[:299] + "…") if len(snippet) > 300 else snippet,
                keyword_hits=_keyword_hits(snippet, _PENALTY_KEYWORDS),
                blocks=blocks,
                offset=base_offset + first_offset,
                confidence=confidence,
            )
        )

    candidates.sort(
        key=lambda item: (
            item["confidence"],
            len(item.get("keyword_hits") or []),
        ),
        reverse=True,
    )
    return candidates[:8]


def mine_penalty_candidates(corpus: str, blocks: list[dict[str, Any]]) -> list[Candidate]:
    normalized = normalize_text(corpus or "")
    snippets = retrieve_sections(normalized).get("penalties") or []
    return _mine_penalty_candidates_in_snippets(normalized, blocks, snippets)


def mine_all_candidates(corpus: str) -> dict[str, list[Candidate]]:
    normalized = normalize_text(corpus or "")
    blocks = split_by_file_markers(normalized)
    retrieved_sections = retrieve_sections(normalized)

    nmck = _mine_nmck_candidates_in_snippets(normalized, blocks, retrieved_sections.get("price"))
    payment = _mine_payment_candidates_in_snippets(normalized, blocks, retrieved_sections.get("payment"))
    execution = _mine_execution_candidates_in_snippets(normalized, blocks, retrieved_sections.get("execution"))
    penalties = _mine_penalty_candidates_in_snippets(normalized, blocks, retrieved_sections.get("penalties"))

    return {
        "nmck": nmck,
        "payment": payment,
        "execution": execution,
        "penalties": penalties,
    }
