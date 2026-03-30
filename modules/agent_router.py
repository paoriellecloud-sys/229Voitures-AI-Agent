from google import genai
from google.genai import types
from modules.scraper import analyze_listing, compare_listings, search_and_analyze
from modules.vin_checker import get_vehicle_report
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


# =============================
# SESSION MANAGEMENT
# =============================

def get_session(user_id: str) -> dict:
    if user_id not in sessions:
        sessions[user_id] = {
            "history": [],
            # DONNÉES UTILISATEUR (ce que l'user a explicitement dit)
            "user_data": {
                "budget": None,
                "vehicle_type": None,
                "preferred_make": None,
                "preferred_model": None,
                "location": None,
                "financing": None,
                "annual_km": None,
                "trade_in": None,
            },
            # ÉTAT OPÉRATIONNEL (non-user data, usage interne)
            "context": {
                "last_listings": [],
                "viewed_urls": [],
                "last_intent": None,
                "last_query": None,
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
    if ctx.get("last_listings"):
        listings_summary = ", ".join([f"#{i+1} {l}" for i, l in enumerate(ctx["last_listings"][:3])])
        parts.append(f"Derniers véhicules trouvés: {listings_summary}")
    context_str = "\n".join(parts) if parts else ""
    history_str = ""
    for msg in history[-6:]:
        role = "Utilisateur" if msg["role"] == "user" else "Agent"
        history_str += f"{role}: {msg['content'][:200]}\n"
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
               options, vehicle_id, raw_content, scraped_at
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
            "raw_content":      row["raw_content"],
            "scraped_at":       row["scraped_at"],
        })
    return results


def search_inventory_cache(query: str, limit: int = 5, vehicle_filter: str = None) -> list[dict]:
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
                photos TEXT, url TEXT, json_url TEXT, raw_content TEXT, scraped_at TEXT,
                UNIQUE(source, vehicle_id)
            )
        """)
        conn.commit()

        # Choisir la meilleure source de termes de recherche
        search_text = vehicle_filter or query
        raw_kw = [k.strip() for k in search_text.lower().split() if len(k.strip()) > 2]
        # Filtrer les stopwords français/génériques
        keywords = [k for k in raw_kw if k not in {s.lower() for s in STOPWORDS_FR}]
        if not keywords:
            keywords = raw_kw  # garde les originaux si tout filtré

        print(f"[search_inventory_cache] query={repr(query)} | vehicle_filter={repr(vehicle_filter)} | keywords={keywords}")

        # ── Essai 1 : AND strict sur max 3 mots-clés véhicule ──────────────
        kw_strict = keywords[:3]
        conditions = []
        params = []
        for kw in kw_strict:
            conditions.append("(LOWER(title) LIKE ? OR LOWER(make) LIKE ? OR LOWER(model) LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%", f"%{kw}%"])

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
            rows = _run_cache_sql(cursor, [f"({' OR '.join(or_parts)})"], or_params, limit)
            print(f"[search_inventory_cache] Essai OR souple ({kw_or}) → {len(rows)} résultat(s)")

        # ── Essai 3 : raw_content si toujours 0 ────────────────────────────
        if not rows and keywords:
            kw_raw = keywords[0]
            rows = _run_cache_sql(
                cursor,
                ["(LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ?)"],
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

        annee          = r.get("year", "")
        marque         = r.get("make", "")
        modele         = r.get("model", "")
        prix_marche    = r.get("avg_market_price", "")
        km             = r.get("mileage", "")
        ville          = r.get("city", "")
        province       = r.get("province", "")
        concessionnaire = r.get("dealer_name", "")
        telephone      = r.get("dealer_phone", "")
        transmission   = r.get("transmission", "")
        moteur         = r.get("engine", "")
        carburant      = r.get("fuel_type", "")
        traction       = r.get("drivetrain", "")
        couleur        = r.get("color", "")
        niv            = r.get("vin", "")
        stock          = r.get("vehicle_id", "")
        tps            = r.get("tps", "")
        tvq            = r.get("tvq", "")
        options        = (r.get("options", "") or "")[:200]
        source         = r.get("source", "")

        if prix and not tps:
            try:
                prix_num = float(str(prix).replace(",", "").replace("$", "").strip())
                tps = round(prix_num * 0.05, 2)
                tvq = round(prix_num * 0.09975, 2)
                total_taxes = round(prix_num + tps + tvq, 2)
            except Exception:
                total_taxes = ""
        else:
            try:
                prix_num = float(str(prix).replace(",", "").replace("$", "").strip())
                total_taxes = round(prix_num + float(str(tps).replace(",","")) + float(str(tvq).replace(",","")), 2)
            except Exception:
                total_taxes = ""

        # Score de fiabilité
        reliability = "✅ Données cohérentes"
        try:
            prix_float = float(str(prix).replace(",", "").replace("$", "").strip())
            km_float = float(str(km)) if km else 0
            prix_marche_float = float(str(prix_marche)) if prix_marche else 0
            if prix_marche_float > 0 and prix_float < prix_marche_float * 0.85:
                reliability = "⚠️ Prix suspect — vérifier l'état du véhicule"
            elif prix_marche_float > 0 and prix_float > prix_marche_float * 1.15:
                reliability = "💡 Prix au-dessus du marché — négocier"
            elif km_float > 150000:
                reliability = "⚠️ Kilométrage élevé — inspection recommandée"
        except Exception:
            pass

        line = f"""
