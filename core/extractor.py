import re
import json
import math
import os
import logging
import ssl
import time
import uuid
import urllib.request
import urllib.parse
from datetime import datetime
from typing import Any, Optional
try:
    import google.generativeai as genai
except Exception:
    genai = None
from dotenv import load_dotenv
from services.extraction.candidates import mine_all_candidates
from services.extraction.normalize import normalize_text
from services.extraction.quality import validate_extracted_data as validate_quality_data
from services.extraction.retrieval import retrieve_sections
from services.extraction.retrieval_snippets import build_llm_context_with_meta
from services.extraction.select import apply_selected_to_extracted_data, select_best_candidate

load_dotenv()
logger = logging.getLogger(__name__)

# ---------- helpers ----------

def _has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE | re.MULTILINE) for p in patterns)

def _normalize_extraction_text(text: str) -> str:
    if not text:
        return ""
    return (
        text
        .replace("\u00a0", " ")
        .replace("\u202f", " ")
        .replace("\u2013", "-")
        .replace("\u2014", "-")
    )

def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = _normalize_extraction_text(v.strip())
        s = re.sub(r"(?iu)\b(?:\u0440\u0443\u0431(?:\.|\u043b\u044f|\u043b\u0435\u0439)?|rur|rub)\b", "", s)
        s = s.replace("\u20bd", "")
        s = s.replace(" ", "").replace(",", ".")
        # СѓР±РµСЂС‘Рј РІСЃС‘ РєСЂРѕРјРµ С†РёС„СЂ Рё С‚РѕС‡РєРё
        s = re.sub(r"[^0-9.\-]", "", s)
        if not s:
            return None
        try:
            return float(s)
        except:
            return None
    return None

def _safe_int(v: Any) -> Optional[int]:
    f = _safe_float(v)
    if f is None:
        return None
    try:
        return int(round(f))
    except:
        return None

def _safe_bool(v: Any) -> bool:
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        return v.strip().lower() in ("true", "1", "yes", "РґР°", "РёСЃС‚РёРЅР°")
    return False

def _extract_json_from_text(s: str) -> dict:
    """
    РњРѕРґРµР»Рё РёРЅРѕРіРґР° РІРѕР·РІСЂР°С‰Р°СЋС‚ JSON + РјСѓСЃРѕСЂ. Р’С‹СЂРµР¶РµРј РїРµСЂРІС‹Р№ {...}.
    """
    if not s:
        return {}
    s = s.strip()
    if s.startswith("{") and s.endswith("}"):
        try:
            return json.loads(s)
        except:
            pass

    m = re.search(r"\{[\s\S]*\}", s)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except:
        return {}


_FILE_MARKER_RE = re.compile(
    r"^===== FILE\s+\d+/\d+:\s*(.+?)\s*=====$",
    flags=re.MULTILINE,
)


def _parse_file_markers(text: str) -> list[tuple[int, str]]:
    markers: list[tuple[int, str]] = []
    for match in _FILE_MARKER_RE.finditer(text):
        name = (match.group(1) or "").strip()
        markers.append((match.start(), name))
    return markers


def _file_for_offset(markers: list[tuple[int, str]], offset: int) -> str | None:
    if not markers:
        return None
    current = None
    for pos, name in markers:
        if pos <= offset:
            current = name
        else:
            break
    return current


def _build_quote(text: str, start: int, end: int, radius: int = 180, max_len: int = 400) -> str:
    if start < 0 or end < 0 or start >= len(text):
        return ""
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    quote = text[left:right].strip()
    if len(quote) <= max_len:
        return quote

    span = max(1, end - start)
    half = max(0, (max_len - span) // 2)
    left = max(0, start - half)
    right = min(len(text), end + half)
    return text[left:right].strip()


def _make_evidence(
    *,
    field: str,
    quote: str,
    offset: int | None,
    file_name: str | None,
    source: str,
) -> dict:
    location: dict[str, Any] = {}
    if file_name:
        location["file"] = file_name
    if offset is not None:
        location["offset"] = offset
    return {
        "field": field,
        "quote": quote,
        "location": location,
        "source": source,
    }


def _merge_non_empty(current: Any, new: Any) -> Any:
    if new is None:
        return current
    if isinstance(new, str) and not new.strip():
        return current
    return new


KW_NMCK = [
    "\u041d\u041c\u0426\u041a",
    "\u043d\u0430\u0447\u0430\u043b\u044c\u043d",
    "\u0446\u0435\u043d\u0430 \u0434\u043e\u0433\u043e\u0432\u043e\u0440\u0430",
    "\u0446\u0435\u043d\u0430 \u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442\u0430",
]
KW_PAYMENT = [
    "\u043e\u043f\u043b\u0430\u0442",
    "\u0440\u0430\u0441\u0447\u0435\u0442",
    "\u043f\u043b\u0430\u0442\u0435\u0436",
    "\u0430\u0432\u0430\u043d\u0441",
    "\u043f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442",
    "\u043e\u043a\u043e\u043d\u0447\u0430\u0442\u0435\u043b\u044c\u043d",
]
KW_EXECUTION = [
    "\u0441\u0440\u043e\u043a",
    "\u043f\u043e\u0441\u0442\u0430\u0432",
    "\u043e\u0442\u0433\u0440\u0443\u0437",
    "\u0438\u0441\u043f\u043e\u043b\u043d",
    "\u0437\u0430\u0432\u0435\u0440\u0448",
    "\u043e\u043a\u0430\u0437\u0430\u043d",
]
KW_PENALTY = [
    "\u043f\u0435\u043d\u044f",
    "\u043d\u0435\u0443\u0441\u0442\u043e\u0439\u043a",
    "\u0448\u0442\u0440\u0430\u0444",
]
KW_FINE = ["\u0448\u0442\u0440\u0430\u0444"]
KW_ADVANCE = [
    "\u0430\u0432\u0430\u043d\u0441",
    "\u043f\u0440\u0435\u0434\u043e\u043f\u043b\u0430\u0442",
]
KW_VAGUE = [
    "\u043f\u043e \u0443\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u0438\u044e \u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a\u0430",
    "\u043f\u043e \u0443\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u0438\u044e",
    "\u043d\u0430 \u0443\u0441\u043c\u043e\u0442\u0440\u0435\u043d\u0438\u0435 \u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a\u0430",
    "\u0432\u043f\u0440\u0430\u0432\u0435 \u043e\u0442\u043a\u0430\u0437\u0430\u0442\u044c",
]
KW_BID_SECURITY = [
    "\u043e\u0431\u0435\u0441\u043f\u0435\u0447",
    "\u0437\u0430\u044f\u0432\u043a",
]
KW_CONTRACT_SECURITY = [
    "\u043e\u0431\u0435\u0441\u043f\u0435\u0447",
    "\u043a\u043e\u043d\u0442\u0440\u0430\u043a\u0442",
]

# ---------- Gemini setup ----------

MODEL_NAME = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")
_MODEL: Any | None = None
_MODEL_INIT_FAILED = False


def _get_model() -> Any | None:
    global _MODEL
    global _MODEL_INIT_FAILED

    if _MODEL is not None:
        return _MODEL
    if _MODEL_INIT_FAILED:
        return None
    if genai is None:
        _MODEL_INIT_FAILED = True
        logger.warning("google.generativeai is not installed. Gemini extraction disabled.")
        return None

    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        _MODEL_INIT_FAILED = True
        logger.warning("GEMINI_API_KEY is missing. Using regex-only extraction fallback.")
        return None

    try:
        genai.configure(api_key=api_key)
        _MODEL = genai.GenerativeModel(MODEL_NAME)
        return _MODEL
    except Exception:
        _MODEL_INIT_FAILED = True
        logger.exception("Failed to initialize Gemini model. Using regex-only extraction fallback.")
        return None

# ---------- GigaChat setup ----------

GIGACHAT_AUTH_URL = os.getenv("GIGACHAT_AUTH_URL", "https://ngw.devices.sberbank.ru:9443/api/v2/oauth")
GIGACHAT_API_URL = os.getenv("GIGACHAT_API_URL", "https://gigachat.devices.sberbank.ru/api/v1/chat/completions")
GIGACHAT_MODEL = os.getenv("GIGACHAT_MODEL", "GigaChat")
GIGACHAT_SCOPE = os.getenv("GIGACHAT_SCOPE", "GIGACHAT_API_PERS")

_GIGACHAT_TOKEN: str | None = None
_GIGACHAT_TOKEN_EXPIRES_AT: float | None = None


def _ssl_context() -> ssl.SSLContext | None:
    ca_bundle = os.getenv("GIGACHAT_CA_BUNDLE")
    if not ca_bundle:
        return None
    try:
        return ssl.create_default_context(cafile=ca_bundle)
    except Exception:
        logger.exception("Failed to load GigaChat CA bundle. Falling back to default SSL context.")
        return None


def _http_post_json(url: str, headers: dict[str, str], payload: dict) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _http_post_form(url: str, headers: dict[str, str], data: dict[str, str]) -> dict:
    body = urllib.parse.urlencode(data).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    with urllib.request.urlopen(req, context=_ssl_context(), timeout=30) as resp:
        raw = resp.read().decode("utf-8", errors="replace")
        return json.loads(raw) if raw else {}


def _get_gigachat_access_token() -> str | None:
    global _GIGACHAT_TOKEN
    global _GIGACHAT_TOKEN_EXPIRES_AT

    direct_token = os.getenv("GIGACHAT_ACCESS_TOKEN")
    if direct_token:
        return direct_token.strip()

    if _GIGACHAT_TOKEN and _GIGACHAT_TOKEN_EXPIRES_AT:
        if _GIGACHAT_TOKEN_EXPIRES_AT - time.time() > 60:
            return _GIGACHAT_TOKEN

    auth_key = os.getenv("GIGACHAT_AUTH_KEY") or os.getenv("GIGACHAT_AUTH_HEADER")
    if not auth_key:
        logger.warning("GIGACHAT_AUTH_KEY/GIGACHAT_AUTH_HEADER or GIGACHAT_ACCESS_TOKEN is missing. GigaChat extraction disabled.")
        return None

    auth_header = auth_key.strip()
    if not auth_header.lower().startswith("basic "):
        auth_header = f"Basic {auth_header}"

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
        "RqUID": os.getenv("GIGACHAT_RQUID") or str(uuid.uuid4()),
        "Authorization": auth_header,
    }

    try:
        data = _http_post_form(GIGACHAT_AUTH_URL, headers, {"scope": GIGACHAT_SCOPE})
        token = data.get("access_token")
        expires_at = data.get("expires_at")
        if token:
            _GIGACHAT_TOKEN = token
            if isinstance(expires_at, (int, float)):
                if expires_at > 10_000_000_000:
                    expires_at = expires_at / 1000.0
                _GIGACHAT_TOKEN_EXPIRES_AT = float(expires_at)
            return token
    except Exception:
        logger.exception("Failed to obtain GigaChat access token.")
        return None

    logger.warning("GigaChat token response did not contain access_token.")
    return None

