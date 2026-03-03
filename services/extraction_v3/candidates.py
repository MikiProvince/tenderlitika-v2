from __future__ import annotations

import math
import re
from typing import Any, TypedDict

from services.extraction_v3.parsers import parse_date_range_days, parse_days, parse_money, parse_percent
from services.extraction_v3.retrieval import Snippet


class Candidate(TypedDict):
    id: str
    field: str
    value: Any
    value_raw: str
    quote: str
    file: str | None
    offset: int
    signals: dict[str, Any]
    confidence_hint: float


_MONEY_RE = re.compile(r"\d[\d\s\u00A0\u202F.,]*\d(?:[.,]\d{1,2})?")

_NMCK_KEYWORDS = [
    "НМЦК",
    "НМЦ",
    "начальная (максимальная) цена",
    "цена договора",
    "цена контракта",
    "цена лота",
    "по извещению",
]
_NMCK_KW_RE = re.compile(
    r"(?iu)(нмцк|нмц\b|начальн\w*\s*\(максимальн\w*\)\s*цена|цена\s+(?:договора|контракта|лота)|по\s+извещению)"
)
_NMCK_STRONG_RE = re.compile(r"(?iu)(нмцк|начальн\w*\s*\(максимальн\w*\)\s*цена)")
_NMCK_EXCLUSIONS = ["обеспечение", "банковская гарантия", "задаток", "штраф", "пеня"]

_PAYMENT_KEYWORDS = [
    "оплата",
    "расчет",
    "аванс",
    "предоплата",
    "окончательный",
    "платеж",
    "приемка",
    "накладная",
]
_AFTER_ACCEPTANCE_RE = re.compile(r"(?iu)(после\s+поставк\w*|после\s+приемк\w*|после\s+подписани\w+\s+накладн\w*)")
_ADVANCE_PCT_RE = re.compile(r"(?iu)(?:аванс|предоплат\w*)[^\n%]{0,120}?(\d+(?:[.,]\d+)?)\s*%")
_FINAL_PCT_RE = re.compile(r"(?iu)(?:окончательн\w*\s+(?:расчет|оплат\w*)|оставш\w+\s+част\w*)[^\n%]{0,120}?(\d+(?:[.,]\d+)?)\s*%")
_ADVANCE_DAYS_RE = re.compile(r"(?iu)(?:аванс|предоплат\w*)[^\n]{0,140}?(\d{1,4}\s*(?:рабоч\w*|календарн\w*)?\s*(?:дн\w*|дней|день|дня))")
_FINAL_DAYS_RE = re.compile(r"(?iu)(?:окончательн\w*\s+(?:расчет|оплат\w*)|после\s+приемк\w*|после\s+поставк\w*)[^\n]{0,160}?(\d{1,4}\s*(?:рабоч\w*|календарн\w*)?\s*(?:дн\w*|дней|день|дня))")
_PAYMENT_CONTEXT_DAYS_RE = re.compile(
    r"(?iu)(?:оплат\w*|расчет\w*|платеж\w*|аванс|предоплат\w*|приемк\w*|накладн\w*)[^\n]{0,110}?(\d{1,4}\s*(?:рабоч\w*|календарн\w*)?\s*(?:дн\w*|дней|день|дня))"
)

_EXECUTION_KEYWORDS = ["срок поставки", "срок исполнения", "исполнения", "поставка", "отгрузка"]
_EXECUTION_DAYS_RE = re.compile(
    r"(?iu)(?:срок\s+(?:поставк\w*|исполнени\w*)|поставк\w*|исполнени\w*)[^\n]{0,160}?(\d{1,4}\s*(?:рабоч\w*|календарн\w*)?\s*(?:дн\w*|дней|день|дня))"
)
_DATE_RANGE_RE = re.compile(
    r"(?iu)(?:с|со)\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}\s*(?:-|–|—|по)\s*\d{1,2}[./-]\d{1,2}[./-]\d{2,4}"
)

