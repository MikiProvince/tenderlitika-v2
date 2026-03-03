from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from services.document_text import extract_text_from_document
from services.evi_extractor.pipeline import run_evi_extractor


SUPPORTED_EXT = {".pdf", ".doc", ".docx", ".txt", ".csv", ".xlsx"}


def _load_file_text(path: Path) -> tuple[str, str]:
    ext = path.suffix.lower()
    raw = path.read_bytes()
    if ext in {".txt", ".csv"}:
        text = raw.decode("utf-8", errors="ignore")
        return text, ext.lstrip(".")
    text, detected = extract_text_from_document(path.name, raw)
    return text, detected


def _collect_inputs(path: Path) -> tuple[list[tuple[str, str]], str | None]:
    if path.is_file():
        text, _ = _load_file_text(path)
        if path.suffix.lower() in {".txt", ".csv"}:
            return [], text
        return [(path.name, text)], None

    files_text: list[tuple[str, str]] = []
    for file_path in sorted(path.rglob("*")):
        if not file_path.is_file() or file_path.suffix.lower() not in SUPPORTED_EXT:
            continue
        text, _ = _load_file_text(file_path)
        files_text.append((str(file_path.name), text))
    return files_text, None


def _key_snapshot(data: dict[str, Any]) -> dict[str, Any]:
    meta = data.get("meta") or {}
    return {
        "nmck": data.get("nmck"),
        "payment_terms_days": data.get("payment_terms_days"),
        "execution_days": data.get("execution_days"),
        "penalties": (meta.get("penalties") or {}),
        "evidence": (meta.get("evidence") or {}),
    }


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        print("Usage: python -m services.evi_extractor.audit_cli <path>")
        return 1

    input_path = Path(args[0]).resolve()
    if not input_path.exists():
        print(f"Path not found: {input_path}")
        return 1

    files_text, manual_text = _collect_inputs(input_path)
    run1 = run_evi_extractor(files_text, manual_text, extracted_data_existing={})
    run2 = run_evi_extractor(files_text, manual_text, extracted_data_existing={})

    snap1 = _key_snapshot(run1)
    snap2 = _key_snapshot(run2)
    if snap1 != snap2:
        raise AssertionError("Idempotency check failed: key fields differ between runs")

    evidence = (run1.get("meta") or {}).get("evidence") or {}
    print("nmck:", run1.get("nmck"))
    print("payment_terms_days:", run1.get("payment_terms_days"))
    print("execution_days:", run1.get("execution_days"))
    penalties = (run1.get("meta") or {}).get("penalties") or {}
    print("penalties:", json.dumps(penalties, ensure_ascii=False))
    for field in ("nmck", "payment_terms", "execution_days", "penalties"):
        ev = evidence.get(field) or {}
        print(f"evidence[{field}].file:", ev.get("file"))

    print("Idempotency: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
