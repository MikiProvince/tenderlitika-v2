from typing import Any, Dict, List, Tuple

def calculate_risk(extracted: Dict[str, Any]) -> Tuple[int, str, List[str]]:
    """
    Возвращает:
      - risk_score: 0..10
      - risk_level: Низкий/Средний/Высокий
      - reasons: список причин (для объяснимости)
    """
    score = 0
    reasons: List[str] = []

    nmck = extracted.get("nmck")
    execution_days = extracted.get("execution_days")
    payment_terms_days = extracted.get("payment_terms_days")
    penalty = extracted.get("penalty_percent_per_day")
    advance = extracted.get("advance_percent")
    bid_sec = extracted.get("bid_security_percent")
    contract_sec = extracted.get("contract_security_percent")
    vague_acceptance = extracted.get("has_vague_acceptance_terms")

    # 1) Данные не извлечены — уже риск
    if nmck is None:
        score += 2
        reasons.append("Не удалось извлечь НМЦК — возможна неполнота данных/нестандартный документ.")

    # 2) Оплата: длинная = кассовый разрыв
    if isinstance(payment_terms_days, (int, float)):
        if payment_terms_days >= 60:
            score += 2
            reasons.append(f"Долгий срок оплаты: {int(payment_terms_days)} дней — высокий риск кассового разрыва.")
        elif payment_terms_days >= 30:
            score += 1
            reasons.append(f"Срок оплаты: {int(payment_terms_days)} дней — возможен кассовый разрыв.")
    else:
        score += 1
        reasons.append("Не найден срок оплаты — риск неопределенности по кэшу.")

    # 3) Срок исполнения: короткий при большой сумме — риск сорвать
    if isinstance(execution_days, (int, float)) and isinstance(nmck, (int, float)):
        if execution_days <= 30 and nmck >= 10_000_000:
            score += 2
            reasons.append(f"Короткий срок исполнения ({int(execution_days)} дней) при НМЦК ≥ 10 млн — риск срыва сроков.")
        elif execution_days <= 20:
            score += 1
            reasons.append(f"Очень короткий срок исполнения: {int(execution_days)} дней.")
    else:
        score += 1
        reasons.append("Не найден срок исполнения — риск неверной оценки нагрузки.")

    # 4) Пеня/штрафы
    if isinstance(penalty, (int, float)):
        if penalty >= 0.2:
            score += 2
            reasons.append(f"Высокая пеня: {penalty}%/день — штрафной риск.")
        elif penalty >= 0.1:
            score += 1
            reasons.append(f"Пеня: {penalty}%/день — заметный штрафной риск.")
    else:
        score += 1
        reasons.append("Не найдена пеня/штрафы — риск сюрпризов в санкциях.")

    # 5) Аванс
    if isinstance(advance, (int, float)):
        if advance == 0:
            score += 1
            reasons.append("Аванс отсутствует — увеличивает кассовую нагрузку.")
        elif advance >= 30:
            score -= 1
            reasons.append(f"Высокий аванс: {advance}% — снижает кассовый риск.")
    # если не нашли аванс — нейтрально, часто его реально нет/не указан

    # 6) Обеспечение
    # грубая эвристика: высокие проценты = заморозка денег/гарантии
    if isinstance(contract_sec, (int, float)) and contract_sec >= 10:
        score += 1
        reasons.append(f"Высокое обеспечение контракта: {contract_sec}% — нагрузка на финансы/гарантии.")
    if isinstance(bid_sec, (int, float)) and bid_sec >= 5:
        score += 1
        reasons.append(f"Высокое обеспечение заявки: {bid_sec}% — финансовая нагрузка.")

    # 7) Размытая приемка
    if vague_acceptance is True:
        score += 2
        reasons.append("Есть признаки размытых условий приемки/оснований отказа — риск конфликтов и задержек оплаты.")

    # нормализация
    if score < 0:
        score = 0
    if score > 10:
        score = 10

    if score <= 3:
        level = "Низкий"
    elif score <= 6:
        level = "Средний"
    else:
        level = "Высокий"

    return score, level, reasons
