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

# Rotate user agents to avoid bot detection
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:123.0) Gecko/20100101 Firefox/123.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_3) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
]

PROACTIVE_INSTRUCTIONS = """
After your analysis, always suggest 2-3 concrete next actions the user can take.
Examples:
- "Je vous suggère de demander un rapport CarFax pour ce véhicule"
- "Négociez le prix — ce modèle se vend en moyenne X$ moins cher en ce moment"
- "Comparez avec cette annonce similaire sur Kijiji ou AutoTrader"
Keep suggestions short and actionable.
"""


# =============================
# EXTRACT PAGE TEXT
# =============================

def extract_page_text(url: str, retries: int = 3) -> str:
    """
    Downloads a web page and extracts the main text content.
    Retries with different user agents if blocked.
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
            # First visit homepage to get cookies (helps avoid bot detection)
            base_url = "/".join(url.split("/")[:3])
            session.get(base_url, headers=headers, timeout=8)
            time.sleep(random.uniform(0.5, 1.5))

            response = session.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            soup = BeautifulSoup(response.text, "html.parser")

            # Remove noise
            for tag in soup(["script", "style", "nav", "footer", "header", "iframe", "noscript"]):
                tag.decompose()

            # Try to find main content area first
            main = (
                soup.find("main") or
                soup.find("article") or
                soup.find(class_=lambda c: c and any(x in c for x in ["listing", "vehicle", "inventory", "result", "content"])) or
                soup.body
            )

            text = main.get_text(separator="\n", strip=True) if main else soup.get_text(separator="\n", strip=True)

            # Clean up excessive blank lines
            lines = [line for line in text.splitlines() if line.strip()]
            text = "\n".join(lines)

            return text[:4000]

        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 403:
                time.sleep(random.uniform(1, 3))
                continue
            return f"HTTP error: {str(e)}"
        except Exception as e:
            if attempt == retries - 1:
                return f"Unable to read page after {retries} attempts: {str(e)}"
            time.sleep(random.uniform(1, 2))

    return "Page blocked all attempts — site may require JavaScript or login."


# =============================
# ANALYZE A LISTING
# =============================

def analyze_listing(url: str) -> dict:
    """
    Scrapes a car listing and asks Gemini to analyze it with proactive suggestions.
    """

    page_text = extract_page_text(url)
    blocked = "blocked" in page_text.lower() or "unable to read" in page_text.lower() or "error" in page_text.lower()

    if blocked:
        # Fallback: let Gemini use Google Search instead
        prompt = f"""
        I could not scrape this URL directly: {url}
        Use Google Search to find information about this listing or similar vehicles from this dealer.

        Give a brief analysis in French (max 4 sentences) and suggest 2 concrete next steps for the user.
        {PROACTIVE_INSTRUCTIONS}
        """
    else:
        prompt = f"""
        Analyze this Canadian car listing and give a recommendation. Be concise (max 5 sentences total).

        PAGE CONTENT:
        {page_text}

        Cover briefly:
        - Vehicle summary (make, model, year, price, mileage)
        - 1 positive point, 1 thing to watch out for
        - Price vs current Canadian market
        - Final recommendation (buy / negotiate / avoid)

        {PROACTIVE_INSTRUCTIONS}

        Respond in French.
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
    Scrapes 2 listings and asks Gemini to compare them with proactive suggestions.
    """

    text1 = extract_page_text(url1)
    text2 = extract_page_text(url2)

    prompt = f"""
    Compare these two Canadian car listings. Be concise (max 6 sentences total).

    LISTING 1 ({url1}):
    {text1[:1500]}

    LISTING 2 ({url2}):
    {text2[:1500]}

    Cover briefly:
    - Key differences (price, km, year, condition)
    - Which is the better deal and why
    - Final recommendation

    {PROACTIVE_INSTRUCTIONS}

    Respond in French.
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