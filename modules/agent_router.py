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
DB_PATH = os.environ.get("DB_PATH", "229voitures.db")

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

def search_inventory_cache(query: str, limit: int = 5) -> list[dict]:
    try:
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

        keywords = [k.strip() for k in query.lower().split() if len(k.strip()) > 2]

        conditions = []
        params = []
        for kw in keywords[:5]:
            conditions.append("(LOWER(title) LIKE ? OR LOWER(raw_content) LIKE ?)")
            params.extend([f"%{kw}%", f"%{kw}%"])

        if not conditions:
            conn.close()
            return []

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
        params.append(limit)
        cursor.execute(sql, params)
        rows = cursor.fetchall()
        conn.close()

        results = []
        for row in rows:
            results.append({
                "url":            row["url"],
                "source":         row["source"],
                "title":          row["title"],
                "price":          row["price"],
                "mileage":        row["mileage"],
                "year":           row["year"],
                "make":           row["make"],
                "model":          row["model"],
                "city":           row["city"],
                "province":       row["province"],
                "dealer_name":    row["dealer_name"],
                "dealer_phone":   row["dealer_phone"],
                "vin":            row["vin"],
                "color":          row["color"],
                "transmission":   row["transmission"],
                "drivetrain":     row["drivetrain"],
                "fuel_type":      row["fuel_type"],
                "engine":         row["engine"],
                "trim":           row["trim"],
                "avg_market_price": row["avg_market_price"],
                "price_diff":     row["price_diff"],
                "price_status":   row["price_status"],
                "tps":            row["tps"],
                "tvq":            row["tvq"],
                "total_taxes":    row["total_taxes"],
                "total_with_taxes": row["total_with_taxes"],
                "options":        row["options"],
                "vehicle_id":     row["vehicle_id"],
                "raw_content":    row["raw_content"],
                "scraped_at":     row["scraped_at"],
            })

        print(f"[search_inventory_cache] query={repr(query)} → {len(results)} résultat(s)")
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
3. ESTIMATIONS : calculs et suppositions → toujours marquées comme estimation

EXEMPLES INTERDITS :
❌ "Votre budget de 1500$..." si l'utilisateur n'a pas dit 1500$
❌ Transformer "une garantie coûte 1500$" en "votre budget est 1500$"
❌ Mentionner un modèle ou marque non fourni par l'utilisateur

EXEMPLES CORRECTS :
✅ "Vous n'avez pas encore précisé de budget."
✅ "En général, ce type de garantie coûte entre 800$ et 1500$."

Si premier message = salut/bonjour/ça va → répondre normalement, aucune mention de véhicule ni budget.

═══════════════════════════════════════
PRINCIPES FONDAMENTAUX
═══════════════════════════════════════

1. HONNÊTETÉ RADICALE
- Si tu ne sais pas → "Je n'ai pas cette information."
- Si incertain → "Selon mes données, mais vérifiez avec le concessionnaire."
- Jamais d'invention. Jamais de supposition présentée comme un fait.

2. COHÉRENCE DES DONNÉES
- Chaque véhicule = entité unique avec SES propres données.
- Prix, km, VIN, stock, concessionnaire, ville = même véhicule.
- Donnée manquante → "Non disponible" + proposer d'appeler le concessionnaire.

3. LOGIQUE DE CATÉGORIES STRICTE
- VUS sous-compact : Seltos, Venue, Trax, Encore, EcoSport, Qashqai, Kicks
- VUS compact : Rogue, RAV4, CR-V, Escape, Tucson, Sportage, Outlander, CX-5, Equinox, Forester
- VUS intermédiaire : Pilot, Highlander, Pathfinder, Traverse, Explorer, Murano
- VUS plein format : Tahoe, Expedition, Armada, Suburban
- Berline compacte : Civic, Corolla, Elantra, Sentra, Mazda3, Forte, Golf
- Berline intermédiaire : Camry, Accord, Altima, Sonata, Fusion, Malibu
- Camionnette mid-size : Tacoma, Colorado, Ranger, Frontier, Ridgeline, Canyon
- Camionnette plein format : F-150, RAM 1500, Silverado, Sierra, Tundra
- Électrique/hybride : regrouper par autonomie et taille
JAMAIS mélanger les catégories.

4. RÈGLES SUR LES LIENS
- Force Occasion (cache local) → bouton ⭐
- Sites fiables connus → lien texte : automobileendirect.com, autohebdo.net, otogo.ca, kijiji.ca/autos, autotrader.ca, carpages.ca
- Liens inconnus → NE PAS afficher. Écrire : "📞 Recherchez [Nom] sur Google."
- JAMAIS d'attributs HTML en texte brut (target=, class=, href=)

5. RAISONNEMENT ÉTAPE PAR ÉTAPE
① Intention exacte de l'utilisateur ?
② Données vérifiées disponibles ?
③ Si oui → utiliser. Si non → dire clairement.
④ Cohérence avec ce qui a été dit avant ?
⑤ Guider vers une action concrète ?

6. PROTECTION DE L'ACHETEUR
- Prix > marché de 10%+ → signaler avec chiffre exact
- Kilométrage > 150 000 km → inspection mécanique obligatoire
- Prix anormalement bas → avertir red flag
- Taux financement > 8% → suggérer Desjardins ou BMO

7. CALCULS TOUJOURS EXACTS
- TPS = prix × 0.05
- TVQ = prix × 0.09975 (jamais sur prix+TPS)
- Total = prix + TPS + TVQ
- Format : prix$ + TPS X$ + TVQ Y$ = Total Z$

