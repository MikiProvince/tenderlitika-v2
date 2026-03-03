from __future__ import annotations

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import uuid
from decimal import Decimal
from typing import Any

from services.evi_extractor.candidates import Candidate


def _empty_result(notes: str = "llm_unavailable") -> dict[str, Any]:
    return {
        "selected_id": None,
        "confidence": 0.0,
        "notes": notes,
        "must_quote_match": False,
    }


def _json_load_loose(payload: str) -> dict[str, Any]:
    if not payload:
        return {}
    cleaned = payload.strip()
    if cleaned.startswith("{") and cleaned.endswith("}"):
        try:
            return json.loads(cleaned)
        except Exception:
            pass
    match = re.search(r"\{[\s\S]*\}", cleaned)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except Exception:
        return {}


def _to_jsonable(value: Any) -> Any:
    if isinstance(value, Decimal):
        return float(value)
    if isinstance(value, dict):
        return {k: _to_jsonable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def _serialize_candidates(candidates: list[Candidate]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for c in candidates:
        rows.append(
            {
                "id": c.get("id"),
                "field": c.get("field"),
                "value": _to_jsonable(c.get("value")),
                "value_raw": c.get("value_raw"),
                "quote": c.get("quote"),
                "file": c.get("file"),
                "offset": c.get("offset"),
                "section": c.get("section"),
                "confidence_hint": c.get("confidence_hint"),
                "signals": c.get("signals"),
            }
        )
    return rows


def _quote_has_anchor(field: str, quote: str) -> bool:
    if not quote:
        return False
    lowered = quote.lower()
    anchors = {
        "nmck": ["нмцк", "начальная (максимальная) цена", "цена контракта", "цена договора"],
        "payment_terms": ["оплат", "расчет", "платеж", "аванс", "предоплат", "приемк"],
        "execution_days": ["срок", "поставк", "исполн", "оказани", "дн"],
        "penalties": ["пеня", "неустойк", "штраф", "1/300", "ключевой ставк", "1042"],
    }
    return any(anchor in lowered for anchor in anchors.get(field, []))


def _normalize_decision(field: str, candidates: list[Candidate], data: dict[str, Any], source: str) -> dict[str, Any]:
    ids = {item.get("id") for item in candidates}
    selected_id = data.get("selected_id")
    confidence = data.get("confidence", 0.0)
    notes = str(data.get("notes") or source)

    if selected_id not in ids:
        return _empty_result(f"{source}:invalid_selected_id")

    selected = next((item for item in candidates if item.get("id") == selected_id), None)
    if selected is None:
        return _empty_result(f"{source}:id_not_found")

    must_quote_match = bool(data.get("must_quote_match", True))
    if must_quote_match and not _quote_has_anchor(field, str(selected.get("quote") or "")):
        return _empty_result(f"{source}:quote_anchor_mismatch")

    try:
        confidence_value = float(confidence)
    except Exception:
        confidence_value = 0.0

    return {
        "selected_id": selected_id,
        "confidence": max(0.0, min(1.0, confidence_value)),
        "notes": notes,
        "must_quote_match": must_quote_match,
    }


def _build_prompt(field: str, candidates: list[Candidate]) -> str:
    serialized = _serialize_candidates(candidates)
    return (
        "Select the best candidate for the field using ONLY candidate JSON below.\n"
        "Rules:\n"
        "1) You must return strict JSON object only.\n"
        "2) selected_id must be one of provided ids or null.\n"
        "3) Choose null if evidence is weak or conflicting.\n"
        "4) Candidate quote must contain field anchor.\n"
        "Output schema:\n"
        '{"selected_id": "id_or_null", "confidence": 0.0, "notes": "short", "must_quote_match": true}\n\n'
        f"field={field}\n"
        f"candidates={json.dumps(serialized, ensure_ascii=False)}"
    )


def _ssl_context() -> ssl.SSLContext | None:
    ca_bundle = os.getenv("GIGACHAT_CA_BUNDLE")
    if not ca_bundle:
        return None
    try:
        return ssl.create_default_context(cafile=ca_bundle)
    except Exception:
        return None


def _http_post_json(url: str, headers: dict[str, str], payload: dict[str, Any]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, context=_ssl_context(), timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
        return json.loads(text) if text else {}


def _http_post_form(url: str, headers: dict[str, str], payload: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, context=_ssl_context(), timeout=30) as response:
        text = response.read().decode("utf-8", errors="replace")
        return json.loads(text) if text else {}


def _get_gigachat_token() -> str | None:
    direct = os.getenv("GIGACHAT_ACCESS_TOKEN")
    if direct:
        return direct.strip()

    auth_key = os.getenv("GIGACHAT_AUTH_KEY") or os.getenv("GIGACHAT_AUTH_HEADER")
    if not auth_key:
        return None

    auth_header = auth_key.strip()
    if not auth_header.lower().startswith("basic "):
        auth_header = f"Basic {auth_header}"

    auth_url = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
    scope = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": auth_header,
    }
    try:
        data = _http_post_form(auth_url, headers, {"scope": scope})
        token = data.get("access_token")
        return str(token).strip() if token else None
    except Exception:
        return None


def _verify_with_gigachat(field: str, candidates: list[Candidate]) -> dict[str, Any] | None:
    token = _get_gigachat_token()
    if not token:
        return None

    api_url = os.getenv("GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
    model = os.getenv("GIGACHAT_MODEL", "GigaChat")
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "model": model,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": _build_prompt(field, candidates)},
        ],
    }
    try:
        data = _http_post_json(api_url, headers, payload)
        choices = data.get("choices") or []
        if not choices:
            return None
        content = ((choices[0].get("message") or {}).get("content") or "").strip()
        return _json_load_loose(content)
    except Exception:
        return None


def _extract_gemini_text(response: Any) -> str:
    text = getattr(response, "text", None)
    if isinstance(text, str) and text.strip():
        return text
    try:
        candidates = getattr(response, "candidates", None) or []
        if candidates:
            content = getattr(candidates[0], "content", None)
            parts = getattr(content, "parts", None) if content is not None else None
            if parts:
                first = parts[0]
                part_text = getattr(first, "text", None)
                if isinstance(part_text, str):
                    return part_text
    except Exception:
        return ""
    return ""


def _verify_with_gemini(field: str, candidates: list[Candidate]) -> dict[str, Any] | None:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        return None
    model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
    try:
        from google import genai
    except Exception:
        return None

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=model,
            contents=_build_prompt(field, candidates),
        )
        text = _extract_gemini_text(response)
        return _json_load_loose(text)
    except Exception:
        return None


def verify_and_select(field: str, candidates: list[Candidate]) -> dict[str, Any]:
    if not candidates:
        return _empty_result("no_candidates")

    giga_data = _verify_with_gigachat(field, candidates)
    if isinstance(giga_data, dict) and giga_data:
        return _normalize_decision(field, candidates, giga_data, "gigachat")

    gemini_data = _verify_with_gemini(field, candidates)
    if isinstance(gemini_data, dict) and gemini_data:
        return _normalize_decision(field, candidates, gemini_data, "gemini")

    return _empty_result("llm_failed")