Véhicule #{i} — {source}
  Titre      : {annee} {marque} {modele}
  Prix       : {prix}$ (marché moyen: {prix_marche}$)
  Taxes QC   : TPS {tps}$ + TVQ {tvq}$ = Total estimé {total_taxes}$
  Kilométrage: {km} km
  Localisation: {ville}, {province}
  Concessionnaire: {concessionnaire} | Tél: {telephone}
  Moteur     : {moteur} | Transmission: {transmission}
  Carburant  : {carburant} | Traction: {traction}
  Couleur    : {couleur}
  VIN        : {niv}
  N° Stock   : {stock}
  Options    : {options}
  Fiabilité  : {reliability}
  URL fiche  : {r.get('url', '')}
"""
        lines.append(line)

    lines.append("\n=== FIN DES DONNÉES FORCE OCCASION ===")
    return "\n".join(lines)


# =============================
# SYSTEM PROMPT
# =============================

SYSTEM_PROMPT = """
Tu es 229Voitures AI Agent, conseiller automobile expert et indépendant au Canada.
Tu es honnête, précis et tu protèges l'acheteur avant tout.
Tu es du côté du client. Jamais du vendeur.

═══════════════════════════════════════
RÈGLE 0 — ABSOLUE (priorité sur tout)
═══════════════════════════════════════
Tu distingues strictement 3 types d'informations :
1. DONNÉES UTILISATEUR : ce que l'utilisateur a explicitement écrit → seul type pouvant être cité comme fait
2. INFORMATIONS GÉNÉRALES : connaissances du marché → toujours présentées comme générales
3. ESTIMATIONS : calculs et suppositions → toujours marquées "(estimation)"

INTERDICTIONS ABSOLUES :
❌ Citer un budget, modèle ou marque que l'utilisateur n'a PAS explicitement mentionné
❌ Transformer une information générale en donnée utilisateur
❌ Inventer des données manquantes — toujours dire "Non disponible"
❌ Présenter un véhicule "représentatif" ou "similaire" comme un véhicule réel
❌ Mentionner un concessionnaire non présenté dans cette conversation
❌ Utiliser target=, class=, href= ou tout attribut HTML en texte brut

Si premier message = salut/bonjour/ça va/comment ça va → répondre normalement, aucune mention de véhicule ni budget.

═══════════════════════════════════════
COHÉRENCE CONVERSATIONNELLE
═══════════════════════════════════════
- Mémoriser TOUS les véhicules présentés dans la conversation en cours.
- Si l'utilisateur fait référence à un véhicule par sa ville, son concessionnaire, son prix, son ordre ("le premier", "celui de Montréal", "le moins cher", "celui-là", "ce véhicule") → identifier précisément CE véhicule dans l'historique et utiliser SES données exactes.
- Si la référence est ambiguë → clarifier avant de répondre : "Vous parlez du [Marque Modèle] à [Prix]$ chez [Concessionnaire] ?"
- Cette règle s'applique à TOUS les véhicules, TOUTES les marques, TOUTES les situations.

═══════════════════════════════════════
RÈGLE SUGGESTIONS PROACTIVES
═══════════════════════════════════════

L'agent suggère proactivement le contact concessionnaire SEULEMENT dans ces situations précises :

DÉCLENCHER la suggestion quand :
- L'utilisateur a vu les détails d'un véhicule spécifique ET pose des questions précises dessus (équipements, garantie, disponibilité)
- L'utilisateur exprime un intérêt clair : "je l'aime bien", "ça m'intéresse", "c'est dans mon budget", "pas mal"
- L'utilisateur demande comment aller plus loin
- L'utilisateur a comparé plusieurs véhicules et semble avoir choisi
- L'utilisateur pose une question à laquelle seul le concessionnaire peut répondre (disponibilité exacte, essai routier, reprise véhicule)

NE PAS déclencher la suggestion quand :
- L'utilisateur est encore en phase de recherche générale
- L'utilisateur vient juste de commencer la conversation
- L'utilisateur pose une question technique ou sur les garanties
- L'utilisateur n'a pas encore vu de véhicule spécifique
- La suggestion a déjà été faite dans cette conversation

FORMAT DE LA SUGGESTION (naturel, pas insistant) :
Ajoute à la fin de ta réponse, sur une nouvelle ligne :
"💬 Souhaitez-vous que je vous mette en contact avec [Nom concessionnaire] pour ce véhicule ?"

Si le concessionnaire est inconnu :
"💬 Souhaitez-vous être mis en contact avec ce concessionnaire ?"

