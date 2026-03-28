import asyncio
import sqlite3
import os
import json
import time
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

DB_PATH = os.environ.get("DB_PATH", "229voitures.db")
IDS_FILE = os.path.join(os.path.dirname(__file__), "fo_vehicle_ids.json")


# =============================
# AUTO-REFRESH FO VEHICLE IDs
# =============================

def refresh_fo_ids():
    """Scrape les sitemaps Force Occasion et met à jour fo_vehicle_ids.json."""
    import requests
    import re

    sitemaps = [
        "https://www.forceoccasion.ca/fr/sitemap.xml",
        "https://www.forceoccasion.ca/fr/sitemap_newinventory.xml",
        "https://www.forceoccasion.ca/fr/sitemap_demo.xml"
    ]

    all_ids = set()
    for url in sitemaps:
        try:
            headers = {"User-Agent": "Mozilla/5.0"}
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                matches = re.findall(r'-id(\d+)', r.text)
                all_ids.update(matches)
                print(f"[refresh_ids] {url} → {len(matches)} IDs")
        except Exception as e:
            print(f"[refresh_ids] Erreur {url}: {e}")

    if len(all_ids) > 100:
        ids_list = sorted(list(all_ids))
        with open(IDS_FILE, "w") as f:
            json.dump(ids_list, f)
        print(f"[refresh_ids] ✅ {len(ids_list)} IDs sauvegardés dans fo_vehicle_ids.json")
        return len(ids_list)
    else:
        print(f"[refresh_ids] ⚠️ Seulement {len(all_ids)} IDs trouvés — garde l'ancien fichier")
        return 0


def check_and_refresh_fo_ids():
    """Vérifie l'âge de fo_vehicle_ids.json et rafraîchit si > 24h ou absent."""
    if os.path.exists(IDS_FILE):
        age_hours = (time.time() - os.path.getmtime(IDS_FILE)) / 3600
        print(f"[fo_vehicle_ids.json] Âge: {age_hours:.1f}h")
        if age_hours > 24:
            print(f"[fo_vehicle_ids.json] > 24h → tentative de refresh automatique")
            count = refresh_fo_ids()
            if count > 0:
                print(f"[fo_vehicle_ids.json] ✅ Refresh réussi: {count} IDs")
            else:
                print(f"[fo_vehicle_ids.json] ⚠️ Refresh échoué — utilise l'ancien fichier")
        else:
            print(f"[fo_vehicle_ids.json] OK — pas besoin de refresh")
    else:
        print(f"[fo_vehicle_ids.json] Fichier absent → refresh obligatoire")
        refresh_fo_ids()


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

    # 0. Refresh des IDs Force Occasion si nécessaire (> 24h ou absent)
    print(f"\n[{datetime.now()}] === Vérification fo_vehicle_ids.json ===")
    check_and_refresh_fo_ids()

    # 1. Force Occasion en premier — Playwright infinite scroll
    print(f"\n[{datetime.now()}] === Force Occasion Scraper (Playwright) ===")
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
