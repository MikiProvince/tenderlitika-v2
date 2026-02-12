from fastapi import FastAPI
from models.tender import TenderInput
from models.report import AnalysisReport
from core.extractor import extract_tender_data
from core.risk_engine import calculate_risk
from core.financial_model import calculate_financials
from fastapi import UploadFile, File, HTTPException, Form
from services.pdf_text import extract_text_from_pdf_bytes

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

@app.post("/analyze/pdf")
async def analyze_tender_pdf(
    file: UploadFile = File(...),
    cost_price: float = Form(...),
    planned_margin_percent: float = Form(...),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")

    pdf_bytes = await file.read()

    try:
        text = extract_text_from_pdf_bytes(pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF text extraction failed: {repr(e)}")

    if not text or len(text) < 100:
        # Это почти всегда означает: PDF — скан/картинки, либо защищённый/пустой текстовый слой
        raise HTTPException(
            status_code=422,
            detail="Не удалось извлечь текст из PDF. Похоже на скан (нужно OCR) или защищённый PDF."
        )

    # дальше — тот же pipeline, что и в /analyze (текстовый)
    try:
        extracted = extract_tender_data(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extractor failed: {repr(e)}")

    risk_score, risk_level, reasons = calculate_risk(extracted)
    roi, cash_gap = calculate_financials(extracted, cost_price, planned_margin_percent)

    if risk_score >= 7:
        verdict = "Не рекомендуется участвовать"
    elif risk_score >= 4:
        verdict = "Участвовать с осторожностью"
    else:
        verdict = "Можно участвовать"

    return {
        "source": {
            "filename": file.filename,
            "text_chars": len(text),
        },
        "extracted_data": extracted,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "expected_roi_percent": round(roi, 2),
        "rough_cash_gap": None if cash_gap is None else round(cash_gap, 2),
        "verdict": verdict,
    }

    