RÈGLE : Une seule suggestion par conversation. Si l'utilisateur dit non → ne plus proposer.

═══════════════════════════════════════
CAPACITÉ LEADS
═══════════════════════════════════════
Quand l'utilisateur veut contacter un concessionnaire, NE PAS dire que tu ne peux pas.
Tu PEUX collecter les coordonnées et envoyer la demande automatiquement.
Déclenche toujours le processus de collecte.

═══════════════════════════════════════
FLUX QUALIFICATIF — RÈGLE DE DÉTECTION
═══════════════════════════════════════
Avant de chercher un véhicule, évalue si la demande est VAGUE ou PRÉCISE.

DEMANDE VAGUE (pose 2-3 questions max) :
- Moins de 2 critères mentionnés (ex: "je cherche une BMW")
- Pas de budget mentionné
- Pas de région mentionnée
- Pas de kilométrage ou année mentionnés

DEMANDE PRÉCISE (cherche immédiatement) :
- 3 critères ou plus mentionnés (ex: "BMW X5 2022, budget 50 000$, Montréal")
- L'utilisateur répond à tes questions qualificatives
- L'utilisateur envoie un lien URL
- L'utilisateur envoie une image/contrat

QUESTIONS QUALIFICATIVES PRIORITAIRES (choisis max 3 selon contexte) :
1. "Quel est votre budget approximatif ?"
2. "Vous êtes dans quelle région du Québec ?"
3. "Neuf ou occasion ?"
4. "Kilométrage maximum acceptable ?"
5. "Vous avez un véhicule à échanger ?"
6. "Achat comptant ou financement ?"
7. "Délai d'achat — urgent ou vous magasinez ?"

FORMAT QUESTIONS :
- Pose les questions de façon naturelle, pas comme une liste robotique
- Maximum 3 questions par message
- Mémorise les réponses pour toute la conversation
- Ne repose JAMAIS une question déjà répondue

RÈGLE ABSOLUE :
❌ Ne jamais chercher et présenter des véhicules sur une demande vague
✅ Qualifier d'abord → chercher ensuite → présenter les meilleurs résultats

═══════════════════════════════════════
PRINCIPES FONDAMENTAUX
═══════════════════════════════════════

1. HONNÊTETÉ RADICALE
- Si tu ne sais pas → "Je n'ai pas cette information."
- Si incertain → "Selon mes données, vérifiez avec le concessionnaire."
- Jamais d'invention. Jamais de supposition présentée comme un fait.

2. COHÉRENCE DES DONNÉES
- Chaque véhicule = entité unique avec SES propres données.
- Prix, km, VIN, stock, concessionnaire, ville = toujours le même véhicule.
- Donnée manquante → "Non disponible" + suggérer de contacter le concessionnaire.
- Maximum 3 véhicules par réponse de recherche — présenter les 3 meilleurs selon prix/km/localisation.

3. LOGIQUE DE CATÉGORIES STRICTE
Véhicules similaires = même catégorie ET fourchette de prix comparable.
- Micro-citadine : Spark, Mirage, Rio, Accent
- Berline compacte : Civic, Corolla, Elantra, Sentra, Mazda3, Forte, Golf, Impreza
- Berline intermédiaire : Camry, Accord, Altima, Sonata, Fusion, Malibu, Passat
- Berline plein format : Charger, 300, Avalon
- VUS sous-compact : Seltos, Venue, Trax, Encore, EcoSport, Qashqai, Kicks, HR-V, C-HR
- VUS compact : Rogue, RAV4, CR-V, Escape, Tucson, Sportage, Outlander, CX-5, Equinox, Forester
- VUS intermédiaire : Pilot, Highlander, Pathfinder, Traverse, Explorer, Murano, CX-9
- VUS plein format : Tahoe, Expedition, Armada, Suburban, Yukon, Durango
- VUS électrique : Model Y, ID.4, Ioniq 5, EV6, Mach-E, Ariya, bZ4X
- Camionnette compacte : Tacoma, Colorado, Ranger, Frontier, Ridgeline, Canyon
- Camionnette plein format : F-150, RAM 1500, Silverado, Sierra, Tundra, Titan
- Fourgonnette : Sienna, Odyssey, Carnival, Pacifica, Grand Caravan
- Électrique compacte : Model 3, Ioniq 6, Leaf, Bolt EV, i3
JAMAIS mélanger les catégories.

4. RÈGLES SUR LES LIENS
- Véhicule dans le cache local → bouton ⭐ avec lien direct
- Véhicule trouvé via recherche web → afficher le nom du site source en texte simple
- Lien non vérifié ou inconnu → ne pas afficher. Écrire : "🔎 Recherchez [Marque Modèle Année] [km]km [Ville] sur Google"
- JAMAIS d'attributs HTML en texte brut

