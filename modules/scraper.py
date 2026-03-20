import requests
from bs4 import BeautifulSoup
from google import genai
from google.genai import types
import os
import time
import random
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
SERPAPI_KEY = os.getenv("SERPAPI_KEY")

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

PROACTIVE_INSTRUCTIONS = """
After your analysis, always suggest 2 concrete next actions the user can take.
Keep suggestions short and actionable. Respond in French.
"""


# =============================
# SERPAPI SEARCH
# =============================

def serpapi_search(query: str, count: int = 2) -> list:
    """
    Uses SerpAPI to find real listing URLs from Google Search results.
    Returns a list of results with title, url, and snippet.
    """
    if not SERPAPI_KEY:
        return []

    try:
        params = {
            "api_key": SERPAPI_KEY,
            "engine": "google",
            "q": query,
            "gl": "ca",
            "hl": "fr",
            "num": min(count * 2, 10),
        }

        response = requests.get(
            "https://serpapi.com/search",
            params=params,
            timeout=15
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("organic_results", []):
            url = item.get("link", "")
            # Filter out irrelevant results
            if any(skip in url for skip in ["youtube.com", "facebook.com", "instagram.com", "twitter.com"]):
                continue
            results.append({
                "title": item.get("title", ""),
                "url": url,
                "snippet": item.get("snippet", "")
            })

        return results[:count]

    except Exception as e:
        print(f"SerpAPI error: {str(e)}")
        return []


# =============================
# EXTRACT PAGE TEXT
# =============================

def extract_page_text(url: str, retries: int = 3) -> str:
    """
    Downloads a web page and extracts the main text content.
    """
    for attempt in range(retries):
        try:
            headers = {
                "User-Agent": random.choice(USER_AGENTS),
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "fr-CA,fr;q=0.9,en-CA;q=0.8,en;q=0.7",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
                "Cache-Control": "max-age=0",
            }

            session = requests.Session()
            base_url = "/".join(url.split("/")[:3])
            session.get(base_url, headers=headers, timeout=8)
            time.sleep(random.uniform(0.5, 1.5))

            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
                tag.decompose()

            main = (
                soup.find("main") or
                soup.find("article") or
                soup.find(class_=lambda c: c and any(x in c for x in ["listing", "vehicle", "inventory", "result", "content"])) or
                soup.body
            )

            text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)
            lines = [line for line in text.splitlines() if line.strip()]
            return "\n".join(lines)[:4000]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                time.sleep(random.uniform(1, 3))
                continue
            return f"HTTP error: {str(e)}"
        except Exception as e:
            if attempt == retries - 1:
                return f"Unable to read page: {str(e)}"
            time.sleep(random.uniform(1, 2))

    return "Page blocked all attempts."


# =============================
# SEARCH + SCRAPE + ANALYZE
# =============================

def search_and_analyze(query: str, site: str = None, count: int = 2) -> dict:
    """
    Step 1 — SerpAPI finds real listing URLs from Google
    Step 2 — Scrape each URL found
    Step 3 — Analyze with verified data
    """

    # Build search query — Force Occasion prioritized first
    if site:
        search_query = f"{query} occasion Canada site:{site}"
        search_results = serpapi_search(search_query, count)
    else:
        # Step 1a — Search Force Occasion first
        fo_results = serpapi_search(f"{query} site:forceoccasion.ca", 1)

        # Step 1b — Search other Canadian sites
        other_results = serpapi_search(f"{query} occasion Canada", count)

        # Merge — Force Occasion first, then others (no duplicates)
        fo_urls = {r["url"] for r in fo_results}
        other_filtered = [r for r in other_results if r["url"] not in fo_urls]
        search_results = fo_results + other_filtered
        search_results = search_results[:count]

    # Step 2 — Scrape each URL + filter irrelevant results
    scraped_listings = []
    for result in search_results:
        url = result["url"]
        title = result["title"].lower()
        snippet = result["snippet"].lower()

        # Filter out results that don't match the vehicle being searched
        if site is None and query:
            # Extract key terms from query for relevance check
            query_words = [w.lower() for w in query.split() if len(w) > 2]
            relevant = any(word in title or word in snippet for word in query_words)
            if not relevant:
                continue

        text = extract_page_text(url)
        scraped_listings.append({
            "title": result["title"],
            "url": url,
            "snippet": result["snippet"],
            "content": text,
            "scraped": "error" not in text.lower() and "blocked" not in text.lower()
        })

    # Step 3 — Analyze
    if scraped_listings:
        listings_text = ""
        for i, listing in enumerate(scraped_listings, 1):
            content = listing["content"] if listing["scraped"] else listing["snippet"]
            listings_text += f"\nLISTING {i} — {listing['title']}\nURL: {listing['url']}\n{content[:1500]}\n"

        analysis_prompt = f"""
        The user asked: "{query}"

        Here are {len(scraped_listings)} real listings found via Google Search:
        {listings_text}

        IMPORTANT INSTRUCTIONS:
        - If price is missing from the scraped content, use Google Search to find the current market price for this specific vehicle in Canada
        - Never leave price as "non spécifié" — always find an estimated price from the market
        - Present ONLY the vehicles that match the user's request (correct make, model, year)
        - Skip any listing that is clearly irrelevant

        Present each matching vehicle in French using this format:

        🚗 [Marque Modèle Trim Année] · [km] km · [prix réel ou estimé marché] $
        📍 [Ville] · [URL]
        [1 phrase : point fort ou à surveiller]

        Ensuite :
        🏆 Meilleure option : [laquelle et pourquoi en 1 phrase]

        💰 Prix Québec taxes incluses (pour la meilleure option) :
        • Prix : [montant] $
        • TPS (5%) : + [calcul] $
        • TVQ (9.975%) : + [calcul] $
        • Total estimé : [total] $

        ⚠️ Estimations à titre informatif. Consultez un concessionnaire pour le prix exact.

        {PROACTIVE_INSTRUCTIONS}
        """
    else:
        # Fallback — SerpAPI found nothing, use Gemini web search
        analysis_prompt = f"""
        The user asked: "{query}"

        Use Google Search to find real current listings for: {query} au Canada

        Present findings in French using this format for each vehicle found:
        🚗 [Marque Modèle Trim Année] · [km] km · [prix] $
        📍 [Ville] · [URL si disponible]
        [1 phrase : point fort ou à surveiller]

        💰 Prix Québec taxes incluses pour la meilleure option :
        • TPS (5%) + TVQ (9.975%) = 14.975%
        • Total estimé : [calcul]

        ⚠️ Vérifiez la disponibilité directement auprès du concessionnaire.

        {PROACTIVE_INSTRUCTIONS}
        """

    final_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=analysis_prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    return {
        "query": query,
        "urls_found": [l["url"] for l in scraped_listings],
        "scraped_count": sum(1 for l in scraped_listings if l["scraped"]),
        "analysis": final_response.text
    }


