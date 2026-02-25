from __future__ import annotations

import logging
import os

import fitz  # PyMuPDF
try:
    from PIL import Image
    import pytesseract
except Exception:
    Image = None
    pytesseract = None

logger = logging.getLogger(__name__)


def _is_true(value: str | None) -> bool:
    if not value:
        return False
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _extract_text_sorted(page: fitz.Page) -> str:
    try:
        return page.get_text("text", sort=True) or ""
    except TypeError:
        return page.get_text("text") or ""


def _get_words(page: fitz.Page) -> list[tuple]:
    try:
        words = page.get_text("words", sort=True)
    except TypeError:
        words = page.get_text("words")
    return words or []


def _group_words_into_rows(
    words: list[tuple],
    page: fitz.Page,
) -> list[list[tuple[float, float, str]]]:
    if not words:
        return []

    row_tol = max(2.0, page.rect.height * 0.005)

    items = []
    for x0, y0, x1, y1, word, *_ in words:
        if not word:
            continue
        y_mid = (y0 + y1) / 2.0
        items.append((y_mid, x0, x1, word))

    items.sort(key=lambda v: (v[0], v[1]))

    rows: list[list[tuple[float, float, str]]] = []
    current_y: float | None = None
    for y_mid, x0, x1, word in items:
        if current_y is None or abs(y_mid - current_y) > row_tol:
            rows.append([])
            current_y = y_mid
        rows[-1].append((x0, x1, word))

    return rows


def _extract_text_rows(rows: list[list[tuple[float, float, str]]], page: fitz.Page) -> str:
    if not rows:
        return ""

    gap_threshold = max(8.0, page.rect.width * 0.02)
    lines: list[str] = []
    for row in rows:
        row.sort(key=lambda v: v[0])
        parts: list[str] = []
        last_x1: float | None = None
        for x0, x1, word in row:
            if last_x1 is None:
                parts.append(word)
            else:
                gap = x0 - last_x1
                if gap > gap_threshold:
                    parts.append("\t" + word)
                else:
                    parts.append(" " + word)
            last_x1 = x1
        lines.append("".join(parts))

    return "\n".join(lines)


def _detect_table(
    rows: list[list[tuple[float, float, str]]],
    page: fitz.Page,
) -> tuple[bool, int, int]:
    if not rows or len(rows) < 3:
        return False, len(rows), 0

    col_tol = max(6.0, page.rect.width * 0.015)
    col_counts: list[int] = []

    for row in rows:
        if len(row) < 3:
            continue
        row.sort(key=lambda v: v[0])
        col_centers: list[float] = []
        for x0, _, _ in row:
            matched = False
            for i, center in enumerate(col_centers):
                if abs(x0 - center) <= col_tol:
                    col_centers[i] = (center + x0) / 2.0
                    matched = True
                    break
            if not matched:
                col_centers.append(x0)
        if len(col_centers) >= 2:
            col_counts.append(len(col_centers))

    if len(col_counts) < 3:
        return False, len(rows), 0

    col_counts.sort()
    median_cols = col_counts[len(col_counts) // 2]

    if median_cols >= 3:
        return True, len(rows), median_cols
    if median_cols == 2 and len(col_counts) >= 6:
        return True, len(rows), median_cols

    return False, len(rows), median_cols


def _choose_text(text_sorted: str, text_rows: str, table_like: bool) -> str:
    if not text_sorted.strip():
        return text_rows
    if not text_rows.strip():
        return text_sorted

    if table_like:
        return text_rows

    tab_count = text_rows.count("\t")
    if tab_count >= 5:
        return text_rows
    if len(text_rows) > len(text_sorted) * 1.1:
        return text_rows
    return text_sorted


def _ocr_page(page: fitz.Page, dpi: int, lang: str) -> str:
    if pytesseract is None or Image is None:
        return ""

    scale = max(1.0, dpi / 72.0)
    matrix = fitz.Matrix(scale, scale)
    pix = page.get_pixmap(matrix=matrix, alpha=False)

    if pix.n >= 3:
        mode = "RGB"
    else:
        mode = "L"
    img = Image.frombytes(mode, (pix.width, pix.height), pix.samples)
    return pytesseract.image_to_string(img, lang=lang)


def extract_text_from_pdf_bytes(pdf_bytes: bytes, max_chars: int = 120_000) -> str:
    """
    Extract text from PDF with optional OCR fallback.
    """
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")

    parts: list[str] = []
    total = 0
    ocr_enabled = _is_true(os.getenv("PDF_OCR", "1"))
    ocr_lang = os.getenv("PDF_OCR_LANG", "rus+eng")
    ocr_dpi = _get_int_env("PDF_OCR_DPI", 200)
    ocr_min_chars = _get_int_env("PDF_OCR_MIN_CHARS", 40)

    try:
        for page_index, page in enumerate(doc, start=1):
            text_sorted = _extract_text_sorted(page)
            words = _get_words(page)
            rows = _group_words_into_rows(words, page)
            text_rows = _extract_text_rows(rows, page)
            table_like, row_count, median_cols = _detect_table(rows, page)
            if table_like:
                logger.info(
                    "pdf.table.detected",
                    extra={
                        "page": page_index,
                        "rows": row_count,
                        "median_cols": median_cols,
                    },
                )
            t = _choose_text(text_sorted, text_rows, table_like)

            if ocr_enabled and len(t.strip()) < ocr_min_chars:
                if pytesseract is None or Image is None:
                    logger.warning("pdf.ocr.missing_deps", extra={"page": page_index})
                else:
                    ocr_text = _ocr_page(page, ocr_dpi, ocr_lang)
                    if ocr_text:
                        logger.info(
                            "pdf.ocr.used",
                            extra={"page": page_index, "ocr_chars": len(ocr_text)},
                        )
                        if len(t.strip()) < ocr_min_chars:
                            t = ocr_text
                        else:
                            if ocr_text not in t:
                                t = t + "\n" + ocr_text

            if not t.strip():
                continue

            t = t.replace("\r", "\n")

            remaining = max_chars - total
            if remaining <= 0:
                break
            if len(t) > remaining:
                t = t[:remaining]

            parts.append(t)
            total += len(t)

            if total >= max_chars:
                break
    finally:
        doc.close()

    return "\n".join(parts).strip()