5. RAISONNEMENT ÉTAPE PAR ÉTAPE
① Quelle est l'intention exacte de l'utilisateur ?
② Est-ce que je fais référence à un véhicule déjà présenté ? Si oui → utiliser SES données
③ Données vérifiées disponibles ? Si non → dire clairement
④ Ma réponse est-elle cohérente avec tout ce qui a été dit avant ?
⑤ Est-ce que je guide vers une action concrète et utile ?

6. PROTECTION DE L'ACHETEUR
- Prix > marché de 10%+ → signaler avec le chiffre exact de l'écart
- Kilométrage > 150 000 km → inspection mécanique indépendante obligatoire
- Prix anormalement bas vs marché → avertir red flag potentiel
- Taux de financement > 8% → suggérer de comparer avec sa banque ou caisse
- Véhicule > 10 ans → mentionner coûts d'entretien potentiellement élevés
- Premier acheteur → expliquer les étapes clés sans jargon

7. CALCULS TOUJOURS EXACTS
- TPS = prix × 0.05 (arrondi 2 décimales)
- TVQ = prix × 0.09975 (jamais calculé sur prix+TPS)
- Total = prix + TPS + TVQ
- Format obligatoire : prix$ + TPS X$ + TVQ Y$ = Total Z$
- Si prix = estimation → indiquer "(estimation)" dans le total

8. FORMAT DE RÉPONSE
- Longueur adaptée au contexte : courte pour les questions simples, détaillée pour les analyses
- Toujours français québécois, toujours en dollars canadiens (CAD)
- UNE seule question ou suggestion concrète à la fin
- Jamais "Bien sûr!", "Absolument!", "Avec plaisir!", "Certainement!" en début de réponse
- Jamais répéter l'introduction après le premier message
- Jamais afficher "Prochaines étapes suggérées" comme section
- Jamais deux questions dans la même réponse
Mots et expressions INTERDITS en début de réponse :
"Excellent!", "Excellent choix!", "Parfait!", "Super!", "Très bien!",
"Bien sûr!", "Absolument!", "Avec plaisir!", "Certainement!",
"C'est une excellente nouvelle", "Je suis ravi"
→ Commencer directement par l'information utile.

9. PRÉSENTATION VÉHICULE (format fixe obligatoire)
🚗 [Année] [Marque] [Modèle] [Version] — [Concessionnaire], [Ville]
- Prix : [X]$ | Marché moyen : [Y]$ | [Sous/Au-dessus/Dans] la moyenne
- Kilométrage : [X] km
- Moteur : [X] | Transmission : [X] | Carburant : [X]
- VIN : [X] | N° Stock : [X]
💰 TPS [X]$ + TVQ [X]$ = Total [X]$
🔗 [lien si disponible et vérifié]

10. RÈGLE CONCESSIONNAIRE
- Toujours afficher le NOM EXACT du concessionnaire tel que disponible dans les données
- Si non disponible → 🔎 Recherchez "[Marque] [Modèle] [Année] [km]km [Ville]" sur Google ou AutoHebdo
- Jamais inventer ou supposer un nom de concessionnaire

11. RÈGLE QUALITÉ MINIMALE
Un véhicule ne peut être présenté que s'il possède AU MINIMUM :
- Prix exact (pas une estimation vague)
- Kilométrage
- Ville
- Nom concessionnaire OU lien direct vers l'annonce
Si ces éléments manquent → ne pas présenter de fiche. Rediriger : "Cherchez directement sur AutoHebdo, Otogo ou Kijiji Autos et envoyez-moi le lien pour une analyse complète."

═══════════════════════════════════════
CONNAISSANCES SPÉCIALISÉES
═══════════════════════════════════════

CONTRAT CCAQ :
A=Prix véhicule | B=Accessoires | C=Prix vente
D=Réduction | E=Prix après réduction | F=Échange
H=Sous-total taxable | K=TPS | L=TVQ | M=Total
P=Accessoires F&I | S=Total à payer | W=Solde livraison

MARCHÉ QUÉBÉCOIS 2025-2026 :
- Taux financement bon crédit (700+) : 5.99%-7.99%
- Taux financement crédit moyen (600-699) : 8%-14%
- Dépréciation moyenne véhicule : 15-20% première année, 10-15% années suivantes
- Kilométrage annuel moyen Québec : 18 000-22 000 km/an
- Véhicule considéré à kilométrage élevé au Québec : > 150 000 km

FLUX QUALIFICATIF ADAPTATIF (une question à la fois, seulement si info manquante) :
- Si l'utilisateur mentionne déjà le type de véhicule → ne pas reposer la question
- Si l'utilisateur mentionne déjà un budget → ne pas reposer la question
- Questions dans l'ordre, seulement si nécessaire :
  1. Type de véhicule souhaité ? (VUS, berline, camionnette, électrique, fourgonnette)
  2. Utilisation principale ? (famille, travail, ville, longues distances, hors-route)
  3. Budget total ou mensuel ?
  4. Achat comptant ou financement ?
  5. Véhicule d'échange ?
  6. Préférence pour la traction intégrale (AWD) — important pour les hivers québécois ?
  7. Critères prioritaires ? (espace, fiabilité, consommation, technologie, confort)

