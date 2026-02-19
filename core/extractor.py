import re
import json
import os
import logging
import google.generativeai as genai
from dotenv import load_dotenv
from typing import Any, Optional

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
_MODEL: genai.GenerativeModel | None = None
_MODEL_INIT_FAILED = False


def _get_model() -> genai.GenerativeModel | None:
    global _MODEL
    global _MODEL_INIT_FAILED

    if _MODEL is not None:
        return _MODEL
    if _MODEL_INIT_FAILED:
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

def extract_with_llm(text: str) -> dict:
    model = _get_model()
    if model is None:
        return {}

    prompt_text = (text or "")[:15000]
    if not prompt_text.strip():
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

# ---------- Regex fallbacks ----------

def extract_nmck_regex(text: str):
    pattern = r'(\d[\d\s]{3,})(?:\s*)(?:руб(?:\.|лей|ля|ль)?|₽)'
    match = re.search(pattern, text.lower())

    if match:
        num = match.group(1).replace(" ", "")
        try:
            return float(num)
        except:
            return None

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

def extract_tender_data(text: str) -> dict:
    t = text or ""

    # 1) LLM extraction
    llm = extract_with_llm(t)

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
