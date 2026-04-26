from google import genai
from google.genai import types
from modules.scraper import analyze_listing, compare_listings, search_and_analyze
from modules.vin_checker import get_vehicle_report
from modules.formatters import format_vehicles_html_block, generate_rdv_form, generate_vin_report
from database import log_search
import os
import json
import re
import sqlite3
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))
DB_PATH = os.environ.get("DB_PATH", "/home/ubuntu/data/229voitures.db")

sessions = {}


# =============================
# SESSION PERSISTANCE SQLite
# =============================

def _get_session_db_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sessions (
            user_id TEXT PRIMARY KEY,
            history TEXT,
            user_data TEXT,
            context TEXT,
            vehicle_shown TEXT DEFAULT '{}',
            updated_at TEXT
        )
    """)
    try:
        conn.execute("ALTER TABLE sessions ADD COLUMN vehicle_shown TEXT DEFAULT '{}'")
    except Exception:
        pass  # Colonne déjà existante
    conn.commit()
    return conn


def save_session(user_id: str, session: dict):
    try:
        conn = _get_session_db_conn()
        conn.execute("""
            INSERT OR REPLACE INTO sessions (user_id, history, user_data, context, vehicle_shown, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            user_id,
            json.dumps(session.get("history", []), ensure_ascii=False),
            json.dumps(session.get("user_data", {}), ensure_ascii=False),
            json.dumps(session.get("context", {}), ensure_ascii=False),
            json.dumps({str(k): v for k, v in session.get("vehicle_shown", {}).items()}, ensure_ascii=False),
            datetime.now().isoformat(),
        ))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[save_session] Erreur: {e}")


def load_session(user_id: str) -> dict | None:
    try:
        conn = _get_session_db_conn()
        row = conn.execute(
            "SELECT history, user_data, context, vehicle_shown FROM sessions WHERE user_id = ?",
            (user_id,)
        ).fetchone()
        conn.close()
        if row:
            _vs_raw = json.loads(row[3] or "{}")
            return {
                "history":       json.loads(row[0] or "[]"),
                "user_data":     json.loads(row[1] or "{}"),
                "context":       json.loads(row[2] or "{}"),
                "vehicle_shown": {int(k): v for k, v in _vs_raw.items()},
            }
    except Exception as e:
        print(f"[load_session] Erreur: {e}")
    return None


# =============================
# NETTOYAGE HTML
# =============================

def strip_html(text: str) -> str:
    if not text:
        return text
    text = re.sub(r'"\s*target="_blank"[^>]*>', '', text)
    text = re.sub(r'\s*class="[^"]*">', '', text)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'  +', ' ', text)
    return text.strip()


def extract_proposition_number(message: str) -> int | None:
    """Détecte si le message fait référence à une proposition numérotée (1, 2 ou 3)."""
    msg = message.lower().strip()
    # Ordinaux français
    if any(w in msg for w in ['première', 'premier', '1re', '1ère', 'premièr']):
        return 1
    if any(w in msg for w in ['deuxième', 'second', 'seconde', '2e', '2ème']):
        return 2
    if any(w in msg for w in ['troisième', '3e', '3ème']):
        return 3
    # "proposition 2", "option 3", "véhicule 1", "la 2", "le 3", etc.
    m = re.search(
        r'(?:proposition|option|v[ée]hicule|voiture|choix|auto|celui|celle|le|la)\s*[#n°]?\s*([123])\b',
        msg
    )
    if m:
        return int(m.group(1))
    # Chiffre seul en contexte de sélection
    m = re.search(r'\b([123])\b', msg)
    if m:
        return int(m.group(1))
    return None


def detect_rdv_intent(message: str) -> bool:
    """
    Détecte EXPLICITEMENT une demande de RDV ou contact concessionnaire.
    NE PAS déclencher sur 'ok', 'oui', 'd'accord' seuls.
    """
    msg = message.lower().strip()
    rdv_patterns = [
        'rendez-vous', 'rendez vous', 'prendre rdv', 'un rdv',
        'visiter', 'voir ce v\u00e9hicule', 'voir cette auto', 'voir cette voiture',
        'contacter', 'me contacter', 'contacter la concession',
        'mettre en contact', 'contact avec', 'me mettre en contact',
        'je veux \u00eatre contact\u00e9', 'je voudrais \u00eatre contact\u00e9',
        'je le veux', 'je la veux', "je veux l'acheter",
        'je suis int\u00e9ress\u00e9 et', 'int\u00e9ress\u00e9 par la proposition',
        'je veux ce v\u00e9hicule', 'je veux cette auto',
        'appeler le concessionnaire', 't\u00e9l\u00e9phoner',
        'je suis pr\u00eat', 'je suis pret', '\u00e7a me convient',
        'je veux y aller', 'je veux le voir', 'comment contacter',
        'transmets mon dossier', 'je suis int\u00e9ress\u00e9',
        'on y va', 'je le prends', 'je veux proc\u00e9der',
        'je suis convaincu', 'comment proc\u00e9der', 'met moi en contact',
        'mets moi en contact', 'contact avec eux',
    ]
    return any(p in msg for p in rdv_patterns)


def has_vehicle_interest(message: str) -> bool:
    """
    Détecte si l'utilisateur exprime un intérêt pour UN véhicule
    sans numéro explicite — 'je le veux', 'celui-là', 'rdv', etc.
    """
    msg = message.lower().strip()
    patterns = [
        'je le veux', 'je la veux', 'je veux celui',
        'je veux celle', 'celui-là', 'celle-là',
        'ce véhicule', 'cette voiture', 'cette auto',
        'je suis intéressé', 'je suis intéressée',
        "ça m'intéresse", "ca m'intéresse",
        'je le prends', 'je la prends',
        "je veux en savoir plus", "plus d'info",
        "plus d'information", 'rdv', 'rendez-vous',
        'visiter', 'voir ce véhicule', 'voir cette auto',
    ]
    return any(p in msg for p in patterns)


def remove_vehicle_bullets(text: str) -> str:
    """Supprime les listes bullets de véhicules dans la réponse Gemini.
    Les fiches HTML les remplacent — le texte ne doit contenir qu'une courte analyse."""
    _SPECS = r'Prix|Kilométrage|Moteur|Transmission|Carburant|Traction|Couleur|VIN|Concessionnaire|Localisation|Options|Fiabilité|Taxes|TPS|TVQ|Stock|LIEN|Version|Marché|Ville'
    vehicle_patterns = [
        # bullet simple : • Prix ou * Prix ou - Prix
        rf'^\s*[•\*\-]\s*({_SPECS})',
        # bullet markdown : * **Prix :** ou * **Moteur** :
        rf'^\s*\*\s*\*{{1,2}}({_SPECS})\*{{0,2}}\s*[:\*]',
        r'^\s*[•\*\-]\s*\d{4}\s+\w+',
        r'🚗|★\s+\d{4}|LIEN ANNONCE|ID Force Occasion|N°\s*Stock',
        r'^\s*Prix\s*:\s*[\d\s\u00a0]+\$',
        r'^\s*Taxes\s*QC\s*:',
        r'^\s*(TPS|TVQ|Total avec taxes)\s*:',
    ]
    lines = text.split('\n')
    clean_lines = [l for l in lines if not any(re.search(p, l) for p in vehicle_patterns)]
    result = re.sub(r'\n{3,}', '\n\n', '\n'.join(clean_lines))
    return result.strip()


# =============================
# SESSION MANAGEMENT
# =============================

def get_session(user_id: str) -> dict:
    if user_id not in sessions:
        # ── Essayer de charger depuis SQLite (survive aux restarts) ──
        persisted = load_session(user_id)
        if persisted:
            sessions[user_id] = {
                "history":         persisted["history"],
                "user_data":       {
                    "budget": None, "vehicle_type": None,
                    "preferred_make": None, "preferred_model": None,
                    "location": None, "financing": None,
                    "annual_km": None, "trade_in": None,
                    **persisted.get("user_data", {}),
                },
                "context": {
                    "last_listings": [], "last_results": [],
                    "viewed_urls": [], "last_intent": None, "last_query": None,
                    **persisted.get("context", {}),
                },
                "vehicle_shown": {},
                "model_statements": [],
                "created_at": datetime.now().isoformat(),
            }
            print(f"[get_session] Session restaurée depuis SQLite pour {user_id} ({len(persisted['history'])} messages)")
        else:
            sessions[user_id] = {
                "history": [],
                "user_data": {
                    "budget": None, "vehicle_type": None,
                    "preferred_make": None, "preferred_model": None,
                    "location": None, "financing": None,
                    "annual_km": None, "trade_in": None,
                },
                "context": {
                    "last_listings": [], "last_results": [],
                    "viewed_urls": [], "last_intent": None, "last_query": None,
                },
                "vehicle_shown": {},
                "model_statements": [],
                "created_at": datetime.now().isoformat(),
            }
            # Charger la mémoire persistante depuis SQLite
            try:
                import sys
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                from database import get_user_memory
                saved = get_user_memory(user_id)
                if saved:
                    if saved.get("budget"):
                        sessions[user_id]["user_data"]["budget"] = saved["budget"]
                    if saved.get("preferred_make"):
                        sessions[user_id]["user_data"]["preferred_make"] = saved["preferred_make"]
                    if saved.get("financing"):
                        sessions[user_id]["user_data"]["financing"] = saved["financing"]
            except Exception:
                pass
    return sessions[user_id]


def update_context(user_id: str, intent_data: dict, response: str):
    session = get_session(user_id)
    ctx = session["context"]
    # Met à jour uniquement l'état opérationnel — PAS de budget extrait de la réponse
    ctx["last_intent"] = intent_data.get("intent")
    urls = intent_data.get("urls", [])
    if urls:
        ctx["viewed_urls"].extend(urls)
        ctx["viewed_urls"] = list(set(ctx["viewed_urls"]))[-10:]
    # Tracker si la suggestion de contact a déjà été faite
    CONTACT_SUGGESTION_PHRASES = [
        "souhaitez-vous que je vous mette en contact",
        "souhaitez-vous être mis en contact",
        "voulez-vous que je vous mette en contact",
        "souhaitez-vous contacter",
    ]
    if isinstance(response, str) and any(p in response.lower() for p in CONTACT_SUGGESTION_PHRASES):
        ctx["contact_suggestion_made"] = True


def build_context_summary(user_id: str):
    session = get_session(user_id)
    ud = session["user_data"]
    ctx = session["context"]
    history = session["history"]
    parts = []
    if ud.get("budget"):
        parts.append(f"Budget mentionné: {ud['budget']}$")
    if ud.get("preferred_make"):
        parts.append(f"Marque préférée: {ud['preferred_make']}")
    if ud.get("location"):
        parts.append(f"Région: {ud['location']}")
    if ud.get("financing"):
        parts.append(f"Mode acquisition: {ud['financing']}")
    # Résumé complet des derniers véhicules présentés (titre + prix + dealer + ville)
    last_results = ctx.get("last_results", [])
    if last_results:
        parts.append("VÉHICULES PRÉSENTÉS DANS CETTE CONVERSATION :")
        for i, r in enumerate(last_results[:5], 1):
            titre = r.get("title", "")
            prix  = r.get("price", "")
            ville = r.get("city", "")
            dealer = r.get("dealer_name", "")
            url   = r.get("url", "")
            parts.append(f"  #{i} {titre} — {prix}$ — {dealer}, {ville} — {url}")
    elif ctx.get("last_listings"):
        listings_summary = ", ".join([f"#{i+1} {l}" for i, l in enumerate(ctx["last_listings"][:3])])
        parts.append(f"Derniers véhicules trouvés (URLs): {listings_summary}")
    if ctx.get("contact_suggestion_made"):
        parts.append("STATUT CONTACT : La suggestion de mise en contact a DÉJÀ été faite dans cette conversation. NE PAS la reposer. Si l'utilisateur dit oui/ok/d'accord → passer directement à la collecte des coordonnées.")
    context_str = "\n".join(parts) if parts else ""
    history_str = ""
    for msg in history[-10:]:
        role = "Utilisateur" if msg["role"] == "user" else "Agent"
        history_str += f"{role}: {msg['content'][:500]}\n"
    return context_str, history_str


# =============================
# INVENTORY CACHE SEARCH
# =============================

STOPWORDS_FR = {
    "recherche", "cherche", "trouve", "montre", "propose", "liste",
    "donne", "veux", "voudrais", "aimerais", "besoin", "occasion",
    "usagé", "usagée", "voiture", "auto", "automobile", "vehicule",
    "véhicule", "dans", "pour", "avec", "sans", "sous", "entre",
    "environ", "autour", "Quebec", "Québec", "Canada", "province",
}


def _run_cache_sql(cursor, conditions: list, params: list, limit: int) -> list:
    sql = f"""
        SELECT url, source, title, price, mileage, year, make, model,
               city, province, dealer_name, dealer_phone, vin, color,
               transmission, drivetrain, fuel_type, engine, trim,
               avg_market_price, price_diff, price_status,
               tps, tvq, total_taxes, total_with_taxes,
               options, vehicle_id, stock_number, raw_content, scraped_at
        FROM inventory_cache
        WHERE {" AND ".join(conditions)}
        ORDER BY scraped_at DESC
        LIMIT ?
    """
    params_copy = list(params) + [limit]
    cursor.execute(sql, params_copy)
    return cursor.fetchall()


def _rows_to_dicts(rows) -> list[dict]:
    results = []
    for row in rows:
        results.append({
            "url":              row["url"],
            "source":           row["source"],
            "title":            row["title"],
            "price":            row["price"],
            "mileage":          row["mileage"],
            "year":             row["year"],
            "make":             row["make"],
            "model":            row["model"],
            "city":             row["city"],
            "province":         row["province"],
            "dealer_name":      row["dealer_name"],
            "dealer_phone":     row["dealer_phone"],
            "vin":              row["vin"],
            "color":            row["color"],
            "transmission":     row["transmission"],
            "drivetrain":       row["drivetrain"],
            "fuel_type":        row["fuel_type"],
            "engine":           row["engine"],
            "trim":             row["trim"],
            "avg_market_price": row["avg_market_price"],
            "price_diff":       row["price_diff"],
            "price_status":     row["price_status"],
            "tps":              row["tps"],
            "tvq":              row["tvq"],
            "total_taxes":      row["total_taxes"],
            "total_with_taxes": row["total_with_taxes"],
            "options":          row["options"],
            "vehicle_id":       row["vehicle_id"],
            "stock_number":     row["stock_number"],
            "raw_content":      row["raw_content"],
            "scraped_at":       row["scraped_at"],
        })
    return results


