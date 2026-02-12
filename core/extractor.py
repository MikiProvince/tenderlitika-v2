import re
import json
import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

MODEL_NAME = os.getenv("GEMINI_MODEL", "models/gemini-flash-latest")
model = genai.GenerativeModel(MODEL_NAME)

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


def extract_with_llm(text: str):
    response = model.generate_content(
        EXTRACTION_PROMPT + "\n\n" + text[:15000],
        generation_config={
            "temperature": 0,
            "response_mime_type": "application/json"
        }
    )

    try:
        return json.loads(response.text)
    except:
        return {}

def extract_nmck_regex(text: str):
    match = re.search(r'(\d[\d\s]{5,})\s?(руб|₽)', text)
    if match:
        return float(match.group(1).replace(" ", ""))
    return None

def extract_tender_data(text: str):
    data = extract_with_llm(text)

    if not data.get("nmck"):
        data["nmck"] = extract_nmck_regex(text)

    return data