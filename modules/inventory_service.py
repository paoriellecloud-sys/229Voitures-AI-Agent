"""
Inventory Service - 229Voitures
Responsabilite UNIQUE : chercher des vehicules dans la DB.
100% Python/SQLite - aucun appel Gemini.
"""

import sqlite3
import os

DB_PATH = os.getenv("DB_PATH", "/home/ubuntu/data/229voitures.db")

CATEGORY_MAP = {
    "vus": "Escape Equinox RDX MDX Explorer Bronco Rogue Tucson Sportage Seltos Kona Durango Traverse Blazer Murano Outlander Palisade Telluride Sorento Tonale GV70 X2 Encore Forester Outback Crosstrek Trailblazer Terrain Acadia RAV4 CR-V Pilot Highlander Pathfinder Santa Fe Compass Wrangler Cherokee Gladiator Edge Flex QX50 QX60 XT4 XT5 XT6",
    "suv": "Escape Equinox RDX MDX Explorer Bronco Rogue Tucson Sportage Seltos Kona Durango Traverse Blazer Murano Outlander Palisade Telluride Sorento RAV4 CR-V Pilot Highlander",
    "berline": "Civic Corolla Camry Accord Elantra Sonata Mazda3 Altima Jetta Model 3 Integra Malibu Legacy Forte K5 Optima Stinger IS ES LS A3 A4 A6 C-Class E-Class G70 G80 CT4 CT5",
    "berlin": "Civic Corolla Camry Accord Elantra Sonata Mazda3 Altima Jetta Model 3",
    "sedan": "Civic Corolla Camry Accord Elantra Sonata Mazda3 Altima Jetta Model 3",
    "camionnette": "F-150 Silverado Ram Tundra Tacoma Frontier Titan Colorado Canyon Ranger Maverick Sierra",
    "truck": "F-150 Silverado Ram Tundra Tacoma Frontier Titan Colorado Canyon Ranger Maverick Sierra",
    "pickup": "F-150 Silverado Ram Tundra Tacoma Frontier Titan Colorado Canyon Ranger Maverick Sierra",
    "fourgonnette": "Odyssey Sienna Carnival Pacifica Caravan Sedona",
    "minivan": "Odyssey Sienna Carnival Pacifica Caravan Sedona",
    "electrique": "Tesla Bolt Leaf Ioniq EV6 EV9 Ariya Mach-E Lightning Solterra bZ4X Model 3 Model Y Kona",
    "hybride": "Prius RAV4 Escape Tucson Santa Outlander Pacifica Wrangler CR-V Elantra Sonata Sienna",
    "phev": "Escape Tucson Santa Outlander Pacifica Wrangler Prius Prime RAV4 Prime",
    "luxe": "BMW Audi Mercedes Lexus Acura Infiniti Cadillac Lincoln Genesis Volvo Porsche Alfa",
    "compacte": "Civic Corolla Elantra Mazda3 Jetta Golf Forte Sentra Kicks Venue Trax",
    "sport": "Mustang Camaro Challenger BRZ Supra Miata Corvette GTI WRX Veloster Civic Type R",
    "mazda3": "Mazda3",
    "mazda 3": "Mazda3",
    "cx5": "CX-5",
    "cx-5": "CX-5",
    "cx3": "CX-3",
    "cx-3": "CX-3",
    "rav4": "RAV4",
    "crv": "CR-V",
    "cr-v": "CR-V",
    "f150": "F-150",
    "f-150": "F-150",
    "kona": "Kona",
    "seltos": "Seltos",
    "elantra": "Elantra",
    "corolla": "Corolla",
    "civic": "Civic",
}

STOPWORDS = {
    "budget", "dollar", "mois", "mensuel", "financement",
    "paiement", "taxes", "inclus", "environ", "approximatif",
    "cherche", "recherche", "trouve", "montre", "propose",
    "voudrais", "veux", "besoin", "avoir", "pour", "avec",
    "dans", "sous", "entre", "vers", "chez", "par",
}