def search_inventory_cache(query: str, limit: int = 5, vehicle_filter: str = None,
                           fuel_filter: str = None, year_filter: str = None,
                           price_max: int = None, mileage_max: int = None,
                           drivetrain_filter: str = None) -> list[dict]:
    """
    Recherche flexible dans inventory_cache.
    1. Essai strict (AND) avec vehicle_filter ou query nettoyée
    2. Si 0 résultat → essai souple (OR) sur les 2 premiers mots-clés véhicule
    3. Si toujours 0 → essai sur make/model directement
    """
    try:
        print(f"[search_inventory_cache] DB_PATH={DB_PATH}")
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS inventory_cache (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source TEXT, vehicle_id TEXT, title TEXT, price REAL, mileage INTEGER,
                year INTEGER, make TEXT, model TEXT, city TEXT, province TEXT,
                dealer_name TEXT, dealer_phone TEXT, vin TEXT, color TEXT,
                transmission TEXT, drivetrain TEXT, fuel_type TEXT, engine TEXT, trim TEXT,
                avg_market_price REAL, price_diff REAL, price_status TEXT,
                tps REAL, tvq REAL, total_taxes REAL, total_with_taxes REAL,
                options TEXT, description TEXT, highway_consumption TEXT, city_consumption TEXT,
                photos TEXT, url TEXT, json_url TEXT, raw_content TEXT, stock_number TEXT, scraped_at TEXT,
                UNIQUE(source, vehicle_id)
            )
        """)
        conn.commit()
        try:
            cursor.execute("ALTER TABLE inventory_cache ADD COLUMN stock_number TEXT")
            conn.commit()
        except Exception:
            pass  # colonne déjà présente

        # Filtrer les termes financiers qui ne sont pas des véhicules
        FINANCIAL_STOPWORDS = {
            "budget", "dollar", "250", "300", "400", "500",
            "mois", "mensuel", "financement", "paiement",
            "taxes", "inclus", "environ", "approximatif"
        }
        if vehicle_filter:
            _vf_words = vehicle_filter.lower().split()
            _vf_clean = [w for w in _vf_words if w not in FINANCIAL_STOPWORDS]
            if _vf_clean:
                vehicle_filter = " ".join(_vf_clean)

        # Mapping catégories → modèles réels
        CATEGORY_MAP = {
            "vus":          "Escape Equinox RDX MDX Explorer Bronco Rogue Tucson Sportage Seltos Durango Traverse Blazer Murano Outlander Palisade Telluride Sorento Tonale GV70 X2 Encore Forester Outback Crosstrek Trailblazer Terrain Acadia",
            "suv":          "Escape Equinox RDX MDX Explorer Bronco Rogue Tucson Sportage Seltos Durango Traverse Blazer Murano Outlander Palisade Telluride Sorento",
            "luxe":         "BMW Audi Mercedes Lexus Acura Infiniti Cadillac Lincoln Genesis Volvo Porsche Alfa",
            "\u00e9lectrique": "Tesla Bolt Leaf Ioniq EV6 EV9 Ariya Mach-E Lightning Solterra bZ4X",
            "electrique":   "Tesla Bolt Leaf Ioniq EV6 EV9 Ariya Mach-E Lightning Solterra bZ4X",
            "hybride":      "Prius RAV4 Escape Tucson Santa Outlander Pacifica Wrangler CR-V Elantra Sonata",
            "camionnette":  "F-150 Silverado Ram Tundra Tacoma Frontier Titan Colorado Canyon Ranger Maverick Sierra",
            "truck":        "F-150 Silverado Ram Tundra Tacoma Frontier Titan Colorado Canyon Ranger Maverick Sierra",
            "pickup":       "F-150 Silverado Ram Tundra Tacoma Frontier Titan Colorado Canyon Ranger Maverick Sierra",
            "pick":         "F-150 Silverado Ram Tundra Tacoma Frontier Titan Colorado Canyon Ranger Sierra",
            "berlin":       "Civic Corolla Camry Accord Elantra Sonata Mazda3 Altima Jetta Model 3 Integra Malibu Legacy",
            "berline":      "Civic Corolla Camry Accord Elantra Sonata Mazda3 Altima Jetta Model 3 Integra Malibu Legacy",
            "sedan":        "Civic Corolla Camry Accord Elantra Sonata Mazda3 Altima Jetta Model 3 Integra Malibu Legacy",
            "fourgonnette": "Odyssey Sienna Carnival Pacifica Caravan Sedona",
            "minivan":      "Odyssey Sienna Carnival Pacifica Caravan Sedona",
            "sport":        "Mustang Camaro Challenger BRZ Supra Miata Corvette GTI WRX Veloster Civic Type R",
            "coupe":        "Mustang Camaro Challenger BRZ Supra Miata Corvette GTI WRX Veloster",
            "compact":      "Civic Corolla Elantra Mazda3 Jetta Golf Forte Sentra",
            "compacte":     "Civic Corolla Elantra Mazda3 Jetta Golf Forte Sentra Kicks Venue Trax",
            "economique":   "Civic Corolla Elantra Mazda3 Accent Rio Yaris Fit Spark Versa Micra",
            "mazda3":       "Mazda3",
            "mazda 3":      "Mazda3",
            "mazda6":       "Mazda6",
            "mazda 6":      "Mazda6",
            "cx3":          "CX-3",
            "cx 3":         "CX-3",
            "cx5":          "CX-5",
            "cx 5":         "CX-5",
            "cx9":          "CX-9",
            "cx 9":         "CX-9",
        }

        # Sauvegarder vehicle_filter original avant réécriture CATEGORY_MAP
        _orig_vf = (vehicle_filter or '').lower()

        # Remplacer la query si c'est une catégorie connue
        query_lower = (vehicle_filter or query).lower().strip()
        for category, models in CATEGORY_MAP.items():
            if category in query_lower:
                vehicle_filter = models
                break

        # Choisir la meilleure source de termes de recherche
        search_text = vehicle_filter or query
        raw_kw = [k.strip() for k in search_text.lower().split() if len(k.strip()) > 2]
        # Filtrer les stopwords français/génériques
        keywords = [k for k in raw_kw if k not in {s.lower() for s in STOPWORDS_FR}]
        if not keywords:
            keywords = raw_kw  # garde les originaux si tout filtré

        print(f"[search_inventory_cache] query={repr(query)} | vehicle_filter={repr(vehicle_filter)} | keywords={keywords}")

        # ── Recherche directe fuel_type si fuel générique (pas de marque spécifique) ──
        _KNOWN_MAKES = ['toyota', 'honda', 'ford', 'kia', 'hyundai', 'mazda', 'nissan',
                        'chevrolet', 'dodge', 'ram', 'jeep', 'subaru']
        if fuel_filter and not any(m in _orig_vf for m in _KNOWN_MAKES):
            try:
                cursor.execute("""
                    SELECT * FROM inventory_cache
                    WHERE LOWER(fuel_type) LIKE ?
                    AND price IS NOT NULL AND price > 0
                    ORDER BY price ASC
                    LIMIT ?
                """, (f'%{fuel_filter.lower()}%', limit))
                _direct_rows = cursor.fetchall()
                if _direct_rows:
                    print(f"[search_inventory_cache] Recherche directe fuel_type={fuel_filter} → {len(_direct_rows)} résultat(s)")
                    conn.close()
                    return [dict(r) for r in _direct_rows]
            except Exception as e:
                print(f"[search] fuel direct error: {e}")

        # ── Conditions extra (fuel_type, year, price, mileage, drivetrain) ──
        extra_conditions = []
        if fuel_filter:
            extra_conditions.append(f"LOWER(fuel_type) LIKE '%{fuel_filter.lower()}%'")
        if year_filter:
            extra_conditions.append(f"year = {year_filter}")
        if price_max:
            extra_conditions.append(f"price <= {int(price_max)}")
        if mileage_max:
            extra_conditions.append(f"mileage <= {int(mileage_max)}")
        if drivetrain_filter:
            extra_conditions.append(f"LOWER(drivetrain) LIKE '%{drivetrain_filter.lower()}%'")

        # ── Essai 1 : AND strict sur max 3 mots-clés véhicule ──────────────
        kw_strict = keywords[:3]
        conditions = []
        params = []
        for kw in kw_strict:
            conditions.append("(LOWER(title) LIKE ? OR LOWER(make) LIKE ? OR LOWER(model) LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
        conditions.extend(extra_conditions)

        rows = []
        if conditions:
            rows = _run_cache_sql(cursor, conditions, params, limit)
            print(f"[search_inventory_cache] Essai AND strict ({kw_strict}) → {len(rows)} résultat(s)")

        # ── Essai 2 : OR sur les 2 premiers mots-clés si 0 résultat ────────
        if not rows and len(keywords) >= 1:
            kw_or = keywords[:2]
            or_parts = []
            or_params = []
            for kw in kw_or:
                or_parts.append("LOWER(title) LIKE ?")
                or_parts.append("LOWER(make) LIKE ?")
                or_parts.append("LOWER(model) LIKE ?")
                or_params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])
            rows = _run_cache_sql(cursor, [f"({' OR '.join(or_parts)})"] + extra_conditions, or_params, limit)
            print(f"[search_inventory_cache] Essai OR souple ({kw_or}) → {len(rows)} résultat(s)")

        # ── Essai 3 : raw_content si toujours 0 ────────────────────────────
        if not rows and keywords:
            kw_raw = keywords[0]
            rows = _run_cache_sql(
                cursor,
                ["(LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ?)"] + extra_conditions,
                [f"%{kw_raw}%", f"%{kw_raw}%"],
                limit
            )
            print(f"[search_inventory_cache] Essai raw_content ({kw_raw}) → {len(rows)} résultat(s)")

        conn.close()
        results = _rows_to_dicts(rows)

        for r in results[:3]:
            print(f"  • {r.get('year','')} {r.get('make','')} {r.get('model','')} | {r.get('price','?')}$ | {r.get('city','?')} | {r.get('url','?')[:60]}")

        return results

    except Exception as e:
        print(f"[search_inventory_cache] Erreur: {e}")
        return []


def format_cache_results_for_prompt(results: list[dict]) -> str:
    if not results:
        return ""

    lines = ["=== VÉHICULES DISPONIBLES (données réelles Force Occasion) ===\n"]
    for i, r in enumerate(results, 1):
        prix  = r.get("price", "")
        titre = r.get("title", "")

        # Skip véhicules avec données essentielles manquantes
        if not prix or not titre:
            continue

        annee           = r.get("year", "") or ""
        marque          = r.get("make", "") or ""
        modele          = r.get("model", "") or ""
        version         = r.get("trim", "") or ""
        km              = r.get("mileage", "") or ""
        ville           = r.get("city", "") or ""
        province        = r.get("province", "") or ""
        concessionnaire = r.get("dealer_name", "") or ""
        telephone       = r.get("dealer_phone", "") or ""
        transmission    = r.get("transmission", "") or ""
        moteur          = r.get("engine", "") or ""
        carburant       = r.get("fuel_type", "") or ""
        traction        = r.get("drivetrain", "") or ""
        couleur         = r.get("color", "") or ""
        niv             = r.get("vin", "") or ""
        fo_id           = r.get("vehicle_id", "") or ""
        stock_number    = r.get("stock_number", "") or ""
        options         = (r.get("options", "") or "")[:200]
        source          = r.get("source", "")

        # CORRECTION 1 — Lien direct : utiliser le champ url de la DB (jamais un lien générique)
        url_annonce = r.get("url", "") or ""

        # CORRECTION 2 — Taxes : utiliser les valeurs déjà calculées dans la DB
        tps            = r.get("tps", "")
        tvq            = r.get("tvq", "")
        total_with_taxes = r.get("total_with_taxes", "")
        if not tps or not tvq:
            try:
                prix_num = float(str(prix).replace(",", "").replace("$", "").strip())
                tps = round(prix_num * 0.05, 2)
                tvq = round(prix_num * 0.09975, 2)
                total_with_taxes = round(prix_num + tps + tvq, 2)
            except Exception:
                total_with_taxes = ""
        elif not total_with_taxes:
            try:
                prix_num = float(str(prix).replace(",", "").replace("$", "").strip())
                total_with_taxes = round(prix_num + float(str(tps)) + float(str(tvq)), 2)
            except Exception:
                total_with_taxes = ""

        # CORRECTION 3 — Prix marché : utiliser avg_market_price, price_diff, price_status de la DB
        prix_marche  = r.get("avg_market_price", "") or ""
        price_diff   = r.get("price_diff", "") or ""
        price_status = r.get("price_status", "") or ""

        # Statut prix lisible
        if price_status and prix_marche:
            statut_prix = f"{price_status} (marché moy: {prix_marche}$, écart: {price_diff}$)"
        elif prix_marche:
            statut_prix = f"Marché moyen: {prix_marche}$"
        else:
            statut_prix = ""

        # Score fiabilité
        reliability = "Données cohérentes"
        try:
            prix_float = float(str(prix).replace(",", "").replace("$", "").strip())
            km_float = float(str(km)) if km else 0
            prix_marche_float = float(str(prix_marche)) if prix_marche else 0
            if prix_marche_float > 0 and prix_float < prix_marche_float * 0.85:
                reliability = "PRIX SUSPECT — vérifier l'état du véhicule"
            elif prix_marche_float > 0 and prix_float > prix_marche_float * 1.15:
                reliability = "Prix au-dessus du marché — négocier"
            elif km_float > 150000:
                reliability = "Kilométrage élevé — inspection recommandée"
        except Exception:
            pass

        _fields = [f"Véhicule #{i} — {source}"]
        _fields.append(f"  Titre         : {annee} {marque} {modele} {version}".rstrip())
        _fields.append(f"  Prix          : {prix}$")
        if statut_prix:
            _fields.append(f"  Statut prix   : {statut_prix}")
        if total_with_taxes:
            _fields.append(f"  Taxes QC      : TPS {tps}$ + TVQ {tvq}$ = Total {total_with_taxes}$")
        if km:
            _fields.append(f"  Kilométrage   : {km} km")
        if ville or province:
            _fields.append(f"  Localisation  : {ville}{', ' + province if province else ''}")
        if concessionnaire:
            _fields.append(f"  Concessionnaire: {concessionnaire}")
        if moteur:
            _fields.append(f"  Moteur        : {moteur}")
        if transmission:
            _fields.append(f"  Transmission  : {transmission}")
        if carburant:
            _fields.append(f"  Carburant     : {carburant}")
        if traction:
            _fields.append(f"  Traction      : {traction}")
        if couleur:
            _fields.append(f"  Couleur       : {couleur}")
        _fields.append(f"  Fiabilité     : {reliability}")
        line = "\n".join(_fields) + "\n"
        lines.append(line)

    lines.append("\n=== FIN DES DONNÉES FORCE OCCASION ===")
    return "\n".join(lines)


# =============================
# SYSTEM PROMPT
# =============================

SYSTEM_PROMPT = """
## IDENTITÉ

Tu es 229Voitures, un conseiller automobile québécois qui protège 
les acheteurs contre les mauvaises décisions financières en concession.

Ta mission : trouver le meilleur véhicule disponible dans l'inventaire 
partenaire et armer l'acheteur avec toutes les informations pour ne pas 
se faire avoir.

Langue : français québécois, tutoiement obligatoire, ton direct et chaleureux.
Pas de "je suis désolé", pas d'"unfortunately", pas de formules corporatives.
Tu es un coach, pas un vendeur.

L'inventaire provient de concessionnaires partenaires (Force Occasion).
D'autres sources d'inventaire pourront s'ajouter dans le futur.

Tu peux donner des recommandations générales de modèles sans inventaire,
mais sans jamais inventer de données précises (prix, kilométrage, 
numéro de stock).


## RÈGLES ABSOLUES — NE JAMAIS VIOLER

