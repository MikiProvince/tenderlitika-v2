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


@dataclass
class ExtractedDoc:
    filename: str
    ext: str
    text: str


def _clean_text(s: str) -> str:
    return normalize_text(s)


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

    corpus_lower = corpus.lower()
    contract_files = [d.filename for d in docs if re.search(r"(договор|контракт|проект)", d.filename.lower())]
    tech_files = [d.filename for d in docs if re.search(r"(тех|техничес|тз|техзад|специф|requirements)", d.filename.lower())]

    if contract_files and not any(k in corpus_lower for k in ("оплата", "неустойк", "штраф", "пеня")):
        logger.warning("contract_text_missing", extra={"files": contract_files})

    if tech_files and not any(k in corpus_lower for k in ("срок", "партия", "отгруз", "поставка")):
        logger.warning("tech_text_missing", extra={"files": tech_files})

    logger.info(
        "batch.corpus.built",
        extra={"file_count": len(docs), "corpus_chars": len(corpus)},
    )

    return corpus
