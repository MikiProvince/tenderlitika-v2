from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from services.document_text import extract_text_from_document
from services.extraction.candidates import mine_all_candidates
from services.extraction.normalize import normalize_text
from services.extraction.quality import validate_extracted_data
from services.extraction.retrieval import retrieve_sections
from services.extraction.select import apply_selected_to_extracted_data, select_best_candidate


ALLOWED_EXT = {".pdf", ".doc", ".docx", ".txt", ".csv"}
REASON_LABELS_RU = {
    "absent_in_docs": "отсутствует в документах",
    "parse_failed": "ошибка извлечения",
    "conflict": "конфликт/некорректное значение",
}


@dataclass
class LoadedDoc:
    filename: str
    ext: str
    text: str


def _read_text_file(path: Path) -> str:
    payload = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return payload.decode(encoding)
        except Exception:
            continue
    return payload.decode("utf-8", errors="ignore")


def _load_doc(path: Path) -> LoadedDoc | None:
    ext = path.suffix.lower()
    if ext not in ALLOWED_EXT:
        return None

    if ext in {".pdf", ".doc", ".docx"}:
        text, _ = extract_text_from_document(path.name, path.read_bytes())
    else:
        text = _read_text_file(path)

    return LoadedDoc(filename=path.name, ext=ext, text=normalize_text(text))


def _build_corpus(docs: list[LoadedDoc]) -> str:
    chunks: list[str] = ["ПАКЕТ ТЕНДЕРА (АУДИТ) - СТРУКТУРИРОВАННЫЙ КОРПУС"]
    total = len(docs)
    for index, doc in enumerate(docs, start=1):
        chunks.append(f"\n===== FILE {index}/{total}: {doc.filename} ({doc.ext}) =====")
        chunks.append(doc.text)
    return normalize_text("\n".join(chunks))


def _run_audit(folder: Path) -> dict[str, Any]:
    docs: list[LoadedDoc] = []
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        loaded = _load_doc(path)
        if loaded and loaded.text:
            docs.append(loaded)

    if not docs:
        raise SystemExit(f"Поддерживаемые непустые файлы не найдены: {folder}")

    corpus = _build_corpus(docs)
    retrieved = retrieve_sections(corpus)
    candidates = mine_all_candidates(corpus)
    selected = {
        "nmck": select_best_candidate(candidates.get("nmck", [])),
        "payment": select_best_candidate(candidates.get("payment", [])),
        "execution": select_best_candidate(candidates.get("execution", [])),
        "penalties": select_best_candidate(candidates.get("penalties", [])),
    }

    extracted_data: dict[str, Any] = {
        "nmck": None,
        "payment_terms_days": None,
        "execution_days": None,
        "penalty_percent_per_day": None,
        "fine_percent": None,
        "meta": {},
    }
    apply_selected_to_extracted_data(extracted_data, selected)
    quality = validate_extracted_data(extracted_data, corpus, retrieved)
    extracted_data.setdefault("meta", {})["quality"] = quality

    return {
        "docs": docs,
        "corpus": corpus,
        "retrieved": retrieved,
        "candidates": candidates,
        "selected": selected,
        "extracted_data": extracted_data,
        "quality": quality,
    }


def _print_summary(report: dict[str, Any]) -> None:
    docs: list[LoadedDoc] = report["docs"]
    candidates: dict[str, list[dict[str, Any]]] = report["candidates"]
    selected = report["selected"]
    quality = report["quality"]

    print(f"Загружено документов: {len(docs)}")
    print(f"Размер корпуса (символов): {len(report['corpus'])}")
    print("Количество кандидатов:")
    print(f"  НМЦК: {len(candidates.get('nmck', []))}")
    print(f"  Оплата: {len(candidates.get('payment', []))}")
    print(f"  Исполнение: {len(candidates.get('execution', []))}")
    print(f"  Штрафы/пени: {len(candidates.get('penalties', []))}")
    print("Выбранные кандидаты (id):")
    print(f"  НМЦК: {selected.get('nmck', {}).get('id') if selected.get('nmck') else None}")
    print(f"  Оплата: {selected.get('payment', {}).get('id') if selected.get('payment') else None}")
    print(f"  Исполнение: {selected.get('execution', {}).get('id') if selected.get('execution') else None}")
    print(f"  Штрафы/пени: {selected.get('penalties', {}).get('id') if selected.get('penalties') else None}")
    print(f"Оценка полноты: {quality.get('completeness_score')}")
    print(f"Критически отсутствуют: {quality.get('critical_missing')}")

    reason_counts = Counter((quality.get("missing_reasons") or {}).values())
    print("Основные причины пропусков:")
    if not reason_counts:
        print("  нет")
    else:
        for reason, count in reason_counts.most_common():
            print(f"  {REASON_LABELS_RU.get(reason, reason)}: {count}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Аудит качества извлечения по папке с тендерными документами.")
    parser.add_argument("folder", help="Путь к папке с файлами pdf/doc/docx/txt/csv.")
    args = parser.parse_args()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.exists() or not folder.is_dir():
        raise SystemExit(f"Папка не найдена: {folder}")

    report = _run_audit(folder)
    _print_summary(report)


if __name__ == "__main__":
    main()
