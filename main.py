from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from models.tender import TenderInput
from core.extractor import extract_tender_data
from core.risk_engine import calculate_risk
from core.financial_model import calculate_financials, calculate_safe_cost_price

from services.pdf_text import extract_text_from_pdf_bytes
from services.analysis_store import save_analysis
from services.current_user import get_current_user
from services.limits import check_monthly_quota
from services.danger_phrases import find_danger_phrases  # ✅ правильный импорт

from db.deps import get_db
from db.models import Analysis, User

from api.auth_routes import router as auth_router


app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)


@app.get("/")
def health_check():
    return {"status": "Tenderlitika V2 is alive"}


@app.post("/analyze")
def analyze_tender(
    data: TenderInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)

    extracted = extract_tender_data(data.text)

    # ✅ danger phrases
    danger = find_danger_phrases(data.text)
    extracted["danger_phrases"] = danger

    risk_score, risk_level, reasons = calculate_risk(extracted)

    roi, cash_gap = calculate_financials(
        extracted,
        data.cost_price,
        data.planned_margin_percent,
    )

    safe_cost = calculate_safe_cost_price(extracted)

    if risk_score >= 7:
        verdict = "Не рекомендуется участвовать"
    elif risk_score >= 4:
        verdict = "Участвовать с осторожностью"
    else:
        verdict = "Можно участвовать"

    row = save_analysis(
        db=db,
        user_id=user.id,
        source_type="text",
        source_name=None,
        extracted_data=extracted,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_reasons=reasons,
        expected_roi_percent=round(roi, 2),
        rough_cash_gap=None if cash_gap is None else round(cash_gap, 2),
        verdict=verdict,
        input_cost_price=float(data.cost_price) if data.cost_price is not None else None,
        input_margin_percent=float(data.planned_margin_percent) if data.planned_margin_percent is not None else None,
        safe_cost_price=None if safe_cost is None else float(safe_cost),
    )

    return {
        "analysis_id": row.id,
        "extracted_data": extracted,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "expected_roi_percent": round(roi, 2),
        "rough_cash_gap": None if cash_gap is None else round(cash_gap, 2),
        "safe_cost_price": None if safe_cost is None else float(safe_cost),  # ✅ единый ключ
        "verdict": verdict,
    }


@app.post("/analyze/pdf")
async def analyze_tender_pdf(
    file: UploadFile = File(...),
    cost_price: float = Form(...),
    planned_margin_percent: float = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)

    # 1) Проверка файла
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Please upload a PDF file")

    # 2) Читаем PDF в память
    pdf_bytes = await file.read()
    if not pdf_bytes:
        raise HTTPException(status_code=400, detail="Empty file")

    # 3) Извлекаем текст из PDF
    try:
        text = extract_text_from_pdf_bytes(pdf_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"PDF text extraction failed: {repr(e)}")

    # 4) Если текста почти нет — это скан/картинки/защита (нужен OCR)
    if not text or len(text) < 100:
        raise HTTPException(
            status_code=422,
            detail="Не удалось извлечь текст из PDF. Похоже на скан (нужен OCR) или защищённый PDF."
        )

    # 5) Pipeline
    try:
        extracted = extract_tender_data(text)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extractor failed: {repr(e)}")

    danger = find_danger_phrases(text)
    extracted["danger_phrases"] = danger

    risk_score, risk_level, reasons = calculate_risk(extracted)
    roi, cash_gap = calculate_financials(extracted, cost_price, planned_margin_percent)

    safe_cost = calculate_safe_cost_price(extracted)

    if risk_score >= 7:
        verdict = "Не рекомендуется участвовать"
    elif risk_score >= 4:
        verdict = "Участвовать с осторожностью"
    else:
        verdict = "Можно участвовать"

    # 6) Сохраняем в БД
    row = save_analysis(
        db=db,
        user_id=user.id,
        source_type="pdf",
        source_name=file.filename,
        extracted_data=extracted,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_reasons=reasons,
        expected_roi_percent=round(roi, 2),
        rough_cash_gap=None if cash_gap is None else round(cash_gap, 2),
        verdict=verdict,
        input_cost_price=float(cost_price),
        input_margin_percent=float(planned_margin_percent),
        safe_cost_price=None if safe_cost is None else float(safe_cost),
    )

    # 7) Ответ
    return {
        "analysis_id": row.id,
        "source": {
            "type": "pdf",
            "filename": file.filename,
            "text_chars": len(text),
        },
        "extracted_data": extracted,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "expected_roi_percent": round(roi, 2),
        "rough_cash_gap": None if cash_gap is None else round(cash_gap, 2),
        "safe_cost_price": None if safe_cost is None else float(safe_cost),
        "verdict": verdict,
    }


@app.get("/analyses")
def list_analyses(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
    limit: int = 20,
):
    safe_limit = max(1, min(limit, 100))
    rows = (
        db.query(Analysis)
        .filter(Analysis.user_id == user.id)
        .order_by(Analysis.id.desc())
        .limit(safe_limit)
        .all()
    )
    return [
        {
            "id": r.id,
            "source_type": r.source_type,
            "source_name": r.source_name,
            "risk_score": r.risk_score,
            "risk_level": r.risk_level,
            "expected_roi_percent": r.expected_roi_percent,
            "rough_cash_gap": r.rough_cash_gap,
            "verdict": r.verdict,
            "input_cost_price": r.input_cost_price,
            "input_margin_percent": r.input_margin_percent,
            "safe_cost_price": r.safe_cost_price,
            "created_at": r.created_at,
        }
        for r in rows
    ]


@app.get("/analyses/{analysis_id}")
def get_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    r = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.user_id == user.id)
        .first()
    )
    if not r:
        raise HTTPException(status_code=404, detail="Not found")

    return {
        "id": r.id,
        "source_type": r.source_type,
        "source_name": r.source_name,
        "extracted_data": r.extracted_data,
        "risk_score": r.risk_score,
        "risk_level": r.risk_level,
        "risk_reasons": r.risk_reasons,
        "expected_roi_percent": r.expected_roi_percent,
        "rough_cash_gap": r.rough_cash_gap,
        "verdict": r.verdict,
        "input_cost_price": r.input_cost_price,
        "input_margin_percent": r.input_margin_percent,
        "safe_cost_price": r.safe_cost_price,
        "created_at": r.created_at,
    }
