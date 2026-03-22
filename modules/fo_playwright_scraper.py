"""
Force Occasion - Playwright Infinite Scroll Scraper
Récupère TOUS les véhicules en simulant le scroll humain
Intégration dans background_scraper.py
"""

import asyncio
import json
import logging
import requests
import aiohttp
from bs4 import BeautifulSoup
from datetime import datetime

logger = logging.getLogger(__name__)

FO_INVENTORY_URL = "https://www.forceoccasion.ca/inventaire.html"
FO_JSON_API = "https://www.forceoccasion.ca/js/json/{vehicle_id}.json"


async def scroll_and_collect_ids(page) -> list:
    """
    Scrolle la page jusqu'en bas en boucle jusqu'à ce qu'aucun
    nouvel ID ne soit chargé. Retourne la liste complète des IDs.
    """
    all_ids = set()
    no_new_count = 0
    max_no_new = 5  # Arrêter après 5 scrolls sans nouveaux IDs

    logger.info("🔄 Début du scroll infini sur Force Occasion...")

    while no_new_count < max_no_new:
        # Extraire les IDs actuellement visibles
        ids_on_page = await page.evaluate("""
            () => {
                const elements = document.querySelectorAll('li.carBoxWrapper[data-carid]');
                return Array.from(elements).map(el => el.getAttribute('data-carid')).filter(id => id);
            }
        """)

        new_ids = set(ids_on_page) - all_ids
        if new_ids:
            all_ids.update(new_ids)
            no_new_count = 0
            logger.info(f"📦 {len(all_ids)} véhicules trouvés jusqu'ici (+{len(new_ids)} nouveaux)")
        else:
            no_new_count += 1
            logger.info(f"⏳ Aucun nouveau véhicule ({no_new_count}/{max_no_new})")

        # Scroller vers le bas
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")

        # Attendre que le contenu charge (lazy loading)
        await asyncio.sleep(2)

        # Vérifier si un spinner/loader est visible (attendre qu'il disparaisse)
        try:
            await page.wait_for_selector(
                ".loading, .spinner, [class*='load']",
                state="hidden",
                timeout=3000
            )
        except Exception:
            pass  # Pas de spinner visible, on continue

    logger.info(f"✅ Scroll terminé. Total: {len(all_ids)} IDs collectés")
    return list(all_ids)


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
    Fonction principale: utilise requests+BeautifulSoup pour collecter les IDs
    depuis plusieurs URLs d'inventaire, puis aiohttp pour les détails JSON en parallèle.
    Retourne une liste de véhicules normalisés.
    """
    logger.info("🚀 Démarrage du scraper Force Occasion (requests + BeautifulSoup)")

    inventory_urls = [
        "https://www.forceoccasion.ca/inventaire.html",
        "https://www.forceoccasion.ca/inventaire.html?filterid=a1b21c2q0-10x0-0-0",
        "https://www.forceoccasion.ca/inventaire.html?cartype=demo",
        "https://www.forceoccasion.ca/inventaire.html?cartype=new",
    ]

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "fr-CA,fr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    }

    vehicle_ids = set()

    for url in inventory_urls:
        try:
            logger.info(f"📄 Chargement de {url}")
            resp = requests.get(url, headers=headers, timeout=30)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            items = soup.select("li.carBoxWrapper[data-carid]")
            ids = {el["data-carid"] for el in items if el.get("data-carid")}
            logger.info(f"  → {len(ids)} IDs trouvés")
            vehicle_ids.update(ids)
        except Exception as e:
            logger.error(f"❌ Erreur chargement {url}: {e}")

    vehicle_ids = list(vehicle_ids)

    if not vehicle_ids:
        logger.warning("⚠️ Aucun ID collecté via requests/BeautifulSoup")
        return []

    logger.info(f"🔗 {len(vehicle_ids)} IDs collectés, récupération des détails JSON...")

    # Récupérer les détails via l'API JSON publique
    raw_vehicles = await get_vehicle_details_batch(vehicle_ids, batch_size=15)

    # Normaliser
    vehicles = []
    for raw in raw_vehicles:
        normalized = normalize_vehicle(raw)
        if normalized:
            vehicles.append(normalized)

    logger.info(f"🏁 Scraping terminé: {len(vehicles)} véhicules prêts")
    return vehicles


# ============================================================
# INTÉGRATION DANS background_scraper.py
# Remplace la fonction scrape_forceoccasion() existante par:
# ============================================================

async def scrape_forceoccasion_for_background(db_conn) -> int:
    """
    Wrapper pour background_scraper.py
    Retourne le nombre de véhicules sauvegardés.
    
    Usage dans background_scraper.py:
        from fo_playwright_scraper import scrape_forceoccasion_for_background
        count = await scrape_forceoccasion_for_background(conn)
    """
    vehicles = await scrape_forceoccasion_full()

    if not vehicles:
        return 0

    saved = 0
    cursor = db_conn.cursor()

    for v in vehicles:
        try:
            # Construire raw_content pour la recherche
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

        # Sauvegarder en JSON pour inspection
        with open("fo_full_inventory.json", "w", encoding="utf-8") as f:
            json.dump(vehicles, f, ensure_ascii=False, indent=2)
        print(f"\n💾 Sauvegardé dans fo_full_inventory.json")

    asyncio.run(test())
