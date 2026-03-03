from __future__ import annotations

import csv
import re
from io import BytesIO, StringIO
from pathlib import Path
from xml.etree import ElementTree
from zipfile import ZipFile

from services.extraction.normalize import normalize_text
from services.pdf_text import extract_text_from_pdf_bytes


_MAX_TEXT_CHARS = 120_000


def _normalize_text(text: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    return normalize_text(text)[:max_chars]


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


def _extract_text_from_plain_bytes(raw_bytes: bytes, max_chars: int = _MAX_TEXT_CHARS) -> str:
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            text = raw_bytes.decode(encoding, errors="strict")
            return _normalize_text(text, max_chars=max_chars)
        except UnicodeDecodeError:
            continue
    return _normalize_text(raw_bytes.decode("utf-8", errors="ignore"), max_chars=max_chars)


def _resolve_xlsx_path(target: str) -> str:
    cleaned = (target or "").replace("\\", "/").strip()
    if not cleaned:
        return ""
    if cleaned.startswith("/"):
        cleaned = cleaned[1:]
    while cleaned.startswith("../"):
        cleaned = cleaned[3:]
    if cleaned.startswith("xl/"):
        return cleaned
    return f"xl/{cleaned}"


def _extract_xlsx_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []

    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    shared: list[str] = []
    for si in root.findall(".//{*}si"):
        parts = [(node.text or "") for node in si.findall(".//{*}t")]
        shared.append("".join(parts))
    return shared


def _extract_xlsx_sheet_map(archive: ZipFile) -> list[tuple[str, str]]:
    if "xl/workbook.xml" not in archive.namelist():
        return []

    workbook_root = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels: dict[str, str] = {}

    rels_path = "xl/_rels/workbook.xml.rels"
    if rels_path in archive.namelist():
        rels_root = ElementTree.fromstring(archive.read(rels_path))
        for rel in rels_root.findall(".//{*}Relationship"):
            rel_id = rel.attrib.get("Id")
            target = rel.attrib.get("Target")
            if rel_id and target:
                rels[rel_id] = _resolve_xlsx_path(target)

    rel_id_keys = (
        "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id",
        "{http://purl.oclc.org/ooxml/officeDocument/relationships}id",
    )
    sheet_map: list[tuple[str, str]] = []
    for sheet in workbook_root.findall(".//{*}sheet"):
        sheet_name = (sheet.attrib.get("name") or "Sheet").strip() or "Sheet"
        rel_id = None
        for key in rel_id_keys:
            if key in sheet.attrib:
                rel_id = sheet.attrib.get(key)
                break
        sheet_path = rels.get(rel_id or "")
        if sheet_path:
            sheet_map.append((sheet_name, sheet_path))

    if sheet_map:
        return sheet_map

    fallback_paths = sorted(
        [name for name in archive.namelist() if name.startswith("xl/worksheets/") and name.endswith(".xml")]
    )
    return [(Path(path).stem, path) for path in fallback_paths]


def _xlsx_column_to_index(cell_ref: str) -> int:
    acc = 0
    for ch in (cell_ref or ""):
        if not ch.isalpha():
            break
        acc = acc * 26 + (ord(ch.upper()) - ord("A") + 1)
    return max(0, acc - 1) if acc else 0


def _extract_xlsx_cell_text(cell_node: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell_node.attrib.get("t")
    if cell_type == "inlineStr":
        parts = [(node.text or "") for node in cell_node.findall(".//{*}is/{*}t")]
        return "".join(parts).strip()

    value_node = cell_node.find("./{*}v")
    if value_node is None or value_node.text is None:
        return ""

    raw = value_node.text.strip()
    if cell_type == "s":
        try:
            idx = int(raw)
            return shared_strings[idx].strip() if 0 <= idx < len(shared_strings) else ""
        except Exception:
            return ""

    return raw


def _extract_xlsx_sheet_rows(
    archive: ZipFile,
    sheet_path: str,
    shared_strings: list[str],
    max_rows: int = 300,
    max_cols: int = 30,
) -> list[str]:
    if sheet_path not in archive.namelist():
        return []

    root = ElementTree.fromstring(archive.read(sheet_path))
    rows: list[str] = []

    for row_node in root.findall(".//{*}sheetData/{*}row"):
        if len(rows) >= max_rows:
            break

        row_map: dict[int, str] = {}
        for cell_node in row_node.findall("./{*}c"):
            col_idx = _xlsx_column_to_index(cell_node.attrib.get("r", ""))
            if col_idx >= max_cols:
                continue
            value = _extract_xlsx_cell_text(cell_node, shared_strings)
            if value:
                row_map[col_idx] = value

        if not row_map:
            continue

        max_idx = max(row_map.keys())
        values = [row_map.get(idx, "").strip() for idx in range(max_idx + 1)]
        while values and not values[-1]:
            values.pop()
        if values:
            rows.append(" | ".join(values))

    return rows


def _extract_text_from_xlsx_bytes(xlsx_bytes: bytes, max_chars: int = _MAX_TEXT_CHARS) -> str:
    with ZipFile(BytesIO(xlsx_bytes), "r") as archive:
        shared_strings = _extract_xlsx_shared_strings(archive)
        sheet_map = _extract_xlsx_sheet_map(archive)
        if not sheet_map:
            return ""

        lines: list[str] = []
        for sheet_name, sheet_path in sheet_map:
            rows = _extract_xlsx_sheet_rows(archive, sheet_path, shared_strings)
            if not rows:
                continue
            lines.append(f"[SHEET] {sheet_name}")
            lines.extend(rows)
            lines.append("")

    return _normalize_text("\n".join(lines), max_chars=max_chars)


def _extract_text_from_csv_bytes(csv_bytes: bytes, max_chars: int = _MAX_TEXT_CHARS) -> str:
    raw = _extract_text_from_plain_bytes(csv_bytes, max_chars=max_chars * 2)
    if not raw:
        return ""

    sample = raw[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except Exception:
        dialect = csv.excel

    reader = csv.reader(StringIO(raw), dialect=dialect)
    rows: list[str] = []
    for idx, row in enumerate(reader):
        if idx >= 1000:
            break
        cells = [str(cell).strip() for cell in row]
        if any(cells):
            rows.append(" | ".join(cells))

    return _normalize_text("\n".join(rows) if rows else raw, max_chars=max_chars)


def extract_text_from_document(filename: str, payload: bytes, max_chars: int = _MAX_TEXT_CHARS) -> tuple[str, str]:
    ext = Path(filename).suffix.lower()

    if ext == ".pdf":
        return extract_text_from_pdf_bytes(payload, max_chars=max_chars), "pdf"
    if ext == ".docx":
        return _extract_text_from_docx_bytes(payload, max_chars=max_chars), "docx"
    if ext == ".doc":
        return _extract_text_from_doc_bytes(payload, max_chars=max_chars), "doc"
    if ext == ".xlsx":
        return _extract_text_from_xlsx_bytes(payload, max_chars=max_chars), "xlsx"
    if ext == ".csv":
        return _extract_text_from_csv_bytes(payload, max_chars=max_chars), "csv"
    if ext == ".txt":
        return _extract_text_from_plain_bytes(payload, max_chars=max_chars), "txt"
    if ext == ".xls":
        raise ValueError("Legacy XLS is not supported. Please resave the file as XLSX.")

    raise ValueError("Unsupported format. Upload PDF, DOC, DOCX, XLSX, CSV or TXT")
