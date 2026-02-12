def calculate_financials(nmck: float | None, cost_price: float, margin_percent: float):
    if nmck is None:
        return 0

    expected_profit = cost_price * (margin_percent / 100)
    roi = (expected_profit / cost_price) * 100

    return roi
