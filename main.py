import logging
import os
import time
import uuid

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.orm import Session

from models.tender import TenderInput
from core.extractor import extract_tender_data, consolidate_extraction
from core.risk_engine import calculate_risk
from core.financial_model import calculate_financials, calculate_safe_cost_price
from core.logging_config import setup_logging, bind_request_id, reset_request_id

from services.pdf_text import extract_text_from_pdf_bytes
from services.document_text import extract_text_from_document
from services.extraction.corpus_awareness import build_quality_gate
from services.extraction_v3.pipeline import run_pipeline as run_pipeline_v3
from services.evi_extractor.pipeline import run_evi_extractor
from services.analysis_store import save_analysis
from services.current_user import get_current_user
from services.limits import check_monthly_quota
from services.danger_phrases import find_danger_phrases  # правильный импорт

from db.deps import get_db
from db.models import Analysis, User

from api.auth_routes import router as auth_router

from typing import List
from services.batch_text import extract_docs_from_uploads, build_structured_corpus


setup_logging()
logger = logging.getLogger(__name__)

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


@app.middleware("http")
async def log_requests(request: Request, call_next):
    request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
    token = bind_request_id(request_id)
    start = time.perf_counter()
    try:
        response = await call_next(request)
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.info(
            "request.complete",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
                "duration_ms": duration_ms,
            },
        )
        response.headers["X-Request-ID"] = request_id
        return response
    except Exception:
        duration_ms = int((time.perf_counter() - start) * 1000)
        logger.exception(
            "request.error",
            extra={
                "method": request.method,
                "path": request.url.path,
                "status_code": 500,
                "duration_ms": duration_ms,
            },
        )
        raise
    finally:
        reset_request_id(token)


def quality_gate(extracted_data: dict, corpus_text: str, input_mode: str) -> dict:
    return build_quality_gate(extracted_data, corpus_text, input_mode)


def can_compute_financials(extracted_data: dict) -> tuple[bool, list[str]]:
    meta = extracted_data.get("meta") or {}
    corpus = meta.get("corpus") or {}
    evi_meta = meta.get("evi_extractor") or {}
    nmck = extracted_data.get("nmck")

    nmck_is_valid = (
        nmck is not None
        and isinstance(nmck, (int, float))
        and float(nmck) > 0
    )

    reasons: list[str] = []
    if nmck is None or (isinstance(nmck, (int, float)) and float(nmck) <= 0) or not isinstance(nmck, (int, float)):
        reasons.append("nmck_missing")

    # Partial corpus should downgrade confidence/verdict, but not block deterministic financial math.
    if bool(corpus.get("is_partial", False)):
        reasons.append("partial_input")
    if bool(evi_meta.get("is_partial_for_price")):
        reasons.append("partial_price_context")

    if bool(evi_meta.get("is_partial_for_price")):
        return False, reasons
    return nmck_is_valid, reasons


def _calculate_financials_compat(
    extracted: dict,
    nmck_value: float,
    cost_price: float,
    planned_margin_percent: float,
) -> tuple[float | None, float | None]:
    try:
        return calculate_financials(
            nmck=float(nmck_value),
            cost_price=float(cost_price),
            margin_percent=float(planned_margin_percent),
            payment_terms_days=extracted.get("payment_terms_days"),
            execution_days=extracted.get("execution_days"),
        )
    except TypeError:
        # Backward compatibility with legacy signature: calculate_financials(extracted, cost, margin)
        return calculate_financials(extracted, float(cost_price), float(planned_margin_percent))


def _calculate_safe_cost_compat(extracted: dict, nmck_value: float, roi_percent: float) -> float | None:
    try:
        return calculate_safe_cost_price(
            nmck=float(nmck_value),
            roi_percent=float(roi_percent),
        )
    except TypeError:
        # Backward compatibility with legacy signature: calculate_safe_cost_price(extracted)
        return calculate_safe_cost_price(extracted)


def _new_pipeline_enabled() -> bool:
    return os.getenv("NEW_PIPELINE", "false").lower() == "true"


def _evi_extractor_enabled() -> bool:
    return os.getenv("EVI_EXTRACTOR", "false").lower() == "true"