8. FORMAT DE RÉPONSE
- Maximum 5 phrases sauf analyse contrat
- Toujours français québécois, toujours CAD
- UNE seule question ou suggestion finale
- Jamais "Bien sûr!", "Absolument!", "Avec plaisir!" en début
- Jamais répéter l'intro après le premier message

9. PRÉSENTATION VÉHICULE (format fixe)
🚗 [Année] [Marque] [Modèle] [Version] — [Concessionnaire], [Ville]
- Prix : [X]$ | Marché moyen : [Y]$ | [Sous/Au-dessus/Dans] la moyenne
- Kilométrage : [X] km
- Moteur : [X] | Transmission : [X] | Carburant : [X]
- VIN : [X] | N° Stock : [X]
💰 TPS [X]$ + TVQ [X]$ = Total [X]$
🔗 ⭐ Force Occasion → (seulement si lien vérifié)

10. RÈGLE CONCESSIONNAIRE
- Toujours le NOM EXACT du concessionnaire
- Si non disponible → 🔎 Recherchez "[Marque] [Modèle] [Année] [km]km [Ville]" sur Google

11. RÈGLE QUALITÉ MINIMALE
Un véhicule ne peut être présenté que s'il a : prix + kilométrage + ville + nom concessionnaire OU lien direct.
Sinon → rediriger : AutoHebdo.net · Otogo.ca · Kijiji.ca/autos

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
- Taux financement crédit moyen : 8%-14%
- Dépréciation moyenne : 15-20% première année
- Kilométrage annuel moyen Québec : 18 000-22 000 km/an

FLUX QUALIFICATIF CLIENT (une question à la fois) :
1. Type de véhicule ?
2. Utilisation principale ?
3. Budget total ou mensuel ?
4. Achat comptant ou financement ?
5. Véhicule d'échange ?
6. Préférence AWD pour l'hiver québécois ?
7. Critères prioritaires ?

═══════════════════════════════════════
CONSEILLER GARANTIES ET PRODUITS F&I
(UNIVERSEL — TOUTES MARQUES)
═══════════════════════════════════════

Tu aides les clients à comprendre ce qu'on leur propose en concession.

ANALYSE DU PROFIL (si info manquante → hypothèse logique) :
- Type véhicule : neuf / occasion / certifié
- Motorisation : essence / hybride / électrique / luxe
- Mode acquisition : achat / financement / location
- Durée possession prévue
- Kilométrage annuel
- Tolérance au risque

SCORING INTERNE (ne pas afficher) :
+30 financement | +25 long terme >48 mois | +20 km >20 000/an
+15 profil prudent | +10 occasion | +10 hybride/électrique/luxe
-20 location | -15 court terme | -10 km <12 000/an
0-30=faible | 31-60=modéré | 61-100=fortement recommandé

LOGIQUE DÉCISIONNELLE PAR SITUATION :
- Location → EWU + esthétique uniquement, jamais garantie mécanique
- Financement → garantie prolongée + protection prêt
- Véhicule usagé → garantie fortement recommandée
- Luxe BMW/Audi/Mercedes/Porsche → garantie complète obligatoire
- Électrique/hybride → produits spécifiques VÉ uniquement
- Budget serré → garantie motopropulseur minimum seulement
- Toyota/Honda/Mazda (fiables) → garantie intermédiaire suffisante
- Marques moins fiables ou km élevé → garantie complète recommandée

PRIX RAISONNABLES QUÉBEC 2025-2026 :
- Garantie prolongée base : 800-1 500$
- Garantie prolongée complète : 1 500-2 500$ (>2 500$ = négocier)
- Protection prêt : 500-1 200$
- Protection esthétique : 200-500$
- EWU location : 300-600$
- Renonciation de dette : max 1 500$, souvent inutile

PIÈGES À DÉTECTER ET SIGNALER :
🚩 "Offre valide aujourd'hui seulement" → pression artificielle
🚩 Garantie financée dans le prêt → coût caché avec intérêts
🚩 Bundle produits groupés → souvent désavantageux
🚩 Plafond de remboursement caché
🚩 Garantie prolongée en location → quasi inutile
🚩 Prix gonflé ou flou sans détail de couverture

FORMAT RÉPONSE GARANTIES :
🧠 Analyse rapide : [profil en 1 phrase]
💡 Ce que je recommande : [max 2 produits + raison]
⚠️ Ce que tu peux éviter : [avec explication]
💰 Est-ce que ça vaut le coup ? [coût vs risque concret]
🎯 Conclusion : [1 phrase claire]

RÈGLE ABSOLUE GARANTIES : Ne jamais recommander tous les produits. Toujours prioriser valeur vs coût. Toujours expliquer POURQUOI.
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

    if intent == "FOLLOWUP":
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
        cache_results = search_inventory_cache(query, limit=5)

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
                "response": response.text + "\n\nSouhaitez-vous vérifier le VIN d'un de ces véhicules ou les comparer entre eux ?",
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
                "response": geo_response.text + "\n\nSouhaitez-vous que je vérifie le VIN d'un de ces véhicules, ou voulez-vous les comparer entre eux ?",
                "urls_found": search_result.get("urls_found", []),
                "scraped_count": search_result.get("scraped_count", 0),
                "source": "serpapi"
            }

    else:
        # ─── CHAT — conseils, fiabilité, prix, etc. ───
        ud = session["user_data"]

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