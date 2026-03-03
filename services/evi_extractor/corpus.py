from __future__ import annotations

from typing import Any

from services.evi_extractor.normalize import normalize_text


def _manual_present(manual_text: str | None) -> bool:
    return bool(manual_text and manual_text.strip())


def _detect_input_mode(files: list[tuple[str, str]], manual_text: str | None) -> str:
    has_files = bool(files)
    has_manual = _manual_present(manual_text)
    if has_files and has_manual:
        return "attachments_plus_text"
    if has_files:
        return "attachments"
    return "manual_text"


def build_corpus(files: list[tuple[str, str]], manual_text: str | None) -> dict[str, Any]:
    input_mode = _detect_input_mode(files, manual_text)

    chunks: list[str] = []
    blocks: list[dict[str, Any]] = []
    cursor = 0

    for filename, raw_text in files:
        marker = f"===== FILE {filename} =====\n"
        chunks.append(marker)
        cursor += len(marker)

        cleaned = normalize_text(raw_text or "")
        blocks.append({"file": filename, "text": cleaned, "start": cursor})
        chunks.append(cleaned + "\n")
        cursor += len(cleaned) + 1

    if _manual_present(manual_text):
        marker = "===== FILE MANUAL_TEXT =====\n"
        chunks.append(marker)
        cursor += len(marker)

        cleaned_manual = normalize_text(manual_text or "")
        blocks.append({"file": None, "text": cleaned_manual, "start": cursor})
        chunks.append(cleaned_manual + "\n")
        cursor += len(cleaned_manual) + 1

    corpus = "".join(chunks).strip()
    return {
        "input_mode": input_mode,
        "corpus": corpus,
        "blocks": blocks,
        "length": len(corpus),
    }