_PENALTY_KEYWORDS = ["пеня", "неустойк", "штраф", "ответственность"]
_PENALTY_PER_DAY_RE = re.compile(
    r"(?iu)(?:пен[яи]|неустойк\w*)[^\n%]{0,140}?(\d+(?:[.,]\d+)?)\s*%[^\n]{0,120}?(?:за\s+кажд\w+\s+дн\w*|в\s+день|ежеднев|сутк)"
)
_CAP_RE = re.compile(r"(?iu)(?:не\s+более|ограничива\w*\s+размером)\s+(\d+(?:[.,]\d+)?)\s*%")
_FINE_PERCENT_RE = re.compile(r"(?iu)штраф\w*[^\n%]{0,100}?(\d+(?:[.,]\d+)?)\s*%")
_FINE_MONEY_RE = re.compile(r"(?iu)штраф\w*[^\n]{0,100}?(\d[\d\s\u00A0\u202F.,]*\d(?:[.,]\d{1,2})?)")


def _clamp(value: float) -> float:
    return round(max(0.0, min(1.0, value)), 4)


def _clip_quote(text: str, start: int, end: int, radius: int = 150, max_len: int = 300) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    quote = text[left:right].strip()
    if len(quote) <= max_len:
        return quote
    return quote[:max_len].rstrip()


def _dedupe_keep_order(candidates: list[Candidate]) -> list[Candidate]:
    deduped: list[Candidate] = []
    seen: set[tuple[str, str, int]] = set()
    for candidate in candidates:
        key = (candidate["field"], str(candidate["value"]), int(candidate["offset"]))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(candidate)
    return deduped


def _sort_candidates(candidates: list[Candidate], limit: int = 10) -> list[Candidate]:
    ordered = sorted(
        candidates,
        key=lambda item: (
            -float(item.get("confidence_hint") or 0.0),
            int(item.get("offset") or 0),
            str(item.get("id") or ""),
        ),
    )
    return _dedupe_keep_order(ordered)[:limit]


def mine_nmck_candidates(corpus: str, snippets: list[Snippet]) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        snippet_text = snippet.get("snippet") or ""
        base_offset = int(snippet.get("offset") or 0)
        if not snippet_text:
            continue

        for kw_match in _NMCK_KW_RE.finditer(snippet_text):
            left = max(0, kw_match.start() - 220)
            right = min(len(snippet_text), kw_match.end() + 220)
            local = snippet_text[left:right]
            for money_match in _MONEY_RE.finditer(local):
                raw_amount = money_match.group(0)
                value = parse_money(raw_amount)
                if value is None:
                    continue
                abs_start = base_offset + left + money_match.start()
                abs_end = base_offset + left + money_match.end()
                quote = _clip_quote(corpus, abs_start, abs_end)
                quote_l = quote.lower()

                exclusions = [word for word in _NMCK_EXCLUSIONS if word in quote_l]
                has_strong_kw = bool(_NMCK_STRONG_RE.search(quote))
                confidence = 0.45
                distance = abs((left + money_match.start()) - kw_match.start())
                confidence += 0.25 * (1.0 - min(220, distance) / 220.0)
                if has_strong_kw:
                    confidence += 0.22
                if ("руб" in quote_l) or ("₽" in quote):
                    confidence += 0.05
                if exclusions and not has_strong_kw:
                    confidence -= 0.35
                if not (1_000 <= value <= 100_000_000_000):
                    confidence -= 0.2

                kw_hits = [kw for kw in _NMCK_KEYWORDS if kw.lower() in quote_l]
                candidates.append(
                    Candidate(
                        id=f"nmck_{idx}",
                        field="nmck",
                        value=float(value),
                        value_raw=raw_amount,
                        quote=quote,
                        file=snippet.get("file"),
                        offset=abs_start,
                        signals={
                            "keywords": kw_hits,
                            "nearby_exclusions": exclusions,
                            "section": snippet.get("section"),
                        },
                        confidence_hint=_clamp(confidence),
                    )
                )
                idx += 1

    return _sort_candidates(candidates, limit=10)


def _to_calendar_days(days: int, day_type: str | None) -> int:
    if day_type == "working":
        return int(math.ceil(days * 1.4))
    return days


