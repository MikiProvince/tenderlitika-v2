from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from models.tender import TenderInput
from core.extractor import extract_tender_data
from core.risk_engine import calculate_risk
from core.financial_model import calculate_financials, calculate_safe_cost_price

from services.pdf_text import extract_text_from_pdf_bytes
from services.document_text import extract_text_from_document
from services.analysis_store import save_analysis
from services.current_user import get_current_user
from services.limits import check_monthly_quota
from services.danger_phrases import find_danger_phrases  # правильный импорт

from db.deps import get_db
from db.models import Analysis, User

from api.auth_routes import router as auth_router

from typing import List
from services.batch_text import extract_docs_from_uploads, build_structured_corpus


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


def _run_analysis_pipeline(
    *,
    text: str,
    db: Session,
    user: User,
    cost_price: float,
    planned_margin_percent: float,
    source_type: str,
    source_name: str | None,
    llm_provider: str | None,
):
    try:
        extracted = extract_tender_data(text, llm_provider)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Extractor failed: {repr(e)}")

    danger = find_danger_phrases(text)
    extracted["danger_phrases"] = danger

    risk_score, risk_level, reasons = calculate_risk(extracted)

    roi, cash_gap = calculate_financials(
        extracted,
        cost_price,
        planned_margin_percent,
    )

    safe_cost = calculate_safe_cost_price(extracted)

    if risk_score >= 7:
        verdict = "\u041d\u0435 \u0440\u0435\u043a\u043e\u043c\u0435\u043d\u0434\u0443\u0435\u0442\u0441\u044f \u0443\u0447\u0430\u0441\u0442\u0432\u043e\u0432\u0430\u0442\u044c"
    elif risk_score >= 4:
        verdict = "\u0423\u0447\u0430\u0441\u0442\u0432\u043e\u0432\u0430\u0442\u044c \u0441 \u043e\u0441\u0442\u043e\u0440\u043e\u0436\u043d\u043e\u0441\u0442\u044c\u044e"
    else:
        verdict = "\u041c\u043e\u0436\u043d\u043e \u0443\u0447\u0430\u0441\u0442\u0432\u043e\u0432\u0430\u0442\u044c"

    row = save_analysis(
        db=db,
        user_id=user.id,
        source_type=source_type,
        source_name=source_name,
        extracted_data=extracted,
        risk_score=risk_score,
        risk_level=risk_level,
        risk_reasons=reasons,
        expected_roi_percent=round(roi, 2),
        rough_cash_gap=None if cash_gap is None else round(cash_gap, 2),
        verdict=verdict,
        input_cost_price=float(cost_price) if cost_price is not None else None,
        input_margin_percent=float(planned_margin_percent) if planned_margin_percent is not None else None,
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
        "safe_cost_price": None if safe_cost is None else float(safe_cost),
        "verdict": verdict,
    }


@app.get("/")
def health_check():
    return {"status": "Tenderlitika V2 is alive"}

@app.post("/analyze/batch")
async def analyze_tender_batch(
    files: List[UploadFile] = File(...),
    cost_price: float = Form(..., gt=0),
    planned_margin_percent: float = Form(..., ge=0, le=100),
    llm_provider: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)

    docs = await extract_docs_from_uploads(files)
    corpus = build_structured_corpus(docs)

    result = _run_analysis_pipeline(
        text=corpus,
        db=db,
        user=user,
        cost_price=cost_price,
        planned_margin_percent=planned_margin_percent,
        source_type="batch",
        source_name=f"Пакет документов ({len(docs)})",
        llm_provider=llm_provider,
    )
    result["source"] = {
        "type": "batch",
        "file_count": len(docs),
        "filenames": [d.filename for d in docs],
        "text_chars": len(corpus),
    }
    return result

@app.post("/analyze")
def analyze_tender(
    data: TenderInput,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)
    return _run_analysis_pipeline(
        text=data.text,
        db=db,
        user=user,
        cost_price=data.cost_price,
        planned_margin_percent=data.planned_margin_percent,
        source_type="text",
        source_name=None,
        llm_provider=data.llm_provider,
    )


@app.post("/analyze/pdf")
async def analyze_tender_pdf(
    file: UploadFile = File(...),
    cost_price: float = Form(..., gt=0),
    planned_margin_percent: float = Form(..., ge=0, le=100),
    llm_provider: str | None = Form(None),
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
            detail="Не удалось извлечь текст из PDF. Похоже на скан (нужен OCR) или защищенный PDF."
        )

    result = _run_analysis_pipeline(
        text=text,
        db=db,
        user=user,
        cost_price=cost_price,
        planned_margin_percent=planned_margin_percent,
        source_type="pdf",
        source_name=file.filename,
        llm_provider=llm_provider,
    )
    result["source"] = {
        "type": "pdf",
        "filename": file.filename,
        "text_chars": len(text),
    }
    return result


@app.post("/analyze/document")
async def analyze_tender_document(
    file: UploadFile = File(...),
    cost_price: float = Form(..., gt=0),
    planned_margin_percent: float = Form(..., ge=0, le=100),
    llm_provider: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)

    if not file.filename:
        raise HTTPException(status_code=400, detail="Please upload a PDF, DOC or DOCX file")

    payload = await file.read()
    if not payload:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        text, detected_type = extract_text_from_document(file.filename, payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Document text extraction failed: {repr(exc)}")

    if not text or len(text) < 100:
        raise HTTPException(
            status_code=422,
            detail="\u041d\u0435 \u0443\u0434\u0430\u043b\u043e\u0441\u044c \u0438\u0437\u0432\u043b\u0435\u0447\u044c \u0442\u0435\u043a\u0441\u0442 \u0438\u0437 \u0434\u043e\u043a\u0443\u043c\u0435\u043d\u0442\u0430. \u041f\u043e\u043f\u0440\u043e\u0431\u0443\u0439\u0442\u0435 \u0434\u0440\u0443\u0433\u043e\u0439 \u0444\u0430\u0439\u043b \u0438\u043b\u0438 \u0432\u0441\u0442\u0430\u0432\u044c\u0442\u0435 \u0442\u0435\u043a\u0441\u0442 \u0432\u0440\u0443\u0447\u043d\u0443\u044e.",
        )

    result = _run_analysis_pipeline(
        text=text,
        db=db,
        user=user,
        cost_price=cost_price,
        planned_margin_percent=planned_margin_percent,
        source_type=detected_type,
        source_name=file.filename,
        llm_provider=llm_provider,
    )
    result["source"] = {
        "type": detected_type,
        "filename": file.filename,
        "text_chars": len(text),
    }
    return result


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


@app.delete("/analyses/{analysis_id}")
def delete_analysis(
    analysis_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    row = (
        db.query(Analysis)
        .filter(Analysis.id == analysis_id, Analysis.user_id == user.id)
        .first()
    )
    if not row:
        raise HTTPException(status_code=404, detail="Not found")

    db.delete(row)
    db.commit()
    return {"ok": True}


@app.delete("/analyses")
def clear_analyses(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = db.query(Analysis).filter(Analysis.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    return {"ok": True, "deleted_count": deleted}
