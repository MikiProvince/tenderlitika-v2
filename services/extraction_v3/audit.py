from __future__ import annotations

import json
import os
from collections import Counter
from pathlib import Path
from typing import Any

from services.extraction_v3.pipeline import run_pipeline


ALLOWED_EXT = {".txt", ".md", ".csv", ".log"}
SNAPSHOT_KEYS = ("nmck", "payment_terms_days", "execution_days", "penalty_percent_per_day", "fine_percent")


def _read_text(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8", "utf-8-sig", "cp1251"):
        try:
            return raw.decode(encoding, errors="strict")
        except Exception:
            continue
    return raw.decode("utf-8", errors="ignore")


def _snapshot(extracted: dict[str, Any]) -> dict[str, Any]:
    meta = extracted.get("meta") or {}
    return {
        "fields": {key: extracted.get(key) for key in SNAPSHOT_KEYS},
        "payment_meta": meta.get("payment"),
        "penalties_meta": meta.get("penalties"),
        "quality": meta.get("quality_gate"),
    }


def run_audit(folder: str) -> int:
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        print(f"Folder not found: {folder}")
        return 2

    files = sorted(
        [
            path
            for path in root.rglob("*")
            if path.is_file() and path.suffix.lower() in ALLOWED_EXT
        ],
        key=lambda path: str(path).lower(),
    )

    if not files:
        print("No supported text files found (.txt/.md/.csv/.log).")
        return 1

    total = len(files)
    nmck_found = 0
    payment_found = 0
    penalties_found = 0
    idempotent_ok = 0
    missing_reasons = Counter()

    for path in files:
        text = _read_text(path)
        payload = [(path.name, text)]
        first = run_pipeline(payload, None, {})
        second = run_pipeline(payload, None, {})

        if isinstance(first.get("nmck"), (int, float)) and float(first.get("nmck")) > 0:
            nmck_found += 1
        if isinstance(first.get("payment_terms_days"), (int, float)) and float(first.get("payment_terms_days")) > 0:
            payment_found += 1
        if isinstance(first.get("penalty_percent_per_day"), (int, float)):
            penalties_found += 1

        q = (first.get("meta") or {}).get("quality_gate") or {}
        for reason in (q.get("missing_reasons") or {}).values():
            missing_reasons[str(reason)] += 1

        if json.dumps(_snapshot(first), ensure_ascii=False, sort_keys=True) == json.dumps(
            _snapshot(second), ensure_ascii=False, sort_keys=True
        ):
            idempotent_ok += 1

    print(f"Files: {total}")
    print(f"% nmck found: {round(100.0 * nmck_found / total, 2)}")
    print(f"% payment found: {round(100.0 * payment_found / total, 2)}")
    print(f"% penalties found: {round(100.0 * penalties_found / total, 2)}")

    if missing_reasons:
        print("Top missing reasons:")
        for reason, count in missing_reasons.most_common(5):
            print(f"  {reason}: {count}")
    else:
        print("Top missing reasons: none")

    print(f"Idempotency: {idempotent_ok}/{total} identical")
    return 0


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Usage: python -m services.extraction_v3.audit <folder>")
        raise SystemExit(2)
    raise SystemExit(run_audit(sys.argv[1]))
