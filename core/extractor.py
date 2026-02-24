import re
import json
import os
import logging
import ssl
import time
import uuid
import urllib.request
import urllib.parse
from typing import Any, Optional
try:
    import google.generativeai as genai
except Exception:
    genai = None
from dotenv import load_dotenv

load_dotenv()
logger = logging.getLogger(__name__)

# ---------- helpers ----------

def _has_any(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text, flags=re.IGNORECASE | re.MULTILINE) for p in patterns)

def _safe_float(v: Any) -> Optional[float]:
    if v is None:
        return None
    if isinstance(v, (int, float)):
        return float(v)
    if isinstance(v, str):
        s = v.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
        # уберём всё кроме цифр и точки
        s = re.sub(r"[^0-9.]", "", s)
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
        return v.strip().lower() in ("true", "1", "yes", "да", "истина")
    return False

def _extract_json_from_text(s: str) -> dict:
    """
    Модели иногда возвращают JSON + мусор. Вырежем первый {...}.
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
Извлеки данные из текста тендера. Верни строго JSON и только JSON:

{
  "nmck": number | null,
  "currency": "RUB" | "USD" | "EUR" | null,

  "execution_days": number | null,
  "payment_terms_days": number | null,

  "bid_security_percent": number | null,
  "contract_security_percent": number | null,

  "advance_percent": number | null,
  "penalty_percent_per_day": number | null,

  "has_vague_acceptance_terms": boolean
}

Правила:
- Если нет данных — null.
- Проценты возвращай числом (например 5 означает 5%).
- has_vague_acceptance_terms = true, если есть расплывчатые условия приемки/основания отказа/«по усмотрению заказчика».
Только JSON. Без пояснений.

Текст:
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


def extract_with_llm(text: str, provider_override: str | None = None) -> dict:
    prompt_text = (text or "")[:15000]
    if not prompt_text.strip():
        return {}

    provider = _normalize_provider(provider_override or os.getenv("LLM_PROVIDER"))
    if provider == "gigachat":
        return _extract_with_gigachat(prompt_text)
    if provider == "gemini":
        return _extract_with_gemini(prompt_text)

    # auto: try Gemini first, then GigaChat
    result = _extract_with_gemini(prompt_text)
    if result:
        return result
    return _extract_with_gigachat(prompt_text)

# ---------- Regex fallbacks ----------

def _parse_amount(raw: str) -> Optional[float]:
    if not raw:
        return None
    s = raw.replace("\u00A0", " ").strip()
    s = s.replace(" ", "")
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

    try:
        return float(s)
    except Exception:
        return None


def extract_nmck_regex(text: str) -> Optional[float]:
    t = text or ""

    amount = r"(\d[\d\s\u00A0.,]*\d)"
    rub = r"(?:\s*(?:руб(?:\.|лей|ля|ль)?|₽))?"

    patterns = [
        rf"(?:нмцк|нмц|нцмк)[^\d]{{0,40}}{amount}{rub}",
        rf"(?:начальн[а-я\s()]*цена|цена\s+(?:договора|контракта|лота))[^\d]{{0,60}}{amount}{rub}",
    ]

    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE | re.DOTALL)
        if m:
            value = _parse_amount(m.group(1))
            if value is not None:
                return value

    generic = re.search(rf"{amount}\s*(?:руб(?:\.|лей|ля|ль)?|₽)", t, flags=re.IGNORECASE)
    if generic:
        return _parse_amount(generic.group(1))

    return None

def extract_execution_days_regex(text: str) -> Optional[int]:
    t = text or ""

    patterns = [
        r"срок\s+поставк[аи]\s*(?:товара|работ|услуг)?\s*—?\s*(?:не\s+)?позднее\s+(\d{1,3})\s*(?:календарн(?:ых|ых)?|рабоч(?:их|их)?)?\s*дн",
        r"срок\s+исполнени[яе]\s*(?:контракта)?\s*—?\s*(?:не\s+)?позднее\s+(\d{1,3})\s*(?:календарн(?:ых|ых)?|рабоч(?:их|их)?)?\s*дн",
        r"в\s+течение\s+(\d{1,3})\s*(?:календарн(?:ых|ых)?|рабоч(?:их|их)?)\s*дн(?:ей|я)?\s*(?:с\s+даты\s+)?(?:заключени[яе]|подписани[яе])\s+контракт",
    ]

    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            return _safe_int(m.group(1))
    return None

def extract_payment_terms_days_regex(text: str) -> Optional[int]:
    t = text or ""
    patterns = [
        r"оплата\s+производит(?:ся|ься)\s+в\s+течение\s+(\d{1,3})\s*календарн(?:ых|ых)?\s*дн",
        r"срок\s+оплат[ыы]\s*—?\s*(\d{1,3})\s*календарн(?:ых|ых)?\s*дн",
        r"оплата\s+в\s+течение\s+(\d{1,3})\s*дн(?:ей|я)?\s+после",
    ]
    for p in patterns:
        m = re.search(p, t, flags=re.IGNORECASE)
        if m:
            return _safe_int(m.group(1))
    return None

# ---------- Main entry ----------

def extract_tender_data(text: str, llm_provider: str | None = None) -> dict:
    t = text or ""

    # 1) LLM extraction
    llm = extract_with_llm(t, llm_provider)

    # 2) Start with schema
    data = dict(BASE_SCHEMA)

    # 3) Merge known fields from LLM (with type coercion)
    data["nmck"] = _safe_float(llm.get("nmck"))
    data["currency"] = llm.get("currency") if llm.get("currency") in ("RUB", "USD", "EUR") else None

    data["execution_days"] = _safe_int(llm.get("execution_days"))
    data["payment_terms_days"] = _safe_int(llm.get("payment_terms_days"))

    data["bid_security_percent"] = _safe_float(llm.get("bid_security_percent"))
    data["contract_security_percent"] = _safe_float(llm.get("contract_security_percent"))
    data["advance_percent"] = _safe_float(llm.get("advance_percent"))
    data["penalty_percent_per_day"] = _safe_float(llm.get("penalty_percent_per_day"))

    data["has_vague_acceptance_terms"] = _safe_bool(llm.get("has_vague_acceptance_terms"))

    # 4) Deterministic fallbacks (important!)
    if data["nmck"] is None:
        data["nmck"] = extract_nmck_regex(t)

    if data["execution_days"] is None:
        data["execution_days"] = extract_execution_days_regex(t)

    if data["payment_terms_days"] is None:
        data["payment_terms_days"] = extract_payment_terms_days_regex(t)

    # 5) Tender traps (regex rules > LLM)
    data["payment_after_full_delivery"] = _has_any(t, [
        r"после\s+полной\s+поставки",
        r"после\s+поставки\s+всего\s+объ[её]ма",
        r"после\s+полного\s+исполнения",
        r"оплата\s+после\s+полной\s+поставки",
    ])

    data["delivery_by_customer_requests"] = _has_any(t, [
        r"по\s+заявк(ам|е)\s+заказчика",
        r"поставка\s+партиями",
        r"отгрузка\s+партиями",
        r"по\s+отдельным\s+заявкам",
        r"по\s+мере\s+необходимости",
    ])

    data["supplier_must_hold_stock"] = _has_any(t, [
        r"обязан\s+обеспечить\s+наличие\s+товара\s+на\s+складе",
        r"обязан\s+иметь\s+товар\s+на\s+складе",
        r"обеспечить\s+наличие\s+на\s+складе",
        r"наличие\s+товара\s+на\s+складе\s+поставщика",
    ])

    return data