EXTRACTION_PROMPT = """
Extract tender data from the text. Return STRICT JSON only:

{
  "nmck": number | null,
  "currency": "RUB" | "USD" | "EUR" | null,

  "execution_days": number | null,
  "payment_terms_days": number | null,

  "bid_security_percent": number | null,
  "contract_security_percent": number | null,

  "advance_percent": number | null,
  "penalty_percent_per_day": number | null,
  "fine_percent": number | null,

  "has_vague_acceptance_terms": boolean
}

Rules:
- If unknown, return null.
- Percent values must be numbers (e.g., 5 means 5%).
- has_vague_acceptance_terms = true if acceptance terms are vague / subjective.

Text:
"""

BASE_SCHEMA = {
    "nmck": None,
    "currency": None,
    "execution_days": None,
    "payment_terms_days": None,
    "bid_security_percent": None,
    "contract_security_percent": None,
    "advance_percent": None,
    "penalty_percent_per_day": None,
    "fine_percent": None,
    "has_vague_acceptance_terms": False,

    # NEW: tender traps
    "payment_after_full_delivery": False,
    "delivery_by_customer_requests": False,
    "supplier_must_hold_stock": False,
}


def _normalize_provider(value: str | None) -> str:
    if not value:
        return "auto"
    value = value.strip().lower()
    if value in ("gemini", "google"):
        return "gemini"
    if value in ("gigachat", "giga"):
        return "gigachat"
    if value in ("auto", "default"):
        return "auto"
    return "auto"


def _extract_with_gemini(prompt_text: str) -> dict:
    model = _get_model()
    if model is None:
        return {}

    for _ in range(2):
        try:
            response = model.generate_content(
                EXTRACTION_PROMPT + "\n\n" + prompt_text,
                generation_config={
                    "temperature": 0,
                    "response_mime_type": "application/json",
                },
            )
            parsed = _extract_json_from_text(getattr(response, "text", "") or "")
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            logger.exception("Gemini extraction failed. Retrying with fallback logic.")

    return {}


