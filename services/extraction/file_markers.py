from __future__ import annotations

import re
from typing import Any


_FILE_MARKER_RE = re.compile(
    r"^===== FILE\s+\d+/\d+:\s*(.+?)\s*=====$",
    flags=re.MULTILINE,
)


def split_by_file_markers(corpus: str) -> list[dict[str, Any]]:
    if corpus is None:
        return [{"file": None, "text": "", "start_offset": 0}]

    matches = list(_FILE_MARKER_RE.finditer(corpus))
    if not matches:
        return [{"file": None, "text": corpus, "start_offset": 0}]

    blocks: list[dict[str, Any]] = []
    for index, match in enumerate(matches):
        next_start = matches[index + 1].start() if index + 1 < len(matches) else len(corpus)
        raw_block = corpus[match.end():next_start]
        leading_ws = len(raw_block) - len(raw_block.lstrip("\r\n"))
        start_offset = match.end() + leading_ws
        blocks.append(
            {
                "file": (match.group(1) or "").strip() or None,
                "text": raw_block.lstrip("\r\n"),
                "start_offset": start_offset,
            }
        )

    if not blocks:
        return [{"file": None, "text": corpus, "start_offset": 0}]
    return blocks


def locate_offset_to_file(blocks: list[dict[str, Any]], offset: int) -> str | None:
    if not blocks:
        return None

    current_file: str | None = None
    for block in blocks:
        start_offset = int(block.get("start_offset", 0))
        if start_offset <= offset:
            current_file = block.get("file")
        else:
            break
    return current_file
