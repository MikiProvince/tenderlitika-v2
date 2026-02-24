from __future__ import annotations

from io import BytesIO
from pathlib import Path
import re
from zipfile import ZipFile
from xml.etree import ElementTree

from services.pdf_text import extract_text_from_pdf_bytes


_MAX_TEXT_CHARS = 120_000


def _normalize_text(text: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    text = text.replace("\r", "\n")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()[:max_chars]


def _extract_text_from_docx_bytes(docx_bytes: bytes, max_chars: int = _MAX_TEXT_CHARS) -> str:
    with ZipFile(BytesIO(docx_bytes), "r") as archive:
        xml_bytes = archive.read("word/document.xml")

    try:
        root = ElementTree.fromstring(xml_bytes)
        parts: list[str] = []
        for node in root.iter():
            tag = node.tag
            if tag.endswith("}t") and node.text:
                parts.append(node.text)
            elif tag.endswith("}tab"):
                parts.append("\t")
            elif tag.endswith("}br") or tag.endswith("}cr") or tag.endswith("}p"):
                parts.append("\n")
        text = "".join(parts)
        return _normalize_text(text, max_chars=max_chars)
    except Exception:
        xml = xml_bytes.decode("utf-8", errors="ignore")
        text = re.sub(r"</w:p>", "\n", xml)
        text = re.sub(r"<[^>]+>", "", text)
        text = text.replace("&amp;", "&")
        text = text.replace("&lt;", "<").replace("&gt;", ">")
        text = text.replace("&quot;", "\"").replace("&apos;", "'")
        return _normalize_text(text, max_chars=max_chars)


def _extract_text_from_doc_bytes(doc_bytes: bytes, max_chars: int = _MAX_TEXT_CHARS) -> str:
    # Для старого бинарного .doc без внешних утилит нет полностью надежного парсинга.
    # Пытаемся извлечь читаемые фрагменты как текст.
    text = doc_bytes.decode("utf-8", errors="ignore")
    if len(text.strip()) < 100:
        text = doc_bytes.decode("cp1251", errors="ignore")
    return _normalize_text(text, max_chars=max_chars)


def extract_text_from_document(filename: str, payload: bytes, max_chars: int = _MAX_TEXT_CHARS) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf_bytes(payload, max_chars=max_chars), "pdf"
    if ext == ".docx":
        return _extract_text_from_docx_bytes(payload, max_chars=max_chars), "docx"
    if ext == ".doc":
        return _extract_text_from_doc_bytes(payload, max_chars=max_chars), "doc"

    raise ValueError("Unsupported format. Upload PDF, DOC or DOCX")
