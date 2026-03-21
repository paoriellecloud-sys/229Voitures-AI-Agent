import asyncio
import time
import os
from datetime import datetime
from playwright_scraper import scrape_with_playwright, save_to_cache, init_inventory_cache
from serpapi_search import search_serpapi


# =============================
# TARGET SITES TO SCRAPE
# =============================

SCRAPE_TARGETS = [
    {
        'name': 'Force Occasion',
        'queries': [
            'site:forceoccasion.ca voiture occasion',
            'site:forceoccasion.ca SUV occasion',
            'site:forceoccasion.ca berline occasion',
        ]
    },
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


# =============================
# BACKGROUND SCRAPE JOB
# =============================

async def scrape_target(query: str, source: str):
    """Scrapes a specific query and saves results to cache."""
    print(f"[{datetime.now()}] Scraping: {query}")

    try:
        # Use SerpAPI to find URLs
        results = search_serpapi(query, num_results=5)

        for result in results:
            url = result.get('url', '')
            if not url:
                continue

            # Scrape with Playwright
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

            await asyncio.sleep(2)  # Polite delay between requests

    except Exception as e:
        print(f"  ❌ Error scraping {query}: {e}")


async def run_scrape_job():
    """Main background scraping job — runs every 6 hours."""
    print(f"\n[{datetime.now()}] Starting background scrape job...")
    init_inventory_cache()

    for target in SCRAPE_TARGETS:
        for query in target['queries']:
            await scrape_target(query, target['name'])
            await asyncio.sleep(5)

    print(f"[{datetime.now()}] Background scrape job completed.")


def start_background_scraper():
    """Starts the background scraper in a loop."""
    async def loop():
        while True:
            await run_scrape_job()
            print(f"Next scrape in 6 hours...")
            await asyncio.sleep(6 * 60 * 60)  # 6 hours

    asyncio.run(loop())


if __name__ == '__main__':
    start_background_scraper()