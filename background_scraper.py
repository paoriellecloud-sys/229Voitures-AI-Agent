import asyncio
import sqlite3
import os
from datetime import datetime

# Imports optionnels — ne pas bloquer si manquants
try:
    from playwright_scraper import scrape_with_playwright, save_to_cache, init_inventory_cache
    from serpapi_search import search_serpapi
    SERPAPI_AVAILABLE = True
except ImportError as e:
    print(f"⚠️ Modules optionnels non disponibles: {e}")
    SERPAPI_AVAILABLE = False
    def init_inventory_cache(): pass
    def save_to_cache(data): pass
    async def scrape_with_playwright(url): return {'success': False}
    def search_serpapi(query, num_results=5): return []

from fo_playwright_scraper import scrape_forceoccasion_for_background


# =============================
# TARGET SITES TO SCRAPE
# =============================

SCRAPE_TARGETS = [
    {
        'name': 'AutoHebdo',
        'queries': [
            'site:autohebdo.net voiture occasion Quebec',
            'site:autohebdo.net SUV occasion Quebec',
        ]
    },
    {
        'name': 'Otogo',
        'queries': [
            'site:otogo.ca voiture occasion',
        ]
    }
]

DB_PATH = os.environ.get("DB_PATH", "vehicles.db")


# =============================
# BACKGROUND SCRAPE JOB
# =============================

async def scrape_target(query: str, source: str):
    """Scrapes a specific query and saves results to cache."""
    print(f"[{datetime.now()}] Scraping: {query}")
    try:
        results = search_serpapi(query, num_results=5)
        for result in results:
            url = result.get('url', '')
            if not url:
                continue
            scraped = await scrape_with_playwright(url)
            if scraped.get('success'):
                vehicle_data = {
                    'url': url,
                    'source': source,
                    'raw_content': scraped.get('content', ''),
                    'price': scraped.get('price', ''),
                    'mileage': scraped.get('mileage', ''),
                    'make': result.get('title', '').split()[0] if result.get('title') else '',
                }
                save_to_cache(vehicle_data)
                print(f"  ✅ Saved: {url[:60]}")
            else:
                print(f"  ❌ Failed: {url[:60]} — {scraped.get('error', '')}")
            await asyncio.sleep(2)
    except Exception as e:
        print(f"  ❌ Error scraping {query}: {e}")


async def run_scrape_job():
    """Main background scraping job — runs every 6 hours."""
    print(f"\n[{datetime.now()}] Starting background scrape job...")
    init_inventory_cache()

    # 1. Force Occasion en premier — Playwright infinite scroll
    print(f"\n[{datetime.now()}] === Force Occasion Scraper (sitemaps XML) ===")
    try:
        conn = sqlite3.connect(DB_PATH)
        fo_count = await scrape_forceoccasion_for_background(conn)
        conn.close()
        print(f"[{datetime.now()}] ✅ Force Occasion: {fo_count} véhicules sauvegardés")
    except Exception as e:
        print(f"[{datetime.now()}] ❌ Erreur Force Occasion: {e}")

    # 2. Autres sites via SerpAPI + Playwright (si disponible)
    if SERPAPI_AVAILABLE:
        for target in SCRAPE_TARGETS:
            for query in target['queries']:
                await scrape_target(query, target['name'])
                await asyncio.sleep(5)
    else:
        print(f"[{datetime.now()}] ⚠️ SerpAPI non disponible — skip AutoHebdo/Otogo")

    print(f"[{datetime.now()}] Background scrape job completed.")


def start_background_scraper():
    """Starts the background scraper in a loop."""
    async def loop():
        while True:
            await run_scrape_job()
            print(f"Next scrape in 6 hours...")
            await asyncio.sleep(6 * 60 * 60)

    asyncio.run(loop())


if __name__ == '__main__':
    start_background_scraper()