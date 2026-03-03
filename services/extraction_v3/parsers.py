from __future__ import annotations

import re
from datetime import date, datetime

from services.extraction_v3.normalize import normalize_text


_DATE_NUM_RE = re.compile(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})")
_DATE_WORD_RE = re.compile(
    r"(?iu)(\d{1,2})\s+(января|февраля|марта|апреля|мая|июня|июля|августа|сентября|октября|ноября|декабря)\s+(\d{4})"
)
_PERCENT_RE = re.compile(r"(-?\d+(?:[.,]\d+)?)\s*%")
_PERCENT_WORD_RE = re.compile(r"(?iu)(-?\d+(?:[.,]\d+)?)\s*процент\w*")
_DAYS_RE = re.compile(
    r"(?iu)(\d{1,4})\s*(рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней|сут\w*)"
)

_MONTHS = {
    "января": 1,
    "февраля": 2,
    "марта": 3,
    "апреля": 4,
    "мая": 5,
    "июня": 6,
    "июля": 7,
    "августа": 8,
    "сентября": 9,
    "октября": 10,
    "ноября": 11,
    "декабря": 12,
}


def _prepare(raw: str) -> str:
    return normalize_text(raw or "")


def _normalize_number_token(value: str) -> str:
    token = re.sub(r"\s+", "", value).strip(".,")
    if not token:
        return ""

    if "," in token and "." in token:
        if token.rfind(",") > token.rfind("."):
            token = token.replace(".", "").replace(",", ".")
        else:
            token = token.replace(",", "")
        return token

    if "," in token:
        if re.search(r",\d{1,2}$", token):
            return token.replace(",", ".")
        return token.replace(",", "")

    if "." in token and not re.search(r"\.\d{1,2}$", token):
        return token.replace(".", "")
    return token


def parse_money(raw: str) -> float | None:
    value = _prepare(raw)
    if not value:
        return None

    value = value.replace("₽", "")
    value = re.sub(r"(?iu)\b(?:руб(?:\.|ля|лей)?|rur|rub)\b", "", value)
    value = re.sub(r"(?iu)\b(?:без\s*ндс|ндс)\b", "", value)

    match = re.search(r"[-+]?\d[\d\s\u00A0\u202F.,]*", value)
    if not match:
        return None

    token = _normalize_number_token(match.group(0))
    if not token:
        return None

    multiplier = 1.0
    tail = value[match.end() : match.end() + 20].lower()
    if "млрд" in tail:
        multiplier = 1_000_000_000.0
    elif "млн" in tail:
        multiplier = 1_000_000.0
    elif "тыс" in tail:
        multiplier = 1_000.0

    try:
        return float(token) * multiplier
    except Exception:
        return None


def parse_percent(raw: str) -> float | None:
    value = _prepare(raw)
    if not value:
        return None

    match = _PERCENT_RE.search(value) or _PERCENT_WORD_RE.search(value)
    if not match:
        return None
    try:
        return float(match.group(1).replace(",", "."))
    except Exception:
        return None


def parse_days(raw: str) -> tuple[int | None, str | None]:
    value = _prepare(raw)
    if not value:
        return None, None

    match = _DAYS_RE.search(value)
    if not match:
        return None, None

    day_type = None
    unit = (match.group(2) or "").lower()
    if "рабоч" in unit:
        day_type = "working"
    elif "календар" in unit:
        day_type = "calendar"

    try:
        return int(match.group(1)), day_type
    except Exception:
        return None, day_type


def parse_date(raw: str) -> date | None:
    value = _prepare(raw)
    if not value:
        return None

    numeric = value.replace("/", ".").replace("-", ".")
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(numeric, fmt).date()
        except Exception:
            continue

    match = _DATE_WORD_RE.search(value)
    if not match:
        return None

    try:
        day = int(match.group(1))
        month = _MONTHS.get(match.group(2).lower())
        year = int(match.group(3))
        if not month:
            return None
        return date(year, month, day)
    except Exception:
        return None


def parse_date_range_days(raw: str) -> int | None:
    value = _prepare(raw)
    if not value:
        return None

    numeric_matches = _DATE_NUM_RE.findall(value)
    parsed_dates: list[date] = []

    if len(numeric_matches) >= 2:
        for item in numeric_matches[:2]:
            parsed = parse_date(item)
            if parsed:
                parsed_dates.append(parsed)
    else:
        for match in _DATE_WORD_RE.finditer(value):
            parsed = parse_date(match.group(0))
            if parsed:
                parsed_dates.append(parsed)
            if len(parsed_dates) >= 2:
                break

    if len(parsed_dates) < 2:
        return None

    delta = (parsed_dates[1] - parsed_dates[0]).days
    if delta <= 0:
        return None
    return delta
