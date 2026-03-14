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
GOOGLE_SEARCH_API_KEY = os.getenv("GOOGLE_SEARCH_API_KEY")
GOOGLE_SEARCH_ENGINE_ID = os.getenv("GOOGLE_SEARCH_ENGINE_ID")

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
# GOOGLE CUSTOM SEARCH
# =============================

def google_search(query: str, count: int = 2) -> list:
    """
    Uses Google Custom Search API to find real listing URLs.
    Returns a list of results with title, url, and snippet.
    """
    if not GOOGLE_SEARCH_API_KEY or not GOOGLE_SEARCH_ENGINE_ID:
        return []

    try:
        params = {
            "key": GOOGLE_SEARCH_API_KEY,
            "cx": GOOGLE_SEARCH_ENGINE_ID,
            "q": query,
            "num": min(count * 2, 10),  # fetch extra in case some are irrelevant
            "gl": "ca",  # Canada
            "hl": "fr",  # French
        }

        response = requests.get(
            "https://www.googleapis.com/customsearch/v1",
            params=params,
            timeout=10
        )
        response.raise_for_status()
        data = response.json()

        results = []
        for item in data.get("items", []):
            results.append({
                "title": item.get("title", ""),
                "url": item.get("link", ""),
                "snippet": item.get("snippet", "")
            })

        return results[:count]

    except Exception as e:
        print(f"Google Search error: {str(e)}")
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
    Step 1 — Google Custom Search API finds real listing URLs
    Step 2 — Scrape each URL found
    Step 3 — Analyze with verified data
    """

    # Build search query
    search_query = f"{query} occasion Canada"
    if site:
        search_query += f" site:{site}"

    # Step 1 — Find real URLs via Google Custom Search API
    search_results = google_search(search_query, count)

    # Step 2 — Scrape each URL
    scraped_listings = []
    for result in search_results:
        url = result["url"]
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

        Provide a concise response in French:
        - For each listing: vehicle name, price, mileage, and exact URL as a clickable link
        - Which is the best deal and why (1 sentence)
        - Final recommendation

        IMPORTANT:
        - Only use data from the content above
        - Always include the exact URL for each listing
        - Max 6 sentences total

        {PROACTIVE_INSTRUCTIONS}
        """
    else:
        # Fallback — Google Search found nothing, use Gemini web search
        analysis_prompt = f"""
        The user asked: "{query}"

        Search for relevant vehicles matching this request in Canada.
        Be honest that results may not reflect current inventory.
        Max 4 sentences in French. Always suggest verifying on dealer site.

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
        I could not scrape this URL: {url}
        Use Google Search to find information about this listing.
        Max 4 sentences in French. Include the URL: {url}
        {PROACTIVE_INSTRUCTIONS}
        """
    else:
        prompt = f"""
        Analyze this Canadian car listing. Max 5 sentences total.

        PAGE CONTENT:
        {page_text}

        Cover: vehicle summary, price, mileage, 1 positive point, 1 thing to watch, recommendation.
        Always include the listing URL: {url}

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