def _extract_with_gigachat(prompt_text: str) -> dict:
    token = _get_gigachat_access_token()
    if not token:
        return {}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    payload = {
        "model": GIGACHAT_MODEL,
        "messages": [
            {"role": "system", "content": EXTRACTION_PROMPT.strip()},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0,
    }

    try:
        data = _http_post_json(GIGACHAT_API_URL, headers, payload)
        choices = data.get("choices") or []
        if not choices:
            logger.warning("GigaChat response has no choices.")
            return {}
        message = (choices[0].get("message") or {})
        content = message.get("content") or ""
        parsed = _extract_json_from_text(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        logger.exception("GigaChat extraction failed.")

    return {}


def _get_int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if not raw:
        return default
    try:
        return int(raw)
    except Exception:
        return default


def _iter_chunks(text: str, chunk_size: int, overlap: int, max_chunks: int) -> list[tuple[int, int, str]]:
    if chunk_size <= 0:
        return [(0, len(text), text)]

    overlap = max(0, min(overlap, chunk_size - 1))
    max_chunks = max(1, max_chunks)

    chunks: list[tuple[int, int, str]] = []
    start = 0
    text_len = len(text)
    while start < text_len and len(chunks) < max_chunks:
        end = min(start + chunk_size, text_len)
        chunks.append((start, end, text[start:end]))
        if end >= text_len:
            break
        start = end - overlap
    return chunks


def _build_number_pattern(value: float | int) -> str:
    try:
        fval = float(value)
    except Exception:
        fval = 0.0

    if abs(fval - int(fval)) > 0.0001:
        s = str(fval).replace(".", "[.,]")
        return r"\b" + s + r"\b"

    s = str(int(round(fval)))
    parts = list(s)
    return r"\b" + r"[\s\u00A0.,]*".join(parts) + r"\b"


def _value_near_keywords(text: str, value: float | int, keywords: list[str], window: int = 140) -> bool:
    if not keywords:
        return False
    pattern = _build_number_pattern(value)
    for m in re.finditer(pattern, text):
        left = max(0, m.start() - window)
        right = min(len(text), m.end() + window)
        snippet = text[left:right].lower()
        if any(kw in snippet for kw in keywords):
            return True
    return False


def _score_numeric_candidate(field: str, value: float | int, text: str, count: int) -> float:
    score = 0.0
    score += min(0.6, 0.2 * count)

    if field == "payment_terms_days":
        if 0 <= value <= 365:
            score += 0.2
        if _value_near_keywords(text, value, KW_PAYMENT):
            score += 0.2
    elif field == "execution_days":
        if 1 <= value <= 5000:
            score += 0.2
        if _value_near_keywords(text, value, KW_EXECUTION):
            score += 0.2
    elif field == "nmck":
        if 1_000 <= value <= 10_000_000_000:
            score += 0.2
        if _value_near_keywords(text, value, KW_NMCK):
            score += 0.2
    elif field in ("penalty_percent_per_day", "fine_percent", "advance_percent"):
        if 0 <= value <= 100:
            score += 0.2
        if _value_near_keywords(text, value, KW_PENALTY + KW_ADVANCE):
            score += 0.2

    return score


def _choose_numeric_value(field: str, values: list[float | int], text: str) -> float | int | None:
    if not values:
        return None

    counts: dict[float | int, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1

    best_value = None
    best_score = -1.0
    for value, count in counts.items():
        score = _score_numeric_candidate(field, value, text, count)
        if score > best_score:
            best_score = score
            best_value = value
        elif score == best_score and best_value is not None:
            if field == "payment_terms_days":
                if value > best_value:
                    best_value = value
            elif field == "execution_days":
                if value < best_value:
                    best_value = value
            elif field in ("penalty_percent_per_day", "fine_percent"):
                if value > best_value:
                    best_value = value
            elif field == "nmck":
                if value > best_value:
                    best_value = value

    return best_value


def _choose_currency(values: list[str]) -> str | None:
    if not values:
        return None
    counts: dict[str, int] = {}
    for v in values:
        counts[v] = counts.get(v, 0) + 1
    return sorted(counts.items(), key=lambda x: (-x[1], x[0]))[0][0]


def _choose_bool(values: list[bool], text: str, keywords: list[str]) -> bool | None:
    if not values:
        return None
    if any(values):
        if keywords and any(kw in text.lower() for kw in keywords):
            return True
        return values[0]
    return False


def _merge_llm_results(results: list[dict], text: str) -> dict:
    numeric_fields = [
        "nmck",
        "execution_days",
        "payment_terms_days",
        "bid_security_percent",
        "contract_security_percent",
        "advance_percent",
        "penalty_percent_per_day",
        "fine_percent",
    ]
    bool_fields = ["has_vague_acceptance_terms"]

    collected: dict[str, list[Any]] = {f: [] for f in numeric_fields + bool_fields + ["currency"]}

    for result in results:
        if not isinstance(result, dict):
            continue

        if "currency" in result and result.get("currency") in ("RUB", "USD", "EUR"):
            collected["currency"].append(result.get("currency"))

        for field in numeric_fields:
            if field not in result:
                continue
            if field in ("execution_days", "payment_terms_days"):
                value = _safe_int(result.get(field))
            else:
                value = _safe_float(result.get(field))
            if value is not None:
                collected[field].append(value)

        for field in bool_fields:
            if field in result:
                collected[field].append(_safe_bool(result.get(field)))

    merged: dict[str, Any] = {}
    merged["currency"] = _choose_currency(collected["currency"])

    for field in numeric_fields:
        merged[field] = _choose_numeric_value(field, collected[field], text)

    merged["has_vague_acceptance_terms"] = _choose_bool(
        collected["has_vague_acceptance_terms"],
        text,
        KW_VAGUE,
    )

    return merged


def _extract_with_provider(provider: str, prompt_text: str) -> dict:
    if provider == "gigachat":
        return _extract_with_gigachat(prompt_text)
    if provider == "gemini":
        return _extract_with_gemini(prompt_text)

    # auto: try GigaChat first, then Gemini
    result = _extract_with_gigachat(prompt_text)
    if result:
        return result

    logger.warning("LLM fallback gigachat -> gemini")
    return _extract_with_gemini(prompt_text)


def extract_with_llm(
    text: str,
    provider_override: str | None = None,
    meta_out: dict[str, Any] | None = None,
) -> dict:
    raw_text = text or ""
    if not raw_text.strip():
        return {}

    provider = _normalize_provider(provider_override or os.getenv("LLM_PROVIDER"))
    context_cap = _get_int_env("LLM_CONTEXT_CAP", 20_000)
    retrieval_window = _get_int_env("LLM_RETRIEVAL_WINDOW", 900)
    retrieval_max_snippets = _get_int_env("LLM_RETRIEVAL_SNIPPETS", 10)
    llm_context, llm_context_meta = build_llm_context_with_meta(
        raw_text,
        total_cap=context_cap,
        window=retrieval_window,
        max_snippets_per_section=retrieval_max_snippets,
    )

    section_counts = (llm_context_meta.get("section_counts") or {})
    retrieval_counts = {
        "price_snippets": int(section_counts.get("price", 0)),
        "payment_snippets": int(section_counts.get("payment", 0)),
        "liability_snippets": int(section_counts.get("liability", 0)),
        "execution_snippets": int(section_counts.get("execution", 0)),
    }
    if isinstance(meta_out, dict):
        meta_out["retrieval"] = retrieval_counts

    if llm_context.strip():
        llm_input = llm_context[:context_cap]
        logger.info(
            "llm.context.built",
            extra={
                "text_chars": len(raw_text),
                "context_chars": len(llm_input),
                "context_cap": context_cap,
                **retrieval_counts,
            },
        )
        result = _extract_with_provider(provider, llm_input)
        if not result:
            return {}
        return _merge_llm_results([result], raw_text)

    fallback_cap = _get_int_env("LLM_FALLBACK_TEXT_CAP", 12_000)
    fallback_text = raw_text[: max(1_000, fallback_cap)]
    logger.warning(
        "llm.context.empty_fallback",
        extra={
            "text_chars": len(raw_text),
            "fallback_chars": len(fallback_text),
            "fallback_cap": fallback_cap,
        },
    )

    chunk_size = min(_get_int_env("LLM_CHUNK_SIZE", 15_000), len(fallback_text))
    overlap = min(_get_int_env("LLM_CHUNK_OVERLAP", 1_500), max(0, chunk_size - 1))
    max_chunks = _get_int_env("LLM_MAX_CHUNKS", 8)

    if len(fallback_text) <= chunk_size:
        result = _extract_with_provider(provider, fallback_text)
        if not result:
            return {}
        return _merge_llm_results([result], fallback_text)

    chunks = _iter_chunks(fallback_text, chunk_size, overlap, max_chunks)
    if chunks:
        logger.info(
            "llm.chunking",
            extra={
                "text_chars": len(fallback_text),
                "chunk_size": chunk_size,
                "overlap": overlap,
                "max_chunks": max_chunks,
                "mode": "fallback",
            },
        )

    results: list[dict] = []
    for start, end, chunk in chunks:
        if not chunk.strip():
            continue
        logger.info(
            "llm.chunk.processing",
            extra={"chunk_start": start, "chunk_end": end, "chunk_chars": len(chunk)},
        )
        result = _extract_with_provider(provider, chunk)
        if result:
            results.append(result)

    return _merge_llm_results(results, fallback_text)


def _call_llm_gigachat(system_prompt: str, user_prompt: str) -> dict:
    token = _get_gigachat_access_token()
    if not token:
        return {}

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {token}",
    }

    payload = {
        "model": GIGACHAT_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }

    try:
        data = _http_post_json(GIGACHAT_API_URL, headers, payload)
        choices = data.get("choices") or []
        if not choices:
            return {}
        message = (choices[0].get("message") or {})
        content = message.get("content") or ""
        parsed = _extract_json_from_text(content)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        logger.exception("LLM repair failed (GigaChat).")
    return {}


def _call_llm_gemini(system_prompt: str, user_prompt: str) -> dict:
    model = _get_model()
    if model is None:
        return {}
    try:
        response = model.generate_content(
            system_prompt + "\n\n" + user_prompt,
            generation_config={
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        )
        parsed = _extract_json_from_text(getattr(response, "text", "") or "")
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        logger.exception("LLM repair failed (Gemini).")
    return {}


def _call_llm_with_fallback(system_prompt: str, user_prompt: str, provider_override: str | None) -> dict:
    provider = _normalize_provider(provider_override or os.getenv("LLM_PROVIDER"))
    if provider == "gigachat":
        return _call_llm_gigachat(system_prompt, user_prompt)
    if provider == "gemini":
        return _call_llm_gemini(system_prompt, user_prompt)

    result = _call_llm_gigachat(system_prompt, user_prompt)
    if result:
        return result

    logger.warning("LLM fallback gigachat -> gemini")
    return _call_llm_gemini(system_prompt, user_prompt)


def _collect_snippets(
    text: str,
    keywords: list[str],
    max_snippets: int = 6,
    window: int = 180,
    max_total_chars: int = 1600,
) -> list[str]:
    if not keywords:
        return []

    markers = _parse_file_markers(text)
    snippets: list[str] = []
    seen: set[str] = set()
    total = 0

    for kw in keywords:
        for m in re.finditer(kw, text, flags=re.IGNORECASE):
            left = max(0, m.start() - window)
            right = min(len(text), m.end() + window)
            snippet = text[left:right].strip()
            if not snippet or snippet in seen:
                continue
            seen.add(snippet)
            file_name = _file_for_offset(markers, m.start())
            if file_name:
                snippet = f"[FILE: {file_name}]\\n{snippet}"
            snippets.append(snippet)
            total += len(snippet)
            if len(snippets) >= max_snippets or total >= max_total_chars:
                return snippets
    return snippets


def _find_value_snippet(text: str, value: float | int, keywords: list[str]) -> tuple[str, dict]:
    pattern = _build_number_pattern(value)
    markers = _parse_file_markers(text)
    for m in re.finditer(pattern, text):
        left = max(0, m.start() - 160)
        right = min(len(text), m.end() + 160)
        snippet = text[left:right].strip()
        if keywords and not any(kw in snippet.lower() for kw in keywords):
            continue
        file_name = _file_for_offset(markers, m.start())
        location = {"file": file_name, "offset": m.start()} if file_name else {"offset": m.start()}
        return snippet, location
    return "", {}


def _find_keyword_evidence(text: str, keywords: list[str]) -> tuple[str, dict]:
    if not keywords:
        return "", {}
    markers = _parse_file_markers(text)
    for kw in keywords:
        m = re.search(kw, text, flags=re.IGNORECASE)
        if not m:
            continue
        quote = _build_quote(text, m.start(), m.end())
        file_name = _file_for_offset(markers, m.start())
        location = {"file": file_name, "offset": m.start()} if file_name else {"offset": m.start()}
        return quote, location
    return "", {}


def _is_value_valid(field: str, value: Any) -> bool:
    if value is None:
        return False
    try:
        if field == "payment_terms_days":
            return 0 < int(value) <= 365
        if field == "execution_days":
            return 0 < int(value) <= 5000
        if field == "penalty_percent_per_day":
            return 0 < float(value) <= 10
        if field == "fine_percent":
            return 0 < float(value) <= 100
        if field in ("advance_percent", "bid_security_percent", "contract_security_percent"):
            return 0 <= float(value) <= 100
        if field == "nmck":
            return 1_000 <= float(value) <= 10_000_000_000
    except Exception:
        return False
    return True


def validate_extracted_data(data: dict) -> list[str]:
    errors: list[str] = []
    if not _is_value_valid("payment_terms_days", data.get("payment_terms_days")):
        errors.append("payment_terms_days missing or out of range")
    if not _is_value_valid("execution_days", data.get("execution_days")):
        errors.append("execution_days missing or out of range")
    if not _is_value_valid("penalty_percent_per_day", data.get("penalty_percent_per_day")):
        errors.append("penalty_percent_per_day missing or out of range")
    return errors


def _repair_with_llm(text: str, data: dict, errors: list[str], provider_override: str | None) -> dict:
    field_keywords = {
        "payment_terms_days": KW_PAYMENT,
        "execution_days": KW_EXECUTION,
        "penalty_percent_per_day": KW_PENALTY + ["%", "\u043f\u0440\u043e\u0446\u0435\u043d\u0442"],
        "fine_percent": KW_FINE + ["%", "\u043f\u0440\u043e\u0446\u0435\u043d\u0442"],
    }

    needed_fields: list[str] = []
    keywords: list[str] = []
    for err in errors:
        for field in field_keywords:
            if field in err:
                needed_fields.append(field)
                keywords.extend(field_keywords[field])

    if not needed_fields:
        return {}

    snippets = _collect_snippets(text, keywords)
    if not snippets:
        return {}

    system_prompt = (
        "You are repairing tender extraction. Use ONLY the snippets provided. "
        "Return STRICT JSON only. Do not invent values."
    )

    schema = ", ".join([f'\"{f}\": number | null' for f in needed_fields])
    user_prompt = (
        f"Extracted JSON so far: {json.dumps(data, ensure_ascii=False)}\\n"
        f"Validation errors: {errors}\\n"
        f"Snippets:\\n{chr(10).join(snippets)}\\n"
        f"Return JSON with fields: {{{schema}}}"
    )

    return _call_llm_with_fallback(system_prompt, user_prompt, provider_override)

# ---------- Regex fallbacks ----------

def _parse_amount(raw: str) -> Optional[float]:
    if not raw:
        return None

    s = _normalize_extraction_text(str(raw))
    s = re.sub(r"(?iu)\b(?:\u0440\u0443\u0431(?:\.|\u043b\u044f|\u043b\u0435\u0439)?|rur|rub)\b", "", s)
    s = s.replace("\u20bd", "")
    s = re.sub(r"[^0-9,.\-\s]", "", s).strip()
    s = re.sub(r"\s+", "", s)
    s = s.strip(".,")
    if not s:
        return None

    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "")
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        if re.search(r",\d{1,2}$", s):
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "." in s:
        if not re.search(r"\.\d{1,2}$", s):
            s = s.replace(".", "")

    if not s or s in {"-", ".", ","}:
        return None
    try:
        return float(s)
    except Exception:
        return None
_WORD_CAL = "РєР°Р»РµРЅРґР°СЂРЅ"
_WORD_WORK = "СЂР°Р±РѕС‡"
_RUB_PATTERN = r"(?:СЂСѓР±\.?|СЂСѓР±(?:Р»РµР№|Р»СЏ)?|в‚Ѕ)"
_DAY_WORDS_PATTERN = r"(?:РґРЅ\w*|СЃСѓС‚Рє\w*|РµР¶РµРґРЅРµРІРЅ\w*)"

_NMCK_KW_PATTERN = rf"(?:{KW_NMCK[0]}|{KW_NMCK[1]}\w*\s+С†РµРЅР°|{KW_NMCK[2]}|{KW_NMCK[3]})"
_PAYMENT_KW_PATTERN = f"(?:{'|'.join(KW_PAYMENT)})"
_EXECUTION_KW_PATTERN = f"(?:{'|'.join(KW_EXECUTION)})"
_PENALTY_KW_PATTERN = f"(?:{'|'.join(KW_PENALTY)})"
_FINE_KW_PATTERN = f"(?:{'|'.join(KW_FINE)})"
_ADVANCE_KW_PATTERN = f"(?:{'|'.join(KW_ADVANCE)})"

_NMCK_PATTERNS = [
    re.compile(
        rf"(?P<kw>{_NMCK_KW_PATTERN})[^\d]{{0,60}}(?P<amount>\d[\d\s\u00A0\u202F.,]*\d)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<amount>\d[\d\s\u00A0\u202F.,]*\d)\s*{_RUB_PATTERN}[^\S\r\n]{{0,8}}(?P<kw>{_NMCK_KW_PATTERN})",
        flags=re.IGNORECASE,
    ),
]

_PAYMENT_PATTERNS = [
    re.compile(
        rf"(?P<kw>{_PAYMENT_KW_PATTERN}\w*)[^\d]{{0,80}}(?P<days>\d{{1,3}})\s*(?:{_WORD_CAL}\w*|{_WORD_WORK}\w*)?\s*РґРЅ",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<days>\d{{1,3}})\s*(?:{_WORD_CAL}\w*|{_WORD_WORK}\w*)?\s*РґРЅ[^\n]{{0,80}}(?P<kw>{_PAYMENT_KW_PATTERN}\w*)",
        flags=re.IGNORECASE,
    ),
]

_EXECUTION_PATTERNS = [
    re.compile(
        rf"(?P<kw>СЃСЂРѕРє\s+(?:РїРѕСЃС‚Р°РІРє\w*|РёСЃРїРѕР»РЅРµРЅ\w*|РѕС‚РіСЂСѓР·Рє\w*|Р·Р°РІРµСЂС€РµРЅ\w*|РѕРєР°Р·Р°РЅ\w*))"
        rf"[^\d]{{0,80}}(?P<days>\d{{1,3}})\s*(?:{_WORD_CAL}\w*|{_WORD_WORK}\w*)?\s*РґРЅ",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<days>\d{{1,3}})\s*(?:{_WORD_CAL}\w*|{_WORD_WORK}\w*)?\s*РґРЅ[^\n]{{0,80}}(?P<kw>{_EXECUTION_KW_PATTERN}\w*)",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"РІ\s+С‚РµС‡РµРЅРёРµ\s+(?P<days>\d{{1,3}})\s*(?:{_WORD_CAL}\w*|{_WORD_WORK}\w*)?\s*РґРЅ",
        flags=re.IGNORECASE,
    ),
]

