from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation


_SPACE_RE = re.compile(r"[\s\u00a0\u202f]+")
_MONEY_RE = re.compile(
    r"(?<!\d)(\d{1,3}(?:[ \u00a0\u202f]\d{3})+(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)(?!\d)"
)
_PERCENT_RE = re.compile(r"(?iu)(\d{1,3}(?:[.,]\d+)?)\s*(?:%|процент\w*)")
_DAYS_RE = re.compile(
    r"(?iu)(\d{1,4})\s*(рабоч\w*|календар\w*)?\s*дн(?:я|ей|ь)?"
)
_FRACTION_PENALTY_RE = re.compile(
    r"(?iu)\b(\d+)\s*/\s*(\d+)\b[^.\n]{0,120}ключев\w*\s+ставк\w*"
)


def normalize_number_tokens(text: str) -> list[str]:
    if not text:
        return []
    standardized = text.replace("\t", "|").replace(";", "|")
    parts: list[str] = []
    for chunk in standardized.split("|"):
        pieces = re.split(r"\s{2,}", chunk)
        for piece in pieces:
            cleaned = piece.strip()
            if cleaned:
                parts.append(cleaned)
    return parts


def _to_decimal(raw: str) -> Decimal | None:
    s = _SPACE_RE.sub("", raw or "")
    s = s.replace("₽", "")
    s = re.sub(r"(?iu)\b(?:руб(?:\.|ля|лей)?|rur|rub)\b", "", s)
    s = s.strip()
    if not s:
        return None

    if "," in s and "." in s:
        last_comma = s.rfind(",")
        last_dot = s.rfind(".")
        if last_comma > last_dot:
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        s = s.replace(",", ".")
    elif s.count(".") > 1:
        left = s[:-1].replace(".", "")
        s = left + s[-1]

    s = re.sub(r"[^0-9.\-]", "", s)
    if not s or s in {"-", ".", "-."}:
        return None

    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def parse_money_ru(text: str) -> Decimal | None:
    if not text:
        return None
    for match in _MONEY_RE.finditer(text):
        value = _to_decimal(match.group(1))
        if value is not None:
            return value
    return None


def parse_percent_ru(text: str) -> Decimal | None:
    if not text:
        return None
    match = _PERCENT_RE.search(text)
    if not match:
        return None
    return _to_decimal(match.group(1))


def parse_days_ru(text: str) -> tuple[int | None, str | None]:
    if not text:
        return None, None

    match = _DAYS_RE.search(text)
    if not match:
        return None, None

    days_raw = match.group(1)
    day_kind_raw = (match.group(2) or "").lower()
    try:
        days = int(days_raw)
    except Exception:
        return None, None

    if "рабоч" in day_kind_raw:
        return days, "working"
    if "календар" in day_kind_raw:
        return days, "calendar"
    return days, None


def parse_fraction_penalty(text: str) -> dict | None:
    if not text:
        return None
    match = _FRACTION_PENALTY_RE.search(text)
    if not match:
        return None
    try:
        numerator = int(match.group(1))
        denominator = int(match.group(2))
    except Exception:
        return None
    if denominator <= 0:
        return None
    return {
        "type": "key_rate_fraction",
        "numerator": numerator,
        "denominator": denominator,
    }
