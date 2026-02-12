def calculate_risk(nmck: float | None) -> tuple[int, str]:
    risk = 0

    if nmck is None:
        risk += 3
    elif nmck > 10_000_000:
        risk += 2

    if risk <= 2:
        level = "Низкий"
    elif risk <= 4:
        level = "Средний"
    else:
        level = "Высокий"

    return risk, level
