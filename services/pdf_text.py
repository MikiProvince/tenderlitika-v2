from __future__ import annotations

import fitz  # PyMuPDF

def extract_text_from_pdf_bytes(pdf_bytes: bytes, max_chars: int = 120_000) -> str:
    """
    Извлекает текст из PDF (не OCR).
    Ограничиваем max_chars, чтобы не перегружать память.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    parts: list[str] = []
    total = 0

    for page in doc:
        t = page.get_text("text") or ""
        if not t.strip():
            continue

        # Нормализуем пробелы слегка, без агрессии
        t = t.replace("\r", "\n")

        parts.append(t)
        total += len(t)

        if total >= max_chars:
            break

    doc.close()
    return "\n".join(parts).strip()