def search(query: str, vehicle_filter: str = None, limit: int = 3) -> list[dict]:
    """
    Cherche des vehicules dans inventory_cache.
    
    1. Applique le CATEGORY_MAP si la query correspond a une categorie
    2. Recherche SQL avec fallback progressif
    3. Retourne max `limit` resultats
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        search_text = vehicle_filter or query
        search_lower = search_text.lower().strip()

        # 1. Détecter le type de carburant demandé EN PREMIER
        fuel_filter = None
        if any(w in search_lower for w in ['hybride', 'hybrid', 'hev']):
            fuel_filter = 'Hybride'
        elif any(w in search_lower for w in ['electr', 'électr', ' ev', 'ev ']):
            fuel_filter = 'lectrique'
        elif any(w in search_lower for w in ['phev', 'plug', 'plug-in', 'rechargeable', 'branche', 'recharge', 'hybride rechargeable']):
            fuel_filter = 'phev'
        elif any(w in search_lower for w in ['diesel']):
            fuel_filter = 'Diesel'

        # 2. Détecter si la query contient une marque/modèle spécifique
        KNOWN_MAKES = {
            'toyota', 'honda', 'ford', 'hyundai', 'kia', 'mazda', 'nissan',
            'chevrolet', 'chevy', 'gmc', 'dodge', 'jeep', 'ram', 'subaru',
            'volkswagen', 'vw', 'bmw', 'audi', 'mercedes', 'lexus', 'acura',
            'infiniti', 'cadillac', 'lincoln', 'buick', 'volvo', 'genesis',
            'mitsubishi', 'tesla', 'rivian', 'lucid', 'polestar',
            'rav4', 'crv', 'cr-v', 'civic', 'corolla', 'camry', 'elantra',
            'kona', 'seltos', 'tucson', 'sportage', 'rogue', 'escape',
            'f-150', 'f150', 'silverado', 'sierra', 'tacoma', 'tundra',
            'cx-5', 'cx5', 'mazda3', 'golf', 'jetta', 'tiguan',
        }
        has_specific_model = any(make in search_lower for make in KNOWN_MAKES)

        # 3. Si fuel_filter sans modèle spécifique → recherche directe par fuel_type
        if fuel_filter and not has_specific_model:
            cursor.execute("""
                SELECT * FROM inventory_cache
                WHERE LOWER(fuel_type) LIKE LOWER(?)
                AND price IS NOT NULL AND price > 0
                ORDER BY price ASC
                LIMIT 6
            """, (f'%{fuel_filter}%',))
            rows = cursor.fetchall()
            conn.close()
            if rows:
                return [dict(r) for r in rows[:limit]]

        # 4. Sinon : appliquer CATEGORY_MAP normalement
        for category, models in CATEGORY_MAP.items():
            if category in search_lower:
                search_text = models
                break

        # Nettoyer les stopwords
        keywords = [
            k.strip() for k in search_text.lower().split()
            if len(k.strip()) > 2 and k.strip() not in STOPWORDS
        ]

        if not keywords:
            keywords = [k for k in search_text.lower().split() if len(k) > 1]

        # Essai 1 : AND strict sur 3 mots max
        results = _search_and(cursor, keywords[:3], fuel_filter)

        # Essai 2 : OR souple sur 2 mots max
        if not results:
            results = _search_or(cursor, keywords[:2], fuel_filter)

        # Essai 3 : make/model direct
        if not results:
            results = _search_make_model(cursor, keywords[:2])

        conn.close()

        # Mapping fuel_type keywords
        FUEL_KEYWORDS = {
            '%lectrique%': ['electr', 'électr', 'ev ', ' ev', 'bolt', 'ioniq', 'tesla', 'leaf'],
            'Hybride':     ['hybride', 'hybrid', 'hev'],
            'PHEV':        ['phev', 'plug-in', 'rechargeable', 'branche'],
            'Diesel':      ['diesel'],
        }
        if not results:
            for fuel_pattern, kws in FUEL_KEYWORDS.items():
                if any(w in search_lower for w in kws):
                    try:
                        conn2 = sqlite3.connect(DB_PATH)
                        conn2.row_factory = sqlite3.Row
                        cursor2 = conn2.cursor()
                        cursor2.execute("""
                            SELECT * FROM inventory_cache
                            WHERE fuel_type LIKE ?
                            AND price IS NOT NULL AND price > 0
                            ORDER BY price ASC
                            LIMIT 6
                        """, (f'%{fuel_pattern}%',))
                        rows = cursor2.fetchall()
                        conn2.close()
                        if rows:
                            return [dict(r) for r in rows]
                    except Exception as e:
                        print(f"[inventory_service] fuel_type search error: {e}")
                    break

        return [dict(r) for r in results[:limit]]

    except Exception as e:
        print(f"[inventory_service] Erreur: {e}")
        return []


def _search_and(cursor, keywords: list, fuel_filter: str = None) -> list:
    if not keywords:
        return []
    conditions = []
    params = []
    for kw in keywords:
        conditions.append("(LOWER(title) LIKE ? OR LOWER(make) LIKE ? OR LOWER(model) LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    if fuel_filter:
        conditions.append(f"fuel_type LIKE '%{fuel_filter}%'")
    sql = f"""
        SELECT * FROM inventory_cache
        WHERE {' AND '.join(conditions)}
        AND price IS NOT NULL AND price > 0
        ORDER BY price ASC
        LIMIT 10
    """
    cursor.execute(sql, params)
    return cursor.fetchall()


def _search_or(cursor, keywords: list, fuel_filter: str = None) -> list:
    if not keywords:
        return []
    conditions = []
    params = []
    for kw in keywords:
        conditions.append("(LOWER(title) LIKE ? OR LOWER(make) LIKE ? OR LOWER(model) LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
    if fuel_filter:
        conditions.append(f"fuel_type LIKE '%{fuel_filter}%'")
    sql = f"""
        SELECT * FROM inventory_cache
        WHERE {' OR '.join(conditions)}
        AND price IS NOT NULL AND price > 0
        ORDER BY price ASC
        LIMIT 10
    """
    cursor.execute(sql, params)
    return cursor.fetchall()


def _search_make_model(cursor, keywords: list) -> list:
    if not keywords:
        return []
    conditions = []
    params = []
    for kw in keywords:
        conditions.append("(LOWER(make) LIKE ? OR LOWER(model) LIKE ?)")
        params.extend([f"%{kw}%", f"%{kw}%"])
    sql = f"""
        SELECT * FROM inventory_cache
        WHERE {' OR '.join(conditions)}
        AND price IS NOT NULL AND price > 0
        ORDER BY price ASC
        LIMIT 10
    """
    cursor.execute(sql, params)
    return cursor.fetchall()


def get_vehicle_by_stock(stock_number: str) -> dict | None:
    """Retrouve un vehicule par son numero de stock."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM inventory_cache WHERE stock_number = ? LIMIT 1",
            (stock_number,)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[inventory_service] get_by_stock error: {e}")
        return None


def get_vehicle_by_vin(vin: str) -> dict | None:
    """Retrouve un vehicule par son VIN."""
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM inventory_cache WHERE vin = ? LIMIT 1",
            (vin.upper(),)
        )
        row = cursor.fetchone()
        conn.close()
        return dict(row) if row else None
    except Exception as e:
        print(f"[inventory_service] get_by_vin error: {e}")
        return None


def count_vehicles() -> int:
    """Retourne le nombre total de vehicules en cache."""
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM inventory_cache")
        count = cursor.fetchone()[0]
        conn.close()
        return count
    except Exception:
        return 0
