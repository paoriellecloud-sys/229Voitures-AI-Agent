"""
Force Occasion Inventaire Scraper
==================================
Étape 1 : Scrape la page inventaire HTML pour extraire tous les data-carid
Étape 2 : Pour chaque ID, appelle l'API JSON publique pour récupérer les détails
Étape 3 : Sauvegarde les données en JSON

Usage:
    python forceoccasion_scraper.py
"""

import requests
import json
import time
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Accept-Language": "fr-CA,fr;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

INVENTORY_URL = "https://www.forceoccasion.ca/inventaire.html?filterid=a1b21c2q0-10x0-0-0"
VEHICLE_JSON_URL = "https://www.forceoccasion.ca/js/json/{vehicle_id}.json"


def get_vehicle_ids_from_page(url: str) -> list[str]:
    """Scrape la page inventaire et retourne tous les data-carid trouvés."""
    print(f"[1/3] Scraping la page inventaire...")
    print(f"      URL: {url}")
    
    try:
        resp = requests.get(url, headers=HEADERS, timeout=30)
        resp.raise_for_status()
    except requests.RequestException as e:
        print(f"      ERREUR: {e}")
        return []

    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Cherche tous les éléments avec data-carid
    wrappers = soup.find_all(attrs={"data-carid": True})
    
    # Déduplique tout en gardant l'ordre
    seen = set()
    ids = []
    for el in wrappers:
        car_id = el.get("data-carid", "").strip()
        if car_id and car_id not in seen:
            seen.add(car_id)
            ids.append(car_id)
    
    print(f"      ✓ {len(ids)} véhicules trouvés: {ids[:5]}{'...' if len(ids) > 5 else ''}")
    return ids


def get_vehicle_details(vehicle_id: str) -> dict | None:
    """Appelle l'API JSON publique pour un véhicule."""
    url = VEHICLE_JSON_URL.format(vehicle_id=vehicle_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            print(f"      ⚠ ID {vehicle_id}: HTTP {resp.status_code}")
            return None
    except Exception as e:
        print(f"      ⚠ ID {vehicle_id}: {e}")
        return None


def extract_summary(data: dict) -> dict:
    """Extrait les champs essentiels d'une fiche véhicule."""
    return {
        "id": data.get("id", ""),
        "niv": data.get("NIV", data.get("niv", "")),
        "annee": data.get("year", ""),
        "marque": data.get("make", ""),
        "modele": data.get("model", ""),
        "prix": data.get("price", ""),
        "prix_marche": data.get("avgMarketPrice", ""),
        "kilometrage": data.get("miles", ""),
        "couleur_ext": data.get("color", ""),
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
        "description": data.get("fulldesc", "")[:300] if data.get("fulldesc") else "",
        "photos": data.get("photos", [])[:3],  # 3 premières photos seulement
        "similaires": [s.get("id") for s in data.get("similars", [])[:5]],
        "tps": data.get("taxes", {}).get("tps", "") if isinstance(data.get("taxes"), dict) else "",
        "tvq": data.get("taxes", {}).get("tvq", "") if isinstance(data.get("taxes"), dict) else "",
        "url_source": f"https://www.forceoccasion.ca/js/json/{data.get('id', '')}.json",
    }


def main():
    print("=" * 60)
    print("  Force Occasion Inventaire Scraper")
    print("=" * 60)
    
    # Étape 1: Récupérer les IDs
    vehicle_ids = get_vehicle_ids_from_page(INVENTORY_URL)
    
    if not vehicle_ids:
        print("\n❌ Aucun véhicule trouvé. Abandon.")
        return
    
    # Étape 2: Récupérer les détails de chaque véhicule
    print(f"\n[2/3] Récupération des détails ({len(vehicle_ids)} véhicules)...")
    
    vehicles_full = []
    vehicles_summary = []
    errors = []
    
    for i, vid in enumerate(vehicle_ids, 1):
        print(f"      [{i}/{len(vehicle_ids)}] ID {vid}...", end=" ", flush=True)
        data = get_vehicle_details(vid)
        
        if data:
            vehicles_full.append(data)
            vehicles_summary.append(extract_summary(data))
            year = data.get("year", "?")
            make = data.get("make", "?")
            model = data.get("model", "?")
            price = data.get("price", "?")
            print(f"✓ {year} {make} {model} - {price}$")
        else:
            errors.append(vid)
            print("✗ échec")
        
        # Pause courte pour ne pas surcharger le serveur
        if i < len(vehicle_ids):
            time.sleep(0.3)
    
    # Étape 3: Sauvegarder
    print(f"\n[3/3] Sauvegarde des résultats...")
    
    output = {
        "meta": {
            "source": INVENTORY_URL,
            "total_ids_found": len(vehicle_ids),
            "total_fetched": len(vehicles_full),
            "errors": errors,
        },
        "vehicles": vehicles_summary
    }
    
    with open("forceoccasion_inventory.json", "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)
    
    with open("forceoccasion_inventory_full.json", "w", encoding="utf-8") as f:
        json.dump(vehicles_full, f, ensure_ascii=False, indent=2)
    
    print(f"\n{'=' * 60}")
    print(f"  ✅ Terminé!")
    print(f"  • {len(vehicles_full)} véhicules récupérés")
    print(f"  • {len(errors)} erreurs: {errors if errors else 'aucune'}")
    print(f"  • Fichiers: forceoccasion_inventory.json (résumé)")
    print(f"              forceoccasion_inventory_full.json (données complètes)")
    print(f"{'=' * 60}")
    
    # Afficher un aperçu
    if vehicles_summary:
        print(f"\n  Aperçu des 3 premiers véhicules:")
        for v in vehicles_summary[:3]:
            print(f"  - {v['annee']} {v['marque']} {v['modele']} | {v['kilometrage']} km | {v['prix']}$ | {v['ville']}")


if __name__ == "__main__":
    main()