def _run_analysis_pipeline(
    *,
    text: str,
    db: Session,
    user: User,
    cost_price: float,
    planned_margin_percent: float,
    source_type: str,
    source_name: str | None,
    input_mode: str,
    llm_provider: str | None,
    files_text: list[tuple[str, str]] | None = None,
    manual_text: str | None = None,
    ingestion_meta: dict | None = None,
):
    logger.info(
        "analysis.start",
        extra={
            "user_id": user.id,
            "source_type": source_type,
            "source_name": source_name or "-",
            "text_chars": len(text),
            "llm_provider": llm_provider or "auto",
        },
    )
    use_evi_extractor = _evi_extractor_enabled()
    use_new_pipeline = _new_pipeline_enabled() and not use_evi_extractor
    try:
        if use_evi_extractor:
            extracted = run_evi_extractor(
                files_text=files_text or [],
                manual_text=manual_text if manual_text is not None else text,
                extracted_data_existing={},
            )
        elif use_new_pipeline:
            extracted = run_pipeline_v3(
                files_text=files_text or [],
                manual_text=manual_text if manual_text is not None else (text if not (files_text or []) else None),
                existing_user_inputs={
                    "cost_price": cost_price,
                    "planned_margin_percent": planned_margin_percent,
                    "llm_provider": llm_provider,
                },
            )
        else:
            extracted = extract_tender_data(text, llm_provider)
    except Exception as e:
        logger.exception(
            "analysis.extract_failed",
            extra={
                "user_id": user.id,
                "source_type": source_type,
                "source_name": source_name or "-",
            },
        )
        raise HTTPException(status_code=500, detail=f"Extractor failed: {repr(e)}")

    if not use_new_pipeline and not use_evi_extractor:
        extracted = consolidate_extraction(extracted)
    meta = extracted.setdefault("meta", {})
    meta["input_mode"] = input_mode
    if __debug__ and not use_new_pipeline and not use_evi_extractor:
        assert isinstance((meta.get("consolidation") or {}), dict), "consolidation must exist before financials"

    if ingestion_meta:
        meta["ingestion"] = ingestion_meta

    if (use_new_pipeline or use_evi_extractor) and isinstance(meta.get("quality_gate"), dict):
        gate = meta.get("quality_gate") or {}
    else:
        gate = quality_gate(extracted, text, input_mode)
    meta["corpus"] = gate.get("corpus") or {}
    meta["missing_reasons"] = gate.get("missing_reasons_base") or {}
    meta["missing_reasons_detail"] = gate.get("missing_reasons") or {}
    meta["quality_gate"] = gate
    logger.info(
        "analysis.corpus_awareness",
        extra={
            "user_id": user.id,
            "input_mode": input_mode,
            "corpus_chars": len(text),
            "has_price_section": bool((meta.get("corpus") or {}).get("has_price_section")),
            "has_payment_section": bool((meta.get("corpus") or {}).get("has_payment_section")),
            "has_execution_section": bool((meta.get("corpus") or {}).get("has_execution_section")),
            "has_liability_section": bool((meta.get("corpus") or {}).get("has_liability_section")),
            "is_partial": bool((meta.get("corpus") or {}).get("is_partial")),
            "partial_reasons": (meta.get("corpus") or {}).get("partial_reasons") or [],
            "can_compute_financials": gate.get("can_compute_financials"),
            "blocking_missing": gate.get("blocking_missing"),
            "completeness_score": gate.get("completeness_score"),
        },
    )

    danger = find_danger_phrases(text)
    extracted["danger_phrases"] = danger

    try:
        risk_score, risk_level, reasons = calculate_risk(extracted, gate)
    except TypeError:
        risk_score, risk_level, reasons = calculate_risk(extracted)

    nmck_value = extracted.get("nmck")
    current_input_mode = meta.get("input_mode")
    is_partial = bool((meta.get("corpus") or {}).get("is_partial", False))
    can_compute = (
        nmck_value is not None
        and isinstance(nmck_value, (int, float))
        and float(nmck_value) > 0
    )
    logger.info(
        "analysis.financials_gate",
        extra={
            "nmck": nmck_value,
            "input_mode": current_input_mode,
            "is_partial": is_partial,
            "financials_computed": can_compute,
        },
    )

    if not can_compute:
        roi, cash_gap = None, None
        safe_cost = None
        extracted["safe_cost_price"] = None
        extracted["roi_percent"] = None
        extracted["cash_gap"] = None
        meta["financials_skipped_due_to_missing_nmck"] = True
        meta["financials_skipped_reason"] = ["nmck_missing"]
        financials_allowed = False
        financial_block_reasons = ["nmck_missing"]
        logger.info("Financials skipped", extra={"reasons": financial_block_reasons})
    else:
        financials_allowed, financial_block_reasons = can_compute_financials(extracted)
        if financials_allowed:
            roi, cash_gap = _calculate_financials_compat(
                extracted=extracted,
                nmck_value=float(nmck_value),
                cost_price=float(cost_price),
                planned_margin_percent=float(planned_margin_percent),
            )
            safe_cost = _calculate_safe_cost_compat(
                extracted=extracted,
                nmck_value=float(nmck_value),
                roi_percent=float(roi),
            )
            if os.getenv("APP_ENV", "dev").lower() in {"dev", "development", "local"}:
                if isinstance(safe_cost, (int, float)) and safe_cost < 1000 and float(nmck_value) > 100000:
                    logger.warning(
                        "Suspicious safe_cost calculation",
                        extra={"nmck": nmck_value, "safe_cost": safe_cost, "roi_percent": roi},
                    )
        else:
            roi, cash_gap = None, None
            safe_cost = None
            meta["financials_skipped_due_to_missing_nmck"] = True
            meta["financials_skipped_reason"] = financial_block_reasons
            logger.info("Financials skipped", extra={"reasons": financial_block_reasons})

    logger.info(
        "analysis.financials_decision",
        extra={
            "user_id": user.id,
            "input_mode": input_mode,
            "financials_computed": financials_allowed,
            "financials_reason": financial_block_reasons,
        },
    )

    if (not financials_allowed) and ("nmck_missing" in financial_block_reasons):
        verdict = "Недостаточно данных для финансовой оценки"
    elif bool((meta.get("corpus") or {}).get("is_partial")):
        verdict = "Требуется проверка"
        meta["notice"] = {
            "type": "partial_analysis",
            "message": "Вставлен неполный текст. Для точного анализа загрузите все приложения (договор, ТЗ, извещение/НМЦ).",
        }
    elif risk_score >= 7:
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
        expected_roi_percent=0.0 if roi is None else round(roi, 2),
        rough_cash_gap=None if cash_gap is None else round(cash_gap, 2),
        verdict=verdict,
        input_cost_price=float(cost_price) if cost_price is not None else None,
        input_margin_percent=float(planned_margin_percent) if planned_margin_percent is not None else None,
        safe_cost_price=None if safe_cost is None else float(safe_cost),
    )

    logger.info(
        "analysis.complete",
        extra={
            "user_id": user.id,
            "analysis_id": row.id,
            "risk_score": risk_score,
            "risk_level": risk_level,
        },
    )

    return {
        "analysis_id": row.id,
        "extracted_data": extracted,
        "risk_score": risk_score,
        "risk_level": risk_level,
        "risk_reasons": reasons,
        "expected_roi_percent": None if roi is None else round(roi, 2),
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
    manual_text: str | None = Form(None),
    cost_price: float = Form(..., gt=0),
    planned_margin_percent: float = Form(..., ge=0, le=100),
    llm_provider: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)

    input_mode = "attachments_plus_text" if manual_text and manual_text.strip() else "attachments"
    docs = await extract_docs_from_uploads(files)
    corpus = build_structured_corpus(docs)
    ingestion_meta = {
        "file_count": len(docs),
        "files": [{"name": d.filename, "chars": len(d.text)} for d in docs],
        "corpus_chars": len(corpus),
        "corpus_preview": corpus[:4000],
        "manual_text_present": bool(manual_text and manual_text.strip()),
    }

    result = _run_analysis_pipeline(
        text=corpus,
        db=db,
        user=user,
        cost_price=cost_price,
        planned_margin_percent=planned_margin_percent,
        source_type="batch",
        source_name=f"Пакет документов ({len(docs)})",
        input_mode=input_mode,
        llm_provider=llm_provider,
        files_text=[(d.filename, d.text) for d in docs],
        manual_text=manual_text,
        ingestion_meta=ingestion_meta,
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
        input_mode="manual_text",
        llm_provider=data.llm_provider,
        files_text=[],
        manual_text=data.text,
    )


