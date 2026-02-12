from fastapi import FastAPI
from models.tender import TenderInput
from models.report import AnalysisReport
from core.extractor import extract_tender_data
from core.risk_engine import calculate_risk
from core.financial_model import calculate_financials

app = FastAPI()

@app.get("/")
def health_check():
    return {"status": "Tenderlitika V2 is alive"}

@app.post("/analyze")
def analyze_tender(data: TenderInput):
    try:
        extracted = extract_tender_data(data.text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extractor failed: {repr(e)}")

    risk_score, risk_level, reasons = calculate_risk(extracted)
    roi, cash_gap = calculate_financials(extracted, data.cost_price, data.planned_margin_percent)

    # Вердикт на базе риска + ROI
    if risk_score >= 7:
        verdict = "Не рекомендуется участвовать"
    elif risk_score >= 4:
        verdict = "Участвовать с осторожностью"
    else:
        verdict = "Можно участвовать"

    return {
        "extracted_data": extracted,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "expected_roi_percent": round(roi, 2),
        "rough_cash_gap": None if cash_gap is None else round(cash_gap, 2),
        "verdict": verdict
    }