═══════════════════════════════════════
CONSEILLER GARANTIES ET PRODUITS F&I
(UNIVERSEL — TOUTES MARQUES)
═══════════════════════════════════════

ANALYSE DU PROFIL (si info manquante → déduire logiquement du contexte) :
- Type véhicule : neuf / occasion / certifié d'occasion
- Motorisation : essence / hybride / électrique / diesel
- Mode acquisition : achat comptant / financement / location
- Durée de possession prévue
- Kilométrage annuel estimé
- Tolérance au risque financier

SCORING INTERNE DE RISQUE (ne jamais afficher le score brut) :
+30 financement | +25 long terme >48 mois | +20 km >20 000/an
+15 profil prudent mentionné | +10 véhicule occasion | +10 véhicule complexe (hybride/électrique/luxe)
-20 location | -15 court terme <36 mois | -10 km <12 000/an
0-30 = faible besoin | 31-60 = modéré | 61-100 = fortement recommandé

LOGIQUE DÉCISIONNELLE UNIVERSELLE :
- Location → ✔ EWU + esthétique | ❌ garantie mécanique inutile
- Financement long terme → ✔ garantie prolongée intermédiaire + protection prêt
- Véhicule usagé → ✔ garantie fortement recommandée selon âge et km
- Véhicule de luxe (réparations coûteuses) → ✔ garantie complète obligatoire
- Électrique/hybride → ✔ garantie spécifique batterie/composants électriques
- Budget serré → ✔ motopropulseur minimum | ❌ tout le reste
- Marque reconnue fiable selon fiabilité historique → garantie intermédiaire suffisante
- Marque à fiabilité variable ou km élevé → garantie complète recommandée

RÈGLES DE COMMUNICATION F&I :
- Toujours trancher clairement : ✔ recommander / ❌ déconseiller / ⚖️ optionnel
- Jamais rester neutre ou dire "peut être pertinent"
- Langage réalité concession : "Ils vont souvent proposer...", "C'est là qu'ils font leur marge...", "Demande le prix séparé"
- Jamais donner un prix fixe — dire : "Le prix varie — compare avec le risque réel de réparation"
- Toujours inclure un warning concret sur les pièges
- Noms de produits spécifiques à une marque → ne pas mentionner, rester universel

PIÈGES À DÉTECTER ET SIGNALER :
🚩 "Offre valide aujourd'hui seulement" → pression artificielle, prendre le temps de réfléchir
🚩 Garantie financée dans le prêt → coût réel augmenté avec les intérêts
🚩 Bundle produits groupés → demander le prix séparé de chaque produit
🚩 Plafond de remboursement caché dans la garantie
🚩 Garantie proposée en location → quasi inutile
🚩 Prix > 2 500$ pour une garantie → négocier

FORMAT RÉPONSE GARANTIES (obligatoire) :
🧠 Analyse rapide : [profil en 1 phrase directe]
💡 Ce que je recommande : [✔ max 2 produits avec décision claire]
⚠️ Ce que tu peux éviter : [❌ avec explication directe]
💰 Est-ce que ça vaut le coup ? [réponse directe oui/non + raison concrète]
🎯 Conclusion : [1 phrase tranchée]
👉 [1 seule question sur le prix ou la couverture exacte proposée]

RÈGLE ABSOLUE GARANTIES : Ne jamais recommander tous les produits. Toujours expliquer POURQUOI. Toujours adapter à la situation réelle.
"""

INTENT_PROMPT = """
Analyze this user message and return ONLY a JSON object with the intent and extracted data.

Message: "{message}"
Conversation context: {context}

Return exactly this JSON format:
{{
  "intent": "CHAT" | "SEARCH" | "ANALYZE_URL" | "COMPARE_URLS" | "CHECK_VIN" | "FOLLOWUP",
  "urls": [],
  "vin": null,
  "query": null,
  "site": null,
  "count": 2,
  "followup_action": null,
  "vehicle_filter": null
}}

Intent rules:

- CHAT: Use for ALL evaluation and advice questions:
  * "bonne affaire?", "c'est bien?", "fiable?", "vaut la peine?", "recommandes-tu?"
  * "problemes connus", "rappels", "historique de fiabilite"
  * "X$ c'est raisonnable?", "trop cher?", "bon prix?"
  * Negotiation advice, cost of ownership questions
  IMPORTANT: For evaluation questions, answer the question FIRST directly,
  then offer to search for listings as a follow-up suggestion.

- SEARCH: ONLY when user EXPLICITLY wants to find/list vehicles.
  Requires keywords: trouve, cherche, montre, propose, liste, donne moi
  Also trigger SEARCH for: "je recherche", "je cherche", "je veux trouver"
  Examples → SEARCH:
  - "Trouve moi un Toyota RAV4 2021" → SEARCH
  - "Cherche des Honda CRV sous 25000" → SEARCH
  - "je recherche une Seltos 2022 au quebec" → SEARCH
  - "Montre moi des Kia Seltos au Quebec" → SEARCH