1. INVENTAIRE UNIQUEMENT
   Tu ne mentionnes QUE les véhicules retournés par la recherche DB.
   Si un véhicule n'est pas dans les résultats → il n'existe pas pour toi.
   Tu n'inventes jamais un prix, un kilométrage, un VIN, un numéro de stock.

2. EXACTEMENT 3 FICHES
   Tu décris UNIQUEMENT les 3 véhicules fournis dans le contexte.
   Jamais de Véhicule #4, #5 ou plus dans le texte.
   Le texte et les fiches affichées doivent être parfaitement alignés.

3. PAS DE FICHES SANS DEMANDE PRÉCISE
   Les fiches s'affichent SEULEMENT si le client nomme un modèle précis
   ("je cherche un RAV4", "as-tu des Kona hybrides").
   Une demande vague → clarification d'abord, fiches ensuite.

4. TUTOIEMENT OBLIGATOIRE
   Tu tutoies toujours, sans exception.
   Jamais de "vous" sauf si le client utilise lui-même le vouvoiement.

5. PAS D'EXCUSE, PAS DE REMPLISSAGE
   Tu ne t'excuses jamais de ne pas trouver un véhicule.
   Pas de "malheureusement", "je suis désolé", "je comprends votre situation".
   Tu vas droit au but avec une solution ou une alternative.


## FLUX DE CONVERSATION

### PRINCIPE DIRECTEUR
Chaque réponse doit faire avancer la conversation vers :
1. Une décision concrète du client
OU
2. Une action concrète (voir le véhicule, appeler le concessionnaire)
Ne jamais terminer une réponse sans direction claire.

### QUESTIONS D'OPINION ET DE RENSEIGNEMENT
Si l'utilisateur pose une question d'opinion
ou de renseignement sur un modèle :
- "que penses-tu du Seltos 2022 ?"
- "quels sont les problèmes du CR-V 2019 ?"
- "est-ce que le RAV4 est fiable ?"

→ Répondre avec ton opinion et tes connaissances
→ NE PAS chercher dans la DB
→ NE PAS afficher de fiches
→ Terminer avec : "Tu veux que je te montre
  ce qu'on a en inventaire ?"

Les fiches s'affichent SEULEMENT si le client
dit explicitement :
"montre-moi", "as-tu", "je cherche",
"trouve-moi", "je veux voir"

### ÉTAPE 1 — CLARIFICATION (si demande vague)
Une demande est vague si elle ne contient pas de modèle précis.
Exemples vagues : "je cherche un VUS", "je veux une auto fiable", 
"je magasine", "je veux échanger mon véhicule".

→ Poser UNE seule question qui couvre budget ET préférence de modèle.
→ Ne pas chercher dans la DB. Ne pas afficher de fiches.
→ Une fois la réponse reçue → passer à l'Étape 2.

Exemple :
"Quel modèle t'intéresse et quel est ton budget approximatif 
(mensuel ou comptant) ?"

### ÉTAPE 2 — RECHERCHE ET FICHES (si demande précise)
Une demande est précise si elle contient un modèle ou une marque.
Exemples précis : "je cherche un RAV4", "as-tu des Kona hybrides", 
"montre-moi des Civic 2020".

→ Chercher dans inventory_cache.
→ Afficher exactement 3 fiches (ou moins si moins disponible).
→ Décrire UNIQUEMENT ces véhicules dans le texte, dans l'ordre.
→ Nommer : Proposition 1, Proposition 2, Proposition 3.
→ Terminer avec UNE question pertinente (budget, financement, 
   inspection, etc.)

### ÉTAPE 3 — SUIVI ET RDV
Si le client exprime de l'intérêt pour une proposition spécifique :
→ Répondre sur CE véhicule uniquement (prix, mécanique, alertes).
→ Proposer le RDV seulement quand le client a clairement choisi.
→ Ne jamais proposer le RDV avant que le client ait confirmé 
   son intérêt pour un véhicule précis.


## AFFICHAGE

### FORMAT DES PROPOSITIONS
Chaque véhicule est présenté comme "Proposition 1", "Proposition 2", 
"Proposition 3" — jamais "Véhicule #1" ou "Résultat 1".

### TEXTE ET FICHES ALIGNÉS
Le texte de ta réponse décrit exactement les mêmes véhicules 
que les fiches affichées, dans le même ordre.
Si 3 fiches → 3 descriptions. Si 2 fiches → 2 descriptions.
Jamais de véhicule mentionné dans le texte qui n'a pas de fiche.

### CONTENU DE CHAQUE DESCRIPTION
Pour chaque proposition, mentionner :
- Positionnement marché (bon prix / dans la moyenne / prix élevé)
- Un point fort ET un point de vigilance (kilométrage, année, 
  rappels connus)
- Le total avec taxes si pertinent

### RÉPONSES COURTES
Maximum 3-4 lignes de texte par proposition.
Pas de bullet points excessifs.
Pas de répétition des données déjà visibles dans la fiche.
Une seule question à la fin, pas plusieurs.

### SI AUCUN RÉSULTAT
Ne pas s'excuser. Proposer immédiatement l'alternative la plus proche :
"Je n'ai pas de [modèle]. Voici ce que j'ai de plus proche :"
→ Afficher 3 fiches alternatives pertinentes.


## PROTECTION ACHETEUR

### FRAIS ILLÉGAUX AU QUÉBEC
Au Québec, le prix affiché doit être le prix total — tout inclus.
Les frais suivants sont ILLÉGAUX s'ils ne sont pas inclus dans le prix :
- Frais de préparation / livraison / documentation
- Frais de dossier de financement
- Frais d'immatriculation gonflés
→ Si le client mentionne ces frais : l'informer immédiatement 
  que c'est contraire à l'OPC et qu'il peut refuser de payer.

### PRODUITS F&I À SURVEILLER
Mentionner ces produits seulement si le client parle de financement.
Toujours présenter les deux côtés (utile / inutile selon le contexte) :

- Assurance vie/invalidité sur prêt → souvent plus chère qu'une 
  assurance personnelle. Rarement nécessaire.
- Garantie esthétique / Vinlock / protection tissu → marge élevée, 
  valeur faible. À éviter dans la majorité des cas.
- Garantie prolongée → peut être utile sur véhicule hors garantie 
  usine ou à haut kilométrage. Négocier le prix.
- Vente liée taux/produit → si le taux préférentiel est conditionnel 
  à l'achat d'un produit F&I, calculer le coût réel avant d'accepter.

### ALERTES MÉCANIQUES PAR MODÈLE
Mentionner automatiquement si ces modèles sont discutés :
- GMC Acadia 2017-2022 → rappel transmission "Shift to Park"
- Chevrolet Equinox 2.4L 2010-2017 → consommation d'huile excessive
- Ford Explorer 2011-2017 → fuite d'échappement dans l'habitacle
- Honda CR-V 1.5T 2017-2019 → dilution d'huile par essence en hiver
- Subaru 2013-2015 → joint de culasse, vérifier historique entretien
- Jeep Cherokee 2014-2018 → transmission 9 vitesses problématique
- Mazda CX-7 2007-2012 → turbo fragile à haut kilométrage

### INSPECTION ET HISTORIQUE
Pour tout véhicule dépassant 80 000 km ou plus de 5 ans :
→ Recommander systématiquement une inspection mécanique indépendante.
→ Suggérer un rapport Carfax ou Équifax Auto avant l'achat.

### NÉGOCIATION
Si le prix est "élevé" selon price_status :
→ Mentionner l'écart exact avec le marché.
→ Suggérer de négocier en citant cet écart comme argument.
"Ce véhicule est 2 300$ au-dessus de la moyenne —
tu peux utiliser ça comme levier de négociation."

### AVANTAGE FISCAL CONCESSION VS PARTICULIER
Depuis 2025, la SAAQ calcule la TVQ sur la
valeur estimative Guide Hebdo pour les
véhicules de 14 ans et moins achetés d'un
particulier — même si le prix payé est plus bas.
En concession → TVQ calculée sur le prix réel payé.
→ Mentionner cet avantage fiscal quand le client
  compare achat en concession vs particulier.


## CALCULS

### TAXES QUÉBEC
Toujours calculer et afficher le total avec taxes :
- TPS : 5%
- TVQ : 9.975%
- Formule : Total = Prix × 1.14975
- Afficher : "TPS [montant]$ + TVQ [montant]$ = Total [montant]$"

### FINANCEMENT ESTIMÉ
Si le client parle de financement ou de budget mensuel :
Taux de référence : 7.99% (taux marché moyen au Québec)
Durées courantes : 60, 72, 84 mois
Formule mensualité :
M = (P × r) / (1 - (1 + r)^-n)
où P = montant financé, r = taux mensuel, n = nombre de mois

Toujours préciser que c'est une estimation :
"Estimation basée sur 7.99% sur 72 mois — 
le taux réel dépend de ton dossier de crédit."

### BUDGET MENSUEL
Si le client donne un budget mensuel :
→ Calculer le prix maximum qu'il peut se permettre.
→ Filtrer les propositions en conséquence.
→ Si aucun véhicule ne rentre dans le budget :
   "Avec 400$/mois sur 72 mois, ton budget d'achat 
   est d'environ 22 000$ taxes incluses. 
   Voici ce que j'ai dans cette fourchette :"

### PROGRAMMES GOUVERNEMENTAUX
Si le véhicule est PHEV ou électrique,
mentionner qu'il existe des programmes
de rabais (Roulez Vert, iVZE).

RÈGLE ABSOLUE :
Ces rabais s'appliquent UNIQUEMENT aux
véhicules NEUFS achetés chez un
concessionnaire autorisé.
Les véhicules d'OCCASION ne sont PAS
admissibles — ne jamais suggérer le contraire.
Rediriger vers roulezvert.gouv.qc.ca
pour les détails officiels.


## TON ET COMPORTEMENT

### STYLE
Direct, chaleureux, franc. Tu parles comme un ami qui s'y connaît 
en auto — pas comme un robot corporatif.
Tutoiement obligatoire. Phrases courtes. Pas de jargon inutile.

### COACH, PAS ESCLAVE
Tu dis la vérité même si elle déplaît.
Si le budget ne suffit pas : "Il te manque 200$/mois pour ce véhicule. 
On ajuste le budget ou on cherche moins cher ?"
Si le véhicule est surévalué : "Ce prix est 3 000$ trop élevé. 
Négocie ou on regarde autre chose ?"
Tu proposes toujours une solution concrète, jamais juste un constat.

### AIDE À LA DÉCISION
Tu aides activement le client à choisir.
Tu peux dire :
"À ta place, je prendrais la Proposition 2 — meilleur rapport km/prix."
"Le meilleur choix ici c'est le RAV4 Prime si ton budget le permet."
Ne pas rester neutre quand le client hésite — prendre position.

### LONGUEUR DES RÉPONSES
- Question simple → 2-3 phrases max
- Présentation de fiches → 2-3 lignes par proposition + 1 question
- Conseil protection → 4-5 lignes max
Jamais de longs paragraphes. Jamais de listes à 8 points.

### CE QUE TU NE DIS JAMAIS
- "Je suis désolé de ne pas pouvoir..."
- "Malheureusement..."
- "En tant que conseiller automobile..."
- "N'hésitez pas à..."
- "Je comprends votre frustration..."
→ Ces phrases sont interdites. Va directement à la solution.

### SUJETS HORS INVENTAIRE
Si on te parle d'un véhicule hors inventaire (Bugatti, Ferrari, etc.) :
Réponds en 2-3 lignes maximum, puis ramène vers l'inventaire :
"C'est une belle machine, mais hors de notre inventaire. 
Tu cherches quelque chose de précis dans notre sélection ?"
"""

INTENT_PROMPT = """
Analyse ce message utilisateur et retourne UNIQUEMENT un objet JSON avec l'intention et les données extraites.

Message: "{message}"
Contexte conversation: {context}

Retourne exactement ce format JSON :
{{
  "intent": "CHAT" | "SEARCH" | "ANALYZE_URL" | "COMPARE_URLS" | "CHECK_VIN" | "FOLLOWUP",
  "urls": [],
  "vin": null,
  "query": null,
  "site": null,
  "count": 3,
  "followup_action": null,
  "vehicle_filter": null
}}

Règles d'intention :

RÈGLE FONDAMENTALE DE CLASSIFICATION :
Question clé : "L'utilisateur mentionne-t-il un véhicule, une marque, un modèle ou une catégorie ?"

- SEARCH : SI OUI — l'utilisateur mentionne un véhicule, une marque, un modèle ou une catégorie (toujours, peu importe la formulation)
  Exemples → SEARCH :
  - "aurais-tu des Kona" → SEARCH, vehicle_filter="hyundai kona"
  - "t'as-tu un Escape" → SEARCH, vehicle_filter="ford escape"
  - "je me magasine un VUS" → SEARCH, vehicle_filter="vus"
  - "c'est quoi tes prix sur les Civic" → SEARCH, vehicle_filter="honda civic"
  - "je pense à un Kona" → SEARCH, vehicle_filter="hyundai kona"
  - "qu'est-ce que t'as comme berline" → SEARCH, vehicle_filter="berline"
  - "show me some SUVs" → SEARCH, vehicle_filter="suv"
  - "do you have any Civics" → SEARCH, vehicle_filter="honda civic"
  - "j'aimerais voir des électriques" → SEARCH, vehicle_filter="électrique"
  - "je me cherche quelque chose d'économique" → SEARCH, vehicle_filter="économique"
  - "Trouve moi un Toyota RAV4 2021" → SEARCH, vehicle_filter="toyota rav4 2021"
  - "Cherche des Honda CRV sous 25000$" → SEARCH, vehicle_filter="honda crv"
  - "je recherche une Seltos 2022 au Québec" → SEARCH, vehicle_filter="kia seltos 2022"
  - "j'ai un Elantra, je veux un VUS" → SEARCH, vehicle_filter="vus"
  - "j'ai une berline, je cherche une camionnette" → SEARCH, vehicle_filter="camionnette"

EXCEPTION — QUESTIONS D'OPINION :
Ces messages doivent être classifiés CHAT
même s'ils mentionnent un modèle :
- "que penses-tu du Seltos 2022 ?"
- "est-ce que le RAV4 est fiable ?"
- "quels sont les problèmes du CR-V ?"
- "c'est quoi les défauts du Kona ?"
- "vaut-il la peine d'acheter un Tucson ?"

Mots-clés → CHAT (pas SEARCH) :
"que penses-tu", "penses-tu", "fiable",
"problèmes", "défauts", "avis", "opinion",
"vaut-il", "c'est bien", "recommandes-tu",
"quels sont les"

  EN CAS DE DOUTE → SEARCH.
  SAUF si le message contient un des
  mots-clés d'opinion ci-dessus → CHAT.

- CHAT : SI NON — question générale sans véhicule spécifique mentionné
  * "c'est quoi la différence entre AWD et 4x4" → CHAT
  * "comment négocier un prix" → CHAT
  * "c'est quoi les taxes au Québec" → CHAT
  * "explique-moi le financement" → CHAT
  * Salutations, remerciements, questions générales sans marque/modèle/catégorie

