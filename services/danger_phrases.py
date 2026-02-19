import re
from typing import List, Dict, Any

def find_danger_phrases(text: str) -> List[Dict[str, Any]]:
    """
    MVP детектор опасных формулировок.
    Возвращает список находок для UI/JSON.
    """
    if not text:
        return []

    rules = [
        # pattern, severity, title, hint
        (r"\bпо\s+заявк(ам|е)\b", "high", "Поставка по заявкам", "Объём/график может быть неопределённым → риск заморозки оборотки."),
        (r"\bобъем\s+не\s+фиксирован\b|\bбез\s+фиксированн(ого|ого)\s+объема\b", "high", "Объём не фиксирован", "Риск непредсказуемых поставок и затрат."),
        (r"\bоплат[аы]\s+после\s+полной\s+поставк(и|и)\b", "high", "Оплата после полной поставки", "Кассовый разрыв: финансируешь поставку целиком."),
        (r"\bбез\s+аванса\b|\bаванс\s+не\s+предусмотрен\b|\bпредоплат[аы]\s+не\s+предусмотрен", "medium", "Нет аванса", "Повышенная потребность в оборотных средствах."),
        (r"\bсрок\s+оплат[ыа]\s+до\s+(\d{2,3})\s+(банковских|рабочих)\s+дн", "medium", "Длинный срок оплаты", "Длинная отсрочка оплаты увеличивает финансовую нагрузку."),
        (r"\bнеустойк[аи]\s+в\s+размере\s+(\d+([.,]\d+)?)\s*%\s*(в\s+день|за\s+день)", "high", "Высокая неустойка", "Штрафы могут съесть маржу."),
        (r"\bобеспечени[ея]\s+исполнени[яе]\s+контракт[аы]\s+в\s+размере\s+(\d+([.,]\d+)?)\s*%", "medium", "Высокое обеспечение контракта", "Заморозка средств/стоимость гарантии."),
    ]

    findings: List[Dict[str, Any]] = []

    for pattern, severity, title, hint in rules:
        for m in re.finditer(pattern, text, flags=re.IGNORECASE | re.MULTILINE):
            start, end = m.span()
            snippet_start = max(0, start - 80)
            snippet_end = min(len(text), end + 120)
            snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()

            findings.append({
                "id": f"dp_{len(findings)+1}",
                "severity": severity,
                "title": title,
                "hint": hint,
                "matches": [{"snippet": snippet, "start": start, "end": end}],
            })

    # Дедуп по title, склеим matches
    merged: Dict[str, Dict[str, Any]] = {}
    for f in findings:
        key = f["title"]
        if key not in merged:
            merged[key] = f
        else:
            merged[key]["matches"].extend(f["matches"])

    return list(merged.values())