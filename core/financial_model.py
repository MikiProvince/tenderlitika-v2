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
