from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# =============================
# CHAT SIMPLE (sans recherche web)
# =============================

def auto_chat(message: str) -> str:
    """
    Chat simple avec Gemini — répond avec ses connaissances.
    """

    system_prompt = """
    Tu es un assistant automobile expert nommé AutoAgent 229Voitures.
    Tu aides les utilisateurs à choisir le meilleur véhicule au Canada.

    Tu compares :
    - prix
    - consommation
    - fiabilité
    - valeur marché

    Tu donnes toujours des conseils clairs et pratiques en français.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=system_prompt + "\nUtilisateur: " + message
    )

    return response.text


# =============================
# CHAT AVEC RECHERCHE WEB
# =============================

def auto_chat_web(message: str) -> str:
    """
    Chat avec Gemini + Google Search activé.
    Permet à l'agent de chercher des prix et offres en temps réel.
    """

    system_prompt = """
    Tu es un assistant automobile expert nommé AutoAgent 229Voitures.
    Tu aides les utilisateurs à trouver le meilleur véhicule au Canada.

    Quand on te demande des prix ou des offres :
    - Cherche sur AutoTrader Canada, Kijiji Autos, ou les sites des concessionnaires
    - Compare les prix du marché actuel
    - Donne des conseils basés sur les vraies offres trouvées

    Réponds toujours en français avec des informations concrètes et à jour.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=system_prompt + "\nUtilisateur: " + message,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return response.text


# =============================
# ANALYSE D'UN LIEN
# =============================

def analyze_vehicle_url(url: str) -> str:
    """
    Demande à Gemini d'analyser une annonce automobile via son URL.
    """

    prompt = f"""
    Analyse cette annonce automobile et dis-moi si c'est une bonne affaire.

    URL : {url}

    Donne-moi :
    1. ✅ Points positifs
    2. ⚠️ Points à surveiller
    3. 💰 Comparaison avec le prix du marché actuel
    4. 🎯 Recommandation finale : acheter ou pas?

    Réponds en français de façon claire et pratique.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return response.text