- ANALYZE_URL : le message contient exactement 1 URL
- COMPARE_URLS : le message contient 2 URL ou plus
- CHECK_VIN : le message contient un VIN (17 caractères alphanumériques)
- FOLLOWUP : l'utilisateur répond à une suggestion précédente
  * Sélection : "le premier", "le 2", "celui-là", "ce véhicule", "le moins cher" → followup_action="select_listing"
  * Comparaison : "compare-les", "lequel est le mieux?", "compare" → followup_action="compare"
  * VIN : "vérifie le VIN", "check le VIN", "rapport VIN" → followup_action="check_vin"
  * Plus : "montre-m'en plus", "d'autres options?" → followup_action="more_results"

Pour SEARCH extraire :
- query : termes de recherche exacts (marque, modèle, année, version, budget, ville)
- vehicle_filter : marque + modèle spécifique (ex: "kia seltos 2022")
  IMPORTANT — vehicle_filter = véhicule DÉSIRÉ uniquement.
  Si l'utilisateur mentionne un véhicule qu'il POSSÈDE ('j'ai un X', 'mon X actuel', 'je veux changer mon X'),
  vehicle_filter = le véhicule CHERCHÉ (Y), jamais X.
  Si budget mensuel mentionné → l'inclure dans query uniquement.
  Si trade-in mentionné → noter dans query, pas dans vehicle_filter.
- site : domaine concessionnaire si mentionné, null sinon
- count : nombre de résultats demandés (défaut 3)

Retourne UNIQUEMENT le JSON, aucune explication.
"""


# =============================
# INTENT DETECTION
# =============================

def detect_intent(message: str, context_summary: str) -> dict:
    # ─── Détection alerte email avant appel Gemini ───
    msg_lower = message.lower()
    ALERT_KEYWORDS = [
        "alerte", "alertez-moi", "notifie", "notifiez",
        "avertis", "préviens", "quand disponible",
        "m'avertir", "me notifier", "surveille",
    ]
    if any(k in msg_lower for k in ALERT_KEYWORDS):
        return {"intent": "CREATE_ALERT", "urls": [], "vin": None, "query": message,
                "site": None, "count": 3, "followup_action": None}

    # ─── Détection contact/lead avant appel Gemini ───
    CONTACT_KEYWORDS = [
        "contacter", "contacter la concession", "contacter le concessionnaire",
        "prendre rendez-vous", "rendez-vous", "appeler", "je veux acheter",
        "comment acheter", "comment contacter", "envoyer un message",
        "je suis intéressé", "intéressé par ce véhicule", "aller voir",
        "rdv", "prendre un rdv", "visiter", "je veux ce véhicule",
        "je le veux", "je la veux", "je le prends", "je la prends",
        "je veux celui", "je veux celle", "voir ce véhicule", "voir cette auto",
    ]
    if any(k in msg_lower for k in CONTACT_KEYWORDS):
        return {"intent": "LEAD_REQUEST", "urls": [], "vin": None, "query": message,
                "site": None, "count": 3, "followup_action": None}

    # ─── Détection F&I rapide avant appel Gemini ───
    FI_KEYWORDS = [
        "finance", "financement", "location", "mensualité", "paiement",
        "72 mois", "60 mois", "48 mois", "36 mois", "taux", "crédit",
        "garantie", "garantie prolongée", "protection", "assurance prêt",
    ]
    VEHICLE_BRANDS = [
        "toyota", "honda", "bmw", "audi", "mercedes", "hyundai", "kia",
        "ford", "chevrolet", "nissan", "mazda", "volkswagen", "lexus",
        "subaru", "mitsubishi", "jeep", "dodge", "ram", "gmc", "buick",
    ]
    has_fi = any(k in msg_lower for k in FI_KEYWORDS)
    has_vehicle = any(b in msg_lower for b in VEHICLE_BRANDS)
    if has_fi and has_vehicle:
        return {"intent": "GARANTIES", "urls": [], "vin": None, "query": message,
                "site": None, "count": 3, "followup_action": None}

    prompt = INTENT_PROMPT.format(message=message, context=context_summary)
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    try:
        raw = response.text.strip()
        match = re.search(r'\{.*\}', raw, re.DOTALL)
        if match:
            return json.loads(match.group())
    except Exception:
        pass
    return {"intent": "CHAT", "urls": [], "vin": None, "query": message, "site": None, "count": 3, "followup_action": None}


# =============================
# FOLLOWUP HANDLER
# =============================

def handle_followup(user_id: str, intent_data: dict, history_str: str, context_summary: str) -> dict:
    session = get_session(user_id)
    ctx = session["context"]
    action = intent_data.get("followup_action")
    # Données structurées en priorité sur les simples URLs
    last_results = ctx.get("last_results", [])

    if action == "select_listing" and last_results:
        # Passe les données réelles (pas des URLs) pour que Gemini ne puisse pas inventer
        vehicles_text = format_cache_results_for_prompt(
            [{**r, "raw_content": ""} for r in last_results]  # strip raw_content pour économiser tokens
        )
        prompt = f"""{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

{vehicles_text}

INSTRUCTION : L'utilisateur a sélectionné un des véhicules présentés ci-dessus. Identifie lequel d'après l'historique, résume SES données exactes, et propose : vérifier le VIN, comparer avec un autre, ou contacter le concessionnaire. Utilise UNIQUEMENT les données fournies ci-dessus."""
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "check_vin":
        prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nL'utilisateur veut vérifier le VIN. Demande-lui le numéro VIN (17 caractères alphanumériques). Max 2 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "compare" and len(last_results) >= 2:
        vehicles_text = format_cache_results_for_prompt(
            [{**r, "raw_content": ""} for r in last_results[:3]]
        )
        budget_label = f"{session['user_data']['budget']}$" if session["user_data"].get("budget") else "non précisé"
        prompt = f"""{SYSTEM_PROMPT}

Budget utilisateur: {budget_label}

{vehicles_text}

INSTRUCTION : Compare ces véhicules RÉELS et recommande le meilleur selon le rapport qualité/prix. Utilise UNIQUEMENT les données fournies. Max 5 phrases."""
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "more_results":
        # Cherche dans l'inventaire, pas sur le web
        last_query = ctx.get("last_query", "")
        if last_query:
            more = search_inventory_cache(last_query, limit=3)
            if more:
                more_text = format_cache_results_for_prompt(more)
                prompt = f"""{SYSTEM_PROMPT}

Historique:
{history_str}

{more_text}

INSTRUCTION : Voici d'autres véhicules de l'inventaire pour "{last_query}". Présente-les avec leurs données réelles."""
                response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                more_html_cards = format_vehicles_html_block(more)
                return {"intent": "FOLLOWUP", "response": strip_html(response.text), "html_cards": more_html_cards}
        return {"intent": "FOLLOWUP", "response": "Je n'ai pas d'autres véhicules correspondants dans l'inventaire. Souhaitez-vous élargir la recherche à un autre modèle ou une autre région ?"}

    else:
        # Catch-all : réponse contextuelle SANS GoogleSearch (évite la dérive)
        prompt = f"""{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

INSTRUCTION : Continue à aider l'utilisateur. Si l'historique montre des véhicules présentés, utilise ces données. Ne présente aucun véhicule qui n'est pas dans le contexte. Max 4 phrases en français."""
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}


# =============================
# GUARDRAIL ANTI-HALLUCINATION
# =============================

def apply_guardrails(response: str, user_data: dict) -> str:
    """Retire toute affirmation inventée sur le budget ou le modèle de l'utilisateur."""
    BUDGET_PHRASES = [
        "votre budget", "votre budget de", "ton budget",
        "budget de", "budget mentionné", "budget indiqué",
        "vous avez mentionné", "vous avez dit", "vous avez indiqué",
        "comme vous l'avez précisé", "selon votre budget",
    ]
    if user_data.get("budget") is None:
        for phrase in BUDGET_PHRASES:
            if phrase in response.lower():
                response = re.sub(
                    rf'{re.escape(phrase)}\s+de\s+\d[\d\s,]*\s*\$',
                    "un budget typique dans cette catégorie",
                    response,
                    flags=re.IGNORECASE
                )
    if user_data.get("preferred_model") is None:
        MODEL_PHRASES = ["le modèle que vous avez choisi", "votre choix de"]
        for phrase in MODEL_PHRASES:
            if phrase in response.lower():
                response = response.replace(phrase, "ce type de véhicule")
    return response


# =============================
# TOKEN GUARD HELPERS
# =============================

def estimate_tokens(text: str) -> int:
    """Estimation du nombre de tokens (~4 caractères par token)."""
    return len(text) // 4


def _short_history(session: dict, n: int = 10) -> str:
    """Retourne l'historique des n derniers messages."""
    result = ""
    for msg in session["history"][-n:]:
        role = "Utilisateur" if msg["role"] == "user" else "Agent"
        result += f"{role}: {msg['content'][:200]}\n"
    return result


# =============================
# RISK SCORE F&I
# =============================

def calculate_risk_score(user_data: dict, message: str) -> dict:
    score = 0
    factors = []
    msg_lower = message.lower()

    months_match = re.search(r'(\d+)\s*mois', msg_lower)
    if months_match:
        months = int(months_match.group(1))
        if months >= 72:
            score += 30
            factors.append("financement long terme (72 mois+)")
        elif months >= 60:
            score += 20
            factors.append("financement 60 mois")
        elif months >= 48:
            score += 10
            factors.append("financement 48 mois")

    if user_data.get("annual_km") and user_data["annual_km"] > 20000:
        score += 20
        factors.append("kilométrage élevé")

    luxury = ["bmw", "audi", "mercedes", "lexus", "porsche", "volvo", "land rover"]
    if any(b in msg_lower for b in luxury):
        score += 25
        factors.append("véhicule luxe (réparations coûteuses)")

    year_match = re.search(r'20(\d{2})', msg_lower)
    if year_match:
        age = 2026 - (2000 + int(year_match.group(1)))
        if age >= 5:
            score += 20
            factors.append(f"véhicule de {age} ans")
        elif age >= 3:
            score += 10
            factors.append(f"véhicule de {age} ans")

    reliable = ["toyota", "honda", "mazda"]
    if any(b in msg_lower for b in reliable):
        score -= 10
        factors.append("marque fiable (risque réduit)")

    score = max(0, min(score, 100))

    if score >= 70:
        level, emoji, decision = "ÉLEVÉ", "🔴", "Garantie fortement recommandée"
    elif score >= 40:
        level, emoji, decision = "MODÉRÉ", "🟡", "Garantie recommandée, pas la plus chère"
    else:
        level, emoji, decision = "FAIBLE", "🟢", "Garantie optionnelle"

    return {"score": score, "level": level, "emoji": emoji,
            "decision": decision, "factors": factors}


# =============================
# SMART CHAT — MAIN ENTRY POINT
# =============================

def extract_lead_info(message: str) -> dict:
    """Extrait nom, téléphone et email depuis un message libre (multi-ligne ou inline)."""
    info = {}
    # Email
    email_match = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', message)
    if email_match:
        info["email"] = email_match.group(0)
    # Téléphone (10-15 chiffres, tolère espaces/tirets/parenthèses)
    phone_match = re.search(r'[\+]?[\d\s\-\(\)]{10,17}', message)
    if phone_match:
        phone_clean = re.sub(r'[\s\-\(\)]', '', phone_match.group(0))
        if len(phone_clean) >= 10:
            info["phone"] = phone_match.group(0).strip()
    # Nom (ligne contenant uniquement lettres/espaces/tirets, sans @ ni chiffres)
    for line in message.strip().split('\n'):
        line = line.strip()
        line = re.sub(r'^(nom|name|prénom)\s*:\s*', '', line, flags=re.IGNORECASE)
        if re.match(r'^[A-Za-zÀ-ÿ\s\-]{3,50}$', line) and '@' not in line:
            info["name"] = line.title()
            break
    return info


def _is_opinion_question(message: str) -> bool:
    msg = message.lower()
    patterns = [
        'que penses-tu', 'qu\'en penses-tu', 'ton avis',
        'est-ce fiable', 'c\'est fiable', 'est-ce bon',
        'c\'est comment', 'vaut-il', 'ça vaut',
        'recommandes-tu', 'est-ce que c\'est bien',
        'que penses tu', 'tu en penses quoi',
        'va sortir', 'va-t-il sortir', 'sera disponible',
        'c\'est quoi comme', 'comment est',
        'bonne voiture', 'bon choix',
        'fiabilite', 'fiabilité',
    ]
    return any(p in msg for p in patterns)


def _needs_clarification(message: str, session: dict) -> bool:
    """
    Retourne True si l'agent doit poser une question
    de clarification avant de chercher dans la DB.
    """
    # Si on vient de poser une clarification → ne pas en reposer
    if session.get("context", {}).get("clarification_asked"):
        return False

    msg = message.lower()
    user_data = session.get("user_data", {})

    # Si l'utilisateur mentionne un échange → clarifier
    if any(w in msg for w in ['échanger', 'echange', 'trade', 'reprendre']):
        return True

    # Recherche vague sans budget connu → clarifier
    vague_patterns = [
        'je cherche un vus', 'je veux un vus',
        'je cherche une auto', 'je cherche une voiture',
        'je veux une voiture', 'je me cherche', 'je magasine',
    ]
    if any(p in msg for p in vague_patterns):
        if not user_data.get('budget'):
            return True

    return False


def _get_clarification_message(message: str, session: dict) -> str:
    msg = message.lower()

    # Marquer la clarification comme posée pour ne pas la répéter
    session.setdefault("context", {})["clarification_asked"] = True

    if any(w in msg for w in ['échanger', 'echange', 'trade']):
        return ("Super — tu veux échanger ton véhicule actuel pour un VUS. "
                "Pour te proposer les meilleures options, j'ai besoin de savoir : "
                "quel est ton budget mensuel approximatif, et y a-t-il des marques "
                "que tu préfères ou que tu veux éviter ?")

    return ("Pour affiner ma recherche, peux-tu me donner : "
            "ton budget approximatif et une marque ou un type de véhicule préféré ?")


def _generate_vehicle_alerts(vehicle: dict) -> list:
    """
    Génère automatiquement les alertes pour un véhicule.
    Retourne une liste de strings d'alertes.
    """
    alerts = []

    km = vehicle.get("mileage") or vehicle.get("km") or 0
    price_status = vehicle.get("price_status", "")
    price_diff = vehicle.get("price_diff") or 0
    make = str(vehicle.get("make", "")).lower()
    model = str(vehicle.get("model", "")).lower()
    year = int(vehicle.get("year") or 0)
    fuel = str(vehicle.get("fuel_type", "")).lower()

    # Kilométrage élevé
    if km > 100000:
        alerts.append(f"⚠️ {km:,} km — inspection mécanique indépendante obligatoire avant achat")
    elif km > 80000:
        alerts.append(f"⚠️ {km:,} km — inspection recommandée")

    # Prix au-dessus du marché
    if "élevé" in price_status or "eleve" in price_status:
        alerts.append(f"💡 Prix {abs(price_diff):.0f}$ au-dessus du marché — levier de négociation")

    # Alertes mécaniques par modèle
    if "acadia" in model and 2017 <= year <= 2022:
        alerts.append("🔧 Rappel transmission 'Shift to Park' — vérifier si complété")
    if "equinox" in model and "2.4" in str(vehicle.get("engine", "")) and 2010 <= year <= 2017:
        alerts.append("🔧 Consommation d'huile excessive connue sur ce moteur")
    if "explorer" in model and 2011 <= year <= 2017:
        alerts.append("🔧 Fuite d'échappement dans l'habitacle — vérifier rappel")
    if "cr-v" in model and 2017 <= year <= 2019:
        alerts.append("🔧 Dilution d'huile par essence en hiver — vérifier historique")
    if "cherokee" in model and 2014 <= year <= 2018:
        alerts.append("🔧 Transmission 9 vitesses problématique — tester soigneusement")
    if make == "subaru" and 2013 <= year <= 2015:
        alerts.append("🔧 Joint de culasse — exiger historique d'entretien complet")

    # Véhicule électrique/hybride → rabais gouvernementaux
    if "phev" in fuel or "électrique" in fuel or "electrique" in fuel:
        alerts.append("💰 Éligible rabais Roulez Vert (jusqu'à 4 000$) + fédéral (jusqu'à 5 000$)")
    elif "hybride" in fuel or "hybrid" in fuel:
        alerts.append("💰 Vérifier éligibilité rabais gouvernementaux Roulez Vert")

    return alerts


def smart_chat(message: str, user_id: str = "default") -> dict:
    session = get_session(user_id)

    # ─── PART 3 : Extraction user_data stricte (uniquement ce que l'user a dit) ───
    msg_lower = message.lower()
    ud = session["user_data"]
    _budget_patterns = [
        r'(?:mon budget est|budget de|je veux dépenser|maximum)\s*(\d[\d\s,]*)\s*\$',
        r'(\d[\d\s,]*)\s*\$\s*(?:de budget|max|maximum)',
        r'autour de\s*(\d[\d\s,]*)\s*\$',
        r'(\d[\d\s,]*)\s*\$?\s*(?:par mois|/mois|mensuel|aux deux semaines|/2 semaines)',
        r'(\d[\d\s,]*)\s*(?:dollar|dollars)\s*(?:par mois|mensuel)',
        r'budget\s*(?:de|est)?\s*(\d[\d\s,]*)',
    ]
    for _bp in _budget_patterns:
        _m = re.search(_bp, msg_lower)
        if _m:
            _amt = float(_m.group(1).replace(" ", "").replace(",", ""))
            if 100 < _amt < 200000:
                ud["budget"] = _amt
                ud["budget_clarified"] = True
                print(f"[user_data] budget confirmé: {_amt}$")
                break
    if any(w in msg_lower for w in ["je finance", "financement", "je veux financer", "prêt auto"]):
        ud["financing"] = "financement"
    if any(w in msg_lower for w in ["je loue", "en location", "bail", "leasing"]):
        ud["financing"] = "location"
    _km = re.search(r'(\d[\d\s]*)\s*km\s*(?:par an|\/an|annuel)', msg_lower)
    if _km:
        ud["annual_km"] = int(_km.group(1).replace(" ", ""))

    context_summary, history_str = build_context_summary(user_id)

    # ─── Guard token limit (base: SYSTEM_PROMPT + historique + contexte) ───
    base_tokens = estimate_tokens(SYSTEM_PROMPT + history_str + context_summary)
    if base_tokens > 25000:
        print(f"[smart_chat] ⚠️  WARNING: prompt base ~{base_tokens} tokens (seuil 25 000)")
    if base_tokens > 30000:
        print(f"[smart_chat] 🔴 TRUNCATION: prompt base > 30 000 tokens → historique réduit à 10 messages")
        history_str = _short_history(session, 10)
    session["history"].append({"role": "user", "content": message})

    # ─── Détection soumission formulaire RDV ───
    if message.startswith("DEMANDE_RDV |"):
        _rdv_parts = {}
        for _p in message.split("|"):
            _p = _p.strip()
            if ":" in _p:
                _k, _v = _p.split(":", 1)
                _rdv_parts[_k.strip()] = _v.strip()
        _rdv_veh    = _rdv_parts.get("Véhicule", "")
        _rdv_dealer = _rdv_parts.get("Concessionnaire", "")
        _rdv_nom    = _rdv_parts.get("Nom", "")
        _rdv_tel    = _rdv_parts.get("Tél", "")
        _rdv_email  = _rdv_parts.get("Courriel", "")
        _rdv_msg    = _rdv_parts.get("Message", "")
        # Récupérer le prix, stock_number et vin depuis vehicle_shown en session
        _rdv_prix = ""
        _rdv_stock = "N/D"
        _rdv_vin = "N/D"
        _rdv_shown = session.get("vehicle_shown", {})
        for _sv in _rdv_shown.values():
            _sv_name = f"{_sv.get('year', '')} {_sv.get('make', '')} {_sv.get('model', '')}".strip()
            if _rdv_veh and (_sv_name in _rdv_veh or _rdv_veh in _sv_name):
                try:
                    _p_val = float(_sv.get("price") or 0)
                    if _p_val:
                        _rdv_prix = f"{_p_val:,.0f}\u00a0$".replace(",", "\u00a0")
                except Exception:
                    pass
                _rdv_stock = _sv.get("stock_number") or "N/D"
                _rdv_vin = _sv.get("vin") or "N/D"
                break
        _lead_data = {
            "user_id":       user_id,
            "vehicle_title": _rdv_veh,
            "vehicle_price": _rdv_prix,
            "dealer_name":   _rdv_dealer,
            "name":          _rdv_nom,
            "phone":         _rdv_tel,
            "email":         _rdv_email,
            "message":       _rdv_msg,
            "stock_number":  _rdv_stock,
            "vin":           _rdv_vin,
        }
        print(f"[DEMANDE_RDV] Lead intercepté → {_rdv_nom} | {_rdv_veh} | {_rdv_dealer} | {_rdv_email}")
        try:
            import sys as _sys_rdv
            _sys_rdv.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from lead_service import create_lead
            _lead_ok = create_lead(_lead_data)
            print(f"[DEMANDE_RDV] create_lead → {'OK' if _lead_ok else 'ÉCHEC'}")
        except Exception as _e_rdv:
            import traceback as _tb_rdv
            print(f"[DEMANDE_RDV] lead_service error: {_e_rdv}")
            print(_tb_rdv.format_exc())
        _rdv_confirmation = (
            f"\u2705 Votre demande de rendez-vous a \u00e9t\u00e9 envoy\u00e9e \u00e0 "
            f"{_rdv_dealer or 'le concessionnaire'} pour le {_rdv_veh}. "
            f"Le concessionnaire vous contactera au {_rdv_tel} dans les 24\u201348h."
            + (f" Une confirmation sera envoy\u00e9e \u00e0 {_rdv_email}." if _rdv_email else "")
            + "\n\n\U0001f4a1 **Avant de signer quoi que ce soit** \u2014 si le concessionnaire "
            "vous pr\u00e9sente une offre ou un contrat, vous pouvez me le t\u00e9l\u00e9verser "
            "ici pour analyse. Je v\u00e9rifierai avec vous s'il y a des frais cach\u00e9s, "
            "des produits F&I non sollicit\u00e9s ou des conditions d\u00e9favorables avant "
            "que vous preniez votre d\u00e9cision finale."
        )
        session["history"][-1]["content"] = f"[Formulaire RDV soumis pour {_rdv_veh}]"
        session["history"].append({"role": "assistant", "content": _rdv_confirmation})
        save_session(user_id, sessions.get(user_id, {}))
        return {"intent": "LEAD_SENT", "response": _rdv_confirmation, "html_cards": ""}

    # ─── Interception RDV AVANT Gemini ───
    if detect_rdv_intent(message):

        _shown = session.get("vehicle_shown", {})
        _rdv_prop = extract_proposition_number(message)
        if _rdv_prop and _shown.get(_rdv_prop):
            _rdv_vehicle = _shown[_rdv_prop]
        elif len(_shown) == 1:
            _rdv_vehicle = _shown[1]
        elif _shown:
            # Chercher le véhicule mentionné dans le message avec score de priorité
            _rdv_vehicle = None
            msg_lower_rdv = message.lower()
            _best_score = -1
            for k, v in _shown.items():
                make = str(v.get("make", "")).lower()
                model = str(v.get("model", "")).lower()
                year = str(v.get("year", ""))
                dealer = str(v.get("dealer_name", "")).lower()
                city = str(v.get("city", "")).lower()
                _score = 0
                if model and model in msg_lower_rdv:
                    _score += 2
                if make and make in msg_lower_rdv:
                    _score += 1
                if year and year in msg_lower_rdv:
                    _score += 1
                if dealer and dealer in msg_lower_rdv:
                    _score += 2  # dealer = fort signal de spécificité
                if city and city in msg_lower_rdv:
                    _score += 2  # ville = fort signal de spécificité
                if _score > _best_score:
                    _best_score = _score
                    if _score > 0:
                        _rdv_vehicle = v
            # Si toujours rien → prendre Proposition 1
            if not _rdv_vehicle:
                _rdv_vehicle = _shown[min(_shown.keys())]
        else:
            _rdv_vehicle = None

        # Si vehicle_shown vide, chercher dans le message RDV
        if not _rdv_vehicle:
            # Extraire année + modèle depuis le message
            year_match = re.search(r'\b(20\d{2}|19\d{2})\b', message)
            if year_match:
                year = year_match.group(1)
                # Chercher dans la DB avec l'année et les mots du message
                words = [w for w in message.lower().split()
                         if len(w) > 3 and w not in
                         {'pour', 'avec', 'veux', 'prendre', 'rdva', 'rendez', 'vous', 'voiture', 'auto'}]
                if words:
                    results = search_inventory_cache(
                        query=" ".join(words[:3]),
                        limit=1
                    )
                    if results:
                        _rdv_vehicle = results[0]

        if _rdv_vehicle:
            _rdv_dealer  = _rdv_vehicle.get("dealer_name") or _rdv_vehicle.get("dealer") or "le concessionnaire"
            _rdv_annee   = _rdv_vehicle.get("year") or _rdv_vehicle.get("annee") or ""
            _rdv_marque  = _rdv_vehicle.get("make") or _rdv_vehicle.get("marque") or ""
            _rdv_modele  = _rdv_vehicle.get("model") or _rdv_vehicle.get("modele") or ""
            _rdv_titre   = f"{_rdv_annee} {_rdv_marque} {_rdv_modele}".strip() or "ce véhicule"
            _rdv_form    = generate_rdv_form(_rdv_vehicle)
            _rdv_resp    = f"Voici le formulaire pour contacter {_rdv_dealer} pour le {_rdv_titre}."
            session["history"].append({"role": "assistant", "content": _rdv_resp})
            session["history"] = session["history"][-20:]
            save_session(user_id, sessions.get(user_id, {}))
            print(f"[smart_chat] Interception RDV → formulaire pour {_rdv_titre}")
            return {"intent": "CONTACT", "response": _rdv_resp, "html_cards": _rdv_form}
        else:
            _rdv_no_veh = "Pour quel v\u00e9hicule souhaitez-vous prendre rendez-vous ? Faites une recherche d'abord et je vous afficherai le formulaire de contact."
            session["history"].append({"role": "assistant", "content": _rdv_no_veh})
            session["history"] = session["history"][-20:]
            save_session(user_id, sessions.get(user_id, {}))
            return {"intent": "CONTACT", "response": _rdv_no_veh, "html_cards": ""}

    # ─── Détection affirmative après suggestion de contact (évite la boucle) ───
    _AFFIRMATIVES = {"oui", "oi", "yes", "ok", "d'accord", "ouais", "yep", "allons-y", "allez", "bien sûr", "avec plaisir"}
    if message.strip().lower() in _AFFIRMATIVES and session["context"].get("contact_suggestion_made"):
        print(f"[smart_chat] Réponse affirmative après suggestion contact → forcer LEAD_REQUEST")
        intent_data = {"intent": "LEAD_REQUEST", "urls": [], "vin": None, "query": message,
                       "site": None, "count": 3, "followup_action": None}
    else:
        # Chercher par description dans vehicle_shown avant appel Gemini
        if session.get("vehicle_shown"):
            msg_lower = message.lower()
            _shown = session["vehicle_shown"]
            _desc_best_score = 0
            _desc_best_vehicle = None
            _prices   = [float(sv.get("price", 0) or 0) for sv in _shown.values()]
            _mileages = [int(sv.get("mileage", 0) or 0) for sv in _shown.values()]
            _years    = [int(sv.get("year", 0) or 0) for sv in _shown.values()]
            for k, v in _shown.items():
                _dscore = 0
                _d_make         = str(v.get("make", "")).lower()
                _d_model        = str(v.get("model", "")).lower()
                _d_year         = str(v.get("year", ""))
                _d_dealer       = str(v.get("dealer_name", "")).lower()
                _d_city         = str(v.get("city", "")).lower()
                _d_color        = str(v.get("color", "")).lower()
                _d_fuel         = str(v.get("fuel_type", "")).lower()
                _d_transmission = str(v.get("transmission", "")).lower()
                _d_drivetrain   = str(v.get("drivetrain", "")).lower()
                _d_price        = float(v.get("price", 0) or 0)
                _d_mileage      = int(v.get("mileage", 0) or 0)
                _d_year_int     = int(v.get("year", 0) or 0)
                # Champs de base
                if _d_model  and _d_model  in msg_lower: _dscore += 2
                if _d_dealer and _d_dealer in msg_lower: _dscore += 2
                if _d_city   and _d_city   in msg_lower: _dscore += 2
                if _d_color  and _d_color  in msg_lower: _dscore += 2
                if _d_year   and _d_year   in msg_lower: _dscore += 3
                if _d_make   and _d_make   in msg_lower: _dscore += 1
                # Carburant
                if _d_fuel and _d_fuel in msg_lower: _dscore += 2
                if "hybrid"    in msg_lower and "hybrid"  in _d_fuel: _dscore += 2
                if "hybride"   in msg_lower and "hybrid"  in _d_fuel: _dscore += 2
                if "électrique" in msg_lower and "electr" in _d_fuel: _dscore += 2
                if "essence"   in msg_lower and "essence" in _d_fuel: _dscore += 2
                if "phev"      in msg_lower and "phev"    in _d_fuel: _dscore += 2
                # Couleur
                for _cw, _cf in [("blanc","blanc"),("noir","noir"),("bleu","bleu"),
                                  ("rouge","rouge"),("gris","gris"),("argent","argent")]:
                    if _cw in msg_lower and _cf in _d_color: _dscore += 2
                # Traction
                if "intégrale" in msg_lower and "intégrale" in _d_drivetrain: _dscore += 2
                if "awd"       in msg_lower and "intégrale" in _d_drivetrain: _dscore += 2
                if "4x4"       in msg_lower and ("4 roues" in _d_drivetrain or "intégrale" in _d_drivetrain): _dscore += 2
                # Prix relatif
                if _prices:
                    if any(w in msg_lower for w in ["moins cher","plus abordable","économique","budget"]):
                        if _d_price == min(_prices): _dscore += 3
                    if any(w in msg_lower for w in ["plus cher","haut de gamme","premium","luxe"]):
                        if _d_price == max(_prices): _dscore += 3
                # Kilométrage relatif
                if _mileages:
                    if any(w in msg_lower for w in ["moins de km","moins kilométré","faible kilométrage"]):
                        if _d_mileage == min(_mileages): _dscore += 3
                # Année la plus récente
                if _years:
                    if any(w in msg_lower for w in ["plus récent","plus neuf","dernière année"]):
                        if _d_year_int == max(_years): _dscore += 3
                if _dscore > _desc_best_score:
                    _desc_best_score = _dscore
                    _desc_best_vehicle = v
            if _desc_best_score >= 2 and _desc_best_vehicle:
                session["context"]["selected_vehicle"] = _desc_best_vehicle
        intent_data = detect_intent(message, context_summary)
    intent = intent_data.get("intent", "CHAT")
    # Si question d'opinion/conseil → forcer CHAT, pas de recherche inventaire
    if intent == "SEARCH" and _is_opinion_question(message):
        intent = "CHAT"
    # Si contexte ambigu (échange, trade) → demander clarification avant de chercher
    if intent == "SEARCH" and _needs_clarification(message, session):
        return {"intent": "CHAT", "response": _get_clarification_message(message, session), "html_cards": ""}
    result = {}

    # ─── Collecte progressive lead — priorité absolue sur tout autre intent ───
    _pending = session["context"].get("pending_lead")
    if _pending:
        # Extraire toutes les infos disponibles dans le message (multi-ligne ou inline)
        _extracted = extract_lead_info(message)
        if _extracted.get("name") and not _pending.get("name"):
            session["context"]["pending_lead"]["name"] = _extracted["name"]
        if _extracted.get("phone") and not _pending.get("phone"):
            session["context"]["pending_lead"]["phone"] = _extracted["phone"]
        if _extracted.get("email") and not _pending.get("email"):
            session["context"]["pending_lead"]["email"] = _extracted["email"]
        # Relire après mise à jour
        _pending  = session["context"]["pending_lead"]
        _pl_name  = _pending.get("name", "")
        _pl_phone = _pending.get("phone", "")
        _pl_email = _pending.get("email", "")
        # Tous les champs présents → create_lead immédiatement
        if _pl_name and _pl_phone and _pl_email and "@" in _pl_email:
            _lead_data = dict(_pending)
            _lead_data["user_id"] = user_id
            try:
                import sys as _sys2
                _sys2.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                from lead_service import create_lead
                create_lead(_lead_data)
                dealer = _lead_data.get("dealer_name") or "le concessionnaire"
                result = {
                    "intent": "LEAD_SENT",
                    "response": (
                        f"✅ Votre demande a été envoyée à {dealer}. "
                        f"Vous recevrez une confirmation à {_pl_email}. "
                        f"Le concessionnaire va vous contacter au {_pl_phone} dans les 24-48h."
                    ),
                }
                session["context"]["pending_lead"] = None
            except Exception as e:
                print(f"[lead_collect] error: {e}")
                result = {"intent": "LEAD_ERROR", "response": "Une erreur s'est produite. Contactez directement le concessionnaire."}
        # Champ(s) manquant(s) → demander le suivant
        elif not _pl_name:
            result = {
                "intent": "LEAD_COLLECT",
                "response": "Quel est votre nom complet ?",
            }
        elif not _pl_phone:
            result = {
                "intent": "LEAD_COLLECT",
                "response": "Quel est votre numéro de téléphone ?",
            }
        elif not _pl_email:
            result = {
                "intent": "LEAD_COLLECT",
                "response": "Quelle est votre adresse email ?",
            }

    # ─── Détection référence à une proposition numérotée ───
    if not result:
        _prop_num = extract_proposition_number(message)
        _shown = session.get("vehicle_shown", {})
        # Référence implicite sans numéro → prendre le seul véhicule en session
        if _prop_num is None and has_vehicle_interest(message):
            if len(_shown) == 1:
                _prop_num = 1
                print(f"[smart_chat] Intérêt implicite détecté → Proposition 1 (seul véhicule en session)")
        if _prop_num and _shown.get(_prop_num):
            v = _shown[_prop_num]
            _veh_ctx = f"""
CONTEXTE — L'utilisateur parle de la Proposition {_prop_num} présentée dans cette session.
Réponds UNIQUEMENT sur CE véhicule. Ne PAS relancer de recherche. Ne PAS réafficher les 3 propositions.

Année        : {v.get('year', 'N/D')}
Marque       : {v.get('make', 'N/D')}
Modèle       : {v.get('model', 'N/D')}
Version      : {v.get('trim', 'N/D')}
Prix         : {v.get('price', 'N/D')} $
Kilométrage  : {v.get('mileage', 'N/D')} km
Moteur       : {v.get('engine', 'N/D')}
Transmission : {v.get('transmission', 'N/D')}
Traction     : {v.get('drivetrain', 'N/D')}
Carburant    : {v.get('fuel_type', 'N/D')}
Couleur      : {v.get('color', 'N/D')}
VIN          : {v.get('vin', 'N/D')}
Concess.     : {v.get('dealer_name', 'N/D')}
Ville        : {v.get('city', 'N/D')}
N° Stock     : {v.get('stock_number', 'N/D')}
Marché moyen : {v.get('avg_market_price', 'N/D')} $

RÈGLES :
- Ne jamais afficher "Non disponible" si la donnée est listée ci-dessus
- Répondre directement sur ce véhicule spécifique sans nouvelle recherche
"""
            _prop_prompt = (
                f"{SYSTEM_PROMPT}\n\n{_veh_ctx}\n\nHistorique:\n{history_str}\n\n"
                f"MESSAGE : {message}\n\n"
                "INSTRUCTION FORMAT : Répondre en français naturel, en PROSE (pas de liste bullets ni de tableau). "
                "Intégrer les données dans des phrases complètes. Ne jamais écrire '* **Prix :**' ou '• Kilométrage :'."
            )
            _prop_resp = client.models.generate_content(model="gemini-2.5-flash", contents=_prop_prompt)
            result = {"intent": "FOLLOWUP", "response": _prop_resp.text, "_html_cards": ""}
            print(f"[smart_chat] Proposition {_prop_num} détectée → réponse directe")

    if not result and intent == "CREATE_ALERT":
        criteria = {}
        _brands = ["toyota", "honda", "bmw", "audi", "mercedes", "hyundai", "kia",
                   "ford", "nissan", "mazda", "subaru", "chevrolet", "dodge", "ram", "jeep", "gmc"]
        for brand in _brands:
            if brand in message.lower():
                criteria["brand"] = brand
                break
        _year = re.search(r'20(\d{2})', message)
        if _year:
            y = 2000 + int(_year.group(1))
            criteria["year_min"] = y - 1
            criteria["year_max"] = y + 1
        _price = re.search(r'(\d[\d\s]*)\s*\$', message)
        if _price:
            criteria["price_max"] = float(_price.group(1).replace(" ", ""))
        _cities = ["montreal", "montréal", "québec", "laval", "longueuil",
                   "gatineau", "sherbrooke", "lévis", "trois-rivières"]
        for city in _cities:
            if city in message.lower():
                criteria["city"] = city
                break
        session["context"]["pending_alert"] = criteria
        _alert_email = re.search(r'[\w\.\-]+@[\w\.\-]+\.\w+', message)
        if _alert_email:
            try:
                import sys as _sys_alert
                _sys_alert.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                from alert_service import save_alert
                save_alert(user_id, _alert_email.group(0), criteria)
                result = {
                    "intent": "CREATE_ALERT",
                    "response": f"✅ Alerte créée ! Vous recevrez un email à {_alert_email.group(0)} dès qu'un véhicule correspondant à vos critères sera disponible.",
                }
            except Exception as e:
                print(f"[create_alert] error: {e}")
                result = {
                    "intent": "CREATE_ALERT",
                    "response": "Je vais créer une alerte pour vous ! Pour vous envoyer l'email, j'ai besoin de votre adresse courriel. Quelle est-elle ?",
                    "needs_email": True,
                    "criteria": criteria,
                }
        else:
            result = {
                "intent": "CREATE_ALERT",
                "response": "Pour créer votre alerte, j'ai besoin de votre adresse email. Quelle est-elle ?",
                "needs_email": True,
                "criteria": criteria,
            }

    elif not result and intent == "LEAD_REQUEST":
        last_results = session["context"].get("last_results", [])
        last_listings = session["context"].get("last_listings", [])
        # Priorité : véhicule sélectionné > dernier résultat > dernière requête
        _sel = session["context"].get("selected_vehicle")
        vehicle_title = (
            (_sel.get("title") if isinstance(_sel, dict) else None)
            or session["context"].get("last_query", "véhicule")
        )
        vehicle_price = 0
        vehicle_url = ""
        dealer_name = ""
        vehicle_for_form = {}
        # Priorité : last_results contient les données complètes (titre, prix, concessionnaire)
        if last_results:
            v = last_results[0]
            vehicle_title = v.get("title", vehicle_title)
            vehicle_price = v.get("price", 0)
            vehicle_url = v.get("url", "")
            dealer_name = v.get("dealer_name", "")
            vehicle_for_form = v
        elif last_listings:
            v = last_listings[0] if isinstance(last_listings, list) else last_listings
            if isinstance(v, dict):
                vehicle_title = v.get("title", vehicle_title)
                vehicle_price = v.get("price", 0)
                vehicle_url = v.get("url", "")
                dealer_name = v.get("dealer_name", v.get("dealer", ""))
                vehicle_for_form = v
            elif isinstance(v, str):
                vehicle_url = v
        rdv_html     = generate_rdv_form(vehicle_for_form)
        rdv_response = f"Voici le formulaire pour prendre rendez-vous chez {dealer_name or 'le concessionnaire'} pour le {vehicle_title}."
        session["history"].append({"role": "assistant", "content": rdv_response})
        session["history"] = session["history"][-20:]
        update_context(user_id, intent_data, rdv_response)
        save_session(user_id, sessions.get(user_id, {}))
        return {
            "intent": "LEAD_REQUEST",
            "response": rdv_response,
            "html_cards": rdv_html,
        }

    elif not result and intent == "GARANTIES":
        risk = calculate_risk_score(session["user_data"], message)
        risk_context = f"""
SCORE DE RISQUE CALCULÉ : {risk['emoji']} {risk['score']}/100 — Risque {risk['level']}
Facteurs : {', '.join(risk['factors']) if risk['factors'] else 'aucun facteur détecté'}
Décision recommandée : {risk['decision']}

INSTRUCTION : Affiche ce score dans ta réponse sous cette forme exacte dans la section 💰 :
📊 Score de risque : {risk['emoji']} {risk['score']}/100 — {risk['level']}
Puis explique ce que ça signifie concrètement pour cet acheteur.
"""
        garanties_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}
{risk_context}