- ANALYZE_URL: message contains exactly 1 URL
- COMPARE_URLS: message contains 2+ URLs
- CHECK_VIN: message contains a VIN (17 alphanumeric characters)
- FOLLOWUP: user responds to a previous suggestion (ex: "le 2", "oui", "compare-les", "verifie le vin")

For SEARCH extract:
- query: exact vehicle search terms (make, model, year, trim, budget, location)
- vehicle_filter: specific make+model being searched (ex: "Kia Seltos 2022")
- site: dealer domain if mentioned, null otherwise
- count: number of results requested (default 3)

Return ONLY the JSON, no explanation.
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

    if action == "select_listing" and ctx["last_listings"]:
        listings_text = "\n".join([f"#{i+1}: {l}" for i, l in enumerate(ctx["last_listings"])])
        prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nContexte: {context_summary}\nAnnonces:\n{listings_text}\nL'utilisateur a sélectionné une annonce. Identifie laquelle et résume-la. Propose: vérifier VIN, comparer, ou contacter le concessionnaire. Max 4 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "check_vin":
        prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nL'utilisateur veut vérifier le VIN. Demande-lui le numéro VIN. Max 2 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "compare" and len(ctx["last_listings"]) >= 2:
        listings_text = "\n".join([f"#{i+1}: {l}" for i, l in enumerate(ctx["last_listings"][:3])])
        budget_label = f"{session['user_data']['budget']}$" if session["user_data"].get("budget") else "non précisé"
        prompt = f"{SYSTEM_PROMPT}\nCompare ces véhicules et recommande le meilleur. Budget: {budget_label}\n{listings_text}\nMax 5 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
        return {"intent": "FOLLOWUP", "response": response.text}

    elif action == "more_results":
        last_query = ctx.get("last_query", "véhicule occasion Canada")
        result = search_and_analyze(query=last_query, count=3)
        return {"intent": "SEARCH", "response": result.get("analysis", ""), "urls_found": result.get("urls_found", []), "scraped_count": result.get("scraped_count", 0)}

    else:
        prompt = f"{SYSTEM_PROMPT}\nHistorique:\n{history_str}\nContexte: {context_summary}\nContinue à aider l'utilisateur naturellement. Max 4 phrases en français."
        response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt, config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())]))
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
                pattern = re.compile(
                    rf'{re.escape(phrase)}[^.]*\d[\d\s,]*\s*\$[^.]*\.',
                    re.IGNORECASE
                )
                response = pattern.sub(
                    "Vous ne m'avez pas encore précisé de budget.",
                    response
                )
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

def smart_chat(message: str, user_id: str = "default") -> dict:
    session = get_session(user_id)

    # ─── PART 3 : Extraction user_data stricte (uniquement ce que l'user a dit) ───
    msg_lower = message.lower()
    ud = session["user_data"]
    _budget_patterns = [
        r'(?:mon budget est|budget de|je veux dépenser|maximum)\s*(\d[\d\s,]*)\s*\$',
        r'(\d[\d\s,]*)\s*\$\s*(?:de budget|max|maximum)',
        r'autour de\s*(\d[\d\s,]*)\s*\$',
    ]
    for _bp in _budget_patterns:
        _m = re.search(_bp, msg_lower)
        if _m:
            _amt = float(_m.group(1).replace(" ", "").replace(",", ""))
            if 1000 < _amt < 200000:
                ud["budget"] = _amt
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
    intent_data = detect_intent(message, context_summary)
    intent = intent_data.get("intent", "CHAT")
    result = {}

    if intent == "CREATE_ALERT":
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
        result = {
            "intent": "CREATE_ALERT",
            "response": "Je vais créer une alerte pour vous ! Pour vous envoyer l'email, j'ai besoin de votre adresse courriel. Quelle est-elle ?",
            "needs_email": True,
            "criteria": criteria,
        }

    elif intent == "LEAD_REQUEST":
        last_listings = session["context"].get("last_listings", [])
        vehicle_title = session["context"].get("last_query", "véhicule")
        vehicle_price = 0
        vehicle_url = ""
        dealer_name = ""
        if last_listings:
            v = last_listings[0] if isinstance(last_listings, list) else last_listings
            if isinstance(v, dict):
                vehicle_title = v.get("title", vehicle_title)
                vehicle_price = v.get("price", 0)
                vehicle_url = v.get("url", "")
                dealer_name = v.get("dealer", "")
            elif isinstance(v, str):
                vehicle_url = v
        session["context"]["pending_lead"] = {
            "vehicle_title": vehicle_title,
            "vehicle_price": vehicle_price,
            "vehicle_url": vehicle_url,
            "dealer_name": dealer_name,
        }
        result = {
            "intent": "LEAD_REQUEST",
            "response": (
                f"Je vais vous mettre en contact avec le concessionnaire pour le {vehicle_title}.\n\n"
                "Pour envoyer votre demande, j'ai besoin de :\n"
                "• Votre prénom et nom\n"
                "• Votre numéro de téléphone\n"
                "• Votre email\n"
                "• Un message optionnel\n\n"
                "Commençons — quel est votre nom complet ?"
            ),
        }

    elif intent == "GARANTIES":
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

    elif intent == "FOLLOWUP":
        result = handle_followup(user_id, intent_data, history_str, context_summary)

    elif intent == "CHECK_VIN" and intent_data.get("vin"):
        result = {"intent": "CHECK_VIN", "response": get_vehicle_report(intent_data["vin"])}

    elif intent == "COMPARE_URLS" and len(intent_data.get("urls", [])) >= 2:
        compare_result = compare_listings(intent_data["urls"][0], intent_data["urls"][1])
        result = {"intent": "COMPARE_URLS", "response": compare_result.get("comparison", ""), "urls": intent_data["urls"]}

    elif intent == "ANALYZE_URL" and len(intent_data.get("urls", [])) >= 1:
        analyze_result = analyze_listing(intent_data["urls"][0])
        result = {"intent": "ANALYZE_URL", "response": analyze_result.get("analysis", ""), "url": intent_data["urls"][0], "scraped": analyze_result.get("scraped", False)}

    elif intent == "SEARCH" and intent_data.get("query"):
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
        cache_results = search_inventory_cache(query, limit=5, vehicle_filter=vehicle_filter)

        if cache_results:
            cache_text = format_cache_results_for_prompt(cache_results)
            session["context"]["last_listings"] = [r["url"] for r in cache_results]

            prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

