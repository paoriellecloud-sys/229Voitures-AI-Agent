import asyncio
import time
import json
import requests
import sqlite3
import os
from datetime import datetime
from bs4 import BeautifulSoup
from playwright_scraper import scrape_with_playwright, save_to_cache, init_inventory_cache
from serpapi_search import search_serpapi


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

# =============================
# FORCE OCCASION — SCRAPER DIRECT
# =============================

FORCE_OCCASION_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-CA,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

# Pages d'inventaire à scraper (ajouter d'autres filterid si nécessaire)
FORCE_OCCASION_PAGES = [
    {
        "label": "Camions",
        "url": "https://www.forceoccasion.ca/inventaire.html?filterid=a1b21c2q0-10x0-0-0"
    },
    {
        "label": "Tous véhicules",
        "url": "https://www.forceoccasion.ca/inventaire.html"
    },
]

FORCE_OCCASION_JSON_URL = "https://www.forceoccasion.ca/js/json/{vehicle_id}.json"
DB_PATH = os.environ.get("DB_PATH", "229voitures.db")


def get_fo_vehicle_ids(url: str) -> list:
    """Scrape une page inventaire Force Occasion et retourne les data-carid."""
    try:
        resp = requests.get(url, headers=FORCE_OCCASION_HEADERS, timeout=30)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        wrappers = soup.find_all(attrs={"data-carid": True})
        seen = set()
        ids = []
        for el in wrappers:
            car_id = el.get("data-carid", "").strip()
            if car_id and car_id not in seen:
                seen.add(car_id)
                ids.append(car_id)
        return ids
    except Exception as e:
        print(f"  ❌ Erreur scraping page FO: {e}")
        return []


def get_fo_vehicle_details(vehicle_id: str) -> dict | None:
    """Appelle l'API JSON publique Force Occasion pour un véhicule."""
    url = FORCE_OCCASION_JSON_URL.format(vehicle_id=vehicle_id)
    try:
        resp = requests.get(url, headers=FORCE_OCCASION_HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        return None
    except Exception:
        return None


def save_fo_vehicle_to_db(data: dict):
    """Sauvegarde un véhicule Force Occasion dans inventory_cache."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        vehicle_id = str(data.get("id", ""))
        url = f"https://www.forceoccasion.ca/js/json/{vehicle_id}.json"
        source = "Force Occasion"

        # Construire un résumé structuré
        summary = {
            "id": vehicle_id,
            "niv": data.get("NIV", data.get("niv", "")),
            "annee": data.get("year", ""),
            "marque": data.get("make", ""),
            "modele": data.get("model", ""),
            "prix": data.get("price", ""),
            "prix_marche": data.get("avgMarketPrice", ""),
            "kilometrage": data.get("miles", ""),
            "couleur": data.get("color", ""),
            "moteur": data.get("moteur", ""),
            "transmission": data.get("transmission", ""),
            "carburant": data.get("carburant", ""),
            "traction": data.get("drivetrain", ""),
            "ville": data.get("city", ""),
            "province": data.get("state", ""),
            "concessionnaire": data.get("dealername", ""),
            "telephone": data.get("agentphone", ""),
            "conso_autoroute": data.get("highwayConsumption", ""),
            "conso_ville": data.get("cityConsumption", ""),
            "options": data.get("optionsTextFR", ""),
            "description": (data.get("fulldesc", "") or "")[:500],
            "photos": data.get("photos", [])[:5],
            "tps": data.get("taxes", {}).get("tps", "") if isinstance(data.get("taxes"), dict) else "",
            "tvq": data.get("taxes", {}).get("tvq", "") if isinstance(data.get("taxes"), dict) else "",
        }

        title = f"{summary['annee']} {summary['marque']} {summary['modele']}"
        price = str(summary["prix"])
        mileage = str(summary["kilometrage"])
        raw_content = json.dumps(summary, ensure_ascii=False)

        # Upsert — mise à jour si l'URL existe déjà
        cursor.execute("""
            INSERT INTO inventory_cache (url, source, title, price, mileage, raw_content, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(url) DO UPDATE SET
                title = excluded.title,
                price = excluded.price,
                mileage = excluded.mileage,
                raw_content = excluded.raw_content,
                scraped_at = excluded.scraped_at
        """, (url, source, title, price, mileage, raw_content, datetime.now().isoformat()))

        conn.commit()
        conn.close()
        return True
    except Exception as e:
        print(f"  ❌ DB error pour véhicule {data.get('id')}: {e}")
        return False


def run_force_occasion_scraper():
    """Scrape tout l'inventaire Force Occasion via leur API JSON publique."""
    print(f"\n[{datetime.now()}] === Force Occasion Scraper ===")

    total_saved = 0
    total_errors = 0
    all_ids_seen = set()

    for page in FORCE_OCCASION_PAGES:
        print(f"  📋 Page: {page['label']}")
        ids = get_fo_vehicle_ids(page["url"])

        if not ids:
            print(f"  ⚠ Aucun véhicule trouvé sur cette page")
            continue

        # Déduplique entre les pages
        new_ids = [i for i in ids if i not in all_ids_seen]
        all_ids_seen.update(new_ids)
        print(f"  🔍 {len(new_ids)} nouveaux véhicules à traiter")

        for i, vid in enumerate(new_ids, 1):
            data = get_fo_vehicle_details(vid)
            if data:
                saved = save_fo_vehicle_to_db(data)
                if saved:
                    total_saved += 1
                    year = data.get("year", "?")
                    make = data.get("make", "?")
                    model = data.get("model", "?")
                    price = data.get("price", "?")
                    print(f"  ✅ [{i}/{len(new_ids)}] {year} {make} {model} — {price}$")
                else:
                    total_errors += 1
            else:
                total_errors += 1
                print(f"  ❌ [{i}/{len(new_ids)}] ID {vid} — échec API")

            time.sleep(0.3)  # Délai poli

    print(f"  📊 Force Occasion: {total_saved} sauvegardés, {total_errors} erreurs")
    return total_saved


# =============================
# BACKGROUND SCRAPE JOB (autres sites)
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

    # 1. Force Occasion en premier (API directe, fiable)
    run_force_occasion_scraper()

    # 2. Autres sites via SerpAPI + Playwright
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
            await asyncio.sleep(6 * 60 * 60)

    asyncio.run(loop())


if __name__ == '__main__':
    start_background_scraper()