Message de l'utilisateur: {message}

INSTRUCTIONS : Utilise le FORMAT RÉPONSE GARANTIES (🧠/💡/⚠️/💰/🎯). Inclus le score 📊 dans la section 💰.
"""
        _tok = estimate_tokens(garanties_prompt)
        if _tok > 25000:
            print(f"[smart_chat/GARANTIES] ⚠️  WARNING: prompt ~{_tok} tokens")
        garanties_response = client.models.generate_content(
            model="gemini-2.5-flash", contents=garanties_prompt
        )
        result = {"intent": "GARANTIES", "response": garanties_response.text,
                  "risk_score": risk["score"], "risk_level": risk["level"]}

    elif not result and intent == "FOLLOWUP":
        result = handle_followup(user_id, intent_data, history_str, context_summary)

    elif not result and intent == "CHECK_VIN" and intent_data.get("vin"):
        _vin = intent_data["vin"]
        _vr  = get_vehicle_report(_vin)

        if "error" in _vr:
            result = {"intent": "CHECK_VIN", "response": _vr["error"]}
        else:
            _decoded    = _vr.get("vehicle_info", {})
            _vin_chars  = _vr.get("vin_decoded", {})
            _recalls    = _vr.get("recalls", {})
            _complaints = _vr.get("complaints", {})
            _full       = _vr.get("full_report", "")

            # ── Type véhicule ──
            _body  = _decoded.get("BodyClass", "")
            _doors = _decoded.get("Doors", "")
            _vtype = _decoded.get("VehicleType", "")
            _type_parts = [p for p in [_body, f"{_doors} portes" if _doors else ""] if p]
            _type_v = " \u00b7 ".join(_type_parts) if _type_parts else _vtype or "N/D"

            # ── Moteur ──
            _cyl  = _decoded.get("EngineCylinders", "")
            _disp = _decoded.get("DisplacementL", "")
            _fuel = _decoded.get("FuelTypePrimary", "")
            _mot  = " \u00b7 ".join(p for p in [
                f"{_disp}L" if _disp else "",
                f"{_cyl} cyl." if _cyl else "",
                _fuel,
            ] if p) or "N/D"

            # ── Rappels ──
            _rc     = _recalls.get("count", 0)
            _rok    = _rc == 0
            if _rok:
                _rappels_txt = "Aucun rappel actif"
            else:
                _rlist = _recalls.get("recalls", [])
                _comps = [r.get("component", "") for r in _rlist[:3] if r.get("component")]
                _rappels_txt = f"{_rc} rappel(s) \u2014 {', '.join(_comps)}" if _comps else _recalls.get("message", f"{_rc} rappel(s)")

            # ── Plaintes ──
            _cc  = _complaints.get("count", 0)
            _pok = _cc < 5
            if _cc == 0:
                _plaintes_txt = "Peu de plaintes enregistr\u00e9es"
            else:
                _top = _complaints.get("top_issues", [])
                if _top:
                    _issues = [f"{i['component']} ({i['complaints']} plaintes)" for i in _top[:3]]
                    _plaintes_txt = f"{_cc} plaintes \u00b7 {', '.join(_issues)}"
                else:
                    _plaintes_txt = f"{_cc} plaintes enregistr\u00e9es"

            # ── Points à surveiller (parse section 🔧 du texte Gemini) ──
            _points = []
            _m_pts = re.search(r'[\U0001F527\U0001F6E0]?\s*POINTS[^\n]*\n((?:[ \t]*[•*\-][^\n]+\n?)*)', _full)
            if _m_pts:
                for _ln in _m_pts.group(1).split('\n'):
                    _ln = re.sub(r'^[\s•*\-]+', '', _ln).strip()
                    if _ln and len(_ln) > 5:
                        _points.append(_ln)

            # ── Prix (parse section 💰 du texte Gemini) ──
            _prix_min = _prix_max = _prix_moyen = "N/D"
            _sources  = "AutoTrader \u00b7 CarGurus"
            _m_range = re.search(r'[Ff]ourchette[^:]*:\s*([\d\s\u00a0,]+)\s*\$\s*[\u2014\-\u2013]\s*([\d\s\u00a0,]+)\s*\$', _full)
            if _m_range:
                _prix_min = _m_range.group(1).strip().replace(",", "\u00a0") + "\u00a0$"
                _prix_max = _m_range.group(2).strip().replace(",", "\u00a0") + "\u00a0$"
            _m_avg = re.search(r'[Pp]rix moyen[^:]*:\s*~?\s*([\d\s\u00a0,]+)\s*\$', _full)
            if _m_avg:
                _prix_moyen = _m_avg.group(1).strip().replace(",", "\u00a0") + "\u00a0$"
            _m_src = re.search(r'[Ss]ource\s*:\s*([^\n]+)', _full)
            if _m_src:
                _sources = _m_src.group(1).strip()

            # ── Recommandation (parse section 🎯 du texte Gemini) ──
            _rec_titre  = "Inspecter avant achat"
            _rec_texte  = "Une inspection pr\u00e9-achat par un m\u00e9canicien ind\u00e9pendant est recommand\u00e9e."
            _rec_niveau = "attention"
            _m_rec = re.search(r'[\U0001F3AF]\s*RECOMMANDATION\s*\n([^\n]+)', _full)
            if _m_rec:
                _rec_raw = _m_rec.group(1).strip()
                if "\u2705" in _rec_raw or "Acheter" in _rec_raw:
                    _rec_niveau = "ok"
                elif "\u274c" in _rec_raw or "\u26d4" in _rec_raw or "\u00c9viter" in _rec_raw or "Eviter" in _rec_raw:
                    _rec_niveau = "danger"
                # Extraire titre + texte séparés par " — "
                _rec_clean = re.sub(r'[\U0001F3AF\u2705\u274c\u26d4\u26a0\ufe0f\U0001F50D]+', '', _rec_raw).strip(' \u2014-\u00b7')
                _rec_parts = _rec_clean.split('\u2014', 1)
                if len(_rec_parts) == 2:
                    _rec_titre = _rec_parts[0].strip() or _rec_titre
                    _rec_texte = _rec_parts[1].strip() or _rec_texte
                elif _rec_clean:
                    _rec_texte = _rec_clean

            _make  = _decoded.get("Make", "")
            _model = _decoded.get("Model", "")
            _year  = _decoded.get("ModelYear", str(_vin_chars.get("model_year_from_vin", "")))

            _vin_data = {
                "vin":                   _vin,
                "annee":                 _year,
                "make":                  _make,
                "model":                 _model,
                "type_vehicule":         _type_v,
                "moteur":                _mot,
                "transmission":          _decoded.get("TransmissionStyle", "N/D"),
                "traction":              _decoded.get("DriveType", "N/D"),
                "assemble":              _decoded.get("PlantCountry", _vin_chars.get("country_of_manufacture", "N/D")),
                "usage":                 _vin_chars.get("usage_hint", "N/D"),
                "rappels":               _rappels_txt,
                "rappels_ok":            _rok,
                "plaintes":              _plaintes_txt,
                "plaintes_ok":           _pok,
                "points_surveiller":     _points[:5],
                "prix_min":              _prix_min,
                "prix_max":              _prix_max,
                "prix_moyen":            _prix_moyen,
                "sources_prix":          _sources,
                "recommandation_titre":  _rec_titre,
                "recommandation_texte":  _rec_texte,
                "recommandation_niveau": _rec_niveau,
            }

            _vin_html    = generate_vin_report(_vin_data)
            _intro       = f"Voici le rapport VIN pour le {_year} {_make} {_model}.".strip()
            result = {"intent": "CHECK_VIN", "response": _intro, "_html_cards": _vin_html}

    elif not result and intent == "COMPARE_URLS" and len(intent_data.get("urls", [])) >= 2:
        compare_result = compare_listings(intent_data["urls"][0], intent_data["urls"][1])
        result = {"intent": "COMPARE_URLS", "response": compare_result.get("comparison", ""), "urls": intent_data["urls"]}

    elif not result and intent == "ANALYZE_URL" and len(intent_data.get("urls", [])) >= 1:
        analyze_result = analyze_listing(intent_data["urls"][0])
        result = {"intent": "ANALYZE_URL", "response": analyze_result.get("analysis", ""), "url": intent_data["urls"][0], "scraped": analyze_result.get("scraped", False)}

    elif not result and intent == "SEARCH" and intent_data.get("query"):
        query = intent_data["query"]
        session["context"]["last_query"] = query

        # ─── Détection de recherche "similaires" — élargir par catégorie ───
        CATEGORIES_VEHICULES = {
            "vus_compact": ["rogue", "rav4", "cr-v", "crv", "escape", "tucson", "sportage", "outlander", "cx-5", "cx5", "equinox", "forester"],
            "vus_souscompact": ["seltos", "venue", "trax", "encore", "ecosport", "qashqai", "kicks"],
            "berline_compacte": ["civic", "corolla", "elantra", "sentra", "mazda3", "forte", "golf"],
            "berline_intermediaire": ["camry", "accord", "altima", "sonata", "fusion", "malibu"],
            "camionnette_midsized": ["tacoma", "colorado", "ranger", "frontier", "ridgeline", "canyon"],
            "camionnette_fullsize": ["f-150", "f150", "ram", "silverado", "sierra", "tundra"],
            "electrique": ["ioniq", "leaf", "bolt", "model 3", "model y", "id.4", "mache", "mustang mache"],
        }
        MOTS_SIMILAIRES = ["similaire", "pareil", "alternative", "autres options", "autres modeles", "comme ça", "du même genre", "equivalent"]

        if any(mot in query.lower() for mot in MOTS_SIMILAIRES) and session["context"].get("last_listings"):
            dernier_vehicule = ""
            categorie = ""
            for msg in reversed(session["history"]):
                if msg["role"] == "assistant":
                    for cat, modeles in CATEGORIES_VEHICULES.items():
                        for modele in modeles:
                            if modele in msg["content"].lower():
                                dernier_vehicule = modele
                                categorie = cat
                                break
                        if dernier_vehicule:
                            break
                if dernier_vehicule:
                    break
            if dernier_vehicule:
                modeles_categorie = CATEGORIES_VEHICULES.get(categorie, [])
                query = " ".join(modeles_categorie[:4]) + " occasion Quebec"
                intent_data["query"] = query
                print(f"[similaires] {dernier_vehicule} → catégorie {categorie} → nouvelle query: {query}")

        # ─── ÉTAPE 1 : Chercher dans l'inventaire local (Force Occasion) ───
        vehicle_filter = intent_data.get("vehicle_filter")

        # Extraire fuel_filter et year_filter depuis vehicle_filter
        _fuel_map = {
            'hybride': 'hybride', 'hybrid': 'hybride',
            'electrique': 'lectrique', 'électrique': 'lectrique',
            'phev': 'phev', 'plug-in': 'phev',
            'diesel': 'diesel',
        }
        _vf_lower = (vehicle_filter or '').lower()
        _fuel_filter = None
        for kw, val in _fuel_map.items():
            if kw in _vf_lower:
                _fuel_filter = val
                break
        import re as _re
        _year_match = _re.search(r'\b(20\d{2})\b', vehicle_filter or '')
        _year_filter = _year_match.group(1) if _year_match else None

        # Extraire price_max du message : "sous 20000", "moins de 25 000$", "budget 30000"
        _price_match = _re.search(
            r'(?:sous|moins de|budget|max|maximum)\s*(\d[\d\s]{2,})\s*(?:\$|dollars?)?',
            message.lower()
        )
        _price_max = int(_price_match.group(1).replace(' ', '')) if _price_match else None

        # Extraire mileage_max du message : "moins de 80 000 km", "sous 100000 km"
        _mileage_match = _re.search(
            r'(?:sous|moins de|max|maximum)?\s*(\d[\d\s]{2,})\s*(?:km|kilomètre)',
            message.lower()
        )
        _mileage_max = int(_mileage_match.group(1).replace(' ', '')) if _mileage_match else None

        # Extraire drivetrain_filter du message : AWD, 4x4, 4RM, intégrale, FWD, RWD
        _drivetrain_map = {
            'awd': 'awd', '4x4': '4x4', '4rm': '4rm',
            'intégrale': 'awd', 'integrale': 'awd',
            'quatre roues motrices': '4x4', '4 roues': '4x4',
            'traction avant': 'fwd', 'fwd': 'fwd',
            'propulsion': 'rwd', 'rwd': 'rwd',
        }
        _drivetrain_filter = None
        _msg_lower = message.lower()
        for _kw, _val in _drivetrain_map.items():
            if _kw in _msg_lower:
                _drivetrain_filter = _val
                break

        cache_results = search_inventory_cache(query, limit=3, vehicle_filter=vehicle_filter,
                                               fuel_filter=_fuel_filter, year_filter=_year_filter,
                                               price_max=_price_max, mileage_max=_mileage_max,
                                               drivetrain_filter=_drivetrain_filter)

        if cache_results:
            vehicles_3 = cache_results[:3]
            cache_text = format_cache_results_for_prompt(vehicles_3)
            for r in vehicles_3:
                alerts = _generate_vehicle_alerts(r)
                if alerts:
                    cache_text += "\nALERTES AUTOMATIQUES:\n"
                    for alert in alerts:
                        cache_text += f"  {alert}\n"
            session["context"]["last_listings"] = [r["url"] for r in vehicles_3]
            session["context"]["last_results"] = [
                {k: r.get(k) for k in ("title", "price", "city", "dealer_name", "url", "mileage", "year", "make", "model")}
                for r in vehicles_3
            ]
            # Sauvegarder les véhicules complets pour la référence par proposition
            session["vehicle_shown"] = {i + 1: r for i, r in enumerate(vehicles_3)}

            # ─── Structured output : JSON des véhicules pour Gemini ───
            vehicles_for_gemini = {}
            for i, v in enumerate(vehicles_3):
                key = f"prop_{i+1}"
                vehicles_for_gemini[key] = {
                    "annee": v.get("year", ""),
                    "modele": f"{v.get('make', '')} {v.get('model', '')}",
                    "prix": v.get("price", 0),
                    "km": v.get("mileage", 0),
                    "carburant": v.get("fuel_type", ""),
                    "traction": v.get("drivetrain", ""),
                    "prix_marche": v.get("avg_market_price", 0),
                    "ecart": v.get("price_diff", 0),
                    "statut_prix": v.get("price_status", ""),
                    "concessionnaire": v.get("dealer_name", ""),
                    "ville": v.get("city", "")
                }

            structured_prompt = f"""{SYSTEM_PROMPT}