{cache_text}

RECHERCHE DE L'UTILISATEUR : "{query}"

INSTRUCTIONS :
- Présente les véhicules trouvés en utilisant UNIQUEMENT les données réelles ci-dessus
- Utilise le FORMAT DE PRÉSENTATION défini dans tes instructions
- Compare le prix au prix du marché si disponible
- Si le kilométrage > 100 000 km, suggère de vérifier le VIN
- Termine avec une question concrète (vérifier VIN, voir plus de détails, comparer ?)
- NE PAS inventer de données — utilise seulement ce qui est fourni
- NE PAS inclure de HTML brut dans ta réponse
"""
            # Token guard — SEARCH cache
            _tok = estimate_tokens(prompt)
            if _tok > 25000:
                print(f"[smart_chat/SEARCH-cache] ⚠️  WARNING: prompt ~{_tok} tokens (seuil 25 000)")
            if _tok > 30000:
                print(f"[smart_chat/SEARCH-cache] 🔴 TRUNCATION: ~{_tok} tokens > 30 000 → historique réduit à 10 messages")
                history_str = _short_history(session, 10)
                prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

{cache_text}

RECHERCHE DE L'UTILISATEUR : "{query}"

INSTRUCTIONS :
- Présente les véhicules trouvés en utilisant UNIQUEMENT les données réelles ci-dessus
- Utilise le FORMAT DE PRÉSENTATION défini dans tes instructions
- Compare le prix au prix du marché si disponible
- Si le kilométrage > 100 000 km, suggère de vérifier le VIN
- Termine avec une question concrète (vérifier VIN, voir plus de détails, comparer ?)
- NE PAS inventer de données — utilise seulement ce qui est fourni
- NE PAS inclure de HTML brut dans ta réponse
"""
            response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
            result = {
                "intent": "SEARCH",
                "response": response.text,
                "urls_found": [r["url"] for r in cache_results],
                "scraped_count": len(cache_results),
                "source": "inventory_cache"
            }

        else:
            # ─── ÉTAPE 2 : Fallback — recherche web via SerpAPI ───
            print(f"[smart_chat] Aucun résultat local pour '{query}' → fallback SerpAPI")
            search_result = search_and_analyze(
                query=query,
                site=intent_data.get("site"),
                count=intent_data.get("count", 3)
            )
            session["context"]["last_listings"] = search_result.get("urls_found", [])

            try:
                log_search(query=query, intent="SEARCH", results_count=search_result.get("scraped_count", 0))
            except Exception:
                pass

            # Nettoyer le HTML parasite dans la réponse SerpAPI
            serp_response = strip_html(search_result.get("analysis", ""))

            # Construire un prompt avec note géo + résultats SerpAPI
            geo_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

RECHERCHE DE L'UTILISATEUR : "{query}"

INSTRUCTION : Aucun véhicule trouvé dans l'inventaire local. Élargis la recherche géographiquement — propose Québec, Lévis, Montréal comme alternatives proches.