@app.post("/analyze/pdf")
async def analyze_tender_pdf(
    file: UploadFile = File(...),
    manual_text: str | None = Form(None),
    cost_price: float = Form(..., gt=0),
    planned_margin_percent: float = Form(..., ge=0, le=100),
    llm_provider: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)
    input_mode = "attachments_plus_text" if manual_text and manual_text.strip() else "attachments"

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
        input_mode=input_mode,
        llm_provider=llm_provider,
        files_text=[(file.filename, text)],
        manual_text=manual_text,
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
    manual_text: str | None = Form(None),
    cost_price: float = Form(..., gt=0),
    planned_margin_percent: float = Form(..., ge=0, le=100),
    llm_provider: str | None = Form(None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    check_monthly_quota(db, user)
    input_mode = "attachments_plus_text" if manual_text and manual_text.strip() else "attachments"

    if not file.filename:
        raise HTTPException(status_code=400, detail="Please upload a PDF, DOC, DOCX, XLSX, CSV or TXT file")

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
        input_mode=input_mode,
        llm_provider=llm_provider,
        files_text=[(file.filename, text)],
        manual_text=manual_text,
    )
    result["source"] = {
        "type": detected_type,
        "filename": file.filename,
        "text_chars": len(text),
    }
    return result


def _is_financials_skipped(extracted_data: dict | None) -> bool:
    meta = (extracted_data or {}).get("meta") if isinstance(extracted_data, dict) else {}
    return bool((meta or {}).get("financials_skipped_due_to_missing_nmck"))


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
            "expected_roi_percent": None if _is_financials_skipped(r.extracted_data) else r.expected_roi_percent,
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
        "expected_roi_percent": None if _is_financials_skipped(r.extracted_data) else r.expected_roi_percent,
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
    logger.info("analysis.deleted", extra={"user_id": user.id, "analysis_id": analysis_id})
    return {"ok": True}


@app.delete("/analyses")
def clear_analyses(
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    deleted = db.query(Analysis).filter(Analysis.user_id == user.id).delete(synchronize_session=False)
    db.commit()
    logger.info("analysis.cleared", extra={"user_id": user.id, "deleted_count": deleted})
    return {"ok": True, "deleted_count": deleted}

