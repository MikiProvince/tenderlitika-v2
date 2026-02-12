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
    extracted = extract_tender_data(data.text)

    nmck = extracted.get("nmck")

    risk_score, risk_level = calculate_risk(nmck)

    roi = calculate_financials(
        nmck,
        data.cost_price,
        data.planned_margin_percent
    )

    if risk_score >= 5:
        verdict = "Не рекомендуется участвовать"
    elif risk_score >= 3:
        verdict = "Участвовать с осторожностью"
    else:
        verdict = "Можно участвовать"

    return {
        "extracted_data": extracted,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "expected_roi_percent": roi,
        "verdict": verdict
    }