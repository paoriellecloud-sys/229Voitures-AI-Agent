from google import genai
from google.genai import types
from modules.scraper import analyze_listing, compare_listings, search_and_analyze
from modules.vin_checker import get_vehicle_report
import os
import json
import re
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT = """
Tu es AutoAgent 229Voitures, assistant automobile expert au Canada.

Règles STRICTES :
- Réponds en maximum 3-4 phrases courtes et directes
- Pas de listes à rallonge, pas de titres markdown inutiles
- Jamais de longues introductions
- Si tu donnes des options, maximum 3
- Toujours en français, toujours en dollars canadiens (CAD)
- Sois honnête : si tu n'as pas de données vérifiées, dis-le clairement
- Termine toujours par 1-2 actions concrètes pour l'utilisateur
"""

INTENT_PROMPT = """
Analyze this user message and return ONLY a JSON object with the intent and extracted data.

Message: "{message}"

Return exactly this JSON format:
{{
  "intent": "CHAT" | "SEARCH" | "ANALYZE_URL" | "COMPARE_URLS" | "CHECK_VIN",
  "urls": [],
  "vin": null,
  "query": null,
  "site": null,
  "count": 2
}}

Intent rules:
- CHAT: general question, advice, comparison without URLs
- SEARCH: user wants to find listings without providing URLs (keywords: trouve, cherche, montre, propose, liste, donne moi)
- ANALYZE_URL: message contains exactly 1 URL
- COMPARE_URLS: message contains 2+ URLs
- CHECK_VIN: message contains a VIN (17 alphanumeric characters)

For SEARCH, extract:
- query: the vehicle search terms (make, model, year, trim, dealer name)
- site: dealer domain if mentioned (ex: forceoccasion.ca), null otherwise
- count: number of results requested (default 2)

Return ONLY the JSON, no explanation.
"""


# =============================
# INTENT DETECTION
# =============================

def detect_intent(message: str) -> dict:
    """
    Detects user intent in a single Gemini call.
    Returns structured intent data.
    """
    prompt = INTENT_PROMPT.format(message=message)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt
    )

    try:
        raw = response.text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass

    # Default to CHAT if detection fails
    return {
        "intent": "CHAT",
        "urls": [],
        "vin": None,
        "query": message,
        "site": None,
        "count": 2
    }


# =============================
# SMART ROUTER — SINGLE ENTRY POINT
# =============================

def smart_chat(message: str) -> dict:
    """
    Single entry point for all user messages.
    Detects intent and routes to the right function automatically.
    """

    # Step 1 — Detect intent
    intent_data = detect_intent(message)
    intent = intent_data.get("intent", "CHAT")

    # Step 2 — Route to the right function
    if intent == "CHECK_VIN" and intent_data.get("vin"):
        result = get_vehicle_report(intent_data["vin"])
        return {
            "intent": "CHECK_VIN",
            "response": result
        }

    elif intent == "COMPARE_URLS" and len(intent_data.get("urls", [])) >= 2:
        result = compare_listings(intent_data["urls"][0], intent_data["urls"][1])
        return {
            "intent": "COMPARE_URLS",
            "response": result.get("comparison", ""),
            "urls": intent_data["urls"]
        }

    elif intent == "ANALYZE_URL" and len(intent_data.get("urls", [])) >= 1:
        result = analyze_listing(intent_data["urls"][0])
        return {
            "intent": "ANALYZE_URL",
            "response": result.get("analysis", ""),
            "url": intent_data["urls"][0],
            "scraped": result.get("scraped", False)
        }

    elif intent == "SEARCH" and intent_data.get("query"):
        result = search_and_analyze(
            query=intent_data["query"],
            site=intent_data.get("site"),
            count=intent_data.get("count", 2)
        )
        return {
            "intent": "SEARCH",
            "response": result.get("analysis", ""),
            "urls_found": result.get("urls_found", []),
            "scraped_count": result.get("scraped_count", 0)
        }

    else:
        # CHAT — general question
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=SYSTEM_PROMPT + "\nUtilisateur: " + message,
            config=types.GenerateContentConfig(
                tools=[types.Tool(google_search=types.GoogleSearch())]
            )
        )
        return {
            "intent": "CHAT",
            "response": response.text
        }