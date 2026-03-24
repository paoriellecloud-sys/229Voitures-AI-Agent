"""
Force Occasion - Sitemap XML Scraper
Récupère TOUS les véhicules via les sitemaps XML publics + API JSON
Intégration dans background_scraper.py
"""

import asyncio
import json
import logging
import os
import re
import aiohttp
from datetime import datetime

logger = logging.getLogger(__name__)

FO_JSON_API = "https://www.forceoccasion.ca/js/json/{vehicle_id}.json"

SITEMAP_URLS = [
    "https://www.forceoccasion.ca/fr/sitemap.xml",
    "https://www.forceoccasion.ca/fr/sitemap_newinventory.xml",
    "https://www.forceoccasion.ca/fr/sitemap_demo.xml",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept": "application/xml,text/xml,*/*;q=0.8",
}


async def fetch_ids_from_sitemaps() -> list:
    """
    Fetche les 3 sitemaps XML en parallèle via aiohttp et extrait
    les IDs de véhicules depuis les URLs /fiche/{id}.
    """
    vehicle_ids = set()

    async def fetch_sitemap(session: aiohttp.ClientSession, url: str):
        try:
            logger.info(f"📥 Fetching sitemap: {url}")
            async with session.get(url, headers=HEADERS, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                resp.raise_for_status()
                text = await resp.text()
                ids = re.findall(r'-id(\d+)(?:-brochure|-pdf)?\.html', text)
                logger.info(f"  → {len(ids)} IDs trouvés dans {url.split('/')[-1]}")
                return ids
        except Exception as e:
            logger.error(f"❌ Erreur sitemap {url}: {e}")
            return []

    async with aiohttp.ClientSession() as session:
        results = await asyncio.gather(*[fetch_sitemap(session, url) for url in SITEMAP_URLS])

    for ids in results:
        vehicle_ids.update(ids)

    logger.info(f"✅ Total IDs uniques collectés: {len(vehicle_ids)}")
    return list(vehicle_ids)


async def get_vehicle_details_batch(vehicle_ids: list, batch_size: int = 10) -> list:
    """
    Récupère les détails JSON pour une liste d'IDs en parallèle.
    Utilise des batches pour éviter de surcharger le serveur.
    """
    vehicles = []
    total = len(vehicle_ids)

    async with aiohttp.ClientSession() as session:
        for i in range(0, total, batch_size):
            batch = vehicle_ids[i:i + batch_size]
            tasks = [fetch_vehicle_json(session, vid) for vid in batch]
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for result in results:
                if isinstance(result, dict) and result:
                    vehicles.append(result)
                elif isinstance(result, Exception):
                    logger.debug(f"Erreur fetch véhicule: {result}")

            logger.info(f"📊 Détails récupérés: {min(i + batch_size, total)}/{total}")
            await asyncio.sleep(0.5)  # Pause polie entre les batches

    return vehicles


async def fetch_vehicle_json(session: aiohttp.ClientSession, vehicle_id: str) -> dict:
    """Récupère le JSON d'un véhicule par son ID."""
    url = FO_JSON_API.format(vehicle_id=vehicle_id)
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Accept": "application/json",
        "Referer": "https://www.forceoccasion.ca/inventaire.html"
    }
    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                data = await resp.json(content_type=None)
                if data and isinstance(data, dict):
                    data['_vehicle_id'] = vehicle_id
                    data['_scraped_at'] = datetime.now().isoformat()
                    return data
    except Exception as e:
        logger.debug(f"Erreur JSON {vehicle_id}: {e}")
    return {}


def normalize_vehicle(raw: dict) -> dict:
    """Normalise les données brutes en format standard pour inventory_cache."""
    def safe(key, default=""):
        return str(raw.get(key, default) or default).strip()

    def safe_int(key, default=0):
        try:
            return int(str(raw.get(key, default)).replace(",", "").replace(" ", "") or default)
        except (ValueError, TypeError):
            return default

    vehicle_id = safe('_vehicle_id')
    title = f"{safe('year')} {safe('make')} {safe('model')}".strip()
    if not title or title == "  ":
        return {}

    # Calcul taxes QC
    price = safe_int('price')
    avg_market = safe_int('avgMarketPrice')
    tps = round(price * 0.05, 2)
    tvq = round(price * 0.09975, 2)
    total_taxes = round(tps + tvq, 2)
    total_with_taxes = round(price + total_taxes, 2)

    # Comparaison prix marché
    price_diff = price - avg_market if avg_market > 0 else 0
    price_status = ""
    if avg_market > 0:
        if price_diff < -500:
            price_status = f"🟢 {abs(price_diff):,}$ sous le marché"
        elif price_diff > 500:
            price_status = f"🔴 {price_diff:,}$ au-dessus du marché"
        else:
            price_status = "🟡 Prix dans la moyenne"

    return {
        'source': 'forceoccasion',
        'vehicle_id': vehicle_id,
        'title': title,
        'year': safe_int('year'),
        'make': safe('make'),
        'model': safe('model'),
        'trim': safe('trim'),
        'price': price,
        'avg_market_price': avg_market,
        'price_diff': price_diff,
        'price_status': price_status,
        'mileage': safe_int('miles'),
        'color': safe('colorDescription') or safe('color'),
        'transmission': safe('transmission'),
        'drivetrain': safe('drivetrain'),
        'fuel_type': safe('carburant') or safe('fuel'),
        'engine': safe('moteur') or safe('engine'),
        'vin': safe('NIV') or safe('vin'),
        'city': safe('city'),
        'province': safe('state') or 'QC',
        'dealer_name': safe('dealername'),
        'dealer_phone': safe('agentphone'),
        'tps': tps,
        'tvq': tvq,
        'total_taxes': total_taxes,
        'total_with_taxes': total_with_taxes,
        'options': safe('optionsTextFR'),
        'description': safe('fulldesc'),
        'highway_consumption': safe('highwayConsumption'),
        'city_consumption': safe('cityConsumption'),
        'photos': json.dumps(raw.get('photos', [])),
        'similars': json.dumps(raw.get('similars', [])),
        'url': f"https://www.forceoccasion.ca/fiche/{vehicle_id}",
        'json_url': FO_JSON_API.format(vehicle_id=vehicle_id),
        'scraped_at': safe('_scraped_at'),
    }


async def scrape_forceoccasion_full() -> list:
    """
    Fonction principale: lit fo_vehicle_ids.json si disponible (/app/ ou dossier courant),
    sinon fallback sur les sitemaps XML. Récupère les détails JSON en parallèle.
    Retourne une liste de véhicules normalisés.
    """
    logger.info("🚀 Démarrage du scraper Force Occasion (sitemaps XML + API JSON)")

    # Priorité : fichier local d'IDs (Railway /app/ ou dossier courant)
    vehicle_ids = None
    for ids_path in ["/app/fo_vehicle_ids.json", "fo_vehicle_ids.json"]:
        if os.path.exists(ids_path):
            try:
                with open(ids_path, encoding="utf-8") as f:
                    vehicle_ids = json.load(f)
                logger.info(f"📂 {len(vehicle_ids)} IDs chargés depuis {ids_path} (fichier local)")
            except Exception as e:
                logger.warning(f"⚠️ Erreur lecture {ids_path}: {e} → fallback sitemaps")
                vehicle_ids = None
            break

    if not vehicle_ids:
        logger.info("📡 fo_vehicle_ids.json introuvable → fetch des sitemaps")
        vehicle_ids = await fetch_ids_from_sitemaps()

    if not vehicle_ids:
        logger.warning("⚠️ Aucun ID collecté")
        return []

    logger.info(f"🔗 {len(vehicle_ids)} IDs collectés, récupération des détails JSON...")

    raw_vehicles = await get_vehicle_details_batch(vehicle_ids, batch_size=15)

    vehicles = []
    for raw in raw_vehicles:
        normalized = normalize_vehicle(raw)
        if normalized:
            vehicles.append(normalized)

    logger.info(f"🏁 Scraping terminé: {len(vehicles)} véhicules prêts")
    return vehicles


async def scrape_forceoccasion_for_background(db_conn) -> int:
    """
    Wrapper pour background_scraper.py
    Retourne le nombre de véhicules sauvegardés.

    Usage dans background_scraper.py:
        from fo_playwright_scraper import scrape_forceoccasion_for_background
        count = await scrape_forceoccasion_for_background(conn)
    """
    db_conn.execute("""
        CREATE TABLE IF NOT EXISTS inventory_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            source TEXT, vehicle_id TEXT, title TEXT, price REAL, mileage INTEGER,
            year INTEGER, make TEXT, model TEXT, city TEXT, province TEXT,
            dealer_name TEXT, dealer_phone TEXT, vin TEXT, color TEXT,
            transmission TEXT, drivetrain TEXT, fuel_type TEXT, engine TEXT, trim TEXT,
            avg_market_price REAL, price_diff REAL, price_status TEXT,
            tps REAL, tvq REAL, total_taxes REAL, total_with_taxes REAL,
            options TEXT, description TEXT, highway_consumption TEXT, city_consumption TEXT,
            photos TEXT, url TEXT, json_url TEXT, raw_content TEXT, scraped_at TEXT,
            UNIQUE(source, vehicle_id)
        )
    """)
    db_conn.commit()

    vehicles = await scrape_forceoccasion_full()

    if not vehicles:
        return 0

    saved = 0
    cursor = db_conn.cursor()

    for v in vehicles:
        try:
            raw_content = (
                f"{v['title']} {v['make']} {v['model']} {v['year']} "
                f"{v['trim']} {v['color']} {v['city']} {v['dealer_name']} "
                f"{v['vin']} {v['fuel_type']} {v['transmission']} {v['options']}"
            ).lower()

            cursor.execute("""
                INSERT INTO inventory_cache
                (source, vehicle_id, title, price, mileage, year, make, model,
                 city, province, dealer_name, dealer_phone, vin, color,
                 transmission, drivetrain, fuel_type, engine, trim,
                 avg_market_price, price_diff, price_status,
                 tps, tvq, total_taxes, total_with_taxes,
                 options, description, highway_consumption, city_consumption,
                 photos, url, json_url, raw_content, scraped_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                        ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(source, vehicle_id) DO UPDATE SET
                    title=excluded.title,
                    price=excluded.price,
                    mileage=excluded.mileage,
                    avg_market_price=excluded.avg_market_price,
                    price_diff=excluded.price_diff,
                    price_status=excluded.price_status,
                    tps=excluded.tps, tvq=excluded.tvq,
                    total_taxes=excluded.total_taxes,
                    total_with_taxes=excluded.total_with_taxes,
                    options=excluded.options,
                    photos=excluded.photos,
                    raw_content=excluded.raw_content,
                    scraped_at=excluded.scraped_at
            """, (
                v['source'], v['vehicle_id'], v['title'], v['price'], v['mileage'],
                v['year'], v['make'], v['model'], v['city'], v['province'],
                v['dealer_name'], v['dealer_phone'], v['vin'], v['color'],
                v['transmission'], v['drivetrain'], v['fuel_type'], v['engine'], v['trim'],
                v['avg_market_price'], v['price_diff'], v['price_status'],
                v['tps'], v['tvq'], v['total_taxes'], v['total_with_taxes'],
                v['options'], v['description'], v['highway_consumption'], v['city_consumption'],
                v['photos'], v['url'], v['json_url'], raw_content, v['scraped_at']
            ))
            saved += 1
        except Exception as e:
            logger.debug(f"Erreur save {v.get('vehicle_id', '?')}: {e}")

    db_conn.commit()
    logger.info(f"💾 {saved}/{len(vehicles)} véhicules sauvegardés dans inventory_cache")

    # Debug: afficher les 3 premiers véhicules sauvegardés avec tous les champs clés
    try:
        cur = db_conn.cursor()
        cur.execute("""
            SELECT source, vehicle_id, make, model, year, price, mileage,
                   city, dealer_name, vin, raw_content
            FROM inventory_cache LIMIT 3
        """)
        rows = cur.fetchall()
        print(f"\n=== DEBUG inventory_cache ({saved} véhicules sauvegardés) ===")
        for row in rows:
            source, vid, make, model, year, price, mileage, city, dealer, vin, raw_content = row
            print(f"  [{source}] {year} {make} {model}")
            print(f"    prix={price} | km={mileage} | ville={city} | dealer={dealer}")
            print(f"    vin={vin} | vehicle_id={vid}")
            print(f"    raw_content[:200]: {str(raw_content)[:200]}")
        print("=== FIN DEBUG ===\n")
    except Exception as e:
        print(f"[DEBUG inventory_cache] Erreur: {e}")

    return saved


# ============================================================
# TEST LOCAL
# ============================================================
if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s"
    )

    async def test():
        vehicles = await scrape_forceoccasion_full()
        print(f"\n{'='*60}")
        print(f"✅ Total véhicules récupérés: {len(vehicles)}")
        print(f"{'='*60}")

        if vehicles:
            print("\n📋 Exemples (5 premiers):")
            for v in vehicles[:5]:
                print(f"  • {v['title']} | {v['mileage']:,} km | {v['price']:,}$ | {v['city']}")
                if v['avg_market_price'] > 0:
                    print(f"    Prix marché: {v['avg_market_price']:,}$ → {v['price_status']}")

        with open("fo_full_inventory.json", "w", encoding="utf-8") as f:
            json.dump(vehicles, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Sauvegardé dans fo_full_inventory.json")

    asyncio.run(test())
