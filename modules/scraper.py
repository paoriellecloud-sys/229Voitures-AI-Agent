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
- "Demandez un rapport CarFax pour ce véhicule"
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
    Step 1 — Ask Gemini to find real listing URLs via Google Search.
    Step 2 — Scrape each URL found.
    Step 3 — Analyze and compare with verified data.

    Works for ANY dealer site without needing a URL upfront.
    """

    # Build search query
    site_filter = f"site:{site}" if site else "site:autotrader.ca OR site:kijiji.ca OR site:forceoccasion.ca OR site:carpages.ca"
    search_query = f"{query} Canada {site_filter}"

    # Step 1 — Find real URLs via Google Search
    url_prompt = f"""
    Search Google for: {search_query}

    Return ONLY a JSON array of the {count} best matching listing URLs found.
    Format: ["url1", "url2"]
    No explanation, no markdown, just the JSON array.
    If you cannot find real URLs, return an empty array: []
    """

    url_response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=url_prompt,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())]
        )
    )

    # Parse URLs from response
    import json
    import re
    urls = []
    try:
        raw = url_response.text.strip()
        match = re.search(r'\[.*?\]', raw, re.DOTALL)
        if match:
            urls = json.loads(match.group())
    except Exception:
        urls = []

    # Step 2 — Scrape each URL found
    scraped_listings = []
    for url in urls[:count]:
        text = extract_page_text(url)
        scraped_listings.append({
            "url": url,
            "content": text,
            "scraped": "error" not in text.lower() and "blocked" not in text.lower()
        })

    # Step 3 — Analyze with real scraped data
    if scraped_listings and any(l["scraped"] for l in scraped_listings):
        listings_text = ""
        for i, listing in enumerate(scraped_listings, 1):
            status = "✅ scraped" if listing["scraped"] else "⚠️ blocked"
            listings_text += f"\nLISTING {i} ({status}) — {listing['url']}:\n{listing['content'][:1500]}\n"

        analysis_prompt = f"""
        The user asked: "{query}"

        Here is the real scraped content from {len(scraped_listings)} listings found online:
        {listings_text}

        Provide a concise analysis in French (max 6 sentences total):
        - For each listing: vehicle name, price, mileage, direct URL
        - Which is the best deal and why
        - Final recommendation

        IMPORTANT: Only use data from the scraped content above. Do not invent data.
        Always include the exact URL for each listing so the user can click directly.

        {PROACTIVE_INSTRUCTIONS}
        """
    else:
        # Fallback — no scraping succeeded, use Google Search knowledge only
        analysis_prompt = f"""
        The user asked: "{query}"

        I could not scrape listings directly. Use your Google Search knowledge to find
        relevant vehicles matching this request in Canada.

        Be honest that these results come from search and may not be current inventory.
        Provide max 4 sentences in French.
        Suggest the user verify directly on the dealer site.

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
    Scrapes a car listing and asks Gemini to analyze it with proactive suggestions.
    """

    page_text = extract_page_text(url)
    blocked = "blocked" in page_text.lower() or "unable to read" in page_text.lower() or "error" in page_text.lower()

    if blocked:
        prompt = f"""
        I could not scrape this URL directly: {url}
        Use Google Search to find information about this listing or similar vehicles.
        Give a brief analysis in French (max 4 sentences) and suggest 2 concrete next steps.
        {PROACTIVE_INSTRUCTIONS}
        """
    else:
        prompt = f"""
        Analyze this Canadian car listing. Be concise (max 5 sentences total).

        PAGE CONTENT:
        {page_text}

        Cover: vehicle summary, 1 positive point, 1 thing to watch, price vs market, recommendation.
        Always include the listing URL in your response: {url}

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
    Scrapes 2 listings and asks Gemini to compare them.
    """

    text1 = extract_page_text(url1)
    text2 = extract_page_text(url2)

    prompt = f"""
    Compare these two Canadian car listings. Be concise (max 6 sentences total).

    LISTING 1 ({url1}):
    {text1[:1500]}

    LISTING 2 ({url2}):
    {text2[:1500]}

    Cover: key differences, which is the better deal and why, final recommendation.
    Include both URLs so the user can access each listing directly.

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