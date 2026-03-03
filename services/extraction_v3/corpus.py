from __future__ import annotations

from typing import Any

from services.extraction_v3.normalize import normalize_text


def build_corpus(files_text: list[tuple[str, str]], manual_text: str | None) -> dict[str, Any]:
    normalized_files: list[tuple[str, str]] = []
    for name, text in files_text or []:
        file_name = (name or "file").strip() or "file"
        normalized_files.append((file_name, normalize_text(text or "")))

    normalized_manual = normalize_text(manual_text or "")

    has_attachments = len(normalized_files) > 0
    has_manual = bool(normalized_manual)

    if has_attachments and has_manual:
        input_mode = "attachments_plus_text"
    elif has_attachments:
        input_mode = "attachments"
    else:
        input_mode = "manual_text"

    chunks: list[str] = []
    blocks: list[dict[str, Any]] = []

    if normalized_files:
        total = len(normalized_files)
        for idx, (file_name, text) in enumerate(normalized_files, start=1):
            marker = f"===== FILE {idx}/{total}: {file_name} =====\n"
            chunks.append(marker)
            block_start = sum(len(part) for part in chunks)
            chunks.append(text)
            chunks.append("\n\n")
            blocks.append(
                {
                    "file": file_name,
                    "text": text,
                    "start": block_start,
                }
            )

    if normalized_manual:
        marker = "===== MANUAL_TEXT =====\n"
        chunks.append(marker)
        block_start = sum(len(part) for part in chunks)
        chunks.append(normalized_manual)
        chunks.append("\n")
        blocks.append(
            {
                "file": "manual_text",
                "text": normalized_manual,
                "start": block_start,
            }
        )

    corpus = "".join(chunks).strip()
    return {
        "corpus": corpus,
        "blocks": blocks,
        "input_mode": input_mode,
        "length": len(corpus),
    }