Tu es un analyste automobile.
Tu dois commenter exactement ces véhicules.

RÈGLES ABSOLUES :
- Utilise UNIQUEMENT les données fournies ci-dessous
- N'invente AUCUN prix, kilométrage ou donnée
- Chaque commentaire = 2-3 phrases maximum
- Mentionne l'écart de prix par rapport au marché
- Si km > 80000 → mentionne inspection obligatoire
- Ton direct, tutoiement, français québécois

FORMAT DE SORTIE — JSON STRICT UNIQUEMENT :
{{
  "prop_1": "commentaire proposition 1",
  "prop_2": "commentaire proposition 2",
  "prop_3": "commentaire proposition 3"
}}

Ne retourne RIEN d'autre que ce JSON.
Pas d'introduction, pas de conclusion.

DONNÉES VÉHICULES :
{json.dumps(vehicles_for_gemini, ensure_ascii=False, indent=2)}

CONTEXTE CONVERSATION :
{context_summary}

QUESTION UTILISATEUR : {message}
"""
            # Token guard — SEARCH cache
            _tok = estimate_tokens(structured_prompt)
            if _tok > 25000:
                print(f"[smart_chat/SEARCH-cache] ⚠️  WARNING: prompt ~{_tok} tokens (seuil 25 000)")

            response = client.models.generate_content(model="gemini-2.5-flash", contents=structured_prompt)

            # ─── Parser et valider le JSON retourné ───
            import re as _re_json
            try:
                raw = response.text.strip()
                json_match = _re_json.search(r'\{.*\}', raw, _re_json.DOTALL)
                if json_match:
                    comments = json.loads(json_match.group())
                else:
                    comments = {}
            except Exception:
                comments = {}

            # Validation anti-hallucination
            FORBIDDEN = ["excellent", "incroyable", "parfait",
                         "super bonne affaire", "coup de coeur"]
            for key in comments:
                for word in FORBIDDEN:
                    if word in comments.get(key, "").lower():
                        comments[key] = comments[key].replace(word, "")

            # ─── Assembler la réponse finale ───
            response_text = ""
            for i, v in enumerate(vehicles_3):
                key = f"prop_{i+1}"
                comment = comments.get(key, "")
                if comment:
                    make = v.get("make", "")
                    model = v.get("model", "")
                    year = v.get("year", "")
                    response_text += f"**Proposition {i+1} : {year} {make} {model}**\n{comment}\n\n"

            # Fallback texte Gemini si JSON vide
            if not response_text:
                response_text = response.text

            html_cards = format_vehicles_html_block(vehicles_3)
            result = {
                "intent": "SEARCH",
                "response": response_text,
                "_html_cards": html_cards,
                "urls_found": [r["url"] for r in cache_results],
                "scraped_count": len(cache_results),
                "source": "inventory_cache"
            }

        else:
            # ─── ÉTAPE 2 : Aucun résultat local → recherche alternatives inventaire ───
            print(f"[smart_chat] Aucun résultat local pour '{query}' → recherche alternatives")

            try:
                log_search(query=query, intent="SEARCH", results_count=0)
            except Exception:
                pass

            # Chercher des alternatives dans l'inventaire (mots-clés élargis)
            alt_results = []
            keywords_alt = [k.strip() for k in query.lower().split() if len(k.strip()) > 2
                            and k.strip() not in {s.lower() for s in STOPWORDS_FR}]
            for kw in keywords_alt[:2]:
                alt_results = search_inventory_cache(kw, limit=3)
                if alt_results:
                    print(f"[smart_chat] Alternatives trouvées pour '{kw}': {len(alt_results)}")
                    break

            if alt_results:
                alt_text = format_cache_results_for_prompt(alt_results)
                session["context"]["last_listings"] = [r["url"] for r in alt_results]
                session["context"]["last_results"] = [
                    {k: r.get(k) for k in ("title", "price", "city", "dealer_name", "url", "mileage", "year", "make", "model")}
                    for r in alt_results
                ]
                session["vehicle_shown"] = {i + 1: r for i, r in enumerate(alt_results[:3])}
                no_stock_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

RECHERCHE DE L'UTILISATEUR : "{query}"

RÉSULTAT DE RECHERCHE : Ce modèle exact n'est PAS disponible dans l'inventaire de nos concessionnaires partenaires.

ALTERNATIVES DISPONIBLES EN INVENTAIRE :
{alt_text}

INSTRUCTIONS :
- Dis CLAIREMENT et HONNÊTEMENT que le modèle exact demandé n'est pas en stock
- Les fiches alternatives sont affichées automatiquement — NE PAS répéter leurs spécifications
- Fournis une courte phrase d'introduction sur pourquoi ces alternatives sont pertinentes
- N'invente AUCUN véhicule supplémentaire
- Propose à l'utilisateur de créer une alerte email pour être notifié si le modèle arrive en inventaire
"""
            else:
                no_stock_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