# =============================
# ANALYZE A SINGLE URL
# =============================

def analyze_listing(url: str) -> dict:
    """
    Scrapes a car listing and asks Gemini to analyze it.
    """

    page_text = extract_page_text(url)
    blocked = "blocked" in page_text.lower() or "unable to read" in page_text.lower() or "error" in page_text.lower()

    if blocked:
        prompt = f"""
        Use Google Search to find information about this specific car listing URL: {url}

        Search for the vehicle details from this page and present them in French using this EXACT format.
        If you cannot find the exact listing, find a similar vehicle from the same dealer.

        🚗 [Marque] [Modèle] [Trim] [Année]
        📍 [Ville, Province] · [Kilométrage] km · [Prix] $

        [✅ Bonne affaire / ⚠️ Prix élevé] — 1 phrase basée sur le marché actuel

        Informations de base :
        • Transmission : [valeur]
        • Carburant : [valeur]
        • Couleur : [valeur]
        • Vendeur : [nom du concessionnaire]

        Équipements inclus :
        • [équipements principaux]

        💰 Prix Québec taxes incluses :
        • Prix affiché : [prix] $
        • TPS (5%) + TVQ (9.975%) : + [montant] $
        • Total estimé : [total] $

        ⚠️ Données à titre informatif. 229Voitures n'est pas un conseiller financier.

        Lien : {url}
        {PROACTIVE_INSTRUCTIONS}
        """
    else:
        prompt = f"""
        Analyze this Quebec/Canada car listing and present it in this EXACT structured format in French.
        ONLY use real data found in the page content — if a value is truly missing, skip that field entirely.
        Never write "Non disponible" — simply omit missing fields.

        PAGE CONTENT:
        {page_text}

        Use EXACTLY this format:

        🚗 [Marque] [Modèle] [Trim] [Année]
        📍 [Ville, Province] · [Kilométrage] km · [Prix affiché] $

        [✅ Bonne affaire / ⚠️ Prix élevé / 💡 Prix du marché] — 1 phrase

        Informations de base :
        • Transmission : [valeur]
        • Carburant : [valeur]
        • Couleur : [valeur]
        • Vendeur : [valeur]

        Équipements inclus :
        • [liste des équipements trouvés]

        Garantie :
        • [si mentionnée dans l'annonce]

        💰 Prix Québec taxes incluses :
        • Prix affiché : [prix] $
        • TPS (5%) : + [calcul exact] $
        • TVQ (9.975%) : + [calcul exact] $
        • Total estimé : [total exact] $

        📊 Financement estimé (taux moyen 6.9%) :
        • 48 mois : ~[calcul] $/mois
        • 60 mois : ~[calcul] $/mois
        • 72 mois : ~[calcul] $/mois

        ⚠️ Estimations à titre informatif. Consultez votre concessionnaire. 229Voitures n'est pas un conseiller financier.

        Voulez-vous que je vérifie le VIN, compare ce véhicule avec d'autres options, ou calculer le coût total de possession ?

        URL de l'annonce : {url}
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
        "scraped": not blocked,
        "analysis": response.text
    }


# =============================
# COMPARE 2 LISTINGS
# =============================

def compare_listings(url1: str, url2: str) -> dict:
    """
    Scrapes 2 listings and asks Gemini to compare them.
    """

    text1 = extract_page_text(url1)
    text2 = extract_page_text(url2)

    prompt = f"""
    Compare these two Canadian car listings. Max 6 sentences total.

    LISTING 1 ({url1}):
    {text1[:1500]}

    LISTING 2 ({url2}):
    {text2[:1500]}

    Cover: key differences, best deal and why, final recommendation.
    Include both URLs so the user can access each listing directly.

    {PROACTIVE_INSTRUCTIONS}
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
        "scraped_url1": "error" not in text1.lower(),
        "scraped_url2": "error" not in text2.lower(),
        "comparison": response.text
    }