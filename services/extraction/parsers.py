from __future__ import annotations

import re
from datetime import date, datetime

from services.extraction.normalize import normalize_text


_DATE_RE = re.compile(r"(\d{1,2}[./-]\d{1,2}[./-]\d{2,4})")


def _prepare(raw: str) -> str:
    return normalize_text(raw or "")


def parse_money(raw: str) -> float | None:
    value = _prepare(raw)
    if not value:
        return None

    value = re.sub(r"(?iu)\b(?:руб(?:\.|ля|лей)?|rur|rub)\b", "", value)
    value = value.replace("₽", "")
    value = re.sub(r"(?iu)\b(?:без\s*ндс|в\s*т\.?\s*ч\.?\s*ндс|ндс)\b", "", value)

    match = re.search(r"[-+]?\d[\d\s\u00A0\u202F.,]*", value)
    if not match:
        return None

    numeric = re.sub(r"\s+", "", match.group(0)).strip(".,")
    if not numeric:
        return None

    if "," in numeric and "." in numeric:
        if numeric.rfind(",") > numeric.rfind("."):
            numeric = numeric.replace(".", "").replace(",", ".")
        else:
            numeric = numeric.replace(",", "")
    elif "," in numeric:
        if re.search(r",\d{1,2}$", numeric):
            numeric = numeric.replace(",", ".")
        else:
            numeric = numeric.replace(",", "")
    elif "." in numeric:
        if not re.search(r"\.\d{1,2}$", numeric):
            numeric = numeric.replace(".", "")

    try:
        return float(numeric)
    except Exception:
        return None


def parse_percent(raw: str) -> float | None:
    value = _prepare(raw)
    if not value:
        return None

    match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*%", value)
    if not match:
        match = re.search(r"(-?\d+(?:[.,]\d+)?)\s*процент\w*", value, flags=re.IGNORECASE)
    if not match:
        return None

    try:
        return float(match.group(1).replace(",", "."))
    except Exception:
        return None


def parse_days(raw: str) -> int | None:
    value = _prepare(raw)
    if not value:
        return None

    match = re.search(
        r"(\d{1,4})\s*(?:рабоч\w*|календарн\w*)?\s*(?:дн\w*|день|дня|дней)",
        value,
        flags=re.IGNORECASE,
    )
    if not match:
        return None
    try:
        return int(match.group(1))
    except Exception:
        return None


def parse_date(raw: str) -> date | None:
    value = _prepare(raw)
    if not value:
        return None
    value = value.replace("/", ".").replace("-", ".")

    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt).date()
        except Exception:
            continue
    return None


def parse_date_range(raw: str) -> int | None:
    value = _prepare(raw)
    if not value:
        return None

    matches = _DATE_RE.findall(value)
    if len(matches) < 2:
        return None

    start = parse_date(matches[0])
    end = parse_date(matches[1])
    if not start or not end:
        return None

    delta = (end - start).days
    if delta <= 0:
        return None
    return delta