def mine_payment_candidates(corpus: str, snippets: list[Snippet]) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        text = snippet.get("snippet") or ""
        if not text:
            continue
        base_offset = int(snippet.get("offset") or 0)
        lowered = text.lower()

        advance_percent = None
        final_percent = None
        advance_days_calendar = None
        final_days_working = None
        final_days_calendar_alt = None
        conservative_values: list[int] = []

        m = _ADVANCE_PCT_RE.search(text)
        if m:
            advance_percent = parse_percent(m.group(0))

        m = _FINAL_PCT_RE.search(text)
        if m:
            final_percent = parse_percent(m.group(0))

        m = _ADVANCE_DAYS_RE.search(text)
        if m:
            parsed_days, day_type = parse_days(m.group(1))
            if parsed_days is not None:
                advance_days_calendar = _to_calendar_days(parsed_days, day_type)
                conservative_values.append(advance_days_calendar)

        m = _FINAL_DAYS_RE.search(text)
        if m:
            parsed_days, day_type = parse_days(m.group(1))
            if parsed_days is not None:
                if day_type == "working":
                    final_days_working = parsed_days
                    conservative_values.append(_to_calendar_days(parsed_days, day_type))
                else:
                    final_days_calendar_alt = parsed_days
                    conservative_values.append(parsed_days)

        for generic in _PAYMENT_CONTEXT_DAYS_RE.finditer(text):
            parsed_days, day_type = parse_days(generic.group(1))
            if parsed_days is not None:
                conservative_values.append(_to_calendar_days(parsed_days, day_type))

        payment_after_acceptance = bool(_AFTER_ACCEPTANCE_RE.search(text))
        if payment_after_acceptance and conservative_values:
            conservative_values.append(max(conservative_values))

        conservative_days = max(conservative_values) if conservative_values else None

        signals_count = sum(
            int(v is not None)
            for v in (
                advance_percent,
                advance_days_calendar,
                final_percent,
                final_days_working,
                final_days_calendar_alt,
                conservative_days,
            )
        )
        if signals_count == 0 and not payment_after_acceptance:
            continue

        confidence = 0.22 + 0.09 * signals_count
        if any(keyword in lowered for keyword in _PAYMENT_KEYWORDS):
            confidence += 0.16
        if payment_after_acceptance:
            confidence += 0.08
        if (
            isinstance(advance_percent, (int, float))
            and isinstance(final_percent, (int, float))
            and 85 <= (advance_percent + final_percent) <= 110
        ):
            confidence += 0.08

        value = {
            "advance_percent": advance_percent,
            "advance_days_calendar": advance_days_calendar,
            "final_percent": final_percent,
            "final_days_working": final_days_working,
            "final_days_calendar_alt": final_days_calendar_alt,
            "payment_after_acceptance": payment_after_acceptance,
            "conservative_days": conservative_days,
        }

        keyword_hits = [kw for kw in _PAYMENT_KEYWORDS if kw in lowered]
        candidates.append(
            Candidate(
                id=f"payment_terms_{idx}",
                field="payment_terms",
                value=value,
                value_raw=text[:260],
                quote=text[:300],
                file=snippet.get("file"),
                offset=base_offset,
                signals={
                    "keywords": keyword_hits,
                    "nearby_exclusions": [],
                    "section": snippet.get("section"),
                },
                confidence_hint=_clamp(confidence),
            )
        )
        idx += 1

    return _sort_candidates(candidates, limit=10)


