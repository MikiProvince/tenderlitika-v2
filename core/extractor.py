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
Извлеки данные из текста тендера.

Верни строго JSON:

{
  "nmck": number | null,
  "execution_days": number | null,
  "payment_terms_days": number | null,
  "penalty_percent_per_day": number | null
}

Без комментариев.
Без текста.
Только JSON.
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