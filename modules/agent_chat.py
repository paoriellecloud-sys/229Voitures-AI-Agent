from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

SYSTEM_PROMPT_BASE = """
Tu es AutoAgent 229Voitures, assistant automobile expert au Canada.

Règles STRICTES :
- Réponds en maximum 3-4 phrases courtes et directes
- Pas de listes à rallonge, pas de titres markdown inutiles
- Jamais de longues introductions comme "En tant qu'AutoAgent..."
- Si tu donnes des options, maximum 3
- Toujours en français, toujours en dollars canadiens (CAD)

Tu aides les Canadiens à choisir des véhicules d'occasion : prix, fiabilité, consommation, valeur marché.
"""

SYSTEM_PROMPT_WEB = """
Tu es AutoAgent 229Voitures, assistant automobile expert au Canada.

Règles STRICTES :
- Réponds en maximum 3-4 phrases courtes et directes
- Pas de listes à rallonge, pas de titres markdown inutiles
- Jamais de longues introductions comme "En tant qu'AutoAgent..."
- Si tu donnes des options, maximum 3
- Toujours en français, toujours en dollars canadiens (CAD)

Quand on te demande des prix ou des offres :
- Cherche sur AutoTrader Canada, Kijiji Autos, ou les sites des concessionnaires
- Donne des résultats concrets et récents du marché canadien
"""


# =============================
# SIMPLE CHAT (no web search)
# =============================

def auto_chat(message: str) -> str:
    """
    Simple chat with Gemini — answers from its own knowledge.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=SYSTEM_PROMPT_BASE + "\nUtilisateur: " + message
    )

    return response.text


# =============================
# CHAT WITH WEB SEARCH
# =============================

def auto_chat_web(message: str) -> str:
    """
    Chat with Gemini + Google Search enabled.
    Allows the agent to search for real-time prices and offers.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=SYSTEM_PROMPT_WEB + "\nUtilisateur: " + message,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return response.text


# =============================
# URL ANALYSIS
# =============================

def analyze_vehicle_url(url: str) -> str:
    """
    Asks Gemini to analyze a car listing from its URL.
    """

    prompt = f"""
    Analyse cette annonce automobile canadienne et dis-moi si c'est une bonne affaire.
    Sois bref : maximum 4-5 phrases au total.

    URL : {url}

    Couvre en 1 phrase chacun :
    ✅ Points positifs
    ⚠️ Points à surveiller
    💰 Prix vs marché canadien actuel
    🎯 Recommandation finale
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return response.text