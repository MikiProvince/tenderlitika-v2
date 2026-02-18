from typing import Any, Dict, Optional, Tuple

def calculate_financials(extracted: Dict[str, Any], cost_price: float, margin_percent: float) -> Tuple[float, Optional[float]]:
    """
    Возвращает:
      - expected_roi_percent
      - rough_cash_gap (грубая оценка кассового разрыва), если хватает данных
    """
    # ROI: ожидаемая прибыль / себестоимость
    expected_profit = cost_price * (margin_percent / 100.0)
    expected_roi = (expected_profit / cost_price) * 100.0 if cost_price > 0 else 0.0

    # Cash gap (очень грубо): сколько денег "висит" до оплаты
    payment_terms_days = extracted.get("payment_terms_days")
    execution_days = extracted.get("execution_days")

    cash_gap = None
    if isinstance(payment_terms_days, (int, float)) and isinstance(execution_days, (int, float)) and execution_days > 0:
        # считаем, что расходы равномерно в течение исполнения
        daily_burn = cost_price / float(execution_days)
        cash_gap = daily_burn * float(payment_terms_days)

    return expected_roi, cash_gap

def calculate_safe_cost_price(extracted: dict) -> float | None:

    nmck = extracted.get("nmck")
    if not isinstance(nmck, (int, float)):
        return None

    contract_sec = extracted.get("contract_security_percent") or 0

    # базовая безопасная маржа
    safety_margin = 0.10

    # нагрузка гарантий (не 1:1, потому что это не полная потеря денег)
    guarantee_load = (contract_sec / 100) * 0.5

    # ловушки
    trap_penalty = 0.0

    if extracted.get("payment_after_full_delivery"):
        trap_penalty += 0.05

    if extracted.get("delivery_by_customer_requests"):
        trap_penalty += 0.05

    if extracted.get("supplier_must_hold_stock"):
        trap_penalty += 0.03

    if extracted.get("has_vague_acceptance_terms"):
        trap_penalty += 0.04

    total_risk_buffer = safety_margin + guarantee_load + trap_penalty

    safe_cost = nmck * (1 - total_risk_buffer)

    return round(safe_cost, 2)