_DATE_RANGE_RE = re.compile(
    r"(?:СЃ|СЃРѕ)\s*(?P<start>\d{1,2}[./-]\d{1,2}[./-]\d{4})\s*(?:РїРѕ|вЂ“|-|вЂ”)\s*(?P<end>\d{1,2}[./-]\d{1,2}[./-]\d{4})",
    flags=re.IGNORECASE,
)

_PENALTY_PER_DAY_PATTERNS = [
    re.compile(
        rf"(?P<kw>{_PENALTY_KW_PATTERN}\w*)[^\d%]{{0,80}}(?P<pct>\d+(?:[.,]\d+)?)\s*%[^\n]{{0,80}}(?P<day>{_DAY_WORDS_PATTERN})",
        flags=re.IGNORECASE,
    ),
    re.compile(
        rf"(?P<pct>\d+(?:[.,]\d+)?)\s*%[^\n]{{0,80}}(?P<kw>{_PENALTY_KW_PATTERN}\w*)[^\n]{{0,80}}(?P<day>{_DAY_WORDS_PATTERN})",
        flags=re.IGNORECASE,
    ),
]

_PENALTY_CAP_RE = re.compile(
    r"(?:РЅРµ\s+Р±РѕР»РµРµ|РЅРµ\s+РїСЂРµРІС‹С€Р°РµС‚|РЅРµ\s+РјРѕР¶РµС‚\s+РїСЂРµРІС‹С€Р°С‚СЊ)\s*(?P<pct>\d+(?:[.,]\d+)?)\s*%",
    flags=re.IGNORECASE,
)

