from typing import Any, Dict, List, Tuple



def _fmt_rub(x: float | int | None) -> str:
    if x is None:
        return "—"
    try:
        return f"{int(round(float(x))):,}".replace(",", " ") + " ₽"
    except:
        return "—"

def _pct_amount(nmck: Any, pct: Any) -> float | None:
    if not isinstance(nmck, (int, float)) or not isinstance(pct, (int, float)):
        return None
    return float(nmck) * float(pct) / 100.0

def _is_num(x: Any) -> bool:
    return isinstance(x, (int, float))

def calculate_risk(extracted: Dict[str, Any], quality_gate: Dict[str, Any] | None = None) -> Tuple[int, str, List[str]]:
    """
    Возвращает:
      - risk_score: 0..10
      - risk_level: Низкий/Средний/Высокий
      - reasons: список причин (для объяснимости)
    """
    score = 0
    reasons: List[str] = []
    missing_reasons = (quality_gate or {}).get("missing_reasons") or {}

    nmck = extracted.get("nmck")
    execution_days = extracted.get("execution_days")
    payment_terms_days = extracted.get("payment_terms_days")
    penalty = extracted.get("penalty_percent_per_day")
    advance = extracted.get("advance_percent")
    bid_sec = extracted.get("bid_security_percent")
    contract_sec = extracted.get("contract_security_percent")
    vague_acceptance = extracted.get("has_vague_acceptance_terms")

    # NEW: tender traps
    payment_after_full_delivery = bool(extracted.get("payment_after_full_delivery"))
    delivery_by_customer_requests = bool(extracted.get("delivery_by_customer_requests"))
    supplier_must_hold_stock = bool(extracted.get("supplier_must_hold_stock"))

    # Денежные оценки (если известна НМЦК)
    bid_sec_amount = _pct_amount(nmck, bid_sec)
    contract_sec_amount = _pct_amount(nmck, contract_sec)

    # Простейшая оценка "заморозки оборотки" = обеспечение + отсутствие аванса (если явно 0)
    frozen_estimate = 0.0
    frozen_parts: list[str] = []

    if bid_sec_amount is not None:
        frozen_estimate += bid_sec_amount
        frozen_parts.append(f"обеспечение заявки ~ {_fmt_rub(bid_sec_amount)}")

    if contract_sec_amount is not None:
        frozen_estimate += contract_sec_amount
        frozen_parts.append(f"обеспечение контракта ~ {_fmt_rub(contract_sec_amount)}")

    # Если аванс = 0, а НМЦК есть — это не деньги "замороженные", но усиливает кассовую нагрузку.
    no_advance = (_is_num(advance) and float(advance) == 0.0)

    # 1) Данные не извлечены — уже риск (но не переусердствовать)
    if nmck is None:
        score += 1
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
        payment_reason = missing_reasons.get("payment_terms_days")
        if payment_reason in ("partial_input", "not_provided_in_text", "absent_in_docs"):
            score += 1
            reasons.append("Недостаточно контекста: условия оплаты не обнаружены в текущем наборе документов (возможно в приложениях).")
        elif payment_reason == "parse_failed":
            score += 2
            reasons.append("Раздел оплаты найден, но срок не распознан — требуется проверка.")
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

    # 4) Пеня/штрафы (важно: отсутствие штрафов = не всегда риск)
    if isinstance(penalty, (int, float)):
        if penalty >= 0.2:
            score += 2
            reasons.append(f"Высокая пеня: {penalty}%/день — штрафной риск.")
        elif penalty >= 0.1:
            score += 1
            reasons.append(f"Пеня: {penalty}%/день — заметный штрафной риск.")
    else:
        penalty_reason = missing_reasons.get("penalty_percent_per_day")
        if penalty_reason in ("partial_input", "not_provided_in_text", "absent_in_docs"):
            reasons.append("Недостаточно контекста: условия по пеням/штрафам не обнаружены в текущем наборе документов (возможно в приложениях).")
        elif penalty_reason == "parse_failed":
            score += 1
            reasons.append("Раздел ответственности найден, но пеня/штраф не распознаны — требуется проверка.")
        else:
            reasons.append("Пеня/штрафы не извлечены — проверь вручную (экстрактор мог не распознать формулировку).")

    # 5) Аванс
    if isinstance(advance, (int, float)):
        if advance == 0:
            score += 1
            reasons.append("Аванс отсутствует — увеличивает кассовую нагрузку.")
        elif advance >= 30:
            score -= 1
            reasons.append(f"Высокий аванс: {advance}% — снижает кассовый риск.")
    # если не нашли аванс — нейтрально

    # 6) Обеспечение (грубая эвристика: высокие проценты = заморозка денег/гарантии)
    if isinstance(contract_sec, (int, float)) and contract_sec >= 10:
        score += 1
        msg = f"Высокое обеспечение контракта: {contract_sec}%"
        if contract_sec_amount is not None:
            msg += f" (~{_fmt_rub(contract_sec_amount)})"
        msg += " — нагрузка на финансы/гарантии."
        reasons.append(msg)
    if isinstance(bid_sec, (int, float)) and bid_sec >= 5:
        score += 1
        msg = f"Высокое обеспечение заявки: {bid_sec}%"
        if bid_sec_amount is not None:
            msg += f" (~{_fmt_rub(bid_sec_amount)})"
        msg += " — финансовая нагрузка."
        reasons.append(msg)

    # 7) Размытая приемка
    if vague_acceptance is True:
        score += 2
        reasons.append("Есть признаки размытых условий приемки/оснований отказа — риск конфликтов и задержек оплаты.")

    # 8) NEW: тендер-ловушки (ключевая ценность продукта)
    if payment_after_full_delivery:
        score += 2
        reasons.append("Оплата только после полной поставки — риск длительного кассового разрыва и зависания оборотки.")

    if delivery_by_customer_requests:
        score += 2
        reasons.append("Поставка партиями/по заявкам заказчика — риск растягивания сроков и заморозки товара/денег.")

    if supplier_must_hold_stock:
        score += 1
        reasons.append("Требование держать товар на складе поставщика — заморозка оборотных средств и риск срыва сроков.")

    # 9) NEW: синергия ловушки (самый “капканный” сценарий)
    # Оплата после полной поставки + поставка по заявкам = деньги могут прийти очень нескоро
    if payment_after_full_delivery and delivery_by_customer_requests:
        score += 1
        reasons.append("Комбо-капкан: оплата после полной поставки + поставка по заявкам — высокий риск долгой заморозки оборотки.")

    # Итоговое денежное пояснение (если есть что сказать)
    if frozen_parts:
        msg = "Оценка заморозки оборотных средств: " + "; ".join(frozen_parts) + "."
        if no_advance:
            msg += " Аванса нет — потребуется больше оборотки."
        if payment_after_full_delivery or delivery_by_customer_requests:
            msg += " Условия оплаты/поставки могут дополнительно растянуть возврат денег."
        reasons.append(msg)

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