def mine_execution_candidates(corpus: str, snippets: list[Snippet]) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        text = snippet.get("snippet") or ""
        if not text:
            continue
        base_offset = int(snippet.get("offset") or 0)
        lowered = text.lower()

        local: list[tuple[int, str, int, int, float]] = []
        for match in _EXECUTION_DAYS_RE.finditer(text):
            days, day_type = parse_days(match.group(1))
            if days is None:
                continue
            cal_days = _to_calendar_days(days, day_type)
            local.append((cal_days, match.group(1), match.start(), match.end(), 0.45))

        for match in _DATE_RANGE_RE.finditer(text):
            range_days = parse_date_range_days(match.group(0))
            if range_days is None:
                continue
            local.append((range_days, match.group(0), match.start(), match.end(), 0.38))

        for days, raw, start, end, base_score in local:
            if not (1 <= days <= 5000):
                continue
            abs_start = base_offset + start
            abs_end = base_offset + end
            quote = _clip_quote(corpus, abs_start, abs_end)
            confidence = base_score
            if any(keyword in quote.lower() for keyword in _EXECUTION_KEYWORDS):
                confidence += 0.22
            keyword_hits = [kw for kw in _EXECUTION_KEYWORDS if kw in lowered]
            candidates.append(
                Candidate(
                    id=f"execution_{idx}",
                    field="execution",
                    value=int(days),
                    value_raw=raw,
                    quote=quote,
                    file=snippet.get("file"),
                    offset=abs_start,
                    signals={
                        "keywords": keyword_hits,
                        "nearby_exclusions": [],
                        "section": snippet.get("section"),
                    },
                    confidence_hint=_clamp(confidence),
                )
            )
            idx += 1

    return _sort_candidates(candidates, limit=10)


def mine_penalties_candidates(corpus: str, snippets: list[Snippet]) -> list[Candidate]:
    candidates: list[Candidate] = []
    idx = 1

    for snippet in snippets:
        text = snippet.get("snippet") or ""
        if not text:
            continue
        base_offset = int(snippet.get("offset") or 0)
        lowered = text.lower()

        per_day = None
        cap_percent = None
        fine_percent = None
        fixed_fine_amount = None

        m = _PENALTY_PER_DAY_RE.search(text)
        if m:
            per_day = parse_percent(m.group(0))

        m = _CAP_RE.search(text)
        if m:
            cap_percent = parse_percent(m.group(0))

        m = _FINE_PERCENT_RE.search(text)
        if m:
            fine_candidate = parse_percent(m.group(0))
            if fine_candidate is not None:
                fine_quote = m.group(0).lower()
                if not any(word in fine_quote for word in ("в день", "ежеднев", "сутк")):
                    fine_percent = fine_candidate

        m = _FINE_MONEY_RE.search(text)
        if m:
            fixed_fine_amount = parse_money(m.group(1))

        if all(value is None for value in (per_day, cap_percent, fine_percent, fixed_fine_amount)):
            continue

        confidence = 0.28
        if per_day is not None:
            confidence += 0.28
        if cap_percent is not None:
            confidence += 0.12
        if fine_percent is not None:
            confidence += 0.12
        if fixed_fine_amount is not None:
            confidence += 0.08
        if any(keyword in lowered for keyword in _PENALTY_KEYWORDS):
            confidence += 0.1

        value = {
            "penalty_percent_per_day": per_day,
            "cap_percent": cap_percent,
            "fine_percent": fine_percent,
            "fixed_fine_amount": fixed_fine_amount,
        }
        keyword_hits = [kw for kw in _PENALTY_KEYWORDS if kw in lowered]

        candidates.append(
            Candidate(
                id=f"penalties_{idx}",
                field="penalties",
                value=value,
                value_raw=text[:260],
                quote=text[:300],
                file=snippet.get("file"),
                offset=base_offset,
                signals={
                    "keywords": keyword_hits,
                    "nearby_exclusions": [],
                    "section": snippet.get("section"),
                },
                confidence_hint=_clamp(confidence),
            )
        )
        idx += 1

    return _sort_candidates(candidates, limit=10)


def mine_candidates(corpus: str, retrieved_sections: dict[str, list[Snippet]]) -> dict[str, list[Candidate]]:
    return {
        "nmck": mine_nmck_candidates(corpus, retrieved_sections.get("price") or []),
        "payment_terms": mine_payment_candidates(corpus, retrieved_sections.get("payment") or []),
        "execution": mine_execution_candidates(corpus, retrieved_sections.get("execution") or []),
        "penalties": mine_penalties_candidates(corpus, retrieved_sections.get("liability") or []),
    }
