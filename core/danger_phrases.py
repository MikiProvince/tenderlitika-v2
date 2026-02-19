import re
from typing import Any, Dict, List

RULES = [
    # Приемка/отказ/усмотрение
    {
        "id": "acceptance_discretion",
        "severity": "high",
        "title": "Приемка/отказ по усмотрению заказчика",
        "patterns": [
            r"по\s+усмотрению\s+заказчика",
            r"на\s+усмотрение\s+заказчика",
            r"в\s+случае\s+неудовлетворительного\s+качества\s+по\s+мнению\s+заказчика",
            r"заказчик\s+вправе\s+отказать\s+в\s+приемк[еии]",
        ],
        "hint": "Риск затяжной приемки и задержки оплаты из-за субъективных критериев.",
    },
    # Оплата/финансирование
    {
        "id": "payment_financing",
        "severity": "high",
        "title": "Оплата при наличии финансирования",
        "patterns": [
            r"при\s+наличии\s+финансирования",
            r"по\s+мере\s+поступления\s+денежных\s+средств",
            r"в\s+пределах\s+доведенных\s+лимитов",
        ],
        "hint": "Риск неопределенности сроков оплаты — деньги могут прийти сильно позже.",
    },
    # Односторонние изменения
    {
        "id": "unilateral_change",
        "severity": "high",
        "title": "Одностороннее изменение условий",
        "patterns": [
            r"заказчик\s+вправе\s+изменить\s+объем",
            r"заказчик\s+вправе\s+изменить\s+срок",
            r"в\s+одностороннем\s+порядке",
            r"по\s+решению\s+заказчика\s+изменяется",
        ],
        "hint": "Риск расширения обязательств/сроков без адекватной компенсации.",
    },
    # Заявки/партии/неопределенность объема
    {
        "id": "requests_volume",
        "severity": "medium",
        "title": "Поставка по заявкам / неопределенный объем",
        "patterns": [
            r"по\s+заявк(ам|е)\s+заказчика",
            r"по\s+мере\s+необходимости",
            r"поставка\s+партиями",
            r"количество\s+может\s+быть\s+изменено",
        ],
        "hint": "Риск растягивания поставки и заморозки оборотки/склада.",
    },
    # Штрафы “жесткие”
    {
        "id": "hard_penalties",
        "severity": "medium",
        "title": "Жесткие штрафы/пени",
        "patterns": [
            r"пеня\s+в\s+размере\s+\d+(?:[.,]\d+)?\s*%\/день",
            r"штраф\s+в\s+размере\s+\d+(?:[.,]\d+)?\s*%\/день",
            r"0[.,]3\s*%\/день|0[.,]4\s*%\/день|0[.,]5\s*%\/день",
        ],
        "hint": "Риск быстрых потерь при просрочке и спорных приемках.",
    },
]

def find_danger_phrases(text: str, max_hits_per_rule: int = 3) -> List[Dict[str, Any]]:
    """
    Возвращает список найденных триггеров:
    [
      {id, severity, title, hint, matches:[{snippet, start, end}]}
    ]
    """
    t = text or ""
    hits: List[Dict[str, Any]] = []

    for rule in RULES:
        matches = []
        for p in rule["patterns"]:
            for m in re.finditer(p, t, flags=re.IGNORECASE | re.MULTILINE):
                start, end = m.start(), m.end()
                # короткий сниппет вокруг совпадения
                left = max(0, start - 60)
                right = min(len(t), end + 60)
                snippet = t[left:right].replace("\n", " ").strip()
                matches.append({"snippet": snippet, "start": start, "end": end})
                if len(matches) >= max_hits_per_rule:
                    break
            if len(matches) >= max_hits_per_rule:
                break

        if matches:
            hits.append({
                "id": rule["id"],
                "severity": rule["severity"],
                "title": rule["title"],
                "hint": rule["hint"],
                "matches": matches,
            })

    return hits
