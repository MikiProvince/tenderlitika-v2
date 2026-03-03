from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass
from typing import List

from fastapi import HTTPException, UploadFile

from services.document_text import extract_text_from_document
from services.extraction.normalize import normalize_text

logger = logging.getLogger(__name__)

MAX_FILES = 25
MAX_FILE_BYTES = 15 * 1024 * 1024  # 15MB на файл (можно поменять)
ALLOWED_EXT = {".pdf", ".txt", ".doc", ".docx", ".xlsx", ".csv"}
ROLE_THRESHOLD = 3

CONTRACT_ANCHORS = [
    "предмет контракта",
    "порядок оплаты",
    "оплата",
    "платеж",
    "платёж",
    "расчет",
    "расчёт",
    "аванс",
    "предоплата",
    "ответственность",
    "неустойк",
    "штраф",
    "пеня",
    "1/300",
    "ключев",
]

TECH_ANCHORS = [
    "техничес",
    "требован",
    "тз",
    "спецификац",
    "описание объекта",
    "поставка",
    "отгруз",
    "партия",
    "срок поставки",
]

PRICE_ANCHORS = [
    "нмцк",
    "начальная (максимальная) цена",
    "цена контракта",
    "обоснование нмц",
    "расчет нмц",
    "итого",
    "цена, руб",
]

CONTRACT_FILENAME_RE = re.compile(r"(контракт|договор|проект)")
TECH_FILENAME_RE = re.compile(r"(тех|тз|требован|описание)")
PRICE_FILENAME_RE = re.compile(r"(нмц|обосн)")


@dataclass
class ExtractedDoc:
    filename: str
    ext: str
    text: str


def _clean_text(s: str) -> str:
    return normalize_text(s)


def _score_doc_role(doc: ExtractedDoc) -> dict:
    lowered_text = (doc.text or "").lower()
    lowered_name = (doc.filename or "").lower()

    contract_hits = [anchor for anchor in CONTRACT_ANCHORS if anchor in lowered_text]
    tech_hits = [anchor for anchor in TECH_ANCHORS if anchor in lowered_text]
    price_hits = [anchor for anchor in PRICE_ANCHORS if anchor in lowered_text]

    contract_score = sum(lowered_text.count(anchor) for anchor in CONTRACT_ANCHORS)
    tech_score = sum(lowered_text.count(anchor) for anchor in TECH_ANCHORS)
    price_score = sum(lowered_text.count(anchor) for anchor in PRICE_ANCHORS)

    if CONTRACT_FILENAME_RE.search(lowered_name):
        contract_score += 2
    if TECH_FILENAME_RE.search(lowered_name):
        tech_score += 2
    if PRICE_FILENAME_RE.search(lowered_name):
        price_score += 2

    return {
        "contract_score": int(contract_score),
        "tech_score": int(tech_score),
        "price_score": int(price_score),
        "anchors": {
            "contract": contract_hits,
            "tech": tech_hits,
            "price": price_hits,
        },
    }


async def extract_docs_from_uploads(files: List[UploadFile]) -> List[ExtractedDoc]:
    if not files:
        raise HTTPException(status_code=400, detail="No files provided")

    if len(files) > MAX_FILES:
        raise HTTPException(status_code=400, detail=f"Too many files. Max {MAX_FILES}")

    docs: List[ExtractedDoc] = []
    non_empty_count = 0

    for uf in files:
        filename = uf.filename or "file"
        ext = os.path.splitext(filename.lower())[1]

        if ext not in ALLOWED_EXT:
            raise HTTPException(
                status_code=400,
                detail=f"Unsupported file type: {ext}. Allowed: {sorted(ALLOWED_EXT)}",
            )

        data = await uf.read()
        if len(data) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail=f"File too large: {filename}")

        try:
            text, _ = extract_text_from_document(filename, data)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

        text = _clean_text(text)
        if text:
            non_empty_count += 1

        docs.append(ExtractedDoc(filename=filename, ext=ext, text=text))

    if not docs or non_empty_count == 0:
        raise HTTPException(status_code=400, detail="No text extracted from provided files")

    logger.info(
        "batch.docs.extracted",
        extra={
            "file_count": len(docs),
            "non_empty_count": non_empty_count,
            "files": [{"name": d.filename, "chars": len(d.text)} for d in docs],
        },
    )

    return docs


def build_structured_corpus(docs: List[ExtractedDoc]) -> str:
    # Важное: явные границы файлов.
    chunks: List[str] = []
    chunks.append("TENDER PACKAGE (MULTI-FILE) - STRUCTURED CORPUS\n")
    for i, d in enumerate(docs, start=1):
        chunks.append(f"\n===== FILE {i}/{len(docs)}: {d.filename} ({d.ext}) =====\n")
        chunks.append(d.text)
    corpus = normalize_text("\n".join(chunks))

    scored_docs: list[dict] = []
    for doc in docs:
        scored_docs.append({"doc": doc, "score": _score_doc_role(doc)})

    logger.info(
        "batch.docs.scored",
        extra={
            "docs": [
                {
                    "name": item["doc"].filename,
                    "chars": len(item["doc"].text),
                    "contract_score": item["score"]["contract_score"],
                    "tech_score": item["score"]["tech_score"],
                    "price_score": item["score"]["price_score"],
                }
                for item in scored_docs
            ]
        },
    )

    contract_docs = [
        item
        for item in scored_docs
        if CONTRACT_FILENAME_RE.search(item["doc"].filename.lower()) or item["score"]["contract_score"] >= ROLE_THRESHOLD
    ]
    tech_docs = [
        item
        for item in scored_docs
        if TECH_FILENAME_RE.search(item["doc"].filename.lower()) or item["score"]["tech_score"] >= ROLE_THRESHOLD
    ]

    for item in contract_docs:
        doc = item["doc"]
        contract_anchors = item["score"]["anchors"]["contract"]
        if not doc.text.strip():
            logger.warning("contract_text_empty", extra={"doc_filename": doc.filename})
        elif not contract_anchors:
            logger.warning("contract_text_no_anchors", extra={"doc_filename": doc.filename})

    for item in tech_docs:
        doc = item["doc"]
        tech_anchors = item["score"]["anchors"]["tech"]
        if not doc.text.strip():
            logger.warning("tech_text_empty", extra={"doc_filename": doc.filename})
        elif not tech_anchors:
            logger.warning("tech_text_no_anchors", extra={"doc_filename": doc.filename})

    logger.info(
        "batch.corpus.built",
        extra={"file_count": len(docs), "corpus_chars": len(corpus)},
    )

    return corpus