RÉSULTATS WEB TROUVÉS :
{serp_response}
"""
            # Token guard — SEARCH SerpAPI
            _tok = estimate_tokens(geo_prompt)
            if _tok > 25000:
                print(f"[smart_chat/SEARCH-serp] ⚠️  WARNING: prompt ~{_tok} tokens (seuil 25 000)")
            if _tok > 30000:
                print(f"[smart_chat/SEARCH-serp] 🔴 TRUNCATION: ~{_tok} tokens > 30 000 → historique réduit à 10 messages")
                history_str = _short_history(session, 10)
                geo_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}

RECHERCHE DE L'UTILISATEUR : "{query}"

INSTRUCTION : Aucun véhicule trouvé dans l'inventaire local. Élargis la recherche géographiquement — propose Québec, Lévis, Montréal comme alternatives proches.

RÉSULTATS WEB TROUVÉS :
{serp_response}
"""
            geo_response = client.models.generate_content(model="gemini-2.5-flash", contents=geo_prompt)

            result = {
                "intent": "SEARCH",
                "response": geo_response.text,
                "urls_found": search_result.get("urls_found", []),
                "scraped_count": search_result.get("scraped_count", 0),
                "source": "serpapi"
            }

    else:
        # ─── CHAT — conseils, fiabilité, prix, etc. ───
        ud = session["user_data"]

        # ─── Collecte progressive lead en cours ───
        pending_lead = session["context"].get("pending_lead")
        if pending_lead and not pending_lead.get("name"):
            if re.search(r'^[A-Za-zÀ-ÿ\s\-]{3,40}$', message.strip()):
                session["context"]["pending_lead"]["name"] = message.strip()
                result = {
                    "intent": "LEAD_COLLECT",
                    "response": f"Merci {message.strip().split()[0]} ! Quel est votre numéro de téléphone ?",
                }
        elif pending_lead and pending_lead.get("name") and not pending_lead.get("phone"):
            session["context"]["pending_lead"]["phone"] = message.strip()
            result = {
                "intent": "LEAD_COLLECT",
                "response": "Parfait. Quelle est votre adresse email ?",
            }
        elif pending_lead and pending_lead.get("phone") and not pending_lead.get("email"):
            if "@" in message:
                session["context"]["pending_lead"]["email"] = message.strip()
                lead_data = dict(session["context"]["pending_lead"])
                lead_data["user_id"] = user_id
                try:
                    import sys as _sys2
                    _sys2.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
                    from lead_service import create_lead
                    create_lead(lead_data)
                    dealer = lead_data.get("dealer_name") or "le concessionnaire"
                    result = {
                        "intent": "LEAD_SENT",
                        "response": (
                            f"✅ Votre demande a été envoyée à {dealer} pour le {lead_data.get('vehicle_title')}.\n\n"
                            "Ils vont vous contacter sous 24-48h. En attendant, souhaitez-vous que je vérifie l'historique VIN de ce véhicule ?"
                        ),
                    }
                    session["context"]["pending_lead"] = None
                except Exception as e:
                    print(f"[lead_collect] error: {e}")
                    result = {"intent": "LEAD_ERROR", "response": "Une erreur s'est produite. Contactez directement le concessionnaire."}

        if not result:
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

            full_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}
{confirmed_context}
{user_memory_context}
{few_shot_examples}

Message de l'utilisateur: {message}

INSTRUCTIONS :
- Réponds directement sans préambule
- Si l'utilisateur mentionne un modèle → utilise Google Search pour les prix actuels au Canada
- Si budget mentionné → vérifie si le prix est réaliste sur le marché canadien
- Calcule toujours TPS 5% + TVQ 9.975% si un prix est mentionné
- NE PAS inclure de HTML brut dans ta réponse
"""
            # Token guard — CHAT
            _tok = estimate_tokens(full_prompt)
            if _tok > 25000:
                print(f"[smart_chat/CHAT] ⚠️  WARNING: prompt ~{_tok} tokens (seuil 25 000)")
            if _tok > 30000:
                print(f"[smart_chat/CHAT] 🔴 TRUNCATION: ~{_tok} tokens > 30 000 → historique réduit à 10 messages")
                history_str = _short_history(session, 10)
                full_prompt = f"""
{SYSTEM_PROMPT}

Historique:
{history_str}

Contexte: {context_summary}
{confirmed_context}
{user_memory_context}
{few_shot_examples}

Message de l'utilisateur: {message}

INSTRUCTIONS :
- Réponds directement sans préambule
- Si l'utilisateur mentionne un modèle → utilise Google Search pour les prix actuels au Canada
- Si budget mentionné → vérifie si le prix est réaliste sur le marché canadien
- Calcule toujours TPS 5% + TVQ 9.975% si un prix est mentionné
- NE PAS inclure de HTML brut dans ta réponse
"""
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=full_prompt,
                config=types.GenerateContentConfig(tools=[types.Tool(google_search=types.GoogleSearch())])
            )
            result = {"intent": "CHAT", "response": response.text}

    response_text = result.get("response", "")
    # ─── PART 5 : Guardrail anti-hallucination + nettoyage HTML ───
    if isinstance(response_text, str):
        response_text = apply_guardrails(response_text, session["user_data"])
        result["response"] = strip_html(response_text)
        session["history"].append({"role": "assistant", "content": result["response"]})
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

    return result