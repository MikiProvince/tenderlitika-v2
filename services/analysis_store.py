from sqlalchemy.orm import Session
from db.models import Analysis

def save_analysis(
    db: Session,
    user_id: int,
    source_type: str,
    source_name: str | None,
    extracted_data: dict,
    risk_score: int,
    risk_level: str,
    risk_reasons: list[str],
    expected_roi_percent: float,
    rough_cash_gap: float | None,
    verdict: str,
    # ✅ NEW
    input_cost_price: float | None = None,
    input_margin_percent: float | None = None,
    safe_cost_price: float | None = None,
) -> Analysis:
    row = Analysis(
        user_id=user_id,
        source_type=source_type,
        source_name=source_name,
        extracted_data=extracted_data,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_reasons=risk_reasons,
        expected_roi_percent=expected_roi_percent,
        rough_cash_gap=rough_cash_gap,
        verdict=verdict,
        # ✅ NEW
        input_cost_price=input_cost_price,
        input_margin_percent=input_margin_percent,
        safe_cost_price=safe_cost_price,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row
