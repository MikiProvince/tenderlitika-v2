from typing import Optional, Tuple


def calculate_financials(
    *,
    nmck: float,
    cost_price: float,
    margin_percent: float,
    payment_terms_days: float | int | None = None,
    execution_days: float | int | None = None,
) -> Tuple[float, Optional[float]]:
    """
    Stateless financial calculation based only on explicit parameters.
    """
    if not isinstance(nmck, (int, float)) or float(nmck) <= 0:
        return 0.0, None

    if not isinstance(cost_price, (int, float)) or float(cost_price) <= 0:
        return 0.0, None

    if not isinstance(margin_percent, (int, float)):
        margin_percent = 0.0

    expected_profit = float(cost_price) * (float(margin_percent) / 100.0)
    expected_roi = (expected_profit / float(cost_price)) * 100.0

    cash_gap = None
    if (
        isinstance(payment_terms_days, (int, float))
        and isinstance(execution_days, (int, float))
        and float(execution_days) > 0
        and float(payment_terms_days) >= 0
    ):
        daily_burn = float(cost_price) / float(execution_days)
        cash_gap = daily_burn * float(payment_terms_days)

    return float(expected_roi), cash_gap


def calculate_safe_cost_price(*, nmck: float, roi_percent: float) -> float | None:
    """
    Deterministic safe cost formula:
      safe_cost = nmck / (1 + roi_percent / 100)
    """
    if not isinstance(nmck, (int, float)) or float(nmck) <= 0:
        return None
    if not isinstance(roi_percent, (int, float)):
        return None

    denominator = 1.0 + (float(roi_percent) / 100.0)
    if denominator <= 0:
        return None
    return round(float(nmck) / denominator, 2)
