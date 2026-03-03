from __future__ import annotations

import json
import os
import re
import ssl
import urllib.parse
import urllib.request
import uuid
from typing import Any

from services.extraction_v3.parsers import parse_days, parse_money, parse_percent

try:
    from google import genai
except Exception:  # pragma: no cover - optional dependency
    genai = None


GIGACHAT_AUTH_URL = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_API_URL = os.getenv("GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")


def _extract_json_dict(text: str) -> dict[str, Any] | None:
    if not text:
        return None
    payload = text.strip()
    if payload.startswith("{") and payload.endswith("}"):
        try:
            parsed = json.loads(payload)
            return parsed if isinstance(parsed, dict) else None
        except Exception:
            pass

    match = re.search(r"\{[\s\S]*\}", payload)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception:
        return None


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
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, context=_ssl_context(), timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = _extract_json_dict(raw)
    return parsed or {}


def _http_post_form(url: str, headers: dict[str, str], payload: dict[str, str]) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=urllib.parse.urlencode(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, context=_ssl_context(), timeout=30) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = _extract_json_dict(raw)
    return parsed or {}


def _get_gigachat_access_token() -> str | None:
    direct_token = (os.getenv("GIGACHAT_ACCESS_TOKEN") or "").strip()
    if direct_token:
        return direct_token

    auth_key = (os.getenv("GIGACHAT_AUTH_KEY") or os.getenv("GIGACHAT_AUTH_HEADER") or "").strip()
    if not auth_key:
        return None

    auth_header = auth_key if auth_key.lower().startswith("basic ") else f"Basic {auth_key}"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": str(uuid.uuid4()),
        "Authorization": auth_header,
    }
    payload = {"scope": GIGACHAT_SCOPE}
    response = _http_post_form(GIGACHAT_AUTH_URL, headers, payload)
    token = response.get("access_token")
    return str(token).strip() if token else None


def _rank_prompt(field: str, candidates: list[dict[str, Any]]) -> str:
    payload = json.dumps(candidates, ensure_ascii=False, sort_keys=True)
    return (
        "Ты ранжируешь кандидатов извлечения. Используй ТОЛЬКО JSON кандидатов.\n"
        "Запрещено придумывать факты.\n"
        "Выбери только один id из списка или null.\n"
        "Опирайся только на quote и signals.\n"
        "Ответ строго JSON без markdown:\n"
        '{"selected_id":"<id>|null","confidence":0.0,"reason":"short","must_have_quote":true}\n'
        f"field={field}\n"
        f"candidates={payload}"
    )


def _repair_prompt(field: str, snippets: list[dict[str, Any]], current_value: Any) -> str:
    payload = json.dumps(snippets, ensure_ascii=False, sort_keys=True)
    current = json.dumps(current_value, ensure_ascii=False, sort_keys=True)
    return (
        "Исправь значение поля по фрагментам. Используй только snippets.\n"
        "Если данных нет, верни null.\n"
        "Ответ строго JSON без markdown:\n"
        '{"value":null}\n'
        f"field={field}\n"
        f"current_value={current}\n"
        f"snippets={payload}"
    )


def _call_gigachat_json(prompt: str) -> dict[str, Any] | None:
    token = _get_gigachat_access_token()
    if not token:
        return None

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }
    payload = {
        "model": GIGACHAT_MODEL,
        "temperature": 0,
        "messages": [
            {"role": "system", "content": "Return strict JSON only."},
            {"role": "user", "content": prompt},
        ],
    }

    response = _http_post_json(GIGACHAT_API_URL, headers, payload)
    choices = response.get("choices") or []
    if not choices:
        return None
    message = (choices[0].get("message") or {}).get("content") or ""
    return _extract_json_dict(message)


def _call_gemini_json(prompt: str) -> dict[str, Any] | None:
    if genai is None:
        return None
    api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if not api_key:
        return None

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
            config={
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        )
    except Exception:
        return None

    text = getattr(response, "text", None)
    if not text and hasattr(response, "candidates"):
        chunks: list[str] = []
        for candidate in getattr(response, "candidates", []) or []:
            content = getattr(candidate, "content", None)
            if not content:
                continue
            for part in getattr(content, "parts", []) or []:
                maybe_text = getattr(part, "text", None)
                if maybe_text:
                    chunks.append(maybe_text)
        text = "\n".join(chunks)
    return _extract_json_dict(text or "")