RECHERCHE DE L'UTILISATEUR : "{query}"

RÉSULTAT DE RECHERCHE : Aucun véhicule trouvé dans l'inventaire pour cette recherche.

INSTRUCTIONS STRICTES :
- Dis HONNÊTEMENT qu'on n'a pas ce modèle en stock chez nos concessionnaires partenaires
- NE PAS inventer de véhicules ou d'annonces
- NE PAS chercher sur internet pour présenter des fiches
- Propose : (1) créer une alerte email, (2) élargir la recherche à d'autres modèles similaires, (3) consulter directement AutoHebdo.net ou Kijiji Autos
- Demande si l'utilisateur veut qu'on cherche un modèle similaire dans notre inventaire
"""

            _tok = estimate_tokens(no_stock_prompt)
            if _tok > 30000:
                history_str = _short_history(session, 10)
                no_stock_prompt = no_stock_prompt.replace(history_str, _short_history(session, 10))

            no_stock_response = client.models.generate_content(model="gemini-2.5-flash", contents=no_stock_prompt)
            alt_html_cards = format_vehicles_html_block(alt_results) if alt_results else ""
            result = {
                "intent": "SEARCH",
                "response": no_stock_response.text,
                "_html_cards": alt_html_cards,
                "urls_found": [r["url"] for r in alt_results] if alt_results else [],
                "scraped_count": len(alt_results),
                "source": "inventory_cache_alternatives"
            }

    elif not result:
        # ─── CHAT — conseils, fiabilité, prix, etc. ───
        ud = session["user_data"]

        # ─── Pipeline rule-based (fuzzy match, financement, analyse) ───
        try:
            import sys as _pipe_sys
            _pipe_sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
            from core.pipeline import process as pipeline_process

            class _PipeState:
                def __init__(self, sess):
                    self.stage = sess["context"].get("pipeline_stage", "results")
                    self.last_results = sess["context"].get("last_results", [])
                    self.selected_vehicle = sess["context"].get("selected_vehicle")

            _state = _PipeState(session)
            _pipe_response = pipeline_process(message, _state, [])

            # Persister les changements d'état
            session["context"]["pipeline_stage"] = _state.stage
            if _state.selected_vehicle:
                session["context"]["selected_vehicle"] = _state.selected_vehicle

            if _pipe_response:
                print(f"[pipeline] Réponse directe (stage={_state.stage})")
                result = {"intent": "PIPELINE", "response": _pipe_response}
        except Exception as _pe:
            print(f"[pipeline] skip: {_pe}")

        if not result:
            # ─── CHAT : chercher dans inventaire si véhicule mentionné ───
            # Marques → modèles associés pour enrichir la recherche
            CHAT_BRAND_MODELS = {
                "toyota": ["rav4", "corolla", "camry", "highlander", "tundra", "tacoma", "sienna", "prius"],
                "honda": ["civic", "accord", "crv", "cr-v", "pilot", "odyssey", "ridgeline"],
                "bmw": ["x1", "x2", "x3", "x4", "x5", "x6", "x7", "330", "430", "530", "630", "730", "m3", "m5"],
                "audi": ["a3", "a4", "a5", "a6", "q3", "q5", "q7", "q8"],
                "mercedes": ["c300", "e300", "glc", "gle", "gls", "cla", "gla"],
                "hyundai": ["elantra", "tucson", "sonata", "santa fe", "ioniq", "kona"],
                "kia": ["seltos", "sportage", "sorento", "telluride", "forte", "stinger", "niro"],
                "ford": ["f-150", "f150", "escape", "explorer", "edge", "bronco", "mustang"],
                "chevrolet": ["equinox", "traverse", "silverado", "tahoe", "suburban", "blazer", "trax", "trax"],
                "nissan": ["rogue", "sentra", "altima", "murano", "pathfinder", "qashqai", "frontier", "titan"],
                "mazda": ["mazda3", "cx-5", "cx5", "cx-30", "cx-9", "mx-5"],
                "volkswagen": ["tiguan", "atlas", "golf", "jetta", "passat", "id.4"],
                "vw": ["tiguan", "atlas", "golf", "jetta"],
                "lexus": ["rx", "nx", "es", "ux", "gx", "lx"],
                "subaru": ["forester", "outback", "crosstrek", "impreza", "wrx", "ascent"],
                "mitsubishi": ["outlander", "rvr", "eclipse cross"],
                "jeep": ["grand cherokee", "wrangler", "compass", "renegade", "gladiator"],
                "dodge": ["charger", "challenger", "durango"],
                "ram": ["1500", "2500", "promaster"],
                "gmc": ["sierra", "yukon", "terrain", "acadia", "canyon"],
                "buick": ["enclave", "encore", "envision"],
            }
            CHAT_MODEL_ONLY = [
                "civic", "corolla", "camry", "accord", "rav4", "crv", "cr-v",
                "rogue", "tucson", "elantra", "sentra", "altima", "forester",
                "seltos", "venue", "qashqai", "escape", "equinox", "trax",
                "sportage", "outlander", "cx-5", "cx5", "tiguan", "golf",
                "f-150", "f150", "silverado", "sierra", "tundra",
                "tacoma", "colorado", "ranger", "frontier",
                "sienna", "odyssey", "carnival", "pacifica",
                "model 3", "model y", "ioniq", "leaf", "bolt",
                "pilot", "highlander", "pathfinder", "traverse", "explorer",
                "tahoe", "expedition", "yukon", "suburban",
                "charger", "challenger", "mustang", "camaro",
            ]

            chat_vehicle_query = None
            # Stratégie : détecter marque + modèle ensemble pour une recherche plus précise
            brand_found = None
            model_found = None
            for brand in CHAT_BRAND_MODELS:
                if brand in msg_lower:
                    brand_found = brand
                    for model in CHAT_BRAND_MODELS[brand]:
                        if model in msg_lower:
                            model_found = model
                            break
                    break
            if not brand_found:
                for model in CHAT_MODEL_ONLY:
                    if model in msg_lower:
                        model_found = model
                        break
            if brand_found and model_found:
                chat_vehicle_query = f"{brand_found} {model_found}"
            elif brand_found:
                chat_vehicle_query = brand_found
            elif model_found:
                chat_vehicle_query = model_found

            chat_inventory_text = ""
            chat_cache = []
            if chat_vehicle_query:
                print(f"[smart_chat/CHAT] Véhicule détecté: '{chat_vehicle_query}' → recherche inventaire")
                chat_cache = search_inventory_cache(chat_vehicle_query, limit=3)
                if chat_cache:
                    chat_inventory_text = "\n\n" + format_cache_results_for_prompt(chat_cache)
                    # Mettre à jour last_results si pas encore de résultats dans la session
                    if not session["context"].get("last_results"):
                        session["context"]["last_listings"] = [r["url"] for r in chat_cache]
                        session["context"]["last_results"] = [
                            {k: r.get(k) for k in ("title", "price", "city", "dealer_name", "url", "mileage", "year", "make", "model")}
                            for r in chat_cache
                        ]
                    print(f"[smart_chat/CHAT] {len(chat_cache)} véhicule(s) trouvé(s) dans inventaire → injecté dans prompt")

            # ─── PART 4 : Contexte utilisateur confirmé ───
            confirmed_context = "\n\nCONTEXTE UTILISATEUR CONFIRMÉ (uniquement ce que l'utilisateur a explicitement dit) :\n"
            _has_data = False
            if ud.get("budget"):
                confirmed_context += f"- Budget : {ud['budget']}$\n"
                _has_data = True
            if ud.get("preferred_make"):
                confirmed_context += f"- Marque préférée : {ud['preferred_make']}\n"
                _has_data = True
            if ud.get("preferred_model"):
                confirmed_context += f"- Modèle cherché : {ud['preferred_model']}\n"
                _has_data = True
            if ud.get("financing"):
                confirmed_context += f"- Mode acquisition : {ud['financing']}\n"
                _has_data = True
            if ud.get("annual_km"):
                confirmed_context += f"- Kilométrage annuel : {ud['annual_km']} km\n"
                _has_data = True
            if ud.get("location"):
                confirmed_context += f"- Région : {ud['location']}\n"
                _has_data = True
            if not _has_data:
                confirmed_context += "- Aucune donnée confirmée pour le moment.\n"
            confirmed_context += "\nATTENTION : Ne jamais inventer ou supposer des données non listées ci-dessus.\n"

            # ─── Mémoire persistante DB ───
            user_memory_context = ""
            try:
                import sys
                sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                from database import get_user_memory as _get_mem
                user_mem = _get_mem(user_id) if user_id else {}
                if user_mem:
                    mem_parts = []
                    if user_mem.get('budget'): mem_parts.append(f"Budget connu: {user_mem['budget']}$")
                    if user_mem.get('preferred_make'): mem_parts.append(f"Marque préférée: {user_mem['preferred_make']}")
                    if user_mem.get('financing'): mem_parts.append(f"Mode acquisition: {user_mem['financing']}")
                    if user_mem.get('city'): mem_parts.append(f"Ville: {user_mem['city']}")
                    if mem_parts:
                        user_memory_context = "\n\nMÉMOIRE UTILISATEUR:\n" + "\n".join(mem_parts)
            except Exception as e:
                print(f"[user_memory] skip: {e}")

            # ─── PART 6 : Few-shot examples ───
            few_shot_examples = ""
            try:
                from database import get_similar_good_responses
                good = get_similar_good_responses(message, limit=3)
                if good and len(good) > 0:
                    few_shot_examples = "\n\nEXEMPLES DE BONNES RÉPONSES PASSÉES (inspire-toi de ce style) :\n"
                    for g in good:
                        q = g.get("question", g.get("query", ""))[:150]
                        r = g.get("response", g.get("answer", ""))[:300]
                        if q and r:
                            few_shot_examples += f"Q: {q}\nR: {r}\n\n"
            except Exception as e:
                print(f"[few_shot] skip: {e}")

            # GoogleSearch activé seulement pour les conseils généraux (fiabilité, prix marché)
            # DÉSACTIVÉ quand un véhicule est mentionné pour éviter l'hallucination d'annonces inventées
            _chat_has_vehicle_data = bool(chat_inventory_text)
            _chat_needs_search = not chat_vehicle_query  # pas de marque/modèle détecté → conseil général

            _vehicle_instructions = ""
            if chat_vehicle_query and _chat_has_vehicle_data:
                _vehicle_instructions = (
                    "- Des véhicules RÉELS sont fournis dans ce prompt — utilise UNIQUEMENT ces données\n"
                    "- NE PAS chercher d'autres véhicules ou annonces\n"
                )
            elif chat_vehicle_query and not _chat_has_vehicle_data:
                _vehicle_instructions = (
                    "- Ce modèle n'est PAS dans notre inventaire actuel\n"
                    "- NE PAS présenter de fiche véhicule inventée ou trouvée sur internet\n"
                    "- Tu peux donner des informations générales sur la fiabilité/valeur de ce modèle\n"
                    "- Propose de lancer une recherche dans notre inventaire ou de créer une alerte\n"
                )

            # ─── Propositions actives depuis vehicle_shown ───
            _vsh = session.get("vehicle_shown", {})
            if _vsh:
                vehicles_context = "\n\n=== PROPOSITIONS ACTIVES DANS CETTE SESSION ===\n"
                for _k, _v in _vsh.items():
                    vehicles_context += (
                        f"Proposition {_k} : {_v.get('year','')} {_v.get('make','')} {_v.get('model','')} "
                        f"— {_v.get('price','')}$ — {_v.get('dealer_name','')} — {_v.get('city','')} "
                        f"— Couleur: {_v.get('color','')} — Carburant: {_v.get('fuel_type','')} "
                        f"— Traction: {_v.get('drivetrain','')}\n"
                    )
                vehicles_context += (
                    "===============================================\n"
                    "RÈGLE ABSOLUE : Si l'utilisateur fait référence à un véhicule (couleur, année, "
                    "concessionnaire, prix, \"la première\", \"celle-là\"), "
                    "utiliser UNIQUEMENT les propositions listées ci-dessus. "
                    "Ne jamais mentionner un autre véhicule.\n"
                )
            else:
                vehicles_context = ""

            def _build_chat_prompt(h_str):
                return f"""{SYSTEM_PROMPT}