_FINE_PERCENT_PATTERNS = [
    re.compile(
        rf"(?P<kw>{_FINE_KW_PATTERN}\w*)[^\d%]{{0,80}}(?P<pct>\d+(?:[.,]\d+)?)\s*%",
        flags=re.IGNORECASE,
    ),
]


def _parse_date(value: str) -> datetime | None:
    if not value:
        return None
    value = value.strip().replace('/', '.').replace('-', '.')
    for fmt in ("%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(value, fmt)
        except Exception:
            continue
    return None


def extract_nmck_with_evidence(text: str, markers: list[tuple[int, str]]) -> tuple[int | None, dict | None]:
    candidates: list[tuple[int, float, int, int, str]] = []
    match_count = 0
    first_parse_failed_raw: str | None = None
    for pattern in _NMCK_PATTERNS:
        for match in pattern.finditer(text):
            match_count += 1
            raw = match.group("amount")
            value = _parse_amount(raw)
            if value is None:
                if first_parse_failed_raw is None:
                    first_parse_failed_raw = (raw or "")[:200]
                continue
            quote = _build_quote(text, match.start(), match.end())
            quote_lower = quote.lower()
            score = 0.0
            if "\u043d\u043c\u0446\u043a" in quote_lower:
                score += 0.5
            if "\u0446\u0435\u043d\u0430" in quote_lower:
                score += 0.2
            if "\u0440\u0443\u0431" in quote_lower or "\u20bd" in quote:
                score += 0.1
            candidates.append((int(round(value)), score, match.start(), match.end(), quote))

    if not candidates:
        if match_count == 0:
            logger.info("nmck.regex.no_matches")
        elif first_parse_failed_raw:
            logger.warning("nmck.regex.parse_failed", extra={"raw": first_parse_failed_raw})
        return None, None

    candidates.sort(key=lambda c: (c[1], c[0]), reverse=True)
    value, _, start, end, quote = candidates[0]
    file_name = _file_for_offset(markers, start)
    logger.info(
        "nmck.extracted",
        extra={"value": value, "quote": re.sub(r"\s+", " ", quote)[:250]},
    )
    evidence = _make_evidence(field="nmck", quote=quote, offset=start, file_name=file_name, source="regex")
    return value, evidence


def extract_payment_terms_with_evidence(text: str, markers: list[tuple[int, str]]) -> tuple[int | None, dict | None]:
    candidates: list[tuple[int, float, int, int, str]] = []
    for pattern in _PAYMENT_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group("days")
            days = _safe_int(raw)
            if days is None:
                continue
            quote = _build_quote(text, match.start(), match.end())
            quote_lower = quote.lower()
            if not any(k in quote_lower for k in KW_PAYMENT):
                continue
            score = 0.3
            if "\u043e\u043f\u043b\u0430\u0442" in quote_lower or "\u043f\u043b\u0430\u0442\u0435\u0436" in quote_lower:
                score += 0.4
            if _WORD_CAL in quote_lower:
                score += 0.1
            if _WORD_WORK in quote_lower:
                score += 0.05
            candidates.append((days, score, match.start(), match.end(), quote))

    if not candidates:
        return None, None

    max_days = max(c[0] for c in candidates)
    best = max([c for c in candidates if c[0] == max_days], key=lambda c: c[1])
    days, _, start, end, quote = best
    file_name = _file_for_offset(markers, start)
    evidence = _make_evidence(field="payment_terms_days", quote=quote, offset=start, file_name=file_name, source="regex")
    return days, evidence


def extract_execution_days_with_evidence(text: str, markers: list[tuple[int, str]]) -> tuple[int | None, dict | None]:
    candidates: list[tuple[int, float, int, int, str]] = []

    for pattern in _EXECUTION_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group("days")
            days = _safe_int(raw)
            if days is None:
                continue
            quote = _build_quote(text, match.start(), match.end())
            quote_lower = quote.lower()
            if not any(k in quote_lower for k in KW_EXECUTION):
                continue
            score = 0.3
            if "\u0441\u0440\u043e\u043a" in quote_lower:
                score += 0.4
            if "\u043d\u0435 \u043f\u043e\u0437\u0434\u043d\u0435\u0435" in quote_lower:
                score += 0.2
            if _WORD_CAL in quote_lower or _WORD_WORK in quote_lower:
                score += 0.1
            candidates.append((days, score, match.start(), match.end(), quote))

    for match in _DATE_RANGE_RE.finditer(text):
        start_dt = _parse_date(match.group("start"))
        end_dt = _parse_date(match.group("end"))
        if not start_dt or not end_dt:
            continue
        delta = (end_dt - start_dt).days
        if delta <= 0:
            continue
        quote = _build_quote(text, match.start(), match.end())
        candidates.append((delta, 0.25, match.start(), match.end(), quote))

    if not candidates:
        return None, None

    candidates.sort(key=lambda c: (c[1], -c[0]), reverse=True)
    best_score = candidates[0][1]
    best_pool = [c for c in candidates if c[1] == best_score]
    best = min(best_pool, key=lambda c: c[0])
    days, _, start, end, quote = best
    file_name = _file_for_offset(markers, start)
    evidence = _make_evidence(field="execution_days", quote=quote, offset=start, file_name=file_name, source="regex")
    return days, evidence


def extract_penalties_with_evidence(text: str, markers: list[tuple[int, str]]) -> tuple[dict, dict]:
    result: dict[str, Any] = {}
    evidence: dict[str, dict] = {}

    per_day_candidates: list[tuple[float, float, int, int, str]] = []
    for pattern in _PENALTY_PER_DAY_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group("pct")
            value = _safe_float(raw)
            if value is None:
                continue
            quote = _build_quote(text, match.start(), match.end())
            quote_lower = quote.lower()
            if not any(k in quote_lower for k in KW_PENALTY):
                continue
            score = 0.3
            if "\u043a\u0430\u0436\u0434\u044b\u0439" in quote_lower or "\u0434\u0435\u043d\u044c" in quote_lower or "\u0441\u0443\u0442\u043a" in quote_lower:
                score += 0.2
            per_day_candidates.append((value, score, match.start(), match.end(), quote))

    if per_day_candidates:
        per_day_candidates.sort(key=lambda c: (c[1], c[0]), reverse=True)
        value, _, start, end, quote = per_day_candidates[0]
        result["penalty_percent_per_day"] = value
        file_name = _file_for_offset(markers, start)
        evidence["penalty_percent_per_day"] = _make_evidence(
            field="penalty_percent_per_day",
            quote=quote,
            offset=start,
            file_name=file_name,
            source="regex",
        )

    for match in _PENALTY_CAP_RE.finditer(text):
        raw = match.group("pct")
        value = _safe_float(raw)
        if value is None:
            continue
        quote = _build_quote(text, match.start(), match.end())
        file_name = _file_for_offset(markers, match.start())
        result["penalty_cap_percent"] = value
        evidence["penalty_cap_percent"] = _make_evidence(
            field="penalty_cap_percent",
            quote=quote,
            offset=match.start(),
            file_name=file_name,
            source="regex",
        )
        break

    fine_candidates: list[tuple[float, float, int, int, str]] = []
    for pattern in _FINE_PERCENT_PATTERNS:
        for match in pattern.finditer(text):
            raw = match.group("pct")
            value = _safe_float(raw)
            if value is None:
                continue
            quote = _build_quote(text, match.start(), match.end())
            quote_lower = quote.lower()
            if any(k in quote_lower for k in ("\u0434\u0435\u043d\u044c", "\u0434\u043d", "\u0441\u0443\u0442\u043a", "\u0435\u0436\u0435\u0434\u043d\u0435\u0432\u043d")):
                continue
            score = 0.2
            fine_candidates.append((value, score, match.start(), match.end(), quote))

    if fine_candidates:
        fine_candidates.sort(key=lambda c: (c[1], c[0]), reverse=True)
        value, _, start, end, quote = fine_candidates[0]
        result["fine_percent"] = value
        file_name = _file_for_offset(markers, start)
        evidence["fine_percent"] = _make_evidence(
            field="fine_percent",
            quote=quote,
            offset=start,
            file_name=file_name,
            source="regex",
        )

    return result, evidence


def _is_non_empty(value: Any) -> bool:
    if value is None:
        return False
    if isinstance(value, str):
        return bool(value.strip())
    return True


def _evidence_source_for_field(extracted_data: dict, field: str) -> str:
    evidence = (extracted_data.get("extraction_evidence") or {}).get(field)
    if isinstance(evidence, dict):
        source = evidence.get("source")
        if isinstance(source, str) and source:
            return source
    return "legacy"


def consolidate_extraction(extracted_data: dict) -> dict:
    data = extracted_data or {}
    meta = data.setdefault("meta", {})

    legacy_fields = [
        "nmck",
        "payment_terms_days",
        "execution_days",
        "penalty_percent_per_day",
        "fine_percent",
    ]
    for field in legacy_fields:
        data.setdefault(field, None)

    sources: dict[str, str] = {}
    chosen_values: dict[str, Any] = {}

    payment_meta = meta.get("payment") if isinstance(meta.get("payment"), dict) else {}
    penalties_meta = meta.get("penalties") if isinstance(meta.get("penalties"), dict) else {}

    derived_payment_days: int | None = None
    if _is_non_empty(payment_meta.get("final_days_calendar_alt")):
        try:
            derived_payment_days = int(round(float(payment_meta.get("final_days_calendar_alt"))))
            sources["payment_terms_days"] = "meta"
        except Exception:
            derived_payment_days = None
    elif _is_non_empty(payment_meta.get("final_days_working")):
        try:
            derived_payment_days = int(math.ceil(float(payment_meta.get("final_days_working")) * 1.4))
            sources["payment_terms_days"] = "meta"
        except Exception:
            derived_payment_days = None
    elif _is_non_empty(payment_meta.get("advance_days_calendar")):
        try:
            derived_payment_days = int(round(float(payment_meta.get("advance_days_calendar"))))
            sources["payment_terms_days"] = "meta"
        except Exception:
            derived_payment_days = None

    if derived_payment_days is not None:
        data["payment_terms_days"] = derived_payment_days
    elif _is_non_empty(data.get("payment_terms_days")):
        sources["payment_terms_days"] = _evidence_source_for_field(data, "payment_terms_days")
    else:
        data["payment_terms_days"] = None
        sources["payment_terms_days"] = "legacy"

    penalty_meta_value = penalties_meta.get("penalty_percent_per_day")
    if _is_non_empty(penalty_meta_value):
        data["penalty_percent_per_day"] = penalty_meta_value
        sources["penalty_percent_per_day"] = "meta"
    elif _is_non_empty(data.get("penalty_percent_per_day")):
        sources["penalty_percent_per_day"] = _evidence_source_for_field(data, "penalty_percent_per_day")
    else:
        data["penalty_percent_per_day"] = None
        sources["penalty_percent_per_day"] = "legacy"

    fine_meta_value = penalties_meta.get("fine_percent")
    if _is_non_empty(fine_meta_value):
        data["fine_percent"] = fine_meta_value
        sources["fine_percent"] = "meta"
    elif _is_non_empty(data.get("fine_percent")):
        sources["fine_percent"] = _evidence_source_for_field(data, "fine_percent")
    else:
        data["fine_percent"] = None
        sources["fine_percent"] = "legacy"

    for field in ("nmck", "execution_days"):
        if _is_non_empty(data.get(field)):
            sources[field] = _evidence_source_for_field(data, field)
        else:
            data[field] = None
            sources[field] = "legacy"

    for field in legacy_fields:
        chosen_values[field] = data.get(field)

    meta["consolidation"] = {
        "sources": sources,
        "chosen_values": chosen_values,
    }
    return data

# ---------- Main entry ----------

def extract_tender_data(text: str, llm_provider: str | None = None) -> dict:
    t = normalize_text(text or "")
    markers = _parse_file_markers(t)

    data = dict(BASE_SCHEMA)
    evidence: dict[str, dict] = {}
    meta = data.setdefault("meta", {})

    retrieved_sections = retrieve_sections(t)
    mined_candidates = mine_all_candidates(t)
    selected_candidates = {
        "nmck": select_best_candidate(mined_candidates.get("nmck", [])),
        "payment": select_best_candidate(mined_candidates.get("payment", [])),
        "execution": select_best_candidate(mined_candidates.get("execution", [])),
        "penalties": select_best_candidate(mined_candidates.get("penalties", [])),
    }
    apply_selected_to_extracted_data(data, selected_candidates)
    logger.info(
        "extract.v3.candidates",
        extra={
            "candidate_counts": {field: len(items) for field, items in mined_candidates.items()},
            "selected_candidate_ids": {
                field: (candidate.get("id") if candidate else None)
                for field, candidate in selected_candidates.items()
            },
        },
    )

    nmck_value, nmck_ev = extract_nmck_with_evidence(t, markers)
    if nmck_value is not None:
        data["nmck"] = nmck_value
        if nmck_ev:
            evidence["nmck"] = nmck_ev

    payment_days, payment_ev = extract_payment_terms_with_evidence(t, markers)
    if payment_days is not None:
        data["payment_terms_days"] = payment_days
        if payment_ev:
            evidence["payment_terms_days"] = payment_ev

    exec_days, exec_ev = extract_execution_days_with_evidence(t, markers)
    if exec_days is not None:
        data["execution_days"] = exec_days
        if exec_ev:
            evidence["execution_days"] = exec_ev

    penalties, penalties_evidence = extract_penalties_with_evidence(t, markers)
    if "penalty_percent_per_day" in penalties:
        data["penalty_percent_per_day"] = penalties["penalty_percent_per_day"]
    if "fine_percent" in penalties:
        data["fine_percent"] = penalties["fine_percent"]
    if "penalty_cap_percent" in penalties:
        meta["penalty_cap_percent"] = penalties["penalty_cap_percent"]

    for key, ev in penalties_evidence.items():
        evidence[key] = ev

    # LLM semantic helper (only fill missing or invalid)
    llm_meta: dict[str, Any] = {}
    llm = extract_with_llm(t, llm_provider, llm_meta)
    retrieval_meta = llm_meta.get("retrieval")
    if isinstance(retrieval_meta, dict):
        meta["retrieval"] = retrieval_meta

    def apply_llm_numeric(field: str, value: Any, keywords: list[str], source: str = "llm") -> None:
        if value is None:
            return
        current = data.get(field)
        if current is None or not _is_value_valid(field, current):
            data[field] = value
            snippet, location = _find_value_snippet(t, value, keywords)
            evidence[field] = {
                "field": field,
                "quote": snippet,
                "location": location,
                "source": source,
            }

    apply_llm_numeric("nmck", _safe_float(llm.get("nmck")), KW_NMCK)
    apply_llm_numeric("payment_terms_days", _safe_int(llm.get("payment_terms_days")), KW_PAYMENT)
    apply_llm_numeric("execution_days", _safe_int(llm.get("execution_days")), KW_EXECUTION)
    apply_llm_numeric("penalty_percent_per_day", _safe_float(llm.get("penalty_percent_per_day")), KW_PENALTY)
    apply_llm_numeric("fine_percent", _safe_float(llm.get("fine_percent")), KW_FINE)
    apply_llm_numeric("advance_percent", _safe_float(llm.get("advance_percent")), KW_ADVANCE)
    apply_llm_numeric("bid_security_percent", _safe_float(llm.get("bid_security_percent")), KW_BID_SECURITY)
    apply_llm_numeric("contract_security_percent", _safe_float(llm.get("contract_security_percent")), KW_CONTRACT_SECURITY)

    data["currency"] = _merge_non_empty(data.get("currency"), llm.get("currency") if llm.get("currency") in ("RUB", "USD", "EUR") else None)

    if "has_vague_acceptance_terms" in llm:
        flag = _safe_bool(llm.get("has_vague_acceptance_terms"))
        if flag:
            snippet, location = _find_keyword_evidence(t, KW_VAGUE)
            data["has_vague_acceptance_terms"] = True
            evidence["has_vague_acceptance_terms"] = {
                "field": "has_vague_acceptance_terms",
                "quote": snippet,
                "location": location,
                "source": "llm",
            }
            if not snippet:
                meta.setdefault("evidence_warnings", []).append("has_vague_acceptance_terms_unverified")
        else:
            data["has_vague_acceptance_terms"] = False


    # Tender traps (regex rules > LLM)
    data["payment_after_full_delivery"] = _has_any(t, [
        r"\u043f\u043e\u0441\u043b\u0435\s+\u043f\u043e\u043b\u043d\u043e\u0439\s+\u043f\u043e\u0441\u0442\u0430\u0432\u043a\u0438",
        r"\u043f\u043e\u0441\u043b\u0435\s+\u043f\u043e\u0441\u0442\u0430\u0432\u043a\u0438\s+\u0432\u0441\u0435\u0433\u043e\s+\u043e\u0431\u044a[\u0435\u0451]\u043c\u0430",
        r"\u043f\u043e\u0441\u043b\u0435\s+\u043f\u043e\u043b\u043d\u043e\u0433\u043e\s+\u0438\u0441\u043f\u043e\u043b\u043d\u0435\u043d\u0438\u044f",
        r"\u043e\u043f\u043b\u0430\u0442\u0430\s+\u043f\u043e\u0441\u043b\u0435\s+\u043f\u043e\u043b\u043d\u043e\u0439\s+\u043f\u043e\u0441\u0442\u0430\u0432\u043a\u0438",
    ])

    data["delivery_by_customer_requests"] = _has_any(t, [
        r"\u043f\u043e\s+\u0437\u0430\u044f\u0432\u043a(\u0430\u043c|\u0435)\s+\u0437\u0430\u043a\u0430\u0437\u0447\u0438\u043a\u0430",
        r"\u043f\u043e\u0441\u0442\u0430\u0432\u043a\u0430\s+\u043f\u0430\u0440\u0442\u0438\u044f\u043c\u0438",
        r"\u043e\u0442\u0433\u0440\u0443\u0437\u043a\u0430\s+\u043f\u0430\u0440\u0442\u0438\u044f\u043c\u0438",
        r"\u043f\u043e\s+\u043e\u0442\u0434\u0435\u043b\u044c\u043d\u044b\u043c\s+\u0437\u0430\u044f\u0432\u043a\u0430\u043c",
        r"\u043f\u043e\s+\u043c\u0435\u0440\u0435\s+\u043d\u0435\u043e\u0431\u0445\u043e\u0434\u0438\u043c\u043e\u0441\u0442\u0438",
    ])

    data["supplier_must_hold_stock"] = _has_any(t, [
        r"\u043e\u0431\u044f\u0437\u0430\u043d\s+\u043e\u0431\u0435\u0441\u043f\u0435\u0447\u0438\u0442\u044c\s+\u043d\u0430\u043b\u0438\u0447\u0438\u0435\s+\u0442\u043e\u0432\u0430\u0440\u0430\s+\u043d\u0430\s+\u0441\u043a\u043b\u0430\u0434\u0435",
        r"\u043e\u0431\u044f\u0437\u0430\u043d\s+\u0438\u043c\u0435\u0442\u044c\s+\u0442\u043e\u0432\u0430\u0440\s+\u043d\u0430\s+\u0441\u043a\u043b\u0430\u0434\u0435",
        r"\u043e\u0431\u0435\u0441\u043f\u0435\u0447\u0438\u0442\u044c\s+\u043d\u0430\u043b\u0438\u0447\u0438\u0435\s+\u043d\u0430\s+\u0441\u043a\u043b\u0430\u0434\u0435",
        r"\u043d\u0430\u043b\u0438\u0447\u0438\u0435\s+\u0442\u043e\u0432\u0430\u0440\u0430\s+\u043d\u0430\s+\u0441\u043a\u043b\u0430\u0434\u0435\s+\u043f\u043e\u0441\u0442\u0430\u0432\u0449\u0438\u043a\u0430",
    ])

    # Post-validation + repair
    errors = validate_extracted_data(data)
    if errors:
        meta["validation_errors"] = errors
        repair = _repair_with_llm(t, data, errors, llm_provider)
        if repair:
            if "payment_terms_days" in repair:
                apply_llm_numeric("payment_terms_days", _safe_int(repair.get("payment_terms_days")), KW_PAYMENT, source="llm_repair")
            if "execution_days" in repair:
                apply_llm_numeric("execution_days", _safe_int(repair.get("execution_days")), KW_EXECUTION, source="llm_repair")
            if "penalty_percent_per_day" in repair:
                apply_llm_numeric("penalty_percent_per_day", _safe_float(repair.get("penalty_percent_per_day")), KW_PENALTY, source="llm_repair")
            if "fine_percent" in repair:
                apply_llm_numeric("fine_percent", _safe_float(repair.get("fine_percent")), KW_FINE, source="llm_repair")

        errors_after = validate_extracted_data(data)
        if errors_after:
            meta["validation_errors"] = errors_after

    if evidence:
        data["extraction_evidence"] = evidence

    consolidate_extraction(data)
    consolidation = (data.get("meta") or {}).get("consolidation") or {}
    consolidation_sources = consolidation.get("sources") or {}

    payment_keywords_found = bool(retrieved_sections.get("payment"))
    penalties_keywords_found = bool(retrieved_sections.get("penalties"))
    payment_struct_present = isinstance((data.get("meta") or {}).get("payment"), dict)
    penalties_struct_present = isinstance((data.get("meta") or {}).get("penalties"), dict)
    logger.info(
        "extract.v3.payment",
        extra={
            "keywords_found": payment_keywords_found,
            "parsed_struct_present": payment_struct_present,
            "payment_terms_days": data.get("payment_terms_days"),
            "source": consolidation_sources.get("payment_terms_days", "legacy"),
        },
    )
    logger.info(
        "extract.v3.penalties",
        extra={
            "keywords_found": penalties_keywords_found,
            "parsed_struct_present": penalties_struct_present,
            "penalty_percent_per_day": data.get("penalty_percent_per_day"),
            "fine_percent": data.get("fine_percent"),
            "penalty_source": consolidation_sources.get("penalty_percent_per_day", "legacy"),
            "fine_source": consolidation_sources.get("fine_percent", "legacy"),
        },
    )

    quality = validate_quality_data(data, t, retrieved_sections)
    meta["quality"] = quality
    logger.info(
        "extract.v3.quality",
        extra={
            "completeness_score": quality.get("completeness_score"),
            "missing_reasons": quality.get("missing_reasons"),
        },
    )

    return data


def _smoke_check_nmck() -> None:
    sample = (
        "Начальная (максимальная) цена договора: "
        "НМЦ по извещению составляет: 7 752 436,93 руб."
    )
    parsed = _parse_amount("7 752 436,93 руб.")
    extracted, _ = extract_nmck_with_evidence(_normalize_extraction_text(sample), markers=[])
    print(f"parsed_amount={parsed}")
    print(f"extracted_nmck={extracted}")
    if parsed is None or abs(parsed - 7752436.93) > 0.01:
        raise SystemExit("SMOKE FAILED: _parse_amount")
    if extracted is None:
        raise SystemExit("SMOKE FAILED: extract_nmck_with_evidence")


if __name__ == "__main__":
    _smoke_check_nmck()