def _deterministic_rank(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    if not candidates:
        return {
            "selected_id": None,
            "confidence": 0.0,
            "reason": "no_candidates",
            "must_have_quote": True,
        }
    ordered = sorted(
        candidates,
        key=lambda item: (
            -float(item.get("confidence_hint") or 0.0),
            int(item.get("offset") or 0),
            str(item.get("id") or ""),
        ),
    )
    selected = next((item for item in ordered if item.get("quote")), ordered[0])
    return {
        "selected_id": selected.get("id"),
        "confidence": float(selected.get("confidence_hint") or 0.0),
        "reason": "deterministic_fallback",
        "must_have_quote": True,
    }


def _validate_rank_output(raw: dict[str, Any] | None, candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    if not isinstance(raw, dict):
        return None

    ids = {str(item.get("id")) for item in candidates}
    selected_id = raw.get("selected_id")
    if selected_id is not None:
        selected_id = str(selected_id)
        if selected_id not in ids:
            return None

    confidence = raw.get("confidence", 0.0)
    try:
        confidence = max(0.0, min(1.0, float(confidence)))
    except Exception:
        confidence = 0.0

    reason = str(raw.get("reason") or "ok")[:200]
    must_have_quote = bool(raw.get("must_have_quote", True))

    if selected_id:
        selected = next((item for item in candidates if str(item.get("id")) == selected_id), None)
        if must_have_quote and (not selected or not selected.get("quote")):
            return None

    return {
        "selected_id": selected_id,
        "confidence": confidence,
        "reason": reason,
        "must_have_quote": must_have_quote,
    }


def rank_candidates(field: str, candidates: list[dict[str, Any]]) -> dict[str, Any]:
    deterministic = _deterministic_rank(candidates)
    if not candidates:
        return deterministic

    prompt = _rank_prompt(field, candidates)
    for provider_call in (_call_gigachat_json, _call_gemini_json):
        try:
            raw = provider_call(prompt)
            validated = _validate_rank_output(raw, candidates)
            if validated is not None:
                return validated
        except Exception:
            continue
    return deterministic


def _repair_parse(field: str, raw_value: Any) -> Any:
    if raw_value is None:
        return None
    if field == "nmck":
        if isinstance(raw_value, (int, float)):
            return float(raw_value)
        return parse_money(str(raw_value))
    if field == "payment_terms":
        if isinstance(raw_value, dict):
            days = raw_value.get("conservative_days")
            if isinstance(days, (int, float)):
                return {"conservative_days": int(round(float(days)))}
        if isinstance(raw_value, (int, float)):
            return {"conservative_days": int(round(float(raw_value)))}
        days, day_type = parse_days(str(raw_value))
        if days is None:
            return None
        return {
            "conservative_days": int(days * 1.4) if day_type == "working" else days,
        }
    if field == "execution":
        if isinstance(raw_value, (int, float)):
            return int(round(float(raw_value)))
        days, day_type = parse_days(str(raw_value))
        if days is None:
            return None
        return int(days * 1.4) if day_type == "working" else days
    if field == "penalties":
        if isinstance(raw_value, dict):
            pct = raw_value.get("penalty_percent_per_day")
            if isinstance(pct, (int, float)):
                return {"penalty_percent_per_day": float(pct)}
        return {
            "penalty_percent_per_day": parse_percent(str(raw_value)),
        }
    return raw_value


def _heuristic_repair(field: str, snippets: list[dict[str, Any]]) -> Any:
    for snippet in snippets:
        text = str(snippet.get("snippet") or "")
        if not text:
            continue
        parsed = _repair_parse(field, text)
        if parsed:
            return parsed
    return None


def repair_field(field: str, snippets: list[dict[str, Any]], current_value: Any) -> Any | None:
    if not snippets:
        return None

    prompt = _repair_prompt(field, snippets, current_value)
    for provider_call in (_call_gigachat_json, _call_gemini_json):
        try:
            raw = provider_call(prompt)
            if not isinstance(raw, dict):
                continue
            repaired = _repair_parse(field, raw.get("value"))
            if repaired is not None:
                return repaired
        except Exception:
            continue

    return _heuristic_repair(field, snippets)
