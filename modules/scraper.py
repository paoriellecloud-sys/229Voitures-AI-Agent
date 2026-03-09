import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import os
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


# =============================
# EXTRAIRE LE TEXTE D'UNE PAGE
# =============================

def extract_page_text(url: str) -> str:
    """
    Télécharge une page web et extrait le texte principal.
    """
    try:
        response = requests.get(url, headers=HEADERS, timeout=10)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        # Supprimer les scripts et styles
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()

        # Extraire le texte
        text = soup.get_text(separator="\n", strip=True)

        # Limiter à 3000 caractères pour Gemini
        return text[:3000]

    except Exception as e:
        return f"Erreur lors de la lecture de la page : {str(e)}"


# =============================
# ANALYSER UNE ANNONCE AVEC GEMINI
# =============================

def analyze_listing(url: str) -> dict:
    """
    Scrape une annonce automobile et demande à Gemini de l'analyser.
    """

    # Étape 1 — Extraire le contenu de la page
    page_text = extract_page_text(url)

    if "Erreur" in page_text:
        return {"error": page_text}

    # Étape 2 — Envoyer à Gemini pour analyse
    prompt = f"""
    Voici le contenu d'une annonce automobile. Analyse-la et donne une recommandation.

    CONTENU DE L'ANNONCE :
    {page_text}

    Réponds avec :
    1. 📋 Résumé du véhicule (marque, modèle, année, prix, kilométrage)
    2. ✅ Points positifs
    3. ⚠️ Points à surveiller
    4. 💰 Évaluation du prix par rapport au marché
    5. 🎯 Recommandation finale (acheter / négocier / éviter)

    Réponds en français de façon claire et structurée.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return {
        "url": url,
        "analysis": response.text
    }


# =============================
# COMPARER 2 ANNONCES
# =============================

def compare_listings(url1: str, url2: str) -> dict:
    """
    Scrape 2 annonces et demande à Gemini de les comparer.
    """

    # Extraire les deux pages
    text1 = extract_page_text(url1)
    text2 = extract_page_text(url2)

    prompt = f"""
    Compare ces deux annonces automobiles et dis laquelle est la meilleure offre.

    ANNONCE 1 ({url1}) :
    {text1[:1500]}

    ANNONCE 2 ({url2}) :
    {text2[:1500]}

    Réponds avec :
    1. 📊 Tableau comparatif (prix, km, année, équipements)
    2. 🏆 Meilleure offre et pourquoi
    3. 💰 Analyse des prix par rapport au marché
    4. 🎯 Recommandation finale

    Réponds en français de façon claire et structurée.
    """

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return {
        "url1": url1,
        "url2": url2,
        "comparison": response.text
    }