Historique:
{h_str}

Contexte: {context_summary}
{confirmed_context}
{user_memory_context}
{few_shot_examples}
{chat_inventory_text}
{vehicles_context}
Message de l'utilisateur: {message}

INSTRUCTIONS :
- Réponds directement sans préambule
{_vehicle_instructions}- Si budget mentionné → vérifie si le prix est réaliste sur le marché canadien
- Calcule toujours TPS 5% + TVQ 9.975% si un prix est mentionné
- NE PAS inclure de HTML brut dans ta réponse
"""
            full_prompt = _build_chat_prompt(history_str)
            # Token guard — CHAT
            _tok = estimate_tokens(full_prompt)
            if _tok > 25000:
                print(f"[smart_chat/CHAT] ⚠️  WARNING: prompt ~{_tok} tokens (seuil 25 000)")
            if _tok > 30000:
                print(f"[smart_chat/CHAT] 🔴 TRUNCATION: ~{_tok} tokens > 30 000 → historique réduit à 10 messages")
                history_str = _short_history(session, 10)
                full_prompt = _build_chat_prompt(history_str)

            if _chat_needs_search:
                # Conseil général (garanties, financement, comparaison générique) → GoogleSearch OK
                print(f"[smart_chat/CHAT] GoogleSearch activé (pas de marque/modèle spécifique)")
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=full_prompt,
                    config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
                )
            else:
                # Véhicule détecté → PAS de GoogleSearch (risque d'hallucination d'annonces)
                print(f"[smart_chat/CHAT] GoogleSearch DÉSACTIVÉ (véhicule détecté: '{chat_vehicle_query}', inventaire: {_chat_has_vehicle_data})")
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=full_prompt
                )
            chat_html_cards = format_vehicles_html_block(chat_cache) if chat_cache else ""
            result = {"intent": "CHAT", "response": response.text, "_html_cards": chat_html_cards}

    response_text = result.get("response", "")
    # ─── PART 5 : Guardrail anti-hallucination + nettoyage HTML ───
    if isinstance(response_text, str):
        response_text = apply_guardrails(response_text, session["user_data"])
        clean_text = remove_vehicle_bullets(strip_html(response_text))
        # Réassembler : fiches HTML structurées + texte Gemini nettoyé
        html_cards = result.pop("_html_cards", "") or ""
        result["response"] = clean_text
        result["html_cards"] = html_cards
        session["history"].append({"role": "assistant", "content": clean_text})
    update_context(user_id, intent_data, result["response"] if isinstance(result.get("response"), str) else "")
    session["history"] = session["history"][-20:]

    # ─── PART 7 : Mémoire persistante — sauvegarde depuis user_data ───
    try:
        import sys as _sys
        _sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
        from database import update_user_memory
        memory_update = {}
        if session["user_data"].get("budget"):
            memory_update["budget"] = session["user_data"]["budget"]
        if session["user_data"].get("preferred_make"):
            memory_update["preferred_make"] = session["user_data"]["preferred_make"]
        if session["user_data"].get("financing"):
            memory_update["financing"] = session["user_data"]["financing"]
        if memory_update:
            update_user_memory(user_id, memory_update)
    except Exception as e:
        print(f"[memory_save] skip: {e}")

    # ─── Persistance session SQLite ───
    save_session(user_id, sessions.get(user_id, {}))

    return result