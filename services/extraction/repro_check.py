from __future__ import annotations

import argparse
import difflib
import json
from pathlib import Path
from typing import Any

from core.extractor import consolidate_extraction, extract_tender_data


KEY_FIELDS = [
    "nmck",
    "payment_terms_days",
    "execution_days",
    "penalty_percent_per_day",
    "fine_percent",
]


def _read_text(path: Path) -> str:
    payload = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return payload.decode(encoding)
        except Exception:
            continue
    return payload.decode("utf-8", errors="ignore")


def _snapshot(extracted: dict[str, Any]) -> dict[str, Any]:
    meta = extracted.get("meta") or {}
    return {
        "fields": {field: extracted.get(field) for field in KEY_FIELDS},
        "meta_payment": meta.get("payment"),
        "meta_penalties": meta.get("penalties"),
        "meta_consolidation": meta.get("consolidation"),
        "meta_quality": meta.get("quality"),
    }


def _run_once(text: str) -> dict[str, Any]:
    extracted = extract_tender_data(text)
    consolidate_extraction(extracted)
    return _snapshot(extracted)


def main() -> None:
    parser = argparse.ArgumentParser(description="Проверка воспроизводимости извлечения по текстовому файлу.")
    parser.add_argument("path", help="Путь к текстовому файлу для повторного прогона экстрактора.")
    args = parser.parse_args()

    path = Path(args.path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        raise SystemExit(f"Файл не найден: {path}")

    text = _read_text(path)
    first = _run_once(text)
    second = _run_once(text)

    if first == second:
        print("OK: результаты идентичны между двумя запусками.")
        print(json.dumps(first, ensure_ascii=False, indent=2, sort_keys=True))
        return

    first_json = json.dumps(first, ensure_ascii=False, indent=2, sort_keys=True)
    second_json = json.dumps(second, ensure_ascii=False, indent=2, sort_keys=True)
    diff = "\n".join(
        difflib.unified_diff(
            first_json.splitlines(),
            second_json.splitlines(),
            fromfile="run_1",
            tofile="run_2",
            lineterm="",
        )
    )
    print("ERROR: результаты отличаются между повторными запусками.")
    print(diff)
    raise SystemExit(1)


if __name__ == "__main__":
    main()
